"""Read stock names from stock-app watchlist screenshots with the local Codex CLI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MODEL = "gpt-5.6-terra"
# Low effort misread rare characters (佶→佑, 鈊→鈺) in about a third of runs.
REASONING_EFFORT = "medium"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# The index row is often cropped at the top of the screenshot (「加權指」).
INDEX_NAME = re.compile(r"指數?$")
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["names"],
    "properties": {"names": {"type": "array", "items": {"type": "string"}}},
}
INSTRUCTIONS = """這些圖片是台股看盤 App「自選」頁的截圖，每一列是一檔股票。
依截圖順序、由上到下，把每一列的股票名稱放進 names。
- 名稱照圖上的字原樣抄寫，保留名稱後面的「*」。名稱被折成兩行時（例如「火星生技」下一行是「*」），合併成「火星生技*」。
- 股票名稱常用罕見字，逐字依筆畫仔細辨認，不要換成字形相近的常用字。
- 不要列出指數（例如加權指數、櫃買指數），也不要列出欄位標題、分頁或按鈕文字。
- 只要名稱，不要代號或價格。
- 截圖之間有重複的股票也照樣列出。"""


def clean_names(names: list[object]) -> list[str]:
    """Drop blanks, index rows and duplicates while keeping the screenshot order."""
    cleaned: list[str] = []
    for raw in names:
        name = "".join(str(raw).split())
        if name and not INDEX_NAME.search(name) and name not in cleaned:
            cleaned.append(name)
    return cleaned


def read_names(images: list[Path], *, timeout: int = 180) -> list[str]:
    if not images:
        raise ValueError("沒有可讀取的截圖")
    resolved = [Path(image).expanduser().resolve() for image in images]
    for image in resolved:
        if image.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支援的圖片格式：{image.suffix}")
        if not image.is_file():
            raise ValueError(f"找不到圖片：{image}")

    codex = os.environ.get("CODEX_CLI_PATH") or shutil.which(
        "codex", path="/opt/homebrew/bin:/usr/local/bin:"
        + str(Path.home() / ".local/bin") + ":" + os.environ.get("PATH", "")
    )
    if not codex:
        raise RuntimeError("找不到 codex CLI，請先安裝並登入")

    with tempfile.TemporaryDirectory(prefix="stock-pick-") as workdir:
        schema_path = Path(workdir) / "schema.json"
        output_path = Path(workdir) / "names.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
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
                command, input=INSTRUCTIONS, text=True, capture_output=True,
                timeout=timeout, env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex 讀取截圖逾時") from exc
        if result.returncode != 0:
            raise RuntimeError(f"Codex 讀取截圖失敗（exit {result.returncode}）")
        try:
            names = json.loads(output_path.read_text(encoding="utf-8"))["names"]
            if not isinstance(names, list):
                raise TypeError("names is not a list")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Codex 回傳的股票名稱格式不正確") from exc
    return clean_names(names)
