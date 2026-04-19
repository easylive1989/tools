import asyncio
import logging
import subprocess
import threading

import rumps

from .bot import run_bot
from .config import Config


log = logging.getLogger(__name__)

_ICONS = {
    "starting": "⚪",
    "connecting": "🟡",
    "ready": "🟢",
    "error": "🔴",
}


class ClawMenuBar(rumps.App):
    """macOS menu bar wrapper. Runs the bot in a background asyncio thread
    and mirrors its connection state into the status bar icon.
    """

    def __init__(self, config: Config):
        super().__init__("pclaw", title=_ICONS["starting"], quit_button=None)
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pending_state = "starting"

        self._status_item = rumps.MenuItem("Status: starting")
        self.menu = [
            self._status_item,
            None,
            rumps.MenuItem("Open logs folder", callback=self._open_logs),
            rumps.MenuItem("Quit", callback=self._quit),
        ]
        self._start_bot_thread()

    # --- Bot thread ---------------------------------------------------

    def _start_bot_thread(self) -> None:
        def runner() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(
                    run_bot(self.config, status_callback=self._enqueue_state)
                )
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("bot thread crashed")
                self._enqueue_state("error")

        self._thread = threading.Thread(target=runner, daemon=True, name="claw-bot")
        self._thread.start()

    def _enqueue_state(self, state: str) -> None:
        # Called from the bot thread. The timer below applies it on main thread.
        self._pending_state = state

    # --- rumps main-thread timer --------------------------------------

    @rumps.timer(1)
    def _refresh(self, _: rumps.Timer) -> None:
        icon = _ICONS.get(self._pending_state, _ICONS["starting"])
        if self.title != icon:
            self.title = icon
        desired = f"Status: {self._pending_state}"
        if self._status_item.title != desired:
            self._status_item.title = desired

    # --- Menu actions -------------------------------------------------

    def _open_logs(self, _) -> None:
        subprocess.run(["open", str(self.config.state_home / "logs")])

    def _quit(self, _) -> None:
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        rumps.quit_application()


def run_menubar(config: Config) -> None:
    ClawMenuBar(config).run()
