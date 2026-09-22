from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from calorie_log.discord_runner import DiscordClient, is_meal_message
from calorie_log.meal_time import TAIPEI
from calorie_log.nutrition_advisor import MealHistory, MealRecord
from calorie_log.weekly_advice import next_review, send_weekly_advice


DUE = datetime(2026, 9, 27, 20, tzinfo=TAIPEI)
HISTORY = MealHistory((MealRecord("2026-09-26T12:00:00+08:00", "雞腿便當", 650, "青菜"),))


@pytest.fixture(autouse=True)
def weekly_settings(monkeypatch):
    monkeypatch.setenv("NUTRITION_WEEKLY_DAY", "6")
    monkeypatch.setenv("NUTRITION_WEEKLY_HOUR", "20")


def due_state():
    return {"last_message_id": "100", "weekly_advice": {
        "schedule": [6, 20], "next_due": DUE.isoformat(),
    }}


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 9, 22, 12, tzinfo=TAIPEI), DUE),
    (datetime(2026, 9, 27, 12, tzinfo=timezone.utc), DUE),
    (datetime(2026, 9, 27, 20, 1, tzinfo=TAIPEI), datetime(2026, 10, 4, 20, tzinfo=TAIPEI)),
    (datetime(2026, 12, 31, 23, tzinfo=TAIPEI), datetime(2027, 1, 3, 20, tzinfo=TAIPEI)),
])
def test_schedule_handles_timezone_boundaries_and_year_rollover(now, expected):
    assert next_review(now, 6, 20) == expected


@pytest.mark.parametrize("day,hour", [(-1, 20), (7, 20), (6, -1), (6, 24)])
def test_invalid_schedule_fails(day, hour):
    with pytest.raises(ValueError):
        next_review(DUE, day, hour)


def test_initialization_waits_until_next_slot_without_reading_meals():
    state, save, discord = {}, Mock(), Mock()
    with patch("calorie_log.weekly_advice.recent_meals") as recent:
        send_weekly_advice(discord, Mock(), "channel", "source", state, save,
                           now=datetime(2026, 9, 22, 12, tzinfo=TAIPEI))
    assert state["weekly_advice"]["next_due"] == DUE.isoformat()
    save.assert_called_once_with(state)
    recent.assert_not_called()
    discord.send_weekly_report.assert_not_called()


def test_default_schedule_sends_monday_at_eight_taipei_time(monkeypatch):
    monkeypatch.delenv("NUTRITION_WEEKLY_DAY")
    monkeypatch.delenv("NUTRITION_WEEKLY_HOUR")
    state, discord = {}, Mock()
    discord.latest_message_id.return_value = "100"
    discord.send_weekly_report.return_value = "200"
    with patch("calorie_log.weekly_advice.recent_meals", return_value=HISTORY) as recent, \
         patch("calorie_log.weekly_advice.advise", return_value="飲食回顧"):
        send_weekly_advice(discord, Mock(), "channel", "source", state, Mock(),
                           now=datetime(2026, 9, 28, 7, 59, tzinfo=TAIPEI))
        assert state["weekly_advice"]["next_due"] == "2026-09-28T08:00:00+08:00"
        recent.assert_not_called()
        send_weekly_advice(discord, Mock(), "channel", "source", state, Mock(),
                           now=datetime(2026, 9, 28, 0, tzinfo=timezone.utc))
    discord.send_weekly_report.assert_called_once()
    assert recent.call_args.kwargs["now"] == datetime(2026, 9, 28, 8, tzinfo=TAIPEI)
    assert state["weekly_advice"]["next_due"] == "2026-10-05T08:00:00+08:00"


def test_weekly_review_uses_fixed_window_profile_and_sends_only_once():
    state, discord, snapshots = due_state(), Mock(), []
    discord.latest_message_id.return_value = "100"
    discord.send_weekly_report.return_value = "200"
    with patch("calorie_log.weekly_advice.recent_meals", return_value=HISTORY) as recent, \
         patch("calorie_log.weekly_advice.advise", return_value="下週便當加一份青菜。") as advice, \
         patch.dict("os.environ", {"NUTRITION_PROFILE": "不喝牛奶", "NUTRITION_LOOKBACK_DAYS": "30"}):
        for _ in range(2):
            send_weekly_advice(discord, Mock(), "channel", "source", state,
                               lambda value: snapshots.append(deepcopy(value)), now=DUE)
    assert recent.call_args.kwargs == {"days": 7, "now": DUE}
    assert advice.call_args.kwargs == {"lookback_days": 7, "profile": "不喝牛奶"}
    assert "2026/09/20 20:00–2026/09/27 20:00" in advice.call_args.args[1]
    assert "pending" in snapshots[0]["weekly_advice"]
    assert "pending" not in snapshots[-1]["weekly_advice"]
    discord.send_weekly_report.assert_called_once()
    assert state["last_message_id"] == "100"
    assert state["weekly_advice"]["message_id"] == "200"
    assert state["weekly_advice"]["next_due"] == "2026-10-04T20:00:00+08:00"


def test_empty_week_skips_without_generating_or_posting():
    state, discord = due_state(), Mock()
    with patch("calorie_log.weekly_advice.recent_meals", return_value=MealHistory(())), \
         patch("calorie_log.weekly_advice.advise") as advice:
        send_weekly_advice(discord, Mock(), "channel", "source", state, Mock(), now=DUE)
    advice.assert_not_called()
    discord.send_weekly_report.assert_not_called()
    assert state["weekly_advice"]["last_skipped"] == DUE.isoformat()


def test_generation_failure_remains_due_for_retry():
    state = due_state()
    with patch("calorie_log.weekly_advice.recent_meals", return_value=HISTORY), \
         patch("calorie_log.weekly_advice.advise", side_effect=RuntimeError("timeout")):
        with pytest.raises(RuntimeError):
            send_weekly_advice(Mock(), Mock(), "channel", "source", state, Mock(), now=DUE)
    assert state == due_state()


def test_failed_delivery_reuses_persisted_content_after_restart():
    state, snapshots, discord = due_state(), [], Mock()
    discord.latest_message_id.return_value = "100"
    discord.send_weekly_report.side_effect = RuntimeError("network")
    with patch("calorie_log.weekly_advice.recent_meals", return_value=HISTORY), \
         patch("calorie_log.weekly_advice.advise", return_value="建議"):
        with pytest.raises(RuntimeError):
            send_weekly_advice(discord, Mock(), "channel", "source", state,
                               lambda value: snapshots.append(deepcopy(value)), now=DUE)
    persisted = snapshots[-1]
    discord.send_weekly_report.side_effect = None
    discord.send_weekly_report.return_value = "200"
    with patch("calorie_log.weekly_advice.advise") as advice:
        send_weekly_advice(discord, Mock(), "channel", "source", persisted, Mock(), now=DUE)
    advice.assert_not_called()
    assert discord.send_weekly_report.call_args_list[0] == discord.send_weekly_report.call_args_list[1]
    assert "pending" not in persisted["weekly_advice"]


def test_outage_only_reviews_latest_due_week():
    state = due_state()
    with patch("calorie_log.weekly_advice.recent_meals", return_value=MealHistory(())) as recent:
        send_weekly_advice(Mock(), Mock(), "channel", "source", state, Mock(),
                           now=datetime(2026, 10, 14, 12, tzinfo=TAIPEI))
    assert recent.call_args.kwargs["now"] == datetime(2026, 10, 11, 20, tzinfo=TAIPEI)
    assert state["weekly_advice"]["next_due"] == "2026-10-18T20:00:00+08:00"


def test_schedule_change_reschedules_next_delivery(monkeypatch):
    state, discord = due_state(), Mock()
    monkeypatch.setenv("NUTRITION_WEEKLY_DAY", "0")
    monkeypatch.setenv("NUTRITION_WEEKLY_HOUR", "9")
    send_weekly_advice(discord, Mock(), "channel", "source", state, Mock(), now=DUE)
    assert state["weekly_advice"]["next_due"] == "2026-09-28T09:00:00+08:00"
    discord.send_weekly_report.assert_not_called()


def test_delivery_recovers_previously_sent_report_from_own_bot():
    client = DiscordClient("test")
    client.request = Mock(return_value=Mock(json=lambda: {"id": "bot"}))
    client.messages_since = Mock(return_value=[
        {"id": "199", "content": "建議\n\n週報編號：food-week-20260927", "author": {"id": "other"}},
        {"id": "200", "content": "建議\n\n週報編號：food-week-20260927", "author": {"id": "bot", "bot": True}},
    ])
    assert client.send_weekly_report("channel", "建議", "food-week-20260927", "100") == "200"
    assert client.request.call_count == 1  # No POST, even long after the nonce expires.
    assert not is_meal_message(client.messages_since.return_value[-1])


def test_new_report_suppresses_mentions_and_uses_a_stable_nonce():
    client = DiscordClient("test")
    client.request = Mock(side_effect=[Mock(json=lambda: {"id": "bot"}), Mock(json=lambda: {"id": "200"})])
    client.messages_since = Mock(return_value=[])
    assert client.send_weekly_report("channel", "建議", "food-week-20260927", "100") == "200"
    payload = client.request.call_args.kwargs["json"]
    assert payload["allowed_mentions"] == {"parse": []}
    assert payload["nonce"] == "food-week-20260927"
    assert payload["enforce_nonce"] is True
