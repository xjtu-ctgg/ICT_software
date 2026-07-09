from __future__ import annotations

import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from typing import Any

from .comments import extract_comment_records, parse_structured_todo
from .models import CommentRecord, DocumentRecord


TEXT_SUFFIXES = {"xml", "java", "py", "html", "md", "js", "txt", "json", "yaml", "yml", "csv", "env", "cmd"}


def _extract_legacy_format(path: Path, suffix: str, rel_path: str) -> tuple[str, list[CommentRecord], list[list[str]]]:
    target_suffix = {"doc": "docx", "ppt": "pptx", "xls": "xlsx"}.get(suffix)
    if not target_suffix:
        text = _read_text(path)
        return text, extract_comment_records(text, rel_path, suffix), []

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    target_suffix,
                    "--outdir",
                    tmp_dir,
                    str(path),
                ],
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            result = None
        if result is not None and result.returncode == 0:
            converted = Path(tmp_dir) / f"{path.stem}.{target_suffix}"
            if converted.exists() and zipfile.is_zipfile(converted):
                return _extract_ooxml(converted, target_suffix, rel_path)

    try:
        from markitdown import MarkItDown  # type: ignore
    except ImportError:
        MarkItDown = None  # type: ignore
    if MarkItDown is not None:
        try:
            converted = MarkItDown().convert(str(path))
            text = getattr(converted, "text_content", str(converted))
            return text, extract_comment_records(text, rel_path, suffix), []
        except Exception:
            pass

    text = _read_text(path)
    return text, extract_comment_records(text, rel_path, suffix), []


def scan_documents(root: Path, permission_guard: Any | None = None) -> list[DocumentRecord]:
    docs_dir = root / "docs"
    records: list[DocumentRecord] = []
    if not docs_dir.exists():
        return records
    for path in sorted(item for item in docs_dir.rglob("*") if item.is_file()):
        rel_path = path.relative_to(root).as_posix()
        if permission_guard is not None and permission_guard.is_denied_path(rel_path, operation="read"):
            suffix = path.suffix.lower().lstrip(".")
            folder = path.parent.relative_to(root / "docs").as_posix() if path.parent != root / "docs" else ""
            records.append(
                DocumentRecord(
                    path=path,
                    rel_path=rel_path,
                    suffix=suffix,
                    folder=folder,
                    metadata={"permission_denied": "true"},
                )
            )
            continue
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
    elif suffix in {"doc", "ppt", "xls"}:
        text, comments, tables = _extract_legacy_format(path, suffix, rel_path)
    elif _docling_enabled():
        docling = _extract_with_docling(path, rel_path, suffix)
        if docling is not None:
            text, comments, tables = docling
        elif suffix in TEXT_SUFFIXES or _looks_text(path):
            text = _read_text(path)
            comments = extract_comment_records(text, rel_path, suffix)
        else:
            text = _read_text(path)
            comments = extract_comment_records(text, rel_path, suffix)
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


def _docling_enabled() -> bool:
    import os

    return os.getenv("LLM_WIKI_ENABLE_DOCLING", "").strip().lower() in {"1", "true", "yes", "on"}


def _extract_with_docling(path: Path, rel_path: str, suffix: str) -> tuple[str, list[CommentRecord], list[list[str]]] | None:
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except ImportError:
        return None
    try:
        result = DocumentConverter().convert(str(path))
        document = result.document
        text = document.export_to_markdown()
    except Exception:
        return None
    return text, extract_comment_records(text, rel_path, suffix), []


def _extract_ooxml(path: Path, suffix: str, rel_path: str) -> tuple[str, list[CommentRecord], list[list[str]]]:
    texts: list[str] = []
    comments: list[CommentRecord] = []
    tables: list[list[str]] = []

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if suffix == "xlsx":
            tables = _extract_xlsx_tables(archive)
            texts.extend("\t".join(cell for cell in row if cell) for row in tables)
        comment_files = _find_comment_files(names, suffix)
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
            if name in comment_files:
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


def _find_comment_files(names: list[str], suffix: str) -> set[str]:
    comment_files: set[str] = set()
    for name in names:
        if not name.endswith(".xml"):
            continue
        basename = name.casefold().rsplit("/", 1)[-1]
        if suffix == "docx" and name.startswith("word/"):
            if basename.startswith("comment") and basename.endswith(".xml"):
                comment_files.add(name)
        elif suffix == "pptx" and name.startswith("ppt/"):
            if basename.startswith("comment") and basename.endswith(".xml"):
                comment_files.add(name)
        elif suffix == "xlsx" and name.startswith("xl/"):
            if "comment" in basename and basename.endswith(".xml"):
                comment_files.add(name)
    return comment_files


def _extract_xlsx_tables(archive: zipfile.ZipFile) -> list[list[str]]:
    shared_strings = _extract_shared_strings(archive)
    rows: list[list[str]] = []
    sheet_names = sorted(
        name
        for name in archive.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    for name in sheet_names:
        root = _parse_xml_bytes(archive.read(name))
        if root is None:
            continue
        for row_node in _iter_local(root, "row"):
            cells: dict[int, str] = {}
            max_col = 0
            next_col = 1
            for cell_node in [child for child in row_node if _local_name(child.tag) == "c"]:
                ref = cell_node.attrib.get("r", "")
                col_idx = _column_index(ref) or next_col
                next_col = col_idx + 1
                max_col = max(max_col, col_idx)
                cells[col_idx] = _xlsx_cell_value(cell_node, shared_strings)
            if max_col:
                rows.append([cells.get(idx, "") for idx in range(1, max_col + 1)])
    return rows


def _extract_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _parse_xml_bytes(archive.read("xl/sharedStrings.xml"))
    if root is None:
        return []
    return [
        re.sub(r"\s+", " ", " ".join(_iter_text(item))).strip()
        for item in _iter_local(root, "si")
    ]


def _xlsx_cell_value(cell_node: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell_node.attrib.get("t", "")
    value_node = next((child for child in cell_node if _local_name(child.tag) == "v"), None)
    if cell_type == "inlineStr":
        return re.sub(r"\s+", " ", " ".join(_iter_text(cell_node))).strip()
    raw = value_node.text.strip() if value_node is not None and value_node.text else ""
    if cell_type == "s" and raw.isdigit():
        idx = int(raw)
        return shared_strings[idx] if idx < len(shared_strings) else raw
    return raw


def _parse_xml_bytes(data: bytes) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return None


def _iter_local(root: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _column_index(cell_ref: str) -> int | None:
    match = re.match(r"([A-Za-z]+)", cell_ref)
    if not match:
        return None
    value = 0
    for char in match.group(1).upper():
        value = value * 26 + ord(char) - ord("A") + 1
    return value


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
        if tag == "comment":
            text = " ".join(_iter_text(node))
            if text.strip():
                items.append(re.sub(r"\s+", " ", text).strip())
    if not items:
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1].lower()
            if "comment" in tag and tag != "comments":
                text = " ".join(_iter_text(node))
                if text.strip():
                    items.append(re.sub(r"\s+", " ", text).strip())
    if not items:
        todo_match = re.search(
            r"todo\s*[:：]\s*.*?[,，]\s*to\s*[:：]\s*.*?[,，]\s*end_date\s*[:：]\s*\d+",
            re.sub(r"<[^>]+>", " ", xml_text),
            re.IGNORECASE | re.DOTALL,
        )
        if todo_match:
            items.append(re.sub(r"\s+", " ", todo_match.group(0)).strip())
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
