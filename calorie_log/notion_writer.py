"""Write a meal estimate into a Notion meal-log data source."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from common.notion import NotionApi
from calorie_log.estimator import Estimate


EXPECTED_PROPERTIES = {
    "時間": "date",
    "備註": "rich_text",
    "餐別": "select",
    "卡路里": "number",
    "照片": "files",
    "餐點": "title",
}


def build_note(estimate: Estimate, description: str, source_message_id: str | None = None) -> str:
    lines = [f"Discord 訊息：[{source_message_id}]"] if source_message_id else []
    if description.strip():
        lines.extend(("", f"原始說明：{description.strip()}"))
    if estimate.assumptions:
        lines.extend(("", f"估算假設：{estimate.assumptions}"))
    lines.extend(("", f"估算信心：{estimate.confidence}"))
    return "\n".join(lines)[:2000]


def write(
    estimate: Estimate,
    description: str,
    images: list[Path],
    notion: NotionApi,
    data_source_id: str,
    eaten_at: datetime,
    meal_type: str | None = None,
    *,
    include_photos: bool = True,
    source_message_id: str | None = None,
    update_existing: bool = False,
) -> str:
    if eaten_at.tzinfo is None or eaten_at.utcoffset() is None:
        raise ValueError("用餐時間必須包含時區")

    schema_response = notion.get_data_source(data_source_id)
    schema_response.raise_for_status()
    properties_schema = schema_response.json().get("properties", {})
    mismatched = [
        name for name, kind in EXPECTED_PROPERTIES.items()
        if properties_schema.get(name, {}).get("type") != kind
    ]
    if mismatched:
        raise ValueError(f"Notion 資料庫缺少所需欄位或欄位類型不符：{', '.join(mismatched)}")
    if meal_type:
        options = {
            option["name"] for option in properties_schema["餐別"]["select"].get("options", [])
        }
        if meal_type not in options:
            raise ValueError(f"Notion 餐別不存在：{meal_type}")

    existing_page = None
    if source_message_id:
        existing = notion.query_data_source(data_source_id, {
            "filter": {"property": "備註", "rich_text": {
                "contains": f"Discord 訊息：[{source_message_id}]"
            }}
        })
        existing.raise_for_status()
        matches = existing.json().get("results", [])
        if matches:
            existing_page = matches[0]
    if update_existing and not existing_page:
        raise ValueError(f"找不到 Discord 訊息 {source_message_id} 對應的 Notion 紀錄")
    if existing_page and not update_existing:
        return existing_page["url"]

    properties: dict = {
        "餐點": {"title": [{"text": {"content": estimate.meal_name[:2000]}}]},
        "卡路里": {"number": estimate.total_kcal},
        "時間": {"date": {"start": eaten_at.isoformat()}},
        "備註": {"rich_text": [{"text": {"content": build_note(estimate, description, source_message_id)}}]},
    }
    if meal_type:
        properties["餐別"] = {"select": {"name": meal_type}}
    if existing_page:
        response = notion.patch_page(existing_page["id"], {"properties": properties})
        response.raise_for_status()
        return response.json()["url"]
    if include_photos:
        properties["照片"] = {"files": [
            {"type": "file_upload", "file_upload": {"id": notion.upload_file(image)},
             "name": image.name}
            for image in images
        ]}
    response = notion.create_page_in_data_source(data_source_id, properties)
    response.raise_for_status()
    return response.json()["url"]
