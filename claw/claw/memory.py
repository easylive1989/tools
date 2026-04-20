import datetime as dt
from pathlib import Path


MEMORY_HEADER = "# pclaw memory\n\n每當你請 pclaw 「記住」什麼，就會追加在這裡；下次 CLI 啟動時會自動帶上。\n\n"


def ensure_memory_file(memory_path: Path) -> None:
    """Create the memory file if missing."""
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    if not memory_path.exists():
        memory_path.write_text(MEMORY_HEADER, encoding="utf-8")


def ensure_cli_symlinks(state_home: Path) -> None:
    """Point ~/.pclaw/CLAUDE.md and GEMINI.md at memory.md so both CLIs auto-load it.

    Claude Code auto-reads CLAUDE.md from cwd, Gemini reads GEMINI.md the same
    way — so a symlink in the pclaw cwd is enough for the memory to be part of
    every new CLI session's system prompt.
    """
    for name in ("CLAUDE.md", "GEMINI.md"):
        link = state_home / name
        if link.is_symlink():
            continue
        if link.exists():
            # Don't clobber a real file the user wrote themselves.
            continue
        link.symlink_to("memory.md")


def append_memory(memory_path: Path, text: str) -> str:
    """Append a dated bullet to memory.md. Returns the rendered entry."""
    ensure_memory_file(memory_path)
    today = dt.date.today().isoformat()
    entry = f"- {today}: {text.strip()}"
    with memory_path.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")
    return entry


def read_memory(memory_path: Path) -> str:
    if not memory_path.exists():
        return ""
    return memory_path.read_text(encoding="utf-8")
