import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_HOME = Path.home() / ".pclaw"


@dataclass(frozen=True)
class Config:
    discord_token: str
    channel_id: int
    cli_kind: str
    cli_model: str | None
    max_concurrency: int
    state_home: Path

    @property
    def db_path(self) -> Path:
        return self.state_home / "claw.db"

    @property
    def workdir(self) -> Path:
        return self.state_home / "workdir"

    @property
    def skills_dir(self) -> Path:
        return self.state_home / "skills"

    @property
    def cron_path(self) -> Path:
        return self.state_home / "cron.toml"


def load_config(path: Path | None = None) -> Config:
    state_home = Path(os.environ.get("CLAW_HOME", DEFAULT_HOME))
    path = path or (state_home / "config.toml")

    raw: dict = {}
    if path.exists():
        with path.open("rb") as f:
            raw = tomllib.load(f)

    discord_cfg = raw.get("discord", {})
    cli_cfg = raw.get("cli", {})

    token = os.environ.get("CLAW_DISCORD_TOKEN") or discord_cfg.get("token")
    if not token:
        raise RuntimeError(
            "Missing Discord token. Set CLAW_DISCORD_TOKEN env or [discord].token in config."
        )

    channel_id_raw = os.environ.get("CLAW_CHANNEL_ID") or discord_cfg.get("channel_id")
    if not channel_id_raw:
        raise RuntimeError(
            "Missing channel id. Set CLAW_CHANNEL_ID env or [discord].channel_id in config."
        )

    return Config(
        discord_token=token,
        channel_id=int(channel_id_raw),
        cli_kind=os.environ.get("CLAW_CLI_KIND") or cli_cfg.get("kind", "gemini"),
        cli_model=os.environ.get("CLAW_CLI_MODEL") or cli_cfg.get("model"),
        max_concurrency=int(
            os.environ.get("CLAW_MAX_CONCURRENCY")
            or cli_cfg.get("max_concurrency", 3)
        ),
        state_home=state_home,
    )
