# Stock Dashboard Design Spec

**Date:** 2026-04-28  
**Status:** Approved

## Overview

Replace the existing Discord stock notification bot with a web-based market dashboard. The dashboard displays key Taiwan market indicators with historical charts, and lets the user manage a custom watchlist of stocks, ETFs, and crypto.

## Architecture

| Layer | Technology | Location |
|---|---|---|
| Frontend | Static HTML + Chart.js (CDN) | GitHub Pages `paul-learning.dev/stock` |
| Backend | FastAPI + APScheduler + SQLite | VPS `api.paul-learning.dev` |

The frontend is a single `index.html` deployed via GitHub Actions. The backend is a standalone FastAPI process on the existing VPS (already HTTPS via nginx + Let's Encrypt).

## Frontend

- Single `index.html` with vanilla JS — no build step, no Node.js required
- Charts rendered by **Chart.js** loaded from CDN
- API base URL hardcoded as `const API_BASE = 'https://api.paul-learning.dev'` at the top of `index.html`
- Polls `GET /api/dashboard` and `GET /api/stocks` every 60 seconds for live updates
- Time range selector (1M, 3M, 6M, 1Y, 3Y) — triggers re-fetch of history endpoints
- Stock watchlist management: add via text input, delete via ✕ button
- Each chart shows crosshair + tooltip (date + value) on hover, handled natively by Chart.js

**Layout (5 indicator cards in a 3-column grid, then watchlist below):**
1. 加權指數 — line chart + current value + % change
2. MM 恐懼與貪婪指數 — gauge (0–100) + line chart
3. 台股融資餘額 — line chart + current value (億元)
4. 國發會景氣指標 — traffic light + score + line chart
5. 台幣兌美金 — line chart + current rate
6. 自選股票 / ETF / 虛擬幣 — table with add/delete

Each card has a manual refresh button that calls `POST /api/refresh/{indicator}`.

## Backend

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Current values for all 5 indicators |
| `GET` | `/api/history/{indicator}` | Historical data for chart (`?range=1M\|3M\|6M\|1Y\|3Y`) |
| `GET` | `/api/stocks` | Watchlist tickers with latest price, change, change% |
| `POST` | `/api/stocks` | Add ticker `{"ticker": "2330.TW"}` |
| `DELETE` | `/api/stocks/{ticker}` | Remove ticker from watchlist |
| `POST` | `/api/refresh/{indicator}` | Manually trigger data refresh for one indicator |

`indicator` values: `taiex`, `fear_greed`, `margin`, `ndc`, `fx`, `stocks`

CORS: allow origin `https://paul-learning.dev`.

### Data Sources & Update Schedule

| Indicator | Source | Schedule |
|---|---|---|
| 加權指數 (`taiex`) | `yfinance` ticker `^TWII` | Every 15 min, Mon–Fri 09:00–13:30 TST |
| 台幣兌美金 (`fx`) | `yfinance` ticker `TWD=X` | Every 15 min, weekdays |
| 自選股 (`stocks`) | `yfinance` (per ticker) | Every 15 min, weekdays |
| MM 恐懼貪婪指數 (`fear_greed`) | Scrape macromicro.me | Daily 08:00 TST |
| 台股融資餘額 (`margin`) | TWSE OpenAPI | Daily 18:00 TST (after settlement) |
| 國發會景氣指標 (`ndc`) | NDC open data API | Monthly, 1st of month 09:00 TST |

### Storage (SQLite)

**`indicator_snapshots`** — time-series data for all 5 indicators
```
id, indicator, timestamp, value, extra_json
```

**`watched_stocks`** — user-managed watchlist
```
id, ticker, added_at
```

**`stock_snapshots`** — price history for watchlist tickers
```
id, ticker, timestamp, price, change, change_pct, currency
```

Historical data is retained for 3 years. The `/api/history` endpoint queries this table and returns the appropriate slice based on `range`.

### Scheduling (APScheduler)

- Uses `BackgroundScheduler` (in-process, no Celery/Redis needed)
- Jobs defined in `scheduler.py`, registered at app startup
- Each job writes to SQLite; API reads from SQLite — no blocking

## Deployment

**Backend (VPS):**
- `stock/dashboard/` subdirectory within this repo
- Runs as a systemd service (`stock-dashboard.service`)
- nginx reverse-proxies `api.paul-learning.dev` → `localhost:8000`

**Frontend (GitHub Pages):**
- `stock/dashboard/frontend/index.html`
- Deployed by a new GitHub Actions workflow `deploy-stock-dashboard.yml` (separate from the existing `deploy-pages.yml` which handles `travel/`)
- Served at `paul-learning.dev/stock`

## Out of Scope

- Authentication / login
- Push notifications
- Real-time WebSocket updates (polling every 60s is sufficient)
- Mobile-native app
