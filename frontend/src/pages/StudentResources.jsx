import { useEffect, useState } from 'react'
import {
  BookOpen, ChevronDown, ChevronRight, Download, FileDown, FileText,
  FolderOpen, GraduationCap, Layers, RefreshCw, Sparkles,
} from 'lucide-react'
import { api } from '../services/api'
import {
  downloadLessonAsDoc, downloadLessonAsPdf, downloadLessonAsPptxHtml,
  downloadQuizAsPdf, downloadQuizAsDoc, downloadFlashcardsAsDoc, downloadFlashcardsAsPdf,
  downloadText, flashcardsToHtml,
} from '../utils/download'

const BACKEND = 'http://localhost:8000'

function typeIcon(type) {
  if (type === 'lesson') return <GraduationCap size={16} />
  if (type === 'flashcard') return <Layers size={16} />
  if (type === 'quiz') return <FileText size={16} />
  return <Sparkles size={16} />
}

function typeColor(type) {
  if (type === 'lesson') return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
  if (type === 'flashcard') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
  if (type === 'quiz') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
  return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
}

function GenerationDownloads({ gen }) {
  const slug = (gen.topic || gen.type).replace(/\s+/g, '-').toLowerCase()
  const data = gen.data || {}

  if (gen.type === 'lesson' && data.topic) {
    return (
      <div className="flex flex-wrap gap-2 mt-2">
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadLessonAsDoc(data, `${slug}.doc`)}><Download size={13} />Word (.doc)</button>
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadLessonAsPptxHtml(data, `${slug}.pptx.html`)}><Download size={13} />PowerPoint Slides</button>
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadLessonAsPdf(data, slug)}><Download size={13} />PDF</button>
      </div>
    )
  }
  if (gen.type === 'flashcard' && data.cards) {
    return (
      <div className="flex flex-wrap gap-2 mt-2">
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadFlashcardsAsDoc(data, `${slug}.doc`)}><Download size={13} />Word (.doc)</button>
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadFlashcardsAsPdf(data, slug)}><Download size={13} />PDF</button>
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadText(flashcardsToHtml(data), `${slug}.html`, 'text/html')}><Download size={13} />Interactive HTML</button>
      </div>
    )
  }
  if (gen.type === 'quiz' && data.questions) {
    return (
      <div className="flex flex-wrap gap-2 mt-2">
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadQuizAsDoc(data, `${slug}.doc`)}><Download size={13} />Word (.doc)</button>
        <button type="button" className="btn-soft text-xs py-1 px-2.5" onClick={() => downloadQuizAsPdf(data, slug)}><Download size={13} />PDF</button>
      </div>
    )
  }
  return <p className="text-xs text-slate-400 mt-1">No downloadable format available for this item.</p>
}

function formatBytes(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function StudentResources() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({}) // sessionId -> bool
  const [sessionData, setSessionData] = useState({}) // sessionId -> { resources, generations, loadingResources, loadingGenerations }

  async function loadSessions() {
    setLoading(true)
    setError('')
    try {
      const data = await api('/sessions/student/my-sessions')
      setSessions(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadSessions() }, [])

  async function toggleSession(session) {
    const sid = session.id
    const isOpen = expanded[sid]
    setExpanded((prev) => ({ ...prev, [sid]: !isOpen }))

    if (!isOpen && !sessionData[sid]) {
      setSessionData((prev) => ({ ...prev, [sid]: { resources: [], generations: [], loadingResources: true, loadingGenerations: true } }))
      try {
        const [resources, generations] = await Promise.allSettled([
          api(`/sessions/${sid}/resources`),
          api(`/sessions/${sid}/generations`),
        ])
        setSessionData((prev) => ({
          ...prev,
          [sid]: {
            resources: resources.status === 'fulfilled' && Array.isArray(resources.value) ? resources.value : [],
            generations: generations.status === 'fulfilled' && Array.isArray(generations.value) ? generations.value : [],
            loadingResources: false,
            loadingGenerations: false,
          },
        }))
      } catch {
        setSessionData((prev) => ({ ...prev, [sid]: { resources: [], generations: [], loadingResources: false, loadingGenerations: false } }))
      }
    }
  }

  const statusBadgeColor = (status) => {
    if (status === 'ongoing') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
    if (status === 'ended') return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    if (status === 'preparing') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
    return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
  }

  return (
    <div className="page-shell space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black flex items-center gap-2">
            <FolderOpen className="text-ocean dark:text-mint" size={24} />
            My Session Resources
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Download resources and AI-generated content from sessions you are enrolled in.
          </p>
        </div>
        <button type="button" className="btn-soft" onClick={loadSessions}>
          <RefreshCw size={18} />Refresh
        </button>
      </div>

      {error && <p className="rounded-xl bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
      {loading && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="h-12 w-12 rounded-full border-4 border-ocean/30 border-t-ocean animate-spin dark:border-mint/30 dark:border-t-mint" />
          <p className="text-sm text-slate-500">Loading your sessions...</p>
        </div>
      )}

      {!loading && sessions.length === 0 && (
        <div className="panel flex flex-col items-center justify-center py-20 gap-4 text-center">
          <FolderOpen size={48} className="text-slate-300" />
          <p className="text-lg font-bold text-slate-600 dark:text-slate-300">No Sessions Yet</p>
          <p className="text-sm text-slate-500 max-w-sm">You haven't enrolled in any sessions. Browse available sessions to get started.</p>
        </div>
      )}

      {!loading && sessions.length > 0 && (
        <div className="space-y-3">
          {sessions.map((session) => {
            const isOpen = !!expanded[session.id]
            const sd = sessionData[session.id]
            return (
              <div
                key={session.id}
                className="panel overflow-hidden"
              >
                {/* Session header – click to expand */}
                <button
                  type="button"
                  className="w-full flex items-center gap-3 text-left"
                  onClick={() => toggleSession(session)}
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-ocean/10 dark:bg-mint/10">
                    <BookOpen size={20} className="text-ocean dark:text-mint" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-bold truncate">{session.title}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {session.instructor_name && <span>{session.instructor_name} · </span>}
                      {session.date} at {session.start_time?.slice(0, 5)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold capitalize ${statusBadgeColor(session.status)}`}>
                      {session.status}
                    </span>
                    {session.attended && (
                      <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                        ✓ Attended
                      </span>
                    )}
                    {isOpen ? <ChevronDown size={18} className="text-slate-400" /> : <ChevronRight size={18} className="text-slate-400" />}
                  </div>
                </button>

                {/* Expanded content */}
                {isOpen && (
                  <div className="mt-4 border-t border-slate-200 dark:border-slate-700 pt-4 space-y-5">
                    {/* Uploaded Resources */}
                    <div>
                      <h3 className="text-sm font-bold flex items-center gap-2 mb-3 text-slate-700 dark:text-slate-200">
                        <FolderOpen size={16} className="text-purple-500" />
                        Uploaded Resources from Instructor
                      </h3>
                      {sd?.loadingResources ? (
                        <p className="text-xs text-slate-400">Loading resources...</p>
                      ) : !sd?.resources?.length ? (
                        <p className="text-xs text-slate-400 italic">No files uploaded by the instructor for this session yet.</p>
                      ) : (
                        <ul className="space-y-2">
                          {sd.resources.map((r) => (
                            <li key={r.id} className="flex items-center gap-3 rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-3 bg-slate-50 dark:bg-slate-800/50">
                              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900/30">
                                <FileDown size={16} className="text-purple-600 dark:text-purple-400" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-semibold truncate">{r.name}</p>
                                <p className="text-xs text-slate-500">{formatBytes(r.file_size)} · {new Date(r.uploaded_at).toLocaleDateString()}</p>
                              </div>
                              <a
                                href={`${BACKEND}${r.url}`}
                                target="_blank"
                                rel="noreferrer"
                                download={r.name}
                                className="btn-soft text-xs py-1.5 px-3 text-ocean dark:text-mint"
                              >
                                <Download size={14} />Download
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {/* AI Generated Content */}
                    <div>
                      <h3 className="text-sm font-bold flex items-center gap-2 mb-3 text-slate-700 dark:text-slate-200">
                        <Sparkles size={16} className="text-amber-500" />
                        AI-Generated Content Used in This Session
                      </h3>
                      {sd?.loadingGenerations ? (
                        <p className="text-xs text-slate-400">Loading AI resources...</p>
                      ) : !sd?.generations?.length ? (
                        <p className="text-xs text-slate-400 italic">No AI-generated content has been linked to this session by the instructor yet.</p>
                      ) : (
                        <div className="space-y-3">
                          {sd.generations.map((gen) => (
                            <div key={gen.id} className="rounded-xl border border-slate-200 dark:border-slate-700 p-4 bg-slate-50 dark:bg-slate-800/50">
                              <div className="flex items-center gap-2">
                                <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ${typeColor(gen.type)}`}>
                                  {typeIcon(gen.type)}{gen.type}
                                </span>
                                <p className="text-sm font-semibold flex-1 truncate">{gen.topic}</p>
                                <p className="text-xs text-slate-400 shrink-0">{new Date(gen.created_at).toLocaleDateString()}</p>
                              </div>
                              <GenerationDownloads gen={gen} />
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
