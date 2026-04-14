# media_download

下載多媒體檔案的工具集。所有下載檔案會輸出到 `media_download/download/`（已於 `.gitignore` 排除）。

## 需求

- [uv](https://docs.astral.sh/uv/)（用來執行 PEP 723 inline script；會自動處理相依套件）
- `yt-dlp` 需要 `ffmpeg` 才能把影片 / 音訊串流合併為單一 mp4
  ```bash
  brew install ffmpeg
  ```

## 工具

### `youtube.py` — 下載 YouTube 影片（mp4）

下載單支 YouTube 影片，自動挑選最佳 mp4 畫質（video + audio 合併）。

**使用方式**

```bash
uv run media_download/youtube.py <youtube-url>
```

**範例**

```bash
uv run media_download/youtube.py "https://www.youtube.com/watch?v=dWeoSKLt_fc"
```

**注意事項**

- 只下載單支影片，不會展開 playlist
- 若看到 `No supported JavaScript runtime could be found` 警告，部分格式可能無法取得；可安裝 deno 補上：`brew install deno`

---

### `podcast.py` — 下載 Apple Podcast 單集音檔（mp3 / m4a）

從 Apple Podcast **單集** 網址下載該集音檔。

**使用方式**

```bash
uv run media_download/podcast.py <apple-podcast-episode-url>
```

**範例**

```bash
uv run media_download/podcast.py "https://podcasts.apple.com/tw/podcast/xxx/id1728703568?i=1000759381485"
```

**運作原理**

1. 從網址 path 中取得 podcast id（`/idXXX`）、query string 取得 episode id（`?i=XXX`）
2. 呼叫 iTunes Lookup API（`https://itunes.apple.com/lookup?id=<podcast_id>&entity=podcastEpisode`）取得該 podcast 所有集數
3. 比對 `trackId` 找到目標集，取 `episodeUrl` 直接串流下載

**限制**

- 網址必須包含 `?i=<episode_id>`（單集頁才有），整個 podcast 的頁面不支援
- 僅下載 Apple Podcast 本身公開提供的原始音檔（大部分 podcast 都可以）

## 輸出

```
media_download/
└── download/          # 所有下載檔案都會存這裡，不納入 git
    ├── <影片標題>.mp4
    └── <集數標題>.mp3
```
