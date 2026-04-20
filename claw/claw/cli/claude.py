import asyncio
import os
import re
import uuid
from pathlib import Path

from .base import BaseCliAdapter, CliError, CliResult


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _augment_path(env: dict[str, str]) -> dict[str, str]:
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    return env


class ClaudeAdapter(BaseCliAdapter):
    """Claude Code CLI in `-p` (print) mode.

    Unlike Gemini, Claude accepts a pre-specified session UUID via
    `--session-id`, so the first turn picks a UUID and subsequent turns
    resume it with `-r`. No need to diff --list-sessions.
    """

    kind = "claude"

    def __init__(self, workdir: Path, model: str | None = None):
        super().__init__(workdir, model)

    async def run(self, prompt: str, session_id: str | None) -> CliResult:
        if session_id is None:
            session_id = str(uuid.uuid4())
            args = self._build_args(session_id, is_new=True)
        else:
            args = self._build_args(session_id, is_new=False)
        reply = await self._invoke(args, prompt)
        return CliResult(reply=reply, session_id=session_id)

    def _build_args(self, session_id: str, *, is_new: bool) -> list[str]:
        args = ["claude", "-p", "--output-format", "text"]
        if self.model:
            args += ["--model", self.model]
        if is_new:
            args += ["--session-id", session_id]
        else:
            args += ["--resume", session_id]
        # Prompt goes via stdin, not as a positional arg, to avoid collisions
        # with Claude Code's variadic option parsing (e.g. --tools/--allowedTools
        # greedily absorbing following positionals).
        return args

    async def _invoke(self, args: list[str], prompt: str) -> str:
        env = _augment_path(os.environ.copy())
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.workdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate(input=prompt.encode("utf-8"))
        if proc.returncode != 0:
            err = _strip_ansi(stderr.decode(errors="replace")).strip()
            raise CliError(err or f"claude exited {proc.returncode}")
        return _strip_ansi(stdout.decode(errors="replace")).strip()
