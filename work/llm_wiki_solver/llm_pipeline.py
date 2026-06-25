from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .llm_client import LLMResponseError, LLMUnavailable
from .models import DocumentRecord, Question
from .permissions import PermissionGuard
from .search import extract_candidate_filename, find_documents_by_filename, normalize_for_match
from .policy import DENY_ANSWER


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    answer_format: str = "datas"
    subqueries: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    needs_repair: bool = False
    needs_execution: bool = False
    confidence: float = 0.0


@dataclass(frozen=True)
class ChunkRecord:
    source: str
    chunk_id: str
    text: str
    headings: list[str] = field(default_factory=list)
    token_estimate: int = 0


@dataclass(frozen=True)
class FactRecord:
    source: str
    fact_type: str
    text: str
    assignee: str | None = None
    end_date: str | None = None
    location: str = ""


@dataclass(frozen=True)
class EvidenceCard:
    source: str
    evidence_type: str
    text: str
    score: float
    safety_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RepairPlan:
    source: str
    target: str
    operations: list[dict[str, Any]]
    confidence: float = 0.0


@dataclass(frozen=True)
class AnswerDraft:
    answer: dict[str, Any]
    evidence_sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    repaired_answer: dict[str, Any] | None = None


@dataclass(frozen=True)
class LocalIndex:
    chunks: list[ChunkRecord]
    facts: list[FactRecord]
    summaries: dict[str, str]


@dataclass(frozen=True)
class PipelineResult:
    answer: dict[str, Any]
    trace: dict[str, Any]


class JsonLLM(Protocol):
    def available(self) -> bool:
        ...

    def complete_json(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


def query_plan_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "intent",
            "answer_format",
            "subqueries",
            "filters",
            "needs_repair",
            "needs_execution",
            "confidence",
        ],
        "properties": {
            "intent": {"type": "string"},
            "answer_format": {"type": "string"},
            "subqueries": {"type": "array", "items": {"type": "string"}},
            "filters": {"type": "object"},
            "needs_repair": {"type": "boolean"},
            "needs_execution": {"type": "boolean"},
            "confidence": {"type": "number"},
        },
    }


def answer_draft_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "evidence_sources", "confidence", "warnings"],
        "properties": {
            "answer": {"type": "object"},
            "evidence_sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    }


def repair_plan_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["source", "target", "operations", "confidence"],
        "properties": {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["op"],
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": [
                                "copy_file",
                                "replace_text",
                                "insert_text",
                                "delete_text",
                                "append_text",
                            ],
                        },
                        "old": {"type": "string"},
                        "new": {"type": "string"},
                        "text": {"type": "string"},
                        "location": {"type": "string"},
                        "path": {"type": "string"},
                    },
                },
            },
            "confidence": {"type": "number"},
        },
    }


def build_local_index(records: list[DocumentRecord]) -> LocalIndex:
    chunks: list[ChunkRecord] = []
    facts: list[FactRecord] = []
    summaries: dict[str, str] = {}
    for record in records:
        summaries[record.rel_path] = _summarize(record.text)
        for idx, text in enumerate(_chunk_text(record.text), start=1):
            chunks.append(
                ChunkRecord(
                    source=record.rel_path,
                    chunk_id=f"{record.rel_path}#{idx}",
                    text=text,
                    headings=_extract_headings(text),
                    token_estimate=max(1, len(text) // 4),
                )
            )
        for comment in [*record.todos, *record.comments]:
            facts.append(
                FactRecord(
                    source=record.rel_path,
                    fact_type=comment.kind,
                    text=comment.text,
                    assignee=comment.assignee,
                    end_date=comment.end_date,
                    location=comment.location,
                )
            )
    return LocalIndex(chunks=chunks, facts=facts, summaries=summaries)


class EvidenceRetriever:
    def __init__(self, index: LocalIndex):
        self.index = index

    def retrieve(self, subqueries: list[str], limit: int = 8) -> list[EvidenceCard]:
        queries = [query for query in subqueries if query.strip()]
        fused: dict[tuple[str, str, str], EvidenceCard] = {}
        for query in queries:
            per_query = self._rank_for_query(query)
            for rank, card in enumerate(per_query[: max(3, limit)], start=1):
                fusion_score = card.score + 1.0 / (50 + rank)
                key = (card.source, card.evidence_type, card.text)
                existing = fused.get(key)
                if existing is None or fusion_score > existing.score:
                    fused[key] = EvidenceCard(
                        source=card.source,
                        evidence_type=card.evidence_type,
                        text=card.text,
                        score=fusion_score,
                        safety_flags=card.safety_flags,
                    )
        cards = sorted(fused.values(), key=lambda card: (-card.score, card.source, card.evidence_type))
        return cards[:limit]

    def _rank_for_query(self, query: str) -> list[EvidenceCard]:
        candidates: list[EvidenceCard] = []
        query_tokens = _tokens(query)
        for fact in self.index.facts:
            score = _score_text(query, f"{fact.source}\n{fact.text}\n{fact.assignee or ''}")
            if score:
                bonus = _source_bonus(fact.source, query_tokens)
                candidates.append(EvidenceCard(fact.source, "fact", fact.text, score + 2.0 + bonus))
        for chunk in self.index.chunks:
            score = _score_text(query, f"{chunk.source}\n{chunk.text}\n{' '.join(chunk.headings)}")
            if score:
                bonus = _source_bonus(chunk.source, query_tokens)
                candidates.append(EvidenceCard(chunk.source, "chunk", chunk.text, score + bonus))
        for source, summary in self.index.summaries.items():
            score = _score_text(query, f"{source}\n{summary}")
            if score:
                bonus = _source_bonus(source, query_tokens)
                candidates.append(EvidenceCard(source, "summary", summary, score + 0.5 + bonus))
        candidates.sort(key=lambda card: (-card.score, card.source, card.evidence_type))
        return candidates


class QuestionPlanner:
    def __init__(self, llm_client: JsonLLM):
        self.llm_client = llm_client

    def plan(self, question: Question, fallback_answer: dict[str, Any]) -> QueryPlan:
        raw = self.llm_client.complete_json(_planner_prompt(question, fallback_answer), schema=query_plan_schema())
        return QueryPlan(
            intent=str(raw.get("intent", "knowledge_query")),
            answer_format=str(raw.get("answer_format", _infer_answer_format(fallback_answer))),
            subqueries=[str(item) for item in raw.get("subqueries", [question.title])],
            filters=dict(raw.get("filters", {})),
            needs_repair=bool(raw.get("needs_repair", False)),
            needs_execution=bool(raw.get("needs_execution", False)),
            confidence=float(raw.get("confidence", 0.0)),
        )


class EvidenceJudge:
    def enough(self, plan: QueryPlan, cards: list[EvidenceCard]) -> bool:
        if plan.intent in {"knowledge_query", "repair"}:
            return bool(cards)
        return len(cards) >= 1


class AnswerComposer:
    def __init__(self, llm_client: JsonLLM):
        self.llm_client = llm_client

    def compose(self, question: Question, plan: QueryPlan, cards: list[EvidenceCard]) -> AnswerDraft:
        raw = self.llm_client.complete_json(_composer_prompt(question, plan, cards), schema=answer_draft_schema())
        return AnswerDraft(
            answer=dict(raw.get("answer", {})),
            evidence_sources=[str(item) for item in raw.get("evidence_sources", [])],
            confidence=float(raw.get("confidence", 0.0)),
            warnings=[str(item) for item in raw.get("warnings", [])],
        )


class RepairPlanner:
    def __init__(self, llm_client: JsonLLM):
        self.llm_client = llm_client

    def plan(
        self,
        question: Question,
        query_plan: QueryPlan,
        cards: list[EvidenceCard],
        fallback_answer: dict[str, Any],
    ) -> RepairPlan:
        raw = self.llm_client.complete_json(
            _repair_prompt(question, query_plan, cards, fallback_answer),
            schema=repair_plan_schema(),
        )
        return RepairPlan(
            source=str(raw.get("source", fallback_answer.get("source", ""))),
            target=str(raw.get("target", fallback_answer.get("target", ""))),
            operations=[dict(item) for item in raw.get("operations", []) if isinstance(item, dict)],
            confidence=float(raw.get("confidence", 0.0)),
        )


class AnswerValidator:
    def __init__(self, permission_guard: PermissionGuard, root: Path):
        self.permission_guard = permission_guard
        self.root = root

    def validate(self, answer: dict[str, Any], expected_format: str) -> ValidationReport:
        if not isinstance(answer, dict):
            return ValidationReport(False, ["answer_not_dict"], {"datas": []})
        safety_error = self._safety_error(answer)
        if safety_error:
            return ValidationReport(False, [safety_error], DENY_ANSWER)
        schema_errors = self._schema_errors(answer, expected_format)
        if schema_errors:
            return ValidationReport(False, schema_errors, self._repair_schema(answer, expected_format))
        return ValidationReport(True, [], answer)

    def _safety_error(self, answer: dict[str, Any]) -> str | None:
        serialized = json.dumps(answer, ensure_ascii=False)
        if self.permission_guard.is_denied_command(serialized):
            return "dangerous_command"
        for path_text in re.findall(r"docs/[^\s\"'，,。\\]+", serialized):
            if self.permission_guard.is_denied_path(path_text, operation="read"):
                return "denied_path"
        if any(word in serialized.casefold() for word in ("root密码", "数据库密码", "api_key", "secret_key")):
            return "sensitive_secret"
        return None

    @staticmethod
    def _schema_errors(answer: dict[str, Any], expected_format: str) -> list[str]:
        if expected_format == "error":
            return [] if set(answer) == {"error_msg"} else ["expected_error_msg"]
        if expected_format == "count":
            return [] if set(answer) == {"count"} and isinstance(answer["count"], int) else ["expected_count"]
        if expected_format == "repair":
            required = {"source", "target"}
            return [] if required.issubset(answer) else ["expected_source_target"]
        if expected_format in {"datas", "knowledge_query"}:
            return [] if set(answer) == {"datas"} and isinstance(answer["datas"], list) else ["expected_datas"]
        if "datas" in answer or "count" in answer or {"source", "target"}.issubset(answer):
            return []
        return ["unknown_answer_format"]

    @staticmethod
    def _repair_schema(answer: dict[str, Any], expected_format: str) -> dict[str, Any]:
        if expected_format == "count":
            return {"count": int(answer.get("count", 0)) if str(answer.get("count", "")).isdigit() else 0}
        if expected_format == "repair" and {"source", "target"}.issubset(answer):
            return {"source": answer["source"], "target": answer["target"]}
        return {"datas": answer.get("datas", []) if isinstance(answer.get("datas"), list) else []}


class ComplexUnderstandingPipeline:
    def __init__(
        self,
        records: list[DocumentRecord],
        permission_guard: PermissionGuard,
        llm_client: JsonLLM,
        root: Path | None = None,
        llm_mode: str = "auto",
    ):
        self.records = records
        self.permission_guard = permission_guard
        self.llm_client = llm_client
        self.root = root or Path(".")
        self.llm_mode = llm_mode
        self.index = build_local_index(records)
        self.retriever = EvidenceRetriever(self.index)
        self.planner = QuestionPlanner(llm_client)
        self.repair_planner = RepairPlanner(llm_client)
        self.judge = EvidenceJudge()
        self.composer = AnswerComposer(llm_client)
        self.validator = AnswerValidator(permission_guard, self.root)

    def solve(self, question: Question, fallback_answer: dict[str, Any]) -> PipelineResult:
        trace: dict[str, Any] = {
            "llm_mode": self.llm_mode,
            "llm_used": False,
            "fallback_reason": None,
        }
        if self.llm_mode == "off":
            trace["fallback_reason"] = "llm_off"
            return PipelineResult(fallback_answer, trace)
        if not self.llm_client.available():
            if self.llm_mode == "required":
                trace["fallback_reason"] = "llm_unavailable_required"
                return PipelineResult({"datas": []}, trace)
            trace["fallback_reason"] = "llm_unavailable_auto"
            return PipelineResult(fallback_answer, trace)

        try:
            plan = self.planner.plan(question, fallback_answer)
            cards = self.retriever.retrieve(plan.subqueries or [question.title], limit=8)
            if not self.judge.enough(plan, cards):
                cards = self.retriever.retrieve([question.title, *plan.subqueries], limit=8)
            trace["plan"] = asdict(plan)
            trace["evidence_sources"] = [card.source for card in cards]
            if plan.needs_repair or plan.intent == "repair" or plan.answer_format == "repair":
                repair_plan = self.repair_planner.plan(question, plan, cards, fallback_answer)
                trace["repair_plan"] = asdict(repair_plan)
                candidate, repair_applied, repair_fallback_reason = self._apply_repair_plan(repair_plan, fallback_answer)
                trace["repair_applied"] = repair_applied
                if repair_fallback_reason:
                    trace["repair_fallback_reason"] = repair_fallback_reason
                report = self.validator.validate(candidate, "repair")
                if not report.ok:
                    trace["repair_fallback_reason"] = ",".join(report.errors)
                    candidate = self._safe_repair_fallback(fallback_answer)
                    report = self.validator.validate(candidate, "repair")
                    trace["repair_applied"] = False
                trace["validation"] = asdict(report)
                trace["llm_used"] = True
                return PipelineResult(report.repaired_answer or candidate, trace)
            draft = self.composer.compose(question, plan, cards)
            report = self.validator.validate(draft.answer, plan.answer_format)
        except (LLMUnavailable, LLMResponseError, ValueError, TypeError) as exc:
            if self.llm_mode == "required":
                trace["fallback_reason"] = f"llm_error_required:{type(exc).__name__}"
                return PipelineResult({"datas": []}, trace)
            trace["fallback_reason"] = f"llm_error_auto:{type(exc).__name__}"
            return PipelineResult(fallback_answer, trace)

        trace.update(
            {
                "llm_used": True,
                "validation": asdict(report),
            }
        )
        return PipelineResult(report.repaired_answer or draft.answer, trace)

    def _apply_repair_plan(
        self,
        repair_plan: RepairPlan,
        fallback_answer: dict[str, Any],
    ) -> tuple[dict[str, Any], bool, str | None]:
        source_rel = repair_plan.source or str(fallback_answer.get("source", ""))
        target_rel = repair_plan.target or str(fallback_answer.get("target", ""))
        if not source_rel or not target_rel:
            return self._safe_repair_fallback(fallback_answer), False, "missing_source_or_target"
        safety_error = self._repair_safety_error(source_rel, target_rel, repair_plan.operations)
        if safety_error:
            return self._safe_repair_fallback(fallback_answer), False, safety_error

        source_path = self._resolve_path(source_rel)
        target_path = self._resolve_path(target_rel)
        if source_path is None or target_path is None:
            return self._safe_repair_fallback(fallback_answer), False, "invalid_path"

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.suffix.lower() in {".md", ".txt", ".py", ".js", ".java", ".html", ".xml", ".json", ".yaml", ".yml"}:
            text = source_path.read_text(encoding="utf-8", errors="ignore")
            patched = self._apply_text_operations(text, repair_plan.operations)
            target_path.write_text(patched, encoding="utf-8")
            return {"source": source_rel, "target": target_rel}, True, None

        if source_path.suffix.lower() in {".docx", ".pptx", ".xlsx"} and zipfile.is_zipfile(source_path):
            applied = self._apply_ooxml_operations(source_path, target_path, repair_plan.operations)
            return (
                {"source": source_rel, "target": target_rel},
                applied,
                None if applied else "ooxml_no_matching_text",
            )

        shutil.copy2(source_path, target_path)
        return {"source": source_rel, "target": target_rel}, True, "binary_copied_only"

    def _repair_safety_error(
        self,
        source_rel: str,
        target_rel: str,
        operations: list[dict[str, Any]],
    ) -> str | None:
        if not source_rel.replace("\\", "/").lstrip("./").startswith("docs/"):
            return "source_outside_docs"
        target_norm = target_rel.replace("\\", "/").lstrip("./")
        if not target_norm.startswith("output/fixed/"):
            return "target_outside_fixed_dir"
        if self.permission_guard.is_denied_path(source_rel, operation="read"):
            return "denied_source_path"
        if self.permission_guard.is_denied_path(target_rel, operation="write"):
            return "denied_target_path"
        serialized = json.dumps(operations, ensure_ascii=False)
        if self.permission_guard.is_denied_command(serialized) or _operations_contain_dangerous_command(operations):
            return "dangerous_repair_operation"
        if any(word in serialized.casefold() for word in ("root密码", "数据库密码", "api_key", "secret_key")):
            return "sensitive_repair_operation"
        for operation in operations:
            path_text = str(operation.get("path", ""))
            if path_text and not path_text.replace("\\", "/").lstrip("./").startswith("output/fixed/"):
                return "operation_path_outside_fixed_dir"
        return None

    def _resolve_path(self, rel_path: str) -> Path | None:
        rel_path = rel_path.replace("\\", "/").lstrip("./")
        if rel_path.startswith("docs/") or rel_path.startswith("output/"):
            candidate = (self.root / rel_path).resolve()
            try:
                candidate.relative_to(self.root.resolve())
            except ValueError:
                return None
            return candidate
        return None

    @staticmethod
    def _apply_text_operations(text: str, operations: list[dict[str, Any]]) -> str:
        result = text
        for operation in operations:
            op = str(operation.get("op", "")).strip()
            if op == "copy_file":
                continue
            if op == "replace_text":
                old = str(operation.get("old", ""))
                new = str(operation.get("new", ""))
                if old:
                    result = result.replace(old, new)
                continue
            if op == "insert_text":
                location = str(operation.get("location", "")).strip()
                text_to_insert = str(operation.get("text", ""))
                if location and location in result:
                    result = result.replace(location, f"{location}{text_to_insert}", 1)
                else:
                    result = f"{result}{text_to_insert}"
                continue
            if op == "delete_text":
                old = str(operation.get("old", ""))
                if old:
                    result = result.replace(old, "")
                continue
            if op == "append_text":
                result = f"{result}{str(operation.get('text', ''))}"
        return result

    def _apply_ooxml_operations(
        self,
        source_path: Path,
        target_path: Path,
        operations: list[dict[str, Any]],
    ) -> bool:
        applied = False
        with zipfile.ZipFile(source_path, "r") as source_zip, zipfile.ZipFile(target_path, "w") as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info.filename)
                if info.filename.endswith(".xml"):
                    original = data.decode("utf-8", errors="ignore")
                    patched = self._apply_text_operations(original, operations)
                    if patched != original:
                        data = patched.encode("utf-8")
                        applied = True
                target_zip.writestr(info, data)
        return applied

    def _safe_repair_fallback(self, fallback_answer: dict[str, Any]) -> dict[str, Any]:
        source = str(fallback_answer.get("source", ""))
        target = str(fallback_answer.get("target", ""))
        if source and target:
            return {"source": source, "target": target}
        return {"datas": []}


def should_use_llm(question: Question, fallback_answer: dict[str, Any], llm_mode: str) -> bool:
    if llm_mode == "off":
        return False
    title = question.title
    if question.level == "困难":
        return True
    if fallback_answer == {"datas": []}:
        return True
    complex_words = ["涉及", "总结", "分析", "完成", "根据", "为什么", "如何", "对比", "关联"]
    return any(word in title for word in complex_words)


def _operations_contain_dangerous_command(operations: list[dict[str, Any]]) -> bool:
    for operation in operations:
        for key in ("old", "new", "text", "location", "path"):
            if _contains_dangerous_command(str(operation.get(key, ""))):
                return True
    return False


def _contains_dangerous_command(text: str) -> bool:
    return bool(
        re.search(
            r"(?<![A-Za-z0-9_-])(?:rm|rmdir|del|erase|remove-item|format|mkfs|shutdown|reboot|kill|taskkill)(?![A-Za-z0-9_-])",
            text,
            flags=re.IGNORECASE,
        )
    )


def _chunk_text(text: str, max_chars: int = 700) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not cleaned:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 > max_chars and current:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip() if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _extract_headings(text: str) -> list[str]:
    return [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.lstrip().startswith("#") and line.lstrip("#").strip()
    ]


def _summarize(text: str, max_chars: int = 220) -> str:
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _score_text(query: str, text: str) -> float:
    tokens = _tokens(query)
    haystack = normalize_for_match(text)
    score = 0.0
    for token in tokens:
        if token in haystack:
            score += 1.0
    for token in tokens:
        if len(token) >= 2 and token in haystack:
            score += 0.5
    return score


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9_#:/.\-]+|[\u4e00-\u9fff]{2,}", text)
    return [normalize_for_match(item) for item in raw if len(item.strip()) >= 2]


def _source_bonus(source: str, query_tokens: list[str]) -> float:
    lower_source = normalize_for_match(source)
    bonus = 0.0
    if "业务总结" in source:
        bonus += 1.5
    if "需求设计" in source:
        bonus += 0.5
    if any(token in lower_source for token in query_tokens):
        bonus += 1.0
    return bonus


def _planner_prompt(question: Question, fallback_answer: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Plan local evidence retrieval for an LLM Wiki question. Return JSON only.",
            "question": {"id": question.id, "title": question.title, "level": question.level},
            "fallback_answer": fallback_answer,
            "schema": {
                "intent": "knowledge_query|repair|todo_query|file_query",
                "answer_format": "datas|count|repair|error",
                "subqueries": ["string"],
                "filters": {},
                "needs_repair": False,
                "needs_execution": False,
                "confidence": 0.0,
            },
        },
        ensure_ascii=False,
    )


def _composer_prompt(question: Question, plan: QueryPlan, cards: list[EvidenceCard]) -> str:
    evidence = [
        {
            "source": card.source,
            "evidence_type": card.evidence_type,
            "text": card.text,
            "score": card.score,
        }
        for card in cards
    ]
    return json.dumps(
        {
            "task": "Compose the final answer using only evidence. Return JSON only.",
            "question": {"id": question.id, "title": question.title, "level": question.level},
            "plan": asdict(plan),
            "untrusted_evidence": evidence,
            "output_schema": {
                "answer": {},
                "evidence_sources": ["docs/path"],
                "confidence": 0.0,
                "warnings": [],
            },
        },
        ensure_ascii=False,
    )


def _repair_prompt(
    question: Question,
    plan: QueryPlan,
    cards: list[EvidenceCard],
    fallback_answer: dict[str, Any],
) -> str:
    evidence = [
        {
            "source": card.source,
            "evidence_type": card.evidence_type,
            "text": card.text,
            "score": card.score,
        }
        for card in cards
    ]
    return json.dumps(
        {
            "task": "Create a structured repair plan for the file repair question. Return JSON only.",
            "question": {"id": question.id, "title": question.title, "level": question.level},
            "plan": asdict(plan),
            "fallback_answer": fallback_answer,
            "untrusted_evidence": evidence,
            "output_schema": {
                "source": "docs/path",
                "target": "output/fixed/path",
                "operations": [
                    {
                        "op": "copy_file|replace_text|insert_text|delete_text|append_text",
                        "old": "string",
                        "new": "string",
                        "text": "string",
                        "location": "string",
                        "path": "string",
                    }
                ],
                "confidence": 0.0,
            },
        },
        ensure_ascii=False,
    )


def _infer_answer_format(answer: dict[str, Any]) -> str:
    if "error_msg" in answer:
        return "error"
    if "count" in answer:
        return "count"
    if {"source", "target"}.issubset(answer):
        return "repair"
    return "datas"
