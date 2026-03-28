import { useState, useRef, useEffect, useCallback } from 'react'
import { days, commonPhrases } from './data/itinerary.js'

// ===== Helper: TTS =====
function useTTS() {
  const [speaking, setSpeaking] = useState(false)

  const speak = useCallback((text) => {
    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-US'
    utterance.rate = 0.9
    utterance.onstart = () => setSpeaking(true)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utterance)
  }, [])

  const cancel = useCallback(() => {
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [])

  return { speak, cancel, speaking }
}

// ===== Helper: Type Label =====
const TYPE_LABELS = {
  transport: '交通',
  food: '飲食',
  sight: '景點',
  hotel: '住宿',
  info: '資訊',
}

// ===== Toast Component =====
function Toast({ message, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 1800)
    return () => clearTimeout(t)
  }, [onDone])
  return <div className="toast">{message}</div>
}

// ===== Phrase Full View =====
function PhraseFullView({ phrase, onClose }) {
  const { speak, cancel, speaking } = useTTS()

  // 進入大字版時自動播放
  useEffect(() => {
    speak(phrase.en)
    return () => cancel()
  }, [phrase.en])

  const handleSpeak = (e) => {
    e.stopPropagation()
    speak(phrase.en)
  }

  return (
    <div className="phrase-full-view" onClick={onClose}>
      <button className="phrase-full-close" onClick={onClose}>✕</button>
      <div className="phrase-full-zh">{phrase.zh}</div>
      <div className="phrase-full-en">{phrase.en}</div>
      <button
        className={`phrase-full-tts ${speaking ? 'speaking' : ''}`}
        onClick={handleSpeak}
        title="朗讀英文"
      >
        {speaking ? '🔊' : '🔈'}
      </button>
      <div className="phrase-full-hint">點任意處關閉</div>
    </div>
  )
}

// ===== Phrase Card =====
function PhraseCard({ phrase, onFullView, onCopied }) {
  const { speak, speaking } = useTTS()

  const handleCopy = (e) => {
    e.stopPropagation()
    if (navigator.clipboard) {
      navigator.clipboard.writeText(phrase.en).then(() => onCopied('已複製英文字卡！'))
    }
  }

  const handleSpeak = (e) => {
    e.stopPropagation()
    speak(phrase.en)
  }

  return (
    <div className="phrase-card" onClick={() => onFullView(phrase)}>
      <div className="phrase-zh">{phrase.zh}</div>
      <div className="phrase-en">{phrase.en}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
        <span className="phrase-tap-hint">點擊大字版 · 方便給外國人看</span>
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            onClick={handleSpeak}
            className={`phrase-btn ${speaking ? 'speaking' : ''}`}
            title="朗讀英文"
          >
            {speaking ? '🔊' : '🔈'}
          </button>
          <button
            onClick={handleCopy}
            className="phrase-btn"
          >
            複製
          </button>
        </div>
      </div>
    </div>
  )
}

// ===== Common Phrases Modal =====
function CommonPhrasesModal({ onClose, onFullView, onCopied }) {
  const [filter, setFilter] = useState('all')

  const filters = [
    { key: 'all', label: '全部' },
    { key: 'general', label: '一般' },
    { key: 'transport', label: '交通' },
    { key: 'food', label: '飲食' },
    { key: 'emergency', label: '緊急' },
  ]

  const filtered = filter === 'all'
    ? commonPhrases
    : commonPhrases.filter(p => p.category === filter)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-handle" />
        <div className="modal-header">
          <div className="modal-title">🌐 常用字卡</div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="phrase-filter">
          {filters.map(f => (
            <button
              key={f.key}
              className={`filter-btn ${filter === f.key ? 'active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {filtered.map((phrase, i) => (
            <PhraseCard
              key={i}
              phrase={phrase}
              onFullView={onFullView}
              onCopied={onCopied}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ===== Timeline Event Card =====
function EventCard({ event }) {
  const type = event.type || 'info'

  return (
    <div className="timeline-item">
      <div className="timeline-left">
        <div className="timeline-time">{event.time}</div>
        <div className={`timeline-dot dot-${type}`}>{event.icon}</div>
      </div>
      <div className={`timeline-card card-${type}`}>
        <div className="card-header">
          <div style={{ flex: 1 }}>
            <div className="card-title">{event.title}</div>
            {event.subtitle && <div className="card-subtitle">{event.subtitle}</div>}
          </div>
          <span className={`type-badge badge-${type}`}>{TYPE_LABELS[type]}</span>
        </div>
        {event.notes && event.notes.length > 0 && (
          <div className="card-notes">
            {event.notes.map((note, i) => (
              <div key={i} className="card-note">{note}</div>
            ))}
          </div>
        )}
        {event.mapUrl && (
          <a
            href={event.mapUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="card-map-link"
          >
            📍 在 Google Maps 查看
          </a>
        )}
      </div>
    </div>
  )
}

// ===== Day Page =====
function DayPage({ dayData, onFullView, onCopied }) {
  const [showPhrases, setShowPhrases] = useState(false)

  return (
    <div className="day-page">
      {/* Day Hero */}
      <div className="day-hero">
        <div className="day-hero-header">
          <div className="day-hero-title-group">
            <div className="day-number">第 {dayData.day} 天 · {dayData.date}</div>
            <div className="day-title">{dayData.title}</div>
            <div className="day-city">📍 {dayData.city}</div>
          </div>
          <div className="day-flag">{dayData.flag}</div>
        </div>

        {dayData.highlights && dayData.highlights.length > 0 && (
          <div className="day-highlights">
            {dayData.highlights.map((h, i) => (
              <div key={i} className="highlight-item">
                <div className="highlight-dot" />
                <span>{h}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Hotel */}
      {dayData.hotel && (
        <div className="hotel-card">
          <div className="hotel-icon">🏨</div>
          <div className="hotel-info">
            <div className="hotel-name">{dayData.hotel.name}</div>
            <div className="hotel-address">{dayData.hotel.address}</div>
            {dayData.hotel.notes && Array.isArray(dayData.hotel.notes)
              ? dayData.hotel.notes.map((n, i) => (
                  <div key={i} className="hotel-note">{n}</div>
                ))
              : dayData.hotel.notes && (
                  <div className="hotel-note">{dayData.hotel.notes}</div>
                )
            }
            {dayData.hotel.mapUrl && (
              <a href={dayData.hotel.mapUrl} target="_blank" rel="noopener noreferrer" className="hotel-map-link">
                📍 地圖
              </a>
            )}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="section-title">📅 今日行程</div>
      <div className="timeline">
        {dayData.events.map((event, i) => (
          <EventCard key={i} event={event} />
        ))}
      </div>

      {/* Day Phrases */}
      {dayData.phrases && dayData.phrases.length > 0 && (
        <>
          <div className="section-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: 16 }}>
            <span>💬 今日字卡</span>
            <button
              onClick={() => setShowPhrases(p => !p)}
              style={{
                background: showPhrases ? '#1a3a5c' : 'white',
                border: '1.5px solid #1a3a5c',
                borderRadius: 20,
                padding: '3px 12px',
                fontSize: '0.7rem',
                color: showPhrases ? 'white' : '#1a3a5c',
                cursor: 'pointer',
              }}
            >
              {showPhrases ? '收起' : '展開'}
            </button>
          </div>

          {showPhrases && (
            <div className="phrases-section">
              {dayData.phrases.map((phrase, i) => (
                <PhraseCard
                  key={i}
                  phrase={phrase}
                  onFullView={onFullView}
                  onCopied={onCopied}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ===== Main App =====
export default function App() {
  const [activeDay, setActiveDay] = useState(1)
  const [showCommonPhrases, setShowCommonPhrases] = useState(false)
  const [fullViewPhrase, setFullViewPhrase] = useState(null)
  const [toast, setToast] = useState(null)
  const navRef = useRef(null)

  const currentDay = days.find(d => d.day === activeDay) || days[0]

  // Auto scroll active tab into view
  useEffect(() => {
    if (navRef.current) {
      const activeTab = navRef.current.querySelector('.day-tab.active')
      if (activeTab) {
        activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
      }
    }
  }, [activeDay])

  const handleDayChange = (day) => {
    setActiveDay(day)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleCopied = (msg) => {
    setToast(msg)
  }

  return (
    <div className="app">
      {/* Header */}
      <div className="header">
        <div className="header-top">
          <span className="header-flags">🇦🇹 🇨🇿</span>
          <span className="header-title">奧捷旅遊手冊 2026</span>
        </div>
        <div className="header-subtitle">2026/4/1 – 4/10 · 9天8夜 · 維也納・哈修塔特・薩爾茲堡・庫倫諾夫・布拉格</div>

        {/* Day Nav */}
        <div className="day-nav" ref={navRef}>
          {days.map(d => (
            <button
              key={d.day}
              className={`day-tab ${activeDay === d.day ? 'active' : ''}`}
              onClick={() => handleDayChange(d.day)}
            >
              <span className="day-tab-num">{d.day}</span>
              <span className="day-tab-date">{d.date}</span>
              <span className="day-tab-flag">{d.flag}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Day Content */}
      <DayPage
        dayData={currentDay}
        onFullView={setFullViewPhrase}
        onCopied={handleCopied}
      />

      {/* FAB: Common Phrases */}
      <button
        className="fab"
        onClick={() => setShowCommonPhrases(true)}
        title="常用字卡"
      >
        🌐
      </button>

      {/* Common Phrases Modal */}
      {showCommonPhrases && (
        <CommonPhrasesModal
          onClose={() => setShowCommonPhrases(false)}
          onFullView={(phrase) => {
            setShowCommonPhrases(false)
            setFullViewPhrase(phrase)
          }}
          onCopied={handleCopied}
        />
      )}

      {/* Full View Phrase */}
      {fullViewPhrase && (
        <PhraseFullView
          phrase={fullViewPhrase}
          onClose={() => setFullViewPhrase(null)}
        />
      )}

      {/* Toast */}
      {toast && (
        <Toast message={toast} onDone={() => setToast(null)} />
      )}
    </div>
  )
}
