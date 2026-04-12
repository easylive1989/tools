# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "playwright",
# ]
# ///

import os
import sys
import json
import tempfile
import subprocess
import requests
from bs4 import BeautifulSoup

DATABASE_ID = "3018303f78f7804c8253c266986003c4"
NOTION_TOKEN = os.environ.get("NOTION_SECRET")
NOTION_VERSION = "2022-06-28"
MAX_VIDEO_MB = 5.0

# CDN 路徑中屬於貼文圖片的關鍵字（排除大頭貼）
POST_IMAGE_PREFIXES = ("t51.82787-", "t51.71878-")


def notion_headers():
    return {
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
        "Authorization": f"Bearer {NOTION_TOKEN}",
    }


# ── 抓取 ──────────────────────────────────────────────────────────────────────

def fetch_thread(url: str) -> dict:
    """從 Threads 頁面抓取文字、圖片、第一支影片的 URL。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="load", timeout=60000)
        # 等待 og:description 或 video 元素出現
        try:
            page.wait_for_selector("meta[property='og:description'], video", timeout=15000)
        except Exception:
            pass

        result = page.evaluate("""() => {
            // ── 文字 ──
            const ogDesc = document.querySelector('meta[property="og:description"]');
            const text = (ogDesc && ogDesc.content) ? ogDesc.content : (() => {
                const spans = [...document.querySelectorAll('span[dir="auto"]')]
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 10);
                return spans[0] || '';
            })();

            // ── 圖片 + 影片：從 og:image 定位主貼文容器，只在容器內搜尋 ──
            let imgs = [];
            let video_url = '';
            const ogImg = document.querySelector('meta[property="og:image"]');
            const ogImgUrl = ogImg ? ogImg.content : '';
            const ogImgBase = ogImgUrl.split('?')[0];

            let targetImg = null;
            for (const img of document.querySelectorAll('img')) {
                if (img.src && img.src.split('?')[0] === ogImgBase) {
                    targetImg = img;
                    break;
                }
            }

            // 若有 og:image：往上找貼文容器（含圖片數 ≤ 10 的最高層），再在容器內找影片
            if (targetImg) {
                let parent = targetImg.parentElement;
                let prevCount = 0;
                let postContainer = null;

                for (let i = 0; i < 25; i++) {
                    if (!parent) break;
                    const cdnImgs = [...parent.querySelectorAll('img')]
                        .map(img => img.src)
                        .filter(s => s.includes('cdninstagram') || s.includes('fbcdn'));

                    if (cdnImgs.length > prevCount) {
                        imgs = cdnImgs;
                        prevCount = cdnImgs.length;
                    }
                    // 若貼文圖片 ≤ 10 張，視為還在主貼文範圍內
                    if (cdnImgs.length <= 10) {
                        postContainer = parent;
                    }

                    const next = parent.parentElement;
                    if (next) {
                        const nextImgs = [...next.querySelectorAll('img')]
                            .filter(img => img.src && (img.src.includes('cdninstagram') || img.src.includes('fbcdn')));
                        if (nextImgs.length > prevCount * 3) break;
                    }
                    parent = parent.parentElement;
                }

                // 只在主貼文容器內找影片
                if (postContainer) {
                    for (const v of postContainer.querySelectorAll('video')) {
                        if (v.src && (v.src.includes('cdninstagram') || v.src.includes('fbcdn'))) {
                            video_url = v.src;
                            break;
                        }
                    }
                }
            } else if (ogImgUrl) {
                imgs = [ogImgUrl];
            }

            // 若沒有 og:image（純影片貼文），直接找頁面第一支影片
            if (!ogImgUrl && !video_url) {
                for (const v of document.querySelectorAll('video')) {
                    if (v.src && (v.src.includes('cdninstagram') || v.src.includes('fbcdn'))) {
                        video_url = v.src;
                        break;
                    }
                }
            }

            return { text, imgs, video_url };
        }""")

        browser.close()

    text = result.get("text", "").strip()
    if not text:
        raise ValueError("無法從頁面中取得文章內容")

    # 過濾掉大頭貼，只保留貼文圖片，並去重
    post_imgs = []
    seen = set()
    for img_url in result.get("imgs", []):
        if any(p in img_url for p in POST_IMAGE_PREFIXES) and img_url not in seen:
            post_imgs.append(img_url)
            seen.add(img_url)

    video_url = result.get("video_url", "")

    print(f"  文字：{text[:80]}{'...' if len(text) > 80 else ''}")
    print(f"  圖片：{len(post_imgs)} 張")
    print(f"  影片：{'有' if video_url else '無'}")

    return {"text": text, "images": post_imgs, "video_url": video_url}


# ── 影片處理 ───────────────────────────────────────────────────────────────────

def download_video(url: str) -> str:
    """下載影片到暫存檔，回傳路徑。"""
    print("  下載影片中...")
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    for chunk in resp.iter_content(chunk_size=65536):
        tmp.write(chunk)
    tmp.close()
    size_mb = os.path.getsize(tmp.name) / 1024 / 1024
    print(f"  下載完成，大小：{size_mb:.1f}MB")
    return tmp.name


def get_video_duration(path: str) -> float | None:
    """用 ffprobe 取得影片秒數。"""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        return None
    info = json.loads(probe.stdout)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            try:
                return float(stream["duration"])
            except (KeyError, ValueError):
                pass
    return None


def compress_video(input_path: str, max_mb: float = MAX_VIDEO_MB) -> str:
    """若影片超過 max_mb，壓縮後回傳新路徑；否則回傳原路徑。"""
    size_mb = os.path.getsize(input_path) / 1024 / 1024
    if size_mb <= max_mb:
        return input_path

    print(f"  影片 {size_mb:.1f}MB 超過 {max_mb}MB，開始壓縮...")
    output_path = input_path.replace(".mp4", "_compressed.mp4")

    duration = get_video_duration(input_path)
    if duration and duration > 0:
        # 目標 bitrate（保留 5% 容差，音訊留 64k）
        target_video_kbps = max(100, int((max_mb * 0.95 * 8 * 1024) / duration) - 64)
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-b:v", f"{target_video_kbps}k",
            "-c:a", "aac", "-b:a", "64k",
            "-preset", "fast",
            output_path,
        ]
    else:
        # fallback：固定 CRF
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-crf", "32",
            "-c:a", "aac", "-b:a", "64k",
            "-preset", "fast",
            output_path,
        ]

    subprocess.run(cmd, capture_output=True, check=True)

    result_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  壓縮完成，大小：{result_mb:.1f}MB")
    return output_path


def upload_video_to_notion(video_path: str) -> str:
    """上傳影片到 Notion，回傳 file_upload id。"""
    filename = os.path.basename(video_path)
    size_mb = os.path.getsize(video_path) / 1024 / 1024
    print(f"  上傳影片到 Notion ({size_mb:.1f}MB)...")

    # Step 1：建立上傳請求
    create_resp = requests.post(
        "https://api.notion.com/v1/file_uploads",
        headers=notion_headers(),
        json={"name": filename, "content_type": "video/mp4"},
    )
    if create_resp.status_code != 200:
        raise RuntimeError(f"建立 Notion 上傳失敗：{create_resp.text}")

    upload_data = create_resp.json()
    file_id = upload_data["id"]
    upload_url = upload_data["upload_url"]

    # Step 2：上傳內容（multipart form）
    upload_headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }
    with open(video_path, "rb") as f:
        send_resp = requests.post(
            upload_url,
            headers=upload_headers,
            files={"file": (filename, f, "video/mp4")},
        )
    if send_resp.status_code not in (200, 201):
        raise RuntimeError(f"影片上傳失敗：{send_resp.text}")

    print(f"  上傳完成，file_upload id：{file_id}")
    return file_id


# ── 儲存到 Notion ──────────────────────────────────────────────────────────────

def save_to_notion(text: str, images: list, video_url: str, url: str):
    """在 Notion database 建立一筆記錄。"""
    title = text[:100] + ("…" if len(text) > 100 else "")

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Source": {"select": {"name": "threads"}},
    }

    children = []

    # 文字段落
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    })

    # 圖片 blocks
    for img_url in images:
        children.append({
            "object": "block",
            "type": "image",
            "image": {"type": "external", "external": {"url": img_url}},
        })

    # 影片 block（若有）
    if video_url:
        downloaded_path = None
        compressed_path = None
        try:
            downloaded_path = download_video(video_url)
            compressed_path = compress_video(downloaded_path)
            file_id = upload_video_to_notion(compressed_path)

            children.append({
                "object": "block",
                "type": "video",
                "video": {
                    "type": "file_upload",
                    "file_upload": {"id": file_id},
                },
            })
        except Exception as e:
            print(f"  影片處理失敗：{e}，改用外部連結")
            children.append({
                "object": "block",
                "type": "video",
                "video": {"type": "external", "external": {"url": video_url}},
            })
        finally:
            for path in {downloaded_path, compressed_path}:
                if path and os.path.exists(path):
                    os.unlink(path)

    # 來源連結
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": url, "link": {"url": url}}}]
        },
    })

    body = {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties,
        "children": children,
    }

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        data=json.dumps(body),
        headers=notion_headers(),
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Notion API 錯誤 {resp.status_code}：{resp.text}")

    page_id = resp.json()["id"]
    print(f"✓ 已儲存到 Notion：{page_id}")
    return page_id


# ── 主程式 ─────────────────────────────────────────────────────────────────────

def main():
    if not NOTION_TOKEN:
        print("請設定環境變數 NOTION_SECRET")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("用法：python extract.py <threads_url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"正在抓取：{url}")

    data = fetch_thread(url)
    save_to_notion(data["text"], data["images"], data["video_url"], url)


if __name__ == "__main__":
    main()
