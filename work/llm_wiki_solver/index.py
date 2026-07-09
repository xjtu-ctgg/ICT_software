from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from .models import DocumentRecord
from .permissions import PermissionGuard


@dataclass
class HybridIndex:
    records: list[DocumentRecord]
    connection: sqlite3.Connection
    fts_available: bool
    fts_trigram_available: bool = False


def build_index(records: list[DocumentRecord], permission_guard: PermissionGuard | None = None) -> HybridIndex:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    _create_schema(connection)
    fts_available, fts_trigram_available = _create_fts(connection)
    for record in records:
        _insert_record(connection, record, permission_guard, fts_available, fts_trigram_available)
    connection.commit()
    return HybridIndex(
        records=records,
        connection=connection,
        fts_available=fts_available,
        fts_trigram_available=fts_trigram_available,
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE documents (
            rel_path TEXT PRIMARY KEY,
            suffix TEXT NOT NULL,
            folder TEXT NOT NULL,
            text TEXT NOT NULL,
            permission_denied INTEGER NOT NULL
        );
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            text TEXT NOT NULL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            text TEXT NOT NULL,
            assignee TEXT,
            end_date TEXT,
            kind TEXT NOT NULL
        );
        CREATE TABLE table_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            text TEXT NOT NULL
        );
        CREATE TABLE code_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            text TEXT NOT NULL
        );
        CREATE TABLE retrieval_trace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id TEXT,
            query TEXT NOT NULL,
            channel TEXT NOT NULL,
            source TEXT NOT NULL,
            score REAL NOT NULL
        );
        """
    )


def _create_fts(connection: sqlite3.Connection) -> tuple[bool, bool]:
    unicode_available = True
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5(source, text, tokenize='unicode61')"
        )
    except sqlite3.OperationalError:
        unicode_available = False

    trigram_available = True
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE chunks_fts_trigram USING fts5(source, text, tokenize='trigram')"
        )
    except sqlite3.OperationalError:
        trigram_available = False
    return unicode_available, trigram_available


def _insert_record(
    connection: sqlite3.Connection,
    record: DocumentRecord,
    permission_guard: PermissionGuard | None,
    fts_available: bool,
    fts_trigram_available: bool,
) -> None:
    denied = record.metadata.get("permission_denied") == "true"
    if permission_guard and permission_guard.is_denied_path(record.rel_path, operation="read"):
        denied = True
    text = "" if denied else record.text
    connection.execute(
        "INSERT INTO documents(rel_path, suffix, folder, text, permission_denied) VALUES (?, ?, ?, ?, ?)",
        (record.rel_path, record.suffix, record.folder, text, int(denied)),
    )
    if denied:
        return

    for chunk in _chunk_text(text):
        connection.execute("INSERT INTO chunks(source, text) VALUES (?, ?)", (record.rel_path, chunk))
        if fts_available:
            connection.execute(
                "INSERT INTO chunks_fts(source, text) VALUES (?, ?)",
                (record.rel_path, chunk),
            )
        if fts_trigram_available:
            connection.execute(
                "INSERT INTO chunks_fts_trigram(source, text) VALUES (?, ?)",
                (record.rel_path, chunk),
            )
    for comment in record.comments:
        connection.execute(
            "INSERT INTO comments(source, text, assignee, end_date, kind) VALUES (?, ?, ?, ?, ?)",
            (comment.source, comment.text, comment.assignee, comment.end_date, comment.kind),
        )
    for idx, row in enumerate(record.tables):
        connection.execute(
            "INSERT INTO table_rows(source, row_index, text) VALUES (?, ?, ?)",
            (record.rel_path, idx, "\t".join(row)),
        )
    if record.suffix in {"py", "java", "js"} and text:
        connection.execute(
            "INSERT INTO code_blocks(source, text) VALUES (?, ?)",
            (record.rel_path, text),
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
