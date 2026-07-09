from __future__ import annotations

import re

from .models import CommentRecord


TODO_PATTERN = re.compile(
    r"todo\s*[:：]\s*(?P<todo>.*?)\s*[,，]\s*to\s*[:：]\s*(?P<to>.*?)\s*[,，]\s*end_date\s*[:：]\s*(?P<date>\d[\s\d]*\d|\d{8})",
    re.IGNORECASE | re.DOTALL,
)

HASH_COMMENT_PATTERN = re.compile(r"^\s*#\s*(?P<body>.+)$")
SLASH_COMMENT_PATTERN = re.compile(r"^\s*//\s*(?P<body>.+)$")
BLOCK_COMMENT_PATTERNS = [
    re.compile(r"/\*\s*(?P<body>.*?)\s*\*/", re.DOTALL),
    re.compile(r"<!--\s*(?P<body>.*?)\s*-->", re.DOTALL),
]
def normalize_comment_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_structured_todo(
    text: str,
    source: str,
    location: str,
    kind: str = "todo",
) -> CommentRecord | None:
    match = TODO_PATTERN.search(text)
    if not match:
        return None
    todo = normalize_comment_text(match.group("todo"))
    assignee = normalize_comment_text(match.group("to"))
    end_date = re.sub(r"\s+", "", match.group("date"))
    if len(end_date) != 8 or not end_date.isdigit():
        return None
    canonical = f"todo: {todo}, to: {assignee}, end_date: {end_date}"
    return CommentRecord(
        source=source,
        text=canonical,
        assignee=assignee,
        end_date=end_date,
        kind=kind,
        location=location,
    )


def extract_comment_records(text: str, source: str, suffix: str) -> list[CommentRecord]:
    records: list[CommentRecord] = []
    seen: set[str] = set()

    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in _line_patterns_for_suffix(suffix):
            match = pattern.match(line)
            if not match:
                continue
            _append_comment(records, seen, match.group("body"), source, f"line:{line_no}")

    for pattern in _block_patterns_for_suffix(suffix):
        for idx, match in enumerate(pattern.finditer(text), start=1):
            _append_comment(records, seen, match.group("body"), source, f"block:{idx}")

    if suffix in {"md", "html", "xml", "java", "js", "py"}:
        for idx, match in enumerate(TODO_PATTERN.finditer(text), start=1):
            record = parse_structured_todo(match.group(0), source, f"todo:{idx}", kind="todo")
            if record and record.text not in seen:
                records.append(record)
                seen.add(record.text)

    return records


def _append_comment(
    records: list[CommentRecord],
    seen: set[str],
    body: str,
    source: str,
    location: str,
) -> None:
    body = normalize_comment_text(body)
    if not body:
        return
    structured = parse_structured_todo(body, source, location, kind="todo")
    record = structured or CommentRecord(
        source=source,
        text=body,
        kind="free",
        location=location,
    )
    key = record.text
    if key in seen:
        return
    records.append(record)
    seen.add(key)


def _line_patterns_for_suffix(suffix: str) -> list[re.Pattern[str]]:
    if suffix == "py":
        return [HASH_COMMENT_PATTERN]
    if suffix in {"java", "js"}:
        return [SLASH_COMMENT_PATTERN]
    return []


def _block_patterns_for_suffix(suffix: str) -> list[re.Pattern[str]]:
    if suffix in {"java", "js", "py"}:
        return [BLOCK_COMMENT_PATTERNS[0]]
    if suffix in {"html", "xml", "md"}:
        return [BLOCK_COMMENT_PATTERNS[1]]
    return []
