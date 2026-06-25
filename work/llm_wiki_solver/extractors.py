from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .comments import extract_comment_records, parse_structured_todo
from .models import CommentRecord, DocumentRecord


TEXT_SUFFIXES = {"xml", "java", "py", "html", "md", "js", "txt", "json", "yaml", "yml", "csv", "env", "cmd"}


def scan_documents(root: Path) -> list[DocumentRecord]:
    docs_dir = root / "docs"
    records: list[DocumentRecord] = []
    if not docs_dir.exists():
        return records
    for path in sorted(item for item in docs_dir.rglob("*") if item.is_file()):
        records.append(extract_document(path, root))
    return records


def extract_document(path: Path, root: Path) -> DocumentRecord:
    suffix = path.suffix.lower().lstrip(".")
    rel_path = path.relative_to(root).as_posix()
    folder = path.parent.relative_to(root / "docs").as_posix() if path.parent != root / "docs" else ""
    text = ""
    comments: list[CommentRecord] = []
    tables: list[list[str]] = []

    if suffix in {"docx", "pptx", "xlsx"} and zipfile.is_zipfile(path):
        text, comments, tables = _extract_ooxml(path, suffix, rel_path)
    elif suffix in TEXT_SUFFIXES or _looks_text(path):
        text = _read_text(path)
        comments = extract_comment_records(text, rel_path, suffix)
    else:
        text = _read_text(path)
        comments = extract_comment_records(text, rel_path, suffix)

    todos = [record for record in comments if record.assignee or record.kind == "todo"]
    return DocumentRecord(
        path=path,
        rel_path=rel_path,
        suffix=suffix,
        folder=folder,
        text=text,
        tables=tables,
        comments=comments,
        todos=todos,
    )


def _extract_ooxml(path: Path, suffix: str, rel_path: str) -> tuple[str, list[CommentRecord], list[list[str]]]:
    texts: list[str] = []
    comments: list[CommentRecord] = []
    tables: list[list[str]] = []

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            if not name.endswith(".xml"):
                continue
            if suffix == "docx" and not name.startswith("word/"):
                continue
            if suffix == "pptx" and not (name.startswith("ppt/slides/") or name.startswith("ppt/comments/")):
                continue
            if suffix == "xlsx" and not (name.startswith("xl/") and ("sheet" in name or "sharedStrings" in name or "comments" in name)):
                continue

            xml_text = archive.read(name).decode("utf-8", errors="ignore")
            plain = _xml_to_text(xml_text)
            if plain:
                texts.append(plain)
            if "comment" in name.lower() or "comments" in name.lower():
                for idx, comment_text in enumerate(_extract_xml_text_items(xml_text), start=1):
                    structured = parse_structured_todo(
                        comment_text,
                        rel_path,
                        f"{name}:{idx}",
                        kind="todo",
                    )
                    comments.append(
                        structured
                        or CommentRecord(
                            source=rel_path,
                            text=comment_text,
                            kind="free",
                            location=f"{name}:{idx}",
                        )
                    )

    merged = "\n".join(texts)
    comments.extend(extract_comment_records(merged, rel_path, suffix))
    comments = _dedupe_comments(comments)
    return merged, comments, tables


def _xml_to_text(xml_text: str) -> str:
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError:
        return re.sub(r"<[^>]+>", " ", xml_text)
    return "\n".join(item for item in _iter_text(root) if item)


def _extract_xml_text_items(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError:
        return [re.sub(r"<[^>]+>", " ", xml_text).strip()]

    items: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if "comment" in tag:
            text = " ".join(_iter_text(node))
            if text.strip():
                items.append(re.sub(r"\s+", " ", text).strip())
    if not items:
        text = " ".join(_iter_text(root))
        if text.strip():
            items.append(re.sub(r"\s+", " ", text).strip())
    return items


def _iter_text(node: ElementTree.Element) -> list[str]:
    values: list[str] = []
    if node.text and node.text.strip():
        values.append(node.text.strip())
    for child in node:
        values.extend(_iter_text(child))
        if child.tail and child.tail.strip():
            values.append(child.tail.strip())
    return values


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding, errors="ignore")
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="ignore")


def _looks_text(path: Path) -> bool:
    try:
        data = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\x00" not in data


def _dedupe_comments(comments: list[CommentRecord]) -> list[CommentRecord]:
    result: list[CommentRecord] = []
    seen: set[tuple[str, str]] = set()
    for comment in comments:
        key = (comment.source, comment.text)
        if key in seen:
            continue
        result.append(comment)
        seen.add(key)
    return result
