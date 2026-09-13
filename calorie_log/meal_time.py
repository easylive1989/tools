"""Choose a meal timestamp and meal type from photo metadata or Discord time."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image


TAIPEI = ZoneInfo("Asia/Taipei")
EXIF_DATETIME_ORIGINAL = 36867
EXIF_OFFSET_TIME_ORIGINAL = 36881


def choose_meal_time(image: Path, message_time: datetime) -> datetime:
    if message_time.tzinfo is None:
        raise ValueError("Discord 訊息時間必須包含時區")
    try:
        if image.suffix.lower() == ".heic":
            from pillow_heif import register_heif_opener

            register_heif_opener()
        with Image.open(image) as photo:
            exif = photo.getexif()
            raw = exif.get(EXIF_DATETIME_ORIGINAL)
            offset = exif.get(EXIF_OFFSET_TIME_ORIGINAL)
        if isinstance(raw, str):
            captured = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
            if isinstance(offset, str):
                captured = datetime.fromisoformat(captured.isoformat() + offset)
            else:
                captured = captured.replace(tzinfo=TAIPEI)
            return captured.astimezone(TAIPEI)
    except (OSError, ValueError, TypeError):
        pass
    return message_time.astimezone(TAIPEI)


def meal_type_at(when: datetime) -> str:
    hour = when.astimezone(TAIPEI).hour
    if 5 <= hour < 11:
        return "早餐"
    if 11 <= hour < 16:
        return "午餐"
    if 16 <= hour < 21:
        return "晚餐"
    return "點心"


def parse_discord_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
