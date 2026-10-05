# 智選股截圖 → Notion

收盤後把智選股 App「自選」頁的截圖貼到 Discord 頻道（`1556684804731179070`），一則訊息可以附多張。
VPS 每 5 分鐘檢查一次：用 Codex CLI 讀出股票名稱，用證交所／櫃買中心官方行情查代號與當天收盤價（興櫃用最後成交價），
寫入 Notion「智選股當天入場」。選股日期：台灣時間 13:30 以後貼的算當天，13:30 以前貼的（例如半夜過後）算前一個交易日。
09:00–13:30 之間貼前一天的圖時，興櫃行情可能已換成當天，會得到 ❌，請改成手動補。

## 訊息上的 emoji

| emoji | 意思 |
|---|---|
| ✅ | 全部寫入（已存在的同日同代號會略過，不重複寫） |
| ⚠️ | 部分寫入；回覆裡列出對不到或當天沒成交的名稱，請手動補 |
| ❌ | 沒有寫入；回覆說明原因（沒辨識到股票、不是交易日、重試 3 次仍失敗等） |

官方行情還沒更新到貼圖當天時會自動等待，最多 12 小時。工具只處理上線之後的新訊息。

## 部署與除錯

push 到 `master` 且改到 `stock_pick/`、`common/discord.py` 或 `common/notion.py` 時，
`Deploy Stock Pick` workflow 會跑測試並部署到 oracle-arm 的 `/opt/stock-pick`（`stock-pick.timer`）。
沿用 GitHub secrets：`VPS_HOST`、`VPS_SSH_KEY`、`DISCORD_BOT_TOKEN`、`NOTION_SECRET`。

- 看執行紀錄：`ssh oracle-arm 'journalctl -u stock-pick.service -n 50 --no-pager'`
- 手動跑一次：`ssh oracle-arm 'sudo systemctl start stock-pick.service'`
- 處理進度：`/opt/stock-pick/stock_pick/state.json`（不進 Git）
