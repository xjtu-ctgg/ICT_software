from __future__ import annotations

import re
from pathlib import Path

from .models import DocumentRecord


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def extract_candidate_filename(title: str) -> str | None:
    contextual = re.search(
        r"(?:找出|查询|读取|打开|修复|完成)?\s*(?P<name>[^\s，,。]+?\.(?:docx?|pptx?|xlsx?|xml|java|py|html|md|js|txt|env|cmd))",
        title,
        re.IGNORECASE,
    )
    if contextual:
        name = contextual.group("name")
        name = re.sub(r"^(?:找出|查询|读取|打开|修复|完成)", "", name)
        return name
    match = re.search(
        r"([\w\u4e00-\u9fff（）()\-_.]+?\.(?:docx?|pptx?|xlsx?|xml|java|py|html|md|js|txt|env|cmd))",
        title,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def find_documents_by_filename(records: list[DocumentRecord], filename: str) -> list[DocumentRecord]:
    target = normalize_for_match(filename)
    matches = [record for record in records if normalize_for_match(Path(record.rel_path).name) == target]
    if matches:
        return matches
    return [record for record in records if target in normalize_for_match(record.rel_path)]


def ranked_text_search(records: list[DocumentRecord], query: str, limit: int = 5) -> list[DocumentRecord]:
    tokens = _query_tokens(query)
    scored: list[tuple[int, DocumentRecord]] = []
    for record in records:
        haystack = normalize_for_match(f"{record.rel_path}\n{record.text}")
        score = sum(1 for token in tokens if token and token in haystack)
        if score:
            scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], item[1].rel_path))
    return [record for _, record in scored[:limit]]


def _query_tokens(query: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9_#:/.\-]+|[\u4e00-\u9fff]{2,}", query)
    return [normalize_for_match(item) for item in raw if len(item.strip()) >= 2]
