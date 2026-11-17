import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from invoice_fields import (  # noqa: E402
    Result, chinese_amount, extract_from_ocr, filing_period, is_valid_tax_id, parse_einvoice,
    split_tax, summarize, to_csv, validate,
)


def ocr(*rows):
    """把一列列文字做成假的 OCR 輸出；同一列可以用 tuple 放多個方塊。"""
    items = []
    for y, row in enumerate(rows):
        parts = row if isinstance(row, tuple) else (row,)
        for x, text in enumerate(parts):
            x0, y0 = x * 200, y * 40
            items.append(([[x0, y0], [x0 + 150, y0], [x0 + 150, y0 + 30], [x0, y0 + 30]], text, 0.95))
    return items


def left_qr(no="AB12345678", roc="1151105", sales=1000, total=1050, buyer="22099131", seller="04595257"):
    return f"{no}{roc}1234{sales:08X}{total:08X}{buyer}{seller}{'0' * 24}:**********:1:1:1:茶:1:{total}"


def test_tax_id():
    assert is_valid_tax_id("22099131")
    assert is_valid_tax_id("04595257")
    assert not is_valid_tax_id("22099132")


def test_einvoice_b2b():
    r = parse_einvoice(left_qr())
    assert (r.invoice_no, r.date, r.format_code) == ("AB12345678", "2026-11-05", 25)
    assert (r.sales_amount, r.tax, r.total) == (1000, 50, 1050)
    assert validate(r)[1] is True


def test_einvoice_b2c_not_deductible():
    r = parse_einvoice(left_qr(buyer="00000000", sales=1050))
    assert r.buyer_tax_id is None and (r.sales_amount, r.tax) == (1000, 50)
    assert validate(r)[1] is False


def test_duplicate_cash_register_with_buyer():
    r = extract_from_ocr(ocr(
        "中華民國115年09-10月份", "收銀機統一發票(收執聯)", ("XY", "12345678"), "好鄰居便利商店",
        "統编：04595257", "2026-09-15 12:30:11", "買方：22099131", "咖啡 65TX", "總計 365", "現金 500", "找零 135",
    ))
    assert r.format_code == 22
    assert r.invoice_no == "XY12345678"
    assert r.date == "2026-09-15"
    assert (r.seller_tax_id, r.buyer_tax_id) == ("04595257", "22099131")
    assert (r.total, r.sales_amount, r.tax) == (365, 348, 17)
    assert r.uncertain == []


def test_triplicate_cash_register_reads_printed_tax():
    r = extract_from_ocr(ocr(
        "收銀機統一發票(扣抵聯)", "AB 87654321", "統一編號：04595257", "買受人統一編號：22099131",
        "日期：115/10/02", "銷售額 2000", "營業稅 100", "總計 2100",
    ))
    assert (r.format_code, r.date) == (25, "2026-10-02")
    assert (r.sales_amount, r.tax, r.total) == (2000, 100, 2100)


def test_period_header_is_not_a_date_and_bad_year_is_fixed():
    r = extract_from_ocr(ocr("中華民國112年11-12月份", "UB01668568", "統編：53356245", "123/12/27 18:57:24", "437TX"))
    assert r.date == "2023-12-27"
    assert "date" in r.uncertain
    assert r.total == 437


def test_misread_subtotal_uses_last_one():
    # 真實照片的 OCR 結果：小計被讀成小韵／小部／小新
    r = extract_from_ocr(ocr("中華民國115年11-12月份", "收銀機統發票", "GH51204513", "纯：82627425",
                             "2026-11-1409=20", "日用百貨 129%", "小韵 329", "日用百貨 -49页", "小部 280", "小新 521"))
    assert (r.invoice_no, r.date, r.seller_tax_id, r.total) == ("GH51204513", "2026-11-14", "82627425", 521)
    assert "total" in r.uncertain


def test_invoice_no_with_ocr_letter_o():
    r = extract_from_ocr(ocr(("UB", "O8524853"), "統編：81007881"))
    assert r.invoice_no == "UB08524853"


def test_receipt():
    r = extract_from_ocr(ocr("收 據", "茲收到王小明先生", "新台幣壹仟伍佰元整", "中華民國115年10月5日"))
    assert r.doc_type == "receipt" and r.format_code is None
    assert (r.total, r.date) == (1500, "2026-10-05")
    assert r.tax is None
    assert validate(r)[1] is False


def test_chinese_amount():
    assert chinese_amount("新台幣壹萬貳仟參佰元整") == 12300
    assert chinese_amount("壹仟零伍拾元") == 1050
    assert chinese_amount("拾伍") == 15
    assert chinese_amount("abc") is None


def test_helpers_and_csv():
    assert split_tax(105) == (100, 5)
    assert filing_period("2026-11-05") == "115年11-12月"
    rows = [("a.jpg", parse_einvoice(left_qr())), ("b.jpg", Result(doc_type="receipt", total=300, date="2026-11-01"))]
    s = summarize([r for _, r in rows])
    assert s["115年11-12月"][1] == [1000, 50] and s["115年11-12月"]["non_deductible"] == 1
    assert s["115年11-12月"]["grand_total"] == 1350
    csv_text = to_csv(rows, "22099131")
    assert csv_text.startswith("﻿檔案,申報期別")
    assert len(csv_text.strip().split("\r\n")) == 3
