import { DiscordClient, RateLimitError } from "./discord";
import { shouldTranslate } from "./filter";
import { buildOutgoingMessage } from "./format";
import { State } from "./state";
import { createTranslator } from "./translator";
import { TranslationError } from "./translator/types";
import type { Env } from "./env";

const FETCH_BATCH_LIMIT = 50;
const MAX_RETRIES = 4;

export default {
  async scheduled(_event: ScheduledController, env: Env, _ctx: ExecutionContext): Promise<void> {
    const state = new State(env.KV);
    const discord = new DiscordClient(env.DISCORD_BOT_TOKEN);

    const lastId = await state.getLastMessageId();
    if (lastId === null) {
      const latest = await discord.fetchLatest(env.SOURCE_CHANNEL_ID);
      if (latest[0]) {
        await state.setLastMessageId(latest[0].id);
        console.log(`bootstrap: last_message_id = ${latest[0].id}`);
      } else {
        console.log("bootstrap: source channel empty, will retry next cron");
      }
      return;
    }

    let messages;
    try {
      messages = await discord.fetchMessagesAfter(
        env.SOURCE_CHANNEL_ID,
        lastId,
        FETCH_BATCH_LIMIT,
      );
    } catch (err) {
      if (err instanceof RateLimitError) {
        console.error(`Discord rate limited, retry in ${err.retryAfterSec}s`);
        return;
      }
      console.error(`fetchMessagesAfter failed: ${(err as Error).message}`);
      return;
    }

    if (messages.length === 0) return;

    const translator = createTranslator(env);

    for (const msg of messages) {
      if (!shouldTranslate(msg)) {
        await state.setLastMessageId(msg.id);
        continue;
      }

      const text = msg.embeds[0]!.description!;
      let translated: string;
      try {
        translated = await translator.translate(text);
      } catch (err) {
        if (err instanceof TranslationError) {
          const retry = await state.incrementRetryCount(msg.id);
          console.error(
            `translate failed for ${msg.id} (retry ${retry}/${MAX_RETRIES}): ${err.message}`,
          );
          if (retry >= MAX_RETRIES) {
            console.error(`giving up on ${msg.id}, skipping`);
            await state.clearRetryCount(msg.id);
            await state.setLastMessageId(msg.id);
            continue;
          }
          return; // 等下次 cron 重試
        }
        throw err;
      }

      try {
        await discord.postMessage(
          env.TARGET_CHANNEL_ID,
          buildOutgoingMessage(msg, translated),
        );
      } catch (err) {
        console.error(`postMessage failed for ${msg.id}: ${(err as Error).message}`);
        return; // 不推進,下次重做(可能重發)
      }

      await state.setLastMessageId(msg.id);
      await state.clearRetryCount(msg.id);
    }
  },
};
