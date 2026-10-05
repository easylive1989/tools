"""Write matched stock picks to the Notion「智選股當天入場」data source."""

from __future__ import annotations

from datetime import date

from common.notion import NotionApi
from stock_pick.quotes import Quote

DATA_SOURCE_ID = "3ea8303f-78f7-801f-9742-000b47c34230"


def build_properties(quote: Quote, day: date) -> dict:
    return {
        "Name": {"title": [{"text": {"content": f"{quote.code} {quote.name}"}}]},
        "進場價格": {"number": quote.price},
        "選股日期": {"date": {"start": day.isoformat()}},
    }


def already_logged(notion: NotionApi, quote: Quote, day: date) -> bool:
    response = notion.query_data_source(DATA_SOURCE_ID, {
        "filter": {"and": [
            {"property": "選股日期", "date": {"equals": day.isoformat()}},
            {"property": "Name", "title": {"starts_with": f"{quote.code} "}},
        ]},
        "page_size": 1,
    })
    response.raise_for_status()
    return bool(response.json().get("results"))


def write(notion: NotionApi, quote: Quote, day: date) -> bool:
    """Create the pick unless this stock is already logged for `day`; True when created."""
    if already_logged(notion, quote, day):
        return False
    response = notion.create_page_in_data_source(DATA_SOURCE_ID, build_properties(quote, day))
    response.raise_for_status()
    return True
