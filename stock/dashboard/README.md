# Stock Dashboard

## VPS 環境變數

`stock-dashboard.service` 會讀取 `/opt/stock-dashboard/backend/.env`。新增/更新環境變數的標準步驟：

```bash
ssh root@$VPS_HOST
echo 'FOO=bar' >> /opt/stock-dashboard/backend/.env
systemctl restart stock-dashboard
```

## 券商分點功能（已停用）

個股詳細頁的「前五大買超券商」原本接 FinMind 的 `TaiwanStockTradingDailyReport`，
但該 dataset 已改為 Sponsor 會員專屬（free / register 等級會收到 400 「Your level is register」），
因此目前功能停用：

- 前端 `stock.html` 不再呼叫 `loadBrokers()`，券商卡片不會顯示
- 後端 `/api/stocks/{ticker}/brokers` 短路回空 (`ok: false, top_brokers: []`)
- `fetchers/broker.py`、`db.py` 的 broker 函式、`broker_daily` table 全部保留
- VPS `.env` 中的 `FINMIND_TOKEN` 也保留

未來要恢復功能：升級 FinMind Sponsor → 改 `fetchers/broker.py` 為「逐日呼叫」
（dataset 規定 single day per request）→ 還原 `app.py` 的 endpoint 實作 →
還原 `stock.html` 的 `loadBrokers()` 呼叫。

## DB Migrations

Schema 由 `backend/db/runner.py` 管理。新增 schema 變更：

1. 建檔 `backend/db/migrations/NNNN_<snake_name>.sql`（流水號，4 位數）
2. 服務啟動（`init_db()`）時 runner 會自動套用未執行的 migration；已套用版本記錄在 `schema_migrations` 表
3. Forward-only：已 push 到 master 的 migration 不可修改，要修正請寫新 migration

VPS 上原有的 legacy DB 透過 runner 的 baseline 機制（見 `MIGR-T4`）匯入 ——
runner 啟動時偵測到「已有 legacy table、無 `schema_migrations`」即把目前所有
migration 標記為已套用，不重跑 SQL。

## API Authentication (Bootstrap)

After deploy lands, the API enforces `Authorization: Bearer <token>` on every endpoint. Bootstrap the first token:

```bash
# 1. Add the ops Discord webhook (one-time)
ssh root@$VPS_HOST 'echo "DISCORD_OPS_WEBHOOK_URL=https://discord.com/api/webhooks/..." >> /opt/stock-dashboard/backend/.env'
ssh root@$VPS_HOST 'systemctl restart stock-dashboard'

# 2. Issue your first token
ssh root@$VPS_HOST 'cd /opt/stock-dashboard/backend && .venv/bin/python -m scripts.issue_token issue --label paul-laptop'
# → Copy the printed sd_... token

# 3. Open https://paul-learning.dev/ and paste the token into the prompt
```

The token is stored in browser `localStorage`. The 🔓 重新登入 button on the dashboard header clears it.

Add `DISCORD_OPS_WEBHOOK_URL` as a GitHub Secret so future deploys re-populate it.

CLI commands:

```bash
python -m scripts.issue_token issue --label <name>            # default 365 days
python -m scripts.issue_token issue --label <name> --no-expiry
python -m scripts.issue_token list
python -m scripts.issue_token revoke <id>
```
