from pathlib import Path

import pytest

from claw.cron import CronJob, load_jobs, save_jobs, upsert_job


def test_load_jobs_parses_toml(tmp_path: Path) -> None:
    path = tmp_path / "cron.toml"
    path.write_text(
        """
[[jobs]]
name = "morning"
schedule = "0 8 * * 1-5"
skill = "summary"
prompt = "整理昨天的熱門新聞"

[[jobs]]
name = "retro"
schedule = "0 22 * * 0"
prompt = "這週值得感謝的三件事"
""",
        encoding="utf-8",
    )

    jobs = load_jobs(path)
    assert len(jobs) == 2
    assert jobs[0] == CronJob(
        name="morning",
        schedule="0 8 * * 1-5",
        prompt="整理昨天的熱門新聞",
        skill="summary",
    )
    assert jobs[1].skill is None


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_jobs(tmp_path / "absent.toml") == []


def test_save_jobs_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "cron.toml"
    jobs = [
        CronJob(name="a", schedule="0 8 * * *", prompt="hello", skill=None),
        CronJob(name="b", schedule="*/15 * * * *", prompt='line1\nline2 with "quote"', skill="summary"),
    ]
    save_jobs(path, jobs)
    reloaded = load_jobs(path)
    assert reloaded == jobs


def test_upsert_replaces_by_name(tmp_path: Path) -> None:
    path = tmp_path / "cron.toml"
    save_jobs(path, [CronJob(name="a", schedule="0 8 * * *", prompt="old")])
    upsert_job(path, CronJob(name="a", schedule="0 9 * * *", prompt="new"))
    jobs = load_jobs(path)
    assert len(jobs) == 1
    assert jobs[0].schedule == "0 9 * * *"
    assert jobs[0].prompt == "new"


def test_upsert_appends_new(tmp_path: Path) -> None:
    path = tmp_path / "cron.toml"
    save_jobs(path, [CronJob(name="a", schedule="0 8 * * *", prompt="one")])
    upsert_job(path, CronJob(name="b", schedule="0 9 * * *", prompt="two"))
    names = [j.name for j in load_jobs(path)]
    assert names == ["a", "b"]


def test_save_jobs_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "cron.toml"
    save_jobs(path, [])
    assert path.read_text() == ""
    assert load_jobs(path) == []
