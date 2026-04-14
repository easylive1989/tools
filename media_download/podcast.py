# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///
"""
下載 Apple Podcast 的單集音檔。

使用方式：
  uv run podcast.py <apple-podcast-episode-url>

範例：
  uv run podcast.py "https://podcasts.apple.com/tw/podcast/xxx/id1728703568?i=1000759381485"

做法：
  從網址的 ?i=<episode_id> 取得 episode id，
  透過 iTunes Lookup API 取得該 episode 的直接音檔 URL 後下載。
"""

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

OUTPUT_DIR = Path(__file__).parent / "download"


def extract_ids(url: str) -> tuple[str, str]:
    """從 Apple Podcast URL 取得 (podcast_id, episode_id)。

    URL 形如：https://podcasts.apple.com/tw/podcast/xxx/id1728703568?i=1000759381485
    path 裡 `idXXXX` 是 podcast id，query string `?i=XXXX` 是 episode id。
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    episode_id = qs.get("i", [None])[0]
    match = re.search(r"/id(\d+)", parsed.path)
    podcast_id = match.group(1) if match else None
    if not podcast_id or not episode_id:
        raise ValueError("無法從 URL 取得 podcast id 或 episode id（需要 /idXXX 與 ?i=XXX）")
    return podcast_id, episode_id


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run podcast.py <apple-podcast-episode-url>")
        sys.exit(1)

    url = sys.argv[1]
    podcast_id, episode_id = extract_ids(url)

    # 用 podcast id + entity=podcastEpisode 取得該 podcast 的所有 episode，
    # 再從中找出 trackId 等於 episode_id 的那一集。
    lookup_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcastEpisode&limit=1000"
    res = requests.get(lookup_url, timeout=15)
    res.raise_for_status()
    data = res.json()

    episode = next(
        (
            r for r in data.get("results", [])
            if r.get("wrapperType") == "podcastEpisode" and str(r.get("trackId")) == episode_id
        ),
        None,
    )
    if not episode:
        raise RuntimeError(f"找不到 episode: {episode_id}（podcast {podcast_id}）")

    title = episode.get("trackName") or episode_id
    audio_url = episode.get("episodeUrl")
    if not audio_url:
        raise RuntimeError("此 episode 沒有可下載的音檔 URL")

    ext = Path(urlparse(audio_url).path).suffix or ".mp3"
    OUTPUT_DIR.mkdir(exist_ok=True)
    filepath = OUTPUT_DIR / f"{sanitize_filename(title)}{ext}"

    print(f"Title: {title}")
    print(f"From : {audio_url}")
    print(f"To   : {filepath}")

    with requests.get(audio_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        downloaded = 0
        next_report = 10  # 每 10% 印一次
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 / total
                    if pct >= next_report or downloaded == total:
                        print(f"  {downloaded / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB ({pct:.1f}%)")
                        while pct >= next_report:
                            next_report += 10

    print(f"Done: {filepath}")


if __name__ == "__main__":
    main()
