import logging
from typing import Awaitable, Callable

import discord

from . import reactions
from .dispatcher import Job
from .storage import Storage


log = logging.getLogger(__name__)

SubmitFn = Callable[[Job], Awaitable[None]]


async def backfill_channel(
    client: discord.Client,
    channel_id: int,
    storage: Storage,
    enqueue: SubmitFn,
) -> None:
    """Re-process any Discord messages missed while the bot was offline.

    Walks the channel and all tracked threads, picking up messages whose snowflake
    exceeds the stored last_processed_id. Already-processed messages (per the DB)
    are skipped to avoid duplicate work on restart.
    """
    try:
        channel = await client.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden) as e:
        log.error("cannot fetch channel %s: %s", channel_id, e)
        return

    last_id = storage.get_last_processed_id(str(channel_id))
    after = discord.Object(id=int(last_id)) if last_id else None

    missed = 0
    async for msg in channel.history(after=after, limit=None, oldest_first=True):
        if not _should_process(msg, client):
            continue
        if storage.is_processed(str(msg.id)):
            continue

        newly = storage.record_message(
            message_id=str(msg.id),
            channel_id=str(msg.channel.id),
            thread_id=None,
            author_id=str(msg.author.id),
            content=msg.content,
            created_at=int(msg.created_at.timestamp()),
        )
        if newly:
            await reactions.mark_queued(msg)
        await enqueue(Job(message=msg))
        missed += 1

    # Now fetch missed replies in each tracked thread
    for thread_row in storage.list_threads():
        try:
            thread = await client.fetch_channel(int(thread_row.thread_id))
        except (discord.NotFound, discord.Forbidden):
            continue
        if not isinstance(thread, discord.Thread):
            continue

        thread_last = storage.last_message_id_in_thread(thread_row.thread_id)
        t_after = discord.Object(id=int(thread_last)) if thread_last else None

        async for msg in thread.history(after=t_after, limit=None, oldest_first=True):
            if not _should_process(msg, client):
                continue
            if storage.is_processed(str(msg.id)):
                continue
            newly = storage.record_message(
                message_id=str(msg.id),
                channel_id=str(thread.parent_id),
                thread_id=str(thread.id),
                author_id=str(msg.author.id),
                content=msg.content,
                created_at=int(msg.created_at.timestamp()),
            )
            if newly:
                await reactions.mark_queued(msg)
            await enqueue(Job(message=msg))
            missed += 1

    if missed:
        log.info("backfill enqueued %d missed messages", missed)


def _should_process(msg: discord.Message, client: discord.Client) -> bool:
    if msg.author.bot:
        return False
    if client.user and msg.author.id == client.user.id:
        return False
    return True
