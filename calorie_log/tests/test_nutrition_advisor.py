import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from calorie_log.meal_time import TAIPEI
from calorie_log.nutrition_advisor import MealHistory, MealRecord, advise, recent_meals


def test_recent_meals_uses_a_bounded_window_and_paginates():
    notion = Mock()
    notion.query_data_source.side_effect = [
        Mock(json=lambda: {
            "results": [{"properties": {
                "時間": {"date": {"start": "2026-09-16T12:00:00+08:00"}},
                "餐點": {"title": [{"plain_text": "便當"}]},
                "卡路里": {"number": 650},
                "備註": {"rich_text": [{"plain_text": "Discord 訊息：[1]\n\n原始說明：雞腿便當\n\n估算假設：一般份量"}]},
            }}],
            "has_more": True, "next_cursor": "page-2",
        }),
        Mock(json=lambda: {
            "results": [{"properties": {
                "時間": {"date": {"start": "2026-09-15T12:00:00+08:00"}},
                "餐點": {"title": [{"plain_text": "湯麵"}]},
                "卡路里": {"number": 400},
                "備註": {"rich_text": []},
            }}],
            "has_more": False, "next_cursor": None,
        }),
    ]
    history = recent_meals(
        notion, "source", days=7,
        now=datetime(2026, 9, 17, 12, tzinfo=TAIPEI),
    )
    assert [meal.name for meal in history.records] == ["便當", "湯麵"]
    assert history.records[0].description == "雞腿便當"
    assert notion.query_data_source.call_args_list[0].args[1]["filter"]["property"] == "時間"
    assert notion.query_data_source.call_args_list[1].args[1]["start_cursor"] == "page-2"


def test_advice_passes_history_and_question_without_secrets(tmp_path):
    codex = tmp_path / "codex"
    codex.write_text("fake")
    captured = {}

    def fake_run(command, **kwargs):
        captured["prompt"] = kwargs["input"]
        captured["env"] = kwargs["env"]
        captured["command"] = command
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"reply": "最近兩餐蔬菜較少；這餐可以加一份青菜。"}), encoding="utf-8")
        return Mock(returncode=0)

    history = MealHistory((MealRecord("2026-09-16T12:00:00+08:00", "雞腿便當", 650, "炸雞腿"),))
    with patch.dict("calorie_log.nutrition_advisor.os.environ", {
        "DISCORD_BOT_TOKEN": "discord-secret", "NOTION_SECRET": "notion-secret",
    }), patch("calorie_log.nutrition_advisor.shutil.which", return_value=str(codex)), \
         patch("calorie_log.nutrition_advisor.subprocess.run", side_effect=fake_run):
        reply = advise([], "我想吃蛋黃酥", history)

    assert "雞腿便當" in captured["prompt"]
    assert "我想吃蛋黃酥" in captured["prompt"]
    assert "211" in captured["prompt"]
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "read-only"
    assert "DISCORD_BOT_TOKEN" not in captured["env"]
    assert "NOTION_SECRET" not in captured["env"]
    assert "加一份青菜" in reply
