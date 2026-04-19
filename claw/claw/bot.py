import logging
from pathlib import Path
from typing import Callable

import discord

from . import reactions, replies
from .backfill import backfill_channel
from .cli import BaseCliAdapter, CliError, get_adapter
from .config import Config
from .dispatcher import Dispatcher, Job
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
        Path(config.state_home / "logs").mkdir(parents=True, exist_ok=True)
        self._notify("connecting")

    # --- Discord lifecycle hooks --------------------------------------

    async def on_connect(self) -> None:
        self._notify("connecting")

    async def on_ready(self) -> None:
        log.info("logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")
        self._notify("ready")
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

        self.storage.record_message(
            message_id=str(msg.id),
            channel_id=str(msg.channel.id),
            thread_id=str(msg.channel.id) if isinstance(msg.channel, discord.Thread) else None,
            author_id=str(msg.author.id),
            content=msg.content,
            created_at=int(msg.created_at.timestamp()),
        )
        await reactions.mark_queued(msg)
        await self.dispatcher.submit(Job(message=msg))

    async def close(self) -> None:
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
            if isinstance(msg.channel, discord.Thread):
                await self._handle_thread_message(msg)
            else:
                await self._handle_top_level_message(msg)
            await reactions.mark_done(msg)
            self.storage.finish_task(str(msg.id))
        except CliError as e:
            log.warning("CLI error on %s: %s", msg.id, e)
            target = msg.channel if isinstance(msg.channel, discord.Thread) else msg
            err_text = str(e)[:1500]
            try:
                if isinstance(target, discord.Thread):
                    await target.send(f"❌ CLI 錯誤：\n```\n{err_text}\n```")
                else:
                    # no thread was created; reply in channel
                    await msg.channel.send(f"❌ CLI 錯誤：\n```\n{err_text}\n```")
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

    async def _handle_top_level_message(self, msg: discord.Message) -> None:
        thread = await msg.create_thread(name=_thread_name(msg.content))
        self.storage.upsert_thread(
            thread_id=str(thread.id),
            parent_msg_id=str(msg.id),
            cli_kind=self.adapter.kind,
        )
        result = await self.adapter.run(msg.content, session_id=None)
        self.storage.set_cli_session(str(thread.id), result.session_id)
        await replies.send_reply(thread, result.reply)

    async def _handle_thread_message(self, msg: discord.Message) -> None:
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
            result = await self.adapter.run(msg.content, session_id=None)
            self.storage.set_cli_session(str(msg.channel.id), result.session_id)
        else:
            result = await self.adapter.run(msg.content, session_id=session_id)

        await replies.send_reply(msg.channel, result.reply)


async def run_bot(config: Config, status_callback: StatusCallback | None = None) -> None:
    bot = ClawBot(config, status_callback=status_callback)
    async with bot:
        await bot.start(config.discord_token)
