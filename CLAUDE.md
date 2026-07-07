# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

A collection of independent personal automation tools, mostly Python scripts. Each subdirectory is a self-contained tool. There is no monorepo build system — tools are run directly.

## Shared Utilities (`common/`)

All cross-tool utilities live here. Import from `common.*` rather than duplicating:

- `common/notify.py` — `send_notification()` (macOS terminal-notifier), `send_to_discord(webhook_url, payload)`
- `common/notion.py` — `NotionApi` class wrapping the Notion REST API
- `common/gemini.py` — `GeminiClient(model_name, use_cli)` with `generate(prompt, timeout)` — handles CLI/API switching, PATH augmentation for Homebrew, ANSI stripping, and tenacity retry

Scripts in subdirectories add the repo root to `sys.path` so `from common.X import Y` works:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

## translate (隨身翻譯 + 檔案翻譯)

SwiftUI app (`translate/translator.swift`) for selection-based translation, plus a
file-translation button that delegates to `translate/file_translator.py` —
a `uv run` script that translates `.docx` / `.pdf` via the local `gemini` CLI
and writes `<stem>_translated.docx` next to the source.

## GitHub Actions

Active workflows (triggered on schedule + `workflow_dispatch`):
- `deploy-pages.yml` — builds the travel apps and deploys to GitHub Pages (custom domain `tools.paul-learning.dev`)
- `update-read-later.yml` — polls the read_later Discord channel and rebuilds `read_later/feed.xml` (cron: every 2h); commits state back
- `update-eat-later.yml` — polls the eat_later Discord channel, extracts restaurant info via Gemini, writes to Notion (cron: every 2h); commits `eat_later/state.json` back
- `deploy-anthropic-translator.yml` — deploys the Anthropic update translator Cloudflare Worker (cron: every 5 min)

The stock dashboard moved to a separate repo: <https://github.com/easylive1989/publixia> (`stock.paul-learning.dev`).

Required secrets: `NOTION_SECRET`, `DISCORD_*_WEBHOOK_URL`, `GOOGLE_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DISCORD_BOT_TOKEN`, `DISCORD_READ_LATER_CHANNEL_ID`, `GEMINI_API_KEY`.

## Environment Variables

Scripts read secrets directly from environment (no `.env` loading at root level):

| Variable | Used by |
|---|---|
| `DISCORD_BOT_TOKEN`, `NOTION_SECRET`, `GOOGLE_API_KEY` | `eat_later/eat_later.py` (channel id is hard-coded) |

## Secrets and Sensitive Data

**永遠不要把以下資訊 commit 或 push 到 GitHub**(包含 commit message、code、註解、test fixture、文件範例、log 輸出、任何會進 git history 的地方):

- API token / key(FinMind, OpenAI, Google API, Notion 等)
- Webhook URL(Discord、Slack 等)
- VPS hostname / IP、SSH 私鑰、SSH cert
- 任何 `.env` 檔內容
- 其他憑證、密碼

正確放法:
- 本機開發 → 環境變數或 `.env`(`.env` 已在 `.gitignore`)
- CI / GitHub Actions → GitHub Secrets,workflow 中以 `${{ secrets.X }}` 引用
- VPS → `/opt/<service>/.env`,由 deploy workflow 從 GitHub Secrets 寫入

對話中提到的 secret 也不要再寫進 git history。如果不小心 commit 了,**rotate / 撤銷該 secret**(force-push 不能消除已複製到別處的歷史)。

## macOS Tooling

- Python scripts intended to run from Raycast use `uv run` (auto-installs deps from inline `# /// script` headers)
- `common/gemini.py` always prepends `/opt/homebrew/bin:/usr/local/bin` to PATH so the `gemini` CLI is found in Raycast/cron contexts
- `common/notify.py` requires `terminal-notifier` (`brew install terminal-notifier`)
