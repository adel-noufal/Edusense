import { useEffect, useMemo, useRef, useState } from 'react'
import { FileDown, FolderOpen, RefreshCw, Trash2, Upload } from 'lucide-react'
import { api, staticUrl } from '../services/api'

export default function InstructorSources() {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState('')
  const [resources, setResources] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploadingResource, setUploadingResource] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  async function loadSessions() {
    setLoading(true)
    setError('')
    try {
      const data = await api('/sessions')
      const sessionList = Array.isArray(data) ? data : []
      setSessions(sessionList)
      setActiveSessionId((current) => current || sessionList[0]?.id?.toString() || '')
    } catch (err) {
      setError(err.message || 'Could not load your sessions')
      setSessions([])
      setActiveSessionId('')
    } finally {
      setLoading(false)
    }
  }

  async function loadResources(sessionId) {
    if (!sessionId) {
      setResources([])
      return
    }
    try {
      const data = await api(`/sessions/${sessionId}/resources`)
      setResources(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.message || 'Could not load resources for this session')
      setResources([])
    }
  }

  useEffect(() => {
    loadSessions()
  }, [])

  useEffect(() => {
    if (!activeSessionId) {
      setResources([])
      return
    }
    loadResources(activeSessionId)
  }, [activeSessionId])

  async function uploadResource(e) {
    const file = e.target.files?.[0]
    if (!file || !activeSessionId) return
    setUploadingResource(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const token = localStorage.getItem('token')
      const res = await fetch(`/api/sessions/${activeSessionId}/resources`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) throw new Error(await res.text())
      await loadResources(activeSessionId)
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
      setResources((current) => current.filter((item) => item.id !== resourceId))
    } catch (err) {
      setError(err.message || 'Could not delete resource')
    }
  }

  function formatBytes(bytes) {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const selectedSession = useMemo(() => sessions.find((session) => String(session.id) === String(activeSessionId)), [activeSessionId, sessions])

  return (
    <div className="page-shell space-y-6">
      <div className="panel space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black">Instructor Sources</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              Upload slides, PDFs, notes, and other materials here so they can be used in your AI lessons, quizzes, and flashcards for the selected session.
            </p>
          </div>
          <button type="button" className="btn-soft" onClick={() => loadSessions()}>
            <RefreshCw size={18} />Refresh
          </button>
        </div>

        {error && <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200">{error}</p>}

        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <div className="space-y-3">
            <label className="space-y-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
              <span>Select a session</span>
              <select className="input" value={activeSessionId} onChange={(e) => setActiveSessionId(e.target.value)}>
                {loading && <option value="">Loading sessions...</option>}
                {!loading && sessions.length === 0 && <option value="">No sessions yet</option>}
                {sessions.map((session) => (
                  <option key={session.id} value={session.id}>{session.title}</option>
                ))}
              </select>
            </label>

            {selectedSession && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
                <p className="font-semibold text-slate-900 dark:text-slate-100">{selectedSession.title}</p>
                <p className="mt-1">{selectedSession.date} · {selectedSession.start_time}</p>
                <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">{selectedSession.status}</p>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-dashed border-slate-300 bg-white/70 p-5 dark:border-slate-700 dark:bg-slate-900/50">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold flex items-center gap-2"><FolderOpen size={18} />Uploaded Sources</h2>
                <p className="mt-1 text-sm text-slate-500">Drop files here for the selected session and use them in AI generation later.</p>
              </div>
              <button type="button" className="btn-soft" onClick={() => fileInputRef.current?.click()}>
                <Upload size={18} />Upload source
              </button>
            </div>
            <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.pptx,.ppt,.doc,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.mp4,.zip" onChange={uploadResource} />

            {uploadingResource && <p className="mt-4 text-sm text-teal-700 dark:text-teal-300">Uploading...</p>}

            <div className="mt-5 space-y-2">
              {resources.length === 0 && !uploadingResource ? (
                <p className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800/60">
                  No files uploaded for this session yet.
                </p>
              ) : (
                resources.map((resource) => (
                  <div key={resource.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 px-4 py-3 dark:border-slate-700">
                    <FileDown size={18} className="shrink-0 text-purple-500" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-sm">{resource.name}</p>
                      <p className="text-xs text-slate-500">{formatBytes(resource.file_size)} · {new Date(resource.uploaded_at).toLocaleDateString()}</p>
                    </div>
                    <a href={staticUrl(resource.url)} target="_blank" rel="noreferrer" className="btn-soft p-1.5" title="Open">
                      <FileDown size={16} />
                    </a>
                    <button type="button" className="btn-soft p-1.5 text-red-500" onClick={() => deleteResource(resource.id)} title="Delete">
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
