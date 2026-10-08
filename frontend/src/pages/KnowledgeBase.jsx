import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle, BookOpen, Brain, CheckCircle2, ChevronDown, ChevronRight,
  Database, FileText, Filter, Layers, Loader2, MessageSquare, Plus,
  RefreshCw, Search, SlidersHorizontal, Sparkles, Trash2, Upload, X, Zap
} from 'lucide-react'
import { api } from '../services/api'

// ─── Helpers ──────────────────────────────────────────────────────────────────
const SUBJECTS = ['Mathematics', 'Physics', 'Chemistry', 'Biology', 'History',
  'Geography', 'English', 'Arabic', 'Computer Science', 'Economics', 'Other']
const GRADES   = ['1','2','3','4','5','6','7','8','9','10','11','12','University']

function Pill({ label, color = 'slate' }) {
  const map = {
    slate:  'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    teal:   'bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300',
    violet: 'bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300',
    amber:  'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300',
    green:  'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300',
    red:    'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[color]}`}>
      {label}
    </span>
  )
}

function StatCard({ icon: Icon, label, value, color = 'teal', sub }) {
  const colors = {
    teal:   'from-teal-500 to-cyan-500',
    violet: 'from-violet-500 to-purple-500',
    amber:  'from-amber-500 to-orange-500',
    green:  'from-emerald-500 to-teal-500',
  }
  return (
    <div className="panel flex items-center gap-4 overflow-hidden">
      <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${colors[color]} text-white shadow-sm`}>
        <Icon size={22} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-black tabular-nums">{value ?? '—'}</p>
        <p className="text-sm font-semibold text-slate-600 dark:text-slate-400">{label}</p>
        {sub && <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">{sub}</p>}
      </div>
    </div>
  )
}

// ─── Upload Modal ─────────────────────────────────────────────────────────────
function UploadModal({ onClose, onSuccess }) {
  const [file, setFile]           = useState(null)
  const [subject, setSubject]     = useState('')
  const [grade, setGrade]         = useState('')
  const [topic, setTopic]         = useState('')
  const [isAsync, setIsAsync]     = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [progress, setProgress]   = useState('')
  const dropRef                   = useRef(null)
  const fileRef                   = useRef(null)

  function handleDrop(e) {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) setFile(f)
  }

  async function submit() {
    if (!file || !subject || !grade || !topic.trim()) {
      setError('Please fill in all fields and select a PDF file.')
      return
    }
    setError('')
    setLoading(true)
    setProgress('Uploading…')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('subject', subject)
      form.append('grade_level', grade)
      form.append('topic', topic.trim())
      form.append('is_async', isAsync ? 'true' : 'false')

      const tok = localStorage.getItem('edusense_token')
      const res = await fetch('/api/rag/ingest', {
        method: 'POST',
        headers: { Authorization: `Bearer ${tok}` },
        body: form,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Upload failed')
      setProgress(data.status === 'queued'
        ? `Queued for background processing (${data.source_id})`
        : `Done — ${data.chunks_added ?? '?'} chunks indexed`)
      setTimeout(() => { onSuccess(); onClose() }, 1600)
    } catch (e) {
      setError(e.message)
      setLoading(false)
      setProgress('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
           style={{ animation: 'modalRise .3s ease-out' }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white">
              <Upload size={18} />
            </div>
            <h2 className="text-lg font-black">Upload to Knowledge Base</h2>
          </div>
          <button id="kb-upload-close" type="button" className="btn-soft p-1.5" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="space-y-4 p-6">
          {/* Drop zone */}
          <div
            ref={dropRef}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-8 transition-colors
              ${file ? 'border-teal-400 bg-teal-50 dark:bg-teal-950/20' : 'border-slate-300 hover:border-teal-400 hover:bg-slate-50 dark:border-slate-600 dark:hover:border-teal-500 dark:hover:bg-slate-800/50'}`}
          >
            <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={(e) => setFile(e.target.files?.[0])} />
            {file ? (
              <>
                <CheckCircle2 size={32} className="text-teal-500" />
                <p className="text-center text-sm font-semibold text-teal-700 dark:text-teal-300">{file.name}</p>
                <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB — click to change</p>
              </>
            ) : (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 dark:bg-slate-800">
                  <FileText size={24} className="text-slate-400" />
                </div>
                <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">Drop a PDF here, or click to browse</p>
                <Pill label="PDF only" />
              </>
            )}
          </div>

          {/* Fields */}
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">
              <span>Subject *</span>
              <select id="kb-subject" className="input" value={subject} onChange={(e) => setSubject(e.target.value)}>
                <option value="">Select…</option>
                {SUBJECTS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="space-y-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">
              <span>Grade Level *</span>
              <select id="kb-grade" className="input" value={grade} onChange={(e) => setGrade(e.target.value)}>
                <option value="">Select…</option>
                {GRADES.map(g => <option key={g} value={g}>Grade {g}</option>)}
              </select>
            </label>
          </div>
          <label className="block space-y-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">
            <span>Topic / Chapter *</span>
            <input id="kb-topic" className="input" placeholder="e.g. Photosynthesis, Chapter 4" value={topic} onChange={(e) => setTopic(e.target.value)} />
          </label>
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 px-4 py-3 dark:border-slate-700">
            <input type="checkbox" className="h-4 w-4 rounded" checked={isAsync} onChange={(e) => setIsAsync(e.target.checked)} />
            <div>
              <p className="text-sm font-semibold">Process in background</p>
              <p className="text-xs text-slate-500">For large files (auto-selected for files &gt;1 MB)</p>
            </div>
          </label>

          {error   && <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
          {progress && <p className="rounded-xl bg-teal-50 px-4 py-3 text-sm font-semibold text-teal-700 dark:bg-teal-950/30 dark:text-teal-300">{progress}</p>}

          <button id="kb-upload-submit" type="button" disabled={loading}
            className="btn-primary w-full justify-center gap-2 py-3"
            onClick={submit}>
            {loading ? <><Loader2 size={18} className="animate-spin" />Processing…</> : <><Zap size={18} />Upload & Index</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Source Card ─────────────────────────────────────────────────────────────
function SourceCard({ src, onDelete, onPreview }) {
  const [expanded, setExpanded] = useState(false)
  const subjectColor = { Biology:'teal', Physics:'violet', Mathematics:'amber', Chemistry:'green' }[src.subject] || 'slate'

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow hover:shadow-md dark:border-slate-700 dark:bg-slate-900/70">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 text-white">
          <FileText size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-bold text-sm">{src.source_file}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {src.subject     && <Pill label={src.subject}            color={subjectColor} />}
            {src.grade_level && <Pill label={`Grade ${src.grade_level}`} color="slate" />}
            {src.topic       && <Pill label={src.topic}              color="slate" />}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {src.chunk_count ?? 0} chunks
          </span>
          <button type="button"
            className="btn-soft p-1.5 text-teal-600 hover:bg-teal-50 dark:hover:bg-teal-950/30"
            title="Preview chunks"
            onClick={() => onPreview(src)}>
            <Search size={15} />
          </button>
          <button type="button"
            className="btn-soft p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
            title="Delete from knowledge base"
            onClick={() => onDelete(src.source_file)}>
            <Trash2 size={15} />
          </button>
          <button type="button"
            className="btn-soft p-1.5"
            onClick={() => setExpanded(v => !v)}>
            {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400 space-y-1">
          {src.ingested_at && (
            <p>Indexed: <span className="font-medium text-slate-700 dark:text-slate-300">{new Date(src.ingested_at).toLocaleString()}</span></p>
          )}
          <p>Chunks: <span className="font-medium text-slate-700 dark:text-slate-300">{src.chunk_count ?? '—'}</span></p>
        </div>
      )}
    </div>
  )
}

// ─── Preview Panel ────────────────────────────────────────────────────────────
function PreviewPanel({ src, onClose }) {
  const [query, setQuery]     = useState(src?.topic || '')
  const [chunks, setChunks]   = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  async function search() {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ topic: query.trim(), top_k: 8 })
      if (src?.subject)     params.set('subject',     src.subject)
      if (src?.grade_level) params.set('grade_level', src.grade_level)
      const data = await api(`/rag/suggest?${params}`)
      setChunks(data.chunks || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (query) search() }, [src])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 backdrop-blur-sm sm:items-center">
      <div className="flex w-full max-w-2xl flex-col rounded-3xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
           style={{ maxHeight: '85vh', animation: 'modalRise .3s ease-out' }}>
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 text-white">
              <Search size={18} />
            </div>
            <div>
              <h2 className="font-black">Chunk Preview</h2>
              <p className="text-xs text-slate-500 truncate max-w-xs">{src?.source_file}</p>
            </div>
          </div>
          <button type="button" className="btn-soft p-1.5" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="flex gap-2 border-b border-slate-100 px-6 py-3 dark:border-slate-800">
          <input id="preview-query" className="input flex-1" placeholder="Search topic in this source…"
            value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()} />
          <button id="preview-search" type="button" className="btn-primary px-4" onClick={search} disabled={loading}>
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-3 p-6">
          {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
          {!loading && chunks.length === 0 && !error && (
            <div className="flex flex-col items-center gap-3 py-10 text-center text-slate-400">
              <Layers size={36} />
              <p className="text-sm">No chunks found. Try a different search.</p>
            </div>
          )}
          {chunks.map((c, i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/60">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <FileText size={13} />
                  <span>{c.source_file} · p.{c.page}</span>
                </div>
                <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-bold text-teal-700 dark:bg-teal-900/40 dark:text-teal-300">
                  score {c.score?.toFixed(3)}
                </span>
              </div>
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed line-clamp-4">{c.text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Q&A / AI Chat Panel ──────────────────────────────────────────────────────
function QAPanel() {
  const [messages, setMessages] = useState([
    {
      sender: 'ai',
      text: 'Hello! I am your EduSense AI Assistant. Ask me anything about your uploaded course materials or general academic topics.',
      sources: [],
      chunks_used: 0,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ])
  const [input, setInput]       = useState('')
  const [subject, setSubject]   = useState('')
  const [grade, setGrade]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const chatEndRef              = useRef(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function sendMessage(textToSend) {
    const q = (textToSend || input).trim()
    if (!q || loading) return

    const userMsg = {
      sender: 'user',
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setError('')
    setLoading(true)

    try {
      const data = await api('/rag/ask', {
        method: 'POST',
        body: { question: q, subject: subject || null, grade_level: grade || null, top_k: 5 }
      })

      const aiMsg = {
        sender: 'ai',
        text: data.answer,
        sources: data.sources || [],
        chunks_used: data.chunks_used || 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (e) {
      setError(e.message || 'Failed to get answer from AI')
    } finally {
      setLoading(false)
    }
  }

  const SUGGESTIONS = [
    'Explain the Calvin cycle in simple terms',
    'What are Newton’s laws of motion?',
    'Summarize key topics from uploaded biology PDFs',
    'Create 3 review questions on cell division'
  ]

  return (
    <div className="panel flex flex-col space-y-4 min-h-[500px]">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-600 text-white shadow-sm">
            <Sparkles size={20} />
          </div>
          <div>
            <h2 className="text-base font-black">EduSense AI Assistant</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">Direct grounded Q&A with your Knowledge Base & Gemini AI</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select id="qa-subject" className="input text-xs w-36 py-1.5" value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">All Subjects</option>
            {SUBJECTS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select id="qa-grade" className="input text-xs w-32 py-1.5" value={grade} onChange={(e) => setGrade(e.target.value)}>
            <option value="">All Grades</option>
            {GRADES.map(g => <option key={g} value={g}>Grade {g}</option>)}
          </select>
          <button type="button" className="btn-soft text-xs py-1.5 px-3" onClick={() => setMessages([messages[0]])}>
            Clear Chat
          </button>
        </div>
      </div>

      {/* Messages Feed */}
      <div className="flex-1 space-y-4 overflow-y-auto max-h-[420px] p-2">
        {messages.map((m, idx) => (
          <div key={idx} className={`flex gap-3 ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.sender === 'ai' && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white text-xs font-bold shadow-sm">
                AI
              </div>
            )}
            <div className={`max-w-[82%] rounded-2xl p-4 text-sm leading-relaxed transition-all ${
              m.sender === 'user'
                ? 'bg-gradient-to-r from-ocean to-teal-600 text-white shadow-sm rounded-br-none'
                : 'border border-slate-200 bg-slate-50/80 text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 rounded-bl-none shadow-sm'
            }`}>
              <p className="whitespace-pre-wrap">{m.text}</p>
              
              {/* Citations / Sources */}
              {m.sources && m.sources.length > 0 && (
                <div className="mt-3 border-t border-slate-200/80 pt-2 dark:border-slate-800 space-y-1">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Grounded in {m.chunks_used} document chunk{m.chunks_used > 1 ? 's' : ''}:
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {m.sources.map((s, i) => (
                      <span key={i} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-slate-700 shadow-xs dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <FileText size={11} className="text-teal-500" />
                        {s.source_file} {s.page ? `(p.${s.page})` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-1 text-right text-[10px] opacity-60">
                {m.timestamp}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-3 items-center text-slate-500 text-xs p-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-teal-500 text-white">
              <Loader2 size={16} className="animate-spin" />
            </div>
            <p className="font-medium animate-pulse">Consulting Knowledge Base & AI models…</p>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Suggested Prompts */}
      {messages.length <= 2 && (
        <div className="flex flex-wrap gap-2 pt-2">
          {SUGGESTIONS.map((sug, i) => (
            <button key={i} type="button" className="btn-soft text-xs py-1 px-3 text-slate-600 hover:text-teal-600 dark:text-slate-300 dark:hover:text-teal-400" onClick={() => sendMessage(sug)}>
              <Zap size={12} className="mr-1 inline text-amber-500" />{sug}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-xl bg-red-50 p-3 text-xs text-red-600 dark:bg-red-950/30 dark:text-red-300">
          <AlertCircle size={14} />{error}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={(e) => { e.preventDefault(); sendMessage(); }} className="flex items-center gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        <input
          id="qa-question"
          className="input flex-1 py-2.5"
          placeholder="Ask a question about your uploaded PDFs or any general topic…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button id="qa-ask" type="submit" className="btn-primary py-2.5 px-5 gap-2 shrink-0" disabled={loading || !input.trim()}>
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Brain size={16} />}
          <span>Send</span>
        </button>
      </form>
    </div>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────
export default function KnowledgeBaseDashboard() {
  const [sources, setSources]         = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [showUpload, setShowUpload]   = useState(false)
  const [previewSrc, setPreviewSrc]   = useState(null)
  const [searchQ, setSearchQ]         = useState('')
  const [filterSubject, setFilter]    = useState('')
  const [deleting, setDeleting]       = useState(null)
  const [activeTab, setActiveTab]     = useState('library') // 'library' | 'qa'

  async function loadSources() {
    setLoading(true)
    setError('')
    try {
      const data = await api('/rag/sources')
      setSources(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message)
      setSources([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadSources() }, [])

  async function deleteSource(sourceId) {
    if (!window.confirm(`Delete "${sourceId}" and all its chunks from the knowledge base?`)) return
    setDeleting(sourceId)
    try {
      await api(`/rag/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' })
      setSources(prev => prev.filter(s => s.source_file !== sourceId))
    } catch (e) {
      setError(e.message)
    } finally {
      setDeleting(null)
    }
  }

  const filtered = sources.filter(s => {
    const q = searchQ.toLowerCase()
    const matchSearch = !q || s.source_file?.toLowerCase().includes(q)
      || s.subject?.toLowerCase().includes(q)
      || s.topic?.toLowerCase().includes(q)
    const matchFilter = !filterSubject || s.subject === filterSubject
    return matchSearch && matchFilter
  })

  const totalChunks  = sources.reduce((a, s) => a + (s.chunk_count || 0), 0)
  const uniqueSubs   = [...new Set(sources.map(s => s.subject).filter(Boolean))].length
  const uniqueGrades = [...new Set(sources.map(s => s.grade_level).filter(Boolean))].length

  return (
    <div className="page-shell space-y-6">
      {/* ── Page Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white">
              <Database size={18} />
            </div>
            <h1 className="text-2xl font-black">Knowledge Base</h1>
          </div>
          <p className="max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            Manage your indexed course materials. Upload PDFs to power RAG-grounded lessons, quizzes, and student Q&A.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button id="kb-chat-btn" type="button" className="btn-soft gap-2 border border-teal-500/30 text-teal-700 dark:text-teal-300 hover:bg-teal-50 dark:hover:bg-teal-950/30" onClick={() => setActiveTab('qa')}>
            <Sparkles size={16} className="text-teal-500" />Chat with AI
          </button>
          <button id="kb-refresh" type="button" className="btn-soft gap-2" onClick={loadSources} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />Refresh
          </button>
          <button id="kb-upload-btn" type="button" className="btn-primary gap-2" onClick={() => setShowUpload(true)}>
            <Plus size={16} />Upload PDF
          </button>
        </div>
      </div>

      {/* ── Stats Row ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={FileText}  label="Documents"    value={sources.length} color="teal"   sub="indexed PDFs" />
        <StatCard icon={Layers}    label="Total Chunks" value={totalChunks}    color="violet" sub="vector embeddings" />
        <StatCard icon={BookOpen}  label="Subjects"     value={uniqueSubs}     color="amber"  sub="covered" />
        <StatCard icon={Zap}       label="Grade Levels" value={uniqueGrades}   color="green"  sub="available" />
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-1 rounded-2xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-900/50 w-fit">
        {[['library', Database, 'Library'], ['qa', Sparkles, 'AI Chat Assistant']].map(([id, Icon, label]) => (
          <button key={id} type="button" id={`kb-tab-${id}`}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all
              ${activeTab === id
                ? 'bg-white shadow text-slate-900 dark:bg-slate-800 dark:text-slate-100'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
            onClick={() => setActiveTab(id)}>
            <Icon size={15} />{label}
          </button>
        ))}
      </div>

      {/* ── Library Tab ── */}
      {activeTab === 'library' && (
        <div className="space-y-4">
          {/* Filter bar */}
          <div className="panel flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-48">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input id="kb-search" className="input pl-9" placeholder="Search by filename, subject, topic…"
                value={searchQ} onChange={(e) => setSearchQ(e.target.value)} />
            </div>
            <div className="flex items-center gap-2">
              <Filter size={15} className="text-slate-400" />
              <select id="kb-filter-subject" className="input w-40" value={filterSubject} onChange={(e) => setFilter(e.target.value)}>
                <option value="">All subjects</option>
                {SUBJECTS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            {(searchQ || filterSubject) && (
              <button type="button" className="btn-soft gap-1.5 text-sm"
                onClick={() => { setSearchQ(''); setFilter('') }}>
                <X size={14} />Clear
              </button>
            )}
            <p className="ms-auto text-xs text-slate-400">{filtered.length} of {sources.length}</p>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900/40 dark:bg-red-950/20">
              <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-500" />
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          )}

          {/* Loading skeleton */}
          {loading && (
            <div className="space-y-3">
              {[0, 1, 2].map(i => (
                <div key={i} className="h-16 rounded-2xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800"
                     style={{ animation: 'shimmer 1.5s infinite linear', backgroundImage: 'linear-gradient(90deg,transparent 0%,rgba(255,255,255,.18) 50%,transparent 100%)', backgroundSize: '200% 100%' }} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!loading && filtered.length === 0 && !error && (
            <div className="panel flex flex-col items-center gap-4 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-100 to-cyan-100 dark:from-teal-900/30 dark:to-cyan-900/30">
                <Database size={28} className="text-teal-500" />
              </div>
              <div>
                <p className="font-bold text-slate-700 dark:text-slate-300">
                  {sources.length === 0 ? 'No documents indexed yet' : 'No documents match your filter'}
                </p>
                <p className="mt-1 text-sm text-slate-400">
                  {sources.length === 0
                    ? 'Upload a PDF to start building your AI knowledge base.'
                    : 'Try clearing your search or subject filter.'}
                </p>
              </div>
              {sources.length === 0 && (
                <button type="button" className="btn-primary gap-2" onClick={() => setShowUpload(true)}>
                  <Upload size={16} />Upload your first PDF
                </button>
              )}
            </div>
          )}

          {/* Source list */}
          {!loading && filtered.length > 0 && (
            <div className="space-y-2">
              {filtered.map(src => (
                deleting === src.source_file ? (
                  <div key={src.source_file} className="flex h-16 items-center justify-center rounded-2xl border border-red-200 bg-red-50 text-sm text-red-600 dark:border-red-900/40 dark:bg-red-950/20">
                    <Loader2 size={16} className="animate-spin mr-2" />Deleting {src.source_file}…
                  </div>
                ) : (
                  <SourceCard key={src.source_file} src={src}
                    onDelete={deleteSource}
                    onPreview={(s) => setPreviewSrc(s)} />
                )
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Q&A Tab ── */}
      {activeTab === 'qa' && <QAPanel />}

      {/* ── Modals ── */}
      {showUpload && (
        <UploadModal onClose={() => setShowUpload(false)} onSuccess={loadSources} />
      )}
      {previewSrc && (
        <PreviewPanel src={previewSrc} onClose={() => setPreviewSrc(null)} />
      )}
    </div>
  )
}
