from pathlib import Path

import pytest

from claw.skills import SkillRegistry, parse_slash


def _write_skill(root: Path, name: str, body: str, description: str = "") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_parse_slash_with_args() -> None:
    assert parse_slash("/summary hello world") == ("summary", "hello world")


def test_parse_slash_no_args() -> None:
    assert parse_slash("/daily") == ("daily", "")


def test_parse_slash_multiline_args() -> None:
    assert parse_slash("/summary line1\nline2") == ("summary", "line1\nline2")


def test_parse_slash_rejects_non_leading() -> None:
    assert parse_slash("read /etc/hosts") is None


def test_registry_loads_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "summary", "Summarize:\n\n{{input}}")
    _write_skill(tmp_path, "translate", "Translate to English:\n\n{{input}}")

    reg = SkillRegistry(tmp_path)
    assert reg.names() == ["summary", "translate"]
    assert reg.get("summary").render("hello").endswith("hello")


def test_render_appends_when_no_placeholder(tmp_path: Path) -> None:
    _write_skill(tmp_path, "cheer", "Always be positive.")
    reg = SkillRegistry(tmp_path)
    rendered = reg.get("cheer").render("today is monday")
    assert rendered.startswith("Always be positive.")
    assert rendered.endswith("today is monday")


def test_missing_frontmatter_is_skipped(tmp_path: Path) -> None:
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here", encoding="utf-8")

    reg = SkillRegistry(tmp_path)
    assert reg.get("broken") is None


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    reg = SkillRegistry(tmp_path / "does-not-exist")
    assert reg.names() == []
