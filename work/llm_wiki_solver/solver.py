from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .extractors import scan_documents
from .llm_client import FakeLLMClient, LLMClient, LLMConfig
from .llm_pipeline import ComplexUnderstandingPipeline, should_use_llm
from .models import Answer, DocumentRecord, Question, SUPPORTED_COUNT_SUFFIXES
from .permissions import PermissionGuard
from .policy import DENY_ANSWER
from .search import extract_candidate_filename, find_documents_by_filename, ranked_text_search


class WikiSolver:
    def __init__(self, root: Path, log_dir: Path | None = None, llm_mode: str = "auto"):
        self.root = root
        self.log_dir = log_dir
        self.llm_mode = llm_mode
        self.permissions = PermissionGuard(self._load_permissions())
        self.records = scan_documents(root)
        self.llm_config = LLMConfig.from_env(mode_override=llm_mode)
        self.llm_client = LLMClient(self.llm_config)
        self.pipeline = ComplexUnderstandingPipeline(
            records=self.records,
            permission_guard=self.permissions,
            llm_client=self.llm_client,
            root=self.root,
            llm_mode=llm_mode,
        )

    def solve_group(self, group_path: Path) -> list[Answer]:
        questions = self._load_questions(group_path)
        answers: list[Answer] = []
        traces: list[dict[str, Any]] = []
        for question in questions:
            answer, trace = self.solve_question_with_trace(question)
            answers.append(Answer(id=question.id, answer=answer))
            traces.append({"id": question.id, **trace})
        self._write_trace(group_path.stem, traces)
        return answers

    def solve_question(self, question: Question) -> dict:
        answer, _ = self.solve_question_with_trace(question)
        return answer

    def solve_question_with_trace(self, question: Question) -> tuple[dict, dict[str, Any]]:
        title = question.title.strip()
        if self._is_high_risk_question(title):
            return DENY_ANSWER, {"llm_used": False, "fallback_reason": "high_risk"}

        count_suffix = self._extract_count_suffix(title)
        if count_suffix:
            fallback = {count_suffix: sum(1 for record in self.records if record.suffix == count_suffix)}
            return self._maybe_llm(question, fallback)

        filename = extract_candidate_filename(title)
        if filename and any(word in title for word in ("路径", "找出", "位置")):
            fallback = {"datas": [record.rel_path for record in find_documents_by_filename(self.records, filename)]}
            return self._maybe_llm(question, fallback)

        if "批注" in title and any(word in title for word in ("数量", "统计")):
            candidates = self._candidate_records(title)
            fallback = {"count": sum(len(record.comments) for record in candidates)}
            return self._maybe_llm(question, fallback)

        if "责任人" in title or "待" in title:
            assignee = self._extract_assignee(title)
            if assignee and any(word in title for word in ("修复", "修改", "处理")):
                fallback = self._repair_by_assignee(assignee)
                return self._maybe_llm(question, fallback)
            if assignee:
                fallback = {"datas": self._comments_by_assignee(assignee)}
                return self._maybe_llm(question, fallback)

        if any(word in title for word in ("TODO", "todo", "批注")):
            assignee = self._extract_assignee(title)
            if assignee:
                fallback = {"datas": self._comments_by_assignee(assignee)}
                return self._maybe_llm(question, fallback)
            fallback = {"datas": [comment.text for record in self.records for comment in record.todos]}
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
            "删除全部",
            "彻底删除",
            "强制kill",
            "读取c盘根目录",
            "读取 C 盘根目录",
        ]
        if any(word.casefold() in title.casefold() for word in injection_words):
            return True
        if "密码" in title and self._is_forbidden_password_query(title):
            return True
        return False

    @staticmethod
    def _extract_count_suffix(title: str) -> str | None:
        for suffix in sorted(SUPPORTED_COUNT_SUFFIXES, key=len, reverse=True):
            token = rf"(?<![A-Za-z0-9_]){re.escape(suffix)}(?![A-Za-z0-9_])"
            patterns = [
                rf"{token}\s*文件.*数量",
                rf"统计.*{token}.*数量",
                rf"{token}.*总数量",
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
        matches = ranked_text_search(self.records, title, limit=5)
        return matches or self.records

    @staticmethod
    def _extract_assignee(title: str) -> str | None:
        patterns = [
            r"责任人为(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+?)(?:的|处理|事项|列表|TODO|todo|批注|$)",
            r"待(?P<name>[\u4e00-\u9fffA-Za-z0-9_]+?)处理",
            r"(?P<name>[\u4e00-\u9fff]{2,4})的TODO",
            r"(?P<name>[\u4e00-\u9fff]{2,4})的批注",
        ]
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group("name")
        return None

    def _comments_by_assignee(self, assignee: str) -> list[str]:
        rows = [
            comment.text
            for record in self.records
            for comment in [*record.todos, *record.comments]
            if comment.assignee == assignee
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
        record = candidates[0]
        target_rel = Path("output") / "fixed" / Path(record.rel_path).relative_to("docs")
        target = self.root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.path, target)
        return {"source": record.rel_path, "target": target_rel.as_posix()}

    def _password_answer(self, title: str) -> dict:
        if self._is_forbidden_password_query(title):
            return DENY_ANSWER
        matches = ranked_text_search(self.records, title, limit=5)
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
        matches = ranked_text_search(self.records, title, limit=5)
        if not matches:
            return []
        snippets: list[str] = []
        for record in matches:
            snippet = re.sub(r"\s+", " ", record.text).strip()[:300]
            snippets.append(f"{record.rel_path}: {snippet}" if snippet else record.rel_path)
        return snippets

    def _maybe_llm(self, question: Question, fallback_answer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not should_use_llm(question, fallback_answer, self.llm_mode):
            return fallback_answer, {"llm_used": False, "fallback_reason": "rule_chain"}
        result = self.pipeline.solve(question, fallback_answer)
        trace = dict(result.trace)
        trace.setdefault("llm_used", False)
        trace.setdefault("fallback_reason", None)
        return (result.answer if result.answer else fallback_answer), trace


def _extract_password_values(text: str, title: str) -> list[str]:
    values: list[str] = []
    title_tokens = [token for token in re.findall(r"[A-Za-z0-9_.:/#-]+|[\u4e00-\u9fff]+", title) if len(token) >= 2]
    for line in text.splitlines():
        if title_tokens and not any(token in line for token in title_tokens):
            continue
        match = re.search(r"(?:密码|password|pwd)\s*[:：=]\s*([^\s，,;；]+)", line, re.IGNORECASE)
        if match:
            values.append(match.group(1))
    if not values:
        for match in re.finditer(r"(?:密码|password|pwd)\s*[:：=]\s*([^\s，,;；]+)", text, re.IGNORECASE):
            values.append(match.group(1))
    return values
