# LLM Wiki Excel Conditions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve hidden-test readiness for spreadsheet questions that combine multiple equality filters with list/count/sum answers.

**Architecture:** Extend `solver.py` table helpers so all spreadsheet operations share one condition parser. Keep support deterministic and header-driven: parse `列为值` phrases, match them to table headers, filter rows, then return lists/counts or grouped sums.

**Tech Stack:** Python 3.11 standard library, pytest.

---

### Task 1: Multi-Condition Table Filtering

**Files:**
- Modify: `tests/test_cli_integration.py`
- Modify: `work/llm_wiki_solver/solver.py`

- [x] **Step 1: Write failing test**

Add a question:

```python
{"id": "group-1-17", "title": "费用统计.xlsx 中状态为已完成且客户为A的金额列表", "level": "困难"}
```

Expected:

```python
{"datas": ["10"]}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because table filtering currently parses only one condition.

- [x] **Step 3: Implement multi-condition filtering**

Replace the single-condition parser with `_extract_table_conditions`, returning all `列为值` conditions. Update filtering to require all matched conditions.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 2: Conditional Grouped Sum

**Files:**
- Modify: `tests/test_cli_integration.py`
- Modify: `work/llm_wiki_solver/solver.py`

- [x] **Step 1: Write failing test**

Add a question:

```python
{"id": "group-1-18", "title": "根据费用统计.xlsx 按客户汇总状态为已完成的金额", "level": "困难"}
```

Expected:

```python
{"datas": ["A:10", "B:7"]}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because aggregation ignores conditions and returns all rows.

- [x] **Step 3: Implement conditional aggregation**

Before grouping, apply parsed table conditions to rows. Keep existing unconditional grouped sum behavior unchanged.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 3: Verification And Records

**Files:**
- Modify: `result/output.md`

- [x] **Step 1: Run full test suite**

Run: `pytest tests -q`

Expected: all tests pass.

- [x] **Step 2: Run sample solver**

Run: `python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto`

Expected: `sample_llm_wiki/output/group-1-answer.md` is generated.

- [x] **Step 3: Update verification record**

Update `result/output.md` to mention multi-condition spreadsheet coverage.
