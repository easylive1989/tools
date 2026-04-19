from pathlib import Path

import pytest

from claw.cron import CronJob, load_jobs


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
