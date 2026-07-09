from __future__ import annotations

from pathlib import Path

from work.llm_wiki_solver.answers import normalize_answer
from work.llm_wiki_solver.extractors import scan_documents
from work.llm_wiki_solver.permissions import PermissionGuard
from work.llm_wiki_solver.retrieval import HybridRetriever, build_hybrid_index, fuzzy_ratio


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "llm-wiki"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (root / "Permission.json").write_text(
        '{"file":{"deny":["secret.env"]},"dir":{"deny":["*/private"]}}',
        encoding="utf-8",
    )
    (docs / "00_业务总结").mkdir()
    (docs / "00_业务总结" / "计费业务总结.md").write_text(
        "计费业务包含账单、折扣、套餐。账单模块负责出账和对账。",
        encoding="utf-8",
    )
    (docs / "05_需求设计").mkdir()
    (docs / "05_需求设计" / "账单需求.md").write_text(
        "<!-- todo: 补充折扣字段,to:张三,end_date:20251231 -->\n"
        "账单需求要求按客户维度聚合费用。",
        encoding="utf-8",
    )
    (docs / "02_环境信息").mkdir()
    (docs / "02_环境信息" / "secret.env").write_text(
        "SECRET=should_not_be_indexed",
        encoding="utf-8",
    )
    return root


def test_hybrid_index_retrieves_semantic_business_files_and_facts(tmp_path):
    root = _workspace(tmp_path)
    guard = PermissionGuard({"file": {"deny": ["secret.env"]}, "dir": {"deny": ["*/private"]}})
    records = scan_documents(root, permission_guard=guard)
    index = build_hybrid_index(records, guard)
    retriever = HybridRetriever(index)

    cards = retriever.retrieve("计费业务涉及哪些文件", limit=5)

    sources = [card.source for card in cards]
    assert "docs/00_业务总结/计费业务总结.md" in sources
    assert "docs/05_需求设计/账单需求.md" in sources
    assert all("secret.env" not in card.source for card in cards)


def test_sqlite_fts_supports_chinese_phrase_recall(tmp_path):
    root = _workspace(tmp_path)
    records = scan_documents(root)
    index = build_hybrid_index(records)
    retriever = HybridRetriever(index)

    cards = retriever.retrieve("账单模块", limit=5)

    assert any(card.source == "docs/00_业务总结/计费业务总结.md" for card in cards)
    assert any("fts" in card.channels for card in cards)


def test_permission_denied_file_keeps_metadata_but_not_text(tmp_path):
    root = _workspace(tmp_path)
    guard = PermissionGuard({"file": {"deny": ["secret.env"]}, "dir": {"deny": ["*/private"]}})
    records = scan_documents(root, permission_guard=guard)

    denied = next(record for record in records if record.rel_path.endswith("secret.env"))
    assert denied.text == ""
    assert denied.comments == []
    assert denied.tables == []
    assert denied.metadata["permission_denied"] == "true"


def test_fuzzy_ratio_handles_close_chinese_names():
    assert fuzzy_ratio("产品规则详解.docx", "产品规则详细.docx") >= 0.75


def test_normalize_answer_sorts_paths_and_shapes_counts():
    assert normalize_answer({"datas": ["docs\\b.md", "docs/a.md", "docs/a.md"]}) == {
        "datas": ["docs/a.md", "docs/b.md"]
    }
    assert normalize_answer({"count": "3"}) == {"count": 3}
    assert normalize_answer({"source": "docs\\a.md", "target": "output\\fixed\\a.md"}) == {
        "source": "docs/a.md",
        "target": "output/fixed/a.md",
    }
