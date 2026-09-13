import json
from pathlib import Path
from unittest.mock import patch

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
    assert "--sandbox" in captured["command"]
    assert "DISCORD_BOT_TOKEN" not in captured["env"]
    assert "NOTION_SECRET" not in captured["env"]
