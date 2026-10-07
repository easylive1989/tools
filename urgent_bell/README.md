# 老公急事鈴 🔔（免費版）

老婆用 LINE 傳急事，老公的 iPhone 一定會響；老公點開通知後，她的 LINE 會收到「老公看到了」。

```
老婆（Android / LINE）
   │  傳訊息給「老公急事鈴」官方帳號
   ▼
Cloudflare Worker（這個專案）
   │  用 Bark 推播
   ▼
老公（iPhone / Bark App）
   │  沒點開就每 2 分鐘再推一次
   ▼
點開通知 → 開啟確認頁 → LINE 回報老婆：「老公 15:30 看到了 ✅」
1 小時都沒點開 → LINE 告訴老婆：「急的話直接打電話給他」
```

**強度設計：** 比 LINE 明顯，比電話溫和。它有獨立的 App 和音效，不會被群組訊息淹沒，可以穿過專注模式，沒點開就一直提醒，但**不會穿透靜音**（靜音時只會震動）。真正緊急的事（安全、健康）還是打電話。

---

## 你需要準備（全部免費）

| 項目 | 誰用 | 費用 |
|---|---|---|
| Bark App（iPhone） | 老公 | 免費、開源 |
| LINE 官方帳號 | 老婆傳訊息的對象 | 免費「輕用量」方案：每月 200 則主動推播。只有「看到了」和「還沒看到」會用到額度 |
| Cloudflare 帳號 | 跑這支程式 | 免費方案就夠（含計時用的 Durable Object） |
| 電腦上的 Node.js 18 以上 | 部署用 | 免費 |

老婆的 Android 手機**不用裝任何東西**，只要在 LINE 加一個好友。

---

## 步驟 1：Bark（你的 iPhone）

1. App Store 搜尋 **Bark** 並安裝，打開後允許通知。
2. App 首頁會顯示一個網址，像這樣：
   ```
   https://api.day.app/AbCdEf123456/這裡改成你自己的推播內容
   ```
   中間那段（例子裡的 `AbCdEf123456`）就是你的 key → 之後的 `BARK_KEY`。
   可以先在 Safari 打開這個網址，手機有響就代表 Bark 正常。
3. iPhone 設定（重要）：
   - **設定 → 通知 → Bark**：允許通知，打開「**時效性通知**」，橫幅樣式選「**持續**」，讓通知停在螢幕上直到你處理。
   - 如果你有用**專注模式／勿擾**：到 **設定 → 專注模式 →（每一個你會用的模式）→ App**，確認「**時效性通知**」是打開的，或直接把 Bark 加進允許的 App。

> 隱私說明：推播內容會經過 Bark 的官方伺服器（api.day.app）轉送。如果在意，可以自架 [bark-server](https://github.com/Finb/bark-server)，再把 `wrangler.toml` 裡的 `BARK_SERVER` 換成你的網址。

## 步驟 2：LINE 官方帳號

1. 到 [LINE Official Account Manager](https://manager.line.biz) 用你的 LINE 登入，**建立官方帳號**，名稱例如「老公急事鈴」。方案維持免費的「輕用量」。
2. 在官方帳號後台 **設定 → Messaging API → 啟用 Messaging API**（第一次會要你建立一個 Provider，隨便取名）。
   - 這頁的 **Channel secret** 抄下來 → `LINE_CHANNEL_SECRET`
3. 到 [LINE Developers Console](https://developers.line.biz/console/) 找到同一個 channel → **Messaging API** 分頁 → 最下面 **Channel access token (long-lived)** 按 **Issue** → `LINE_CHANNEL_ACCESS_TOKEN`
4. 回官方帳號後台 **設定 → 回應設定**：
   - 聊天：**關閉**
   - 加入好友的歡迎訊息：**關閉**
   - 自動回應訊息：**關閉**
   - Webhook：**開啟**

## 步驟 3：部署到 Cloudflare

用 GitHub Actions（`.github/workflows/deploy-urgent-bell.yml`）部署：push 到 `master` 且有改到 `urgent_bell/` 時會自動跑，也可以手動觸發。流程是測試 → 部署 Worker → 把 GitHub Secrets 同步成 Worker 的 secrets。

**3-1. Cloudflare 準備（只做一次）**

1. Worker 掛在 `urgent-bell.paul-learning.dev`（`wrangler.toml` 的 `routes`），`paul-learning.dev` 要在同一個 Cloudflare 帳號裡。部署時 Cloudflare 會自動建 DNS 記錄和憑證。
2. 登入 [Cloudflare dashboard](https://dash.cloudflare.com) → **Workers & Pages**，右側可以看到 **Account ID** → `CLOUDFLARE_ACCOUNT_ID`
3. 右上頭像 → **My Profile → API Tokens → Create Token**，選 **Edit Cloudflare Workers** 範本建立 → `CLOUDFLARE_API_TOKEN`

**3-2. 設定 GitHub Secrets**

到 repo 的 **Settings → Secrets and variables → Actions** 新增，或用 `gh`（每一行會提示你貼上數值）：

```bash
gh secret set CLOUDFLARE_API_TOKEN
gh secret set CLOUDFLARE_ACCOUNT_ID
gh secret set URGENT_BELL_LINE_CHANNEL_SECRET        # 步驟 2 的 Channel secret
gh secret set URGENT_BELL_LINE_CHANNEL_ACCESS_TOKEN  # 步驟 2 的 Channel access token
gh secret set URGENT_BELL_BARK_KEY                   # 步驟 1 的 Bark key
openssl rand -hex 16 | gh secret set URGENT_BELL_CALLBACK_SECRET  # 自動產生一串亂碼
```

**3-3. 部署**

```bash
gh workflow run deploy-urgent-bell.yml
gh run watch
```

部署完 Worker 的網址是 `https://urgent-bell.paul-learning.dev`，打開會看到 `urgent-bell is running`。

<details>
<summary>不用 GitHub Actions，直接從電腦部署</summary>

```bash
cd urgent_bell
npm install
npx wrangler login          # 開瀏覽器登入 Cloudflare
npx wrangler deploy

npx wrangler secret put LINE_CHANNEL_SECRET
npx wrangler secret put LINE_CHANNEL_ACCESS_TOKEN
npx wrangler secret put BARK_KEY
openssl rand -hex 16                    # 產生一串亂碼，複製起來
npx wrangler secret put CALLBACK_SECRET # 貼上剛剛的亂碼
```

注意：之後只要 GitHub Actions 跑一次，就會用 GitHub Secrets 覆蓋這裡設定的值。

</details>

最後回 LINE Developers Console → **Messaging API** 分頁：

- **Webhook URL** 填 `https://urgent-bell.paul-learning.dev/line/webhook`
- 按 **Verify**，要看到 Success
- 打開 **Use webhook**

## 步驟 4：先用自己測試

不用設定誰是老婆：**任何人**一對一傳訊息給官方帳號都會觸發通知，「看到了」和逾時通知會回給傳訊息的那個人（群組訊息不處理）。

1. 在官方帳號後台的「加入好友」頁找到 QR code，**用你自己的 LINE 加好友**，隨便傳一句話。
2. 應該會：
   - LINE 回「收到，已經通知老公了 🔔」
   - iPhone 上的 Bark 響起；不理它的話，2 分鐘後會再響（標題變成「第 2 次提醒」）
   - **點一下通知** → 開啟確認頁，顯示「✅ 已經告訴老婆你看到了」
   - LINE 收到「老公 HH:MM 看到了 ✅」

四個都有出現就代表整條路是通的。

## 步驟 5：給老婆

請老婆用 LINE 掃 QR code 加好友，就完成了。

官方帳號只有知道 ID 或 QR code 的人加得到。如果有陌生人加好友亂傳，也會讓你的手機響，到時候在官方帳號後台封鎖對方就好。

---

## 怎麼「確認」

**點通知**就是確認：會打開一個網頁，同時告訴老婆你看到了，網頁上也會顯示她的訊息和「打開 LINE」按鈕。

把通知滑掉**不算**確認，它會繼續提醒。這是故意的：滑掉不代表你看過了。

她短時間內連傳好幾則時，只有**最新一則**會繼續提醒，不會好幾個疊在一起。

---

## 給老婆的說明（可以直接傳給她）

> 我做了一個「老公急事鈴」，在 LINE 裡面。
> 有需要我**盡快看到**的事，就傳到那裡，我手機會一直提醒，直到我點開為止。
> - 它回「已經通知老公了」→ 送出成功
> - 它回「老公 xx:xx 看到了」→ 我真的看到了
> - 它回「還沒點開通知」或「通知沒有送出去」→ 直接打電話給我
>
> 平常聊天一樣傳我們原本的 LINE 就好 ❤️

建議兩個人先約好什麼事算「急事」。另外很重要的一點：**鈴響了就要點開**。這個通道有效，是因為她相信你一定會看到；只要被忽略幾次，它就沒用了。

---

## 調整

修改 `wrangler.toml` 後 push 到 `master`，GitHub Actions 會自動重新部署：

| 設定 | 預設 | 說明 |
|---|---|---|
| `RETRY_SECONDS` | `120` | 沒點開時多久再提醒一次（秒，最少 30） |
| `EXPIRE_SECONDS` | `3600` | 最多持續提醒多久（秒），時間到會告訴老婆 |
| `ALERT_TITLE` | `老婆找你` | 通知標題 |
| `BARK_LEVEL` | `timeSensitive` | `active`：一般通知；`timeSensitive`：可穿過專注模式；`critical`：穿透靜音，等同電話 |
| `BARK_SOUND` | 空白 | 鈴聲名稱，可在 Bark App 的鈴聲列表試聽；空白用預設 |
| `BARK_CALL` | `0` | `1` = 每次提醒鈴聲連續響 30 秒 |
| `BARK_SERVER` | `https://api.day.app` | 自架 bark-server 時才需要改 |

**想要更強：** `BARK_LEVEL = "critical"`，或 `BARK_CALL = "1"`。
**想要更弱：** 把 `RETRY_SECONDS` 調大，例如 `900`（15 分鐘）。

---

## 疑難排解

先開 `npm run logs`，再重現一次問題，錯誤訊息會出現在 log 裡。

| 狀況 | 可能原因 |
|---|---|
| Webhook Verify 失敗 | Channel secret 貼錯，或網址少了 `/line/webhook` |
| 傳訊息後完全沒反應 | 回應設定裡的 Webhook 沒開，或「聊天」還開著 |
| 她收到「通知沒有送出去」 | `BARK_KEY` 貼錯（只要中間那段，不含網址和斜線） |
| 點開通知了但她沒收到「看到了」 | LINE access token 錯，或本月 200 則推播額度用完（確認頁會顯示「回報失敗」） |
| iPhone 沒響 | Bark 的時效性通知沒開、專注模式沒放行；或手機在靜音模式（只會震動，這是設計） |

## 開發

```bash
npm test     # 用模擬的 LINE / Bark API 跑過整個流程（含重複提醒、確認、逾時）
```
