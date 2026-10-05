from datetime import date
from unittest.mock import Mock

from stock_pick.notion_writer import DATA_SOURCE_ID, build_properties, write
from stock_pick.quotes import Quote

DAY = date(2026, 10, 5)
QUOTE = Quote("7731", "火星生技*", "興櫃", 4.51)


def response(payload):
    resp = Mock()
    resp.json.return_value = payload
    return resp


def test_build_properties_matches_existing_rows():
    assert build_properties(QUOTE, DAY) == {
        "Name": {"title": [{"text": {"content": "7731 火星生技*"}}]},
        "進場價格": {"number": 4.51},
        "選股日期": {"date": {"start": "2026-10-05"}},
    }


def test_write_creates_page_when_not_logged_yet():
    notion = Mock()
    notion.query_data_source.return_value = response({"results": []})

    assert write(notion, QUOTE, DAY) is True

    data_source, body = notion.query_data_source.call_args.args
    assert data_source == DATA_SOURCE_ID
    assert body["filter"]["and"] == [
        {"property": "選股日期", "date": {"equals": "2026-10-05"}},
        {"property": "Name", "title": {"starts_with": "7731 "}},
    ]
    notion.create_page_in_data_source.assert_called_once_with(
        DATA_SOURCE_ID, build_properties(QUOTE, DAY))


def test_write_skips_stock_already_logged_that_day():
    notion = Mock()
    notion.query_data_source.return_value = response({"results": [{"id": "page"}]})

    assert write(notion, QUOTE, DAY) is False
    notion.create_page_in_data_source.assert_not_called()
