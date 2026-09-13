# Discord 餐點熱量紀錄

這個工具在已安裝且登入 Codex CLI 的 Oracle VM 上執行。它讀取 Discord「餐點紀錄」頻道的新訊息，選取每則訊息的第一張食物照片與文字說明，估算整餐熱量，並寫入 Notion「每餐紀錄」。照片會上傳到該筆 Notion 記錄。從原始餐點訊息開啟的公開 thread 可以補充吃了什麼；工具會用原始照片和所有補充文字重新估算，更新同一筆 Notion 記錄。估算屬粗估，不適合當成精確營養數據。

## 環境

- VM 上已安裝且登入 `codex` CLI。背景服務須使用同一位作業系統使用者，才能讀到登入狀態。
- Python 3.10+、可建立虛擬環境的 `python3`，以及具有無密碼 `sudo` 權限的部署帳號。
- `DISCORD_BOT_TOKEN`：可讀取指定頻道訊息與附件的 bot token。
- 選用 `DISCORD_CALORIE_CHANNEL_ID`：預設使用 Paul's Labs 的「餐點紀錄」頻道。
- `NOTION_SECRET`：能讀取與新增「每餐紀錄」頁面、上傳檔案的 Notion token。
- 選用 `NOTION_CALORIE_DATA_SOURCE_ID`：預設使用現有「每餐紀錄」data source。

CI 會在 `master` 分支的 `calorie_log/`、`common/notion.py` 或部署 workflow 變更時執行測試並部署；也可在 GitHub Actions 手動執行 `Deploy Calorie Log`。首次設定需在 repository 的 Actions Secrets 填入：

| Secret | 用途 |
| --- | --- |
| `ORACLE_VM_HOST` | Oracle VM 公開 IP 或 DNS 名稱 |
| `ORACLE_VM_USER` | SSH 使用者；必須是已登入 Codex CLI 的同一位使用者 |
| `ORACLE_VM_SSH_KEY` | 可登入 VM 的 SSH 私鑰原文 |
| `ORACLE_VM_KNOWN_HOSTS` | VM 的 SSH host key 行（先在可信環境驗證指紋，再從 `ssh-keyscan -H <host>` 取得） |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `NOTION_SECRET` | Notion integration token |

CI 會把程式同步到 VM 的 `~/tools`、建立 Python 虛擬環境、安裝 systemd timer，並立即執行一次。VM 上的 Codex CLI 必須由 `ORACLE_VM_USER` 登入；部署腳本會先檢查 `codex login status`。Secrets 缺漏時 workflow 會在部署前明確失敗。VM 的 `/opt/calorie-log/.env` 權限為 `600`，不會進 Git。

若要在 VM 手動執行一次，可使用：

```sh
./calorie_log/run.sh
```

第一次執行會把目前最新 Discord 訊息設為起點，只處理之後的新訊息。若要首次補登既有訊息，可在 VM 執行 `~/tools/.venv/bin/python ~/tools/calorie_log/discord_runner.py --backfill`。systemd timer 每分鐘執行一次。處理進度存於 `calorie_log/state.json`，已排除 Git 追蹤。

照片若有可讀取的拍攝時間，會用拍攝時間；否則用 Discord 訊息時間。所有時間都轉成台灣時間。餐別區間是早餐 05:00–10:59、午餐 11:00–15:59、晚餐 16:00–20:59，其餘為點心。

Notion 的「卡路里」欄位只存整餐總熱量。「備註」包含原始說明、影響估算的假設、信心等級與 Discord 訊息 ID，供失敗重試時避免重複建立。上傳照片大小目前支援 20 MiB 以下；免費 Notion 工作區可能另有更低的上限。
