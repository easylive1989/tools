import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extractor import extract_urls


def test_extract_urls_finds_https():
    urls = extract_urls("去這家！https://www.google.com 很好吃")
    assert urls == ["https://www.google.com"]


def test_extract_urls_finds_multiple():
    urls = extract_urls("https://a.com 和 https://b.com/path?q=1")
    assert urls == ["https://a.com", "https://b.com/path?q=1"]


def test_extract_urls_empty():
    assert extract_urls("沒有網址的訊息") == []


from unittest.mock import MagicMock, patch
from extractor import extract, ExtractResult


def _make_gemini(reply: str) -> MagicMock:
    g = MagicMock()
    g.generate.return_value = reply
    return g


def test_extract_full_json():
    gemini = _make_gemini(
        '{"name":"鼎泰豐","url":"https://dtf.com","region":"台北市",'
        '"town":"大安區","types":["台式","小籠包"],"note":"必點XO醬","rating":4.5}'
    )
    with patch("extractor.fetch_page_text", return_value=None):
        result = extract("https://dtf.com 鼎泰豐超讚", gemini)
    assert result.name == "鼎泰豐"
    assert result.region == "台北市"
    assert result.town == "大安區"
    assert result.types == ["台式", "小籠包"]
    assert result.rating == 4.5
    assert result.confidence == "full"


def test_extract_partial_fallback_on_bad_json():
    gemini = _make_gemini("抱歉我無法解析這個")
    with patch("extractor.fetch_page_text", return_value=None):
        result = extract("https://example.com 好吃的餐廳", gemini)
    assert result.confidence == "partial"
    assert result.url == "https://example.com"
    assert "好吃的餐廳" in result.note


def test_extract_no_url():
    gemini = _make_gemini('{"name":"某餐廳","url":null,"region":null,"town":null,"types":[],"note":"","rating":null}')
    result = extract("某餐廳在信義區，很好吃", gemini)
    assert result.name == "某餐廳"
    assert result.url is None
    assert result.confidence == "full"
