# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "yt-dlp",
# ]
# ///
"""
下載 YouTube 影片為 mp4。

使用方式：
  uv run youtube.py <youtube-url>
"""

import sys
from pathlib import Path

import yt_dlp

OUTPUT_DIR = Path(__file__).parent / "download"


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run youtube.py <youtube-url>")
        sys.exit(1)

    url = sys.argv[1]
    OUTPUT_DIR.mkdir(exist_ok=True)

    opts = {
        # 優先挑 mp4 的視訊 + m4a 音訊，合併為 mp4；否則退而求其次抓單一 mp4
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(OUTPUT_DIR / "%(title)s.%(ext)s"),
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


if __name__ == "__main__":
    main()
