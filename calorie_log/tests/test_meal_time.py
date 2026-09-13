from datetime import datetime, timezone

from PIL import Image

from calorie_log.meal_time import choose_meal_time, meal_type_at


def test_photo_capture_time_takes_precedence(tmp_path):
    path = tmp_path / "meal.jpg"
    exif = Image.Exif()
    exif[36867] = "2026:09:12 12:34:56"
    Image.new("RGB", (1, 1)).save(path, exif=exif)

    when = choose_meal_time(path, datetime(2026, 9, 13, tzinfo=timezone.utc))
    assert when.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-12 12:34:56"
    assert meal_type_at(when) == "午餐"


def test_message_time_is_fallback(tmp_path):
    path = tmp_path / "meal.jpg"
    Image.new("RGB", (1, 1)).save(path)

    when = choose_meal_time(path, datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc))
    assert when.hour == 9
    assert meal_type_at(when) == "早餐"
