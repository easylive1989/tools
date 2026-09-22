# Discord 餐點熱量紀錄

這個工具在 Hetzner VPS 上執行。它讀取 Discord「餐點紀錄」頻道的新訊息；純文字餐點或照片都能觸發。若附多張照片，只取第一張。工具呼叫 VPS 本機的 Codex CLI，以 `gpt-5.6-terra`、`medium` 推理強度估算整餐熱量，直接寫入 Notion「每餐紀錄」，並在對應的 Thread 中回覆估算的總熱量（例如：`【排骨便當】預估總熱量：750 kcal`），同時在 Discord 訊息加上 ✅。原始照片會上傳到該筆 Notion 記錄。從原始餐點訊息開啟的公開 thread 可以補充吃了什麼；工具會用原始內容和所有補充文字重新估算、更新同一筆 Notion 記錄，在 Thread 中回覆更新後的熱量，並在最新補充訊息加上 ✅。每次估算都會讀取 [食物熱量參考表](food_calorie_reference.md)，對照食藥署樣品資料與實際產品標示，再依份量和烹調方式調整。估算屬粗估，不適合當成精確營養數據。

## 詢問 AI 飲食建議

在「餐點紀錄」頻道發送以 `建議：` 開頭的訊息，例如 `建議：依最近的飲食，我今晚怎麼吃？`；直接說 `我想吃炸雞，怎麼搭配？`、`我打算吃蛋黃酥` 等尚未吃的計畫也會觸發建議。可以附照片，也可以在既有餐點的公開 thread 詢問。Bot 會讀取 Notion 最近 7 天的已記錄餐點，在詢問訊息下回覆一次，不把這則詢問當成已吃的餐點，也不將預計吃的食物寫入 Notion。若最後真的吃了，另發一則一般餐點訊息記錄。建議只根據已有紀錄推論；漏記的餐次不會被當成沒吃。

帶問號的訊息會視為詢問；若要確定把一則帶問號的已吃餐點存進 Notion，可在開頭加 `記錄：`。

[飲食建議提示詞](nutrition_advisor_prompt.md)整理了講義的 211／321 餐盤、六大類食物、外食選擇及少糖少鹽等原則，並要求給出符合近期飲食模式的具體建議。甜點、炸物等可以依近期整體飲食與當下選擇彈性安排，不用跳餐或過度運動「補償」。這是一般健康資訊，不是疾病治療或個人熱量處方。講義的重點另可與[國民健康署「我的餐盤」](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=1405&pid=8629&sid=10109)及 [NHS Eatwell Guide](https://www.nhs.uk/live-well/eat-well/food-guidelines-and-food-labels/the-eatwell-guide/)對照。

可選用 GitHub Actions secret `NUTRITION_PROFILE` 保存個人飲食限制、過敏、飲食目標等文字；可選用 repository variable `NUTRITION_LOOKBACK_DAYS` 改變回看天數，預設 7。前者若涉及醫囑，仍需以醫師或持照營養師的指示為準。Bot 需要在頻道具備發送訊息及讀取歷史訊息權限。

## 每週自動飲食回顧

部署後預設於每週一早上 08:00（臺灣時間），在 Discord「餐點紀錄」頻道發送一則飲食回顧。內容根據排定時間往前 7 天的 Notion 餐點紀錄，引用實際餐點，整理值得維持的習慣及下週可嘗試的 2–3 個具體調整；沿用 `NUTRITION_PROFILE` 個人限制。週報固定回看 7 天，不受即時問答的 `NUTRITION_LOOKBACK_DAYS` 影響。

首次啟用或修改時間後，從下一個排定時間開始。沿用現有每分鐘執行的 systemd timer，通常於排定時間後的一輪執行送出。停機後僅補最近一期；整週沒有紀錄則略過，紀錄不足不推定沒吃。發送前保存待送內容，失敗後重試；重啟時會檢查 Bot 已發送的週報編號，避免因發送成功但狀態未寫回而重複發送。

可用 GitHub repository variables `NUTRITION_WEEKLY_DAY`（0=週一，…，6=週日；預設 0）及 `NUTRITION_WEEKLY_HOUR`（臺灣時間 0–23；預設 8）調整，再執行部署。週報進度與待送內容保存在既有的 `calorie_log/state.json`。

## 環境

- Hetzner VPS 須可使用 `root` SSH 登入，並安裝 Python 3.10+ 與 `python3-venv`。
- `codex` CLI 須以 `root` 帳號安裝並登入；可在首次 CI 部署後再做，排程會持續等待登入。
- `DISCORD_BOT_TOKEN`：可讀取指定頻道訊息與附件的 bot token。
- 選用 `DISCORD_CALORIE_CHANNEL_ID`：預設使用 Paul's Labs 的「餐點紀錄」頻道。
- `NOTION_SECRET`：能讀取與新增「每餐紀錄」頁面、上傳檔案的 Notion token。
- 選用 `NOTION_CALORIE_DATA_SOURCE_ID`：預設使用現有「每餐紀錄」data source。

CI 會在 `master` 分支的 `calorie_log/`、`common/notion.py` 或部署 workflow 變更時執行測試並部署；也可在 GitHub Actions 手動執行 `Deploy Calorie Log`。使用 repository 現有的 Actions Secrets：

| Secret | 用途 |
| --- | --- |
| `VPS_HOST` | Hetzner VPS 公開 IP 或 DNS 名稱 |
| `VPS_SSH_KEY` | 可用 `root` 登入 VPS 的 SSH 私鑰原文 |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `NOTION_SECRET` | Notion integration token |

選用 `VPS_KNOWN_HOSTS` 可放入事先驗證過的 SSH host key，讓 CI 固定比對；未設定時 CI 會在每次部署前用 `ssh-keyscan` 取得主機目前的 key。

CI 會把程式同步到 VPS 的 `/opt/calorie-log`、建立 Python 虛擬環境、安裝並啟用 systemd timer。若 `root` 已登入 Codex CLI，部署時會立即執行一次；否則 timer 會每分鐘重試，直到登入完成。VPS 的 `/opt/calorie-log/.env` 權限為 `600`，不會進 Git。

熱量參考表會隨每次部署複製到 VPS。修改 `calorie_log/food_calorie_reference.md` 後推送到 `master`，CI 會執行測試並部署；下一次估算便會讀取更新後的表。新增數值時應保留食品樣品名稱、每 100 克或每份的單位與原始來源，避免把生食、熟食或不同品牌視為同一數值。

在 Hetzner VPS 用 `root` 執行 `codex login` 與 `codex login status`。完成登入後可執行 `systemctl start calorie-log.service` 立即測試。

若要在 VPS 手動執行一次，可使用：

```sh
/opt/calorie-log/calorie_log/run.sh
```

第一次成功執行會把目前最新 Discord 訊息設為起點，只處理之後的新訊息。這次加入純文字支援時，會自動檢查最近兩天、最新 100 則訊息，補登舊版略過的純文字餐點。若要首次補登更早的既有訊息，可在 VPS 執行 `/opt/calorie-log/.venv/bin/python /opt/calorie-log/calorie_log/discord_runner.py --backfill`。systemd timer 每分鐘執行一次。處理進度存於 `calorie_log/state.json`，已排除 Git 追蹤。

照片若有可讀取的拍攝時間，會用拍攝時間；否則用 Discord 訊息時間。所有時間都轉成台灣時間。餐別區間是早餐 05:00–10:59、午餐 11:00–15:59、晚餐 16:00–20:59，其餘為點心。

Notion 的「卡路里」欄位只存整餐總熱量。「備註」包含原始說明、影響估算的假設、信心等級與 Discord 訊息 ID，供失敗重試時避免重複建立。上傳照片大小目前支援 20 MiB 以下；免費 Notion 工作區可能另有更低的上限。
