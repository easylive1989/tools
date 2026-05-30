import { DiscordClient, RateLimitError } from "./discord";
import { shouldTranslate } from "./filter";
import { buildHackMdContent, buildOutgoingMessage } from "./format";
import { State } from "./state";
import { createTranslator, type Translator } from "./translator";
import { TranslationError } from "./translator/types";
import { extractAnthropicArticle } from "./article";
import { chunkParagraphs } from "./chunk";
import { HackMdClient } from "./hackmd";
import type { DiscordMessage } from "./filter";
import type { Env } from "./env";

const FETCH_BATCH_LIMIT = 50;
const MAX_RETRIES = 4;
const ARTICLE_CHUNK_CHARS = 3000; // 每批譯文原文上限,控制在 Workers AI 單次 prompt 預算內

/**
 * 嘗試把推文連到的 anthropic.com 文章翻成繁中、寫進 HackMD,回傳 note 連結。
 * 已建過(KV 有快取)就直接回快取連結;沒有 anthropic.com 連結就回 undefined。
 * 任一步驟失敗會往上丟,由呼叫端 try/catch 吞掉(HackMD 為附加功能)。
 */
async function resolveHackMdLink(
  msg: DiscordMessage,
  translator: Translator,
  hackmd: HackMdClient,
  state: State,
): Promise<string | undefined> {
  const cached = await state.getHackMdLink(msg.id);
  if (cached) return cached;

  const article = await extractAnthropicArticle(msg);
  if (!article) return undefined;

  const batches = chunkParagraphs(article.paragraphs, ARTICLE_CHUNK_CHARS);
  const parts: string[] = [];
  for (const batch of batches) {
    parts.push(await translator.translateArticle(batch));
  }

  const content = buildHackMdContent(article, parts.join("\n\n"));
  const { publishLink } = await hackmd.createNote(content);
  await state.setHackMdLink(msg.id, publishLink);
  return publishLink;
}

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
    const hackmd = new HackMdClient(env.HACKMD_API_TOKEN);

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

      // HackMD 支線:附加功能,失敗只 log,不影響推文發送
      let hackmdUrl: string | undefined;
      try {
        hackmdUrl = await resolveHackMdLink(msg, translator, hackmd, state);
      } catch (err) {
        console.error(`HackMD pipeline failed for ${msg.id}: ${(err as Error).message}`);
      }

      const outgoing = buildOutgoingMessage(msg, translated, hackmdUrl);
      try {
        await discord.postMessage(env.TARGET_CHANNEL_ID, outgoing);
      } catch (err) {
        console.error(`postMessage failed for ${msg.id}: ${(err as Error).message}`);
        return; // 不推進,下次重做(可能重發)
      }

      await state.setLastMessageId(msg.id);
      await state.clearRetryCount(msg.id);
    }
  },
};
