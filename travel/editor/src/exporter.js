function dayHeader(day) {
  return `## 第 ${day.day} 天｜${day.date}｜${day.title}｜${day.flag}｜${day.city}`
}

function eventHeader(event) {
  const parts = ['####', `[${event.time}]`, event.type]
  if (event.icon) parts.push(event.icon)
  parts.push(event.title)
  return parts.join(' ')
}

export function exportMarkdown(itinerary) {
  const out = []

  out.push(`# ${itinerary.title}`)
  if (itinerary.subtitle) out.push(itinerary.subtitle)
  out.push('')

  out.push('## 通用字卡')
  out.push('')
  out.push('| 中文 | 英文 | 分類 |')
  out.push('|------|------|------|')
  for (const p of itinerary.commonPhrases) {
    out.push(`| ${p.zh} | ${p.en} | ${p.category} |`)
  }
  out.push('')

  for (const day of itinerary.days) {
    out.push('---')
    out.push('')
    out.push(dayHeader(day))
    out.push('')

    if (day.highlights.length > 0) {
      out.push('### 今日重點')
      for (const h of day.highlights) out.push(`- ${h}`)
      out.push('')
    }

    if (day.hotel) {
      out.push('### 飯店')
      out.push(`名稱：${day.hotel.name}`)
      out.push(`地址：${day.hotel.address}`)
      if (day.hotel.mapUrl) out.push(`地圖：${day.hotel.mapUrl}`)
      for (const note of day.hotel.notes) out.push(`備註：${note}`)
      out.push('')
    }

    if (day.events.length > 0) {
      out.push('### 行程')
      out.push('')
      for (const event of day.events) {
        out.push(eventHeader(event))
        if (event.subtitle) out.push(event.subtitle)
        if (event.mapUrl) out.push(`📍 ${event.mapUrl}`)
        for (const note of event.notes) out.push(`- ${note}`)
        out.push('')
      }
    }

    if (day.phrases.length > 0) {
      out.push('### 英文字卡')
      out.push('')
      out.push('| 中文 | 英文 | 分類 |')
      out.push('|------|------|------|')
      for (const p of day.phrases) {
        out.push(`| ${p.zh} | ${p.en} | ${p.category} |`)
      }
      out.push('')
    }
  }

  return out.join('\n')
}
