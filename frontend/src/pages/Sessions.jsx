import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, CheckCircle2, FileDown, FolderOpen, Link2, PlayCircle, Plus, RefreshCw, Trash2, Upload, Users, X } from 'lucide-react'
import { api } from '../services/api'
import { useLanguage } from '../context/LanguageContext'
import { useToast } from '../context/ToastContext'

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
  const [editingSession, setEditingSession] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [attendeesModal, setAttendeesModal] = useState(null) // { session, list }
  const [loadingAttendees, setLoadingAttendees] = useState(false)
  const [resourcePanel, setResourcePanel] = useState(null) // { session, resources: [] }
  const [uploadingResource, setUploadingResource] = useState(false)
  const fileInputRef = useRef(null)
  const createFileRef = useRef(null)
  const [pendingCreateFile, setPendingCreateFile] = useState(null)
  const [linkPanel, setLinkPanel] = useState(null) // { session, generations: [] }
  const [linkingId, setLinkingId] = useState(null)
  const [availableGenerations, setAvailableGenerations] = useState([])
  const [selectedGenerationId, setSelectedGenerationId] = useState('')
  const toast = useToast()

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [sessionData, generationsData] = await Promise.all([
        api('/sessions'),
        api('/ai/generations'),
      ])
      setSessions(Array.isArray(sessionData) ? sessionData : [])
      setAvailableGenerations(Array.isArray(generationsData) ? generationsData : [])
    } catch (err) {
      setError(err.message)
      setSessions([])
      setAvailableGenerations([])
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
      const created = await api('/sessions', { method: 'POST', body: JSON.stringify(payload) })
      if (pendingCreateFile && created?.id) {
        setUploadingResource(true)
        try {
          const formData = new FormData()
          formData.append('file', pendingCreateFile)
          const token = localStorage.getItem('token')
          const res = await fetch(`/api/sessions/${created.id}/resources`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          })
          if (!res.ok) throw new Error(await res.text())
        } catch (uploadErr) {
          setError(uploadErr.message || 'Session created, but file upload failed')
        } finally {
          setUploadingResource(false)
        }
      }
      setForm((current) => ({ ...current, title: '', description: '', max_students: '' }))
      setPendingCreateFile(null)
      if (selectedGenerationId && created?.id) {
        try {
          await api(`/sessions/${created.id}/link-generation/${selectedGenerationId}`, { method: 'POST' })
          toast.success('Selected AI content linked to the new session.')
        } catch (linkErr) {
          setError(linkErr.message || 'Session created, but linking AI content failed')
        }
      }
      setSelectedGenerationId('')
      if (createFileRef.current) createFileRef.current.value = ''
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEdit(session) {
    setEditingSession(session)
    setEditForm({
      title: session.title,
      description: session.description || '',
      date: session.date,
      start_time: session.start_time,
      duration: session.duration,
      max_students: session.max_students || '',
    })
  }

  async function saveEdit(e) {
    e.preventDefault()
    try {
      const payload = {
        ...editForm,
        max_students: editForm.max_students ? Number(editForm.max_students) : null
      }
      await api(`/sessions/${editingSession.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      if (selectedGenerationId) {
        try {
          await api(`/sessions/${editingSession.id}/link-generation/${selectedGenerationId}`, { method: 'POST' })
          toast.success('AI content linked to the edited session.')
        } catch (linkErr) {
          setError(linkErr.message || 'Session updated, but linking AI content failed')
        }
      }
      setSelectedGenerationId('')
      setEditingSession(null)
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

  async function viewAttendees(session) {
    setLoadingAttendees(true)
    setAttendeesModal({ session, list: [] })
    try {
      const list = await api(`/sessions/${session.id}/attendees`)
      setAttendeesModal({ session, list: Array.isArray(list) ? list : [] })
    } catch {
      setAttendeesModal({ session, list: [] })
    } finally {
      setLoadingAttendees(false)
    }
  }

  async function openResourcePanel(session) {
    setResourcePanel({ session, resources: [], loading: true })
    try {
      const list = await api(`/sessions/${session.id}/resources`)
      setResourcePanel({ session, resources: Array.isArray(list) ? list : [], loading: false })
    } catch {
      setResourcePanel({ session, resources: [], loading: false })
    }
  }

  async function uploadResource(e) {
    const file = e.target.files?.[0]
    if (!file || !resourcePanel) return
    setUploadingResource(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const token = localStorage.getItem('token')
      const res = await fetch(`/api/sessions/${resourcePanel.session.id}/resources`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) throw new Error(await res.text())
      // Refresh resources list
      const list = await api(`/sessions/${resourcePanel.session.id}/resources`)
      setResourcePanel((prev) => ({ ...prev, resources: Array.isArray(list) ? list : [] }))
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploadingResource(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function deleteResource(resourceId) {
    try {
      await api(`/sessions/resources/${resourceId}`, { method: 'DELETE' })
      setResourcePanel((prev) => ({ ...prev, resources: prev.resources.filter((r) => r.id !== resourceId) }))
    } catch (err) {
      setError(err.message)
    }
  }

  function formatBytes(bytes) {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  async function openLinkPanel(session) {
    setLinkPanel({ session, generations: [], loading: true })
    try {
      const data = await api('/ai/generations')
      setLinkPanel({ session, generations: Array.isArray(data) ? data : [], loading: false })
    } catch {
      setLinkPanel({ session, generations: [], loading: false })
    }
  }

  async function linkGeneration(genId) {
    if (!linkPanel) return
    setLinkingId(genId)
    try {
      await api(`/sessions/${linkPanel.session.id}/link-generation/${genId}`, { method: 'POST' })
      toast.success('Content linked to session — students can access it after enrolling.')
    } catch (err) {
      setError(err.message || 'Could not link content')
    } finally {
      setLinkingId(null)
    }
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
        <label className="block space-y-2">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">Link AI content (optional)</span>
          <select className="input" value={selectedGenerationId} onChange={(e) => setSelectedGenerationId(e.target.value)}>
            <option value="">None</option>
            {availableGenerations.map((gen) => (
              <option key={gen.id} value={gen.id}>{gen.topic} · {gen.type}</option>
            ))}
          </select>
          <p className="text-xs text-slate-500">Pick an existing lesson, quiz, flashcard deck, or video to open to enrolled students.</p>
        </label>
        <label className="block space-y-2">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">Preparation file (optional)</span>
          <input
            ref={createFileRef}
            className="input file:me-3 file:rounded-md file:border-0 file:bg-purple-100 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-purple-700 dark:file:bg-purple-950/40 dark:file:text-purple-200"
            type="file"
            accept=".pdf,.pptx,.ppt,.doc,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.mp4,.zip"
            onChange={(e) => setPendingCreateFile(e.target.files?.[0] || null)}
          />
          {pendingCreateFile && (
            <p className="text-xs text-slate-500">Will attach: {pendingCreateFile.name}</p>
          )}
        </label>
        <button className="btn-primary w-full" disabled={uploadingResource}>
          <Plus size={18} />{uploadingResource ? 'Uploading preparation...' : t('sessions.create')}
        </button>
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
            <div className="rounded-2xl border border-slate-200 p-4 transition hover:shadow-md dark:border-slate-700" key={session.id}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-lg font-bold">{session.title}</p>
                  <p className="text-sm text-slate-500">{session.date} | {session.start_time} | {session.status}</p>
                  <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{session.description || t('sessions.noDescription')}</p>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  {session.max_students != null && Number(session.max_students) > 0 && (
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase dark:bg-slate-800">{session.max_students} {t('sessions.seats')}</span>
                  )}
                  <button
                    className="flex items-center gap-1.5 rounded-full bg-ocean/10 px-3 py-1 text-xs font-semibold text-ocean transition hover:bg-ocean/20 dark:bg-mint/10 dark:text-mint dark:hover:bg-mint/20"
                    type="button"
                    onClick={() => viewAttendees(session)}
                  >
                    <Users size={13} />
                    Enrolled students
                  </button>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button className="btn-soft" type="button" onClick={() => startEdit(session)}>Edit</button>
                <button className="btn-soft" type="button" onClick={() => startSession(session.id)}><PlayCircle size={18} />{t('sessions.start')}</button>
                <button className="btn-soft" type="button" onClick={() => endSession(session.id)}>{t('sessions.end')}</button>
                <button
                  className="btn-soft text-purple-600 hover:bg-purple-50 dark:text-purple-400 dark:hover:bg-purple-950/20"
                  type="button"
                  onClick={() => openResourcePanel(session)}
                >
                  <FolderOpen size={18} />Manage Resources
                </button>
                <button
                  className="btn-soft text-teal-700 hover:bg-teal-50 dark:text-mint dark:hover:bg-teal-950/20"
                  type="button"
                  onClick={() => openLinkPanel(session)}
                >
                  <Link2 size={18} />Link AI Content
                </button>
                <button className="btn-soft text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20" type="button" onClick={() => remove(session.id)}><Trash2 size={18} />{t('sessions.delete')}</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Edit modal */}
      {editingSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setEditingSession(null)}>
          <form className="modal-panel w-full max-w-md space-y-3 rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 dark:text-slate-100" onSubmit={saveEdit} onClick={(e) => e.stopPropagation()}>
            <h3 className="text-xl font-bold">Edit Session</h3>
            <input className="input dark:bg-slate-800 dark:border-slate-700" placeholder="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} required />
            <textarea className="input min-h-24 dark:bg-slate-800 dark:border-slate-700" placeholder="Description" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
            <input className="input dark:bg-slate-800 dark:border-slate-700" type="date" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} required />
            <input className="input dark:bg-slate-800 dark:border-slate-700" type="time" value={editForm.start_time} onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })} required />
            <div className="grid grid-cols-2 gap-3">
              <input className="input dark:bg-slate-800 dark:border-slate-700" type="number" min="5" max="480" placeholder="Duration (min)" value={editForm.duration} onChange={(e) => setEditForm({ ...editForm, duration: Number(e.target.value) })} />
              <input className="input dark:bg-slate-800 dark:border-slate-700" type="number" min="1" max="500" placeholder="Seats (Optional)" value={editForm.max_students} onChange={(e) => setEditForm({ ...editForm, max_students: e.target.value })} />
            </div>
            <label className="block space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">Link AI content (optional)</span>
              <select className="input dark:bg-slate-800 dark:border-slate-700" value={selectedGenerationId} onChange={(e) => setSelectedGenerationId(e.target.value)}>
                <option value="">None</option>
                {availableGenerations.map((gen) => (
                  <option key={gen.id} value={gen.id}>{gen.topic} · {gen.type}</option>
                ))}
              </select>
            </label>
            <div className="flex gap-2 pt-2">
              <button className="btn-primary flex-1" type="submit">Save Changes</button>
              <button className="btn-soft flex-1" type="button" onClick={() => setEditingSession(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Enrolled students modal */}
      {attendeesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="modal-panel w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold">Enrolled Students</h3>
              <button className="btn-soft p-1.5" type="button" onClick={() => setAttendeesModal(null)}><X size={18} /></button>
            </div>
            <p className="text-xs text-slate-500 -mt-2">{attendeesModal.session.title}</p>
            {loadingAttendees ? (
              <p className="text-sm text-slate-500">Loading students...</p>
            ) : attendeesModal.list.length === 0 ? (
              <p className="text-sm text-slate-500">No students enrolled yet.</p>
            ) : (
              <ul className="space-y-2 max-h-72 overflow-y-auto">
                {attendeesModal.list.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 rounded-xl border border-slate-200 px-4 py-2.5 dark:border-slate-700">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ocean/10 text-sm font-black text-ocean dark:bg-mint/10 dark:text-mint">
                      {s.name?.[0]?.toUpperCase() || '?'}
                    </div>
                    <div>
                      <p className="font-semibold text-sm">{s.name}</p>
                      <p className="text-xs text-slate-500">{s.email}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Resource Management Modal */}
      {resourcePanel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl dark:bg-slate-900 dark:text-slate-100 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
              <div>
                <h3 className="text-lg font-bold flex items-center gap-2"><FolderOpen size={20} className="text-purple-500" />Session Resources</h3>
                <p className="text-xs text-slate-500 mt-0.5">{resourcePanel.session.title}</p>
              </div>
              <button className="btn-soft p-1.5" type="button" onClick={() => setResourcePanel(null)}><X size={18} /></button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {/* Upload area */}
              <div
                className="border-2 border-dashed border-purple-300 dark:border-purple-700 rounded-xl p-6 text-center cursor-pointer hover:border-purple-500 hover:bg-purple-50 dark:hover:bg-purple-950/20 transition"
                onClick={() => fileInputRef.current?.click()}
              >
                <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.pptx,.ppt,.doc,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.mp4,.zip" onChange={uploadResource} />
                {uploadingResource ? (
                  <div className="flex flex-col items-center gap-2">
                    <div className="h-8 w-8 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
                    <p className="text-sm text-purple-600 font-semibold">Uploading...</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Upload size={28} className="text-purple-400" />
                    <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">Click to upload a resource</p>
                    <p className="text-xs text-slate-400">PDF, PPTX, DOC, DOCX, XLSX, Images, MP4, ZIP</p>
                  </div>
                )}
              </div>

              {/* Resources list */}
              {resourcePanel.loading ? (
                <p className="text-sm text-slate-500 text-center">Loading resources...</p>
              ) : resourcePanel.resources.length === 0 ? (
                <div className="text-center py-6">
                  <FolderOpen size={36} className="mx-auto mb-2 text-slate-300" />
                  <p className="text-sm text-slate-500">No resources uploaded yet. Upload presentations, slides, or any files you want students to access after the session.</p>
                </div>
              ) : (
                <ul className="space-y-2">
                  {resourcePanel.resources.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900/40">
                        <FileDown size={18} className="text-purple-600 dark:text-purple-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm truncate">{r.name}</p>
                        <p className="text-xs text-slate-500">{formatBytes(r.file_size)} · {new Date(r.uploaded_at).toLocaleDateString()}</p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <a
                          href={`http://localhost:8000${r.url}`}
                          target="_blank"
                          rel="noreferrer"
                          className="btn-soft p-1.5 text-ocean dark:text-mint"
                          title="Download"
                        >
                          <FileDown size={16} />
                        </a>
                        <button
                          type="button"
                          className="btn-soft p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                          onClick={() => deleteResource(r.id)}
                          title="Delete"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-slate-400 text-center">Students enrolled in this session can download these resources from their session history.</p>
            </div>
          </div>
        </div>
      )}

      {/* Link AI content modal */}
      {linkPanel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="modal-panel w-full max-w-lg rounded-2xl bg-white shadow-2xl dark:bg-slate-900 dark:text-slate-100 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
              <div>
                <h3 className="text-lg font-bold flex items-center gap-2"><Link2 size={20} className="text-teal-600" />Link AI Content</h3>
                <p className="text-xs text-slate-500 mt-0.5">{linkPanel.session.title}</p>
              </div>
              <button className="btn-soft p-1.5" type="button" onClick={() => setLinkPanel(null)}><X size={18} /></button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-3">
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Pick a lesson, flashcard deck, or video to share with students enrolled in this session.
              </p>
              {linkPanel.loading ? (
                <p className="text-sm text-slate-500">Loading your AI generations...</p>
              ) : linkPanel.generations.length === 0 ? (
                <p className="text-sm text-slate-500">No AI content generated yet. Create lessons, flashcards, or videos first.</p>
              ) : (
                <ul className="space-y-2">
                  {linkPanel.generations.map((gen) => (
                    <li key={gen.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-sm truncate">{gen.topic}</p>
                        <p className="text-xs text-slate-500 capitalize">{gen.type} · {new Date(gen.created_at).toLocaleDateString()}</p>
                      </div>
                      <button
                        type="button"
                        className="btn-soft shrink-0 text-teal-700 dark:text-mint"
                        disabled={linkingId === gen.id}
                        onClick={() => linkGeneration(gen.id)}
                      >
                        {linkingId === gen.id ? 'Linking...' : 'Link'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
