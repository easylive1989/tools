# 鉅亨網台股新聞 Raycast Script Command

透過 Raycast Script Command 直接列出鉅亨網（cnYES）即時台股新聞，無需任何 API Key 或第三方帳號。

## 功能特點

- **零帳號與密碼**：透過公開端點拉取即時新聞，免認證、無用量限制。
- **一鍵開文章**：列出最新 10 則新聞與發布時間，附帶新聞超連結。在 Raycast 中按住 `⌘` 點擊網址即可在瀏覽器打開全文。
- **雙模支援**：優先使用鉅亨網公開 API 端點（免 API Key，穩定性高），並內建 RSS XML 備援解析機制。
- **自動更新**：設定 `@raycast.refreshTime 10m`，Raycast 會定時重新整理。

## 加入 Raycast 步驟

1. 打開 Raycast 設定（`⌘ + ,`）
2. 切換至 **Extensions** 分頁
3. 點選左側的 **Script Commands**
4. 點擊 **Add Script Directory**（或快速鍵 `⌘ + ⇧ + D`）
5. 選擇或填入本資料夾路徑：
   ```
   /Users/paulps/Documents/Github/tools/cnyes_news
   ```
6. 之後只要在 Raycast 輸入 `鉅亨網台股新聞` 即可立即查看最新新聞！
