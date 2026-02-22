# Notion to Medium 發佈工具

這個腳本使用自定義的 `NotionApi` 類別，可以將 Notion 頁面內容轉換為 Markdown 格式並發佈到 Medium。

## 功能特點

- 從 Notion API 獲取頁面內容
- 自動轉換為 Markdown 格式
- 支援多種 Notion 區塊類型（標題、段落、列表、程式碼、引言、圖片等）
- 保留文字格式（粗體、斜體、程式碼、刪除線）
- 支援連結轉換
- **自動圖片處理**：從 Notion 下載圖片並上傳到 Medium
- 直接發佈到 Medium（草稿模式）

## 環境設定

### 必要的環境變數

```bash
export NOTION_TOKEN="your_notion_integration_token"
export MEDIUM_TOKEN="your_medium_integration_token" 
export MEDIUM_USER_ID="your_medium_user_id"
```

### 獲取所需的 Token

1. **Notion Token**: 
   - 前往 https://www.notion.so/my-integrations
   - 建立新的整合
   - 複製 Integration Token

2. **Medium Token**:
   - 前往 https://medium.com/me/settings
   - 找到 Integration tokens 部分
   - 產生新的 token

3. **Medium User ID**:
   - 使用 Medium API: `https://api.medium.com/v1/me`
   - 或使用腳本中的工具函式獲取

## 使用方法

```bash
python3 post_a_note_to_medium.py <notion_page_id>
```

### 參數說明

- `notion_page_id`: Notion 頁面的 ID，可以從頁面 URL 中獲取

### 例子

```bash
python3 post_a_note_to_medium.py 12345678-1234-1234-1234-123456789012
```

## 支援的 Notion 區塊類型

- 段落 (paragraph)
- 標題 1-3 (heading_1, heading_2, heading_3)
- 無序列表 (bulleted_list_item)
- 有序列表 (numbered_list_item)
- 引言 (quote)
- 程式碼區塊 (code)
- 分隔線 (divider)
- **圖片 (image)** - 支援外部連結和 Notion 檔案，自動上傳到 Medium

## 支援的文字格式

- **粗體**
- *斜體*
- `程式碼`
- ~~刪除線~~
- [連結](url)

## 依賴檔案

- `notion_api.py` - 自定義的 Notion API 包裝類別
- `post_a_note_to_medium.py` - 主要腳本

## 注意事項

1. 發佈的文章會以草稿模式建立在 Medium
2. Notion 整合需要有存取目標頁面的權限
3. 確保所有環境變數都已正確設定
4. 程式碼區塊的語言標示會保留
5. **圖片會自動從 Notion 下載並上傳到 Medium**
6. 腳本使用自定義的 `NotionApi` 類別進行 API 呼叫
7. 圖片處理可能需要一些時間，請耐心等候

## 錯誤排除

1. **401 Unauthorized**: 檢查 Token 是否正確
2. **403 Forbidden**: 檢查 Notion 整合是否有頁面存取權限
3. **404 Not Found**: 檢查頁面 ID 是否正確
4. **環境變數錯誤**: 確保所有必要的環境變數都已設定