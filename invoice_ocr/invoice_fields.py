"""從電子發票 QR Code 或 OCR 文字抓出營業稅 401 申報要用的欄位。

純函式，不碰檔案和模型，方便測試。OCR 的輸入是 ``[(box, text, score), ...]``，
box 是四個角的座標（PaddleOCR / RapidOCR 的格式）。
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

FORMAT_CODES = {
    21: "進項三聯式、電子計算機統一發票",
    22: "進項二聯式收銀機統一發票、載有稅額之其他憑證",
    25: "進項三聯式收銀機統一發票、一般稅額計算之電子發票",
}

# OCR 偶爾吐出簡體字，關鍵字先轉回繁體再比對
_S2T = str.maketrans("统编号电话计额税货买卖发证联总应实销额项码营业", "統編號電話計額稅貨買賣發證聯總應實銷額項碼營業")
# 只在「應該是數字」的地方使用
_DIGITISH = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "Z": "2", "S": "5", "B": "8"})


@dataclass
class Result:
    doc_type: str = "receipt"
    format_code: int | None = None
    invoice_no: str | None = None
    date: str | None = None
    seller_tax_id: str | None = None
    seller_name: str | None = None
    buyer_tax_id: str | None = None
    sales_amount: int | None = None
    tax: int | None = None
    total: int | None = None
    tax_type: int = 1
    deduct_code: int = 1
    source: str = "ocr"
    uncertain: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


# ---------------------------------------------------------------- 驗證工具


def is_valid_tax_id(s: str | None) -> bool:
    """統一編號檢查碼（2023 年起「可被 5 整除」規則；舊的被 10 整除也會通過）。"""
    if not s or not re.fullmatch(r"\d{8}", s):
        return False
    w = [1, 2, 1, 2, 1, 2, 4, 1]
    total = 0
    for d, k in zip(s, w):
        p = int(d) * k
        total += p // 10 + p % 10
    if total % 5 == 0:
        return True
    return s[6] == "7" and (total + 1) % 5 == 0


def is_valid_invoice_no(s: str | None) -> bool:
    return bool(s) and re.fullmatch(r"[A-Z]{2}\d{8}", s) is not None


def roc_now() -> int:
    return date.today().year - 1911


def filing_period(iso: str | None) -> str | None:
    m = re.match(r"(\d{4})-(\d{2})", iso or "")
    if not m:
        return None
    start = (int(m[2]) - 1) // 2 * 2 + 1
    return f"{int(m[1]) - 1911}年{start:02d}-{start + 1:02d}月"


def split_tax(total: int) -> tuple[int, int]:
    sales = round(total / 1.05)
    return sales, total - sales


def fill_amounts(r: Result) -> Result:
    """補齊 銷售額／稅額／總計 中缺的欄位。"""
    s, t, T = r.sales_amount, r.tax, r.total
    if r.tax_type != 1:
        t = 0
        s = s if s is not None else T
        T = T if T is not None else s
    elif s is not None and t is not None and T is None:
        T = s + t
    elif s is not None and T is not None and t is None:
        t = T - s
    elif t is not None and T is not None and s is None:
        s = T - t
    elif T is not None and s is None and t is None:
        s, t = split_tax(T)
    elif s is not None and t is None and T is None:
        t = round(s * 0.05)
        T = s + t
    r.sales_amount, r.tax, r.total = s, t, T
    return r


def validate(r: Result, company_tax_id: str = "") -> tuple[dict[str, str], bool, str]:
    """回傳 (errors, 可否扣抵, 不可扣抵原因)。"""
    e: dict[str, str] = {}
    is_receipt = r.doc_type == "receipt" or r.format_code not in FORMAT_CODES
    if not r.invoice_no:
        if not is_receipt:
            e["invoice_no"] = "缺少發票號碼"
    elif not is_valid_invoice_no(r.invoice_no):
        e["invoice_no"] = "發票號碼應為 2 碼英文 + 8 碼數字"
    if not r.seller_tax_id:
        if not is_receipt:
            e["seller_tax_id"] = "缺少賣方統編"
    elif not is_valid_tax_id(r.seller_tax_id):
        e["seller_tax_id"] = "賣方統編檢查碼不正確"
    if r.buyer_tax_id and not is_valid_tax_id(r.buyer_tax_id):
        e["buyer_tax_id"] = "買方統編檢查碼不正確"
    elif company_tax_id and r.buyer_tax_id and r.buyer_tax_id != company_tax_id:
        e["buyer_tax_id"] = f"買方統編不是貴公司（{company_tax_id}）"
    if not r.date:
        e["date"] = "缺少日期"
    elif r.date > date.today().isoformat():
        e["date"] = "日期在未來"
    if r.total is None:
        e["total"] = "缺少總計"
    elif r.sales_amount is not None and r.tax is not None and r.sales_amount + r.tax != r.total:
        e["total"] = f"銷售額 {r.sales_amount} + 稅額 {r.tax} ≠ 總計 {r.total}"
    if r.tax_type == 1 and r.sales_amount and r.tax is not None and abs(round(r.sales_amount * 0.05) - r.tax) > 1:
        e["tax"] = f"稅額和銷售額的 5%（{round(r.sales_amount * 0.05)}）差太多"

    if is_receipt:
        return e, False, "收據或非統一發票，不能扣抵進項稅額"
    if not r.buyer_tax_id:
        return e, False, "沒有買方統編，不能扣抵進項稅額"
    if r.deduct_code == 0:
        return e, False, "已標記為不可扣抵"
    return e, True, ""


# ---------------------------------------------------------------- 電子發票 QR

_LEFT_QR = re.compile(r"^([A-Z]{2}\d{8})(\d{7})([0-9A-Za-z]{4})([0-9a-fA-F]{8})([0-9a-fA-F]{8})(\d{8})(\d{8})")


def classify_qr(text: str) -> str | None:
    if text.startswith("**"):
        return "right"
    if _LEFT_QR.match(text):
        return "left"
    return None


def parse_einvoice(text: str) -> Result:
    m = _LEFT_QR.match(text)
    if not m:
        raise ValueError("不是電子發票左邊的 QR Code")
    inv, roc, _rnd, sales_hex, total_hex, buyer, seller = m.groups()
    total = int(total_hex, 16)
    buyer_id = None if buyer == "00000000" else buyer
    sales: int | None = int(sales_hex, 16)
    if not buyer_id or sales >= total:
        sales = None  # B2C 的「銷售額」通常等於含稅總額，改用總額回推
    r = Result(
        doc_type="e_invoice", format_code=25, invoice_no=inv,
        date=f"{int(roc[:3]) + 1911}-{roc[3:5]}-{roc[5:7]}",
        seller_tax_id=seller, buyer_tax_id=buyer_id, total=total, sales_amount=sales,
        tax=None if sales is None else total - sales, source="qr",
    )
    return fill_amounts(r)


# ---------------------------------------------------------------- OCR 版面


@dataclass
class Line:
    text: str
    x: float
    y: float
    h: float
    score: float


def to_rows(items) -> list[list[Line]]:
    """把 OCR 方塊依垂直位置分成一列一列，每列由左到右排序。"""
    lines = []
    for box, text, score in items:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(Line(str(text).translate(_S2T), min(xs), (min(ys) + max(ys)) / 2, max(ys) - min(ys), float(score)))
    lines.sort(key=lambda l: l.y)
    rows: list[list[Line]] = []
    for ln in lines:
        if rows:
            last = rows[-1]
            ref = sum(l.y for l in last) / len(last)
            if abs(ln.y - ref) < 0.5 * max(ln.h, min(l.h for l in last)):
                last.append(ln)
                continue
        rows.append([ln])
    return [sorted(r, key=lambda l: l.x) for r in rows]


def row_text(row: list[Line]) -> str:
    return " ".join(l.text for l in row)


# ---------------------------------------------------------------- 欄位規則

_INV = re.compile(r"(?<![A-Z])([A-Z]{2})\s*[-－]?\s*([0-9OoDQIl|]{8})(?![0-9])")
_TAXID_LABEL = re.compile(r"統\s*一?\s*編\s*號?|統編")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PERIOD = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*[-－~～至]\s*(\d{1,2})\s*(?:月份?|份)")
_DATE = re.compile(r"(?<!\d)(\d{2,4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")


def _find_invoice_no(rows: list[list[Line]]) -> str | None:
    # 先看單一方塊，再看同一列相鄰兩個方塊接起來（字軌和號碼常被拆成兩塊，例如「UB」「08524853」）
    candidates = [l.text for row in rows for l in row]
    candidates += [a.text + b.text for row in rows for a, b in zip(row, row[1:])]
    for t in candidates:
        for m in _INV.finditer(t.replace(" ", "")):
            digits = m[2].translate(_DIGITISH)
            if digits.isdigit():
                return m[1] + digits
    return None


def _find_period(texts: list[str]) -> tuple[int, int, int] | None:
    for t in texts:
        m = _PERIOD.search(t.replace(" ", ""))
        if m:
            y, a, b = int(m[1]), int(m[2]), int(m[3])
            if 1 <= a <= 12 and b == a + 1:
                return y, a, b
    return None


def _find_date(texts: list[str], period, uncertain: list[str]) -> str | None:
    now = roc_now()
    for t in texts:
        t = _PERIOD.sub(" ", t.replace(" ", ""))  # 「112年11-12月份」是期別，不是日期
        for m in _DATE.finditer(t):
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                continue
            guessed = False
            if 2000 <= y <= 2100:
                ad = y
            elif 100 <= y <= now:
                ad = y + 1911
            elif y >= 100:  # 例如 2023 被讀成 123
                ad, guessed = 2000 + y % 100, True
            else:
                continue
            if period:
                py, a, b = period
                if ad - 1911 != py or mo not in (a, b):
                    if guessed:
                        continue
                    uncertain.append("date")
            elif guessed:
                uncertain.append("date")
            if guessed and "date" not in uncertain:
                uncertain.append("date")
            return f"{ad:04d}-{mo:02d}-{d:02d}"
    return None


def _ids_in(text: str) -> list[str]:
    s = text.replace(" ", "").translate(str.maketrans({"O": "0", "o": "0"}))
    return [m for m in re.findall(r"(?<!\d)(\d{8})(?!\d)", s) if is_valid_tax_id(m)]


def _find_tax_ids(texts: list[str], invoice_no: str | None, uncertain: list[str]):
    inv_digits = invoice_no[2:] if invoice_no else None
    seller = buyer = None
    unlabeled: list[str] = []
    for t in texts:
        ids = [i for i in _ids_in(t) if i != inv_digits]
        if not ids:
            continue
        if "買" in t:
            buyer = buyer or ids[0]
        elif _TAXID_LABEL.search(t) or "賣" in t:
            if seller is None:
                seller = ids[0]
            elif ids[0] != seller and buyer is None:
                buyer = ids[0]  # 第二個「統一編號」通常是買方
                uncertain.append("buyer_tax_id")
        else:
            unlabeled.extend(ids)
    unlabeled = [i for i in dict.fromkeys(unlabeled) if i not in (seller, buyer)]
    if seller is None and unlabeled:
        seller = unlabeled.pop(0)
        uncertain.append("seller_tax_id")
    return seller, buyer


def _amount(text: str) -> int | None:
    nums = [n for n in _NUM.findall(text.replace("$", " ")) if n.replace(",", "").replace(".", "").isdigit()]
    if not nums:
        return None
    try:
        return round(float(nums[-1].replace(",", "")))
    except ValueError:
        return None


_TOTAL_LABELS = [("總計", 0), ("總金額", 0), ("總額", 0), ("合計", 1), ("應收", 2), ("實收", 2), ("應付", 2), ("小計", 3)]
_SKIP = ("找零", "找錢", "找贖", "現金", "收現", "付款", "信用卡", "悠遊", "電話", "統編", "數量", "件", "項")


_CN_DIGITS = dict(zip("零〇一壹二貳兩三參叁四肆五伍六陸七柒八捌九玖", [0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9]))
_CN_SMALL = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
_CN_BIG = {"萬": 10_000, "億": 100_000_000}


def chinese_amount(text: str) -> int | None:
    """國字金額轉數字：「新台幣壹仟伍佰元整」→ 1500。認不得就回傳 None。"""
    s = re.sub(r"新[臺台]幣|NT\$?|[元圓整正\s]", "", text)
    s = re.sub(r"[角分].*$", "", s)
    if not s or not all(c in _CN_DIGITS or c in _CN_SMALL or c in _CN_BIG for c in s):
        return None
    total = section = 0
    digit = None
    for c in s:
        if c in _CN_DIGITS:
            digit = _CN_DIGITS[c]
        elif c in _CN_SMALL:
            section += (1 if digit is None else digit) * _CN_SMALL[c]
            digit = None
        else:
            total += (section + (digit or 0)) * _CN_BIG[c]
            section, digit = 0, None
    return total + section + (digit or 0)


def _find_total(rows: list[list[Line]], uncertain: list[str]) -> int | None:
    best: tuple[float, int] | None = None
    for i, row in enumerate(rows):
        t = row_text(row).replace(" ", "")
        # 收據常見寫法：「新台幣壹仟伍佰元整」、「NT$1,500」
        m = re.search(r"(?:NT\$|新[臺台]幣)\$?([\d,]+)", t)
        cn = re.search(r"新[臺台]幣([零〇一壹二貳兩三參叁四肆五伍六陸七柒八捌九玖十拾百佰千仟萬億]+)", t)
        v = int(m[1].replace(",", "")) if m and m[1].replace(",", "") else chinese_amount(cn[1]) if cn else None
        if v is not None and (best is None or best[0] > 1):
            best = (1, v)
        for label, pri in _TOTAL_LABELS:
            if label in t and not any(s in t for s in _SKIP):
                after = t.split(label, 1)[1]
                v = _amount(after)
                if v is None and i + 1 < len(rows):  # 金額換到下一列
                    v = _amount(row_text(rows[i + 1]))
                if v is not None and (best is None or pri < best[0] or (pri == best[0] and v > best[1])):
                    best = (pri, v)
                break
        # 「小計」常被讀成「小韵」「小部」「小新」：小 + 任一字 + 數字。有好幾個小計時取最後一個
        sub = re.fullmatch(r"小\S\s*\$?(-?\d[\d,]*)", t)
        if sub and "-" not in sub[1] and (best is None or best[0] >= 3):
            best = (3, int(sub[1].replace(",", "")))
        m = re.search(r"(\d[\d,]*)\s*TX|TX\s*\$?\s*(\d[\d,]*)", t)
        if m:
            v = int((m[1] or m[2]).replace(",", ""))
            if best is None or 1.5 < best[0]:
                best = (1.5, v)
    if best is None:
        return None
    if best[0] >= 2:
        uncertain.append("total")
    return best[1]


def _labeled_amount(texts: list[str], labels: tuple[str, ...], exclude: tuple[str, ...] = ()) -> int | None:
    for t in texts:
        c = t.replace(" ", "")
        for lb in labels:
            if lb in c and not any(x in c for x in exclude):
                v = _amount(c.split(lb, 1)[1])
                if v is not None:
                    return v
    return None


def _doc_type(full: str, has_invoice_no: bool) -> tuple[str, int | None]:
    f = full.replace(" ", "")
    if "電子發票證明聯" in f:
        return "e_invoice", 25
    if "電子計算機" in f:
        return "triplicate", 21
    if "收銀機" in f:
        if "扣抵聯" in f or "三聯" in f:
            return "triplicate_cash_register", 25
        return "duplicate_cash_register", 22
    if "統一發票" in f and ("扣抵聯" in f or "三聯" in f):
        return "triplicate", 21
    if "收據" in f and not has_invoice_no:
        return "receipt", None
    if has_invoice_no:
        return "duplicate_cash_register", 22
    return "receipt", None


def extract_from_ocr(items, default_deduct: int = 1) -> Result:
    rows = to_rows(items)
    texts = [row_text(r) for r in rows]
    full = "\n".join(texts)
    unc: list[str] = []
    r = Result()
    r.invoice_no = _find_invoice_no(rows)
    r.doc_type, r.format_code = _doc_type(full, bool(r.invoice_no))
    if r.doc_type == "duplicate_cash_register" and "收銀機" not in full:
        unc.append("format_code")
    period = _find_period(texts)
    r.date = _find_date(texts, period, unc)
    if r.date is None and period:
        r.notes.append(f"只讀到期別 {period[0]}年{period[1]}-{period[2]}月，日期請手動補")
    r.seller_tax_id, r.buyer_tax_id = _find_tax_ids(texts, r.invoice_no, unc)
    r.total = _find_total(rows, unc)
    r.sales_amount = _labeled_amount(texts, ("銷售額", "銷售金額", "未稅"), exclude=("總計",))
    r.tax = _labeled_amount(texts, ("營業稅", "稅額", "稅金"), exclude=("免稅", "未稅", "含稅"))
    if "免稅" in full.replace(" ", "") and r.tax is None:
        r.tax_type = 3
    r.deduct_code = 0 if r.doc_type == "receipt" else default_deduct
    for f in ("invoice_no", "date", "seller_tax_id", "total"):
        if getattr(r, f) is None and f not in unc:
            unc.append(f)
    r.uncertain = list(dict.fromkeys(unc))
    if r.doc_type == "receipt":
        return r  # 收據沒有營業稅，不回推稅額；總計仍會算進「進項總金額」
    return fill_amounts(r)


# ---------------------------------------------------------------- 匯出

CSV_COLUMNS = [
    ("file", "檔案"), ("period", "申報期別"), ("format_code", "格式代號"), ("date", "發票日期"),
    ("invoice_no", "發票號碼"), ("seller_tax_id", "賣方統編"), ("seller_name", "賣方名稱"),
    ("buyer_tax_id", "買方統編"), ("sales_amount", "銷售額"), ("tax", "稅額"), ("total", "總計"),
    ("tax_type", "課稅別"), ("deduct_code", "扣抵代號"), ("deductible", "可扣抵"),
    ("source", "來源"), ("check", "需要確認"), ("note", "備註"),
]
FIELD_NAMES = {
    "invoice_no": "發票號碼", "date": "日期", "seller_tax_id": "賣方統編", "buyer_tax_id": "買方統編",
    "total": "總計", "tax": "稅額", "format_code": "格式代號",
}


def to_csv(rows: list[tuple[str, Result]], company_tax_id: str = "") -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([h for _, h in CSV_COLUMNS])
    for fname, r in rows:
        errors, ok, reason = validate(r, company_tax_id)
        check = [FIELD_NAMES.get(f, f) for f in dict.fromkeys(list(r.uncertain) + list(errors))]
        rec = r.as_dict() | {
            "file": fname, "period": filing_period(r.date), "deductible": "Y" if ok else "N",
            "deduct_code": r.deduct_code if ok else "", "check": "、".join(check),
            "note": "；".join([*errors.values(), *([reason] if reason else []), *r.notes]),
        }
        w.writerow(["" if rec.get(k) is None else rec[k] for k, _ in CSV_COLUMNS])
    return "﻿" + buf.getvalue()


def summarize(rows: list[Result], company_tax_id: str = "") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        p = filing_period(r.date) or "日期未知"
        s = out.setdefault(p, {"count": 0, "non_deductible": 0, "grand_total": 0, 1: [0, 0], 2: [0, 0]})
        s["count"] += 1
        s["grand_total"] += r.total or 0  # 進項總金額（含不得扣抵憑證及普通收據）
        _, ok, _ = validate(r, company_tax_id)
        if not ok:
            s["non_deductible"] += 1
            continue
        k = 2 if r.deduct_code == 2 else 1
        s[k][0] += r.sales_amount or 0
        s[k][1] += r.tax or 0
    return out
