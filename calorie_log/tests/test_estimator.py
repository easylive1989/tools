import json
from pathlib import Path
from unittest.mock import patch

import pytest

from calorie_log.estimator import estimate


def test_estimate_sends_images_and_description_to_codex(tmp_path):
    image = tmp_path / "meal.jpg"
    image.write_bytes(b"test image")
    codex = tmp_path / "codex"
    codex.write_text("fake")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["prompt"] = kwargs["input"]
        captured["env"] = kwargs["env"]
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({
            "meal_name": "雞肉飯",
            "items": [{"name": "雞肉飯", "portion": "一碗", "kcal": 480}],
            "total_kcal": 480,
            "assumptions": "醬汁份量未明",
            "confidence": "medium",
        }), encoding="utf-8")
        return type("Result", (), {"returncode": 0})()

    with patch.dict("calorie_log.estimator.os.environ", {
            "DISCORD_BOT_TOKEN": "discord-secret", "NOTION_SECRET": "notion-secret"
         }), \
         patch("calorie_log.estimator.shutil.which", return_value=str(codex)), \
         patch("calorie_log.estimator.subprocess.run", side_effect=fake_run):
        result = estimate([image], "吃了一碗雞肉飯")

    assert result.total_kcal == 480
    assert result.items[0].portion == "一碗"
    assert captured["command"][captured["command"].index("--image") + 1] == str(image)
    assert "吃了一碗雞肉飯" in captured["prompt"]
    assert "食物熱量對照表" in captured["prompt"]
    assert "Q0500401" in captured["prompt"]
    assert "每 100 克" in captured["prompt"]
    assert "永遠以使用者實際吃下的量計算" in captured["prompt"]
    assert "使用者的文字修正永遠優先於圖片辨識" in captured["prompt"]
    assert "±15～25%" in captured["prompt"]
    assert "不得重複計算同一份食物、醬汁或油脂" in captured["prompt"]
    assert "total_kcal 必須永遠提供" in captured["prompt"]
    assert "--sandbox" in captured["command"]
    assert captured["command"][captured["command"].index("--model") + 1] == "gpt-5.6-terra"
    assert captured["command"][captured["command"].index("--config") + 1] == "model_reasoning_effort=medium"
    assert "DISCORD_BOT_TOKEN" not in captured["env"]
    assert "NOTION_SECRET" not in captured["env"]


def test_text_only_meal_uses_codex_without_image(tmp_path):
    codex = tmp_path / "codex"
    codex.write_text("fake")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["prompt"] = kwargs["input"]
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({
            "meal_name": "蛋黃酥",
            "items": [{"name": "蛋黃酥", "portion": "一個", "kcal": 300}],
            "total_kcal": 300,
            "assumptions": "以一般大小的一個估算",
            "confidence": "low",
        }), encoding="utf-8")
        return type("Result", (), {"returncode": 0})()

    with patch("calorie_log.estimator.shutil.which", return_value=str(codex)), \
         patch("calorie_log.estimator.subprocess.run", side_effect=fake_run):
        result = estimate([], "蛋黃酥")

    assert result.total_kcal == 300
    assert "--image" not in captured["command"]
    assert captured["command"][captured["command"].index("--model") + 1] == "gpt-5.6-terra"
    assert captured["command"][captured["command"].index("--config") + 1] == "model_reasoning_effort=medium"
    assert "蛋黃酥" in captured["prompt"]
    assert "一般單份" in captured["prompt"]
    assert "284.3 kcal" in captured["prompt"]


def test_official_decimal_calories_are_preserved(tmp_path):
    codex = tmp_path / "codex"
    codex.write_text("fake")

    def fake_run(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({
            "meal_name": "包裝食品",
            "items": [{"name": "包裝食品", "portion": "一份", "kcal": 234.5}],
            "total_kcal": 234.5,
            "assumptions": "採用包裝官方營養標示",
            "confidence": "high",
        }), encoding="utf-8")
        return type("Result", (), {"returncode": 0})()

    with patch("calorie_log.estimator.shutil.which", return_value=str(codex)), \
         patch("calorie_log.estimator.subprocess.run", side_effect=fake_run):
        result = estimate([], "包裝標示每份 234.5 kcal，我吃一份")

    assert result.items[0].kcal == 234.5
    assert result.total_kcal == 234.5


def test_estimate_requires_reference_file(tmp_path):
    codex = tmp_path / "codex"
    codex.write_text("fake")
    with patch("calorie_log.estimator.shutil.which", return_value=str(codex)), \
         patch("calorie_log.estimator.REFERENCE_PATH", tmp_path / "missing.md"), \
         patch("calorie_log.estimator.subprocess.run") as run:
        with pytest.raises(RuntimeError, match="無法讀取食物熱量參考表"):
            estimate([], "蛋黃酥")
    run.assert_not_called()
