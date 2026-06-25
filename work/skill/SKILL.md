---
name: llm-wiki-solver
description: Solve ICT AI Arena LLM Wiki question groups with deterministic document indexing, TODO/comment handling, repair output, and safety refusal.
---

# LLM Wiki Solver Skill

Use this skill when the current workspace contains an `llm-wiki` directory with `docs`, `question`, `output`, and `Permission.json`.

## Run

Execute the Python solver from the package root:

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group all --log-dir ./logs/trace --llm-mode auto
```

For one group:

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group group-1 --log-dir ./logs/trace --llm-mode auto
```

## Behavior

- Scan all files under `llm-wiki/docs`.
- Extract text, Office comments, and code TODO comments.
- Reject dangerous command, path, file, and password requests according to `Permission.json` and built-in safety rules.
- Write JSON answers to `llm-wiki/output/group-x-answer.md`.
- Copy repaired files to `llm-wiki/output/fixed/`.
- Write trace summaries under `logs/trace/`.
- Use optional LLM enhancement in `auto` mode when model environment variables are configured; otherwise fall back to deterministic rules.
- Keep all LLM outputs schema-bound: query planning, answer drafting, and repair planning all go through structured JSON validation before use.
