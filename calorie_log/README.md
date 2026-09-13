# Discord 餐點熱量紀錄

這個工具在 Hetzner VPS 上執行。它讀取 Discord「餐點紀錄」頻道的新訊息；純文字餐點或照片都能觸發。若附多張照片，只取第一張。工具呼叫 VPS 本機的 Codex CLI 估算整餐熱量，直接寫入 Notion「每餐紀錄」，並在成功處理的 Discord 訊息加上 ✅，不發文字回覆。原始照片會上傳到該筆 Notion 記錄。從原始餐點訊息開啟的公開 thread 可以補充吃了什麼；工具會用原始內容和所有補充文字重新估算、更新同一筆 Notion 記錄，並在最新補充訊息加上 ✅。每次估算都會讀取 [食物熱量參考表](food_calorie_reference.md)，對照食藥署樣品資料與實際產品標示，再依份量和烹調方式調整。估算屬粗估，不適合當成精確營養數據。

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
