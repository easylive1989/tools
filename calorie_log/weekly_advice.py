"""Weekly meal reviews driven by the existing serialized systemd poller."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from calorie_log.meal_time import TAIPEI
from calorie_log.nutrition_advisor import advise, recent_meals


def next_review(now: datetime, day: int, hour: int) -> datetime:
    """Return the next slot, including now; weekdays use Monday=0."""
    if not 0 <= day <= 6 or not 0 <= hour <= 23:
        raise ValueError("每週建議的星期須為 0–6，時間須為 0–23")
    local = now.astimezone(TAIPEI)
    slot = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    slot += timedelta(days=(day - local.weekday()) % 7)
    return slot if slot >= local else slot + timedelta(days=7)


def send_weekly_advice(discord, notion, channel_id: str, data_source_id: str,
                       state: dict, save_state, *, now: datetime | None = None) -> None:
    """Persist an outbox before sending, and advance only after delivery."""
    current = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    day = int(os.environ.get("NUTRITION_WEEKLY_DAY", "0"))
    hour = int(os.environ.get("NUTRITION_WEEKLY_HOUR", "8"))
    upcoming = next_review(current, day, hour)
    weekly = state.setdefault("weekly_advice", {})
    if not weekly.get("pending") and weekly.get("schedule") != [day, hour]:
        weekly.update(schedule=[day, hour], next_due=upcoming.isoformat())
        save_state(state)
    due = datetime.fromisoformat(weekly["next_due"])
    if current < due:
        return

    if not weekly.get("pending"):
        # After a long outage, review only the most recent due week.
        due += timedelta(weeks=(current - due).days // 7)
        history = recent_meals(notion, data_source_id, days=7, now=due)
        if not history.records:
            weekly.update(next_due=next_review(current + timedelta(microseconds=1), day, hour).isoformat(),
                          last_skipped=due.isoformat())
            save_state(state)
            return
        start = due - timedelta(days=7)
        period = f"{start:%Y/%m/%d %H:%M}–{due:%Y/%m/%d %H:%M}（台灣時間）"
        question = (
            f"請提供每週飲食回顧，期間為 {period}。"
            "先簡短整理本週已記錄的飲食模式，引用 2–3 個實際餐點作為依據，"
            "指出一個值得維持的習慣，並給出下週最值得嘗試的 2–3 個具體調整，"
            "包含容易實行的外食搭配或替換例子。紀錄少時請縮小結論，不要硬湊模式。"
            "未記錄不代表沒吃，不以估算熱量判定熱量盈虧，不要求跳餐或補償。"
            "若資料截斷須明說。最多 600 字，不必重複期間或筆數。"
        )
        after_id = discord.latest_message_id(channel_id) or "0"
        reply = advise([], question, history, lookback_days=7,
                       profile=os.environ.get("NUTRITION_PROFILE", ""))
        key = f"food-week-{due:%Y%m%d}"
        content = f"🥗 每週飲食回顧\n{period}\n已記錄 {len(history.records)} 餐\n\n{reply}\n\n週報編號：{key}"
        if len(content) > 2000:
            raise RuntimeError("每週飲食建議超過 Discord 訊息長度限制")
        weekly["pending"] = {"key": key, "content": content, "after_id": after_id,
                             "channel_id": channel_id}
        save_state(state)

    pending = weekly["pending"]
    message_id = discord.send_weekly_report(**pending)
    weekly.update(last_sent=pending["key"], message_id=message_id, schedule=[day, hour],
                  next_due=next_review(current + timedelta(microseconds=1), day, hour).isoformat())
    del weekly["pending"]
    save_state(state)
