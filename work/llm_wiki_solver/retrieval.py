from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .index import HybridIndex, build_index
from .models import DocumentRecord
from .permissions import PermissionGuard
from .search import normalize_for_match


@dataclass(frozen=True)
class RetrievalCard:
    source: str
    evidence_type: str
    text: str
    score: float
    channels: list[str] = field(default_factory=list)


def build_hybrid_index(records: list[DocumentRecord], permission_guard: PermissionGuard | None = None) -> HybridIndex:
    return build_index(records, permission_guard)


class HybridRetriever:
    def __init__(self, index: HybridIndex):
        self.index = index

    def retrieve(self, query: str | list[str], limit: int = 8) -> list[RetrievalCard]:
        queries = [query] if isinstance(query, str) else query
        pools: list[list[RetrievalCard]] = []
        for item in queries:
            if not item.strip():
                continue
            pools.append(self._structured_recall(item))
            pools.append(self._fts_recall(item))
            pools.append(self._text_recall(item))
            pools.append(self._fuzzy_path_recall(item))
            pools.append(self._related_document_recall(item))
        return _rrf_fuse(pools, limit)

    def find_documents(self, query: str, limit: int = 5) -> list[DocumentRecord]:
        by_path = {record.rel_path: record for record in self.index.records}
        results: list[DocumentRecord] = []
        for card in self.retrieve(query, limit=max(limit * 2, 8)):
            record = by_path.get(card.source)
            if record and record not in results:
                results.append(record)
            if len(results) >= limit:
                break
        return results

    def _structured_recall(self, query: str) -> list[RetrievalCard]:
        tokens = _query_tokens(query)
        cards: list[RetrievalCard] = []
        for record in self.index.records:
            if record.metadata.get("permission_denied") == "true":
                continue
            path_text = normalize_for_match(f"{record.rel_path} {record.folder} {Path(record.rel_path).name}")
            path_score = _token_score(tokens, path_text)
            if path_score:
                cards.append(
                    RetrievalCard(record.rel_path, "document", record.rel_path, path_score + 1.0, ["path"])
                )
            for comment in record.comments:
                fact_text = f"{comment.text} {comment.assignee or ''} {comment.end_date or ''}"
                score = _token_score(tokens, normalize_for_match(fact_text))
                if score:
                    cards.append(
                        RetrievalCard(record.rel_path, "comment", comment.text, score + 2.0, ["comment"])
                    )
            for row in record.tables[:20]:
                row_text = "\t".join(row)
                score = _token_score(tokens, normalize_for_match(row_text))
                if score:
                    cards.append(
                        RetrievalCard(record.rel_path, "table_row", row_text, score + 1.5, ["table"])
                    )
        return sorted(cards, key=lambda card: (-card.score, card.source, card.evidence_type))

    def _fts_recall(self, query: str) -> list[RetrievalCard]:
        rows = []
        tokens = _query_tokens(query)
        ascii_tokens = [token for token in tokens if re.search(r"[A-Za-z0-9_]", token)]
        cjk_phrases = _cjk_fts_phrases(query)
        if self.index.fts_available and ascii_tokens:
            expression = " OR ".join(_escape_fts_token(token) for token in ascii_tokens[:8])
            try:
                rows.extend(
                    self.index.connection.execute(
                        """
                        SELECT source, text, bm25(chunks_fts) AS rank
                        FROM chunks_fts
                        WHERE chunks_fts MATCH ?
                        ORDER BY rank
                        LIMIT 20
                        """,
                        (expression,),
                    ).fetchall()
                )
            except sqlite3.OperationalError:
                pass
        if self.index.fts_trigram_available and cjk_phrases:
            expression = " OR ".join(_escape_fts_token(token) for token in cjk_phrases[:8])
            try:
                rows.extend(
                    self.index.connection.execute(
                        """
                        SELECT source, text, bm25(chunks_fts_trigram) AS rank
                        FROM chunks_fts_trigram
                        WHERE chunks_fts_trigram MATCH ?
                        ORDER BY rank
                        LIMIT 20
                        """,
                        (expression,),
                    ).fetchall()
                )
            except sqlite3.OperationalError:
                pass
        cards: list[RetrievalCard] = []
        for row in rows:
            rank = float(row["rank"])
            cards.append(
                RetrievalCard(row["source"], "chunk", row["text"], 3.0 + (1.0 / (1.0 + abs(rank))), ["fts"])
            )
        return cards

    def _text_recall(self, query: str) -> list[RetrievalCard]:
        tokens = _query_tokens(query)
        cards: list[RetrievalCard] = []
        for row in self.index.connection.execute(
            "SELECT rel_path, text FROM documents WHERE permission_denied = 0"
        ):
            haystack = normalize_for_match(f"{row['rel_path']} {row['text']}")
            score = _token_score(tokens, haystack)
            if score:
                snippet = re.sub(r"\s+", " ", row["text"]).strip()[:300]
                cards.append(
                    RetrievalCard(row["rel_path"], "text", snippet or row["rel_path"], score, ["text"])
                )
        return sorted(cards, key=lambda card: (-card.score, card.source))

    def _fuzzy_path_recall(self, query: str) -> list[RetrievalCard]:
        query_parts = re.findall(r"[\w\u4e00-\u9fff（）()\-_.]+", query)
        cards: list[RetrievalCard] = []
        for record in self.index.records:
            if record.metadata.get("permission_denied") == "true":
                continue
            name = Path(record.rel_path).name
            score = max((fuzzy_ratio(name, part) for part in query_parts), default=0.0)
            if score >= 0.68:
                cards.append(RetrievalCard(record.rel_path, "document", record.rel_path, score, ["fuzzy"]))
        return sorted(cards, key=lambda card: (-card.score, card.source))

    def _related_document_recall(self, query: str) -> list[RetrievalCard]:
        if not any(word in query for word in ("涉及", "相关", "哪些文件", "文件")):
            return []
        direct = self._text_recall(query)[:2]
        if not direct:
            return []
        expansion_terms: list[str] = []
        for card in direct:
            expansion_terms.extend(_query_tokens(card.text))
        expansion_terms = [
            term
            for term in dict.fromkeys(expansion_terms)
            if len(term) >= 2 and term not in {"文件", "涉及", "相关", "哪些", "哪些文件"}
        ][:20]
        cards: list[RetrievalCard] = []
        for row in self.index.connection.execute(
            "SELECT rel_path, text FROM documents WHERE permission_denied = 0"
        ):
            haystack = normalize_for_match(f"{row['rel_path']} {row['text']}")
            score = _token_score(expansion_terms, haystack)
            if score:
                snippet = re.sub(r"\s+", " ", row["text"]).strip()[:300]
                cards.append(
                    RetrievalCard(row["rel_path"], "related", snippet or row["rel_path"], score * 0.8, ["related"])
                )
        return sorted(cards, key=lambda card: (-card.score, card.source))


def fuzzy_ratio(left: str, right: str) -> float:
    try:
        from rapidfuzz import fuzz  # type: ignore
    except ImportError:
        return SequenceMatcher(None, normalize_for_match(left), normalize_for_match(right)).ratio()
    return fuzz.ratio(left, right) / 100.0


def _rrf_fuse(pools: list[list[RetrievalCard]], limit: int, k: int = 50) -> list[RetrievalCard]:
    fused: dict[tuple[str, str, str], RetrievalCard] = {}
    for pool in pools:
        for rank, card in enumerate(pool, start=1):
            key = (card.source, card.evidence_type, card.text)
            bonus = 1.0 / (k + rank)
            existing = fused.get(key)
            score = card.score + bonus
            channels = list(dict.fromkeys([*card.channels, "rrf"]))
            if existing is None or score > existing.score:
                fused[key] = RetrievalCard(card.source, card.evidence_type, card.text, score, channels)
    return sorted(fused.values(), key=lambda item: (-item.score, item.source, item.evidence_type))[:limit]


def _query_tokens(query: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9_#:/.\-]+|[\u4e00-\u9fff]{2,}", query)
    tokens: list[str] = []
    for item in raw:
        normalized = normalize_for_match(item)
        if len(normalized) >= 2 and normalized not in tokens:
            tokens.append(normalized)
        if re.search(r"[\u4e00-\u9fff]", item) and len(item) > 2:
            chars = [char for char in item if "\u4e00" <= char <= "\u9fff"]
            for idx in range(len(chars) - 1):
                bigram = normalize_for_match(chars[idx] + chars[idx + 1])
                if bigram not in tokens:
                    tokens.append(bigram)
    return tokens


def _cjk_fts_phrases(query: str) -> list[str]:
    phrases: list[str] = []
    for item in re.findall(r"[\u4e00-\u9fff]{3,}", query):
        normalized = normalize_for_match(item)
        if len(normalized) >= 3 and normalized not in phrases:
            phrases.append(normalized)
        chars = [char for char in normalized if "\u4e00" <= char <= "\u9fff"]
        for width in (4, 3):
            for idx in range(0, max(len(chars) - width + 1, 0)):
                phrase = "".join(chars[idx : idx + width])
                if phrase not in phrases:
                    phrases.append(phrase)
    return phrases


def _token_score(tokens: Iterable[str], haystack: str) -> float:
    score = 0.0
    for token in tokens:
        if token and token in haystack:
            score += 1.0 if len(token) <= 2 else 1.5
    return score


def _escape_fts_token(token: str) -> str:
    cleaned = re.sub(r'["\s]+', " ", token).strip()
    return f'"{cleaned}"'
