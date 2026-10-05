from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from stock_pick import runner
from stock_pick.quotes import MarketQuotes, Quote

DAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 5, 15, 30, tzinfo=timezone.utc)  # 台灣 23:30
QUOTES = MarketQuotes({"上市": DAY, "上櫃": DAY, "興櫃": DAY}, {
    "鈊象": Quote("3293", "鈊象", "上櫃", 794.0),
    "火星生技*": Quote("7731", "火星生技*", "興櫃", 4.51),
})
NOT_PUBLISHED = MarketQuotes({"上市": None, "上櫃": date(2026, 10, 2), "興櫃": date(2026, 10, 2)}, {})


def screenshot(message_id="200", timestamp="2026-10-05T14:57:00.000000+00:00"):
    return {
        "id": message_id, "type": 0, "timestamp": timestamp, "author": {"bot": False},
        "content": "",
        "attachments": [{"url": "https://cdn.discordapp.com/x.jpeg",
                         "filename": "IMG_8812.jpeg", "content_type": "image/jpeg"}],
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setenv("NOTION_SECRET", "secret")
    monkeypatch.setattr(runner, "STATE_PATH", tmp_path / "state.json")
    discord = Mock()
    discord.download.side_effect = lambda url, path: path
    monkeypatch.setattr(runner, "DiscordClient", Mock(return_value=discord))
    monkeypatch.setattr(runner, "NotionApi", Mock())
    fakes = SimpleNamespace(
        discord=discord,
        write=Mock(return_value=True),
        fetch=Mock(return_value=QUOTES),
        read=Mock(return_value=["鈊象", "火星生技*"]),
    )
    monkeypatch.setattr(runner, "write", fakes.write)
    monkeypatch.setattr(runner, "fetch_quotes", fakes.fetch)
    monkeypatch.setattr(runner, "read_names", fakes.read)
    monkeypatch.setattr(runner, "is_trading_day", Mock(return_value=True))
    runner.save_state({"last_message_id": "100", "attempts": {}})
    return fakes


def test_first_run_starts_after_the_latest_message(env):
    runner.save_state({})
    env.discord.latest_message_id.return_value = "555"
    runner.run_once(NOW)
    assert runner.load_state()["last_message_id"] == "555"
    env.discord.messages_since.assert_not_called()


def test_logs_every_stock_and_reacts_ok(env):
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.fetch.assert_called_once_with(DAY)
    assert [call.args[1].code for call in env.write.call_args_list] == ["3293", "7731"]
    assert all(call.args[2] == DAY for call in env.write.call_args_list)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "✅")
    env.discord.reply.assert_not_called()
    assert runner.load_state() == {"last_message_id": "200", "attempts": {}}


def test_post_from_the_close_on_uses_that_taipei_day(monkeypatch):
    previous = Mock()
    monkeypatch.setattr(runner, "previous_trading_day", previous)
    monkeypatch.setattr(runner, "is_trading_day", Mock(return_value=True))
    assert runner.pick_day(screenshot(timestamp="2026-10-05T05:30:00Z")) == DAY  # 13:30
    assert runner.pick_day(screenshot(timestamp="2026-10-05T15:59:00Z")) == DAY  # 23:59
    previous.assert_not_called()


def test_post_on_a_market_holiday_uses_the_latest_trading_day(monkeypatch):
    trading = Mock(return_value=False)
    monkeypatch.setattr(runner, "is_trading_day", trading)
    monkeypatch.setattr(runner, "previous_trading_day", Mock(return_value=date(2026, 10, 2)))
    assert runner.pick_day(screenshot(timestamp="2026-10-03T07:00:00Z")) == date(2026, 10, 2)  # 週六 15:00
    trading.assert_called_once_with(date(2026, 10, 3))


def test_post_before_the_close_uses_the_previous_trading_day(monkeypatch):
    previous = Mock(side_effect=lambda day: {date(2026, 10, 6): DAY, DAY: date(2026, 10, 2)}[day])
    monkeypatch.setattr(runner, "previous_trading_day", previous)
    assert runner.pick_day(screenshot(timestamp="2026-10-05T16:10:00Z")) == DAY  # 10/6 00:10
    assert runner.pick_day(screenshot(timestamp="2026-10-05T05:29:00Z")) == date(2026, 10, 2)  # 13:29


def test_screenshot_after_midnight_is_logged_for_the_previous_trading_day(env, monkeypatch):
    monkeypatch.setattr(runner, "previous_trading_day", Mock(return_value=DAY))
    env.discord.messages_since.return_value = [screenshot(timestamp="2026-10-05T16:10:00Z")]
    runner.run_once(datetime(2026, 10, 5, 16, 15, tzinfo=timezone.utc))
    env.fetch.assert_called_once_with(DAY)
    assert all(call.args[2] == DAY for call in env.write.call_args_list)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "✅")


def test_downloads_every_image_in_the_message(env):
    message = screenshot()
    message["attachments"].append({"url": "https://cdn.discordapp.com/y.png",
                                   "filename": "b.png", "content_type": "image/png"})
    env.discord.messages_since.return_value = [message]
    runner.run_once(NOW)
    assert [path.name for path in env.read.call_args.args[0]] == ["screenshot0.jpeg", "screenshot1.png"]


def test_partial_match_writes_found_and_lists_missing(env):
    env.read.return_value = ["鈊象", "鈊像"]
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    assert env.write.call_count == 1
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "⚠️")
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "找不到這些股票的 2026-10-05 收盤價：鈊像")


def test_no_match_at_all_is_an_error(env):
    env.read.return_value = ["鈊像"]
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.write.assert_not_called()
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "找不到這些股票的 2026-10-05 收盤價：鈊像")


def test_empty_screenshot_is_an_error(env):
    env.read.return_value = []
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    env.discord.reply.assert_called_once_with(runner.CHANNEL_ID, "200", "截圖中沒有辨識到股票")


def test_waits_without_reading_when_quotes_are_not_published(env):
    env.fetch.return_value = NOT_PUBLISHED
    env.discord.messages_since.return_value = [screenshot(), screenshot("201")]
    runner.run_once(NOW)
    env.read.assert_not_called()
    env.discord.react.assert_not_called()
    assert runner.load_state() == {"last_message_id": "100", "attempts": {}}


def test_gives_up_waiting_after_twelve_hours(env):
    env.fetch.return_value = NOT_PUBLISHED
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc))
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "找不到 2026-10-05 的收盤行情，可能不是交易日")
    assert runner.load_state()["last_message_id"] == "200"


def test_reports_when_quotes_moved_past_the_pick_day(env):
    env.fetch.return_value = MarketQuotes(
        {"上市": None, "上櫃": date(2026, 10, 6), "興櫃": date(2026, 10, 6)}, {})
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "官方行情已更新到 2026-10-06，無法取得 2026-10-05 的收盤價")


def test_retries_failures_then_gives_up_on_the_third(env):
    env.read.side_effect = RuntimeError("Codex 讀取截圖失敗（exit 1）")
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    runner.run_once(NOW)
    assert runner.load_state() == {"last_message_id": "100", "attempts": {"200": 2}}
    env.discord.react.assert_not_called()

    runner.run_once(NOW)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    assert "Codex 讀取截圖失敗" in env.discord.reply.call_args.args[2]
    assert runner.load_state() == {"last_message_id": "200", "attempts": {}}


def test_waiting_resets_the_failure_count(env):
    env.fetch.side_effect = [RuntimeError("TPEx 502"), NOT_PUBLISHED] * 3 + [QUOTES]
    env.discord.messages_since.return_value = [screenshot()]
    for _ in range(6):
        runner.run_once(NOW)
    env.discord.react.assert_not_called()

    runner.run_once(NOW)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "✅")
    assert runner.load_state() == {"last_message_id": "200", "attempts": {}}


def test_skips_text_and_bot_messages(env):
    text = {"id": "150", "type": 0, "timestamp": "2026-10-05T14:00:00+00:00",
            "author": {"bot": False}, "content": "今天大漲", "attachments": []}
    bot = {**screenshot("160"), "author": {"bot": True}}
    env.discord.messages_since.return_value = [text, bot]
    runner.run_once(NOW)
    env.fetch.assert_not_called()
    assert runner.load_state()["last_message_id"] == "160"
