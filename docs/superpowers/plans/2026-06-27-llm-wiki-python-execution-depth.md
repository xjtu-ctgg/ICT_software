# LLM Wiki Python Execution Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Answer more realistic safe Python execution-result questions involving functions and loops while preserving strict refusal for unsafe code.

**Architecture:** Extend the existing constrained AST executor in `solver.py`. Keep the executor allowlist-based: add only simple control-flow and function nodes needed by tests, and leave imports, attributes, filesystem, process, network, and dunder access rejected.

**Tech Stack:** Python 3.11 standard library, `ast`, pytest.

---

### Task 1: Function And Loop Execution

**Files:**
- Modify: `tests/test_cli_integration.py`
- Modify: `work/llm_wiki_solver/solver.py`

- [x] **Step 1: Write failing test**

Add a safe Python file:

```python
def square(x):
    return x * x

total = 0
for number in [1, 2, 3]:
    total += square(number)
print(total)
```

Ask:

```python
{"id": "group-1-16", "title": "运行calc_loop.py并返回输出结果", "level": "困难"}
```

Expected:

```python
{"datas": ["14"]}
```

- [x] **Step 2: Run red test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: fail because the safe executor currently rejects function and loop AST nodes.

- [x] **Step 3: Extend AST allowlist minimally**

Allow `FunctionDef`, `Return`, `arguments`, `arg`, `For`, `AugAssign`, and safe loop targets. Keep `Import`, `Attribute`, `While`, `With`, `Try`, `Lambda`, comprehensions, and dunder names rejected.

- [x] **Step 4: Run green test**

Run: `pytest tests/test_cli_integration.py::test_run_solves_counts_comments_repair_and_safety -q`

Expected: pass, with existing unsafe `danger.py` still returning `error_msg`.

### Task 2: Verification And Records

**Files:**
- Modify: `result/output.md`

- [x] **Step 1: Run full test suite**

Run: `pytest tests -q`

Expected: all tests pass.

- [x] **Step 2: Run sample solver**

Run: `python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto`

Expected: `sample_llm_wiki/output/group-1-answer.md` is generated.

- [x] **Step 3: Update verification record**

Update `result/output.md` to mention safe Python function/loop execution coverage.
