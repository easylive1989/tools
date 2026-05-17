# anthropic-update-translator

Cloudflare Worker:每 5 分鐘輪詢 Discord `anthropic-update-raw` 頻道,把 Anthropic / Claude 官方推文 embed 翻成繁體中文,在 `anthropic-updates` 頻道用 Bot 發送同款 embed。

## 一次性設定

1. **Discord Bot**(假設你已經有 Bot):確認 Bot 在你的 server 中,且擁有
   - source 頻道 `anthropic-update-raw`: `Read Messages` + `Read Message History`
   - target 頻道 `anthropic-updates`: `Send Messages` + `Embed Links`
   - 取得 source / target 兩個頻道的 channel ID(右鍵頻道 → 複製頻道 ID,需先開啟 Discord 開發者模式)。

2. **Cloudflare KV namespace**
   - Cloudflare Dashboard → Workers & Pages → KV → Create namespace
   - 命名:`anthropic-update-translator`
   - 把 namespace ID 寫進 `wrangler.toml` 的 `[[kv_namespaces]] id`。

3. **Cloudflare API token**
   - My Profile → API Tokens → Create Token → Custom token
   - 權限:
     - Account → Workers Scripts → Edit
     - Account → Workers KV Storage → Edit
   - 取得 token 字串;Account ID 在 Dashboard 右側面板可見。

4. **填入 `wrangler.toml` 兩個 channel ID 與 KV namespace ID**,commit 推上 master。

5. **GitHub Secrets**(Settings → Secrets and variables → Actions → New):
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
   - `DISCORD_BOT_TOKEN`
   - `GEMINI_API_KEY`

6. push 觸發 `.github/workflows/deploy-anthropic-translator.yml`,或在 Actions 頁面手動 `workflow_dispatch`。

## 切換到 Claude 翻譯

1. GitHub Secrets 新增 `CLAUDE_API_KEY`。
2. 修改 `wrangler.toml`:`TRANSLATOR = "claude"`。
3. 修改 workflow,在 `secrets:` 與 `env:` 區塊加入 `CLAUDE_API_KEY`。
4. push 觸發部署。

## 本機開發

```bash
cd anthropic_update_translator
npm install
npm test          # vitest
npm run typecheck # tsc --noEmit
```

不需在本機跑 `wrangler deploy`;部署一律走 GitHub Actions。

## 監控

Cloudflare Dashboard → Workers & Pages → `anthropic-update-translator` → Logs(real-time)。所有錯誤都會 `console.error`。
