import { useState } from 'react'
import { EVENT_TYPE_MAP, EVENT_TYPE_COLORS, WEEKDAYS } from '../constants.js'
import { newEvent } from '../parser.js'
import { FlagPicker, EventEditorModal, PhraseList } from './Modals.jsx'

export function DayDetail({ day, onChange }) {
  const update = (patch) => onChange({ ...day, ...patch })

  return (
    <div className="day-detail">
      <div className="day-detail-grid">
        <div className="day-col-main">
          <EventList
            events={day.events}
            onChange={(events) => update({ events })}
          />
          <Section icon="💬" title="英文字卡">
            <PhraseList
              phrases={day.phrases}
              onChange={(phrases) => update({ phrases })}
            />
          </Section>
        </div>

        <div className="day-col-side">
          <Section icon="ℹ️" title="基本資料">
            <div className="form-grid">
              <label>天期</label>
              <div className="row-inline">
                <span className="muted">第</span>
                <input
                  type="number"
                  className="num-input"
                  value={day.day}
                  onChange={(e) => update({ day: parseInt(e.target.value || '1', 10) })}
                />
                <span className="muted">天</span>
              </div>
              <label>日期</label>
              <DateField
                value={day.date}
                onChange={(date) => update({ date })}
              />
              <label>標題</label>
              <input
                type="text"
                value={day.title}
                onChange={(e) => update({ title: e.target.value })}
                placeholder="出發 → 維也納"
              />
              <label>城市</label>
              <div className="row-inline">
                <input
                  type="text"
                  value={day.city}
                  onChange={(e) => update({ city: e.target.value })}
                  placeholder="台灣 → 維也納"
                />
                <FlagPicker
                  flag={day.flag}
                  onChange={(flag) => update({ flag })}
                />
              </div>
            </div>
          </Section>

          <HotelEditor
            hotel={day.hotel}
            onChange={(hotel) => update({ hotel })}
          />

          <StringList
            icon="⭐"
            title="今日重點"
            items={day.highlights}
            onChange={(highlights) => update({ highlights })}
            placeholder="新增重點..."
          />
        </div>
      </div>
    </div>
  )
}

function Section({ icon, title, children, action }) {
  return (
    <div className="section-card">
      <div className="section-header">
        <span className="section-title">
          {icon && <span className="section-icon">{icon}</span>}
          {title}
        </span>
        {action}
      </div>
      <div className="section-content">{children}</div>
    </div>
  )
}

function DateField({ value, onChange }) {
  // value format: "4/1 (三)"
  const parsed = parseDateString(value)
  const isoValue = parsed ? toIsoDate(parsed) : ''

  const onInput = (e) => {
    const iso = e.target.value
    if (!iso) { onChange(''); return }
    const [y, m, d] = iso.split('-').map((s) => parseInt(s, 10))
    const date = new Date(Date.UTC(y, m - 1, d))
    const wd = WEEKDAYS[date.getUTCDay()]
    onChange(`${m}/${d} (${wd})`)
  }

  return (
    <div className="row-inline">
      <input type="date" value={isoValue} onChange={onInput} />
      {value && <span className="muted">{value}</span>}
    </div>
  )
}

function parseDateString(s) {
  if (!s) return null
  const m = s.match(/^\s*(\d+)\s*\/\s*(\d+)/)
  if (!m) return null
  return { month: parseInt(m[1], 10), day: parseInt(m[2], 10) }
}

function toIsoDate({ month, day }) {
  // Default to 2026 if no year encoded — matches Swift behaviour
  const year = 2026
  const mm = String(month).padStart(2, '0')
  const dd = String(day).padStart(2, '0')
  return `${year}-${mm}-${dd}`
}

function HotelEditor({ hotel, onChange }) {
  if (!hotel) {
    return (
      <Section icon="🛏️" title="住宿">
        <div className="row-inline space-between">
          <span className="muted">尚未設定住宿</span>
          <button
            className="btn-secondary"
            onClick={() => onChange({ name: '', address: '', mapUrl: '', notes: [] })}
          >新增住宿</button>
        </div>
      </Section>
    )
  }

  const update = (patch) => onChange({ ...hotel, ...patch })
  const updateNote = (idx, val) => {
    const notes = hotel.notes.map((n, i) => i === idx ? val : n)
    update({ notes })
  }
  const removeNote = (idx) => update({ notes: hotel.notes.filter((_, i) => i !== idx) })
  const addNote = () => update({ notes: [...hotel.notes, ''] })

  return (
    <Section icon="🛏️" title="住宿">
      <div className="form-grid">
        <label>名稱</label>
        <input
          type="text"
          value={hotel.name}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="飯店名稱"
        />
        <label>地址</label>
        <input
          type="text"
          value={hotel.address}
          onChange={(e) => update({ address: e.target.value })}
          placeholder="地址"
        />
        <label>地圖</label>
        <input
          type="text"
          value={hotel.mapUrl}
          onChange={(e) => update({ mapUrl: e.target.value })}
          placeholder="Google Maps URL"
        />
      </div>

      <div className="notes-block">
        <div className="notes-label">備註</div>
        {hotel.notes.map((n, idx) => (
          <div className="note-row" key={idx}>
            <input
              type="text"
              value={n}
              onChange={(e) => updateNote(idx, e.target.value)}
              placeholder="備註內容"
            />
            <button
              className="btn-icon danger"
              onClick={() => removeNote(idx)}
            >🗑️</button>
          </div>
        ))}
        <button className="btn-link" onClick={addNote}>＋ 新增備註</button>
      </div>

      <button
        className="btn-link danger"
        onClick={() => onChange(null)}
      >移除住宿資訊</button>
    </Section>
  )
}

function StringList({ icon, title, items, onChange, placeholder }) {
  const [draft, setDraft] = useState('')

  const update = (idx, val) => {
    const next = items.map((it, i) => i === idx ? val : it)
    onChange(next)
  }
  const remove = (idx) => onChange(items.filter((_, i) => i !== idx))
  const commit = () => {
    const trimmed = draft.trim()
    if (!trimmed) return
    onChange([...items, trimmed])
    setDraft('')
  }

  return (
    <Section icon={icon} title={title}>
      {items.map((it, idx) => (
        <div className="note-row" key={idx}>
          <input
            type="text"
            value={it}
            onChange={(e) => update(idx, e.target.value)}
          />
          <button
            className="btn-icon danger"
            onClick={() => remove(idx)}
          >🗑️</button>
        </div>
      ))}
      <div className="note-row">
        <input
          type="text"
          placeholder={placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') commit() }}
        />
        <button className="btn-icon" onClick={commit}>＋</button>
      </div>
    </Section>
  )
}

function EventList({ events, onChange }) {
  const [editing, setEditing] = useState(null) // { event, index | -1 }

  const remove = (idx) => onChange(events.filter((_, i) => i !== idx))
  const moveUp = (idx) => {
    if (idx === 0) return
    const next = [...events]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    onChange(next)
  }
  const moveDown = (idx) => {
    if (idx >= events.length - 1) return
    const next = [...events]
    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
    onChange(next)
  }

  return (
    <Section
      icon="📅"
      title="行程"
      action={
        <button
          className="btn-secondary"
          onClick={() => setEditing({ event: newEvent(), index: -1 })}
        >＋ 新增行程</button>
      }
    >
      {events.length === 0 && (
        <div className="empty">尚無行程項目</div>
      )}
      {events.map((event, idx) => (
        <EventRow
          key={event.id}
          event={event}
          isFirst={idx === 0}
          isLast={idx === events.length - 1}
          onClick={() => setEditing({ event, index: idx })}
          onDelete={() => remove(idx)}
          onMoveUp={() => moveUp(idx)}
          onMoveDown={() => moveDown(idx)}
        />
      ))}

      {editing && (
        <EventEditorModal
          initial={editing.event}
          onClose={() => setEditing(null)}
          onSave={(updated) => {
            if (editing.index === -1) {
              onChange([...events, updated])
            } else {
              const next = events.map((e, i) => i === editing.index ? updated : e)
              onChange(next)
            }
            setEditing(null)
          }}
        />
      )}
    </Section>
  )
}

function EventRow({ event, isFirst, isLast, onClick, onDelete, onMoveUp, onMoveDown }) {
  const meta = EVENT_TYPE_MAP[event.type] ?? EVENT_TYPE_MAP.info
  const color = EVENT_TYPE_COLORS[event.type] ?? '#6b7280'

  const stop = (fn) => (e) => { e.stopPropagation(); fn() }

  return (
    <div className="event-row" onClick={onClick}>
      <div className="event-time-col">
        <div className="event-time">{event.time || '--:--'}</div>
        <div className="event-icon">{event.icon || meta.defaultIcon}</div>
      </div>
      <div className="event-content">
        <div className="event-title-row">
          <span className="event-title">{event.title || '（未命名）'}</span>
          <span
            className="event-type-badge"
            style={{ background: color + '22', color }}
          >{meta.label}</span>
          {event.mapUrl && <span className="event-map-icon">🗺️</span>}
        </div>
        {event.subtitle && (
          <div className="event-subtitle">{event.subtitle}</div>
        )}
        {event.notes.length > 0 && (
          <div className="event-notes">
            {event.notes.slice(0, 2).join('・')}
          </div>
        )}
      </div>
      <div className="event-actions">
        <button
          className="btn-icon"
          disabled={isFirst}
          onClick={stop(onMoveUp)}
          title="上移"
        >▲</button>
        <button
          className="btn-icon"
          disabled={isLast}
          onClick={stop(onMoveDown)}
          title="下移"
        >▼</button>
        <button
          className="btn-icon danger"
          onClick={stop(onDelete)}
          title="刪除"
        >🗑️</button>
      </div>
    </div>
  )
}
