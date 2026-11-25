/**
 * Normalize citation/source entries into one stable shape.
 *
 * Legacy chat messages stored sources as plain strings or objects with
 * different keys ({source_file,page,...} vs {title,url}). Rendering raw
 * objects as React children crashes the app, so every display site must go
 * through normalizeSource/normalizeSources.
 */

/** @returns {{label:string, url:string|null, page:number|null, raw:*}} */
export function normalizeSource(entry) {
  if (entry == null) return null
  if (typeof entry === 'string') {
    const label = entry.trim()
    return label ? { label, url: null, page: null, raw: entry } : null
  }
  if (typeof entry !== 'object') return null

  const page = Number.isFinite(entry.page) ? entry.page : (Number.isFinite(entry.page_number) ? entry.page_number : null)
  const label =
    entry.source_file || entry.filename || entry.title || entry.name ||
    entry.file || entry.document || entry.url || 'Source'
  const url = entry.url || entry.link || entry.file_url || null
  const text = String(label).trim()
  if (!text) return null
  return { label: text, url: typeof url === 'string' && url ? url : null, page, raw: entry }
}

/** Normalize a sources array; drops null/invalid entries. */
export function normalizeSources(list) {
  if (!Array.isArray(list)) return []
  return list.map(normalizeSource).filter(Boolean)
}
