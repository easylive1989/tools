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

function Welcome({ onOpen, onNew }) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

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
    </div>
  )
}
