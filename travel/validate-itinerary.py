#!/usr/bin/env python3
"""
驗證 itinerary.md 是否符合 itinerary-format.md 的規範
用法：python3 validate-itinerary.py <path/to/itinerary.md>
"""

import sys
import re

VALID_CATEGORIES = {"general", "transport", "food", "emergency"}
VALID_EVENT_TYPES = {"transport", "food", "sight", "hotel", "info"}
SHORT_URL_PATTERN = re.compile(r"maps\.app\.goo\.gl")
FULL_MAPS_URL_PATTERN = re.compile(r"https://www\.google\.com/maps")

# 全形直線 U+FF5C
FULL_WIDTH_PIPE = "｜"
ASCII_PIPE = "|"


def error(line_no, msg):
    return {"line": line_no, "msg": msg}


def validate(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    errors = []
    i = 0
    total = len(lines)

    def L(idx):
        return lines[idx].rstrip("\n") if idx < total else ""

    def add(idx, msg):
        errors.append(error(idx + 1, msg))

    # ── 1. 標題區塊 ──────────────────────────────────────────────
    if not L(0).startswith("# "):
        add(0, "第一行必須以 '# ' 開頭（旅程標題）")
    if L(1).startswith("#"):
        add(1, "第二行（副標題）不能以 '#' 開頭")

    # ── 解析整個檔案 ─────────────────────────────────────────────
    found_vocab = False
    day_sections = []   # list of (line_idx, header_line)
    i = 0
    while i < total:
        line = L(i)

        # 通用字卡
        if line.strip() == "## 通用字卡":
            found_vocab = True
            i += 1
            # 空行
            while i < total and L(i).strip() == "":
                i += 1
            # 表頭
            if i < total and "中文" in L(i) and "英文" in L(i) and "分類" in L(i):
                i += 1  # 表頭行
                if i < total and re.match(r"^\|[-| ]+\|$", L(i).strip()):
                    i += 1  # 分隔行
                # 資料列
                while i < total and L(i).strip().startswith("|"):
                    cols = [c.strip() for c in L(i).strip().strip("|").split("|")]
                    if len(cols) >= 3:
                        cat = cols[2].strip()
                        if cat and cat not in VALID_CATEGORIES:
                            add(i, f"通用字卡 分類值 '{cat}' 無效，只允許：{', '.join(sorted(VALID_CATEGORIES))}")
                    i += 1
            else:
                add(i, "通用字卡 表格欄位順序應為 '中文 | 英文 | 分類'")
            continue

        # 天標題（必須有前置 ---）
        if re.match(r"^## 第\s*\d+\s*天", line):
            # 檢查全形直線
            if FULL_WIDTH_PIPE not in line and ASCII_PIPE in line:
                add(i, f"天標題的分隔符應使用全形直線 '｜'（U+FF5C），而非 ASCII '|'")
            elif FULL_WIDTH_PIPE in line:
                parts = line[3:].split(FULL_WIDTH_PIPE)
                if len(parts) < 5:
                    add(i, f"天標題應有 5 個欄位：第 N 天｜日期｜標題｜國旗｜城市（目前只有 {len(parts)} 個）")
                else:
                    # 第 N 天格式
                    day_part = parts[0].strip()
                    if not re.match(r"^第\s+\d+\s+天$", day_part):
                        add(i, f"天標題第一欄格式應為 '第 N 天'（N 為數字，有空格），目前是 '{day_part}'")
            # 檢查前面有沒有 ---
            prev = i - 1
            while prev >= 0 and L(prev).strip() == "":
                prev -= 1
            if prev < 0 or L(prev).strip() != "---":
                add(i, "天標題前面必須有 '---' 水平線")
            day_sections.append(i)

        # 行程項目
        elif line.startswith("#### "):
            content = line[5:]
            # 格式：[時間] 類型 icon? 標題
            m = re.match(r"^\[([^\]]+)\]\s+(\S+)(\s+.*)?$", content)
            if not m:
                add(i, f"行程標頭格式錯誤，應為 '#### [時間] 類型 icon 標題'，目前：'{content}'")
            else:
                event_type = m.group(2).strip()
                if event_type not in VALID_EVENT_TYPES:
                    add(i, f"行程類型 '{event_type}' 無效，只允許：{', '.join(sorted(VALID_EVENT_TYPES))}")

        # 📍 連結
        elif "📍" in line:
            after = line[line.index("📍") + len("📍"):]
            if not after.startswith(" "):
                add(i, "📍 後面必須有一個空格，再接 URL")
            url_match = re.search(r"https?://\S+", after)
            if url_match:
                url = url_match.group(0)
                if SHORT_URL_PATTERN.search(url):
                    add(i, f"不能使用 maps.app.goo.gl 短網址，請使用完整 Google Maps URL")
            else:
                add(i, "📍 後面未找到 URL")

        # 飯店地圖欄位
        elif line.startswith("地圖：") or line.startswith("地图："):
            if line.startswith("地圖："):
                url_part = line[len("地圖："):].strip()
            else:
                url_part = line[len("地图："):].strip()
                add(i, "地圖欄位的冒號應使用全形 '：'")
            if SHORT_URL_PATTERN.search(url_part):
                add(i, "地圖 URL 不能使用 maps.app.goo.gl 短網址，請使用完整 Google Maps URL")
            elif not FULL_MAPS_URL_PATTERN.search(url_part) and url_part:
                add(i, f"地圖 URL 應為完整 Google Maps URL（https://www.google.com/maps/...），目前：'{url_part}'")

        # 飯店欄位冒號檢查（ASCII 冒號誤用）
        for prefix in ["名稱", "地址", "地圖", "備註"]:
            if line.startswith(f"{prefix}:") and not line.startswith(f"{prefix}："):
                add(i, f"'{prefix}' 欄位的冒號應使用全形 '：'，而非 ASCII ':'")

        # 英文字卡表格
        if re.match(r"^\s*\|", line) and "中文" not in line and "---" not in line:
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) >= 3:
                cat = cols[2].strip()
                if cat and cat not in VALID_CATEGORIES:
                    add(i, f"字卡 分類值 '{cat}' 無效，只允許：{', '.join(sorted(VALID_CATEGORIES))}")

        i += 1

    # 通用字卡必須存在
    if not found_vocab:
        errors.append(error(0, "缺少 '## 通用字卡' 區塊"))

    return errors


def main():
    if len(sys.argv) < 2:
        print("用法：python3 validate-itinerary.py <path/to/itinerary.md>")
        sys.exit(1)

    path = sys.argv[1]
    errors = validate(path)

    if not errors:
        print(f"✅ {path} 驗證通過，格式正確！")
    else:
        print(f"❌ {path} 發現 {len(errors)} 個問題：\n")
        for e in errors:
            print(f"  第 {e['line']:4d} 行：{e['msg']}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
