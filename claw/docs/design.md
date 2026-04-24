# Claw — 設計文件

## 背景 / 目標

要有一個本機跑的 Discord AI 助理：在個人 Discord server 的專用頻道貼訊息，本機 bot 就會呼叫本地安裝的 CLI（`gemini -p`、`claude -p`、`codex`）產生回覆貼回 thread。

**核心限制：完全不使用 API 模式**，目的是用 CLI 訂閱配額而不是額外花 API 費用。

**真正的挑戰**是電腦會關機/休眠。Bot 重上線時必須去 Discord REST 把離線期間漏掉的訊息全部抓回來處理，不能漏訊息。這是單純靠 `discord.py` 的 Gateway 事件（離線期間事件直接掉）做不到的。

MVP 範圍：先跑通 Gemini CLI + 單一頻道，CLI adapter 設計成抽象介面，之後無痛擴到 Claude Code / Codex。

---

## 設計原則：筆電前提（laptop-first）

claw 跑在個人筆電（macOS）上，不是 24/7 通電的 server。**任何新功能都必須假設程式會在任意時間被睡眠中斷，且睡眠期間時間不會推進**。這是預設行為，不是邊角情境。

具體要設計進去的 fail mode：

1. **時間相關邏輯**：asyncio / `time.monotonic` 的 timer 在 macOS 睡眠期間不會走（包括 `asyncio.sleep`、`call_later` 與所有靠它們的排程器）。睡眠中錯過的觸發點，醒來後不會自動補觸發 —— 要靠 wall-clock 重新比對或啟動時的 catch-up 邏輯（持久化「上次執行時間」+ 醒來時補跑）。
2. **網路連線**：Discord Gateway / HTTP 連線必斷。補救靠 `on_resumed` 重連 + REST backfill 把離線期間漏掉的事件補回。Gateway 推送的事件本身在離線期間直接掉，不能依賴 push。
3. **長時間 subprocess**：CLI subprocess 跑到一半可能被 OS 一起暫停數小時；醒來後可能因 token / 連線過期而失敗。要 graceful 處理而非靠 timeout 預設。
4. **外部資源時效**：Discord 附件 CDN 簽章 URL、OAuth token、API rate-limit 視窗，睡眠前抓到的，醒來後可能已經過期。不能假設睡眠前後外部狀態連續。
5. **狀態持久化**：任何「下次該做什麼 / 上次做到哪」的資訊不能只放 in-memory，必須落到 SQLite / 檔案，讓喚醒甚至 launchd 重啟後能還原。

**新功能 review checklist**：

- [ ] 此功能有依賴「絕對時間」或「相對延遲」的行為嗎？睡眠中錯過會發生什麼？
- [ ] 此功能有依賴連線狀態嗎？斷線重連會 replay 嗎、會掉資料嗎？
- [ ] 此功能有 in-memory only 的狀態嗎？process 重啟後會丟嗎？
- [ ] 喚醒後此功能能否判定「上次做到哪」並補上漏掉的工作？
- [ ] 外部資源（URL、token、session）在睡眠後仍有效嗎？無效時 fallback 是什麼？

---

## 架構總覽

```
┌──────────────────────────────────────────────────────────────┐
│ macOS launchd  (KeepAlive, runs on login + after wake)       │
└────────────────────┬─────────────────────────────────────────┘
                     │ spawns
                     ▼
┌──────────────────────────────────────────────────────────────┐
│ claw process (single asyncio event loop, Python 3.12+)       │
│                                                              │
│  ┌──────────────┐  on_ready/   ┌──────────────┐              │
│  │ Discord      │──on_resumed→ │ Backfill     │              │
│  │ Gateway      │              │ Service      │              │
│  │ (discord.py) │              │ (REST crawl) │              │
│  └──────┬───────┘              └──────┬───────┘              │
│         │on_message                   │ enqueue missed       │
│         ▼                             ▼                      │
│  ┌────────────────────────────────────────────┐              │
│  │ Task Dispatcher                            │              │
│  │  - per-thread FIFO queue                   │              │
│  │  - per top-level message: own queue        │              │
│  │  - global asyncio.Semaphore(MAX_CONCURRENCY)│             │
│  └──────────┬─────────────────────────────────┘              │
│             │                                                │
│             ▼                                                │
│  ┌───────────────────┐    ┌──────────────────┐               │
│  │ CLI Adapter       │◀──▶│ State Store      │               │
│  │  BaseCliAdapter   │    │ SQLite (WAL)     │               │
│  │  └ GeminiAdapter  │    │  channels        │               │
│  │  (Claude/Codex    │    │  threads         │               │
│  │   later)          │    │  messages        │               │
│  └─────────┬─────────┘    │  tasks           │               │
│            │              └──────────────────┘               │
│            ▼                                                 │
│     subprocess: gemini -r <id> -p "..."                      │
│                                                              │
│  ┌───────────────────┐                                       │
│  │ Reaction Manager  │  ⏳ → ✅ / ❌                          │
│  └───────────────────┘                                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 決策表

| 項目 | 決定 |
|---|---|
| 用途 | 通用 AI 任務助理（不寫 code） |
| 對話單位 | Discord thread = 一個 CLI session |
| CLI 模式 | 全域單一 CLI（config 指定），MVP 用 Gemini |
| 監聽 | 一個指定 channel，裡面每則 top-level 訊息觸發任務 |
| Thread 命名 | 取首則訊息前 50 字 |
| 離線補抓 | SQLite 存 `last_processed_message_id` + Discord emoji 反應 |
| 反應語意 | ⏳ 處理中 → ✅ 完成 / ❌ 失敗 |
| 併發 | 不同 thread / 不同 top-level 訊息並行（`MAX_CONCURRENCY` 預設 3）、同 thread 內 FIFO |
| 輸出 | CLI 跑完一次性回覆；超過 2000 字自動切，超過 10000 字改附 `.md` |
| 存取控制 | 信任 Discord 頻道權限，不自建 allowlist |
| CLI 工作目錄 | 全域 `~/.pclaw/`（也是 pclaw state home） |
| 逾時/取消 | 都不做（MVP） |
| 部署 | macOS launchd，`RunAtLoad + KeepAlive`；休眠喚醒後靠 `on_resumed` 事件觸發補抓 |
| 錯誤 | CLI 非零退出 → ❌ + 在 thread 貼 stderr 摘要，不自動重試 |

---

## 模組配置

```
claw/
├── pyproject.toml              # 依賴：discord.py, 其餘全部 stdlib
├── README.md                   # 安裝與操作
├── docs/
│   └── design.md               # 本文件
├── claw/
│   ├── __main__.py             # python -m claw 入口
│   ├── config.py               # 讀 ~/.pclaw/config.toml + env 覆蓋
│   ├── bot.py                  # discord.py Client：on_ready/on_resumed/on_message
│   ├── backfill.py             # REST 補抓漏掉的訊息
│   ├── dispatcher.py           # per-thread queue + 全域 Semaphore
│   ├── storage.py              # SQLite schema + CRUD
│   ├── reactions.py            # ⏳/✅/❌
│   ├── replies.py              # 切段與 >10k 附檔
│   └── cli/
│       ├── base.py             # BaseCliAdapter 抽象介面
│       └── gemini.py           # GeminiAdapter
├── launchd/
│   └── com.paulwu.claw.plist
└── tests/
```

執行時的狀態目錄（runtime 建立，也是 CLI subprocess 的 cwd）：

```
~/.pclaw/
├── config.toml                 # token、channel id、CLI 種類、並發數
├── claw.db                     # SQLite WAL
├── skills/<name>/SKILL.md      # pclaw skill 的 source of truth
├── .claude/                    # install-skills.sh 建的 Claude plugin
│   ├── .claude-plugin/plugin.json
│   └── skills/<name>           → symlink → ../skills/<name>
├── .gemini/                    # gemini skills link --scope workspace 的結果
│   └── skills/<name>           → symlink → ../skills/<name>
├── attachments/<msg_id>/       # 下載的 Discord 附件（`@ref` 相對路徑的錨點）
└── logs/                       # stdout/stderr
```

CLI subprocess 的 cwd 就是 `~/.pclaw/` 本身。好處：gemini 的 workspace-scope skills 自然落在 `~/.pclaw/.gemini/`、和 `.claude/` 同層；global `~/.claude/skills/` 和 `~/.gemini/skills/` 不會被污染。

---

## SQLite Schema

```sql
-- 追蹤 bot 監聽的 channel 補抓進度
CREATE TABLE channels (
    channel_id        TEXT PRIMARY KEY,
    last_processed_id TEXT,                    -- 最後處理過的 message snowflake
    updated_at        INTEGER NOT NULL
);

-- Discord thread ↔ CLI session 對應
CREATE TABLE threads (
    thread_id       TEXT PRIMARY KEY,
    parent_msg_id   TEXT NOT NULL,
    cli_session_id  TEXT,
    cli_kind        TEXT NOT NULL,             -- 'gemini' | 'claude' | 'codex'
    created_at      INTEGER NOT NULL
);

-- 每則進來的使用者訊息（用於補抓去重）
CREATE TABLE messages (
    message_id   TEXT PRIMARY KEY,
    channel_id   TEXT NOT NULL,
    thread_id    TEXT,                         -- NULL = top-level channel 訊息
    author_id    TEXT NOT NULL,
    content      TEXT NOT NULL,
    created_at   INTEGER NOT NULL,
    processed_at INTEGER                       -- NULL = 尚未處理
);

-- 任務歷史（除錯用）
CREATE TABLE tasks (
    task_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL,                -- 'running' | 'done' | 'error'
    started_at   INTEGER,
    finished_at  INTEGER,
    error_text   TEXT,
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
);

CREATE INDEX idx_messages_channel_created ON messages(channel_id, created_at);
CREATE INDEX idx_messages_thread ON messages(thread_id, created_at);
```

`PRAGMA journal_mode=WAL`、`last_processed_id` 用 `CAST(... AS INTEGER)` 比大小避免 snowflake 字串比較出錯。

---

## 關鍵流程

### 1. 啟動 / 喚醒後補抓

`bot.py` 的 `on_ready` 和 `on_resumed` 都會觸發 `backfill.backfill_channel`：

1. 依 `channels.last_processed_id` 從 Discord REST 拉 channel 內所有新訊息 → 記入 `messages` → 加 ⏳ → 丟進 dispatcher queue。
2. 對 `threads` 表的每個已追蹤 thread，從該 thread 最後一則已處理的訊息往後拉 → 一樣記入並入列。

順序：先 channel top-level（每則會觸發新 thread）→ 再各已存在 thread 的回覆。

### 2. 新訊息（Gateway `on_message`）

```python
if msg 不屬於監聽的 channel 或其下的 thread: return
if msg.author 是 bot: return
storage.record_message(...)
await reactions.mark_queued(msg)    # 加 ⏳
await dispatcher.submit(Job(msg))
```

### 3. Dispatcher

- `queue_key`：thread 訊息 → `thread:<id>`；top-level → `msg:<msg_id>`（每則 top-level 訊息各自一條一次性 queue，互不阻擋）。
- 每條 queue 都有自己的 worker task；worker 拿到 job 後取全域 `Semaphore`（`MAX_CONCURRENCY`）再執行。
- 同 thread 內嚴格 FIFO；不同 thread / 不同 top-level 可並行至 semaphore 上限。

### 4. Job handler

- Top-level 訊息：`msg.create_thread(name=前50字)` → `adapter.run(content, session_id=None)` → 存回 `threads.cli_session_id` → 在 thread 內 `send_reply`。
- Thread 內訊息：從 `threads` 取 `cli_session_id` → `adapter.run(content, session_id=...)` → 在同 thread 內 `send_reply`。

收尾：⏳ → ✅（或 ❌ 並貼錯誤摘要）、`mark_processed`、`update_last_processed_id`。

### 5a. ClaudeAdapter

```python
async def run(prompt, session_id):
    if session_id is None:
        session_id = str(uuid.uuid4())          # 我們自己挑
        reply = subprocess("claude -p --output-format text [--model M] --session-id UUID --tools '' PROMPT")
    else:
        reply = subprocess("claude -p --output-format text [--model M] --resume UUID --tools '' PROMPT")
    return CliResult(reply, session_id)
```

- `--session-id <uuid>` 讓我們**預先指定** UUID，所以第一次呼叫就能把 id 存進 DB，不需要 diff。
- `--tools ""` 關閉 Claude Code 的 Bash/Edit/Read 等內建工具 — claw 當通用助理用，不需要它動手。附件是用 `@path` 嵌進 prompt 的，不走 Read 工具。
- 切換 adapter（gemini → claude）後，既有 thread 的 `threads.cli_kind` 會和當前 adapter 不符；`_handle_thread_message` 偵測到就在該 thread 起一個新 session，`set_cli_session` 會把 kind 和 session_id 一起更新。

### 5b. GeminiAdapter

```python
async def run(prompt, session_id):
    if session_id is None:
        async with new_session_lock:
            before = list_session_uuids()
            reply = subprocess("gemini -o text [-m model] -p PROMPT")
            after = list_session_uuids()
        new_ids = after - before
        assert len(new_ids) == 1
        return CliResult(reply, new_ids[0])
    else:
        reply = subprocess("gemini -o text [-m model] -r SESSION_ID -p PROMPT")
        return CliResult(reply, session_id)
```

- `cwd=~/.pclaw/` 讓 gemini 的 session 存在專屬 project（project hash 唯一），同時 workspace-scope skills 自動落在 `~/.pclaw/.gemini/`。
- `PATH` 前置 `/opt/homebrew/bin:/usr/local/bin` 沿用 `common/gemini.py` 的做法，讓 launchd 下找得到 `gemini`。
- UUID 正規：`\[([0-9a-f-]{36})\]` 從 `--list-sessions` 文字輸出擷取。
- `new_session_lock` 防止兩個同時的新 session 建立造成 before/after diff 出現多筆。

### 6. 回覆切段 (`replies.py`)

- `<= 1900` 字：一則送出。
- `<= 10000` 字：以 paragraph > sentence > hard cut 逐級切段。
- `> 10000` 字：附 `reply.md` 檔 + 一則摘要文字。

---

## launchd

`~/Library/LaunchAgents/com.paulwu.claw.plist`：`RunAtLoad=true`、`KeepAlive=true`、`ThrottleInterval=15`。休眠/喚醒時網路一回來 discord.py 自動重連觸發 `on_resumed`，補抓邏輯掛在那個事件上。

## 設定

`~/.pclaw/config.toml`：

```toml
[discord]
token = "..."
channel_id = "..."

[cli]
kind = "gemini"
model = "gemini-2.5-pro"
max_concurrency = 3
```

env 覆蓋：`CLAW_DISCORD_TOKEN`、`CLAW_CHANNEL_ID`、`CLAW_CLI_KIND`、`CLAW_CLI_MODEL`、`CLAW_MAX_CONCURRENCY`、`CLAW_HOME`。

---

## 驗證計畫

### 單元測試

`uv run pytest tests/ -v`，覆蓋：

- `storage`：schema、`record_message` 冪等、`last_processed_id` 只進不退、thread/task 生命週期
- `dispatcher`：同 thread 序列化、不同 top-level 並行、`MAX_CONCURRENCY` 上限
- `GeminiAdapter`：mock subprocess，驗證 session_id 有/無時 args 正確、`--list-sessions` diff 取新 id、錯誤非零退出會拋 `CliError`
- `replies`：paragraph/sentence/hard-cut 切段
- `config`：toml 讀取、env 覆蓋、缺 token 報錯

### 手動端到端

1. Discord Developer Portal 建 Application + Bot，打開 **Message Content Intent**。
2. 邀 bot 進 personal server，建 `#claw`，給 View/Send/SendInThreads/CreatePublicThreads/AddReactions/ReadHistory 權限。
3. 填 `~/.pclaw/config.toml`，前台跑 `uv run python -m claw`。
4. 在 `#claw` 發「幫我規劃週末行程」→ 應看到 ⏳ → thread 建出 → gemini 回覆 → ⏳ 變 ✅。
5. 在該 thread 發「改成只待一天」→ gemini 應接續原本 context 回覆。
6. **模擬離線**：`launchctl unload …`，在頻道和 thread 各發一則訊息，`launchctl load …` → bot 應補處理兩則。
7. **模擬休眠**：讓 Mac 睡眠，喚醒後 `tail ~/.pclaw/logs/stderr.log` 看有 `gateway resumed; running backfill`。
8. 上 launchd：`cp launchd/com.paulwu.claw.plist ~/Library/LaunchAgents/ && launchctl load …`。

### 觀察點

- `~/.pclaw/logs/stderr.log`：每則訊息進來 / 任務完成 / 錯誤都有 log。
- `sqlite3 ~/.pclaw/claw.db "SELECT * FROM tasks ORDER BY task_id DESC LIMIT 20"`
- `sqlite3 ~/.pclaw/claw.db "SELECT thread_id, cli_session_id, cli_kind FROM threads"`

---

## 長期記憶

- 檔：`~/.pclaw/memory.md`（bot 啟動時自動建立含 header 的 stub）
- 符號連結：`~/.pclaw/CLAUDE.md` 和 `~/.pclaw/GEMINI.md` 指向它，讓 Claude Code 和 Gemini CLI 在每次新 session 載入時自動把內容加入 system prompt context
- 寫入：`/remember <text>` 內建指令（不經 dispatcher / CLI），直接 append 帶日期的 bullet；成功反應 🧠
- 讀：使用者可直接編輯 `memory.md`；改完不用重啟 bot（下一個新 CLI session 自然讀到新版）
- 內建指令 vs skill：`/remember` 在 `_handle_builtin` 優先攔截，不會去找 `SkillRegistry`；其他以後可能的內建指令（`/forget`, `/memory`）都走這條路徑

## 附件（圖片 / 檔案）

- Discord `message.attachments` 的每個檔案下載到 `~/.pclaw/attachments/<message_id>/<sanitized_filename>`
- Prompt 尾端追加 gemini 的 `@<relative_path>` 語法，讓 CLI 以 multimodal 方式把檔案載入（圖片/PDF/純文字/聲音皆可）
- 失敗（最常是長時間離線後 Discord CDN 簽章 URL 過期）會 log warning 跳過，不擋住文字部分的處理
- 觸發時機在 `_handle_job` 內，所以 `on_message` 和 backfill 都走同一條路

## Skills（類似 openclaw / Claude Code）

- 目錄：`~/.pclaw/skills/<name>/SKILL.md`
- 檔案格式：YAML frontmatter（`name`, `description`）+ markdown body
- Body 內用 `{{input}}` 當 placeholder（user 輸入會塞進去；沒寫 placeholder 就自動 append）
- 觸發：Discord 訊息以 `/<name>` 開頭 → `skills.parse_slash` → `SkillRegistry.get(name).render(args)` → 送進 CLI
- 不存在的 slash 名稱：pass-through 當普通訊息處理
- 啟動時掃描一次；要重新載入就 unload/load launchd agent

## 定時任務

- 設定：`~/.pclaw/cron.toml`，格式：

```toml
[[jobs]]
name = "morning-briefing"
schedule = "0 8 * * 1-5"    # 標準 5 欄 cron
skill = "summary"            # 選配，用 skill template 包一層
prompt = "..."              # skill 為空就直接當 CLI prompt 送
```

- 引擎：`apscheduler.schedulers.asyncio.AsyncIOScheduler`，跟 bot 同一個 event loop
- 啟動時機：`on_ready`（等連上 Gateway 再開始，避免還沒登入就觸發）
- 關閉：`close()` 時 `scheduler.shutdown(wait=False)`
- 每次觸發：`ClawBot._run_cron_job` → `channel.send("⏰ <name>")` seed 訊息 → `seed.create_thread(...)` → 跑 CLI → `replies.send_reply(thread, result)`
- 結果 = 主頻道 top-level 看到 `⏰ <name>` + 可展開的 thread 內有 CLI 回覆；user 可在 thread 內繼續對話（會走原本 `on_message` 流程，認到 thread ↔ session 對應）
- `coalesce=True` + `misfire_grace_time=3600`：scheduler 在跑、但 firing 被延遲（例如同 job 還在執行）時，1 小時內會合併成一次補跑

**已知限制（受「筆電前提」原則影響）**：

- macOS 睡眠期間 asyncio monotonic timer 會凍結，APScheduler 不會試圖 firing，因此 `misfire_grace_time` 對「睡眠錯過」**沒有作用**。
- 目前 `on_ready` 會 re-add jobs 把 `next_fire_time` 對齊 wall clock，但只會推進到「下一個未來」的觸發點，過去被睡掉的那次不補跑。
- 結論：每天 9 點的 job，若 9 點時電腦在睡、11 點才開蓋，今天那次會丟失，下次是隔天 9 點。
- TODO：要做真正的 catch-up 需要持久化每個 job 的 `last_run`，啟動 / `on_ready` 時比對「上一個應觸發時間 > last_run」就補跑一次。

## 已知未驗證的行為

- `gemini -r <id> -p "..."` 在非互動模式下的 resume 行為是本設計的關鍵假設（help 未明說；實務可行性由作者報告為準）。MVP 首次真實跑通是驗證點 5。
- 真實 Discord Gateway 連線僅有 mock 測試。
- 休眠喚醒 `on_resumed` 的補抓時序只能在實體環境驗證。
