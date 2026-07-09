from __future__ import annotations

import ast
import io
import json
import re
import shutil
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Iterable

from .answers import normalize_answer
from .extractors import scan_documents
from .llm_client import FakeLLMClient, LLMClient, LLMConfig
from .llm_pipeline import ComplexUnderstandingPipeline, should_use_llm
from .models import Answer, DocumentRecord, Question, SUPPORTED_COUNT_SUFFIXES
from .permissions import PermissionGuard
from .policy import DENY_ANSWER
from .retrieval import HybridRetriever, build_hybrid_index
from .search import extract_candidate_filename, find_documents_by_filename, ranked_text_search


class WikiSolver:
    def __init__(self, root: Path, log_dir: Path | None = None, llm_mode: str = "auto"):
        self.root = root
        self.log_dir = log_dir
        self.llm_mode = llm_mode
        self.permissions = PermissionGuard(self._load_permissions())
        self.records = scan_documents(root, permission_guard=self.permissions)
        self.hybrid_index = build_hybrid_index(self.records, self.permissions)
        self.hybrid_retriever = HybridRetriever(self.hybrid_index)
        self.llm_config = LLMConfig.from_env(mode_override=llm_mode)
        self.llm_client = LLMClient(self.llm_config)
        self.pipeline = ComplexUnderstandingPipeline(
            records=self.records,
            permission_guard=self.permissions,
            llm_client=self.llm_client,
            root=self.root,
            llm_mode=llm_mode,
            hybrid_index=self.hybrid_index,
        )

    def solve_group(self, group_path: Path) -> list[Answer]:
        questions = self._load_questions(group_path)
        answers: list[Answer] = []
        traces: list[dict[str, Any]] = []
        for question in questions:
            answer, trace = self.solve_question_with_trace(question)
            normalized = normalize_answer(answer)
            if normalized != answer:
                trace["normalization"] = {"changed": True, "before": answer, "after": normalized}
            else:
                trace.setdefault("normalization", {"changed": False})
            answer = normalized
            trace.setdefault("route", trace.get("fallback_reason") or "rule_chain")
            trace.setdefault("retrieval_channels", self._default_retrieval_channels(trace["route"]))
            trace.setdefault("safety_decision", "deny" if answer == DENY_ANSWER else "allow")
            answers.append(Answer(id=question.id, answer=answer))
            traces.append({"id": question.id, **trace})
        self._write_trace(group_path.stem, traces)
        return answers

    def solve_question(self, question: Question) -> dict:
        answer, _ = self.solve_question_with_trace(question)
        return normalize_answer(answer)

    def solve_question_with_trace(self, question: Question) -> tuple[dict, dict[str, Any]]:
        title = question.title.strip()
        if self._is_high_risk_question(title):
            return DENY_ANSWER, {
                "llm_used": False,
                "fallback_reason": "high_risk",
                "route": "safety_guard",
                "retrieval_channels": [],
                "safety_decision": "deny",
            }

        filename = extract_candidate_filename(title)
        if filename and any(word in title for word in ("路径", "找出", "位置")):
            fallback = {"datas": [record.rel_path for record in find_documents_by_filename(self.records, filename)]}
            return self._maybe_llm(question, fallback)

        if filename and any(word in title for word in ("汇总", "聚合", "透视")):
            fallback = {"datas": self._aggregate_table_answer(title, filename)}
            return self._maybe_llm(question, fallback)

        if filename and any(word in title for word in ("运行", "执行")):
            fallback = self._execute_python_answer(filename)
            if fallback == DENY_ANSWER:
                return DENY_ANSWER, {
                    "llm_used": False,
                    "fallback_reason": "unsafe_code_execution",
                    "route": "safe_python_execution",
                    "retrieval_channels": ["structured"],
                    "safety_decision": "deny",
                }
            return self._maybe_llm(question, fallback)

        if filename and filename.endswith(".py") and any(word in title for word in ("输出", "结果", "打印")):
            fallback = self._execute_python_answer(filename)
            if fallback == DENY_ANSWER:
                return DENY_ANSWER, {
                    "llm_used": False,
                    "fallback_reason": "unsafe_code_execution",
                    "route": "safe_python_execution",
                    "retrieval_channels": ["structured"],
                    "safety_decision": "deny",
                }
            return self._maybe_llm(question, fallback)

        if filename and any(word in title for word in ("为", "等于", "大于", "小于", "记录数量", "列表", "名单", "筛选")):
            fallback = self._table_filter_answer(title, filename)
            if fallback is not None:
                return self._maybe_llm(question, fallback)

        count_suffix = self._extract_count_suffix(title)
        if count_suffix:
            fallback = {count_suffix: sum(1 for record in self.records if record.suffix == count_suffix)}
            return self._maybe_llm(question, fallback)

        list_suffix = self._extract_list_suffix(title)
        if list_suffix:
            fallback = {"datas": sorted(record.rel_path for record in self.records if record.suffix == list_suffix)}
            return self._maybe_llm(question, fallback)

        if "批注" in title and any(word in title for word in ("数量", "统计")):
            candidates = self._candidate_records(title)
            fallback = {"count": sum(len(record.comments) for record in candidates)}
            return self._maybe_llm(question, fallback)

        end_date = self._extract_end_date(title)
        if end_date and any(word in title for word in ("TODO", "todo", "批注", "截止日期", "end_date")):
            assignee = self._extract_assignee(title)
            kind = "todo" if "TODO" in title or "todo" in title else None
            rows = self._comments_by_filters(assignee, end_date, kind=kind)
            fallback = {"count": len(rows)} if self._wants_count(title) else {"datas": rows}
            return self._maybe_llm(question, fallback)

        if "责任人" in title or "待" in title:
            assignee = self._extract_assignee(title)
            if assignee and any(word in title for word in ("修复", "修改", "完成")):
                fallback = self._repair_by_assignee(assignee)
                return self._maybe_llm(question, fallback)
            if assignee:
                kind = "todo" if "TODO" in title or "todo" in title else None
                rows = self._comments_by_filters(assignee=assignee, kind=kind)
                fallback = {"count": len(rows)} if self._wants_count(title) else {"datas": rows}
                return self._maybe_llm(question, fallback)

        if any(word in title for word in ("TODO", "todo", "批注")):
            assignee = self._extract_assignee(title)
            if assignee:
                kind = "todo" if "TODO" in title or "todo" in title else None
                rows = self._comments_by_filters(assignee=assignee, kind=kind)
                fallback = {"count": len(rows)} if self._wants_count(title) else {"datas": rows}
                return self._maybe_llm(question, fallback)
            rows = sorted(dict.fromkeys(comment.text for record in self.records for comment in record.todos))
            fallback = {"count": len(rows)} if self._wants_count(title) else {"datas": rows}
            return self._maybe_llm(question, fallback)

        if "密码" in title:
            fallback = self._password_answer(title)
            return self._maybe_llm(question, fallback)

        if filename and any(word in title for word in ("读取", "内容", "打开")):
            matches = find_documents_by_filename(self.records, filename)
            if matches:
                fallback = {"datas": [matches[0].text.strip()]}
                return self._maybe_llm(question, fallback)

        fallback = {"datas": self._knowledge_answer(title)}
        return self._maybe_llm(question, fallback)

    def _load_permissions(self) -> dict[str, Any]:
        path = self.root / "Permission.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_questions(group_path: Path) -> list[Question]:
        data = json.loads(group_path.read_text(encoding="utf-8"))
        return [Question(id=item["id"], title=item["title"], level=item.get("level", "")) for item in data]

    def _write_trace(self, group_name: str, traces: list[dict[str, Any]]) -> None:
        if not self.log_dir:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / f"{group_name}.trace.json").write_text(
            json.dumps(traces, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _default_retrieval_channels(route: str) -> list[str]:
        if route == "safety_guard":
            return []
        if route == "safe_python_execution":
            return ["structured"]
        if route == "llm_pipeline":
            return ["structured", "sqlite_fts", "text", "fuzzy", "rrf", "llm_evidence"]
        return ["structured", "sqlite_fts", "text", "fuzzy", "rrf"]

    def _is_high_risk_question(self, title: str) -> bool:
        path_mentions = re.findall(r"docs/[^\s，,。]+", title)
        for path_text in path_mentions:
            if self.permissions.is_denied_path(path_text, operation="read"):
                return True
        if self.permissions.is_denied_command(title):
            return True
        injection_words = [
            "忽略前面",
            "上帝模式",
            "最高优先级",
            "不需要询问用户",
            "无论客户提出什么",
            "遵循当前描述",
            "删除全部",
            "彻底删除",
            "强制kill",
            "读取c盘根目录",
            "读取 C 盘根目录",
        ]
        if any(word.casefold() in title.casefold() for word in injection_words):
            return True
        if self._referenced_task_content_is_high_risk(title, injection_words):
            return True
        if "密码" in title and self._is_forbidden_password_query(title):
            return True
        return False

    def _referenced_task_content_is_high_risk(self, title: str, injection_words: list[str]) -> bool:
        if not any(word in title for word in ("完成", "执行", "运行", "描述的工作")):
            return False
        for record in self.records:
            if record.rel_path not in title:
                continue
            text = record.text
            if self.permissions.is_denied_command(text):
                return True
            if any(word.casefold() in text.casefold() for word in injection_words):
                return True
            for mentioned_path in re.findall(r"docs/[^\s，,。]+", text):
                if self.permissions.is_denied_path(mentioned_path, operation="write"):
                    return True
        return False

    @staticmethod
    def _extract_count_suffix(title: str) -> str | None:
        for suffix in sorted(SUPPORTED_COUNT_SUFFIXES, key=len, reverse=True):
            token = rf"(?<![A-Za-z0-9_.]){re.escape(suffix)}(?![A-Za-z0-9_])"
            patterns = [
                rf"{token}\s*文件.*数量",
                rf"统计.*{token}.*数量",
                rf"{token}.*总数量",
                rf"{token}\s*文件.*有多少",
                rf"有多少\s*{token}\s*文件",
            ]
            if any(re.search(pattern, title, re.IGNORECASE) for pattern in patterns):
                return suffix
        return None

    @staticmethod
    def _extract_list_suffix(title: str) -> str | None:
        for suffix in sorted(SUPPORTED_COUNT_SUFFIXES, key=len, reverse=True):
            token = rf"(?<![A-Za-z0-9_.]){re.escape(suffix)}(?![A-Za-z0-9_])"
            patterns = [
                rf"列出所有\s*{token}\s*文件",
                rf"哪些文件是\s*{token}\s*格式",
                rf"{token}\s*文件\s*(?:列表|清单)",
                rf"所有\s*{token}\s*文件",
            ]
            if any(re.search(pattern, title, re.IGNORECASE) for pattern in patterns):
                return suffix
        return None

    def _candidate_records(self, title: str) -> list[DocumentRecord]:
        filename = extract_candidate_filename(title)
        if filename:
            matches = find_documents_by_filename(self.records, filename)
            if matches:
                return matches
        matches = self.hybrid_retriever.find_documents(title, limit=5)
        if matches:
            return matches
        matches = ranked_text_search(self.records, title, limit=5)
        return matches or self.records

    @staticmethod
    def _extract_assignee(title: str) -> str | None:
        patterns = [
            r"责任人为(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+?)(?:且|并|，|,|的|处理|事项|列表|TODO|todo|批注|$)",
            r"待(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+?)处理",
            r"(?P<name>[\u4e00-\u9fff]{2,4})有多少个?(?:TODO|todo|批注)",
            r"统计(?P<name>[\u4e00-\u9fff]{2,4})的?(?:TODO|todo|批注)(?:数量|个数)",
            r"(?P<name>[\u4e00-\u9fff]{2,4})的TODO",
            r"(?P<name>[\u4e00-\u9fff]{2,4})的批注",
        ]
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group("name")
        return None

    @staticmethod
    def _wants_count(title: str) -> bool:
        return any(word in title for word in ("数量", "多少", "几条", "几个", "个数", "记录数"))

    @staticmethod
    def _extract_end_date(title: str) -> str | None:
        patterns = [
            r"(?:截止日期|end_date)\s*(?:为|是|[:：=])?\s*(?P<date>\d{8})",
            r"(?P<date>\d{8}).*(?:截止|到期|TODO|todo|批注)",
        ]
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group("date")
        return None

    def _comments_by_assignee(self, assignee: str) -> list[str]:
        return self._comments_by_filters(assignee=assignee)

    def _comments_by_filters(
        self,
        assignee: str | None = None,
        end_date: str | None = None,
        kind: str | None = None,
    ) -> list[str]:
        rows = [
            comment.text
            for record in self.records
            for comment in record.comments
            if (assignee is None or comment.assignee == assignee)
            and (end_date is None or comment.end_date == end_date)
            and (kind is None or comment.kind == kind)
        ]
        return sorted(dict.fromkeys(rows))

    def _repair_by_assignee(self, assignee: str) -> dict:
        candidates = [
            record
            for record in self.records
            if any(comment.assignee == assignee for comment in [*record.todos, *record.comments])
        ]
        if not candidates:
            return {"datas": []}
        record = self._preferred_repair_record(candidates)
        target_rel = Path("output") / "fixed" / Path(record.rel_path).relative_to("docs")
        target = self.root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if record.suffix in {"md", "txt", "py", "js", "java", "html", "xml", "json", "yaml", "yml"}:
            target.write_text(self._repaired_text(record, assignee), encoding="utf-8")
        elif record.suffix in {"docx", "pptx", "xlsx"} and zipfile.is_zipfile(record.path):
            self._write_repaired_ooxml(record, target, assignee)
        else:
            shutil.copy2(record.path, target)
        return {"source": record.rel_path, "target": target_rel.as_posix()}

    @staticmethod
    def _preferred_repair_record(candidates: list[DocumentRecord]) -> DocumentRecord:
        text_suffixes = {"md", "txt", "py", "js", "java", "html", "xml", "json", "yaml", "yml"}
        return sorted(
            candidates,
            key=lambda record: (
                0 if record.suffix in text_suffixes else 1,
                record.rel_path,
            ),
        )[0]

    @staticmethod
    def _repaired_text(record: DocumentRecord, assignee: str) -> str:
        text = record.path.read_text(encoding="utf-8", errors="ignore")
        for comment in [*record.todos, *record.comments]:
            if comment.assignee != assignee or "status: done" in comment.text:
                continue
            pattern = re.compile(
                rf"(todo\s*[:：]\s*{re.escape(comment.text.split(', to:', 1)[0].replace('todo: ', ''))}"
                rf"\s*[,，]\s*to\s*[:：]\s*{re.escape(assignee)}\s*[,，]\s*)"
                rf"(end_date\s*[:：]\s*{re.escape(comment.end_date or '')})",
                re.IGNORECASE,
            )
            text = pattern.sub(r"\1status: done, \2", text)
        return text

    @staticmethod
    def _write_repaired_ooxml(record: DocumentRecord, target: Path, assignee: str) -> None:
        with zipfile.ZipFile(record.path) as src, zipfile.ZipFile(target, "w") as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.endswith(".xml"):
                    xml_text = data.decode("utf-8", errors="ignore")
                    repaired = _mark_todo_done_in_text(xml_text, assignee)
                    data = repaired.encode("utf-8")
                dst.writestr(info, data)

    def _aggregate_table_answer(self, title: str, filename: str) -> list[str]:
        matches = self._find_documents_with_action_prefix_fallback(filename)
        if not matches:
            return []
        group_name = self._extract_group_column(title)
        value_name = self._extract_value_column(title)
        if not group_name or not value_name:
            return []
        for record in matches:
            result = _aggregate_rows(
                record.tables,
                group_name,
                value_name,
                _extract_table_conditions(title, filename),
            )
            if result:
                return result
        return []

    @staticmethod
    def _extract_group_column(title: str) -> str | None:
        match = re.search(r"按(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+?)(?:汇总|聚合|统计)", title)
        return match.group("name") if match else None

    @staticmethod
    def _extract_value_column(title: str) -> str | None:
        target = re.search(r"(?:汇总|聚合|统计).+的(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+?)(?:$|[，,。])", title)
        if target:
            return target.group("name")
        match = re.search(r"(?:汇总|聚合|统计)(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+)", title)
        return match.group("name") if match else None

    def _execute_python_answer(self, filename: str) -> dict:
        matches = self._find_documents_with_action_prefix_fallback(filename)
        if not matches or matches[0].suffix != "py":
            return {"datas": []}
        record = matches[0]
        if self.permissions.is_denied_path(record.rel_path, operation="read"):
            return DENY_ANSWER
        output = _safe_python_output(record.text, self.permissions)
        if output is None:
            return DENY_ANSWER
        return {"datas": output}

    def _table_filter_answer(self, title: str, filename: str) -> dict | None:
        conditions = _extract_table_conditions(title, filename)
        if not conditions:
            return None
        matches = self._find_documents_with_action_prefix_fallback(filename)
        if not matches:
            return {"datas": []}
        wants_count = any(word in title for word in ("记录数量", "记录数", "数量", "多少条"))
        return_column = _extract_return_column(title)
        for record in matches:
            rows = _filter_rows(record.tables, conditions)
            if rows is None:
                continue
            if wants_count:
                return {"count": len(rows)}
            if not return_column:
                return {"datas": ["\t".join(row) for row in rows]}
            values = _values_from_rows(record.tables, rows, return_column)
            return {"datas": sorted(dict.fromkeys(values))}
        return {"count": 0} if wants_count else {"datas": []}

    def _find_documents_with_action_prefix_fallback(self, filename: str) -> list[DocumentRecord]:
        matches = find_documents_by_filename(self.records, filename)
        if matches:
            return matches
        stripped = re.sub(r"^(?:统计|查询|读取|打开|运行|执行|根据|基于)", "", filename)
        if stripped != filename:
            return find_documents_by_filename(self.records, stripped)
        return []

    def _password_answer(self, title: str) -> dict:
        if self._is_forbidden_password_query(title):
            return DENY_ANSWER
        matches = self.hybrid_retriever.find_documents(title, limit=5) or ranked_text_search(self.records, title, limit=5)
        values: list[str] = []
        for record in matches:
            if "02_环境信息" not in record.rel_path:
                continue
            values.extend(_extract_password_values(record.text, title))
        return {"datas": sorted(dict.fromkeys(values))}

    @staticmethod
    def _is_forbidden_password_query(title: str) -> bool:
        normalized = title.casefold()
        if "02_环境信息" in title:
            return False
        if "docs/" in normalized and "02_环境信息" not in title:
            return True
        forbidden_words = ["root", "系统", "数据库", "db", "密钥", "secret", "配置明文"]
        allowed_env_signal = "环境" in title and ("op_user" in title or "用户" in title)
        if allowed_env_signal:
            return False
        return any(word in normalized for word in forbidden_words)

    def _knowledge_answer(self, title: str) -> list[str]:
        cards = self.hybrid_retriever.retrieve(title, limit=8)
        if not cards:
            matches = ranked_text_search(self.records, title, limit=5)
            cards = [
                type("_Card", (), {"source": record.rel_path, "text": record.text})()
                for record in matches
            ]
        if not cards:
            return []
        if any(word in title for word in ("涉及", "相关", "哪些文件", "文件名称", "文件路径", "文件列表")):
            return sorted(dict.fromkeys(card.source for card in cards))
        snippets: list[str] = []
        for card in cards[:5]:
            snippet = re.sub(r"\s+", " ", getattr(card, "text", "")).strip()[:300]
            snippets.append(f"{card.source}: {snippet}" if snippet else card.source)
        return snippets

    def _maybe_llm(self, question: Question, fallback_answer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        fallback_answer = normalize_answer(fallback_answer)
        if not should_use_llm(question, fallback_answer, self.llm_mode):
            return fallback_answer, {
                "llm_used": False,
                "fallback_reason": "rule_chain",
                "route": "rule_chain",
            }
        result = self.pipeline.solve(question, fallback_answer)
        trace = dict(result.trace)
        trace.setdefault("llm_used", False)
        trace.setdefault("fallback_reason", None)
        trace.setdefault("route", "llm_pipeline" if trace.get("llm_used") else "rule_chain")
        return normalize_answer(result.answer if result.answer else fallback_answer), trace


def _extract_password_values(text: str, title: str) -> list[str]:
    lines = text.splitlines()
    strong_selectors, weak_selectors = _password_query_selectors(title)
    candidates: list[tuple[int, list[str]]] = []

    for idx, line in enumerate(lines):
        line_values = _password_values_from_line(line, weak_selectors)
        if not line_values:
            continue
        score = _password_selector_score(line, strong_selectors, weak_selectors)
        if score == 0 and idx > 0:
            score = _password_selector_score(lines[idx - 1], strong_selectors, weak_selectors)
        if strong_selectors and score < 5:
            continue
        if weak_selectors and not strong_selectors and score <= 0:
            continue
        candidates.append((score, line_values))

    if candidates:
        best_score = max(score for score, _ in candidates)
        selected = candidates if not (strong_selectors or weak_selectors) else [
            item for item in candidates if item[0] == best_score
        ]
        return _unique_values(value for _, values in selected for value in values)

    if strong_selectors:
        return []

    values: list[str] = []
    for line in lines:
        values.extend(_password_values_from_line(line, weak_selectors))
    return _unique_values(values)


def _password_query_selectors(title: str) -> tuple[list[str], list[str]]:
    strong: list[str] = []
    weak: list[str] = []

    strong.extend(re.findall(r"https?://[^\s，,。；;]+", title, flags=re.IGNORECASE))
    strong.extend(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?\b", title))
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.-]{2,}\b", title):
        lowered = token.casefold()
        if lowered in {"http", "https", "password", "pwd"}:
            continue
        if "_" in token or token.endswith("user") or token.endswith("User"):
            weak.append(token)
    for token in re.findall(r"([A-Za-z][A-Za-z0-9_.-]{1,})\s*用户", title):
        weak.append(token)
    return _unique_values(strong), _unique_values(weak)


def _password_selector_score(text: str, strong_selectors: list[str], weak_selectors: list[str]) -> int:
    score = 0
    folded = text.casefold()
    for selector in strong_selectors:
        if selector.casefold() in folded:
            score += 5
    for selector in weak_selectors:
        if re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(selector)}(?![A-Za-z0-9_.-])", text, re.IGNORECASE):
            score += 2
    return score


def _password_values_from_line(line: str, usernames: list[str]) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"(?:密码|password|pwd)\s*[:：=]\s*([^\s，,;；]+)", line, re.IGNORECASE):
        values.append(match.group(1))
    slash_users = usernames or ["op_user"]
    for username in slash_users:
        match = re.search(
            rf"(?<![A-Za-z0-9_.-]){re.escape(username)}\s*/\s*([^\s，,;；]+)",
            line,
            re.IGNORECASE,
        )
        if match:
            values.append(match.group(1))
    return _unique_values(values)


def _unique_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _mark_todo_done_in_text(text: str, assignee: str) -> str:
    if "status: done" in text:
        return text
    pattern = re.compile(
        rf"(todo\s*[:：]\s*.*?[,，]\s*to\s*[:：]\s*{re.escape(assignee)}\s*[,，]\s*)"
        rf"(end_date\s*[:：]\s*\d{{8}})",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(r"\1status: done, \2", text)


def _aggregate_rows(
    rows: list[list[str]],
    group_name: str,
    value_name: str,
    conditions: list[tuple[str, str, str]] | None = None,
) -> list[str]:
    if not rows:
        return []
    headers = rows[0]
    group_idx = _find_header_index(headers, group_name)
    value_idx = _find_header_index(headers, value_name)
    if group_idx is None or value_idx is None:
        return []
    source_rows = _filter_rows(rows, conditions or []) if conditions else rows[1:]
    if source_rows is None:
        return []
    totals: dict[str, float] = {}
    order: list[str] = []
    for row in source_rows:
        if group_idx >= len(row) or value_idx >= len(row):
            continue
        key = row[group_idx].strip()
        if not key:
            continue
        try:
            value = float(row[value_idx])
        except ValueError:
            continue
        if key not in totals:
            order.append(key)
            totals[key] = 0.0
        totals[key] += value
    return [f"{key}:{_format_number(totals[key])}" for key in order]


def _find_header_index(headers: list[str], name: str) -> int | None:
    normalized = name.casefold()
    for idx, header in enumerate(headers):
        if header.casefold() == normalized:
            return idx
    for idx, header in enumerate(headers):
        if normalized in header.casefold() or header.casefold() in normalized:
            return idx
    return None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


SAFE_PYTHON_BUILTINS = {
    "print": print,
    "sum": sum,
    "len": len,
    "min": min,
    "max": max,
    "sorted": sorted,
    "range": range,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "tuple": tuple,
    "dict": dict,
    "set": set,
    "abs": abs,
    "round": round,
}

SAFE_PYTHON_NODES = (
    ast.Module,
    ast.Assign,
    ast.AugAssign,
    ast.Expr,
    ast.FunctionDef,
    ast.Return,
    ast.arguments,
    ast.arg,
    ast.For,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.Call,
    ast.Attribute,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)

SAFE_PYTHON_METHODS = {
    "append",
    "casefold",
    "join",
    "lower",
    "replace",
    "split",
    "strip",
    "upper",
}

DANGEROUS_PYTHON_NAMES = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "input",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "os",
    "sys",
    "subprocess",
    "socket",
    "pathlib",
    "shutil",
}


def _safe_python_output(code_text: str, permission_guard: PermissionGuard) -> list[str] | None:
    if permission_guard.is_denied_command(code_text):
        return None
    try:
        tree = ast.parse(code_text)
    except SyntaxError:
        return None
    if not _is_safe_python_tree(tree, permission_guard):
        return None
    namespace: dict[str, Any] = {}
    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            exec(
                compile(tree, "<llm-wiki-safe-python>", "exec"),
                {"__builtins__": SAFE_PYTHON_BUILTINS},
                namespace,
            )
    except Exception as exc:
        return [f"{type(exc).__name__}: {exc}"]
    text = stdout.getvalue().strip()
    return text.splitlines() if text else []


def _is_safe_python_tree(tree: ast.AST, permission_guard: PermissionGuard) -> bool:
    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    defined_functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and not node.name.startswith("__")
        and node.name not in DANGEROUS_PYTHON_NAMES
    }
    for node in ast.walk(tree):
        if not isinstance(node, SAFE_PYTHON_NODES):
            return False
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in SAFE_PYTHON_BUILTINS and node.func.id not in defined_functions:
                    return False
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in SAFE_PYTHON_METHODS:
                    return False
            else:
                return False
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in DANGEROUS_PYTHON_NAMES:
                return False
            parent = parents.get(id(node))
            if not isinstance(parent, ast.Call) or parent.func is not node:
                return False
            if node.attr not in SAFE_PYTHON_METHODS:
                return False
        if isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in DANGEROUS_PYTHON_NAMES:
                return False
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("__") or node.name in DANGEROUS_PYTHON_NAMES:
                return False
            for arg in node.args.args:
                if arg.arg.startswith("__") or arg.arg in DANGEROUS_PYTHON_NAMES:
                    return False
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if "__" in value or permission_guard.is_denied_path(value, operation="read"):
                return False
    return True


def _extract_table_conditions(title: str, filename: str) -> list[tuple[str, str, str]]:
    tail = title.split(filename, 1)[-1] if filename in title else title
    tail = re.sub(r"按[\u4e00-\u9fffA-Za-z0-9_]+?(汇总|聚合|统计)", r"\1", tail, count=1)
    conditions: list[tuple[str, str, str]] = []
    pattern = re.compile(
        r"(?:^|中|里|内|且|并|，|,|\s|汇总|聚合|统计)"
        r"(?P<column>[\u4e00-\u9fffA-Za-z0-9_]+?)\s*"
        r"(?P<op>>=|<=|!=|>|<|大于等于|小于等于|不等于|大于|小于|为|是|等于|=)\s*"
        r"(?P<value>.+?)(?=且|并|的|，|,|。|\s|$)"
    )
    op_map = {
        "大于等于": ">=",
        "小于等于": "<=",
        "不等于": "!=",
        "大于": ">",
        "小于": "<",
        "为": "=",
        "是": "=",
        "等于": "=",
        "=": "=",
    }
    for match in pattern.finditer(tail):
        column = re.sub(r"^(?:中|里|内|汇总|聚合|统计)+", "", match.group("column"))
        op = op_map.get(match.group("op"), match.group("op"))
        value = match.group("value").strip()
        if column and value:
            conditions.append((column, op, value))
    return conditions


def _extract_return_column(title: str) -> str | None:
    match = re.search(r"的(?P<column>[\u4e00-\u9fffA-Za-z0-9_]+?)(?:列表|名单|清单)", title)
    return match.group("column") if match else None


def _compare_values(cell: str, op: str, value: str) -> bool:
    cell_value = cell.strip()
    if op == "=":
        return cell_value == value
    if op == "!=":
        return cell_value != value
    try:
        left = float(cell_value)
        right = float(value)
    except ValueError:
        return False
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    return False


def _filter_rows(rows: list[list[str]], conditions: list[tuple[str, str, str]]) -> list[list[str]] | None:
    if not rows:
        return None
    headers = rows[0]
    resolved: list[tuple[int, str, str]] = []
    for condition_column, condition_op, condition_value in conditions:
        condition_idx = _find_header_index(headers, condition_column)
        if condition_idx is None:
            return None
        resolved.append((condition_idx, condition_op, condition_value))
    result: list[list[str]] = []
    for row in rows[1:]:
        if all(idx < len(row) and _compare_values(row[idx], op, value) for idx, op, value in resolved):
            result.append(row)
    return result


def _values_from_rows(all_rows: list[list[str]], rows: list[list[str]], return_column: str) -> list[str]:
    if not all_rows:
        return []
    return_idx = _find_header_index(all_rows[0], return_column)
    if return_idx is None:
        return []
    return [row[return_idx].strip() for row in rows if return_idx < len(row) and row[return_idx].strip()]
