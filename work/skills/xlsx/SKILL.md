---
name: xlsx
description: Analyze XLSX/XLS tables for LLM Wiki tasks with safe row filtering, counting, grouping, and formula-aware fallback guidance.
---

# XLSX Skill for LLM Wiki

Use this skill only as support for the LLM Wiki solver when Excel files under `/app/code/judge-assets/01_01_llm_wiki/docs` or `./llm-wiki/docs` are involved.

## Scope

- Extract `.xlsx` sheets from OOXML using shared strings and worksheet rows.
- Convert legacy `.xls` to `.xlsx` only when LibreOffice is available.
- Support table-style questions: filter rows, count records, list column values, and group numeric values by a column.
- Keep trace information under `logs/trace`.
- Return answers in solver JSON format only.

## Procedure

1. Let `work/llm_wiki_solver/main.py` scan workbook rows.
2. Resolve columns by exact or close header match.
3. Apply conditions such as `为`, `等于`, `大于`, `小于`, `>=`, `<=`, and multi-condition filters.
4. For repair tasks, write only to `llm-wiki/output/fixed/`.

## Safety

- Do not execute macros or external links.
- Do not read denied files or system paths.
- Do not expose forbidden secrets.
- Dangerous requests must return `{"error_msg":"高危命令，拒绝访问"}`.
