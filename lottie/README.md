# Video to Lottie

將影片轉換為 Lottie JSON 動畫檔。從影片中擷取指定數量的幀，編碼為 base64 JPEG 後打包成 Lottie 格式。

參考來源：[Observable - Video to Lottie](https://observablehq.com/@forresto/video-to-lottie)

## 前置需求

```bash
pip install opencv-python Pillow
```

## 使用方式

```bash
python lottie/video_to_lottie.py input.mp4

python lottie/video_to_lottie.py input.mp4 -o out.lottie.json --frames 20 --scale 0.3 --quality 80 --start 1.0 --end 5.0
```

## 參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `input` | （必填） | 輸入影片檔案 |
| `-o`, `--output` | `<input>.lottie.json` | 輸出路徑 |
| `--frames` | `30` | 擷取幀數 |
| `--scale` | `0.5` | 輸出縮放比例（0–1） |
| `--quality` | `80` | JPEG 品質（1–95） |
| `--start` | `0.0` | 剪輯起始秒數 |
| `--end` | 影片結尾 | 剪輯結束秒數 |
| `--fps` | 自動 | 輸出幀率，控制播放速度 |

## 播放時長

輸出動畫時長 = `frames / fps`。

- 預設 fps 自動計算，播放時長等於原片段長度
- `--fps 10`：30 幀播 3 秒
- `--fps 2`：30 幀播 15 秒（慢動作）

## 預覽

輸出的 `.lottie.json` 可上傳至 [LottieFiles Preview](https://lottiefiles.com/preview) 預覽。
