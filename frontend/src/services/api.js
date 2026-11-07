const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export function token() {
  return localStorage.getItem('edusense_token')
}

function stringifyValue(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value.map(stringifyValue).filter(Boolean).join(', ')
  }
  if (typeof value === 'object') {
    return value.msg || value.message || value.detail || JSON.stringify(value)
  }
  return String(value)
}

function formatApiError(data, statusText) {
  const parts = [
    stringifyValue(data?.detail),
    stringifyValue(data?.message),
    stringifyValue(data?.error),
  ].filter(Boolean)
  return parts.join(' ') || statusText || 'Request failed'
}

export async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (token()) headers.Authorization = `Bearer ${token()}`

  let body = options.body
  if (body && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof Blob)) {
    body = JSON.stringify(body)
  }

  try {
    const response = await fetch(`${API_URL}${path}`, { ...options, headers, body })
    const raw = await response.text()
    let data = null
    if (raw) {
      try {
        data = JSON.parse(raw)
      } catch {
        data = { detail: raw }
      }
    }

    if (!response.ok) {
      throw new Error(formatApiError(data, response.statusText))
    }

    return data
  } catch (error) {
    if (error instanceof TypeError && /Failed to fetch|NetworkError/i.test(error.message)) {
      throw new Error(`Cannot reach the backend at ${API_URL.replace('/api', '')}. Start the FastAPI server on port 8000.`)
    }
    throw error
  }
}

export function staticUrl(path) {
  const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '')
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

export async function downloadAuthenticated(path, filename) {
  return downloadAuthenticatedRequest(path, filename)
}

export async function downloadAuthenticatedRequest(path, filename, options = {}) {
  const headers = {}
  if (token()) headers.Authorization = `Bearer ${token()}`
  const response = await fetch(`${API_URL}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } })
  if (!response.ok) {
    const raw = await response.text()
    let data = null
    try { data = JSON.parse(raw) } catch { data = { detail: raw } }
    throw new Error(formatApiError(data, response.statusText))
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
