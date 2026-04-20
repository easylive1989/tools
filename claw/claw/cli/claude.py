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
            reply = await self._invoke(self._build_args(prompt, session_id, is_new=True))
        else:
            reply = await self._invoke(self._build_args(prompt, session_id, is_new=False))
        return CliResult(reply=reply, session_id=session_id)

    def _build_args(self, prompt: str, session_id: str, *, is_new: bool) -> list[str]:
        args = ["claude", "-p", "--output-format", "text"]
        if self.model:
            args += ["--model", self.model]
        if is_new:
            args += ["--session-id", session_id]
        else:
            args += ["--resume", session_id]
        # Disable tools: claw is a text-only assistant, no Bash/Edit/Read needed
        # (attachments come in as @refs which are inlined, not tool-fetched).
        args += ["--tools", ""]
        args += [prompt]
        return args

    async def _invoke(self, args: list[str]) -> str:
        env = _augment_path(os.environ.copy())
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = _strip_ansi(stderr.decode(errors="replace")).strip()
            raise CliError(err or f"claude exited {proc.returncode}")
        return _strip_ansi(stdout.decode(errors="replace")).strip()
