// Shared tools data for all showcase mockups.
// status: active | experiment | retired
window.TOOLS = [
  { id: 'document_translator', name: 'document_translator', icon: '📄',
    status: 'active', tags: ['python', 'typer', 'gemini', 'docx', 'epub', 'pdf'],
    summary: '把 docx / md / epub / pdf 翻成繁中。Typer CLI 包 Gemini，可切 CLI 或 API 模式。',
    runs: 'manual · CLI' },

  { id: 'ledger_analysis', name: 'ledger_analysis', icon: '💰',
    status: 'active', tags: ['python', 'notion', 'github actions'],
    summary: '月度記帳分析，產出摘要寫回 Notion。GitHub Actions 每月自動跑。',
    runs: 'GH Actions · monthly' },

  { id: 'personal_retro', name: 'personal_retro', icon: '🪞',
    status: 'active', tags: ['python', 'notion', 'discord', 'openai'],
    summary: '個人 weekly retro：從 Notion 抓 log，用 LLM 整理回顧並發到 Discord。',
    runs: 'manual / cron' },

  { id: 'transcribe', name: 'transcribe', icon: '🎙',
    status: 'active', tags: ['python', 'blackhole', 'whisper', 'macos'],
    summary: 'macOS 用 BlackHole 錄 Discord 音訊，可串接 Whisper 自動轉錄。',
    runs: 'manual · CLI' },

  { id: 'travel', name: 'travel', icon: '✈️',
    status: 'active', tags: ['react', 'vite', 'github pages'],
    summary: '旅遊行程 web app + 編輯器，部署在 tools.paul-learning.dev/travel。',
    runs: 'GitHub Pages',
    link: 'https://tools.paul-learning.dev/travel/2026_austria_czechia/' },

  { id: 'rss', name: 'rss', icon: '📡',
    status: 'active', tags: ['python', 'uv', 'notion', 'raycast'],
    summary: '把多個 RSS 來源同步到 Notion；從 Raycast 用 uv run 觸發。',
    runs: 'Raycast' },

  { id: 'rss_hub', name: 'rss_hub', icon: '📰',
    status: 'active', tags: ['python', 'github actions', 'rss'],
    summary: '產生個人化 RSS feed，由 GitHub Actions 定期更新部署到 Pages。',
    runs: 'GH Actions' },

  { id: 'read_later', name: 'read_later', icon: '📑',
    status: 'active', tags: ['python', 'rss'],
    summary: '把暫存的待讀文章輸出成 feed.xml。',
    runs: 'GH Actions' },

  { id: 'medium', name: 'medium', icon: '✍️',
    status: 'active', tags: ['python', 'notion', 'medium api'],
    summary: '把寫好的文章從 Notion 推到 Medium。',
    runs: 'manual' },

  { id: 'sharing', name: 'sharing', icon: '🤖',
    status: 'active', tags: ['python', 'discord', 'vps', 'systemd'],
    summary: 'VPS 上的 Discord 分享 bot，systemd 跑；用 rsync workflow 部署。',
    runs: 'VPS · systemd' },

  { id: 'thread_extractor', name: 'thread_extractor', icon: '🧵',
    status: 'active', tags: ['python', 'scraping'],
    summary: '從 X / Threads 抓討論串並輸出整理過的文字。',
    runs: 'manual' },

  { id: 'media_download', name: 'media_download', icon: '⬇️',
    status: 'active', tags: ['python', 'yt-dlp'],
    summary: '批次下載多媒體素材的小工具。',
    runs: 'manual' },

  { id: 'leadtime_analyze', name: 'leadtime_analyze', icon: '📊',
    status: 'active', tags: ['python', 'analytics'],
    summary: '分析 lead time / cycle time 的小工具。',
    runs: 'manual' },

  { id: 'translate', name: 'translate', icon: '🌐',
    status: 'active', tags: ['python', 'raycast', 'gemini'],
    summary: 'Raycast 上的快速翻譯腳本。',
    runs: 'Raycast' },

  { id: 'macos_init', name: 'macos_init', icon: '🛠',
    status: 'active', tags: ['shell', 'macos'],
    summary: '新 macOS 機器的初始化腳本。',
    runs: 'manual' },

  { id: 'lottie', name: 'lottie', icon: '✨',
    status: 'experiment', tags: ['lottie'],
    summary: 'Lottie 動畫相關處理 (實驗性)。',
    runs: '—' },

  { id: 'tinyflow', name: 'tinyflow', icon: '🌊',
    status: 'experiment', tags: ['python'],
    summary: '小型 workflow 實驗。',
    runs: '—' },

  { id: 'claw', name: 'claw', icon: '🦀',
    status: 'retired', tags: ['archived'],
    summary: '已退役 — 保留在 repo 作為歷史紀錄。',
    runs: '—' },
];

window.REPO_URL = 'https://github.com/easylive1989/tools';

window.MOCKUPS = [
  { id: 'a', file: 'a-retro-os.html',     name: 'A · Retro Tools OS',   blurb: '假桌面作業系統，雙擊圖示開視窗' },
  { id: 'b', file: 'b-subway-map.html',   name: 'B · Subway Map',       blurb: '地鐵路線圖，按主題分線' },
  { id: 'c', file: 'c-terminal.html',     name: 'C · Terminal',         blurb: '互動 shell，可以打指令探索' },
  { id: 'd', file: 'd-notebook.html',     name: 'D · Notebook',         blurb: '手繪工程師筆記本' },
  { id: 'e', file: 'e-tcg.html',          name: 'E · Tool TCG',         blurb: '可收藏的工具卡牌' },
  { id: 'f', file: 'f-pixel-town.html',   name: 'F · Pixel Town',       blurb: '像素 RPG 小鎮' },
  { id: 'g', file: 'g-garden.html',       name: 'G · Zen Garden',       blurb: '工具盆栽園' },
];
