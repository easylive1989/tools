import { test, beforeEach, mock } from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import worker, { AlertState } from '../src/worker.js';

const ORIGIN = 'https://urgent-bell.example.workers.dev';
const WIFE = 'Uwife000000000000000000000000000';
const STRANGER = 'Ustranger0000000000000000000000';
const DISCORD = 'https://discord.com/api/webhooks/123/webhook-token';

// LINE 內容 API 的回應（每次呼叫產生新的 Response）
const content = (status, bytes = new Uint8Array([1, 2, 3]), headers = { 'content-type': 'image/jpeg' }) => () =>
  new Response(status === 200 ? bytes : null, { status, headers: status === 200 ? headers : {} });

// ---------- mocks ----------

class MockStorage {
  constructor() {
    this.data = new Map();
    this.alarm = null;
  }
  async get(k) { return this.data.has(k) ? structuredClone(this.data.get(k)) : undefined; }
  async put(k, v) { this.data.set(k, structuredClone(v)); }
  async delete(k) { return this.data.delete(k); }
  async setAlarm(t) { this.alarm = t; }
  async getAlarm() { return this.alarm; }
  async deleteAlarm() { this.alarm = null; }
}

let calls;
let barkResponse;
let lineStatus;
let contentResponses;
let discordStatuses;
let env;
let obj;

beforeEach(() => {
  mock.timers.reset();
  calls = [];
  barkResponse = { code: 200, message: 'success' };
  lineStatus = 200;
  contentResponses = [content(200)];
  discordStatuses = [204];

  env = {
    LINE_CHANNEL_SECRET: 'line-secret',
    LINE_CHANNEL_ACCESS_TOKEN: 'line-token',
    BARK_KEY: 'barkkey',
    CALLBACK_SECRET: 'cb-secret',
    RETRY_SECONDS: '300',
    EXPIRE_SECONDS: '3600',
    ALERT_TITLE: '老婆找你',
    BARK_LEVEL: 'timeSensitive',
    BARK_SOUND: '',
    BARK_CALL: '0',
    BARK_SERVER: 'https://api.day.app',
    CONTENT_RETRY_MS: '0',
  };
  const storage = new MockStorage();
  obj = new AlertState({ storage }, env);
  obj.storage = storage;
  env.ALERTS = {
    idFromName: (name) => `id:${name}`,
    get: () => ({ fetch: (url, init) => obj.fetch(new Request(url, init)) }),
  };

  globalThis.fetch = async (url, init = {}) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (call.url.startsWith('https://api.day.app/')) {
      return new Response(JSON.stringify(barkResponse), { status: barkResponse.code === 200 ? 200 : 400 });
    }
    if (call.url.startsWith('https://api.line.me/v2/bot/profile/')) {
      return new Response(JSON.stringify({ displayName: '小美' }), { status: lineStatus });
    }
    if (call.url.startsWith('https://api.line.me/')) {
      return new Response('{}', { status: lineStatus });
    }
    if (call.url.startsWith('https://api-data.line.me/')) {
      const next = contentResponses.length > 1 ? contentResponses.shift() : contentResponses[0];
      return next();
    }
    if (call.url === DISCORD) {
      if ((init.method || 'GET') === 'GET') return Response.json({ guild_id: 'G1', channel_id: 'C1' });
      const status = discordStatuses.length > 1 ? discordStatuses.shift() : discordStatuses[0];
      return new Response(status === 204 ? null : '{"message":"nope"}', { status });
    }
    throw new Error(`unexpected fetch ${call.url}`);
  };
});

// ---------- helpers ----------

const sign = (body) => createHmac('sha256', env.LINE_CHANNEL_SECRET).update(body).digest('base64');

async function sendWebhook(events, { signature } = {}) {
  const body = JSON.stringify({ destination: 'Ubot', events });
  const pending = [];
  const ctx = { waitUntil: (p) => pending.push(p) };
  const req = new Request(`${ORIGIN}/line/webhook`, {
    method: 'POST',
    headers: { 'x-line-signature': signature ?? sign(body), 'content-type': 'application/json' },
    body,
  });
  const res = await worker.fetch(req, env, ctx);
  await Promise.all(pending);
  return res;
}

const textEvent = (userId, text) => ({
  type: 'message',
  replyToken: 'reply-1',
  timestamp: 1791358200000,
  source: { type: 'user', userId },
  message: { type: 'text', id: '1', text },
});

const barkCalls = () => calls.filter((c) => c.url.startsWith('https://api.day.app/')).map((c) => JSON.parse(c.init.body));
const lineCalls = (path) =>
  calls.filter((c) => c.url === `https://api.line.me/v2/bot/${path}`).map((c) => JSON.parse(c.init.body));

const openAck = (key = 'cb-secret') => worker.fetch(new Request(`${ORIGIN}/ack?key=${key}`), env, { waitUntil() {} });

const mediaEvent = (type) => ({ ...textEvent(WIFE, ''), message: { type, id: 'm1' } });
const contentCalls = () => calls.filter((c) => c.url.startsWith('https://api-data.line.me/'));
const discordPosts = () => calls.filter((c) => c.url === DISCORD && c.init.method === 'POST');
const discordPayload = (c) =>
  JSON.parse(c.init.body instanceof FormData ? c.init.body.get('payload_json') : c.init.body);
const mediaSig = (id) => createHmac('sha256', env.CALLBACK_SECRET).update(`media:${id}`).digest('base64url');

// ---------- webhook ----------

test('rejects a bad signature', async () => {
  const res = await sendWebhook([textEvent(WIFE, 'hi')], { signature: 'nope' });
  assert.equal(res.status, 401);
  assert.equal(calls.length, 0);
});

test('LINE webhook verify (empty events) returns 200', async () => {
  const res = await sendWebhook([]);
  assert.equal(res.status, 200);
  assert.equal(calls.length, 0);
});

test('any one-on-one sender triggers an alert', async () => {
  await sendWebhook([textEvent(STRANGER, 'hi')]);
  assert.equal(barkCalls().length, 1);
  assert.equal((await obj.storage.get('pending')).userId, STRANGER);
  assert.match(lineCalls('message/reply')[0].messages[0].text, /已經通知老公/);
});

test('wife text → Bark push, alarm scheduled, confirmation reply', async () => {
  mock.timers.enable({ apis: ['Date'], now: 1_000_000 });
  await sendWebhook([textEvent(WIFE, '小孩發燒了，回我')]);

  const [push] = barkCalls();
  assert.equal(calls.find((c) => c.url.startsWith('https://api.day.app/')).url, 'https://api.day.app/barkkey');
  assert.equal(push.title, '老婆找你');
  assert.equal(push.body, '小孩發燒了，回我');
  assert.equal(push.level, 'timeSensitive');
  assert.equal(push.url, `${ORIGIN}/ack?key=cb-secret`);
  assert.equal(push.group, '老婆急事');
  assert.equal('sound' in push, false);
  assert.equal('call' in push, false);

  assert.equal(obj.storage.alarm, 1_000_000 + 300_000);
  const pending = await obj.storage.get('pending');
  assert.equal(pending.count, 1);
  assert.equal(pending.expireAt, 1_000_000 + 3_600_000);

  assert.match(lineCalls('message/reply')[0].messages[0].text, /已經通知老公/);
});

test('sound / call / level options are passed through', async () => {
  Object.assign(env, { BARK_SOUND: 'minuet', BARK_CALL: '1', BARK_LEVEL: 'critical' });
  await sendWebhook([textEvent(WIFE, 'x')]);
  const [push] = barkCalls();
  assert.equal(push.sound, 'minuet');
  assert.equal(push.call, '1');
  assert.equal(push.level, 'critical');
});

test('Bark failure tells her to call instead and stores nothing', async () => {
  barkResponse = { code: 400, message: 'failed to get device token' };
  await sendWebhook([textEvent(WIFE, '在嗎')]);
  assert.match(lineCalls('message/reply')[0].messages[0].text, /直接打電話/);
  assert.equal(await obj.storage.get('pending'), undefined);
  assert.equal(obj.storage.alarm, null);
});

test('non-text messages are described; long text is truncated', async () => {
  await sendWebhook([{ ...textEvent(WIFE, ''), message: { type: 'image', id: '2' } }]);
  assert.match(barkCalls()[0].body, /照片/);

  calls = [];
  await sendWebhook([{ ...textEvent(WIFE, ''), message: { type: 'location', id: '3', title: '台中榮總', address: '台中市西屯區' } }]);
  assert.match(barkCalls()[0].body, /台中榮總/);

  calls = [];
  await sendWebhook([textEvent(WIFE, '急'.repeat(3000))]);
  const body = barkCalls()[0].body;
  assert.equal(Array.from(body).length, 1000);
  assert.ok(body.endsWith('…'));
});

test('group chats are ignored', async () => {
  await sendWebhook([{ ...textEvent(WIFE, 'group msg'), source: { type: 'group', groupId: 'G1', userId: WIFE } }]);
  assert.equal(calls.length, 0);
});

test('follow event from wife gets the welcome text, no alert', async () => {
  await sendWebhook([{ type: 'follow', replyToken: 'r', timestamp: 1, source: { type: 'user', userId: WIFE } }]);
  assert.match(lineCalls('message/reply')[0].messages[0].text, /老公急事鈴/);
  assert.equal(barkCalls().length, 0);
});

// ---------- repeat & expire ----------

test('alarm re-sends with a count until expire, then tells her to call', async () => {
  mock.timers.enable({ apis: ['Date'], now: 0 });
  await sendWebhook([textEvent(WIFE, '回電')]);
  calls = [];

  // 5 分鐘後：第 2 次提醒
  mock.timers.setTime(300_000);
  await obj.alarm();
  assert.equal(barkCalls()[0].title, '老婆找你（第 2 次提醒）');
  assert.equal(obj.storage.alarm, 600_000);

  // 55 分鐘：下一次排在 60 分鐘（不超過 expire）
  mock.timers.setTime(3_300_000);
  await obj.alarm();
  assert.equal(obj.storage.alarm, 3_600_000);

  // 60 分鐘：時間到，停止提醒並告訴老婆
  calls = [];
  mock.timers.setTime(3_600_000);
  await obj.alarm();
  assert.equal(barkCalls().length, 0);
  const pushes = lineCalls('message/push');
  assert.equal(pushes.length, 1);
  assert.equal(pushes[0].to, WIFE);
  assert.match(pushes[0].messages[0].text, /60 分鐘內都還沒點開/);
  assert.equal(await obj.storage.get('pending'), undefined);
});

test('a newer message replaces the pending one', async () => {
  mock.timers.enable({ apis: ['Date'], now: 0 });
  await sendWebhook([textEvent(WIFE, '第一則')]);
  mock.timers.setTime(60_000);
  await sendWebhook([textEvent(STRANGER, '第二則')]);
  const pending = await obj.storage.get('pending');
  assert.equal(pending.text, '第二則');
  assert.equal(pending.userId, STRANGER);
  assert.equal(pending.count, 1);
  assert.equal(obj.storage.alarm, 360_000);
});

test('alarm with nothing pending does nothing', async () => {
  await obj.alarm();
  assert.equal(calls.length, 0);
});

// ---------- ack ----------

test('ack with wrong key is rejected', async () => {
  const res = await openAck('wrong');
  assert.equal(res.status, 403);
  assert.equal(calls.length, 0);
});

test('ack stops reminders, tells wife with Taipei time, shows her message', async () => {
  await sendWebhook([textEvent(WIFE, '<b>幫我買牛奶</b>')]);
  calls = [];
  // 2026-10-07 07:30 UTC = 15:30 台北
  mock.timers.enable({ apis: ['Date'], now: 1791358200000 });

  const res = await openAck();
  assert.equal(res.status, 200);
  const html = await res.text();
  assert.match(html, /已經告訴老婆你看到了/);
  assert.match(html, /&lt;b&gt;幫我買牛奶&lt;\/b&gt;/); // escaped

  const pushes = lineCalls('message/push');
  assert.equal(pushes.length, 1);
  assert.equal(pushes[0].to, WIFE);
  assert.equal(pushes[0].messages[0].text, '老公 15:30 看到了 ✅');
  assert.equal(await obj.storage.get('pending'), undefined);
  assert.equal(obj.storage.alarm, null);

  // 再點一次：不會重複通知
  calls = [];
  const again = await openAck();
  assert.match(await again.text(), /沒有待確認的訊息/);
  assert.equal(calls.length, 0);
});

test('ack still stops reminders when LINE push fails, and says so', async () => {
  await sendWebhook([textEvent(WIFE, 'x')]);
  lineStatus = 500;
  const html = await (await openAck()).text();
  assert.match(html, /回報失敗/);
  assert.equal(await obj.storage.get('pending'), undefined);
});

test('unknown paths 404', async () => {
  const res = await worker.fetch(new Request(`${ORIGIN}/nope`), env, { waitUntil() {} });
  assert.equal(res.status, 404);
});

// ---------- Discord ----------

test('with Discord: Bark only says there is a message, the full text goes to Discord', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  await sendWebhook([textEvent(WIFE, '小孩發燒了 @everyone')]);

  assert.equal(barkCalls()[0].body, '有新訊息，點開後到 Discord 看');
  const posts = discordPosts();
  assert.equal(posts.length, 1);
  const payload = discordPayload(posts[0]);
  assert.equal(payload.content, '**小美** 15:30\n小孩發燒了 @everyone');
  assert.deepEqual(payload.allowed_mentions, { parse: [] });
});

test('image is downloaded from LINE and uploaded to Discord as a file', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  await sendWebhook([mediaEvent('image')]);

  const [contentCall] = contentCalls();
  assert.equal(contentCall.url, 'https://api-data.line.me/v2/bot/message/m1/content');
  assert.equal(contentCall.init.headers.Authorization, 'Bearer line-token');

  const [post] = discordPosts();
  const file = post.init.body.get('files[0]');
  assert.equal(file.name, 'image-m1.jpg');
  assert.equal(file.size, 3);
  assert.match(discordPayload(post).content, /照片/);
});

test('video still transcoding (202) is retried before uploading', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  contentResponses = [content(202), content(202), content(200, new Uint8Array(5), { 'content-type': 'video/mp4' })];
  await sendWebhook([mediaEvent('video')]);

  assert.equal(contentCalls().length, 3);
  assert.equal(discordPosts()[0].init.body.get('files[0]').name, 'video-m1.mp4');
});

test('media too large for Discord falls back to a signed /media link', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  contentResponses = [
    content(200, new Uint8Array(1), { 'content-type': 'video/mp4', 'content-length': String(20 * 1024 * 1024) }),
  ];
  await sendWebhook([mediaEvent('video')]);

  const posts = discordPosts();
  assert.equal(posts.length, 1);
  assert.ok(!(posts[0].init.body instanceof FormData));
  assert.ok(discordPayload(posts[0]).content.includes(`${ORIGIN}/media/m1?sig=${mediaSig('m1')}`));
});

test('a rejected Discord upload falls back to the link', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  discordStatuses = [413, 204];
  await sendWebhook([mediaEvent('audio')]);

  const posts = discordPosts();
  assert.equal(posts.length, 2);
  assert.ok(posts[0].init.body instanceof FormData);
  assert.match(discordPayload(posts[1]).content, /\/media\/m1\?sig=/);
});

test('Bark and the LINE reply still go out when Discord is down', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  discordStatuses = [500];
  await sendWebhook([textEvent(WIFE, 'x')]);

  assert.equal(barkCalls().length, 1);
  assert.match(lineCalls('message/reply')[0].messages[0].text, /已經通知老公/);
});

test('/media streams LINE content only with a valid signature', async () => {
  const bad = await worker.fetch(new Request(`${ORIGIN}/media/m1?sig=nope`), env, { waitUntil() {} });
  assert.equal(bad.status, 403);
  assert.equal(contentCalls().length, 0);

  const res = await worker.fetch(new Request(`${ORIGIN}/media/m1?sig=${mediaSig('m1')}`), env, { waitUntil() {} });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('content-type'), 'image/jpeg');
  assert.deepEqual(new Uint8Array(await res.arrayBuffer()), new Uint8Array([1, 2, 3]));
});

test('ack page links to the Discord channel from the webhook', async () => {
  env.DISCORD_WEBHOOK_URL = DISCORD;
  await sendWebhook([textEvent(WIFE, 'x')]);
  const html = await (await openAck()).text();
  assert.match(html, /href="https:\/\/discord\.com\/channels\/G1\/C1"/);
});
