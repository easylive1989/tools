import { EVENT_TYPE_MAP } from './constants.js'

let _idCounter = 0
const nextId = () => `id-${Date.now()}-${++_idCounter}`

export function newPhrase() {
  return { id: nextId(), zh: '', en: '', category: 'general' }
}

export function newEvent() {
  return {
    id: nextId(), time: '', type: 'info', icon: '',
    title: '', subtitle: '', mapUrl: '', notes: [],
  }
}

export function newDay(num = 1) {
  return {
    id: nextId(), day: num, date: '', title: '新行程',
    city: '', flag: '🇦🇹',
    highlights: [], hotel: null, events: [], phrases: [],
  }
}

export function newItinerary() {
  return { title: '新旅程', subtitle: '', commonPhrases: [], days: [] }
}

const EMOJI_RE = /\p{Extended_Pictographic}/u

function isEmoji(s) {
  return !!s && EMOJI_RE.test(s)
}

function parseTableRow(line) {
  if (!line.startsWith('|')) return null
  const cols = line.split('|').map(c => c.trim()).filter(c => c !== '')
  if (cols.length < 3) return null
  if (cols[0] === '中文' || cols[0].startsWith('---')) return null
  const category = ['general', 'transport', 'food', 'emergency'].includes(cols[2])
    ? cols[2] : 'general'
  return { id: nextId(), zh: cols[0], en: cols[1], category }
}

function parseDayHeader(line) {
  // "## 第 1 天｜4/1 (三)｜出發 → 維也納抵達｜🇦🇹｜台灣 → 維也納"
  const content = line.slice(3) // remove "## "
  const parts = content.split('｜').map(p => p.trim())
  let dayNum = 1
  if (parts.length > 0) {
    const m = parts[0].match(/\d+/)
    if (m) dayNum = parseInt(m[0], 10)
  }
  return {
    day: dayNum,
    date:  parts[1] || '',
    title: parts[2] || '',
    flag:  parts[3] || '',
    city:  parts[4] || '',
  }
}

function parseEvent(lines, start) {
  const event = newEvent()
  const header = lines[start].replace(/^####\s*/, '')

  const timeMatch = header.match(/^\[([^\]]*)\]\s*/)
  let rest = header
  if (timeMatch) {
    event.time = timeMatch[1]
    rest = header.slice(timeMatch[0].length)
  }

  const tokens = rest.split(' ')
  if (tokens.length > 0 && EVENT_TYPE_MAP[tokens[0]]) {
    event.type = tokens[0]
    rest = tokens.slice(1).join(' ')
  }

  const tail = rest.split(' ')
  if (tail.length > 0 && isEmoji(tail[0])) {
    event.icon = tail[0]
    rest = tail.slice(1).join(' ')
  } else {
    event.icon = EVENT_TYPE_MAP[event.type].defaultIcon
  }

  event.title = rest

  let i = start + 1
  let subtitleSet = false
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('####') || line.startsWith('###') ||
        line.startsWith('##') || line === '---') break
    if (line.startsWith('📍 ')) {
      event.mapUrl = line.slice('📍 '.length)
    } else if (line.startsWith('- ')) {
      event.notes.push(line.slice(2))
    } else if (line !== '' && !subtitleSet) {
      event.subtitle = line
      subtitleSet = true
    }
    i++
  }
  return [event, i]
}

function parseDay(headerInfo, lines, start) {
  const day = newDay(headerInfo.day)
  day.day = headerInfo.day
  day.date = headerInfo.date
  day.title = headerInfo.title
  day.flag = headerInfo.flag
  day.city = headerInfo.city

  let i = start
  let section = ''

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith('## 第')) break

    if (line.startsWith('### ')) {
      section = line
      i++
      continue
    }

    if (section.includes('今日重點')) {
      if (line.startsWith('- ')) day.highlights.push(line.slice(2))
      i++; continue
    }

    if (section.includes('飯店')) {
      if (line.startsWith('名稱：')) {
        if (!day.hotel) day.hotel = { name: '', address: '', mapUrl: '', notes: [] }
        day.hotel.name = line.slice(3)
      } else if (line.startsWith('地址：')) {
        if (!day.hotel) day.hotel = { name: '', address: '', mapUrl: '', notes: [] }
        day.hotel.address = line.slice(3)
      } else if (line.startsWith('地圖：')) {
        if (!day.hotel) day.hotel = { name: '', address: '', mapUrl: '', notes: [] }
        day.hotel.mapUrl = line.slice(3)
      } else if (line.startsWith('備註：')) {
        if (!day.hotel) day.hotel = { name: '', address: '', mapUrl: '', notes: [] }
        day.hotel.notes.push(line.slice(3))
      } else if (line.startsWith('- ')) {
        if (!day.hotel) day.hotel = { name: '', address: '', mapUrl: '', notes: [] }
        day.hotel.notes.push(line.slice(2))
      }
      i++; continue
    }

    if (section.includes('行程')) {
      if (line.startsWith('#### ')) {
        const [event, nextI] = parseEvent(lines, i)
        day.events.push(event)
        i = nextI
        continue
      }
      i++; continue
    }

    if (section.includes('英文字卡')) {
      const phrase = parseTableRow(line)
      if (phrase) day.phrases.push(phrase)
      i++; continue
    }

    i++
  }

  return [day, i]
}

export function parseMarkdown(text) {
  const itinerary = newItinerary()
  itinerary.title = ''
  itinerary.subtitle = ''
  const lines = text.split('\n')
  let i = 0

  // Title block
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('# ') && !line.startsWith('## ')) {
      itinerary.title = line.slice(2)
      i++
      if (i < lines.length && !lines[i].startsWith('#') && lines[i] !== '') {
        itinerary.subtitle = lines[i]
      }
    } else if (line === '## 通用字卡') {
      break
    }
    i++
  }

  // Common phrases
  if (i < lines.length && lines[i] === '## 通用字卡') {
    i++
    while (i < lines.length &&
           !lines[i].startsWith('---') &&
           !lines[i].startsWith('## 第')) {
      const phrase = parseTableRow(lines[i])
      if (phrase) itinerary.commonPhrases.push(phrase)
      i++
    }
  }

  // Days
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('## 第')) {
      const headerInfo = parseDayHeader(line)
      i++
      const [day, nextI] = parseDay(headerInfo, lines, i)
      itinerary.days.push(day)
      i = nextI
    } else {
      i++
    }
  }

  return itinerary
}
