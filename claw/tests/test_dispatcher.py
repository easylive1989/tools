import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from claw.dispatcher import Dispatcher, Job


def make_msg(channel_type: str, channel_id: int, msg_id: int):
    msg = MagicMock()
    msg.id = msg_id
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    # Dispatcher's isinstance(msg.channel, discord.Thread) check gets
    # short-circuited by MagicMock's default — patch behaviour via attribute.
    msg.channel.__class__.__name__ = channel_type
    return msg


@pytest.fixture(autouse=True)
def patch_thread_check(monkeypatch):
    """Make dispatcher's isinstance check hit a flag on our mock channel."""

    class _ThreadMarker:
        pass

    import claw.dispatcher as d

    monkeypatch.setattr(d.discord, "Thread", _ThreadMarker)

    def _coerce(kind, channel_id, msg_id):
        msg = make_msg(kind, channel_id, msg_id)
        if kind == "thread":
            msg.channel.__class__ = _ThreadMarker
        return msg

    return _coerce


async def test_same_thread_serializes(patch_thread_check) -> None:
    order: list[int] = []
    gate = asyncio.Event()

    async def handler(job):
        order.append(job.message.id)
        if job.message.id == 1:
            await gate.wait()

    d = Dispatcher(handler, max_concurrency=5)
    m1 = patch_thread_check("thread", 100, 1)
    m2 = patch_thread_check("thread", 100, 2)
    await d.submit(Job(m1))
    await d.submit(Job(m2))

    await asyncio.sleep(0.05)
    # m1 started, m2 still queued behind it
    assert order == [1]
    gate.set()
    await asyncio.sleep(0.05)
    assert order == [1, 2]
    await d.shutdown()


async def test_top_level_messages_parallel(patch_thread_check) -> None:
    running: set[int] = set()
    peak = 0
    gate = asyncio.Event()

    async def handler(job):
        nonlocal peak
        running.add(job.message.id)
        peak = max(peak, len(running))
        await gate.wait()
        running.discard(job.message.id)

    d = Dispatcher(handler, max_concurrency=5)
    m1 = patch_thread_check("text", 200, 101)
    m2 = patch_thread_check("text", 200, 102)
    m3 = patch_thread_check("text", 200, 103)
    await d.submit(Job(m1))
    await d.submit(Job(m2))
    await d.submit(Job(m3))

    await asyncio.sleep(0.05)
    assert peak == 3
    gate.set()
    await d.shutdown()


async def test_semaphore_caps_parallelism(patch_thread_check) -> None:
    running = 0
    peak = 0
    event = asyncio.Event()

    async def handler(job):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await event.wait()
        running -= 1

    d = Dispatcher(handler, max_concurrency=2)
    for i in range(5):
        await d.submit(Job(patch_thread_check("text", 300, i)))

    await asyncio.sleep(0.05)
    assert peak == 2
    event.set()
    await d.shutdown()
