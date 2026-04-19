import logging
from pathlib import Path
from typing import Callable

import discord

from . import reactions, replies
from .attachments import build_attachment_prompt, download_attachments
from .backfill import backfill_channel
from .cli import BaseCliAdapter, CliError, get_adapter
from .config import Config
from .cron import CronJob, CronScheduler, load_jobs
from .dispatcher import Dispatcher, Job
from .skills import Skill, SkillRegistry, parse_slash
from .storage import Storage


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
        self.storage.set_cli_session(str(thread.id), result.session_id)
        await replies.send_reply(thread, result.reply)

    async def _handle_thread_message(self, job: Job, prompt: str) -> None:
        msg = job.message
        assert isinstance(msg.channel, discord.Thread)
        thread_row = self.storage.get_thread(str(msg.channel.id))
        session_id = thread_row.cli_session_id if thread_row else None

        if session_id is None:
            # Thread exists but we have no session record (e.g. bot lost DB or
            # the thread pre-dates this bot). Treat this turn as a fresh session.
            self.storage.upsert_thread(
                thread_id=str(msg.channel.id),
                parent_msg_id=str(msg.channel.id),
                cli_kind=self.adapter.kind,
            )
            result = await self.adapter.run(prompt, session_id=None)
            self.storage.set_cli_session(str(msg.channel.id), result.session_id)
        else:
            result = await self.adapter.run(prompt, session_id=session_id)

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

        self.storage.set_cli_session(str(thread.id), result.session_id)
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
