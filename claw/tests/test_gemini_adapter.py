from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from claw.cli import CliError, GeminiAdapter


SAMPLE_LIST_ONE = b"""Available sessions for this project (1):
  1. hello (1 min ago) [aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa]
"""

SAMPLE_LIST_TWO = b"""Available sessions for this project (2):
  1. hello (2 min ago) [aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa]
  2. follow up (1 min ago) [bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb]
"""

SAMPLE_NONE = b"No previous sessions found for this project.\n"


class FakeProc:
    def __init__(self, returncode: int, stdout: bytes, stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.fixture
def adapter(tmp_path: Path) -> GeminiAdapter:
    return GeminiAdapter(workdir=tmp_path / "workdir")


async def test_new_session_diffs_and_captures_id(adapter: GeminiAdapter) -> None:
    # Sequence of subprocess calls: list (before), gemini -p (run), list (after)
    call_sequence = [
        FakeProc(0, SAMPLE_NONE),
        FakeProc(0, b"hi there\n"),
        FakeProc(0, SAMPLE_LIST_ONE),
    ]
    call_iter = iter(call_sequence)

    async def fake_exec(*args, **kwargs):
        return next(call_iter)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec) as mock_exec:
        result = await adapter.run("hello", session_id=None)

    assert result.reply == "hi there"
    assert result.session_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    # 3 subprocess calls: list, run, list
    assert mock_exec.call_count == 3


async def test_resume_passes_session_id(adapter: GeminiAdapter) -> None:
    calls: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc(0, b"resumed reply\n")

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await adapter.run("continue", session_id="ff-11")

    assert result.reply == "resumed reply"
    assert result.session_id == "ff-11"
    assert "-r" in calls[0]
    assert "ff-11" in calls[0]
    assert "-p" in calls[0]


async def test_cli_nonzero_raises(adapter: GeminiAdapter) -> None:
    async def fake_exec(*args, **kwargs):
        return FakeProc(1, b"", b"boom\n")

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        with pytest.raises(CliError, match="boom"):
            await adapter.run("continue", session_id="ff-11")


async def test_new_session_count_mismatch_raises(adapter: GeminiAdapter) -> None:
    # Before shows 1 session, after still shows 1 (run didn't create one)
    call_sequence = [
        FakeProc(0, SAMPLE_LIST_ONE),
        FakeProc(0, b"reply\n"),
        FakeProc(0, SAMPLE_LIST_ONE),
    ]
    call_iter = iter(call_sequence)

    async def fake_exec(*args, **kwargs):
        return next(call_iter)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        with pytest.raises(CliError, match="Expected 1 new"):
            await adapter.run("hello", session_id=None)


async def test_model_is_passed(adapter: GeminiAdapter, tmp_path: Path) -> None:
    adapter = GeminiAdapter(workdir=tmp_path / "w", model="gemini-2.5-pro")
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc(0, b"hi\n")

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await adapter.run("x", session_id="existing")

    assert "-m" in calls[0]
    assert "gemini-2.5-pro" in calls[0]
