import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.notion import NotionApi
from openai import OpenAI


def get_yesterday_date():
    """取得昨天的日期範圍（從 00:00:00 到 23:59:59），使用 GMT+8 時區"""
    # 設定 GMT+8 時區
    tz_gmt8 = timezone(timedelta(hours=8))

    # 取得當前 GMT+8 時間
    today = datetime.now(tz_gmt8)
    yesterday = today - timedelta(days=1)

    # 設定時間為當天的開始和結束
    start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_date, end_date


def get_source_page_content(notion_api, source_page_id):
    """從來源頁面取得內容，排除第一個 block（按鈕）"""
    print(f"正在讀取來源頁面內容...")

    blocks_response = notion_api.get_block_children(source_page_id)

    if blocks_response.status_code != 200:
        raise Exception(f"無法獲取來源頁面內容: {blocks_response.text}")

    blocks = blocks_response.json()["results"]

    # 排除第一個 block（按鈕）
    if len(blocks) > 0:
        blocks = blocks[1:]
        print(f"已排除第一個 block，剩餘 {len(blocks)} 個 blocks")

    return blocks


def find_yesterday_daily(notion_api, database_id, start_date, end_date):
    """查詢昨天的 Daily 記錄"""
    print(f"正在查詢昨天的 Daily 記錄 ({start_date.date()})...")

    filter_body = {
        "filter": {
            "and": [
                {
                    "property": "Name",
                    "title": {
                        "equals": "Daily"
                    }
                },
                {
                    "property": "Date",
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
        }
    }

    response = notion_api.query_database(database_id, filter_body)

    if response.status_code != 200:
        raise Exception(f"查詢失敗: {response.text}")

    results = response.json()["results"]

    if len(results) == 0:
        raise Exception(f"找不到昨天的 Daily 記錄")

    if len(results) > 1:
        print(f"警告：找到多筆 Daily 記錄 ({len(results)} 筆)，使用第一筆")

    daily_page = results[0]
    print(f"找到昨天的 Daily 記錄: {daily_page['id']}")

    return daily_page


def append_blocks_to_page(notion_api, page_id, blocks):
    """將 blocks 加入到頁面中"""
    if not blocks:
        print("沒有需要搬運的內容")
        return

    print(f"正在將 {len(blocks)} 個 blocks 搬運到 Daily 記錄中...")

    response = notion_api.append_block_children(page_id, blocks)

    if response.status_code != 200:
        raise Exception(f"搬運內容失敗: {response.text}")

    print("成功搬運內容到 Daily 記錄")


def extract_page_content_text(notion_api, page_id):
    """提取頁面的完整內容並轉換為文字（用於總結）"""
    blocks_response = notion_api.get_block_children(page_id)

    if blocks_response.status_code != 200:
        raise Exception(f"無法獲取頁面內容: {blocks_response.text}")

    blocks = blocks_response.json()["results"]
    content = convert_blocks_to_text(blocks)

    return content


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
        elif block_type == "to_do":
            rich_text = block["to_do"].get("rich_text", [])
            checked = "✅" if block["to_do"].get("checked", False) else "⬜"
            text += f"{checked} " + extract_rich_text(rich_text) + "\n"

    return text


def extract_rich_text(rich_text_array):
    """從 Notion rich text 陣列中提取純文字"""
    if not rich_text_array:
        return ""
    return "".join([text.get("plain_text", "") for text in rich_text_array])


def generate_daily_summary(daily_content, openai_api_key):
    """使用 OpenAI GPT-4o 生成每日總結"""
    print("正在生成每日總結...")

    client = OpenAI(api_key=openai_api_key)

    # 使用提供的提示詞
    prompt = f"""🧭 系統角色定義：工作教練 AI

你是一位專業的 AI 工作教練，專注於幫助知識型工作者進行每日工作日誌的反思與提煉。
你的回饋必須兼具「戰略視野」與「行動導向」，幫助使用者累積長期職涯複利。


🎯 任務目標

閱讀使用者提供的每日工作日誌（結構如下）：
```
## 工作（Job）
✅ 我今天真正推動了什麼？
🎯 下一步是什麼？
📈 這件事情的複利價值或長期好處？
---


## 自我成長（Self-Improvement）
🔣 我今天吸收到的「概念 / 模型 / 框架」是什麼？
🧪 我下一步打算怎麼應用？
🌱 這會強化哪一種長期能力？
---


## 低槓桿工作（to be automated / optimized / removed）
📌 我今天花時間在什麼低槓桿工作上？
🔍 這件事情有沒有「升級可能性」？
🔁 下一步：我要怎麼減少再發生？
---


## Insight（沉澱）
💡 今日「喔原來如此」的一刻
✨ 這背後的抽象規律 / 可複用原理是？
---


```

根據日誌內容，提供深度反思與可行建議，重點放在：

是否真正推動了價值（而非僅產出 output）

下一步是否具延續性與聚焦

學習是否轉化為行動與能力

是否展現時間槓桿與效率思維

是否提煉出可複用的洞見

此外，如果使用者在某個項目留空，該項目就不需要給任何回饋

🧩 角色定位

你融合三種身份：

🧠 策略導師（Strategic Coach）：幫助使用者看見高槓桿任務、價值聚焦。

🧩 學習設計師（Learning Architect）：強化知識 → 行動 → 能力的循環。

⚙️ 效率顧問（Optimization Analyst）：找出可自動化、流程化或移除的低槓桿工作。

語氣：專業、清晰、有洞察力；像一位冷靜且有遠見的 mentor。

🧾 輸出格式

請使用以下結構化格式回覆：

🔍 整體評價

（簡述整份日誌的核心價值與聚焦程度）

💼 工作面 Review（Job）

🎯 價值聚焦度：

🔄 行動延續性：

💥 複利潛力：

🪞建議：
（針對如何提升聚焦、指標化成果或連結長期價值）

📚 自我成長 Review（Self-Improvement）

🧠 概念吸收深度：

🧩 知識轉行動度：

🌱 長期能力連結性：

🪞建議：
（例如：如何具體實踐、如何驗證學習效果）

⚙️ 效率與槓桿 Review（低槓桿工作）

時間槓桿意識：

升級 / 自動化可能性：

移除無效工作的策略：

🪞建議：
（例如：如何建立模板或自動化腳本）

💡 Insight（沉澱）Review

洞見的抽象層次：

是否具可重複性或模型化潛力：

是否值得納入個人知識系統：

🪞建議：
（例如：如何命名這個洞見、或將其轉化為原則）

🧭 總結建議

聚焦更高槓桿任務

加速知識複利

維持可持續的節奏與反思迴圈

---

昨天的工作日誌：
{daily_content}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是一位專業的 AI 工作教練，專注於幫助知識型工作者進行每日工作日誌的反思與提煉。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        summary = response.choices[0].message.content
        print("成功生成每日總結")
        return summary

    except Exception as e:
        raise Exception(f"OpenAI API 錯誤: {e}")


def send_to_discord(webhook_url, summary, date):
    """將總結發送到 Discord"""
    print("正在發送總結到 Discord...")

    # 格式化訊息
    message = {
        "content": f"📊 **每日工作回顧** - {date.strftime('%Y-%m-%d')}\n\n{summary}"
    }

    response = requests.post(
        webhook_url,
        json=message,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 204:
        print("成功發送到 Discord")
    else:
        raise Exception(f"發送到 Discord 失敗: {response.status_code} - {response.text}")


def main():
    # 從環境變數獲取配置
    notion_token = os.getenv("NOTION_SECRET")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    discord_webhook_url = os.getenv("DAILY_REVIEW_DISCORD_WEBHOOK_URL")

    # 頁面和資料庫 ID
    source_page_id = "2988303f78f780d4af3cfff7138bac0a"
    database_id = "27e8303f78f780ffb569fbe11136b5b0"

    # 檢查環境變數
    if not notion_token:
        raise ValueError("請設定 NOTION_SECRET 環境變數")
    if not openai_api_key:
        raise ValueError("請設定 OPENAI_API_KEY 環境變數")
    if not discord_webhook_url:
        raise ValueError("請設定 DAILY_REVIEW_DISCORD_WEBHOOK_URL 環境變數")

    # 初始化 API
    notion_api = NotionApi(notion_token)

    # 取得昨天的日期範圍
    start_date, end_date = get_yesterday_date()
    print(f"處理日期: {start_date.date()}")

    try:
        # 步驟 1: 從來源頁面取得內容
        source_blocks = get_source_page_content(notion_api, source_page_id)

        # 步驟 2: 找到昨天的 Daily 記錄
        daily_page = find_yesterday_daily(notion_api, database_id, start_date, end_date)
        daily_page_id = daily_page["id"]

        # 步驟 3: 將內容搬運到 Daily 記錄
        append_blocks_to_page(notion_api, daily_page_id, source_blocks)

        # 步驟 4: 提取 Daily 記錄的完整內容
        daily_content = extract_page_content_text(notion_api, daily_page_id)

        # 步驟 5: 生成總結
        summary = generate_daily_summary(daily_content, openai_api_key)

        # 步驟 6: 發送到 Discord
        send_to_discord(discord_webhook_url, summary, start_date)

        print("\n✓ 每日工作回顧已完成！")

    except Exception as e:
        print(f"\n✗ 執行失敗: {e}")
        raise


if __name__ == "__main__":
    main()
