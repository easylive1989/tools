import io
import re

import discord


DISCORD_HARD_LIMIT = 2000
SOFT_CHUNK = 1900
ATTACH_THRESHOLD = 10_000


def _split_by_boundary(text: str, boundary: str, chunk_size: int) -> list[str]:
    parts = text.split(boundary)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        piece = part + boundary
        if len(buf) + len(piece) > chunk_size:
            if buf:
                chunks.append(buf)
            if len(piece) > chunk_size:
                # single piece too long, caller will do next-level split
                chunks.append(piece)
                buf = ""
            else:
                buf = piece
        else:
            buf += piece
    if buf:
        chunks.append(buf)
    # Trim trailing boundary (we appended one extra in the last piece)
    return [c.rstrip(boundary) if c.endswith(boundary) else c for c in chunks]


def split_for_discord(text: str, chunk_size: int = SOFT_CHUNK) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    # paragraph → sentence → hard cut
    chunks = _split_by_boundary(text, "\n\n", chunk_size)

    refined: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            refined.append(chunk)
            continue
        for sub in _split_by_boundary(chunk, ". ", chunk_size):
            if len(sub) <= chunk_size:
                refined.append(sub)
            else:
                # hard cut
                for i in range(0, len(sub), chunk_size):
                    refined.append(sub[i : i + chunk_size])
    return [c for c in refined if c]


async def send_reply(channel: discord.abc.Messageable, text: str) -> None:
    text = text.strip()
    if not text:
        await channel.send("_(empty reply)_")
        return

    if len(text) > ATTACH_THRESHOLD:
        summary = text[:SOFT_CHUNK]
        file = discord.File(io.BytesIO(text.encode("utf-8")), filename="reply.md")
        await channel.send(
            content=summary + "\n\n_(output too long, see attachment)_",
            file=file,
        )
        return

    for chunk in split_for_discord(text):
        await channel.send(chunk)
