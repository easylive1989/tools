import asyncio
import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CronJob:
    name: str
    schedule: str             # standard cron: "minute hour dom month dow"
    prompt: str
    skill: str | None = None


JobRunner = Callable[[CronJob], Awaitable[None]]


def load_jobs(path: Path) -> list[CronJob]:
    if not path.exists():
        return []
    with path.open("rb") as f:
        raw = tomllib.load(f)
    jobs: list[CronJob] = []
    for entry in raw.get("jobs", []):
        jobs.append(
            CronJob(
                name=str(entry["name"]),
                schedule=str(entry["schedule"]),
                prompt=str(entry["prompt"]),
                skill=entry.get("skill"),
            )
        )
    return jobs


class CronScheduler:
    """Thin wrapper over APScheduler that fires `runner(job)` per cron hit."""

    def __init__(self, jobs: list[CronJob], runner: JobRunner):
        self._jobs = jobs
        self._runner = runner
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        for job in self._jobs:
            try:
                trigger = CronTrigger.from_crontab(job.schedule)
            except ValueError as e:
                log.error("cron job %s has invalid schedule %r: %s", job.name, job.schedule, e)
                continue
            self._scheduler.add_job(
                self._fire,
                trigger=trigger,
                args=[job],
                id=job.name,
                name=job.name,
                coalesce=True,                # missed runs collapse into one
                misfire_grace_time=60 * 60,
                max_instances=1,
                replace_existing=True,
            )
        if self._jobs:
            self._scheduler.start()
            log.info("cron scheduler started with %d jobs", len(self._jobs))

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def _fire(self, job: CronJob) -> None:
        try:
            await self._runner(job)
        except Exception:
            log.exception("cron job %s failed", job.name)
