import { useEffect, useState } from 'react'
import { api } from '../services/api'

export function useInstructorSessions() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/sessions')
      .then((data) => setSessions(Array.isArray(data) ? data : []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false))
  }, [])

  return { sessions, loading }
}

export function SessionPickerFields({ form, setForm, showLinkSession = true, showSourceSession = true }) {
  const { sessions, loading } = useInstructorSessions()

  const options = [
    { value: '', label: loading ? 'Loading sessions...' : 'None' },
    ...sessions.map((s) => ({ value: String(s.id), label: `${s.title} (${s.date})` })),
  ]

  function Select({ label, hint, field }) {
    return (
      <label className="space-y-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
        <span>{label}</span>
        {hint && <p className="text-xs font-normal text-slate-500">{hint}</p>}
        <select
          className="input"
          value={form[field] ?? ''}
          onChange={(e) => setForm({ ...form, [field]: e.target.value })}
        >
          {options.map((opt) => (
            <option key={`${field}-${opt.value || 'none'}`} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>
    )
  }

  if (!showLinkSession && !showSourceSession) return null

  return (
    <>
      {showLinkSession && (
        <Select
          label="Link to session"
          hint="Students enrolled in this session can access the generated content."
          field="session_id"
        />
      )}
      {showSourceSession && (
        <Select
          label="Use uploaded preparation from"
          hint="Pulls text from PDFs and documents you uploaded to that session."
          field="source_session_id"
        />
      )}
    </>
  )
}
