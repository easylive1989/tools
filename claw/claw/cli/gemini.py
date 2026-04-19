import asyncio
import os
import re
from pathlib import Path

from .base import BaseCliAdapter, CliError, CliResult


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r")
_UUID_RE = re.compile(
    r"\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]"
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _augment_path(env: dict[str, str]) -> dict[str, str]:
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    return env


class GeminiAdapter(BaseCliAdapter):
    kind = "gemini"

    def __init__(self, workdir: Path, model: str | None = None):
        super().__init__(workdir, model)
        self._new_session_lock = asyncio.Lock()

    async def run(self, prompt: str, session_id: str | None) -> CliResult:
        if session_id is None:
            return await self._new_session_run(prompt)
        return await self._resume_run(prompt, session_id)

    async def _new_session_run(self, prompt: str) -> CliResult:
        async with self._new_session_lock:
            before = await self._list_session_ids()
            reply = await self._invoke(self._build_args(prompt))
            after = await self._list_session_ids()
        new_ids = [sid for sid in after if sid not in before]
        if len(new_ids) != 1:
            raise CliError(
                f"Expected 1 new gemini session after run, got {len(new_ids)}: {new_ids}"
            )
        return CliResult(reply=reply, session_id=new_ids[0])

    async def _resume_run(self, prompt: str, session_id: str) -> CliResult:
        reply = await self._invoke(self._build_args(prompt, resume=session_id))
        return CliResult(reply=reply, session_id=session_id)

    def _build_args(self, prompt: str, *, resume: str | None = None) -> list[str]:
        args = ["gemini", "-o", "text"]
        if self.model:
            args += ["-m", self.model]
        if resume:
            args += ["-r", resume]
        args += ["-p", prompt]
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
            raise CliError(err or f"gemini exited {proc.returncode}")
        return _strip_ansi(stdout.decode(errors="replace")).strip()

    async def _list_session_ids(self) -> list[str]:
        env = _augment_path(os.environ.copy())
        proc = await asyncio.create_subprocess_exec(
            "gemini",
            "--list-sessions",
            cwd=str(self.workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, _ = await proc.communicate()
        return _UUID_RE.findall(_strip_ansi(stdout.decode(errors="replace")))
