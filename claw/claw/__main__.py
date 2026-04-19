import asyncio
import logging
import os
import sys

from .config import load_config


def _menubar_enabled() -> bool:
    return os.environ.get("CLAW_MENUBAR", "1") != "0"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = load_config()

    if _menubar_enabled():
        from .menubar import run_menubar

        run_menubar(config)
        return 0

    from .bot import run_bot

    try:
        asyncio.run(run_bot(config))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
