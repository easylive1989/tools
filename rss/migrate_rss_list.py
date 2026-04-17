#!/usr/bin/env python3
"""一次性遷移工具：將 rss_list.txt 轉換為 rss_list.json。"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TXT_FILE = os.path.join(BASE_DIR, "rss_list.txt")
JSON_FILE = os.path.join(BASE_DIR, "rss_list.json")


def parse_rss_list_txt(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [l.rstrip() for l in f.readlines()]

    feeds = []
    current_section = "未分類"
    pending_comments = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 空行：若只有一個待處理的 comment，視為分類標題
            if len(pending_comments) == 1:
                current_section = pending_comments[0]
            pending_comments = []
        elif stripped.startswith("#"):
            text = stripped.lstrip("#").strip()
            if text:
                pending_comments.append(text)
        else:
            # URL 行
            url = stripped
            if len(pending_comments) >= 2:
                # 最後兩個：倒數第二為分類，最後為名稱
                current_section = pending_comments[-2]
                name = pending_comments[-1]
            elif len(pending_comments) == 1:
                name = pending_comments[0]
            else:
                name = url
            feeds.append({
                "name": name,
                "url": url,
                "section": current_section,
                "auto_translate": False,
            })
            pending_comments = []

    return feeds


def main():
    if not os.path.exists(TXT_FILE):
        print(f"找不到 {TXT_FILE}，請確認路徑是否正確。")
        return

    if os.path.exists(JSON_FILE):
        ans = input(f"{JSON_FILE} 已存在，是否覆蓋？(y/N) ").strip().lower()
        if ans != "y":
            print("已取消。")
            return

    feeds = parse_rss_list_txt(TXT_FILE)
    data = {"feeds": feeds}

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"遷移完成！共 {len(feeds)} 個來源 → {JSON_FILE}")
    print("原始 rss_list.txt 保留作為備份，確認無誤後可自行刪除。")


if __name__ == "__main__":
    main()
