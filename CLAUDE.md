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

## Running Tools

Most tools are single scripts. Common patterns:

```bash
# RSS sync (Raycast launcher uses uv)
cd rss && uv run rss.py

# Document translation
cd document_translator
source venv/bin/activate
python src/docx_translator.py <file> [--use-cli] [--target-lang "Traditional Chinese"]

# Ledger analysis (needs NOTION_SECRET)
python ledger_analysis/ledger_analysis.py
```

## document_translator Architecture

The most structured sub-project. Entry points in `src/` (`docx_translator.py`, `obsidian_md_translator.py`, etc.) each:
1. Parse CLI args via `typer`
2. Initialise a `GeminiClient` via `src/utils/cli_helper.py`
3. Delegate to a handler in `src/handlers/` (one per format: markdown, docx, epub, pdf)

`src/services/gemini.py` is a thin wrapper over `common.gemini.GeminiClient` that adds translation-specific logic (`translate_text`, `translate_texts`).

Run tests:
```bash
cd document_translator && python -m pytest tests/ -v
```

## GitHub Actions

Active workflows (triggered on schedule + `workflow_dispatch`):
- `monthly-ledger-analysis.yml` — monthly ledger summary to Notion
- `deploy-pages.yml` — builds the travel apps and deploys to GitHub Pages (custom domain `tools.paul-learning.dev`)
- `deploy-sharing-bot.yml` — rsyncs sharing bot to VPS, restarts systemd service

The stock dashboard moved to a separate repo: <https://github.com/easylive1989/publixia> (`stock.paul-learning.dev`).

Required secrets: `NOTION_SECRET`, `DISCORD_*_WEBHOOK_URL`, `GOOGLE_API_KEY`.

## Environment Variables

Scripts read secrets directly from environment (no `.env` loading at root level; `document_translator` uses `python-dotenv`):

| Variable | Used by |
|---|---|
| `NOTION_SECRET` | `ledger_analysis.py`, `personal_retro/`, `medium/` |
| `DISCORD_*_WEBHOOK_URL` | `personal_retro/` |
| `GOOGLE_API_KEY` | `document_translator` (API mode) |
| `OPENAI_API_KEY` | `personal_retro/daily_review.py` |

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
