# LLM Wiki Hidden Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve hidden-test readiness for TODO filtering, deterministic text repair, and XLSX table aggregation while keeping the solver dependency-light.

**Architecture:** Extend the existing rule-chain before the optional LLM layer. Keep extraction in `extractors.py`, question routing in `solver.py`, and add focused integration tests around realistic contest question wording.

**Tech Stack:** Python 3.11 standard library, `zipfile`/`xml.etree.ElementTree` for OOXML, pytest.

---

### Task 1: TODO Date Filtering

**Files:**
- Modify: `work/llm_wiki_solver/solver.py`
- Test: `tests/test_cli_integration.py`

- [x] **Step 1: Write failing tests**

Add integration questions for `end_date` filtering:

```python
{"id": "group-1-9", "title": "统计截止日期为20251015的TODO列表", "level": "中等"}
{"id": "group-1-10", "title": "统计责任人为李四且截止日期为20251015的TODO列表", "level": "困难"}
```

Expected answers:

```python
{"datas": ["todo: 待实现接口, to: 李四,end_date: 20251015"]}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because date filtering is not implemented.

- [x] **Step 3: Implement minimal routing and filtering**

Add `_extract_end_date(title)` and `_comments_by_filters(assignee=None, end_date=None)`. Route TODO/批注 questions with `截止日期` or `end_date` to the new filter.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 2: Deterministic Text Repair

**Files:**
- Modify: `work/llm_wiki_solver/solver.py`
- Test: `tests/test_cli_integration.py`

- [x] **Step 1: Write failing test**

Assert that repairing a Markdown TODO by assignee creates a target file whose TODO line is marked complete and no longer appears as an open TODO:

```python
assert "status: done" in repaired_text
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because the current rule-chain repair only copies the source file.

- [x] **Step 3: Implement minimal text repair**

For text-like files, copy content to `output/fixed` and replace matching structured TODO snippets with `status: done` appended before `end_date`. Leave binary and OOXML fallback behavior unchanged.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 3: XLSX Table Extraction And Aggregation

**Files:**
- Modify: `work/llm_wiki_solver/extractors.py`
- Modify: `work/llm_wiki_solver/solver.py`
- Test: `tests/test_cli_integration.py`

- [x] **Step 1: Write failing test**

Create a minimal `.xlsx` with shared strings and numeric rows:

```text
客户,金额
A,10
A,15
B,7
```

Ask:

```python
{"id": "group-1-11", "title": "根据费用统计.xlsx 按客户汇总金额", "level": "困难"}
```

Expected:

```python
{"datas": ["A:25", "B:7"]}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because `tables` is empty and aggregation routing is absent.

- [x] **Step 3: Implement minimal XLSX parsing**

Parse `xl/sharedStrings.xml` and `xl/worksheets/sheet*.xml` into `DocumentRecord.tables` as row lists. Include table cell text in `DocumentRecord.text` for retrieval.

- [x] **Step 4: Implement minimal aggregation routing**

For questions containing `汇总` plus a filename, locate the workbook, infer the group column from `按客户`, infer the numeric column from `金额`, sum numeric values, and return sorted `datas`.

- [x] **Step 5: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 4: Full Verification

**Files:**
- No production changes unless failures expose issues.

- [x] **Step 1: Run full test suite**

Run: `pytest tests -q`

Expected: all tests pass.

- [x] **Step 2: Run sample solver**

Run: `python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto`

Expected: `sample_llm_wiki/output/group-1-answer.md` is generated.
