from pathlib import Path

from .base import BaseCliAdapter, CliError, CliResult
from .gemini import GeminiAdapter


def get_adapter(kind: str, workdir: Path, model: str | None = None) -> BaseCliAdapter:
    if kind == "gemini":
        return GeminiAdapter(workdir=workdir, model=model)
    raise ValueError(f"Unsupported CLI kind: {kind}")


__all__ = ["BaseCliAdapter", "CliError", "CliResult", "GeminiAdapter", "get_adapter"]
