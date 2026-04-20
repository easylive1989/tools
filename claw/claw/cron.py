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


def _toml_string(value: str) -> str:
    """Serialise a string for cron.toml using basic or multi-line TOML syntax."""
    if "\n" in value or '"' in value:
        escaped = value.replace("\\", "\\\\").replace('"""', '\\"""')
        return f'"""{escaped}"""'
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_jobs(path: Path, jobs: list[CronJob]) -> None:
    """Rewrite cron.toml with the given jobs. Deterministic; overwrites in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for job in jobs:
        lines = [
            "[[jobs]]",
            f"name = {_toml_string(job.name)}",
            f"schedule = {_toml_string(job.schedule)}",
        ]
        if job.skill:
            lines.append(f"skill = {_toml_string(job.skill)}")
        lines.append(f"prompt = {_toml_string(job.prompt)}")
        blocks.append("\n".join(lines))
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def upsert_job(path: Path, job: CronJob) -> list[CronJob]:
    """Insert or replace a job by name. Returns the resulting job list."""
    jobs = [j for j in load_jobs(path) if j.name != job.name]
    jobs.append(job)
    save_jobs(path, jobs)
    return jobs


def remove_job(path: Path, name: str) -> bool:
    """Remove a job by name. Returns True if a match was found and removed."""
    jobs = load_jobs(path)
    remaining = [j for j in jobs if j.name != name]
    if len(remaining) == len(jobs):
        return False
    save_jobs(path, remaining)
    return True


class CronScheduler:
    """Thin wrapper over APScheduler that fires `runner(job)` per cron hit."""

    def __init__(self, jobs: list[CronJob], runner: JobRunner):
        self._jobs = jobs
        self._runner = runner
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        for job in self._jobs:
            self._add(job)
        if self._jobs:
            self._scheduler.start()
            log.info("cron scheduler started with %d jobs", len(self._jobs))

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def reload(self, jobs: list[CronJob]) -> None:
        """Replace the current job set without re-creating the scheduler.

        Safe to call while the scheduler is running — existing triggers are
        removed and new ones installed in place.
        """
        for existing in list(self._scheduler.get_jobs()):
            existing.remove()
        self._jobs = jobs
        for job in jobs:
            self._add(job)
        if not self._scheduler.running and jobs:
            self._scheduler.start()
        log.info("cron scheduler reloaded with %d jobs", len(jobs))

    def _add(self, job: CronJob) -> None:
        try:
            trigger = CronTrigger.from_crontab(job.schedule)
        except ValueError as e:
            log.error("cron job %s has invalid schedule %r: %s", job.name, job.schedule, e)
            return
        self._scheduler.add_job(
            self._fire,
            trigger=trigger,
            args=[job],
            id=job.name,
            name=job.name,
            coalesce=True,
            misfire_grace_time=60 * 60,
            max_instances=1,
            replace_existing=True,
        )

    async def _fire(self, job: CronJob) -> None:
        try:
            await self._runner(job)
        except Exception:
            log.exception("cron job %s failed", job.name)
