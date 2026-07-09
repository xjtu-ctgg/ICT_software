from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


SUPPORTED_COUNT_SUFFIXES = {
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "xml",
    "java",
    "py",
    "html",
    "md",
    "js",
    "txt",
    "json",
    "yaml",
    "yml",
    "csv",
    "env",
    "cmd",
}


@dataclass(frozen=True)
class CommentRecord:
    source: str
    text: str
    assignee: str | None = None
    end_date: str | None = None
    kind: str = "free"
    location: str = ""


@dataclass
class DocumentRecord:
    path: Path
    rel_path: str
    suffix: str
    folder: str
    text: str = ""
    tables: list[list[str]] = field(default_factory=list)
    comments: list[CommentRecord] = field(default_factory=list)
    todos: list[CommentRecord] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Question:
    id: str
    title: str
    level: str


@dataclass(frozen=True)
class Answer:
    id: str
    answer: dict
