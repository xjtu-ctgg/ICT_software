from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from .models import DocumentRecord


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def extract_candidate_filename(title: str) -> str | None:
    extensions = r"(?:docx?|pptx?|xlsx?|xml|java|py|html|md|js|txt|json|ya?ml|csv|env|cmd)"
    verb_prefix = r"(?:找出|查询|读取|打开|修复|完成|根据|基于|运行|执行|使用\s+\w+\s+删除|删除|查找|搜索|定位)"
    matches: list[tuple[int, str]] = []
    for match in re.finditer(
        r"((?:[\w\u4e00-\u9fff（）()\-_.]+\s+)*[\w\u4e00-\u9fff（）()\-_.]+\." + extensions + r")",
        title,
        re.IGNORECASE,
    ):
        candidate = re.sub(r"^" + verb_prefix + r"\s*", "", match.group(1).strip())
        matches.append((match.start(), candidate))
    for match in re.finditer(
        r"([\w\u4e00-\u9fff（）()\-_.]+\." + extensions + r")",
        title,
        re.IGNORECASE,
    ):
        candidate = re.sub(r"^" + verb_prefix + r"\s*", "", match.group(1).strip())
        matches.append((match.start(), candidate))
    if not matches:
        return None
    seen: set[str] = set()
    unique: list[str] = []
    for _, candidate in sorted(matches, key=lambda item: (-len(item[1]), item[0])):
        if candidate and "." in candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique[0] if unique else None


def find_documents_by_filename(records: list[DocumentRecord], filename: str) -> list[DocumentRecord]:
    target = normalize_for_match(filename)
    matches = [record for record in records if normalize_for_match(Path(record.rel_path).name) == target]
    if matches:
        return matches
    contains = [record for record in records if target in normalize_for_match(record.rel_path)]
    if contains:
        return contains
    fuzzy: list[tuple[float, DocumentRecord]] = []
    for record in records:
        score = SequenceMatcher(None, target, normalize_for_match(Path(record.rel_path).name)).ratio()
        if score >= 0.72:
            fuzzy.append((score, record))
    fuzzy.sort(key=lambda item: (-item[0], item[1].rel_path))
    return [record for _, record in fuzzy]


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
    tokens: list[str] = []
    for item in raw:
        normalized = normalize_for_match(item)
        if len(normalized.strip()) >= 2:
            tokens.append(normalized)
        if re.search(r"[\u4e00-\u9fff]", item) and len(item) > 2:
            chars = [char for char in item if "\u4e00" <= char <= "\u9fff"]
            for idx in range(len(chars) - 1):
                bigram = normalize_for_match(chars[idx] + chars[idx + 1])
                if bigram not in tokens:
                    tokens.append(bigram)
    return tokens
