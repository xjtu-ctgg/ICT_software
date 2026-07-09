from __future__ import annotations

from pathlib import Path


REQUIRED_SKILLS = {
    "llm-wiki-solver",
    "docx",
    "pptx",
    "xlsx",
}


def test_required_submission_root_files_and_directories_exist():
    root = Path(__file__).resolve().parents[1]

    assert (root / "INSTRUCTION.md").is_file()
    assert (root / "work").is_dir()
    assert (root / "result").is_dir()
    assert (root / "result" / "output.md").is_file()
    assert (root / "logs").is_dir()
    assert (root / "logs" / "interaction.md").is_file()
    assert (root / "logs" / "trace").is_dir()
    assert not (root / "work" / "skill").exists()


def test_required_skills_use_platform_path_and_frontmatter():
    root = Path(__file__).resolve().parents[1]
    for skill_name in REQUIRED_SKILLS:
        skill_path = root / "work" / "skills" / skill_name / "SKILL.md"
        assert skill_path.exists(), f"missing {skill_path}"
        text = skill_path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert f"name: {skill_name}" in text
        assert "description:" in text
        assert "/app/code/judge-assets/01_01_llm_wiki" in text or "./llm-wiki" in text
        assert "logs/trace" in text


def test_instruction_points_to_platform_skill_paths_and_cli():
    root = Path(__file__).resolve().parents[1]
    text = (root / "INSTRUCTION.md").read_text(encoding="utf-8")

    assert "work/skills/llm-wiki-solver/SKILL.md" in text
    assert "work/skills/docx/SKILL.md" in text
    assert "work/skills/pptx/SKILL.md" in text
    assert "work/skills/xlsx/SKILL.md" in text
    assert ".opencode" not in text
    assert "python work/llm_wiki_solver/main.py --root /app/code/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto" in text
