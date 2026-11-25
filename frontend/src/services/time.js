// Issue U2: the API sends ISO-8601 UTC ("...Z"); the browser renders local time.
// Never call toLocaleString() on an API timestamp directly: browsers read a
// string without a zone as local time, which is what produced 06:19 instead of
// 08:19 in Africa/Cairo.

export function parseUtc(value) {
  if (!value) return null
  if (value instanceof Date) return value
  const text = String(value).trim()
  // A bare "2026-11-23T06:19:00" from an older record is UTC, not local time.
  const normalized = /^\d{4}-\d{2}-\d{2}T[\d:.]+$/.test(text) ? `${text}Z` : text
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value, options) {
  const date = parseUtc(value)
  if (!date) return ''
  return date.toLocaleString(undefined, options || {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function formatDate(value, options) {
  const date = parseUtc(value)
  if (!date) return ''
  return date.toLocaleDateString(undefined, options || { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatTime(value, options) {
  const date = parseUtc(value)
  if (!date) return ''
  return date.toLocaleTimeString(undefined, options || { hour: '2-digit', minute: '2-digit' })
}

export function isoOf(value) {
  const date = parseUtc(value)
  return date ? date.toISOString() : ''
}
