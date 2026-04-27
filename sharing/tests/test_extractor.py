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
