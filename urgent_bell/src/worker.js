/**
 * 老公急事鈴（免費版：LINE + Bark + Cloudflare Workers）
 *
 * 老婆在 LINE 傳訊息給專用官方帳號（任何人一對一傳訊息都當成老婆）
 *   → 這支 Worker 收到 LINE webhook
 *   → 用 Bark 推播到老公的 iPhone（時效性通知，可穿過專注模式，但不穿透靜音）
 *   → 完整訊息（文字、照片、影片、語音、檔案）轉貼到 Discord 頻道，Bark 只顯示「有新訊息」
 *   → 沒點開就每隔幾分鐘再推一次（Durable Object 的 alarm 負責計時）
 *   → 老公點開通知 → 開啟 /ack 頁面 → 用 LINE 告訴老婆「老公看到了」，頁面上有按鈕打開 Discord
 *   → 超過時間都沒點開 → 用 LINE 告訴老婆「急的話直接打電話」
 *
 * Secrets（用 `npx wrangler secret put <NAME>` 設定）：
 *   LINE_CHANNEL_SECRET        LINE Messaging API 的 Channel secret（驗證 webhook 簽章）
 *   LINE_CHANNEL_ACCESS_TOKEN  LINE Messaging API 的 Channel access token
 *   BARK_KEY                   Bark App 裡的推播 key
 *   CALLBACK_SECRET            自己產生的一串亂碼，保護確認網址和 /media 下載連結
 *   DISCORD_WEBHOOK_URL        轉貼完整訊息的 Discord webhook（沒設定就把文字直接放在 Bark 通知裡）
 *
 * Vars（在 wrangler.toml 調整）：
 *   RETRY_SECONDS   沒點開時多久再提醒一次（秒，最少 30）
 *   EXPIRE_SECONDS  最多持續提醒多久（秒），時間到會告訴老婆
 *   ALERT_TITLE     通知標題
 *   BARK_LEVEL      active / timeSensitive / critical
 *   BARK_SOUND      Bark 鈴聲名稱（留空用預設）
 *   BARK_CALL       "1" = 鈴聲連續響 30 秒
 *   BARK_SERVER     Bark 伺服器（預設官方 https://api.day.app，可換成自架的）
 */

const DEFAULT_LINE_API = 'https://api.line.me/v2/bot';
const DEFAULT_LINE_DATA_API = 'https://api-data.line.me/v2/bot';
const DEFAULT_BARK_SERVER = 'https://api.day.app';
const BARK_BODY_LIMIT = 1000;
const BARK_DISCORD_BODY = '有新訊息，點開後到 Discord 看';
const DISCORD_CONTENT_LIMIT = 2000;
// Discord 沒加成的伺服器上傳上限；超過就改貼 /media 下載連結
const DISCORD_UPLOAD_LIMIT = 10 * 1024 * 1024;
// 影片、語音 LINE 要先轉檔，還沒好會回 202；最多等 8 次
const CONTENT_ATTEMPTS = 8;
const MEDIA_TYPES = new Set(['image', 'video', 'audio', 'file']);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/line/webhook') {
      return handleLineWebhook(request, env, ctx, url);
    }
    if (request.method === 'GET' && url.pathname === '/ack') {
      return handleAck(env, url);
    }
    if (request.method === 'GET' && url.pathname.startsWith('/media/')) {
      return handleMedia(env, url);
    }
    if (request.method === 'GET' && url.pathname === '/') {
      return new Response('urgent-bell is running');
    }
    return new Response('Not found', { status: 404 });
  },
};

// ---------- 提醒狀態（Durable Object：只有一個實例，負責計時與重複提醒） ----------

export class AlertState {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);

    // 開始一個新的提醒（取代還沒確認的舊提醒）
    if (pathname === '/start') {
      const { text, origin, userId } = await request.json();
      const now = Date.now();
      const pending = {
        text,
        origin,
        userId,
        count: 1,
        firstSentAt: now,
        expireAt: now + expireSeconds(this.env) * 1000,
      };
      const ok = await sendBark(this.env, pending);
      if (!ok) return Response.json({ ok: false });

      await this.state.storage.put('pending', pending);
      await this.state.storage.setAlarm(Math.min(now + retrySeconds(this.env) * 1000, pending.expireAt));
      return Response.json({ ok: true });
    }

    // 老公點開通知：結束提醒，回傳那則訊息
    if (pathname === '/ack') {
      const pending = await this.state.storage.get('pending');
      if (!pending) return Response.json({ pending: null });
      await this.state.storage.delete('pending');
      await this.state.storage.deleteAlarm();
      return Response.json({ pending });
    }

    return new Response('Not found', { status: 404 });
  }

  // 計時到：再提醒一次，或是時間到了告訴老婆
  async alarm() {
    const pending = await this.state.storage.get('pending');
    if (!pending) return;

    const now = Date.now();
    if (now >= pending.expireAt) {
      await this.state.storage.delete('pending');
      const minutes = Math.round((pending.expireAt - pending.firstSentAt) / 60000);
      await linePush(
        this.env,
        pending.userId,
        `他 ${minutes} 分鐘內都還沒點開通知 😥\n如果很急，直接打電話給他吧。`,
      );
      return;
    }

    pending.count += 1;
    await sendBark(this.env, pending);
    await this.state.storage.put('pending', pending);
    await this.state.storage.setAlarm(Math.min(now + retrySeconds(this.env) * 1000, pending.expireAt));
  }
}

function alertStub(env) {
  return env.ALERTS.get(env.ALERTS.idFromName('wife'));
}

function retrySeconds(env) {
  return Math.max(30, Number(env.RETRY_SECONDS) || 300);
}

function expireSeconds(env) {
  return Math.max(60, Number(env.EXPIRE_SECONDS) || 3600);
}

// ---------- LINE webhook ----------

async function handleLineWebhook(request, env, ctx, url) {
  const body = await request.text();
  const signature = request.headers.get('x-line-signature');

  if (!(await verifyLineSignature(body, signature, env.LINE_CHANNEL_SECRET))) {
    return new Response('Bad signature', { status: 401 });
  }

  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    return new Response('Bad JSON', { status: 400 });
  }

  // LINE 建議盡快回 200，實際處理放到背景
  const events = Array.isArray(payload.events) ? payload.events : [];
  ctx.waitUntil(
    Promise.all(
      events.map((event) =>
        handleEvent(event, env, url.origin).catch((err) => console.error('handleEvent failed', err)),
      ),
    ),
  );

  return new Response('OK');
}

async function handleEvent(event, env, origin) {
  // 只處理一對一聊天（不處理群組）
  if (event.source?.type !== 'user') return;
  const userId = event.source.userId;

  if (event.type === 'follow') {
    await lineReply(
      env,
      event.replyToken,
      [
        '這裡是老公急事鈴 🔔',
        '有需要他盡快看到的事，就傳到這裡。',
        '他點開通知後，我會跟妳說「他看到了」。',
        '真的很緊急（安全、健康）還是直接打電話喔！',
      ].join('\n'),
    );
    return;
  }

  if (event.type !== 'message') return;

  const text = describeMessage(event.message);
  let ok = false;
  try {
    const res = await alertStub(env).fetch('https://alert/start', {
      method: 'POST',
      body: JSON.stringify({ text, origin, userId }),
    });
    ok = (await res.json()).ok === true;
  } catch (err) {
    console.error('start alert failed', err);
  }

  await lineReply(
    env,
    event.replyToken,
    ok
      ? '收到，已經通知老公了 🔔\n他點開通知後我會跟妳說。'
      : '通知沒有送出去 😢\n有急事請直接打電話給他。',
  );

  // 通知送出後才轉貼 Discord：下載影片可能要等幾秒，不能拖慢 Bark
  try {
    await forwardToDiscord(env, event, origin);
  } catch (err) {
    console.error('forward to Discord failed', err);
  }
}

function describeMessage(message = {}) {
  switch (message.type) {
    case 'text':
      return message.text || '(空白訊息)';
    case 'image':
      return '📷 傳了一張照片';
    case 'video':
      return '🎬 傳了一段影片';
    case 'audio':
      return '🎤 傳了一段語音';
    case 'file':
      return `📎 傳了一個檔案：${message.fileName || ''}`.trim();
    case 'location':
      return `📍 傳了位置：${[message.title, message.address].filter(Boolean).join(' ')}`.trim();
    case 'sticker':
      return '傳了一張貼圖';
    default:
      return '傳了一則訊息';
  }
}

// ---------- Discord（完整訊息） ----------

async function forwardToDiscord(env, event, origin) {
  if (!env.DISCORD_WEBHOOK_URL) return;
  const message = event.message || {};
  const name = await lineDisplayName(env, event.source.userId);
  let content = `**${name}** ${formatTaipeiTime(event.timestamp || Date.now())}\n${describeMessage(message)}`;
  if (message.type === 'location' && message.latitude != null) {
    content += `\nhttps://www.google.com/maps/search/?api=1&query=${message.latitude},${message.longitude}`;
  }

  if (!MEDIA_TYPES.has(message.type)) {
    await discordPost(env, content);
    return;
  }

  const res = await lineContentWhenReady(env, message.id);
  if (res?.ok) {
    const size = Number(res.headers.get('content-length')) || 0;
    if (size > DISCORD_UPLOAD_LIMIT) {
      await res.body?.cancel();
    } else {
      const blob = await res.blob();
      if (blob.size <= DISCORD_UPLOAD_LIMIT && (await discordPost(env, content, { blob, name: mediaFileName(message, blob.type) }))) {
        return;
      }
    }
  } else if (res) {
    console.error('LINE content failed', res.status);
    await res.body?.cancel();
  }

  // 太大、還在轉檔、或上傳失敗：改貼由這支 Worker 代理的下載連結
  const link = `${origin}/media/${encodeURIComponent(message.id)}?sig=${await mediaSignature(env, message.id)}`;
  await discordPost(env, `${content}\n（沒辦法直接上傳，點這裡看：${link} ）`);
}

async function discordPost(env, content, file) {
  const payload = {
    content: truncate(content, DISCORD_CONTENT_LIMIT),
    allowed_mentions: { parse: [] },
  };
  let init;
  if (file) {
    const form = new FormData();
    form.append('payload_json', JSON.stringify(payload));
    form.append('files[0]', file.blob, file.name);
    init = { method: 'POST', body: form };
  } else {
    init = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) };
  }
  try {
    const res = await fetch(env.DISCORD_WEBHOOK_URL, init);
    if (!res.ok) {
      console.error('Discord post failed', res.status, await res.text());
      return false;
    }
    return true;
  } catch (err) {
    console.error('Discord post error', err);
    return false;
  }
}

// webhook 本身就記著伺服器和頻道，確認頁用它組出「打開 Discord」的連結
async function discordChannelUrl(env) {
  if (!env.DISCORD_WEBHOOK_URL) return null;
  try {
    const res = await fetch(env.DISCORD_WEBHOOK_URL);
    if (!res.ok) return null;
    const { guild_id: guildId, channel_id: channelId } = await res.json();
    return guildId && channelId ? `https://discord.com/channels/${guildId}/${channelId}` : null;
  } catch (err) {
    console.error('Discord webhook lookup error', err);
    return null;
  }
}

function mediaFileName(message, contentType = '') {
  if (message.type === 'file' && message.fileName) return message.fileName;
  const byType = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'video/mp4': 'mp4', 'audio/x-m4a': 'm4a', 'audio/m4a': 'm4a', 'audio/mp4': 'm4a' };
  const ext = byType[contentType.split(';')[0].trim()] || { image: 'jpg', video: 'mp4', audio: 'm4a' }[message.type] || 'bin';
  return `${message.type}-${message.id}.${ext}`;
}

// ---------- 媒體下載連結（Discord 放不下的檔案） ----------

async function handleMedia(env, url) {
  const messageId = decodeURIComponent(url.pathname.slice('/media/'.length));
  const sig = url.searchParams.get('sig') || '';
  if (!messageId || !env.CALLBACK_SECRET || !safeEqual(sig, await mediaSignature(env, messageId))) {
    return new Response('連結無效', { status: 403, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }

  const res = await lineContent(env, messageId);
  if (res.status === 202) {
    await res.body?.cancel();
    return new Response('LINE 還在處理這個檔案，過幾秒再重新整理', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '5' },
    });
  }
  if (!res.ok) {
    await res.body?.cancel();
    return new Response('找不到這個檔案，可能已經過期了', { status: 404, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }
  return new Response(res.body, {
    headers: {
      'Content-Type': res.headers.get('content-type') || 'application/octet-stream',
      'Cache-Control': 'private, max-age=3600',
    },
  });
}

async function mediaSignature(env, messageId) {
  const mac = await hmacSha256(env.CALLBACK_SECRET, `media:${messageId}`);
  return toBase64(mac).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// ---------- 確認頁（老公點開 Bark 通知時打開） ----------

async function handleAck(env, url) {
  if (!env.CALLBACK_SECRET || !safeEqual(url.searchParams.get('key') || '', env.CALLBACK_SECRET)) {
    return htmlPage('連結無效', '<p>這個連結無效。</p>', 403);
  }

  const res = await alertStub(env).fetch('https://alert/ack', { method: 'POST' });
  const { pending } = await res.json();

  if (!pending) {
    return htmlPage('沒有待確認的訊息', '<h1>👌</h1><p>目前沒有待確認的訊息，可能已經確認過了。</p>');
  }

  const time = formatTaipeiTime(Date.now());
  const [pushed, discordUrl] = await Promise.all([
    linePush(env, pending.userId, `老公 ${time} 看到了 ✅`),
    discordChannelUrl(env),
  ]);

  const status = pushed
    ? '<h1>✅ 已經告訴老婆你看到了</h1>'
    : '<h1>⚠️ 回報失敗</h1><p>提醒已經停止，但沒能通知她，請直接回她 LINE。</p>';
  const discordButton = discordUrl
    ? `<a class="btn discord" href="${escapeHtml(discordUrl)}">打開 Discord 看完整訊息</a>`
    : '';

  return htmlPage(
    '老婆找你',
    `${status}
     <blockquote>${escapeHtml(pending.text)}</blockquote>
     ${discordButton}
     <a class="btn" href="https://line.me/R/nv/chat">打開 LINE 回她</a>`,
  );
}

function htmlPage(title, inner, status = 200) {
  const html = `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "PingFang TC", "Noto Sans TC", sans-serif; margin: 0; padding: 32px 20px;
         background: Canvas; color: CanvasText; line-height: 1.6; }
  main { max-width: 480px; margin: 0 auto; }
  h1 { font-size: 1.4rem; }
  blockquote { margin: 16px 0; padding: 12px 16px; border-radius: 12px; background: rgba(127,127,127,.15);
               white-space: pre-wrap; word-break: break-word; }
  .btn { display: block; margin-top: 12px; padding: 14px 20px; border-radius: 999px; background: #06c755;
         color: #fff; text-decoration: none; font-weight: 600; text-align: center; }
  .btn.discord { background: #5865f2; }
</style>
</head>
<body><main>${inner}</main></body>
</html>`;
  return new Response(html, { status, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

// ---------- Bark ----------

async function sendBark(env, pending) {
  const title = env.ALERT_TITLE || '老婆找你';
  const payload = {
    title: pending.count > 1 ? `${title}（第 ${pending.count} 次提醒）` : title,
    body: env.DISCORD_WEBHOOK_URL ? BARK_DISCORD_BODY : truncate(pending.text, BARK_BODY_LIMIT),
    level: env.BARK_LEVEL || 'timeSensitive',
    group: '老婆急事',
    url: `${pending.origin}/ack?key=${encodeURIComponent(env.CALLBACK_SECRET)}`,
  };
  if (env.BARK_SOUND) payload.sound = env.BARK_SOUND;
  if (env.BARK_CALL === '1') payload.call = '1';

  const server = (env.BARK_SERVER || DEFAULT_BARK_SERVER).replace(/\/+$/, '');
  try {
    const res = await fetch(`${server}/${encodeURIComponent(env.BARK_KEY)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.code !== 200) {
      console.error('Bark push failed', res.status, JSON.stringify(data));
      return false;
    }
    return true;
  } catch (err) {
    console.error('Bark push error', err);
    return false;
  }
}

// ---------- LINE API ----------

async function lineReply(env, replyToken, text) {
  if (!replyToken) return false;
  return lineCall(env, 'message/reply', { replyToken, messages: [{ type: 'text', text }] });
}

async function linePush(env, to, text) {
  if (!to) return false;
  return lineCall(env, 'message/push', { to, messages: [{ type: 'text', text }] });
}

async function lineCall(env, path, payload) {
  const base = env.LINE_API_BASE || DEFAULT_LINE_API;
  try {
    const res = await fetch(`${base}/${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      console.error(`LINE ${path} failed`, res.status, await res.text());
      return false;
    }
    return true;
  } catch (err) {
    console.error(`LINE ${path} error`, err);
    return false;
  }
}

function lineAuth(env) {
  return { Authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}` };
}

async function lineDisplayName(env, userId) {
  const base = env.LINE_API_BASE || DEFAULT_LINE_API;
  try {
    const res = await fetch(`${base}/profile/${encodeURIComponent(userId)}`, { headers: lineAuth(env) });
    if (res.ok) return (await res.json()).displayName || '老婆';
    await res.body?.cancel();
  } catch (err) {
    console.error('LINE profile error', err);
  }
  return '老婆';
}

function lineContent(env, messageId) {
  const base = env.LINE_DATA_API_BASE || DEFAULT_LINE_DATA_API;
  return fetch(`${base}/message/${encodeURIComponent(messageId)}/content`, { headers: lineAuth(env) });
}

// 回傳 LINE 的回應；轉檔一直沒好就回 null
async function lineContentWhenReady(env, messageId) {
  const delayMs = Number(env.CONTENT_RETRY_MS ?? 2000);
  for (let attempt = 0; attempt < CONTENT_ATTEMPTS; attempt++) {
    const res = await lineContent(env, messageId);
    if (res.status !== 202) return res;
    await res.body?.cancel();
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return null;
}

// ---------- helpers ----------

async function hmacSha256(secret, data) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(data)));
}

async function verifyLineSignature(body, signature, channelSecret) {
  if (!signature || !channelSecret) return false;
  return safeEqual(toBase64(await hmacSha256(channelSecret, body)), signature);
}

function toBase64(bytes) {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

function safeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function truncate(text, max) {
  const chars = Array.from(text);
  return chars.length <= max ? text : chars.slice(0, max - 1).join('') + '…';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

function formatTaipeiTime(ms) {
  return new Date(ms).toLocaleTimeString('zh-TW', {
    timeZone: 'Asia/Taipei',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}
