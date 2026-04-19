from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class CliError(RuntimeError):
    """Raised when a CLI subprocess exits non-zero or its output can't be parsed."""


@dataclass
class CliResult:
    reply: str
    session_id: str


class BaseCliAdapter(ABC):
    """Subprocess wrapper around a local AI CLI (gemini, claude, codex)."""

    kind: str  # class-level: 'gemini' | 'claude' | 'codex'

    def __init__(self, workdir: Path, model: str | None = None):
        self.workdir = workdir
        self.model = model
        self.workdir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    async def run(self, prompt: str, session_id: str | None) -> CliResult:
        """Run one turn.

        - session_id=None: start a new session, capture the CLI-assigned id.
        - session_id!=None: resume that session.
        """
