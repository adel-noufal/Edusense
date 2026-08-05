import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, PlayCircle, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../services/api'
import { useLanguage } from '../context/LanguageContext'

const initialForm = {
  title: '',
  description: '',
  date: new Date().toISOString().slice(0, 10),
  start_time: '10:00',
  duration: 60,
  max_students: '',
}

export default function Sessions() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await api('/sessions')
      setSessions(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.message)
      setSessions([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function create(e) {
    e.preventDefault()
    setError('')
    try {
      const payload = {
        ...form,
        max_students: form.max_students ? Number(form.max_students) : null
      }
      await api('/sessions', { method: 'POST', body: JSON.stringify(payload) })
      setForm((current) => ({ ...current, title: '', description: '', max_students: '' }))
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(id) {
    try { await api(`/sessions/${id}`, { method: 'DELETE' }); await load() } catch (err) { setError(err.message) }
  }

  async function startSession(id) {
    try {
      await api(`/sessions/${id}/start`, { method: 'POST' })
      navigate(`/instructor/sessions/${id}/live`)
    } catch (err) { setError(err.message) }
  }

  async function endSession(id) {
    try { await api(`/sessions/${id}/end`, { method: 'POST' }); await load() } catch (err) { setError(err.message) }
  }

  return (
    <div className="page-shell grid gap-6 xl:grid-cols-[minmax(280px,380px)_1fr]">
      <form className="panel space-y-3" onSubmit={create}>
        <div className="flex items-center gap-3">
          <BookOpen size={20} className="text-ocean dark:text-mint" />
          <h1 className="text-xl font-black">{t('sessions.title')}</h1>
        </div>
        <p className="text-sm text-slate-500">{t('sessions.subtitle')}</p>
        <input className="input" placeholder={t('sessions.titleField')} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea className="input min-h-28" placeholder={t('sessions.description')} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <input className="input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        <input className="input" type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
        <div className="grid grid-cols-2 gap-3">
          <input className="input" type="number" min="5" max="480" value={form.duration} onChange={(e) => setForm({ ...form, duration: Number(e.target.value) })} />
          <input className="input" type="number" min="1" max="500" placeholder="Seats (Optional)" value={form.max_students} onChange={(e) => setForm({ ...form, max_students: e.target.value })} />
        </div>
        <button className="btn-primary w-full"><Plus size={18} />{t('sessions.create')}</button>
      </form>

      <div className="panel space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xl font-black">{t('sessions.scheduled')}</h2>
          <button className="btn-soft" type="button" onClick={load}><RefreshCw size={18} />{t('sessions.refresh')}</button>
        </div>
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
        {loading && <p className="text-sm text-slate-500">{t('sessions.loading')}</p>}
        {!loading && sessions.length === 0 && !error && <p className="text-sm text-slate-500">{t('sessions.empty')}</p>}
        <div className="space-y-3">
          {sessions.map((session) => (
            <div className="rounded-md border border-slate-200 p-4 dark:border-slate-700" key={session.id}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-lg font-bold">{session.title}</p>
                  <p className="text-sm text-slate-500">{session.date} | {session.start_time} | {session.status}</p>
                  <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{session.description || t('sessions.noDescription')}</p>
                </div>
                {session.max_students ? (
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase dark:bg-slate-800">{session.max_students} {t('sessions.seats')}</span>
                ) : (
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase dark:bg-slate-800">Unlimited</span>
                )}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button className="btn-soft" type="button" onClick={() => startSession(session.id)}><PlayCircle size={18} />{t('sessions.start')}</button>
                <button className="btn-soft" type="button" onClick={() => endSession(session.id)}>{t('sessions.end')}</button>
                <button className="btn-soft" type="button" onClick={() => remove(session.id)}><Trash2 size={18} />{t('sessions.delete')}</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
