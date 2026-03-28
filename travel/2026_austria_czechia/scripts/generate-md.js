/**
 * generate-md.js
 * 把 src/data/itinerary.js 轉換成 itinerary.md
 * 執行一次即可，之後 itinerary.md 為使用者編輯的主要檔案
 */

import { createRequire } from 'module';
import { readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const root = join(__dirname, '..');

// 動態 import itinerary.js
const { commonPhrases, days } = await import('../src/data/itinerary.js');

function renderTable(phrases) {
  const lines = [];
  lines.push('| 中文 | 英文 | 分類 |');
  lines.push('|------|------|------|');
  for (const p of phrases) {
    const zh = p.zh.replace(/\|/g, '\\|');
    const en = p.en.replace(/\|/g, '\\|');
    lines.push(`| ${zh} | ${en} | ${p.category} |`);
  }
  return lines.join('\n');
}

function renderDay(day) {
  const lines = [];

  // Day header: ## 第 N 天｜日期｜標題｜flag｜城市
  lines.push(`## 第 ${day.day} 天｜${day.date}｜${day.title}｜${day.flag}｜${day.city}`);
  lines.push('');

  // 今日重點
  lines.push('### 今日重點');
  for (const h of day.highlights) {
    lines.push(`- ${h}`);
  }
  lines.push('');

  // 飯店
  if (day.hotel) {
    lines.push('### 飯店');
    lines.push(`名稱：${day.hotel.name}`);
    if (day.hotel.address) lines.push(`地址：${day.hotel.address}`);
    if (day.hotel.mapUrl) lines.push(`地圖：${day.hotel.mapUrl}`);
    if (day.hotel.notes) {
      const notesArr = Array.isArray(day.hotel.notes) ? day.hotel.notes : [day.hotel.notes];
      for (const n of notesArr) {
        lines.push(`備註：${n}`);
      }
    }
    lines.push('');
  }

  // 行程
  lines.push('### 行程');
  lines.push('');
  for (const ev of day.events) {
    // #### [TIME] type icon Title
    lines.push(`#### [${ev.time}] ${ev.type} ${ev.icon} ${ev.title}`);
    if (ev.subtitle) {
      lines.push(ev.subtitle);
    }
    if (ev.mapUrl) {
      lines.push(`📍 ${ev.mapUrl}`);
    }
    if (ev.notes && ev.notes.length > 0) {
      for (const n of ev.notes) {
        lines.push(`- ${n}`);
      }
    }
    lines.push('');
  }

  // 英文字卡
  if (day.phrases && day.phrases.length > 0) {
    lines.push('### 英文字卡');
    lines.push('');
    lines.push(renderTable(day.phrases));
    lines.push('');
  }

  return lines.join('\n');
}

const md = [];
md.push('# 奧捷旅遊手冊 2026');
md.push('2026/4/1 – 4/10 · 9天8夜 · 維也納・哈修塔特・薩爾茲堡・庫倫諾夫・布拉格');
md.push('');

// 通用字卡
md.push('## 通用字卡');
md.push('');
md.push(renderTable(commonPhrases));
md.push('');
md.push('---');
md.push('');

// 每天
for (const day of days) {
  md.push(renderDay(day));
  md.push('---');
  md.push('');
}

const output = md.join('\n');
const outPath = join(root, 'itinerary.md');
writeFileSync(outPath, output, 'utf8');
console.log(`已產生 itinerary.md（${output.length} 字元）`);
