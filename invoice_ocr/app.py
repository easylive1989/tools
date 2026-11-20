# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "rapidocr>=3.4",
#     "onnxruntime>=1.18",
#     "zxing-cpp>=2.2",
#     "pillow>=10",
#     "pillow-heif>=0.16",
#     "numpy",
# ]
# ///
"""進項發票辨識的本機網頁介面：把圖片拖進瀏覽器，用 PaddleOCR 解析。

用法：
    uv run invoice_ocr/app.py            # 開 http://127.0.0.1:8765 並自動打開瀏覽器
    uv run invoice_ocr/app.py --port 9000 --no-browser

只綁 127.0.0.1，照片不會離開這台電腦。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import traceback
import webbrowser
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from invoice_fields import Result, filing_period, summarize, to_csv, validate  # noqa: E402
from invoice_ocr import analyze, get_ocr, load_image  # noqa: E402

MAX_UPLOAD = 40 * 1024 * 1024
_ocr_lock = threading.Lock()
_state = {"ready": False, "error": None}

_RESULT_FIELDS = {f.name for f in fields(Result)}
_INT_FIELDS = {"format_code", "sales_amount", "tax", "total", "tax_type", "deduct_code"}


def to_result(d: dict) -> Result:
    """把前端送回來（可能被使用者改過）的資料轉回 Result。"""
    kw = {}
    for k, v in d.items():
        if k not in _RESULT_FIELDS:
            continue
        if k in _INT_FIELDS:
            v = None if v in ("", None) else int(round(float(str(v).replace(",", ""))))
        elif k in ("uncertain", "notes"):
            v = list(v or [])
        elif isinstance(v, str):
            v = v.strip() or None
        kw[k] = v
    r = Result(**kw)
    if r.invoice_no:
        r.invoice_no = r.invoice_no.upper().replace("-", "").replace(" ", "")
    if r.tax_type is None:
        r.tax_type = 1
    if r.deduct_code is None:
        r.deduct_code = 1
    if r.format_code is None:
        r.doc_type = "receipt"
    elif r.doc_type == "receipt":
        r.doc_type = "invoice"
    return r


def jpeg_data_url(img, max_side: int, quality: int = 80) -> str:
    """把辨識用的圖縮成 JPEG data URL 給前端預覽（Chrome 不能直接顯示 HEIC）。"""
    import base64
    import io

    from PIL import Image

    im = Image.fromarray(img)
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def check(r: Result, company: str) -> dict:
    errors, ok, reason = validate(r, company)
    return {"errors": errors, "deductible": ok, "reason": reason, "period": filing_period(r.date)}


def warm_up() -> None:
    try:
        get_ocr()
        _state["ready"] = True
    except BaseException as e:  # 模型下載失敗之類，讓前端顯示
        _state["error"] = str(e)
        traceback.print_exc()


class Handler(BaseHTTPRequestHandler):
    server_version = "invoice-ocr"

    def log_message(self, fmt, *args):  # 安靜一點，只印錯誤
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("檔案太大（上限 40 MB）")
        return self.rfile.read(n)

    def _same_origin(self) -> bool:
        # 只接受從這個頁面送來的請求，避免其他網站對 localhost 亂打
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        return origin is None or origin in (f"http://{host}",)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "ui.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/status":
            self._json(_state)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._same_origin():
            return self._send(403, b"forbidden", "text/plain")
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path == "/api/analyze":
                deduct = int(q.get("deduct", ["1"])[0])
                company = q.get("company", [""])[0]
                img = load_image(self._body())
                with _ocr_lock:
                    r, lines = analyze(img, deduct)
                self._json({
                    "record": r.as_dict(), "lines": lines, **check(r, company),
                    "thumb": jpeg_data_url(img, 360, 70), "preview": jpeg_data_url(img, 1600, 82),
                })
            elif url.path == "/api/check":
                data = json.loads(self._body() or b"{}")
                company = data.get("company", "")
                rs = [to_result(d) for d in data.get("records", [])]
                summary = summarize(rs, company)
                self._json({
                    "checks": [check(r, company) for r in rs],
                    "summary": {p: {"count": s["count"], "non_deductible": s["non_deductible"],
                                    "grand_total": s["grand_total"], "expense": s[1], "asset": s[2]}
                                for p, s in sorted(summary.items(), reverse=True)},
                })
            elif url.path == "/api/csv":
                data = json.loads(self._body() or b"{}")
                rows = [(d.get("file", ""), to_result(d)) for d in data.get("records", [])]
                name = data.get("filename") or "進項發票.csv"
                self._send(200, to_csv(rows, data.get("company", "")).encode("utf-8"), "text/csv; charset=utf-8",
                           {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as e:
            traceback.print_exc()
            self._json({"error": f"{type(e).__name__}: {e}"}, 400)


def main() -> None:
    ap = argparse.ArgumentParser(description="進項發票辨識（本機網頁介面）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="不要自動打開瀏覽器")
    args = ap.parse_args()

    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("找不到可以用的 port")
    url = f"http://127.0.0.1:{server.server_port}/"
    threading.Thread(target=warm_up, daemon=True).start()
    print(f"進項發票辨識：{url}（Ctrl+C 結束）")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已結束")


if __name__ == "__main__":
    main()
