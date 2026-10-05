import json
from pathlib import Path
from unittest.mock import patch

import pytest

from stock_pick.reader import clean_names, read_names

ENV = {"DISCORD_BOT_TOKEN": "discord-secret", "NOTION_SECRET": "notion-secret",
       "CODEX_CLI_PATH": "/usr/local/bin/codex"}


def fake_codex(output, captured, returncode=0):
    def run(command, **kwargs):
        captured["command"] = command
        captured["prompt"] = kwargs["input"]
        captured["env"] = kwargs["env"]
        Path(command[command.index("--output-last-message") + 1]).write_text(output, encoding="utf-8")
        return type("Result", (), {"returncode": returncode})()
    return run


def images_in(tmp_path, *names):
    paths = [tmp_path / name for name in names]
    for path in paths:
        path.write_bytes(b"image")
    return paths


def test_clean_names_drops_indexes_blanks_and_duplicates():
    names = ["加權指", "鈊象", "火星生技 *", "", "櫃買指數", "鈊象", "群益證"]
    assert clean_names(names) == ["鈊象", "火星生技*", "群益證"]


def test_read_names_sends_every_image_to_codex(tmp_path):
    images = images_in(tmp_path, "a.png", "b.jpg")
    captured = {}
    output = json.dumps({"names": ["加權指", "鈊象", "火星生技*", "鈊象"]})
    with patch.dict("stock_pick.reader.os.environ", ENV), \
         patch("stock_pick.reader.subprocess.run", side_effect=fake_codex(output, captured)):
        assert read_names(images) == ["鈊象", "火星生技*"]

    command = captured["command"]
    sent = [command[i + 1] for i, part in enumerate(command) if part == "--image"]
    assert sent == [str(image.resolve()) for image in images]
    assert command[command.index("--model") + 1] == "gpt-5.6-terra"
    assert command[command.index("--config") + 1] == "model_reasoning_effort=medium"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "保留名稱後面的「*」" in captured["prompt"]
    assert "不要換成字形相近的常用字" in captured["prompt"]
    assert "DISCORD_BOT_TOKEN" not in captured["env"]
    assert "NOTION_SECRET" not in captured["env"]


def test_read_names_rejects_malformed_codex_output(tmp_path):
    with patch.dict("stock_pick.reader.os.environ", ENV), \
         patch("stock_pick.reader.subprocess.run", side_effect=fake_codex("not json", {})):
        with pytest.raises(RuntimeError, match="格式不正確"):
            read_names(images_in(tmp_path, "a.png"))


def test_read_names_reports_codex_failure(tmp_path):
    with patch.dict("stock_pick.reader.os.environ", ENV), \
         patch("stock_pick.reader.subprocess.run", side_effect=fake_codex("", {}, returncode=1)):
        with pytest.raises(RuntimeError, match="讀取截圖失敗"):
            read_names(images_in(tmp_path, "a.png"))


def test_read_names_rejects_unsupported_images(tmp_path):
    with pytest.raises(ValueError, match="不支援的圖片格式"):
        read_names(images_in(tmp_path, "a.heic"))
