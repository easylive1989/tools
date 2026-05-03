import { useEffect, useState } from 'react'
import { COMMON_FLAGS, EVENT_TYPES, PHRASE_CATEGORIES } from '../constants.js'
import { newPhrase, newEvent } from '../parser.js'

export function Modal({ title, onClose, width = 600, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={{ width }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button className="btn-icon" onClick={onClose} title="關閉">✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

export function FlagPicker({ flag, onChange }) {
  return (
    <details className="flag-picker">
      <summary className="flag-summary">{flag || '🏳️'}</summary>
      <div className="flag-grid">
        {COMMON_FLAGS.map(([emoji, name]) => (
          <button
            key={emoji}
            className={`flag-cell ${flag === emoji ? 'active' : ''}`}
            onClick={(e) => {
              onChange(emoji)
              e.currentTarget.closest('details').open = false
            }}
          >
            <span className="flag-emoji">{emoji}</span>
            <span className="flag-name">{name}</span>
          </button>
        ))}
      </div>
    </details>
  )
}

export function TripSettingsModal({ itinerary, onChange, onClose }) {
  return (
    <Modal title="旅程設定" onClose={onClose} width={520}>
      <div className="form-grid">
        <label>標題</label>
        <input
          type="text"
          value={itinerary.title}
          onChange={(e) => onChange({ ...itinerary, title: e.target.value })}
          placeholder="奧捷旅遊手冊 2026"
        />
        <label>副標題</label>
        <input
          type="text"
          value={itinerary.subtitle}
          onChange={(e) => onChange({ ...itinerary, subtitle: e.target.value })}
          placeholder="日期・天數・城市"
        />
      </div>
    </Modal>
  )
}

export function PhraseList({ phrases, onChange }) {
  const update = (idx, patch) => {
    const next = phrases.map((p, i) => i === idx ? { ...p, ...patch } : p)
    onChange(next)
  }
  const remove = (idx) => onChange(phrases.filter((_, i) => i !== idx))
  const add = () => onChange([...phrases, newPhrase()])

  return (
    <div className="phrase-list">
      {phrases.length === 0 && (
        <div className="empty">尚無字卡</div>
      )}
      {phrases.map((p, idx) => (
        <div className="phrase-row" key={p.id}>
          <div className="phrase-fields">
            <input
              type="text"
              className="phrase-zh"
              placeholder="中文"
              value={p.zh}
              onChange={(e) => update(idx, { zh: e.target.value })}
            />
            <input
              type="text"
              className="phrase-en"
              placeholder="English"
              value={p.en}
              onChange={(e) => update(idx, { en: e.target.value })}
            />
            <select
              value={p.category}
              onChange={(e) => update(idx, { category: e.target.value })}
            >
              {PHRASE_CATEGORIES.map(c => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
          <button
            className="btn-icon danger"
            onClick={() => remove(idx)}
            title="刪除"
          >🗑️</button>
        </div>
      ))}
      <button className="btn-link" onClick={add}>＋ 新增字卡</button>
    </div>
  )
}

export function CommonPhrasesModal({ phrases, onChange, onClose }) {
  return (
    <Modal title="通用字卡" onClose={onClose} width={680}>
      <PhraseList phrases={phrases} onChange={onChange} />
    </Modal>
  )
}

export function EventEditorModal({ initial, onSave, onClose }) {
  const [event, setEvent] = useState(initial ?? newEvent())

  const update = (patch) => setEvent({ ...event, ...patch })
  const updateNote = (idx, val) => {
    const notes = event.notes.map((n, i) => i === idx ? val : n)
    update({ notes })
  }
  const removeNote = (idx) => update({ notes: event.notes.filter((_, i) => i !== idx) })
  const addNote = () => update({ notes: [...event.notes, ''] })

  const useDefaultIcon = () => {
    const t = EVENT_TYPES.find(t => t.value === event.type)
    update({ icon: t.defaultIcon })
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={{ width: 600 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <button className="btn-link" onClick={onClose}>取消</button>
          <span className="modal-title">{event.title || '新增行程'}</span>
          <button className="btn-primary" onClick={() => onSave(event)}>儲存</button>
        </div>
        <div className="modal-body">
          <div className="form-grid">
            <label>時間</label>
            <input
              type="text"
              value={event.time}
              onChange={(e) => update({ time: e.target.value })}
              placeholder="例：10:46"
            />
            <label>類型</label>
            <div className="segmented">
              {EVENT_TYPES.map(t => (
                <button
                  key={t.value}
                  className={`segment ${event.type === t.value ? 'active' : ''}`}
                  onClick={() => update({ type: t.value })}
                >{t.label}</button>
              ))}
            </div>
            <label>圖示</label>
            <div className="row-inline">
              <input
                type="text"
                className="icon-input"
                value={event.icon}
                onChange={(e) => update({ icon: e.target.value })}
                placeholder="🚌"
              />
              <button className="btn-secondary" onClick={useDefaultIcon}>預設</button>
            </div>
            <label>標題</label>
            <input
              type="text"
              value={event.title}
              onChange={(e) => update({ title: e.target.value })}
              placeholder="行程標題"
            />
            <label>副標題</label>
            <input
              type="text"
              value={event.subtitle}
              onChange={(e) => update({ subtitle: e.target.value })}
              placeholder="地點或說明"
            />
            <label>地圖</label>
            <input
              type="text"
              value={event.mapUrl}
              onChange={(e) => update({ mapUrl: e.target.value })}
              placeholder="Google Maps URL"
            />
          </div>

          <div className="notes-block">
            <div className="notes-label">注意事項</div>
            {event.notes.map((n, idx) => (
              <div className="note-row" key={idx}>
                <input
                  type="text"
                  value={n}
                  onChange={(e) => updateNote(idx, e.target.value)}
                />
                <button
                  className="btn-icon danger"
                  onClick={() => removeNote(idx)}
                >🗑️</button>
              </div>
            ))}
            <button className="btn-link" onClick={addNote}>＋ 新增注意事項</button>
          </div>
        </div>
      </div>
    </div>
  )
}
