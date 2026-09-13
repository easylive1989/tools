from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from calorie_log.discord_runner import (
    DiscordClient, combined_description, first_image, supplementary_messages,
    run_once, update_active_threads,
)
from calorie_log.estimator import Estimate, FoodItem


def test_first_image_ignores_non_images_and_uses_one_photo():
    message = {"attachments": [
        {"filename": "notes.pdf", "content_type": "application/pdf"},
        {"filename": "lunch.heic", "content_type": "image/heic", "url": "first"},
        {"filename": "lunch2.jpg", "content_type": "image/jpeg", "url": "second"},
    ]}
    assert first_image(message)["url"] == "first"


def test_messages_since_walks_backward_without_skipping_a_busy_channel():
    client = DiscordClient("fake-token")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(kwargs["params"])
        before = kwargs["params"].get("before")
        ids = range(101, 201) if before is None else range(51, 101)
        return type("Response", (), {"json": lambda self: [
            {"id": str(number)} for number in reversed(ids)
        ]})()

    client.request = fake_request
    result = client.messages_since("channel", "75")
    assert [int(item["id"]) for item in result] == list(range(76, 201))
    assert calls == [{"limit": 100}, {"limit": 100, "before": "101"}]


def test_thread_supplements_update_the_original_meal(tmp_path):
    discord = Mock()
    discord.active_public_threads.return_value = [{"id": "123"}]
    discord.messages_since.return_value = [
        {"id": "123", "type": 21, "content": ""},
        {"id": "124", "type": 0, "content": "還有一杯拿鐵", "author": {"bot": False}},
    ]
    discord.get_message.return_value = {
        "id": "123", "content": "一個三明治", "timestamp": "2026-09-13T04:00:00Z",
        "attachments": [{"filename": "meal.jpg", "content_type": "image/jpeg", "url": "photo"}],
    }
    notion = Mock()
    state = {"threads": {"123": "0"}}
    estimate_result = Estimate(
        "三明治與拿鐵", (FoodItem("餐點", "一份", 500),), 500, "", "medium"
    )

    def fake_download(attachment, directory):
        photo = Path(directory) / "meal.jpg"
        photo.write_bytes(b"photo")
        return photo

    with patch("calorie_log.discord_runner.download_image", side_effect=fake_download), \
         patch("calorie_log.discord_runner.estimate", return_value=estimate_result) as estimate_mock, \
         patch("calorie_log.discord_runner.choose_meal_time", return_value=datetime(2026, 9, 13, 12, tzinfo=timezone.utc)), \
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal") as write_mock, \
         patch("calorie_log.discord_runner.save_state"):
        update_active_threads(discord, notion, "channel", "source", state)

    assert "還有一杯拿鐵" in estimate_mock.call_args.args[1]
    assert write_mock.call_args.kwargs["update_existing"] is True
    assert write_mock.call_args.kwargs["source_message_id"] == "123"
    assert state["threads"]["123"] == "124"
    discord.reply.assert_not_called()


def test_supplements_ignore_bot_and_starter_messages():
    messages = [
        {"id": "1", "type": 21, "content": "", "author": {"bot": False}},
        {"id": "2", "type": 0, "content": "補充", "author": {"bot": False}},
        {"id": "3", "type": 0, "content": "已更新", "author": {"bot": True}},
    ]
    assert [message["id"] for message in supplementary_messages(messages)] == ["2"]
    assert "補充：補充" in combined_description({"content": "原本"}, messages[1:2])


def test_recorded_meal_is_tracked_for_future_thread_updates():
    discord = Mock()
    discord.messages_since.return_value = [
        {"id": "101", "content": "文字訊息", "attachments": [], "author": {"bot": False}},
        {"id": "102", "content": "一份午餐", "timestamp": "2026-09-13T04:00:00Z",
         "attachments": [{"filename": "meal.jpg", "content_type": "image/jpeg", "url": "photo"}],
         "author": {"bot": False}},
    ]
    state = {"last_message_id": "100"}
    estimate_result = Estimate(
        "午餐", (FoodItem("午餐", "一份", 500),), 500, "", "medium"
    )

    def fake_download(attachment, directory):
        photo = Path(directory) / "meal.jpg"
        photo.write_bytes(b"photo")
        return photo

    with patch.dict("calorie_log.discord_runner.os.environ", {
            "DISCORD_BOT_TOKEN": "token", "NOTION_SECRET": "token"
         }), \
         patch("calorie_log.discord_runner.DiscordClient", return_value=discord), \
         patch("calorie_log.discord_runner.NotionApi"), \
         patch("calorie_log.discord_runner.load_state", return_value=state), \
         patch("calorie_log.discord_runner.save_state"), \
         patch("calorie_log.discord_runner.download_image", side_effect=fake_download), \
         patch("calorie_log.discord_runner.estimate", return_value=estimate_result), \
         patch("calorie_log.discord_runner.choose_meal_time", return_value=datetime(2026, 9, 13, 12, tzinfo=timezone.utc)), \
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal"), \
         patch("calorie_log.discord_runner.update_active_threads"):
        run_once()

    assert state["last_message_id"] == "102"
    assert state["threads"] == {"102": "0"}
    discord.reply.assert_not_called()
