import sys
import os
import requests
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from notion_api import NotionApi


def get_notion_page_content(page_id: str):
    """從 Notion 獲取頁面內容並轉換為 markdown 格式"""
    notion_token = os.getenv("NOTION_SECRET")
    if not notion_token:
        raise ValueError("請設定 NOTION_SECRET 環境變數")

    notion_api = NotionApi(notion_token)
    content = notion_api.get_page_content(page_id)

    return convert_notion_to_markdown(content["page"], content["blocks"])


def convert_notion_to_markdown(page_data, blocks_data):
    """將 Notion 內容轉換為 markdown 格式"""
    markdown_content = ""

    # 獲取標題
    title = ""
    if "properties" in page_data:
        for prop_name, prop_data in page_data["properties"].items():
            if prop_data["type"] == "title" and prop_data["title"]:
                title = "".join([text["plain_text"] for text in prop_data["title"]])
                break

    # 如果有標題，加入 markdown
    if title:
        markdown_content += f"# {title}\n\n"

    # 轉換內容塊
    for block in blocks_data["results"]:
        block_markdown = convert_block_to_markdown(block)
        markdown_content += block_markdown

    # 處理圖片上傳
    markdown_content = process_images_in_markdown(markdown_content)

    return {"title": title, "content": markdown_content, "tags": []}


def convert_block_to_markdown(block):
    """將單個 Notion 塊轉換為 markdown"""
    block_type = block["type"]
    markdown = ""

    if block_type == "paragraph":
        text = extract_rich_text(block["paragraph"]["rich_text"])
        markdown = f"{text}\n\n"

    elif block_type == "heading_1":
        text = extract_rich_text(block["heading_1"]["rich_text"])
        markdown = f"# {text}\n\n"

    elif block_type == "heading_2":
        text = extract_rich_text(block["heading_2"]["rich_text"])
        markdown = f"## {text}\n\n"

    elif block_type == "heading_3":
        text = extract_rich_text(block["heading_3"]["rich_text"])
        markdown = f"### {text}\n\n"

    elif block_type == "bulleted_list_item":
        text = extract_rich_text(block["bulleted_list_item"]["rich_text"])
        markdown = f"- {text}\n"

    elif block_type == "numbered_list_item":
        text = extract_rich_text(block["numbered_list_item"]["rich_text"])
        markdown = f"1. {text}\n"

    elif block_type == "quote":
        text = extract_rich_text(block["quote"]["rich_text"])
        markdown = f"> {text}\n\n"

    elif block_type == "code":
        language = block["code"]["language"] or ""
        text = extract_rich_text(block["code"]["rich_text"])
        markdown = f"```{language}\n{text}\n```\n\n"

    elif block_type == "divider":
        markdown = "---\n\n"

    elif block_type == "image":
        image_data = block["image"]
        image_url = ""
        alt_text = ""

        # 處理不同類型的圖片來源
        if image_data["type"] == "external":
            image_url = image_data["external"]["url"]
        elif image_data["type"] == "file":
            image_url = image_data["file"]["url"]

        # 獲取圖片說明文字
        if image_data.get("caption"):
            alt_text = extract_rich_text(image_data["caption"])

        # 標記圖片需要上傳到 Medium
        markdown = f"![{alt_text}]({image_url})\n\n"

    return markdown


def extract_rich_text(rich_text_array):
    """從 Notion rich text 陣列中提取純文字"""
    if not rich_text_array:
        return ""

    text = ""
    for text_obj in rich_text_array:
        plain_text = text_obj.get("plain_text", "")

        # 處理格式化
        annotations = text_obj.get("annotations", {})
        if annotations.get("bold"):
            plain_text = f"**{plain_text}**"
        if annotations.get("italic"):
            plain_text = f"*{plain_text}*"
        if annotations.get("code"):
            plain_text = f"`{plain_text}`"
        if annotations.get("strikethrough"):
            plain_text = f"~~{plain_text}~~"

        # 處理連結
        if text_obj.get("href"):
            plain_text = f"[{plain_text}]({text_obj['href']})"

        text += plain_text

    return text


def process_images_in_markdown(markdown_content: str) -> str:
    """處理 markdown 中的圖片，上傳到 Medium 並替換 URL"""
    import re

    # 找出所有圖片連結的正規表達式
    image_pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

    def replace_image(match):
        alt_text = match.group(1)
        original_url = match.group(2)

        # 檢查是否為外部 URL（需要上傳到 Medium）
        if original_url.startswith(("http://", "https://")):
            print(f"處理圖片: {alt_text or 'untitled'}")
            medium_url = upload_image_to_medium(original_url)
            return f"![{alt_text}]({medium_url})"
        else:
            # 如果不是外部 URL，保持原樣
            return match.group(0)

    # 替換所有圖片
    processed_content = re.sub(image_pattern, replace_image, markdown_content)

    return processed_content


def create_post(title: str, content: str, tags):
    medium_token = os.getenv("MEDIUM_TOKEN")
    medium_user_id = os.getenv("MEDIUM_USER_ID")

    if not medium_token:
        raise ValueError("請設定 MEDIUM_TOKEN 環境變數")
    if not medium_user_id:
        raise ValueError("請設定 MEDIUM_USER_ID 環境變數")

    print(content)
    result = requests.post(
        f"https://api.medium.com/v1/users/{medium_user_id}/posts",
        data=json.dumps(
            {
                "title": title,
                "contentFormat": "markdown",
                "content": content,
                "tags": tags,
                "publishStatus": "draft",
            }
        ),
        headers={
            "Content-type": "application/json",
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "Authorization": f"Bearer {medium_token}",
        },
    )

    print(result.json())


def upload_image_to_medium(image_url: str) -> str:
    """從 URL 下載圖片並上傳到 Medium，回傳 Medium 圖片 URL"""
    medium_token = os.getenv("MEDIUM_TOKEN")
    if not medium_token:
        raise ValueError("請設定 MEDIUM_TOKEN 環境變數")

    try:
        # 下載圖片
        print(f"正在下載圖片: {image_url}")
        image_response = requests.get(image_url)

        if image_response.status_code != 200:
            print(f"無法下載圖片: {image_url}")
            return image_url  # 回傳原始 URL

        # 取得檔名和副檔名
        import urllib.parse
        from pathlib import Path

        parsed_url = urllib.parse.urlparse(image_url)
        filename = Path(parsed_url.path).name
        if not filename or "." not in filename:
            filename = "image.png"  # 預設檔名

        # 準備 multipart/form-data
        files = {
            "image": (
                filename,
                image_response.content,
                f"image/{filename.split('.')[-1]}",
            )
        }

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {medium_token}",
        }

        print(f"正在上傳圖片到 Medium: {filename}")
        result = requests.post(
            "https://api.medium.com/v1/images", files=files, headers=headers
        )

        if result.status_code == 201:
            response_data = result.json()
            medium_url = response_data.get("data", {}).get("url", "")
            if medium_url:
                print(f"圖片上傳成功: {medium_url}")
                return medium_url

        print(f"圖片上傳失敗: {result.status_code}, {result.text}")
        return image_url  # 回傳原始 URL

    except Exception as e:
        print(f"圖片處理錯誤: {e}")
        return image_url  # 回傳原始 URL


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python post_a_note_to_medium.py <notion_page_id>")
        sys.exit(1)

    notion_page_id = sys.argv[1]

    try:
        # 從 Notion 獲取頁面內容
        notion_data = get_notion_page_content(notion_page_id)

        print(f"title: {notion_data['title']}")
        print(f"tags: {notion_data['tags']}")
        print(f"content preview: {notion_data['content'][:100]}...")

        # 發佈到 Medium
        create_post(notion_data["title"], notion_data["content"], notion_data["tags"])

        print("create post successfully")

    except Exception as e:
        print(f"錯誤: {e}")
        sys.exit(1)
