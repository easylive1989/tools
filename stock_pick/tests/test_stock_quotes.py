from datetime import date
from unittest.mock import patch

import pytest

from stock_pick.quotes import (
    PASSED, READY, TPEX_OTC, TWSE_DAILY, WAITING, Quote, fetch_quotes, match,
    is_trading_day, parse_tpex, parse_twse, previous_trading_day, quote_status, roc_date,
)

DAY = date(2026, 10, 5)
TWSE_PAYLOAD = {
    "stat": "OK",
    "date": "20261005",
    "tables": [
        {"fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "49,712.04"]]},
        {"fields": ["證券代號", "證券名稱", "成交股數", "收盤價"], "data": [
            ["1477", "聚陽", "1,000", "197.50"],
            ["2485", "兆赫  ", "2,000", "44.60"],
            ["9999", "停牌股", "0", "--"],
            ["2330", "台積電", "9,000", "1,234.50"],
        ]},
    ],
}
OTC_ROWS = [
    {"Date": "1151005", "SecuritiesCompanyCode": "3293", "CompanyName": "鈊象", "Close": "794.00"},
    {"Date": "1151005", "SecuritiesCompanyCode": "5452", "CompanyName": "佶優", "Close": "30.00"},
]
ESB_ROWS = [
    {"Date": "1151005", "SecuritiesCompanyCode": "7731", "CompanyName": "火星生技*", "LatestPrice": "4.51"},
    {"Date": "1151005", "SecuritiesCompanyCode": "1260", "CompanyName": "富味鄉", "LatestPrice": ""},
]


def test_roc_date_converts_minguo_year():
    assert roc_date("1151005") == date(2026, 10, 5)
    assert roc_date("991231") == date(2010, 12, 31)
    assert roc_date("115/10/05") == date(2026, 10, 5)


TRADING_DAYS = {
    "20261001": {"stat": "OK", "data": [["115/10/01", "1"], ["115/10/02", "1"], ["115/10/05", "1"]]},
    "20260901": {"stat": "OK", "data": [["115/09/29", "1"], ["115/09/30", "1"]]},
}


def fake_calendar(url, params=None):
    return TRADING_DAYS.get(params["date"], {"stat": "很抱歉，沒有符合條件的資料!"})


def test_previous_trading_day_skips_the_weekend():
    with patch("stock_pick.quotes._get_json", side_effect=fake_calendar):
        assert previous_trading_day(date(2026, 10, 5)) == date(2026, 10, 2)
        assert previous_trading_day(date(2026, 10, 6)) == date(2026, 10, 5)


def test_previous_trading_day_looks_back_into_the_previous_month():
    with patch("stock_pick.quotes._get_json", side_effect=fake_calendar):
        assert previous_trading_day(date(2026, 10, 1)) == date(2026, 9, 30)


HOLIDAYS_2026 = {"stat": "ok", "fields": ["日期", "名稱", "說明"], "data": [
    ["2026-01-01", "中華民國開國紀念日", "依規定放假1日。"],
    ["2026-01-02", "國曆新年開始交易日", "國曆新年開始交易。"],
    ["2026-02-11", "農曆春節前最後交易日", "農曆春節前最後交易。\r\n"],
    ["2026-02-12", "市場無交易，僅辦理結算交割作業", ""],
    ["2026-10-09", "國慶日", "國慶日為10月10日適逢星期六，於10月9日（星期五）補假。"],
]}


def fake_holidays(url, params=None):
    assert params["date"] == "20260101"
    return HOLIDAYS_2026


@pytest.mark.parametrize(("day", "expected"), [
    (date(2026, 10, 6), True),    # 一般週二
    (date(2026, 10, 9), False),   # 國慶日補假（週五）
    (date(2026, 2, 12), False),   # 市場無交易，僅辦理結算交割
    (date(2026, 1, 2), True),     # 開始交易日只是說明，照常交易
    (date(2026, 2, 11), True),    # 最後交易日照常交易
])
def test_is_trading_day_reads_the_twse_holiday_schedule(day, expected):
    with patch("stock_pick.quotes._get_json", side_effect=fake_holidays):
        assert is_trading_day(day) is expected


def test_weekends_are_never_trading_days_without_asking_twse():
    with patch("stock_pick.quotes._get_json") as get:
        assert is_trading_day(date(2026, 10, 3)) is False
        assert is_trading_day(date(2026, 10, 4)) is False
    get.assert_not_called()


def test_previous_trading_day_gives_up_without_any_trading_day():
    with patch("stock_pick.quotes._get_json", side_effect=fake_calendar):
        with pytest.raises(ValueError, match="之前的交易日"):
            previous_trading_day(date(2026, 8, 3))


def test_parse_twse_reads_the_closing_table_and_cleans_names():
    quotes = {quote.name: quote for quote in parse_twse(TWSE_PAYLOAD, DAY)}
    assert quotes["兆赫"] == Quote("2485", "兆赫", "上市", 44.6)
    assert quotes["台積電"].price == 1234.5
    assert quotes["停牌股"].price is None


def test_parse_twse_returns_none_when_the_day_is_not_published():
    assert parse_twse({"stat": "很抱歉，沒有符合條件的資料!"}, DAY) is None


def test_parse_twse_rejects_a_different_day():
    with pytest.raises(ValueError, match="日期不符"):
        parse_twse({**TWSE_PAYLOAD, "date": "20261002"}, DAY)


def test_parse_tpex_returns_latest_day_and_quotes():
    day, quotes = parse_tpex(ESB_ROWS, "興櫃", "LatestPrice")
    assert day == DAY
    assert quotes[0] == Quote("7731", "火星生技*", "興櫃", 4.51)
    assert quotes[1].price is None


def test_fetch_quotes_merges_three_markets():
    def fake_get(url, params=None):
        if url == TWSE_DAILY:
            assert params["date"] == "20261005"
            return TWSE_PAYLOAD
        return OTC_ROWS if url == TPEX_OTC else ESB_ROWS

    with patch("stock_pick.quotes._get_json", side_effect=fake_get):
        quotes = fetch_quotes(DAY)

    assert quotes.days == {"上市": DAY, "上櫃": DAY, "興櫃": DAY}
    assert quotes.by_name["聚陽"] == Quote("1477", "聚陽", "上市", 197.5)
    assert quotes.by_name["鈊象"].market == "上櫃"
    assert quotes.by_name["火星生技*"].code == "7731"


def test_fetch_quotes_marks_unpublished_twse_day_as_none():
    def fake_get(url, params=None):
        if url == TWSE_DAILY:
            return {"stat": "很抱歉，沒有符合條件的資料!"}
        return OTC_ROWS if url == TPEX_OTC else ESB_ROWS

    with patch("stock_pick.quotes._get_json", side_effect=fake_get):
        assert fetch_quotes(DAY).days["上市"] is None


@pytest.mark.parametrize(("days", "expected"), [
    ({"上市": DAY, "上櫃": DAY, "興櫃": DAY}, READY),
    ({"上市": None, "上櫃": DAY, "興櫃": DAY}, WAITING),
    ({"上市": DAY, "上櫃": date(2026, 10, 2), "興櫃": DAY}, WAITING),
    ({"上市": None, "上櫃": date(2026, 10, 6), "興櫃": date(2026, 10, 6)}, PASSED),
])
def test_quote_status(days, expected):
    assert quote_status(days, DAY) == expected


def test_match_treats_full_width_and_half_width_alike():
    by_name = {"亞德客-KY": Quote("1590", "亞德客-KY", "上市", 300.0)}
    found, missing = match(["亞德客－KY", "亞德客-ＫＹ"], by_name)
    assert [quote.code for quote in found] == ["1590", "1590"]
    assert missing == []


def test_match_adds_the_emerging_star_codex_left_off():
    star = Quote("7731", "火星生技*", "興櫃", 4.51)
    found, missing = match(["火星生技"], {"火星生技*": star})
    assert found == [star]
    assert missing == []


def test_match_ignores_whitespace_and_reports_missing_names():
    by_name = {
        "群益證": Quote("6005", "群益證", "上市", 33.0),
        "富味鄉": Quote("1260", "富味鄉", "興櫃", None),
    }
    found, missing = match(["群益 證", "群益　證", "富味鄉", "鈊像"], by_name)
    assert found == [Quote("6005", "群益證", "上市", 33.0)] * 2
    assert missing == ["富味鄉", "鈊像"]
