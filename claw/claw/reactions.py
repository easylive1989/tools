import logging

import discord


QUEUED = "⏳"
DONE = "✅"
ERROR = "❌"

log = logging.getLogger(__name__)


async def _safe_add(msg: discord.Message, emoji: str) -> None:
    try:
        await msg.add_reaction(emoji)
    except discord.HTTPException as e:
        log.warning("add_reaction %s failed on %s: %s", emoji, msg.id, e)


async def _safe_remove(msg: discord.Message, emoji: str) -> None:
    try:
        await msg.remove_reaction(emoji, msg.guild.me if msg.guild else None)
    except discord.HTTPException as e:
        log.warning("remove_reaction %s failed on %s: %s", emoji, msg.id, e)


async def mark_queued(msg: discord.Message) -> None:
    await _safe_add(msg, QUEUED)


async def mark_done(msg: discord.Message) -> None:
    await _safe_remove(msg, QUEUED)
    await _safe_add(msg, DONE)


async def mark_error(msg: discord.Message) -> None:
    await _safe_remove(msg, QUEUED)
    await _safe_add(msg, ERROR)
