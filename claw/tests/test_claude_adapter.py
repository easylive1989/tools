import re
from pathlib import Path
from unittest.mock import patch

import pytest

from claw.cli import ClaudeAdapter, CliError


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class FakeProc:
    def __init__(self, returncode: int, stdout: bytes, stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.received_stdin: bytes | None = None

    async def communicate(self, input: bytes | None = None):
        self.received_stdin = input
        return self._stdout, self._stderr


@pytest.fixture
def adapter(tmp_path: Path) -> ClaudeAdapter:
    return ClaudeAdapter(workdir=tmp_path / "workdir")


async def test_new_session_generates_uuid_and_passes_session_id(adapter: ClaudeAdapter) -> None:
    captured: list[FakeProc] = []

    async def fake_exec(*args, **kwargs):
        proc = FakeProc(0, b"hi there\n")
        proc.args = args
        captured.append(proc)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await adapter.run("hello", session_id=None)

    assert result.reply == "hi there"
    assert _UUID_RE.match(result.session_id)
    assert "--session-id" in captured[0].args
    assert result.session_id in captured[0].args
    assert "--resume" not in captured[0].args


async def test_resume_uses_existing_id(adapter: ClaudeAdapter) -> None:
    captured: list[FakeProc] = []

    async def fake_exec(*args, **kwargs):
        proc = FakeProc(0, b"resumed\n")
        proc.args = args
        captured.append(proc)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await adapter.run("continue", session_id="11111111-2222-3333-4444-555555555555")

    assert result.reply == "resumed"
    assert result.session_id == "11111111-2222-3333-4444-555555555555"
    assert "--resume" in captured[0].args
    assert "11111111-2222-3333-4444-555555555555" in captured[0].args
    assert "--session-id" not in captured[0].args


async def test_prompt_sent_via_stdin_not_argv(adapter: ClaudeAdapter) -> None:
    """The prompt must go through stdin; otherwise Claude's variadic options
    (--tools, --allowedTools, etc.) can greedily absorb it and fail."""
    captured: list[FakeProc] = []

    async def fake_exec(*args, **kwargs):
        proc = FakeProc(0, b"ok\n")
        proc.args = args
        captured.append(proc)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await adapter.run("幫我找一下 0050 的價格", session_id=None)

    assert "幫我找一下 0050 的價格" not in captured[0].args
    assert captured[0].received_stdin == "幫我找一下 0050 的價格".encode("utf-8")


async def test_allowed_tools_passed(adapter: ClaudeAdapter) -> None:
    captured: list[FakeProc] = []

    async def fake_exec(*args, **kwargs):
        proc = FakeProc(0, b"ok\n")
        proc.args = args
        captured.append(proc)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await adapter.run("x", session_id=None)

    args = captured[0].args
    assert "--allowedTools" in args
    # Read must be in the allow-list so @ref attachments resolve.
    assert "Read" in args
    assert "WebSearch" in args
    # Write/Bash/Edit stay blocked.
    assert "Bash" not in args
    assert "Write" not in args


async def test_non_zero_raises(adapter: ClaudeAdapter) -> None:
    async def fake_exec(*args, **kwargs):
        return FakeProc(1, b"", b"bad auth\n")

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        with pytest.raises(CliError, match="bad auth"):
            await adapter.run("x", session_id=None)


async def test_model_is_passed(tmp_path: Path) -> None:
    adapter = ClaudeAdapter(workdir=tmp_path / "w", model="opus")
    captured: list[FakeProc] = []

    async def fake_exec(*args, **kwargs):
        proc = FakeProc(0, b"ok\n")
        proc.args = args
        captured.append(proc)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await adapter.run("x", session_id="aa")

    assert "--model" in captured[0].args
    assert "opus" in captured[0].args
