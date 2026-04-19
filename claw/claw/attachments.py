import logging
import re
from pathlib import Path

import discord


log = logging.getLogger(__name__)

_SAFE_RE = re.compile(r"[^\w.\-]")


def sanitize_filename(name: str) -> str:
    """Strip directory components and non-word characters from an uploaded filename.

    Returns a name safe to use as a path segment under `workdir/attachments/...`.
    """
    base = Path(name).name or "file"
    collapsed = _SAFE_RE.sub("_", base.replace(" ", "_"))
    collapsed = collapsed.strip("_") or "file"
    return collapsed[:120]


def build_attachment_prompt(base: str, rel_paths: list[str]) -> str:
    """Compose a gemini-style prompt that references downloaded attachments.

    Uses gemini CLI's `@relative/path` reference syntax so the model pulls the
    file content (text, image, pdf, ...) into context.
    """
    if not rel_paths:
        return base
    refs = " ".join(f"@{p}" for p in rel_paths)
    if base.strip():
        return f"{base}\n\n{refs}"
    return refs


async def download_attachments(
    message: discord.Message,
    workdir: Path,
) -> list[str]:
    """Save every attachment on `message` under `<workdir>/attachments/<msg_id>/`.

    Returns the list of paths relative to `workdir` (suitable for `@` refs in
    a gemini prompt). Failed downloads are logged and skipped — stale Discord
    CDN URLs (from long-offline backfill) are the most common failure.
    """
    if not message.attachments:
        return []

    dest_dir = workdir / "attachments" / str(message.id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    rel_paths: list[str] = []
    for att in message.attachments:
        local_path = dest_dir / sanitize_filename(att.filename)
        try:
            await att.save(local_path)
        except (discord.HTTPException, OSError) as e:
            log.warning("attachment download failed for %s: %s", att.filename, e)
            continue
        rel_paths.append(str(local_path.relative_to(workdir)))
    return rel_paths
