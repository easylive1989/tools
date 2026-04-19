import os
from pathlib import Path

import pytest

from claw.config import load_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("CLAW_"):
            monkeypatch.delenv(k, raising=False)


def test_load_from_toml(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[discord]
token = "tok"
channel_id = "12345"

[cli]
kind = "gemini"
model = "gemini-2.5-pro"
max_concurrency = 5
"""
    )
    monkeypatch.setenv("CLAW_HOME", str(tmp_path))

    cfg = load_config(cfg_path)
    assert cfg.discord_token == "tok"
    assert cfg.channel_id == 12345
    assert cfg.cli_kind == "gemini"
    assert cfg.cli_model == "gemini-2.5-pro"
    assert cfg.max_concurrency == 5
    assert cfg.db_path == tmp_path / "claw.db"
    assert cfg.workdir == tmp_path / "workdir"


def test_env_overrides_toml(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[discord]
token = "from-toml"
channel_id = "111"

[cli]
kind = "gemini"
"""
    )
    monkeypatch.setenv("CLAW_HOME", str(tmp_path))
    monkeypatch.setenv("CLAW_DISCORD_TOKEN", "from-env")
    monkeypatch.setenv("CLAW_CHANNEL_ID", "222")

    cfg = load_config(cfg_path)
    assert cfg.discord_token == "from-env"
    assert cfg.channel_id == 222


def test_env_only_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAW_HOME", str(tmp_path))
    monkeypatch.setenv("CLAW_DISCORD_TOKEN", "tok")
    monkeypatch.setenv("CLAW_CHANNEL_ID", "999")

    cfg = load_config()
    assert cfg.discord_token == "tok"
    assert cfg.channel_id == 999
    assert cfg.cli_kind == "gemini"


def test_missing_token_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAW_HOME", str(tmp_path))
    monkeypatch.setenv("CLAW_CHANNEL_ID", "1")
    with pytest.raises(RuntimeError, match="Discord token"):
        load_config()
