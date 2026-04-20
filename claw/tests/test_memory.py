from pathlib import Path

from claw import memory


def test_ensure_memory_file_creates_with_header(tmp_path: Path) -> None:
    p = tmp_path / "memory.md"
    memory.ensure_memory_file(p)
    assert p.exists()
    assert p.read_text(encoding="utf-8").startswith("# pclaw memory")


def test_ensure_memory_file_keeps_existing(tmp_path: Path) -> None:
    p = tmp_path / "memory.md"
    p.write_text("custom content\n", encoding="utf-8")
    memory.ensure_memory_file(p)
    assert p.read_text(encoding="utf-8") == "custom content\n"


def test_append_memory_adds_dated_bullet(tmp_path: Path) -> None:
    p = tmp_path / "memory.md"
    entry = memory.append_memory(p, "喜歡喝無糖茶")
    assert entry.endswith("喜歡喝無糖茶")
    body = p.read_text(encoding="utf-8")
    assert "喜歡喝無糖茶" in body
    assert body.startswith("# pclaw memory")


def test_append_memory_strips_whitespace(tmp_path: Path) -> None:
    p = tmp_path / "memory.md"
    memory.append_memory(p, "  leading and trailing  \n")
    assert "leading and trailing" in p.read_text(encoding="utf-8")
    assert "  leading" not in p.read_text(encoding="utf-8")


def test_ensure_cli_symlinks_creates_both(tmp_path: Path) -> None:
    memory.ensure_memory_file(tmp_path / "memory.md")
    memory.ensure_cli_symlinks(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    gemini_md = tmp_path / "GEMINI.md"
    assert claude_md.is_symlink()
    assert gemini_md.is_symlink()
    assert claude_md.read_text(encoding="utf-8").startswith("# pclaw memory")


def test_ensure_cli_symlinks_skips_real_files(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("user-authored\n", encoding="utf-8")
    memory.ensure_memory_file(tmp_path / "memory.md")
    memory.ensure_cli_symlinks(tmp_path)
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "user-authored\n"
    assert not (tmp_path / "CLAUDE.md").is_symlink()
