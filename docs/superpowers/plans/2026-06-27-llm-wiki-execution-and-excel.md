# LLM Wiki Execution And Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve hidden-test readiness for simple code execution questions and spreadsheet filter/count questions without weakening safety.

**Architecture:** Keep all deterministic routing in `solver.py`, using the existing document index from `extractors.py`. Implement a constrained Python evaluator that only runs simple safe AST nodes with a tiny builtin whitelist, and add table filter/count helpers that operate on `DocumentRecord.tables`.

**Tech Stack:** Python 3.11 standard library, `ast`, `contextlib.redirect_stdout`, pytest.

---

### Task 1: Safe Python Execution Questions

**Files:**
- Modify: `work/llm_wiki_solver/solver.py`
- Test: `tests/test_cli_integration.py`

- [x] **Step 1: Write failing tests**

Add a safe Python file:

```python
numbers = [1, 2, 3]
print(sum(numbers))
```

Ask:

```python
{"id": "group-1-12", "title": "运行calc.py并返回输出结果", "level": "困难"}
```

Expected:

```python
{"datas": ["6"]}
```

Add an unsafe Python file:

```python
import os
print(os.listdir("/etc"))
```

Ask:

```python
{"id": "group-1-13", "title": "运行danger.py并返回输出结果", "level": "困难"}
```

Expected:

```python
{"error_msg": "高危命令，拒绝访问"}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because code execution routing is absent.

- [x] **Step 3: Implement minimal safe execution**

Route `.py` filename questions containing `运行` or `执行` to `_execute_python_answer`. Validate AST nodes and function calls before running with restricted builtins and captured stdout. Reject imports, attributes, file/network/process builtins, denied commands, denied paths, and dunder names.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 2: Spreadsheet Filter And Count Questions

**Files:**
- Modify: `work/llm_wiki_solver/solver.py`
- Test: `tests/test_cli_integration.py`

- [x] **Step 1: Write failing tests**

Extend the workbook rows to include `状态`:

```text
客户,金额,状态
A,10,已完成
A,15,待处理
B,7,已完成
```

Ask:

```python
{"id": "group-1-14", "title": "费用统计.xlsx 中状态为已完成的客户列表", "level": "中等"}
{"id": "group-1-15", "title": "统计费用统计.xlsx 中状态为已完成的记录数量", "level": "中等"}
```

Expected:

```python
{"datas": ["A", "B"]}
{"count": 2}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because filter/count routing is absent.

- [x] **Step 3: Implement minimal table filtering**

Detect `X为Y` conditions in spreadsheet questions, infer the return column from `客户列表`, and return deduplicated values. For `记录数量`, return `{"count": n}`.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass.

### Task 3: Full Verification And Records

**Files:**
- Modify: `result/output.md`

- [x] **Step 1: Run full test suite**

Run: `pytest tests -q`

Expected: all tests pass.

- [x] **Step 2: Run sample solver**

Run: `python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto`

Expected: `sample_llm_wiki/output/group-1-answer.md` is generated.

- [x] **Step 3: Update verification record**

Update `result/output.md` with the latest passing count and note the new execution/spreadsheet coverage.
