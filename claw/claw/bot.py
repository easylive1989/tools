import logging
from pathlib import Path
from typing import Callable

import discord

import json
import re

from . import memory, reactions, replies
from .attachments import build_attachment_prompt, download_attachments
from .backfill import backfill_channel
from .cli import BaseCliAdapter, CliError, get_adapter
from .config import Config
from .cron import CronJob, CronScheduler, load_jobs, upsert_job
from .dispatcher import Dispatcher, Job
from .skills import Skill, SkillRegistry, parse_slash
from .storage import Storage


_SCHEDULE_PARSE_PROMPT = """You are a scheduling parser for pclaw, a Discord bot.

Parse the user's natural-language description into a JSON object with EXACTLY
these fields. Output ONLY the JSON — no prose, no markdown code fences.

{{
  "name": "<kebab-case ASCII identifier, <= 40 chars>",
  "schedule": "<standard 5-field cron: MIN HOUR DOM MONTH DOW>",
  "human_readable": "<one short 繁體中文 sentence describing when it runs>",
  "skill": "<existing pclaw skill name, or null if no fit>",
  "prompt": "<what to ask the AI at runtime, distinct from a skill reference>"
}}

Day-of-week uses 0=Sunday through 6=Saturday. Minutes/hours are local machine time.

Existing pclaw skills you may reference by name: {skills}

User description:
{user_text}
"""


def _extract_json_object(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        return json.loads(m.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in CLI output")


StatusCallback = Callable[[str], None]


log = logging.getLogger(__name__)


def _thread_name(content: str) -> str:
    first_line = content.strip().split("\n", 1)[0].strip() or "claw"
    return first_line[:50]


class ClawBot(discord.Client):
    def __init__(self, config: Config, status_callback: StatusCallback | None = None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        super().__init__(intents=intents)

        self.config = config
        self.status_callback = status_callback
        self.storage = Storage(config.db_path)
        self.adapter: BaseCliAdapter = get_adapter(
            config.cli_kind, workdir=config.workdir, model=config.cli_model
        )
        self.dispatcher = Dispatcher(self._handle_job, config.max_concurrency)
        self.skills = SkillRegistry(config.skills_dir)
        self.cron = CronScheduler(load_jobs(config.cron_path), self._run_cron_job)
        Path(config.state_home / "logs").mkdir(parents=True, exist_ok=True)
        memory.ensure_memory_file(config.memory_path)
        memory.ensure_cli_symlinks(config.state_home)
        self._notify("connecting")

    # --- Discord lifecycle hooks --------------------------------------

    async def on_connect(self) -> None:
        self._notify("connecting")

    async def on_ready(self) -> None:
        log.info("logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")
        self._notify("ready")
        self.cron.start()
        await self._run_backfill()

    async def on_resumed(self) -> None:
        log.info("gateway resumed; running backfill")
        self._notify("ready")
        await self._run_backfill()

    async def on_disconnect(self) -> None:
        self._notify("connecting")

    def _notify(self, state: str) -> None:
        if self.status_callback is None:
            return
        try:
            self.status_callback(state)
        except Exception:
            log.exception("status callback failed")

    async def on_message(self, msg: discord.Message) -> None:
        if not self._is_relevant(msg):
            return
        if msg.author.bot or msg.author.id == (self.user.id if self.user else 0):
            return

        if await self._handle_builtin(msg):
            return

        effective_content = self._expand_slash(msg)

        self.storage.record_message(
            message_id=str(msg.id),
            channel_id=str(msg.channel.id),
            thread_id=str(msg.channel.id) if isinstance(msg.channel, discord.Thread) else None,
            author_id=str(msg.author.id),
            content=msg.content,
            created_at=int(msg.created_at.timestamp()),
        )
        await reactions.mark_queued(msg)
        await self.dispatcher.submit(Job(message=msg, effective_content=effective_content))

    async def close(self) -> None:
        self.cron.shutdown()
        await self.dispatcher.shutdown()
        self.storage.close()
        await super().close()

    # --- Internals ----------------------------------------------------

    def _is_relevant(self, msg: discord.Message) -> bool:
        if msg.channel.id == self.config.channel_id:
            return True
        if isinstance(msg.channel, discord.Thread) and msg.channel.parent_id == self.config.channel_id:
            return True
        return False

    async def _handle_builtin(self, msg: discord.Message) -> bool:
        """Intercept pclaw-internal slash commands that don't go through the CLI.

        Returns True if the message was handled; False to let normal dispatch
        continue. These commands execute synchronously and don't create threads.
        """
        slash = parse_slash(msg.content)
        if slash is None:
            return False
        name, args = slash
        if name == "remember":
            await self._cmd_remember(msg, args)
            return True
        if name == "schedule":
            await self._cmd_schedule(msg, args)
            return True
        return False

    async def _cmd_schedule(self, msg: discord.Message, text: str) -> None:
        if not text.strip():
            await msg.reply(
                "`/schedule` 需要描述，例如 `/schedule 每天早上 8:28 用 morning-note skill 產生台股大盤`"
            )
            return

        await reactions.mark_queued(msg)

        skills_csv = ", ".join(self.skills.names()) or "(none)"
        parse_prompt = _SCHEDULE_PARSE_PROMPT.format(skills=skills_csv, user_text=text)
        try:
            result = await self.adapter.run(parse_prompt, session_id=None)
        except CliError as e:
            log.warning("schedule parse failed: %s", e)
            await reactions.mark_error(msg)
            await msg.reply(f"❌ 解析失敗（CLI 錯誤）：\n```\n{str(e)[:500]}\n```")
            return

        try:
            parsed = _extract_json_object(result.reply)
        except (ValueError, json.JSONDecodeError) as e:
            log.warning("schedule JSON parse failed: %s\nraw: %s", e, result.reply[:500])
            await reactions.mark_error(msg)
            await msg.reply(
                f"❌ 無法從 CLI 輸出抽出 JSON：\n```\n{result.reply[:500]}\n```"
            )
            return

        try:
            job = self._build_cron_job(parsed)
        except ValueError as e:
            await reactions.mark_error(msg)
            await msg.reply(f"❌ 排程無效：{e}")
            return

        upsert_job(self.config.cron_path, job)
        self.cron.reload(load_jobs(self.config.cron_path))

        readable = parsed.get("human_readable") or job.schedule
        skill_line = f"\n🧠 skill: `{job.skill}`" if job.skill else ""
        await reactions.mark_done(msg)
        await msg.reply(
            f"✅ 已排程 **{job.name}**\n"
            f"⏰ `{job.schedule}` — {readable}{skill_line}\n"
            f"📝 {job.prompt[:200]}"
        )

    def _build_cron_job(self, parsed: dict) -> CronJob:
        name = str(parsed.get("name") or "").strip()
        schedule = str(parsed.get("schedule") or "").strip()
        prompt = str(parsed.get("prompt") or "").strip()
        skill = parsed.get("skill")
        if not name or not re.match(r"^[a-z0-9][a-z0-9-]{0,39}$", name):
            raise ValueError(f"name 不合法: {name!r}（需 kebab-case、ASCII、≤40 字）")
        if not schedule or len(schedule.split()) != 5:
            raise ValueError(f"schedule 不是 5-field cron: {schedule!r}")
        if not prompt:
            raise ValueError("prompt 不能為空")
        if skill and skill not in self.skills.names():
            raise ValueError(f"skill `{skill}` 不存在。現有: {', '.join(self.skills.names())}")
        # Final sanity: APScheduler parse
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(schedule)
        return CronJob(name=name, schedule=schedule, prompt=prompt, skill=skill or None)

    async def _cmd_remember(self, msg: discord.Message, text: str) -> None:
        if not text.strip():
            await msg.add_reaction("❌")
            try:
                await msg.reply("`/remember` 需要內容，例如 `/remember 我喜歡喝無糖茶`")
            except discord.HTTPException:
                pass
            return
        entry = memory.append_memory(self.config.memory_path, text)
        log.info("memory appended: %s", entry)
        try:
            await msg.add_reaction("🧠")
        except discord.HTTPException:
            pass

    def _expand_slash(self, msg: discord.Message) -> str | None:
        slash = parse_slash(msg.content)
        if slash is None:
            return None
        name, args = slash
        skill = self.skills.get(name)
        if skill is None:
            log.info("slash /%s has no matching skill; passing through verbatim", name)
            return None
        log.info("expanding /%s skill (%d chars of input)", name, len(args))
        return skill.render(args)

    async def _run_backfill(self) -> None:
        try:
            await backfill_channel(
                client=self,
                channel_id=self.config.channel_id,
                storage=self.storage,
                enqueue=self.dispatcher.submit,
            )
        except Exception:
            log.exception("backfill failed")

    async def _handle_job(self, job: Job) -> None:
        msg = job.message
        self.storage.start_task(str(msg.id))

        try:
            prompt = await self._prepare_prompt(job)
            if isinstance(msg.channel, discord.Thread):
                await self._handle_thread_message(job, prompt)
            else:
                await self._handle_top_level_message(job, prompt)
            await reactions.mark_done(msg)
            self.storage.finish_task(str(msg.id))
        except CliError as e:
            log.warning("CLI error on %s: %s", msg.id, e)
            err_text = str(e)[:1500]
            try:
                target = msg.channel if isinstance(msg.channel, discord.Thread) else msg.channel
                await target.send(f"❌ CLI 錯誤：\n```\n{err_text}\n```")
            except discord.HTTPException:
                log.exception("failed to post error message")
            await reactions.mark_error(msg)
            self.storage.finish_task(str(msg.id), error=err_text)
        except Exception as e:
            log.exception("unexpected error processing %s", msg.id)
            await reactions.mark_error(msg)
            self.storage.finish_task(str(msg.id), error=repr(e))
        finally:
            self.storage.mark_processed(str(msg.id))
            self.storage.update_last_processed_id(
                str(self.config.channel_id), str(msg.id)
            )

    async def _prepare_prompt(self, job: Job) -> str:
        """Augment the base prompt with @references for any Discord attachments."""
        rel_paths = await download_attachments(job.message, self.config.workdir)
        return build_attachment_prompt(job.prompt, rel_paths)

    async def _handle_top_level_message(self, job: Job, prompt: str) -> None:
        msg = job.message
        thread = await msg.create_thread(name=_thread_name(msg.content))
        self.storage.upsert_thread(
            thread_id=str(thread.id),
            parent_msg_id=str(msg.id),
            cli_kind=self.adapter.kind,
        )
        result = await self.adapter.run(prompt, session_id=None)
        self.storage.set_cli_session(str(thread.id), result.session_id, self.adapter.kind)
        await replies.send_reply(thread, result.reply)

    async def _handle_thread_message(self, job: Job, prompt: str) -> None:
        msg = job.message
        assert isinstance(msg.channel, discord.Thread)
        thread_row = self.storage.get_thread(str(msg.channel.id))

        # Reuse an existing session only when it was created by the currently
        # configured CLI. If the user switched CLIs (gemini→claude etc.) or
        # we've lost the DB entry entirely, start a fresh session for this
        # thread under the current adapter.
        can_resume = (
            thread_row is not None
            and thread_row.cli_kind == self.adapter.kind
            and thread_row.cli_session_id is not None
        )

        if can_resume:
            result = await self.adapter.run(prompt, session_id=thread_row.cli_session_id)
        else:
            self.storage.upsert_thread(
                thread_id=str(msg.channel.id),
                parent_msg_id=str(msg.channel.id),
                cli_kind=self.adapter.kind,
            )
            result = await self.adapter.run(prompt, session_id=None)
            self.storage.set_cli_session(
                str(msg.channel.id), result.session_id, self.adapter.kind
            )

        await replies.send_reply(msg.channel, result.reply)

    # --- Cron ---------------------------------------------------------

    async def _run_cron_job(self, job: CronJob) -> None:
        channel = await self.fetch_channel(self.config.channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.error("cron channel %s is not a text channel", self.config.channel_id)
            return

        prompt = self._expand_cron_prompt(job)

        # Post a seed message so the thread has somewhere to attach + the user
        # can see what triggered this run.
        seed = await channel.send(f"⏰ **{job.name}**")
        thread = await seed.create_thread(name=job.name[:50] or "cron")
        self.storage.upsert_thread(
            thread_id=str(thread.id),
            parent_msg_id=str(seed.id),
            cli_kind=self.adapter.kind,
        )

        try:
            result = await self.adapter.run(prompt, session_id=None)
        except CliError as e:
            await thread.send(f"❌ CLI 錯誤：\n```\n{str(e)[:1500]}\n```")
            return

        self.storage.set_cli_session(str(thread.id), result.session_id, self.adapter.kind)
        await replies.send_reply(thread, result.reply)

    def _expand_cron_prompt(self, job: CronJob) -> str:
        if job.skill:
            skill: Skill | None = self.skills.get(job.skill)
            if skill is None:
                log.warning("cron job %s references unknown skill %s", job.name, job.skill)
                return job.prompt
            return skill.render(job.prompt)
        return job.prompt


async def run_bot(config: Config, status_callback: StatusCallback | None = None) -> None:
    bot = ClawBot(config, status_callback=status_callback)
    async with bot:
        await bot.start(config.discord_token)
