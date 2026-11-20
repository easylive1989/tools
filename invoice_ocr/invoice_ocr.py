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
"""進項發票本機辨識（PaddleOCR PP-OCRv5，給營業稅 401 申報用）。

用法：
    uv run invoice_ocr/invoice_ocr.py 照片1.jpg 照片2.heic 資料夾/ -o 進項.csv
    uv run invoice_ocr/invoice_ocr.py ~/Desktop/發票 --company 12345678 --debug

電子發票先讀左邊的 QR Code；沒有 QR Code 的（收銀機發票、三聯式、收據）用
PaddleOCR 辨識文字，再用規則抓出發票號碼、日期、統編、金額。一張照片只放一張發票。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
from invoice_fields import (  # noqa: E402
    Result, classify_qr, extract_from_ocr, filing_period, parse_einvoice, summarize, to_csv, validate,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff"}

# PP-OCRv5 mobile 模型（Apache-2.0），經 npm 套件 pdfmarkdown-ppocrv5-models 由 jsDelivr 提供
_CDN = "https://cdn.jsdelivr.net/npm/pdfmarkdown-ppocrv5-models@1.0.0/"
MODELS = {
    "det.ort": (_CDN + "detection/PP-OCRv5_mobile_det_infer.ort", "30acfc4e21f2a23669d01a75aaeb92190f96874613108a0f7086bed264420abc"),
    "rec.onnx": (_CDN + "recognition/PP-OCRv5_mobile_rec_infer.onnx", "d253c3cbee6e507828a5271a30ab0ec8ae7c2a99d0cc8e6f844fe380809d22b3"),
    "dict.txt": (_CDN + "recognition/ppocrv5_dict.txt", "9dfc80c50b6cb07399a47a7cf25d11db475fb4ad0e1fc96b2eff6467c8166ff3"),
}
CACHE = Path.home() / ".cache" / "invoice_ocr"


def ensure_models() -> dict[str, Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (url, sha) in MODELS.items():
        p = CACHE / name
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            print(f"下載模型 {name} …", file=sys.stderr)
            tmp = p.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            if hashlib.sha256(tmp.read_bytes()).hexdigest() != sha:
                tmp.unlink()
                raise SystemExit(f"{name} 下載內容的 checksum 不對，請稍後再試")
            tmp.replace(p)
        paths[name] = p
    # 原始字典第二行是多出來的空行，會讓辨識結果整個錯位，要拿掉
    fixed = CACHE / "dict_fixed.txt"
    if not fixed.exists():
        lines = paths["dict.txt"].read_text(encoding="utf-8").split("\n")
        fixed.write_text("\n".join(l for l in lines if l != ""), encoding="utf-8")
    paths["dict"] = fixed
    return paths


_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr import RapidOCR

        m = ensure_models()
        _ocr = RapidOCR(params={
            "Global.use_cls": False,
            "Global.log_level": "warning",
            "Det.model_path": str(m["det.ort"]),
            "Rec.model_path": str(m["rec.onnx"]),
            "Rec.rec_keys_path": str(m["dict"]),
        })
    return _ocr


def load_image(src) -> np.ndarray:
    """讀圖片：可以是路徑或 bytes（HEIC 也行），依 EXIF 轉正。"""
    import io

    from pillow_heif import register_heif_opener

    register_heif_opener()
    f = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    img = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
    return np.asarray(img)


def read_qr(img: np.ndarray) -> str | None:
    import zxingcpp

    for b in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode):
        if classify_qr(b.text) == "left":
            return b.text
    return None


def analyze(img: np.ndarray, deduct: int = 1) -> tuple[Result, list[str]]:
    """辨識一張圖片，回傳 (結果, OCR 讀到的每一列文字)。電子發票走 QR Code，沒有 OCR 文字。"""
    from invoice_fields import row_text, to_rows

    left = read_qr(img)
    if left:
        r = parse_einvoice(left)
        r.deduct_code = deduct
        return r, []
    out = get_ocr()(img[:, :, ::-1])  # RapidOCR 吃 BGR
    items = list(zip(out.boxes, out.txts, out.scores)) if out.txts else []
    return extract_from_ocr(items, default_deduct=deduct), [row_text(row) for row in to_rows(items)]


def process(path: Path, deduct: int, debug: bool) -> Result:
    r, lines = analyze(load_image(path), deduct)
    if debug and lines:
        print(f"  ── OCR {path.name}", file=sys.stderr)
        for line in lines:
            print("   ", line, file=sys.stderr)
    return r


def _walk_images(root: Path) -> list[Path]:
    """os.walk 版的 rglob：pathlib 的 rglob 遇到權限錯誤會安靜地當成空資料夾，這裡要把它講出來。"""
    import os

    found: list[Path] = []
    denied: list[str] = []
    for dirpath, _dirs, names in os.walk(root, onerror=lambda e: denied.append(e.filename)):
        found += [Path(dirpath) / n for n in names if Path(n).suffix.lower() in IMAGE_EXTS and not n.startswith(".")]
    for d in denied:
        print(
            f"沒有權限讀取 {d}。\n"
            "  macOS 要允許你的終端機 App 存取這個位置：系統設定 → 隱私權與安全性 → 檔案與資料夾\n"
            "  （或「完整磁碟取用權限」），把終端機 App 的「桌面／文件／下載項目」打開後重開終端機。\n"
            "  也可以先把照片搬到其他資料夾，例如 ~/發票。",
            file=sys.stderr,
        )
    return sorted(found)


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        p = p.expanduser()
        if p.is_dir():
            files += _walk_images(p)
        elif p.exists():
            files.append(p)
        else:
            print(f"找不到 {p}", file=sys.stderr)
    return files


def fmt(v) -> str:
    return "—" if v is None else f"{v:,}" if isinstance(v, int) else str(v)


def main() -> None:
    ap = argparse.ArgumentParser(description="進項發票本機辨識（PaddleOCR），輸出 401 申報用 CSV")
    ap.add_argument("paths", nargs="+", help="圖片檔或資料夾")
    ap.add_argument("-o", "--output", default="進項發票.csv", help="輸出 CSV（預設：進項發票.csv）")
    ap.add_argument("--json", help="另外輸出完整結果 JSON")
    ap.add_argument("--company", default="", help="貴公司統編，用來檢查買方統編")
    ap.add_argument("--deduct", type=int, choices=[1, 2], default=1, help="扣抵代號：1 進貨及費用、2 固定資產")
    ap.add_argument("--debug", action="store_true", help="印出 OCR 讀到的每一列文字")
    args = ap.parse_args()

    files = collect(args.paths)
    if not files:
        raise SystemExit("沒有可以處理的圖片")
    results: list[tuple[str, Result]] = []
    seen: dict[str, str] = {}
    t0 = time.time()
    for i, f in enumerate(files, 1):
        try:
            r = process(f, args.deduct, args.debug)
        except Exception as e:  # 單張失敗不要中斷整批
            print(f"[{i}/{len(files)}] {f.name}  失敗：{e}", file=sys.stderr)
            continue
        if r.invoice_no and r.invoice_no in seen:
            r.notes.append(f"和 {seen[r.invoice_no]} 重複")
        elif r.invoice_no:
            seen[r.invoice_no] = f.name
        errors, ok, reason = validate(r, args.company)
        flag = "✓" if not errors and not r.uncertain else "⚠"
        print(
            f"[{i}/{len(files)}] {flag} {f.name}  {r.format_code or '收據'}  {fmt(r.invoice_no)}  {fmt(r.date)}"
            f"  賣方 {fmt(r.seller_tax_id)}  買方 {fmt(r.buyer_tax_id)}  總計 {fmt(r.total)}  稅 {fmt(r.tax)}"
            + ("" if ok else f"  （{reason}）")
        )
        results.append((str(f.name), r))

    out = Path(args.output).expanduser()
    out.write_text(to_csv(results, args.company), encoding="utf-8")
    if args.json:
        Path(args.json).expanduser().write_text(
            json.dumps([{"file": n, **r.as_dict(), "period": filing_period(r.date)} for n, r in results],
                       ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n完成 {len(results)}/{len(files)} 張，{time.time() - t0:.1f} 秒 → {out}")
    for period, s in sorted(summarize([r for _, r in results], args.company).items()):
        print(f"  {period}：{s['count']} 張（不可扣抵 {s['non_deductible']}）"
              f"  進貨及費用 銷售額 {s[1][0]:,} 稅額 {s[1][1]:,}"
              + (f"  固定資產 銷售額 {s[2][0]:,} 稅額 {s[2][1]:,}" if s[2][0] else "")
              + f"  進項總金額 {s['grand_total']:,}")
    n_check = sum(1 for _, r in results if r.uncertain or validate(r, args.company)[0])
    if n_check:
        print(f"  有 {n_check} 張需要人工確認，看 CSV 的「需要確認」欄")


if __name__ == "__main__":
    main()
