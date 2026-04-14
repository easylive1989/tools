import os
import sys
import json
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from notion_api import NotionApi
from openai import OpenAI


def get_week_date_range():
    tz_gmt8 = timezone(timedelta(hours=8))

    """計算上週日到上週六的日期範圍（適用於週日執行）"""
    today = datetime.now(tz_gmt8)

    # 如果今天是週日（weekday: 0=週一, 6=週日），上週六就是昨天
    if today.weekday() == 6:
        last_saturday = today - timedelta(days=1)
    else:
        # 否則計算上一個週六
        days_since_saturday = (today.weekday() + 2) % 7
        if days_since_saturday == 0:
            days_since_saturday = 7
        last_saturday = today - timedelta(days=days_since_saturday)

    # 上週日 = 上週六 - 6 天
    last_sunday = last_saturday - timedelta(days=6)

    # 設定時間為當天的開始和結束
    start_date = last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = last_saturday.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_date, end_date, last_saturday


def query_daily_notes(notion_api, database_id, start_date, end_date):
    """查詢指定日期範圍內標題包含 'Daily' 的所有頁面"""
    filter_body = {
        "filter": {
            "and": [
                {
                    "property": "Name",  # 假設標題屬性名稱為 Name，可能需要調整
                    "title": {
                        "contains": "Daily"
                    }
                },
                {
                    "property": "Date",  # 假設日期屬性名稱為 Date，可能需要調整
                    "date": {
                        "on_or_after": start_date.isoformat()
                    }
                },
                {
                    "property": "Date",
                    "date": {
                        "on_or_before": end_date.isoformat()
                    }
                }
            ]
        },
        "sorts": [
            {
                "property": "Date",
                "direction": "ascending"
            }
        ]
    }

    response = notion_api.query_database(database_id, filter_body)

    if response.status_code == 200:
        return response.json()["results"]
    else:
        print(f"查詢失敗: {response.status_code}")
        print(response.text)
        return []


def extract_page_content(notion_api, page):
    """提取頁面的標題和內容"""
    page_id = page["id"]

    # 獲取標題
    title = ""
    for prop_name, prop_data in page["properties"].items():
        if prop_data["type"] == "title" and prop_data["title"]:
            title = "".join([text["plain_text"] for text in prop_data["title"]])
            break

    # 獲取頁面內容
    try:
        blocks_response = notion_api.get_block_children(page_id)
        if blocks_response.status_code == 200:
            blocks = blocks_response.json()["results"]
            content = convert_blocks_to_text(blocks)
        else:
            content = ""
    except Exception as e:
        print(f"無法獲取頁面內容: {e}")
        content = ""

    return {
        "title": title,
        "content": content,
        "date": page["properties"].get("Date", {})
    }


def convert_blocks_to_text(blocks):
    """將 Notion blocks 轉換為純文字"""
    text = ""

    for block in blocks:
        block_type = block["type"]

        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
            rich_text = block[block_type].get("rich_text", [])
            text += extract_rich_text(rich_text) + "\n"
        elif block_type in ["bulleted_list_item", "numbered_list_item"]:
            rich_text = block[block_type].get("rich_text", [])
            text += "• " + extract_rich_text(rich_text) + "\n"
        elif block_type == "quote":
            rich_text = block["quote"].get("rich_text", [])
            text += "> " + extract_rich_text(rich_text) + "\n"
        elif block_type == "code":
            rich_text = block["code"].get("rich_text", [])
            text += extract_rich_text(rich_text) + "\n"

    return text


def extract_rich_text(rich_text_array):
    """從 Notion rich text 陣列中提取純文字"""
    if not rich_text_array:
        return ""
    return "".join([text.get("plain_text", "") for text in rich_text_array])


def generate_weekly_summary(daily_notes, openai_api_key):
    """使用 OpenAI 生成週總結"""
    client = OpenAI(api_key=openai_api_key)

    # 準備所有 Daily Notes 的內容
    all_content = ""
    for note in daily_notes:
        all_content += f"\n\n## {note['title']}\n{note['content']}\n"

    # 建立 prompt
    prompt = f"""
你是一位「策略型成長教練」。請用下列結構協助我完成本週工作與成長的總結。不要只是紀錄發生了什麼，而是要抽取本週真正的槓桿、洞察與下週策略聚焦方向。

請根據以下架構輸出：

## 1. 本週關鍵成果（WHAT → WHY）
- 我真正推動了哪件有價值的事情？為什麼有價值？
- 哪個成果對「長期複利」貢獻最大？

## 2. 能力成長（SYSTEM → CAPABILITY）
- 我這週新增／強化了哪些能力？
- 這些能力會如何在未來轉化為決策質量或產出效率？

## 3. 槓桿 & 阻力分析
- 本週最高槓桿行為是什麼？為什麼？
- 本週最大阻力（時間摩擦／心智摩擦）是什麼？來自哪個系統／習慣？
- 未來要如何降低這個阻力？

## 4. 下週策略聚焦（FROM 善用 → 複利）
- 下週我最應該把時間押在什麼事情上（只選 1 個領域）？
- 如果我只能做好一件事，就會望最大化複利，那是哪件事？

## 5. 反脆弱沉澱（INSIGHT）
- 本週「喔原來如此」的一刻是什麼？
- 它對我未來有什麼「可複用原則」？

請依照上述結構產出完整的週回顧。。

一週的工作日誌：
{all_content}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # 使用 GPT-4o 模型
            messages=[
                {"role": "system", "content": "你是一個專業的工作日誌分析助手，擅長從每日記錄中提煉關鍵資訊和成果。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        summary = response.choices[0].message.content
        return summary

    except Exception as e:
        print(f"OpenAI API 錯誤: {e}")
        return None


def create_weekly_note(notion_api, database_id, summary, saturday_date):
    """建立 Weekly Note 到 Notion"""
    # 設定週六晚上 11:00
    saturday_datetime = saturday_date.replace(hour=23, minute=0, second=0, microsecond=0)

    # 準備頁面屬性
    properties = {
        "Name": {  # 假設標題屬性名稱為 Name
            "title": [
                {
                    "text": {
                        "content": "Weekly"
                    }
                }
            ]
        },
        "Date": {  # 假設日期屬性名稱為 Date
            "date": {
                "start": saturday_datetime.isoformat()
            }
        }
    }

    # 建立頁面
    response = notion_api.create_page(database_id, properties)

    if response.status_code == 200:
        page_id = response.json()["id"]
        print(f"成功建立 Weekly Note: {page_id}")

        # 將總結內容加入頁面
        add_summary_to_page(notion_api, page_id, summary)

        return page_id
    else:
        print(f"建立 Weekly Note 失敗: {response.status_code}")
        print(response.text)
        return None


def add_summary_to_page(notion_api, page_id, summary):
    """將總結內容加入到頁面中"""
    # 將 markdown 轉換為 Notion blocks
    # 簡化版本：直接將內容切分為段落
    lines = summary.split('\n')
    children = []

    for line in lines:
        if not line.strip():
            continue

        # 處理標題
        if line.startswith('###'):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]
                }
            })
        elif line.startswith('##'):
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                }
            })
        elif line.startswith('#'):
            children.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": line[1:].strip()}}]
                }
            })
        elif line.startswith('-') or line.startswith('•'):
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[1:].strip()}}]
                }
            })
        else:
            # 普通段落
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }
            })

    if children:
        response = notion_api.append_block_children(page_id, children)
        if response.status_code == 200:
            print("成功加入總結內容")
        else:
            print(f"加入內容失敗: {response.status_code}")
            print(response.text)


def main():
    # 從環境變數獲取 API keys
    notion_token = os.getenv("NOTION_SECRET")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    database_id = "27e8303f78f780ffb569fbe11136b5b0"

    if not notion_token:
        raise ValueError("請設定 NOTION_SECRET 環境變數")
    if not openai_api_key:
        raise ValueError("請設定 OPENAI_API_KEY 環境變數")

    # 初始化 API
    notion_api = NotionApi(notion_token)

    # 計算日期範圍
    start_date, end_date, last_saturday = get_week_date_range()
    print(f"查詢日期範圍: {start_date.date()} 到 {end_date.date()}")

    # 查詢 Daily Notes
    print("正在查詢 Daily Notes...")
    pages = query_daily_notes(notion_api, database_id, start_date, end_date)
    print(f"找到 {len(pages)} 篇 Daily Notes")

    if not pages:
        print("沒有找到任何 Daily Notes，結束執行")
        return

    # 提取每篇 Daily Note 的內容
    print("正在讀取 Daily Notes 內容...")
    daily_notes = []
    for page in pages:
        note = extract_page_content(notion_api, page)
        daily_notes.append(note)
        print(f"  - {note['title']}")

    # 生成週總結
    print("\n正在生成週總結...")
    summary = generate_weekly_summary(daily_notes, openai_api_key)

    if summary:
        print("\n生成的週總結：")
        print("=" * 50)
        print(summary)
        print("=" * 50)

        # 建立 Weekly Note
        print("\n正在建立 Weekly Note...")
        page_id = create_weekly_note(notion_api, database_id, summary, last_saturday)

        if page_id:
            print(f"\n✓ 週總結已成功建立！")
        else:
            print("\n✗ 建立 Weekly Note 失敗")
    else:
        print("\n✗ 生成週總結失敗")


if __name__ == "__main__":
    main()
