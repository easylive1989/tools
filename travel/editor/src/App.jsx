import { useRef, useState } from 'react'
import { parseMarkdown, newItinerary, newDay } from './parser.js'
import { exportMarkdown } from './exporter.js'
import { DayDetail } from './components/DayDetail.jsx'
import {
  TripSettingsModal,
  CommonPhrasesModal,
} from './components/Modals.jsx'

export default function App() {
  const [itinerary, setItinerary] = useState(null)
  const [fileName, setFileName] = useState('itinerary.md')
  const [selectedDayId, setSelectedDayId] = useState(null)
  const [showTripSettings, setShowTripSettings] = useState(false)
  const [showCommonPhrases, setShowCommonPhrases] = useState(false)

  const startNew = () => {
    const it = newItinerary()
    setItinerary(it)
    setFileName('untitled.md')
    setSelectedDayId(null)
  }

  const loadText = (text, name) => {
    const it = parseMarkdown(text)
    setItinerary(it)
    setFileName(name || 'itinerary.md')
    setSelectedDayId(it.days[0]?.id ?? null)
  }

  const handleFile = (file) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => loadText(String(reader.result ?? ''), file.name)
    reader.readAsText(file, 'utf-8')
  }

  const download = () => {
    if (!itinerary) return
    const md = exportMarkdown(itinerary)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName || 'itinerary.md'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  if (!itinerary) {
    return <Welcome onOpen={handleFile} onNew={startNew} />
  }

  const updateItinerary = (next) => setItinerary(next)
  const selectedDay = itinerary.days.find(d => d.id === selectedDayId) ?? null

  const updateDay = (next) => {
    setItinerary({
      ...itinerary,
      days: itinerary.days.map(d => d.id === next.id ? next : d),
    })
  }

  const addDay = () => {
    const nextNum = (itinerary.days.reduce((m, d) => Math.max(m, d.day), 0)) + 1
    const day = newDay(nextNum)
    setItinerary({ ...itinerary, days: [...itinerary.days, day] })
    setSelectedDayId(day.id)
  }

  const deleteDay = (id) => {
    if (!confirm('確定要刪除這天嗎？')) return
    const next = itinerary.days.filter(d => d.id !== id)
    setItinerary({ ...itinerary, days: next })
    if (selectedDayId === id) setSelectedDayId(next[0]?.id ?? null)
  }

  const moveDay = (id, dir) => {
    const idx = itinerary.days.findIndex(d => d.id === id)
    const target = idx + dir
    if (idx < 0 || target < 0 || target >= itinerary.days.length) return
    const next = [...itinerary.days]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    next.forEach((d, i) => { d.day = i + 1 })
    setItinerary({ ...itinerary, days: next })
  }

  return (
    <div className="app">
      <Toolbar
        fileName={fileName}
        onFileNameChange={setFileName}
        onOpen={handleFile}
        onNew={startNew}
        onDownload={download}
        onTripSettings={() => setShowTripSettings(true)}
        onCommonPhrases={() => setShowCommonPhrases(true)}
      />

      <div className="main">
        <Sidebar
          itinerary={itinerary}
          selectedDayId={selectedDayId}
          onSelect={setSelectedDayId}
          onAddDay={addDay}
          onDeleteDay={deleteDay}
          onMoveDay={moveDay}
        />
        <div className="detail">
          {selectedDay ? (
            <DayDetail
              day={selectedDay}
              onChange={updateDay}
            />
          ) : (
            <EmptyDetail onAddDay={addDay} />
          )}
        </div>
      </div>

      {showTripSettings && (
        <TripSettingsModal
          itinerary={itinerary}
          onChange={updateItinerary}
          onClose={() => setShowTripSettings(false)}
        />
      )}
      {showCommonPhrases && (
        <CommonPhrasesModal
          phrases={itinerary.commonPhrases}
          onChange={(commonPhrases) => updateItinerary({ ...itinerary, commonPhrases })}
          onClose={() => setShowCommonPhrases(false)}
        />
      )}
    </div>
  )
}

function Toolbar({ fileName, onFileNameChange, onOpen, onNew, onDownload,
                   onTripSettings, onCommonPhrases }) {
  const inputRef = useRef(null)
  return (
    <div className="toolbar">
      <div className="toolbar-left">
        <span className="toolbar-icon">✈️</span>
        <span className="toolbar-app-name">旅遊行程編輯器</span>
        <span className="toolbar-divider" />
        <input
          type="text"
          className="toolbar-filename"
          value={fileName}
          onChange={(e) => onFileNameChange(e.target.value)}
        />
      </div>
      <div className="toolbar-right">
        <button className="btn-secondary" onClick={onTripSettings}>旅程設定</button>
        <button className="btn-secondary" onClick={onCommonPhrases}>通用字卡</button>
        <button className="btn-secondary" onClick={() => inputRef.current?.click()}>開啟…</button>
        <button className="btn-secondary" onClick={onNew}>新建</button>
        <button className="btn-primary" onClick={onDownload}>下載 .md</button>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.markdown,text/markdown,text/plain"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onOpen(file)
            e.target.value = ''
          }}
        />
      </div>
    </div>
  )
}

function Sidebar({ itinerary, selectedDayId, onSelect, onAddDay, onDeleteDay, onMoveDay }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="trip-title">{itinerary.title || '未命名旅程'}</div>
        {itinerary.subtitle && (
          <div className="trip-subtitle">{itinerary.subtitle}</div>
        )}
      </div>
      <div className="day-list">
        {itinerary.days.map((day, idx) => (
          <DayRow
            key={day.id}
            day={day}
            isSelected={day.id === selectedDayId}
            isFirst={idx === 0}
            isLast={idx === itinerary.days.length - 1}
            onSelect={() => onSelect(day.id)}
            onDelete={() => onDeleteDay(day.id)}
            onMoveUp={() => onMoveDay(day.id, -1)}
            onMoveDown={() => onMoveDay(day.id, +1)}
          />
        ))}
        {itinerary.days.length === 0 && (
          <div className="empty muted">尚未有任何天數</div>
        )}
      </div>
      <div className="sidebar-footer">
        <button className="btn-link" onClick={onAddDay}>＋ 新增天</button>
      </div>
    </aside>
  )
}

function DayRow({ day, isSelected, isFirst, isLast, onSelect, onDelete, onMoveUp, onMoveDown }) {
  const stop = (fn) => (e) => { e.stopPropagation(); fn() }
  return (
    <div
      className={`day-row ${isSelected ? 'selected' : ''}`}
      onClick={onSelect}
    >
      <div className="day-row-flag">{day.flag || '📅'}</div>
      <div className="day-row-main">
        <div className="day-row-meta">
          第 {day.day} 天{day.date && <span className="muted"> · {day.date}</span>}
        </div>
        <div className="day-row-title">{day.title || '（未命名）'}</div>
        {day.city && <div className="day-row-city">{day.city}</div>}
      </div>
      <div className="day-row-actions">
        <button
          className="btn-icon"
          disabled={isFirst}
          onClick={stop(onMoveUp)}
        >▲</button>
        <button
          className="btn-icon"
          disabled={isLast}
          onClick={stop(onMoveDown)}
        >▼</button>
        <button
          className="btn-icon danger"
          onClick={stop(onDelete)}
        >🗑️</button>
      </div>
    </div>
  )
}

function EmptyDetail({ onAddDay }) {
  return (
    <div className="empty-detail">
      <div className="empty-icon">✈️</div>
      <div className="empty-text">選擇左側的天數開始編輯</div>
      <button className="btn-secondary" onClick={onAddDay}>新增第一天</button>
    </div>
  )
}

const SKILL_PROMPT = `你是一位旅遊行程整理助理。請把使用者提供的行程資料，整理成下方指定的 Markdown 格式，以便匯入旅遊行程編輯器。

## 輸出格式規範

整體結構：
\`\`\`
# 旅程標題
副標題（日期・天數・城市）

## 通用字卡

| 中文 | 英文 | 分類 |
|------|------|------|
| 謝謝 | Thank you | general |

---

## 第 N 天｜日期｜標題｜國旗｜城市

### 今日重點
- 重點一

### 飯店
名稱：飯店名稱
地址：地址
地圖：https://www.google.com/maps/...
備註：備註內容

### 行程

#### [時間] 類型 icon 標題
副標題
📍 https://www.google.com/maps/...
- 注意事項

### 英文字卡

| 中文 | 英文 | 分類 |
|------|------|------|
\`\`\`

## 重要規則

1. **天標題**：使用全形直線 ｜（U+FF5C），格式為 \`## 第 N 天｜日期｜標題｜國旗｜城市\`
2. **行程類型**只能用小寫英文：\`transport\`、\`food\`、\`sight\`、\`hotel\`、\`info\`
3. **字卡分類**只能是：\`general\`、\`transport\`、\`food\`、\`emergency\`
4. **飯店欄位**使用全形冒號：\`名稱：\`、\`地址：\`、\`地圖：\`、\`備註：\`
5. **地圖連結**必須是完整 Google Maps URL（不能用短網址）；如果沒有地圖資訊則省略 📍 那行
6. **行程標頭**格式：\`#### [時間] 類型 icon 標題\`，icon 可省略
7. **每天前面**必須有 \`---\` 獨立成一行
8. 副標題（緊接在 \`####\` 下方的第一個非空行）只能有一行

## 常見錯誤對照

| 錯誤 | 正確 |
|------|------|
| \`## 第1天|...\` | \`## 第 1 天｜...\`（有空格，全形｜） |
| \`Transport\` | \`transport\`（必須小寫） |
| \`地圖: https://...\` | \`地圖：https://...\`（全形冒號） |
| \`📍https://...\` | \`📍 https://...\`（📍 後有空格） |
| \`maps.app.goo.gl/xxx\` | 完整 Google Maps URL |

---

請根據以上規範，將使用者提供的行程資料整理成符合格式的 Markdown。如果資料不完整（例如缺少地圖網址），請省略對應欄位，不要自行填入假資料。整理完成後只輸出 Markdown 內容，不需要額外說明。`

function SkillPromptModal({ onClose }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(SKILL_PROMPT).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal skill-prompt-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">🤖 LLM 整理提示詞</span>
          <button className="btn-icon" onClick={onClose} title="關閉">✕</button>
        </div>
        <div className="modal-body">
          <p className="skill-prompt-desc">
            將此提示詞貼入 ChatGPT、Claude 等 LLM，再把你的行程資料貼上，
            LLM 就會幫你整理成可直接匯入本工具的 <code>.md</code> 格式。
          </p>
          <textarea
            className="skill-prompt-text"
            readOnly
            value={SKILL_PROMPT}
          />
          <div className="skill-prompt-actions">
            <button className="btn-primary" onClick={copy}>
              {copied ? '✓ 已複製！' : '📋 複製提示詞'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Welcome({ onOpen, onNew }) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [showSkillPrompt, setShowSkillPrompt] = useState(false)

  return (
    <div
      className={`welcome ${dragOver ? 'drag-over' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const file = e.dataTransfer.files?.[0]
        if (file) onOpen(file)
      }}
    >
      <div className="welcome-icon">✈️</div>
      <h1 className="welcome-title">旅遊行程編輯工具</h1>
      <p className="welcome-subtitle">開啟或新建 itinerary.md 檔案開始編輯</p>
      <div className="welcome-actions">
        <button
          className="btn-primary"
          onClick={() => inputRef.current?.click()}
        >📂 開啟行程檔案…</button>
        <button className="btn-secondary" onClick={onNew}>＋ 新建旅程</button>
      </div>
      <button className="btn-link welcome-skill-btn" onClick={() => setShowSkillPrompt(true)}>
        🤖 用 LLM 整理行程？取得提示詞
      </button>
      <p className="welcome-hint">提示：可直接把 itinerary.md 拖放到此視窗</p>
      <input
        ref={inputRef}
        type="file"
        accept=".md,.markdown,text/markdown,text/plain"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onOpen(file)
          e.target.value = ''
        }}
      />
      {showSkillPrompt && <SkillPromptModal onClose={() => setShowSkillPrompt(false)} />}
    </div>
  )
}
