# Stock Dashboard

## VPS 環境變數

`stock-dashboard.service` 會讀取 `/opt/stock-dashboard/backend/.env`。新增/更新環境變數的標準步驟：

```bash
ssh root@$VPS_HOST
echo 'FOO=bar' >> /opt/stock-dashboard/backend/.env
systemctl restart stock-dashboard
```

## FinMind Token（券商分點功能用）

個股詳細頁的「前五大買超券商」資料來自 FinMind 的 `TaiwanStockTradingDailyReport`。

- 不設 token：免費，**每小時 300 次** request
- 設 token：免費註冊，**每小時 600 次** request

如果 watchlist 股票數 × 每天訪問次數會超過免費配額，建議設 token：

1. 到 <https://finmindtrade.com/> 註冊帳號並驗證信箱
2. 登入後在「會員中心」取得 API Token
3. 寫入 VPS 的 .env：
   ```bash
   ssh root@$VPS_HOST
   echo 'FINMIND_TOKEN=你的token' >> /opt/stock-dashboard/backend/.env
   systemctl restart stock-dashboard
   ```
4. 確認服務正常：
   ```bash
   systemctl status stock-dashboard --no-pager
   curl -s https://api.paul-learning.dev/api/stocks/2330.TW/brokers?days=20 | jq .as_of
   ```

未設 token 時功能仍可運作，只是 rate limit 較緊。
