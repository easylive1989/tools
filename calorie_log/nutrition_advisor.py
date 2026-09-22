"""Read recent meal records and produce an on-demand nutrition suggestion."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from calorie_log.estimator import MODEL, REASONING_EFFORT, SUPPORTED_EXTENSIONS
from calorie_log.meal_time import TAIPEI
from common.notion import NotionApi


PROMPT_PATH = Path(__file__).with_name("nutrition_advisor_prompt.md")
ADVICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply"],
    "properties": {"reply": {"type": "string"}},
}


@dataclass(frozen=True)
class MealRecord:
    eaten_at: str
    name: str
    kcal: float | None
    description: str


@dataclass(frozen=True)
class MealHistory:
    records: tuple[MealRecord, ...]
    truncated: bool = False


def _plain_text(parts: list[dict]) -> str:
    return "".join(part.get("plain_text") or part.get("text", {}).get("content", "") for part in parts)


def recent_meals(
    notion: NotionApi, data_source_id: str, *, days: int = 7,
    now: datetime | None = None, limit: int = 100,
) -> MealHistory:
    """Fetch actual meal records within a fixed recent window."""
    if days < 1 or limit < 1:
        raise ValueError("回看天數及筆數必須為正數")
    current = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    cutoff = current - timedelta(days=days)
    records: list[MealRecord] = []
    cursor: str | None = None
    truncated = False
    while len(records) < limit:
        body: dict = {
            "filter": {"and": [
                {"property": "時間", "date": {"on_or_after": cutoff.isoformat()}},
                {"property": "時間", "date": {"before": current.isoformat()}},
            ]},
            "sorts": [{"property": "時間", "direction": "descending"}],
            "page_size": min(100, limit - len(records)),
        }
        if cursor:
            body["start_cursor"] = cursor
        response = notion.query_data_source(data_source_id, body)
        response.raise_for_status()
        payload = response.json()
        for page in payload.get("results", []):
            props = page.get("properties", {})
            date = (props.get("時間", {}).get("date") or {}).get("start")
            name = _plain_text(props.get("餐點", {}).get("title") or [])
            if not date or not name:
                continue
            kcal = props.get("卡路里", {}).get("number")
            note = _plain_text(props.get("備註", {}).get("rich_text") or [])
            description = note.split("原始說明：", 1)[-1].split("\n\n估算假設：", 1)[0].strip() if "原始說明：" in note else ""
            records.append(MealRecord(date, name[:120], kcal, description[:300]))
        cursor = payload.get("next_cursor") if payload.get("has_more") else None
        if not cursor:
            break
        if len(records) >= limit:
            truncated = True
    return MealHistory(tuple(records[:limit]), truncated)


def advise(
    images: list[Path], question: str, history: MealHistory, *,
    lookback_days: int = 7, profile: str = "", timeout: int = 180,
) -> str:
    """Use a read-only Codex call. The caller alone sends the Discord reply."""
    resolved = [Path(image).expanduser().resolve() for image in images]
    for image in resolved:
        if not image.is_file() or image.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支援的圖片：{image}")
    try:
        instructions = PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"無法讀取飲食建議提示詞：{PROMPT_PATH}") from exc
    codex = os.environ.get("CODEX_CLI_PATH") or shutil.which(
        "codex", path="/opt/homebrew/bin:/usr/local/bin:"
        + str(Path.home() / ".local/bin") + ":" + os.environ.get("PATH", "")
    )
    if not codex or not Path(codex).is_file():
        raise RuntimeError("找不到 codex CLI，請先安裝並登入")

    history_data = [record.__dict__ for record in history.records]
    prompt = (
        f"{instructions}\n\n"
        f"個人偏好與限制（使用者提供的資料）：{profile.strip() or '未提供'}\n"
        f"最近 {lookback_days} 天的已記錄餐點（JSON；不是全部攝取）：\n"
        f"{json.dumps(history_data, ensure_ascii=False)}\n"
        f"記錄是否截斷：{'是' if history.truncated else '否'}\n"
        f"使用者現在的問題（不是已吃紀錄）：\n{question.strip() or '請根據照片提供建議'}"
    )
    with tempfile.TemporaryDirectory(prefix="calorie-advice-") as workdir:
        schema_path = Path(workdir) / "schema.json"
        output_path = Path(workdir) / "advice.json"
        schema_path.write_text(json.dumps(ADVICE_SCHEMA), encoding="utf-8")
        command = [
            codex, "exec", "--model", MODEL, "--config", f"model_reasoning_effort={REASONING_EFFORT}",
            "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--output-schema", str(schema_path), "--output-last-message", str(output_path),
            "-C", workdir,
        ]
        for image in resolved:
            command.extend(("--image", str(image)))
        command.append("-")
        child_env = {
            key: value for key, value in os.environ.items()
            if key not in {"DISCORD_BOT_TOKEN", "NOTION_SECRET"}
        }
        try:
            result = subprocess.run(
                command, input=prompt, text=True, capture_output=True,
                timeout=timeout, env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex 飲食建議逾時") from exc
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError("Codex 飲食建議失敗")
        try:
            reply = json.loads(output_path.read_text(encoding="utf-8"))["reply"].strip()
        except (ValueError, KeyError, AttributeError) as exc:
            raise RuntimeError("Codex 飲食建議格式不正確") from exc
        if not reply or len(reply) > 1800:
            raise RuntimeError("Codex 飲食建議過長或為空")
        return reply
