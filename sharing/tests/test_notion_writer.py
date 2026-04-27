import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extractor import ExtractResult
from notion_writer import build_properties


def test_build_properties_full():
    result = ExtractResult(
        name="鼎泰豐",
        url="https://dtf.com",
        region="台北市",
        town="大安區",
        types=["台式", "小籠包"],
        note="必點XO醬",
        rating=4.5,
        confidence="full",
    )
    props = build_properties(result)
    assert props["Name"] == {"title": [{"text": {"content": "鼎泰豐"}}]}
    assert props["連結"] == {"url": "https://dtf.com"}
    assert props["地區"] == {"select": {"name": "台北市"}}
    assert props["鄉鎮"] == {"select": {"name": "大安區"}}
    assert props["類型"] == {"multi_select": [{"name": "台式"}, {"name": "小籠包"}]}
    assert props["Note"] == {"rich_text": [{"text": {"content": "必點XO醬"}}]}
    assert props["評級"] == {"number": 4.5}
    assert "吃過" not in props  # 不預設寫入，讓 Notion 用 DB 預設值


def test_build_properties_partial_no_rating():
    result = ExtractResult(
        name="某餐廳",
        url=None,
        region=None,
        town=None,
        types=[],
        note="原始訊息",
        rating=None,
        confidence="partial",
    )
    props = build_properties(result)
    assert props["Name"] == {"title": [{"text": {"content": "某餐廳"}}]}
    assert "連結" not in props
    assert "地區" not in props
    assert "鄉鎮" not in props
    assert props["類型"] == {"multi_select": []}
    assert "評級" not in props


def test_build_properties_note_truncated():
    result = ExtractResult(
        name="x", url=None, region=None, town=None,
        types=[], note="a" * 3000, rating=None, confidence="partial"
    )
    props = build_properties(result)
    # Notion rich_text 單欄位限 2000 字
    content = props["Note"]["rich_text"][0]["text"]["content"]
    assert len(content) <= 2000
