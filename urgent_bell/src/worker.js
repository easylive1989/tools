/**
 * 老公急事鈴（免費版：LINE + Bark + Cloudflare Workers）
 *
 * 老婆在 LINE 傳訊息給專用官方帳號
 *   → 這支 Worker 收到 LINE webhook
 *   → 用 Bark 推播到老公的 iPhone（時效性通知，可穿過專注模式，但不穿透靜音）
 *   → 沒點開就每隔幾分鐘再推一次（Durable Object 的 alarm 負責計時）
 *   → 老公點開通知 → 開啟 /ack 頁面 → 用 LINE 告訴老婆「老公看到了」
 *   → 超過時間都沒點開 → 用 LINE 告訴老婆「急的話直接打電話」
 *
 * Secrets（用 `npx wrangler secret put <NAME>` 設定）：
 *   LINE_CHANNEL_SECRET        LINE Messaging API 的 Channel secret（驗證 webhook 簽章）
 *   LINE_CHANNEL_ACCESS_TOKEN  LINE Messaging API 的 Channel access token
 *   BARK_KEY                   Bark App 裡的推播 key
 *   CALLBACK_SECRET            自己產生的一串亂碼，保護確認網址
 *   WIFE_USER_ID               老婆的 LINE userId（還沒設定前是「設定模式」）
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
const DEFAULT_BARK_SERVER = 'https://api.day.app';
const BARK_BODY_LIMIT = 1000;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/line/webhook') {
      return handleLineWebhook(request, env, ctx, url);
    }
    if (request.method === 'GET' && url.pathname === '/ack') {
      return handleAck(env, url);
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
      const { text, origin } = await request.json();
      const now = Date.now();
      const pending = {
        text,
        origin,
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
        this.env.WIFE_USER_ID,
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

  // 設定模式：還沒設定 WIFE_USER_ID 時，回覆對方的 userId
  if (!env.WIFE_USER_ID) {
    console.log(`[setup] LINE userId: ${userId}`);
    await lineReply(env, event.replyToken, ['🔧 設定模式', '請把下面這串 ID 傳給老公：', userId].join('\n'));
    return;
  }

  // 不是老婆就不理會（但留下 log，換人設定時可以用 `npm run logs` 看到對方的 ID）
  if (userId !== env.WIFE_USER_ID) {
    console.log(`[ignored] LINE userId: ${userId}`);
    return;
  }

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
      body: JSON.stringify({ text, origin }),
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
}

function describeMessage(message = {}) {
  switch (message.type) {
    case 'text':
      return message.text || '(空白訊息)';
    case 'image':
      return '📷 傳了一張照片，請打開 LINE 看';
    case 'video':
      return '🎬 傳了一段影片，請打開 LINE 看';
    case 'audio':
      return '🎤 傳了一段語音，請打開 LINE 聽';
    case 'file':
      return `📎 傳了一個檔案：${message.fileName || ''}`.trim();
    case 'location':
      return `📍 傳了位置：${[message.title, message.address].filter(Boolean).join(' ') || '請打開 LINE 看'}`;
    case 'sticker':
      return '傳了一張貼圖，請打開 LINE 看';
    default:
      return '傳了一則訊息，請打開 LINE 看';
  }
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
  const pushed = await linePush(env, env.WIFE_USER_ID, `老公 ${time} 看到了 ✅`);

  const status = pushed
    ? '<h1>✅ 已經告訴老婆你看到了</h1>'
    : '<h1>⚠️ 回報失敗</h1><p>提醒已經停止，但沒能通知她，請直接回她 LINE。</p>';

  return htmlPage(
    '老婆找你',
    `${status}
     <blockquote>${escapeHtml(pending.text)}</blockquote>
     <p>記得回她喔。</p>
     <a class="btn" href="line://">打開 LINE</a>`,
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
  .btn { display: inline-block; margin-top: 8px; padding: 12px 20px; border-radius: 999px; background: #06c755;
         color: #fff; text-decoration: none; font-weight: 600; }
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
    body: truncate(pending.text, BARK_BODY_LIMIT),
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

// ---------- helpers ----------

async function verifyLineSignature(body, signature, channelSecret) {
  if (!signature || !channelSecret) return false;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(channelSecret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, enc.encode(body));
  return safeEqual(toBase64(new Uint8Array(mac)), signature);
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
