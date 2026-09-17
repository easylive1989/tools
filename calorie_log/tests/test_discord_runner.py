from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from calorie_log.discord_runner import (
    DiscordClient, backfill_recent_text, combined_description, first_image,
    format_calorie_reply, is_advice_request, is_meal_message,
    record_meal_message, supplementary_messages, run_once, update_active_threads,
)
from calorie_log.estimator import Estimate, FoodItem


def test_advice_request_is_answered_without_creating_a_meal_record():
    message = {
        "id": "101", "content": "建議：我今晚想吃炸雞，可以嗎？",
        "timestamp": "2026-09-17T12:00:00Z", "attachments": [],
        "author": {"bot": False},
    }
    assert is_advice_request(message)
    assert not is_meal_message(message)
    discord = Mock()
    discord.messages_since.return_value = [message]
    discord.reply.return_value = "202"
    notion = Mock()
    state = {"last_message_id": "100", "text_only_backfill_v1": True}

    with patch.dict("calorie_log.discord_runner.os.environ", {
        "DISCORD_BOT_TOKEN": "token", "NOTION_SECRET": "token",
    }), patch("calorie_log.discord_runner.DiscordClient", return_value=discord), \
         patch("calorie_log.discord_runner.NotionApi", return_value=notion), \
         patch("calorie_log.discord_runner.load_state", return_value=state), \
         patch("calorie_log.discord_runner.save_state"), \
         patch("calorie_log.discord_runner.recent_meals") as history_mock, \
         patch("calorie_log.discord_runner.advise", return_value="可以搭配青菜與無糖飲料。") as advice_mock, \
         patch("calorie_log.discord_runner.write") as write_mock, \
         patch("calorie_log.discord_runner.update_active_threads"):
        run_once()

    history_mock.assert_called_once()
    assert advice_mock.call_args.args[1] == "我今晚想吃炸雞，可以嗎？"
    discord.reply.assert_called_once_with("1548580916765401088", "101", "可以搭配青菜與無糖飲料。")
    write_mock.assert_not_called()
    assert state["last_message_id"] == "101"
    assert state["advice_replies"] == {"101": "202"}


def test_discord_advice_reply_is_a_non_mentioning_idempotent_reply():
    client = DiscordClient("fake-token")
    client.request = Mock(return_value=Mock(json=lambda: {"id": "202"}))
    assert client.reply("channel", "101", "可以適量吃。") == "202"
    payload = client.request.call_args.kwargs["json"]
    assert payload["message_reference"]["message_id"] == "101"
    assert payload["allowed_mentions"] == {"parse": [], "replied_user": False}
    assert payload["nonce"] == "101" and payload["enforce_nonce"] is True


def test_planned_food_is_advice_but_completed_food_is_a_meal():
    planned = {"content": "我打算吃炸雞，怎麼搭配？", "author": {"bot": False}}
    recent_question = {"content": "我最近飲食怎麼樣", "author": {"bot": False}}
    completed = {"content": "本來想吃炸雞，最後吃了牛肉麵", "author": {"bot": False}}
    forced_record = {"content": "記錄：吃了雞腿便當，熱量多少？", "author": {"bot": False}}
    assert is_advice_request(planned) and not is_meal_message(planned)
    assert is_advice_request(recent_question) and not is_meal_message(recent_question)
    assert not is_advice_request(completed) and is_meal_message(completed)
    assert not is_advice_request(forced_record) and is_meal_message(forced_record)


def test_advice_in_a_meal_thread_does_not_reestimate_or_move_main_cursor():
    discord = Mock()
    discord.active_public_threads.return_value = [{"id": "123"}]
    discord.messages_since.return_value = [
        {"id": "124", "content": "我想吃蛋黃酥，可以嗎？", "author": {"bot": False}},
    ]
    discord.get_message.return_value = {"id": "123", "content": "午餐便當", "attachments": []}
    discord.reply.return_value = "125"
    state = {"last_message_id": "200", "threads": {"123": "0"}}
    with patch("calorie_log.discord_runner.recent_meals"), \
         patch("calorie_log.discord_runner.advise", return_value="可以考慮一個小份量。") as advice_mock, \
         patch("calorie_log.discord_runner.write") as write_mock, \
         patch("calorie_log.discord_runner.save_state"):
        update_active_threads(discord, Mock(), "channel", "source", state)
    assert "午餐便當" in advice_mock.call_args.args[1]
    discord.reply.assert_called_once_with("123", "124", "可以考慮一個小份量。")
    write_mock.assert_not_called()
    assert state["last_message_id"] == "200"
    assert state["advice_replies"] == {"124": "125"}


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


def test_send_message_posts_to_channel_or_thread():
    client = DiscordClient("fake-token")
    captured = {}

    def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return type("Response", (), {"json": lambda self: {"id": "999", "content": kwargs["json"]["content"]}})()

    client.request = fake_request
    resp = client.send_message("thread-123", "【排骨便當】預估總熱量：750 kcal")
    assert captured == {
        "method": "POST",
        "path": "/channels/thread-123/messages",
        "json": {"content": "【排骨便當】預估總熱量：750 kcal"},
    }
    assert resp["id"] == "999"


def test_get_or_create_thread_creates_thread_successfully():
    client = DiscordClient("fake-token")
    captured = {}

    def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return type("Response", (), {"json": lambda self: {"id": "123"}})()

    client.request = fake_request
    thread_id = client.get_or_create_thread("channel-1", "123", "排骨便當")
    assert captured == {
        "method": "POST",
        "path": "/channels/channel-1/messages/123/threads",
        "json": {"name": "排骨便當"},
    }
    assert thread_id == "123"


def test_get_or_create_thread_handles_already_exists_error():
    import requests

    client = DiscordClient("fake-token")

    def fake_request(method, path, **kwargs):
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"code": 160004, "message": "Thread already exists"}'
        raise requests.HTTPError(response=response)

    client.request = fake_request
    thread_id = client.get_or_create_thread("channel-1", "123", "排骨便當")
    assert thread_id == "123"


def test_get_or_create_thread_truncates_long_name_and_falls_back_if_blank():
    client = DiscordClient("fake-token")
    names_sent = []

    def fake_request(method, path, **kwargs):
        names_sent.append(kwargs["json"]["name"])
        return type("Response", (), {"json": lambda self: {"id": "123"}})()

    client.request = fake_request
    client.get_or_create_thread("channel-1", "123", "a" * 150)
    client.get_or_create_thread("channel-1", "123", "   ")
    assert names_sent == ["a" * 100, "熱量估算"]


def test_format_calorie_reply_integer_and_decimal():
    est1 = Estimate("排骨便當", (FoodItem("排骨便當", "一份", 750.0),), 750.0, "", "high")
    assert format_calorie_reply(est1) == "【排骨便當】預估總熱量：750 kcal"

    est2 = Estimate("小點心", (FoodItem("小點心", "一份", 234.5),), 234.5, "", "medium")
    assert format_calorie_reply(est2) == "【小點心】預估總熱量：234.5 kcal"

    est3 = Estimate("   ", (FoodItem("食物", "一份", 100.0),), 100.0, "", "low")
    assert format_calorie_reply(est3) == "【餐點】預估總熱量：100 kcal"


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
    discord.send_message.assert_called_once_with("123", "【三明治與拿鐵】預估總熱量：500 kcal")
    discord.react.assert_called_once_with("123", "124", "✅")


def test_text_only_thread_supplement_updates_same_meal():
    discord = Mock()
    discord.active_public_threads.return_value = [{"id": "123"}]
    discord.messages_since.return_value = [
        {"id": "124", "type": 0, "content": "其實吃了兩個", "author": {"bot": False}},
    ]
    discord.get_message.return_value = {
        "id": "123", "content": "蛋黃酥", "timestamp": "2026-09-13T07:16:00Z",
        "attachments": [],
    }
    state = {"threads": {"123": "0"}}
    estimate_result = Estimate(
        "蛋黃酥兩個", (FoodItem("蛋黃酥", "兩個", 600),), 600, "", "low"
    )
    with patch("calorie_log.discord_runner.estimate", return_value=estimate_result) as estimate_mock, \
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal") as write_mock, \
         patch("calorie_log.discord_runner.save_state"):
        update_active_threads(discord, Mock(), "channel", "source", state)

    assert estimate_mock.call_args.args[0] == []
    assert "其實吃了兩個" in estimate_mock.call_args.args[1]
    assert write_mock.call_args.kwargs["update_existing"] is True
    discord.send_message.assert_called_once_with("123", "【蛋黃酥兩個】預估總熱量：600 kcal")
    discord.react.assert_called_once_with("123", "124", "✅")


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
        {"id": "101", "content": "蛋黃酥", "timestamp": "2026-09-13T07:16:00Z",
         "attachments": [], "author": {"bot": False}},
        {"id": "102", "content": "一份午餐", "timestamp": "2026-09-13T04:00:00Z",
         "attachments": [{"filename": "meal.jpg", "content_type": "image/jpeg", "url": "photo"}],
         "author": {"bot": False}},
    ]
    state = {"last_message_id": "100", "text_only_backfill_v1": True}
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
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal") as write_mock, \
         patch("calorie_log.discord_runner.update_active_threads"):
        run_once()

    assert state["last_message_id"] == "102"
    assert state["threads"] == {"101": "0", "102": "0"}
    assert write_mock.call_count == 2
    assert write_mock.call_args_list[0].kwargs["include_photos"] is False
    assert discord.get_or_create_thread.call_count == 2
    assert discord.send_message.call_count == 2
    assert discord.react.call_count == 2


def test_one_time_backfill_records_recent_skipped_text_without_moving_cursor():
    discord = Mock()
    discord.get_or_create_thread.return_value = "101"
    discord.request.return_value.json.return_value = [
        {"id": "102", "content": "之後的新訊息", "timestamp": "2026-09-13T07:17:00Z",
         "attachments": [], "author": {"bot": False}},
        {"id": "101", "content": "蛋黃酥", "timestamp": "2026-09-13T07:16:00Z",
         "attachments": [], "author": {"bot": False}},
    ]
    state = {"last_message_id": "101"}
    estimate_result = Estimate(
        "蛋黃酥", (FoodItem("蛋黃酥", "一個", 300),), 300, "一般大小", "low"
    )
    with patch("calorie_log.discord_runner.datetime") as clock_mock, \
         patch("calorie_log.discord_runner.estimate", return_value=estimate_result), \
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal") as write_mock, \
         patch("calorie_log.discord_runner.save_state"):
        clock_mock.now.return_value = datetime(2026, 9, 13, 8, tzinfo=timezone.utc)
        assert backfill_recent_text(discord, Mock(), "channel", "source", state, "101") is True

    assert state["last_message_id"] == "101"
    assert state["text_only_backfill_v1"] is True
    assert state["threads"]["101"] == "0"
    assert write_mock.call_count == 1
    discord.get_or_create_thread.assert_called_once_with("channel", "101", "蛋黃酥")
    discord.send_message.assert_called_once_with("101", "【蛋黃酥】預估總熱量：300 kcal")
    discord.react.assert_called_once_with("channel", "101", "✅")


def test_reaction_failure_keeps_text_meal_pending_for_retry():
    discord = Mock()
    discord.react.side_effect = RuntimeError("missing reaction permission")
    state = {"last_message_id": "100"}
    message = {
        "id": "101", "content": "蛋黃酥", "timestamp": "2026-09-13T07:16:00Z",
        "attachments": [], "author": {"bot": False},
    }
    estimate_result = Estimate(
        "蛋黃酥", (FoodItem("蛋黃酥", "一個", 300),), 300, "一般大小", "low"
    )
    with patch("calorie_log.discord_runner.estimate", return_value=estimate_result), \
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal") as write_mock, \
         patch("calorie_log.discord_runner.save_state") as save_mock:
        ok = record_meal_message(
            discord, Mock(), "channel", "source", state, message,
            advance_cursor=True,
        )

    assert ok is False
    assert state["last_message_id"] == "100"
    write_mock.assert_called_once()
    save_mock.assert_not_called()


def test_thread_reply_failure_keeps_meal_pending_for_retry():
    discord = Mock()
    discord.send_message.side_effect = RuntimeError("failed to send message in thread")
    state = {"last_message_id": "100"}
    message = {
        "id": "101", "content": "蛋黃酥", "timestamp": "2026-09-13T07:16:00Z",
        "attachments": [], "author": {"bot": False},
    }
    estimate_result = Estimate(
        "蛋黃酥", (FoodItem("蛋黃酥", "一個", 300),), 300, "一般大小", "low"
    )
    with patch("calorie_log.discord_runner.estimate", return_value=estimate_result), \
         patch("calorie_log.discord_runner.write", return_value="https://www.notion.so/meal") as write_mock, \
         patch("calorie_log.discord_runner.save_state") as save_mock:
        ok = record_meal_message(
            discord, Mock(), "channel", "source", state, message,
            advance_cursor=True,
        )

    assert ok is False
    assert state["last_message_id"] == "100"
    write_mock.assert_called_once()
    discord.react.assert_not_called()
    save_mock.assert_not_called()
