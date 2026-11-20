# invoice_ocr（進項發票本機辨識）

把發票照片丟進去，在本機用 PaddleOCR（PP-OCRv5）辨識，輸出營業稅 401 申報要用的欄位 CSV。
不需要 API key，照片不會上傳。

## 網頁介面（拖圖片進去）

```bash
uv run invoice_ocr/app.py          # 自動打開 http://127.0.0.1:8765
```

把照片拖進瀏覽器就會辨識，結果可以直接在卡片上改（黃框是規則猜的、紅框是檢查沒過），
上方依申報期別即時加總，按「匯出 CSV」下載。資料存在瀏覽器 localStorage，重新整理不會不見。
伺服器只綁 127.0.0.1，`--port` 換 port、`--no-browser` 不自動開瀏覽器。
規則、驗證、CSV 都走 Python（`/api/analyze`、`/api/check`、`/api/csv`），頁面在 `ui.html`。

## 指令列

```bash
uv run invoice_ocr/invoice_ocr.py ~/Desktop/發票/ -o 進項.csv --company 12345678
uv run invoice_ocr/invoice_ocr.py IMG_0001.HEIC IMG_0002.HEIC --debug   # 印出 OCR 讀到的每一列
```

| 參數 | 說明 |
|---|---|
| `paths` | 圖片檔或資料夾（會往下找 jpg/png/heic/webp…） |
| `-o` | 輸出 CSV，預設 `進項發票.csv`（UTF-8 BOM，Excel 直接開） |
| `--company` | 貴公司統編，買方統編不同會標出來 |
| `--deduct` | 預設扣抵代號：1 進貨及費用（預設）、2 固定資產 |
| `--json` | 另外輸出完整結果 JSON |
| `--debug` | 印出 OCR 每一列文字，規則抓錯時用來看原因 |

第一次執行會從 jsDelivr 下載 PP-OCRv5 mobile 模型（約 21 MB，npm 套件
`pdfmarkdown-ppocrv5-models`，Apache-2.0）到 `~/.cache/invoice_ocr/`，有驗 sha256。
原始字典第二行多一個空行會讓辨識整個錯位，程式會自動修正成 `dict_fixed.txt`。

## 流程

1. 先找電子發票左邊的 QR Code（zxing-cpp），有的話直接解碼，100% 準確。
2. 沒有 QR Code → RapidOCR（PaddleOCR 模型跑在 onnxruntime 上）辨識文字，依方塊位置排成一列一列。
3. `invoice_fields.py` 用規則抓欄位：
   - 發票號碼：2 碼英文 + 8 碼數字，字軌和號碼被拆成兩個方塊也會接起來，號碼裡的 O 當 0
   - 日期：西元或民國；「112年11-12月份」是期別不是日期；年份讀壞（2023 → 123）時用期別校正並標成需要確認
   - 統編：有「統編／統一編號」標籤的是賣方、有「買」的是買方，都要過檢查碼
   - 總計：總計 > 合計 > `437TX` > 應收／實收；收據看「新台幣壹仟伍佰元整」「NT$1,500」
   - 格式代號：收銀機 + 扣抵聯 → 25、收銀機 → 22、電子計算機 → 21、收據 → 不可扣抵
4. 抓不到或用猜的欄位會列在 CSV 的「需要確認」欄。

## 限制

- 一張照片只放一張發票，疊在一起的會互相干擾。
- 褪色的感熱紙、手寫收據準確度明顯較差，結果一定要人工看過。
- 二聯式發票沒印買方統編就不能扣抵，工具會標「不可扣抵」，但仍算進「進項總金額」。

測試：`python -m pytest invoice_ocr/tests`
