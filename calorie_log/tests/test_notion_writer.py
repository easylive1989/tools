from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from calorie_log.estimator import Estimate, FoodItem
from calorie_log.notion_writer import write


def test_write_maps_estimate_to_meal_log_properties():
    estimate = Estimate(
        meal_name="雞肉飯", items=(FoodItem("雞肉飯", "一碗", 480),),
        total_kcal=480, assumptions="醬汁份量未明", confidence="medium",
    )
    notion = Mock()
    notion.get_data_source.return_value.json.return_value = {"properties": {
        "時間": {"type": "date"}, "備註": {"type": "rich_text"},
        "餐別": {"type": "select", "select": {"options": [{"name": "午餐"}]}},
        "卡路里": {"type": "number"}, "照片": {"type": "files"},
        "餐點": {"type": "title"},
    }}
    notion.upload_file.return_value = "upload-1"
    notion.create_page_in_data_source.return_value.json.return_value = {
        "url": "https://www.notion.so/meal"
    }

    url = write(
        estimate, "吃了一碗雞肉飯", [Path("meal.jpg")], notion, "source-1",
        datetime(2026, 9, 13, 12, 30, tzinfo=timezone.utc), "午餐",
    )

    props = notion.create_page_in_data_source.call_args.args[1]
    assert url == "https://www.notion.so/meal"
    assert props["卡路里"]["number"] == 480
    assert props["餐別"]["select"]["name"] == "午餐"
    assert props["照片"]["files"][0]["file_upload"]["id"] == "upload-1"
    assert "醬汁份量未明" in props["備註"]["rich_text"][0]["text"]["content"]


def test_retry_finds_existing_message_without_uploading_again():
    estimate = Estimate(
        meal_name="雞肉飯", items=(FoodItem("雞肉飯", "一碗", 480),),
        total_kcal=480, assumptions="", confidence="medium",
    )
    notion = Mock()
    notion.get_data_source.return_value.json.return_value = {"properties": {
        "時間": {"type": "date"}, "備註": {"type": "rich_text"},
        "餐別": {"type": "select", "select": {"options": []}},
        "卡路里": {"type": "number"}, "照片": {"type": "files"},
        "餐點": {"type": "title"},
    }}
    notion.query_data_source.return_value.json.return_value = {
        "results": [{"url": "https://www.notion.so/existing"}]
    }

    url = write(
        estimate, "", [Path("meal.jpg")], notion, "source-1",
        datetime(2026, 9, 13, tzinfo=timezone.utc),
        source_message_id="12345",
    )

    assert url == "https://www.notion.so/existing"
    notion.upload_file.assert_not_called()
    notion.create_page_in_data_source.assert_not_called()


def test_thread_update_changes_existing_page_without_replacing_photo():
    estimate = Estimate(
        meal_name="雞肉飯與拿鐵", items=(FoodItem("餐點", "一份", 600),),
        total_kcal=600, assumptions="", confidence="medium",
    )
    notion = Mock()
    notion.get_data_source.return_value.json.return_value = {"properties": {
        "時間": {"type": "date"}, "備註": {"type": "rich_text"},
        "餐別": {"type": "select", "select": {"options": []}},
        "卡路里": {"type": "number"}, "照片": {"type": "files"},
        "餐點": {"type": "title"},
    }}
    notion.query_data_source.return_value.json.return_value = {
        "results": [{"id": "page-1", "url": "https://www.notion.so/meal"}]
    }
    notion.patch_page.return_value.json.return_value = {"url": "https://www.notion.so/meal"}

    write(
        estimate, "補充：還有拿鐵", [], notion, "source-1",
        datetime(2026, 9, 13, tzinfo=timezone.utc),
        include_photos=False, source_message_id="12345", update_existing=True,
    )

    body = notion.patch_page.call_args.args[1]
    assert body["properties"]["卡路里"]["number"] == 600
    assert "照片" not in body["properties"]
    notion.upload_file.assert_not_called()
