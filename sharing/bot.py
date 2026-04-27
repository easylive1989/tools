import asyncio
import logging
import os
import sys

import discord

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)

from common.gemini import GeminiClient
from common.notion import NotionApi
from extractor import extract
from notion_writer import write

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

REACTION_OK = "✅"
REACTION_PARTIAL = "🔖"
REACTION_ERROR = "❌"


class SharingBot(discord.Client):
    def __init__(self, channel_id: int, gemini: GeminiClient, notion: NotionApi):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.gemini = gemini
        self.notion = notion

    async def on_ready(self) -> None:
        log.info("sharing bot ready, watching channel %s", self.channel_id)

    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot:
            return
        if msg.channel.id != self.channel_id:
            return
        if not msg.content.strip():
            return

        log.info("processing message %s from %s", msg.id, msg.author)
        try:
            result = extract(msg.content, self.gemini)
            write(result, self.notion)
            reaction = REACTION_OK if result.confidence == "full" else REACTION_PARTIAL
            await msg.add_reaction(reaction)
            log.info("saved %r (confidence=%s)", result.name, result.confidence)
        except Exception as e:
            log.exception("failed to process message %s", msg.id)
            await msg.add_reaction(REACTION_ERROR)
            try:
                await msg.reply(f"❌ 儲存失敗：{str(e)[:200]}")
            except discord.HTTPException:
                pass


async def main() -> None:
    token = os.environ["CLAW_DISCORD_TOKEN"]
    channel_id = int(os.environ["SHARING_CHANNEL_ID"])
    notion_secret = os.environ["NOTION_SECRET"]
    google_api_key = os.environ.get("GOOGLE_API_KEY", "")

    if not google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required")

    gemini = GeminiClient(model_name="flash")
    notion = NotionApi(notion_secret)
    bot = SharingBot(channel_id, gemini, notion)

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
