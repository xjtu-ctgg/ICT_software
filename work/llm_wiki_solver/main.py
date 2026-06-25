from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from work.llm_wiki_solver.models import Answer
    from work.llm_wiki_solver.solver import WikiSolver
else:
    from .models import Answer
    from .solver import WikiSolver


def run(
    root: Path | str,
    group: str = "all",
    log_dir: Path | str | None = None,
    llm_mode: str = "auto",
) -> list[Path]:
    root = Path(root)
    log_path = Path(log_dir) if log_dir else None
    solver = WikiSolver(root=root, log_dir=log_path, llm_mode=llm_mode)
    group_paths = _resolve_group_paths(root, group)
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for group_path in group_paths:
        answers = solver.solve_group(group_path)
        target = output_dir / f"{group_path.stem}-answer.md"
        target.write_text(
            json.dumps(_serialize_answers(answers), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Solve LLM Wiki contest questions.")
    parser.add_argument("--root", default="./llm-wiki", help="Path to llm-wiki directory")
    parser.add_argument("--group", default="all", help="Question group name, e.g. group-1 or all")
    parser.add_argument("--log-dir", default="./logs/trace", help="Trace log directory")
    parser.add_argument("--llm-mode", default="auto", choices=["off", "auto", "required"], help="LLM enhancement mode")
    args = parser.parse_args(argv)

    written = run(root=args.root, group=args.group, log_dir=args.log_dir, llm_mode=args.llm_mode)
    for path in written:
        print(path.as_posix())
    return 0


def _resolve_group_paths(root: Path, group: str) -> list[Path]:
    question_dir = root / "question"
    if group == "all":
        return sorted(question_dir.glob("group-*.md"))
    group_name = group if group.endswith(".md") else f"{group}.md"
    return [question_dir / group_name]


def _serialize_answers(answers: list[Answer]) -> list[dict]:
    return [{"id": answer.id, "answer": answer.answer} for answer in answers]


if __name__ == "__main__":
    raise SystemExit(main())
