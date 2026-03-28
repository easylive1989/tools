/**
 * md-to-data.js
 * 把 itinerary.md 轉換成 src/data/itinerary.js
 */

import { readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const root = join(__dirname, '..');

const mdPath = join(root, 'itinerary.md');
const outPath = join(root, 'src', 'data', 'itinerary.js');

const content = readFileSync(mdPath, 'utf8');
const lines = content.split('\n');

// ─── 工具函式 ────────────────────────────────────────────────

/**
 * 解析 markdown table，回傳 phrase 物件陣列
 * 跳過 header 行（含 `---`）
 */
function parseTable(tableLines) {
  const result = [];
  for (const line of tableLines) {
    if (!line.startsWith('|')) continue;
    if (line.match(/^[\s|:-]+$/)) continue; // separator row
    const cols = line
      .split('|')
      .map((c) => c.trim())
      .filter((c) => c !== '');
    if (cols.length < 3) continue;
    // 如果第一欄是「中文」，代表是 header，跳過
    if (cols[0] === '中文') continue;
    result.push({
      zh: cols[0].replace(/\\\|/g, '|'),
      en: cols[1].replace(/\\\|/g, '|'),
      category: cols[2],
    });
  }
  return result;
}

/**
 * 解析 #### header，回傳 { time, type, icon, title }
 * 格式：#### [TIME] type icon Title...
 */
function parseEventHeader(headerText) {
  // 移除開頭的 #### 和空白
  const text = headerText.replace(/^####\s*/, '').trim();

  // 擷取 [TIME]
  const timeMatch = text.match(/^\[([^\]]+)\]\s*/);
  if (!timeMatch) return null;
  const time = timeMatch[1];
  const rest = text.slice(timeMatch[0].length).trim();

  // 接著是 type（英文字母）
  const typeMatch = rest.match(/^(\w+)\s*/);
  if (!typeMatch) return null;
  const type = typeMatch[1];
  const rest2 = rest.slice(typeMatch[0].length).trim();

  // 接著是 emoji icon（可能是多個 unicode 字元組成的 emoji）
  // 用正則抓第一個 emoji segment（非空白字元且不是 ASCII 字母數字）
  const emojiMatch = rest2.match(/^(\S+)\s*/);
  if (!emojiMatch) return null;
  const icon = emojiMatch[1];
  const title = rest2.slice(emojiMatch[0].length).trim();

  return { time, type, icon, title };
}

// ─── 解析主體 ────────────────────────────────────────────────

let commonPhrases = [];
const days = [];

// 狀態機
let state = 'global'; // global | commonPhrases | day
let currentDay = null;
let currentSection = null; // highlights | hotel | events | phrases
let currentEvent = null;
let commonPhrasesLines = [];
let phrasesLines = [];
let hotelLines = [];

function finalizeEvent() {
  if (currentEvent && currentDay) {
    currentDay.events.push(currentEvent);
    currentEvent = null;
  }
}

function finalizeDay() {
  if (currentDay) {
    // 處理最後一個 event
    finalizeEvent();
    days.push(currentDay);
    currentDay = null;
  }
}

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];

  // ── H1：手冊標題（忽略，只需辨識位置）
  if (line.startsWith('# ') && !line.startsWith('## ')) {
    state = 'global';
    continue;
  }

  // ── H2：各大區塊
  if (line.startsWith('## ')) {
    // 先結束上一個 day
    finalizeDay();
    currentSection = null;

    if (line === '## 通用字卡') {
      state = 'commonPhrases';
      commonPhrasesLines = [];
      continue;
    }

    // 每天：## 第 N 天｜日期｜標題｜flag｜城市
    const dayMatch = line.match(/^## 第\s*(\d+)\s*天｜(.+?)｜(.+?)｜(.+?)｜(.+)$/);
    if (dayMatch) {
      state = 'day';
      currentDay = {
        day: parseInt(dayMatch[1], 10),
        date: dayMatch[2].trim(),
        title: dayMatch[3].trim(),
        flag: dayMatch[4].trim(),
        city: dayMatch[5].trim(),
        highlights: [],
        hotel: null,
        events: [],
        phrases: [],
      };
      continue;
    }

    continue;
  }

  // ── 收集通用字卡 table
  if (state === 'commonPhrases') {
    if (line.startsWith('|')) {
      commonPhrasesLines.push(line);
    } else if (line.trim() === '---' || line.startsWith('## ')) {
      commonPhrases = parseTable(commonPhrasesLines);
      // 如果是 ---，繼續往下；如果是 ##，i 需要重新處理（不過這裡已經在 for loop 底部，下一次迭代會處理）
    }
    continue;
  }

  // ── 在 day 內部
  if (state === 'day' && currentDay) {
    // H3 子區塊
    if (line.startsWith('### ')) {
      finalizeEvent(); // 結束上一個 event（如果有）
      const section = line.replace(/^### /, '').trim();
      if (section === '今日重點') {
        currentSection = 'highlights';
      } else if (section === '飯店') {
        currentSection = 'hotel';
        hotelLines = [];
        currentDay.hotel = {};
      } else if (section === '行程') {
        currentSection = 'events';
      } else if (section === '英文字卡') {
        currentSection = 'phrases';
        phrasesLines = [];
      }
      continue;
    }

    // ── 今日重點
    if (currentSection === 'highlights') {
      if (line.startsWith('- ')) {
        currentDay.highlights.push(line.slice(2).trim());
      }
      continue;
    }

    // ── 飯店
    if (currentSection === 'hotel') {
      if (line.startsWith('名稱：')) {
        currentDay.hotel.name = line.slice(3).trim();
      } else if (line.startsWith('地址：')) {
        currentDay.hotel.address = line.slice(3).trim();
      } else if (line.startsWith('地圖：')) {
        currentDay.hotel.mapUrl = line.slice(3).trim();
      } else if (line.startsWith('備註：')) {
        const note = line.slice(3).trim();
        if (!currentDay.hotel.notes) {
          currentDay.hotel.notes = [];
        }
        currentDay.hotel.notes.push(note);
      }
      continue;
    }

    // ── 行程
    if (currentSection === 'events') {
      // H4 event header
      if (line.startsWith('#### ')) {
        finalizeEvent();
        const parsed = parseEventHeader(line);
        if (parsed) {
          currentEvent = {
            time: parsed.time,
            type: parsed.type,
            icon: parsed.icon,
            title: parsed.title,
            subtitle: null,
            notes: [],
          };
        }
        continue;
      }

      if (currentEvent) {
        if (line.startsWith('📍 ')) {
          currentEvent.mapUrl = line.slice(3).trim();
        } else if (line.startsWith('- ')) {
          currentEvent.notes.push(line.slice(2).trim());
        } else if (line.trim() !== '' && !line.startsWith('#')) {
          // 第一個非空、非特殊行是 subtitle（只取第一行）
          if (currentEvent.subtitle === null) {
            currentEvent.subtitle = line.trim();
          }
        }
      }
      // 讓 `---` 可以走到下面的分隔線處理
      if (line.trim() !== '---') continue;
    }

    // ── 英文字卡
    if (currentSection === 'phrases') {
      if (line.startsWith('|')) {
        phrasesLines.push(line);
      }
      // 不在這裡 continue，讓 `---` 可以走到下面的分隔線處理
      if (line.trim() !== '---') continue;
    }
  }

  // ── 分隔線：結束一天（phrases 需要先解析）
  if (line.trim() === '---') {
    if (state === 'commonPhrases') {
      commonPhrases = parseTable(commonPhrasesLines);
      state = 'global';
    } else if (state === 'day' && currentDay) {
      // 解析 phrases
      if (phrasesLines.length > 0) {
        currentDay.phrases = parseTable(phrasesLines);
        phrasesLines = [];
      }
      finalizeDay();
      state = 'global';
    }
    continue;
  }
}

// 確保最後一天也被處理
if (state === 'day' && currentDay) {
  if (phrasesLines.length > 0) {
    currentDay.phrases = parseTable(phrasesLines);
  }
  finalizeDay();
}

// ─── 清理 event 物件 ────────────────────────────────────────

function cleanEvent(ev) {
  const obj = {
    time: ev.time,
    type: ev.type,
    icon: ev.icon,
    title: ev.title,
  };
  if (ev.subtitle) obj.subtitle = ev.subtitle;
  if (ev.mapUrl) obj.mapUrl = ev.mapUrl;
  obj.notes = ev.notes || [];
  return obj;
}

// ─── 產生 JS 輸出 ────────────────────────────────────────────

function jsString(s) {
  if (s === null || s === undefined) return 'null';
  // 使用單引號，並 escape 內部的單引號
  return "'" + s.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
}

function jsStringArray(arr) {
  if (!arr || arr.length === 0) return '[]';
  return '[\n' + arr.map((s) => `          ${jsString(s)},`).join('\n') + '\n        ]';
}

function renderPhraseObj(p) {
  return `  { zh: ${jsString(p.zh)}, en: ${jsString(p.en)}, category: ${jsString(p.category)} }`;
}

function renderEventObj(ev) {
  const clean = cleanEvent(ev);
  const lines = [];
  lines.push('      {');
  lines.push(`        time: ${jsString(clean.time)},`);
  lines.push(`        type: ${jsString(clean.type)},`);
  lines.push(`        icon: ${jsString(clean.icon)},`);
  lines.push(`        title: ${jsString(clean.title)},`);
  if (clean.subtitle !== undefined) {
    lines.push(`        subtitle: ${jsString(clean.subtitle)},`);
  }
  if (clean.mapUrl !== undefined) {
    lines.push(`        mapUrl: ${jsString(clean.mapUrl)},`);
  }
  lines.push(`        notes: ${jsStringArray(clean.notes)},`);
  lines.push('      }');
  return lines.join('\n');
}

function renderHotel(hotel) {
  if (!hotel) return 'null';
  const lines = [];
  lines.push('    {');
  lines.push(`      name: ${jsString(hotel.name)},`);
  if (hotel.address) lines.push(`      address: ${jsString(hotel.address)},`);
  if (hotel.mapUrl) lines.push(`      mapUrl: ${jsString(hotel.mapUrl)},`);
  if (hotel.notes && hotel.notes.length > 0) {
    lines.push(`      notes: ${jsStringArray(hotel.notes)},`);
  }
  lines.push('    }');
  return lines.join('\n');
}

function renderDayObj(day) {
  const lines = [];
  lines.push('  {');
  lines.push(`    day: ${day.day},`);
  lines.push(`    date: ${jsString(day.date)},`);
  lines.push(`    title: ${jsString(day.title)},`);
  lines.push(`    city: ${jsString(day.city)},`);
  lines.push(`    flag: ${jsString(day.flag)},`);

  // highlights
  lines.push(`    highlights: [`);
  for (const h of day.highlights) {
    lines.push(`      ${jsString(h)},`);
  }
  lines.push(`    ],`);

  // hotel
  if (day.hotel) {
    lines.push(`    hotel: ${renderHotel(day.hotel)},`);
  }

  // events
  lines.push(`    events: [`);
  for (const ev of day.events) {
    lines.push(renderEventObj(ev) + ',');
  }
  lines.push(`    ],`);

  // phrases
  lines.push(`    phrases: [`);
  for (const p of day.phrases) {
    lines.push(`      ${renderPhraseObj(p)},`);
  }
  lines.push(`    ],`);

  lines.push('  }');
  return lines.join('\n');
}

// ─── 組合輸出 ────────────────────────────────────────────────

const output = [
  `export const commonPhrases = [`,
  commonPhrases.map(renderPhraseObj).join(',\n'),
  `]`,
  ``,
  `export const days = [`,
  days.map(renderDayObj).join(',\n'),
  `]`,
  ``,
].join('\n');

writeFileSync(outPath, output, 'utf8');
console.log(`已產生 src/data/itinerary.js（${days.length} 天，${commonPhrases.length} 個通用字卡）`);
days.forEach((d) => {
  console.log(`  第 ${d.day} 天：${d.events.length} 個事件，${d.phrases.length} 個字卡`);
});
