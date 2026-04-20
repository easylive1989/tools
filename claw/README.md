# claw

Local Discord → CLI AI assistant. Post a message in a dedicated Discord channel; claw spawns a thread, runs a local CLI (`gemini -p`, and later `claude -p` / `codex`), and replies back.

Designed around the fact that the host Mac may be **shut down or asleep**: when the bot comes back online it walks the channel via REST to backfill any missed messages.

## How it works

- One dedicated Discord channel → every top-level message triggers a task.
- First message: claw creates a thread named after the message and starts a new CLI session.
- Thread replies: claw resumes the CLI session mapped to that thread, so conversation context is preserved by the CLI itself.
- Backfill: on startup **and** on every Discord gateway reconnect (`on_resumed`), claw walks the channel and tracked threads via REST and enqueues anything it missed.
- Visual feedback via emoji reactions: ⏳ queued → ✅ done / ❌ error.

See [`docs/design.md`](docs/design.md) for the full design.

## Install

```bash
cd /Users/paulwu/Documents/Github/tools/claw
uv sync --extra dev
```

Create state dir:

```bash
mkdir -p ~/.pclaw/{workdir,logs}
```

## Discord setup

1. https://discord.com/developers/applications → **New Application** → add a **Bot**.
2. In the Bot page, enable **Message Content Intent**.
3. OAuth2 → URL generator:
   - scopes: `bot`
   - bot permissions: View Channel, Send Messages, Send Messages in Threads, Create Public Threads, Add Reactions, Read Message History.
4. Invite the bot into your personal server, create a channel (e.g. `#claw`).
5. Copy the channel id (right-click channel → Copy Channel ID with developer mode on).

## Configuration

`~/.pclaw/config.toml`:

```toml
[discord]
token = "MTIz..."
channel_id = "123456789012345678"

[cli]
kind = "gemini"           # 'gemini' or 'claude'
model = "gemini-2.5-pro"  # for claude: 'opus' | 'sonnet' | 'haiku' | full model name
max_concurrency = 3
```

Switching `kind` and reloading will start fresh CLI sessions for any threads that were previously bound to the other CLI. Existing thread history in Discord is untouched; only the underlying CLI session ID is regenerated.

Env overrides (useful under launchd): `CLAW_DISCORD_TOKEN`, `CLAW_CHANNEL_ID`, `CLAW_CLI_KIND`, `CLAW_CLI_MODEL`, `CLAW_MAX_CONCURRENCY`, `CLAW_HOME`.

## Run (foreground)

```bash
uv run python -m claw
```

## Install as a launchd agent

```bash
cp launchd/com.paulwu.claw.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.paulwu.claw.plist
```

To stop / reload:

```bash
./reload.sh                  # quick reload + tails stderr
# or manually:
launchctl unload ~/Library/LaunchAgents/com.paulwu.claw.plist
launchctl load ~/Library/LaunchAgents/com.paulwu.claw.plist
```

`KeepAlive=true` restarts the process on crash. After sleep/wake, `discord.py` reconnects to the gateway and fires `on_resumed`, which triggers the backfill.

## Attachments

Drop any image, PDF, text file, or audio into a Discord message and claw will download it under `~/.pclaw/workdir/attachments/<message-id>/` and splice `@path` references into the prompt so Gemini picks it up natively (multimodal). No extra syntax needed — just attach and send.

## Skills

Named prompt templates stored as `~/.pclaw/skills/<name>/SKILL.md`. Trigger in Discord with `/<name> [args]`:

```
/summary 這是一段很長的文章 ...
/translate This English text should come back in Traditional Chinese.
/daily-retro 今天跟設計師討論了新的 onboarding 流程
```

`SKILL.md` format (YAML frontmatter + body, `{{input}}` marks where args go):

```markdown
---
name: summary
description: 把長文章整理成三點摘要
---

請把下面的內容整理成三個要點：

{{input}}
```

Three ready-to-use examples live in `examples/skills/`. Copy them to `~/.pclaw/skills/` and reload the agent:

```bash
mkdir -p ~/.pclaw/skills
cp -R examples/skills/* ~/.pclaw/skills/
launchctl unload ~/Library/LaunchAgents/com.paulwu.claw.plist
launchctl load   ~/Library/LaunchAgents/com.paulwu.claw.plist
```

Slash commands that don't match a known skill are passed through as normal prompts.

### Exposing skills to the CLI natively

Pclaw's own `/skill` routing always works. But if you also want Claude / Gemini to **auto-activate** skills from their own registries (so they kick in even when you didn't type `/`), run:

```bash
./install-skills.sh
```

This symlinks each `~/.pclaw/skills/<name>` into:
- `~/.claude/skills/<name>` (Claude Code picks it up on next run)
- `gemini skills link <path> --consent` (Gemini keeps a symlink under `~/.gemini/skills/`)

Because they're symlinks, editing the pclaw source reflects in both CLIs immediately; no reinstall needed.

## Scheduled tasks

`~/.pclaw/cron.toml` with standard 5-field cron entries:

```toml
[[jobs]]
name = "morning-briefing"
schedule = "0 8 * * 1-5"
skill = "summary"
prompt = "把昨天我關注的科技新聞整理一下"

[[jobs]]
name = "weekly-retro"
schedule = "0 22 * * 0"
prompt = "這週值得感謝的三件事是什麼？"
```

At fire time the bot posts a `⏰ <name>` seed message into the main channel, creates a thread, runs the CLI, and replies in the thread — same flow as a manual message, so you can keep chatting in the thread to follow up.

See `examples/cron.toml` for a commented template.

## Tests

```bash
uv run pytest tests/ -v
```

## Manual end-to-end checks

1. In `#claw` send: `幫我規劃週末行程` → expect ⏳ → a thread appears → gemini reply → ⏳ becomes ✅.
2. In that thread: `改成只待一天` → expect a follow-up that clearly carries the earlier context.
3. Offline check: `launchctl unload ~/Library/LaunchAgents/com.paulwu.claw.plist`, send a channel message **and** a thread reply, then `launchctl load ...`. Both should be processed on startup.
4. Sleep/wake check: put the Mac to sleep, wake it, tail `~/.pclaw/logs/stderr.log` for `gateway resumed; running backfill`.

Inspect state:

```bash
sqlite3 ~/.pclaw/claw.db "SELECT * FROM tasks ORDER BY task_id DESC LIMIT 20"
sqlite3 ~/.pclaw/claw.db "SELECT thread_id, cli_session_id, cli_kind FROM threads"
```
