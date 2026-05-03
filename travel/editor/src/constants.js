export const EVENT_TYPES = [
  { value: 'transport', label: '交通', defaultIcon: '🚌' },
  { value: 'food',      label: '飲食', defaultIcon: '🍽️' },
  { value: 'sight',     label: '景點', defaultIcon: '📸' },
  { value: 'hotel',     label: '住宿', defaultIcon: '🏨' },
  { value: 'info',      label: '資訊', defaultIcon: 'ℹ️' },
]

export const EVENT_TYPE_MAP = Object.fromEntries(EVENT_TYPES.map(t => [t.value, t]))

export const EVENT_TYPE_COLORS = {
  transport: '#3b82f6',
  food:      '#f97316',
  sight:     '#22c55e',
  hotel:     '#a855f7',
  info:      '#6b7280',
}

export const PHRASE_CATEGORIES = [
  { value: 'general',   label: '一般' },
  { value: 'transport', label: '交通' },
  { value: 'food',      label: '飲食' },
  { value: 'emergency', label: '緊急' },
]

export const COMMON_FLAGS = [
  ['🇹🇼', '台灣'], ['🇦🇹', '奧地利'], ['🇨🇿', '捷克'],
  ['🇩🇪', '德國'], ['🇨🇭', '瑞士'], ['🇮🇹', '義大利'],
  ['🇫🇷', '法國'], ['🇪🇸', '西班牙'], ['🇬🇧', '英國'],
  ['🇯🇵', '日本'], ['🇰🇷', '韓國'], ['🇺🇸', '美國'],
  ['🇹🇭', '泰國'], ['🇸🇬', '新加坡'], ['🇭🇰', '香港'],
  ['🇳🇱', '荷蘭'], ['🇧🇪', '比利時'], ['🇵🇱', '波蘭'],
  ['🇭🇺', '匈牙利'], ['🇸🇰', '斯洛伐克'], ['🇭🇷', '克羅埃西亞'],
]

export const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']
