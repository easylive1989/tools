import { DiscordClient, RateLimitError } from "./discord";
import { shouldTranslate } from "./filter";
import {
  buildHackMdContent,
  buildHackMdErrorMessage,
  buildOutgoingMessage,
  type HackMdFailureReason,
} from "./format";
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
 * HackMD 支線的結果:
 * - ok / cached → 成功取得 note 連結(cached 為 KV 既有)
 * - skipped → 沒抓到文章(原因見 reason),屬可預期情況
 * - failed → 翻譯或建立 note 失敗(detail 帶錯誤訊息)
 */
type HackMdOutcome =
  | { kind: "ok"; link: string }
  | { kind: "cached"; link: string }
  | { kind: "skipped"; reason: HackMdFailureReason }
  | { kind: "failed"; reason: HackMdFailureReason; detail: string };

/**
 * 嘗試把推文連到的 anthropic.com 文章翻成繁中、寫進 HackMD。
 * 已建過(KV 有快取)直接回快取連結;否則回報是哪一類情況/失敗。
 * 本函式不 throw(翻譯與 HackMD 的錯誤都轉成 outcome)。
 */
async function resolveHackMdLink(
  msg: DiscordMessage,
  translator: Translator,
  hackmd: HackMdClient,
  state: State,
): Promise<HackMdOutcome> {
  const cached = await state.getHackMdLink(msg.id);
  if (cached) return { kind: "cached", link: cached };

  const extraction = await extractAnthropicArticle(msg);
  if (!extraction.ok) return { kind: "skipped", reason: extraction.reason };
  const article = extraction.article;

  const batches = chunkParagraphs(article.paragraphs, ARTICLE_CHUNK_CHARS);
  const parts: string[] = [];
  for (const batch of batches) {
    try {
      parts.push(await translator.translateArticle(batch));
    } catch (err) {
      return { kind: "failed", reason: "translate-failed", detail: (err as Error).message };
    }
  }

  const content = buildHackMdContent(article, parts.join("\n\n"));
  let publishLink: string;
  try {
    ({ publishLink } = await hackmd.createNote(content));
  } catch (err) {
    return { kind: "failed", reason: "hackmd-failed", detail: (err as Error).message };
  }
  await state.setHackMdLink(msg.id, publishLink);
  return { kind: "ok", link: publishLink };
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
      let outcome: HackMdOutcome;
      try {
        outcome = await resolveHackMdLink(msg, translator, hackmd, state);
      } catch (err) {
        // 多半是 KV 例外等非預期錯誤,當成 failed 處理
        outcome = { kind: "failed", reason: "hackmd-failed", detail: (err as Error).message };
      }
      const hackmdUrl =
        outcome.kind === "ok" || outcome.kind === "cached" ? outcome.link : undefined;

      const outgoing = buildOutgoingMessage(msg, translated, hackmdUrl);
      try {
        await discord.postMessage(env.TARGET_CHANNEL_ID, outgoing);
      } catch (err) {
        console.error(`postMessage failed for ${msg.id}: ${(err as Error).message}`);
        return; // 不推進,下次重做(可能重發)
      }

      // 沒產生 HackMD 連結 → 補發一則錯誤通知說明原因(發送失敗只 log,不影響推進)
      if (!hackmdUrl && outcome.kind !== "ok" && outcome.kind !== "cached") {
        const detail = outcome.kind === "failed" ? outcome.detail : undefined;
        console.error(`HackMD pipeline ${outcome.reason} for ${msg.id}${detail ? `: ${detail}` : ""}`);
        try {
          await discord.postMessage(
            env.TARGET_CHANNEL_ID,
            buildHackMdErrorMessage(msg, outcome.reason, detail),
          );
        } catch (err) {
          console.error(`HackMd error notice failed for ${msg.id}: ${(err as Error).message}`);
        }
      }

      await state.setLastMessageId(msg.id);
      await state.clearRetryCount(msg.id);
    }
  },
};
