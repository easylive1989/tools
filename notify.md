# notify.py 使用說明

macOS 桌面通知發送工具，基於 `terminal-notifier`。

## 前置需求

```bash
brew install terminal-notifier
```

## 命令列用法

```bash
# 基本通知
python notify.py "Hello World"

# 自訂標題
python notify.py "內容" -t "標題"

# 點擊通知時開啟指定 App
python notify.py "開啟 Safari" -a com.apple.Safari

# 點擊通知時開啟 URL
python notify.py "查看連結" -o "https://example.com"
```

## 參數

| 參數 | 說明 |
|---|---|
| `message` | 通知內容（必填） |
| `-t`, `--title` | 通知標題，預設 `Notification` |
| `-a`, `--activate` | 點擊時啟動的 App Bundle ID |
| `-o`, `--open` | 點擊時開啟的 URL |

## 作為模組使用

```python
from notify import send_notification

send_notification("完成", title="任務通知")
send_notification("點我", open_url="https://example.com")
```
