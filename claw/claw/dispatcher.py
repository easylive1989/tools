import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

import discord


log = logging.getLogger(__name__)


@dataclass
class Job:
    message: discord.Message


JobHandler = Callable[[Job], Awaitable[None]]


class Dispatcher:
    """Per-thread FIFO queues + global concurrency cap.

    Jobs sharing the same `queue_key` are processed strictly in insertion order
    (no parallelism within a queue). Across queues, up to `max_concurrency`
    jobs run simultaneously.
    """

    def __init__(self, handler: JobHandler, max_concurrency: int):
        self._handler = handler
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._queues: dict[str, asyncio.Queue[Job]] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._shutdown = False

    async def submit(self, job: Job) -> None:
        key = self._queue_key(job.message)
        async with self._lock:
            if self._shutdown:
                return
            queue = self._queues.get(key)
            if queue is None:
                queue = asyncio.Queue()
                self._queues[key] = queue
                self._workers[key] = asyncio.create_task(self._worker(key, queue))
        await queue.put(job)

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutdown = True
            workers = list(self._workers.values())
        for w in workers:
            w.cancel()
        for w in workers:
            try:
                await w
            except (asyncio.CancelledError, Exception):
                pass

    def _queue_key(self, msg: discord.Message) -> str:
        # Thread messages serialize per-thread. Top-level channel messages each
        # spawn a fresh session and should run in parallel, so each gets a
        # unique one-shot queue keyed by message id.
        if isinstance(msg.channel, discord.Thread):
            return f"thread:{msg.channel.id}"
        return f"msg:{msg.id}"

    async def _worker(self, key: str, queue: asyncio.Queue[Job]) -> None:
        while True:
            job = await queue.get()
            try:
                async with self._semaphore:
                    await self._handler(job)
            except Exception:
                log.exception("dispatcher handler failed for %s", job.message.id)
            finally:
                queue.task_done()
