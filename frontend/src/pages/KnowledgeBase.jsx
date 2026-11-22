import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle, BookOpen, Brain, CheckCircle2, ChevronDown, ChevronRight,
  Database, Download, ExternalLink, Eye, FileText, Filter, Layers, Loader2, MessageSquare, PanelLeftClose, PanelLeftOpen, Pencil, Plus,
  Paperclip, RefreshCw, Search, SlidersHorizontal, Sparkles, Trash2, Upload, X, Zap, Maximize2, Minimize2
} from 'lucide-react'
import { api } from '../services/api'
import { normalizeSources } from '../utils/sources'
import SearchInput from '../components/SearchInput'

// ─── Helpers ──────────────────────────────────────────────────────────────────
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
  const [progressPct, setProgressPct] = useState(0)
  const dropRef                   = useRef(null)
  const fileRef                   = useRef(null)

  function handleFileSelection(f) {
    if (!f) return
    setFile(f)
    if (f.size > 1024 * 1024) {
      setIsAsync(true)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    handleFileSelection(f)
  }

  async function submit() {
    if (!file || !topic.trim()) {
      setError('Please select a file and enter a topic.')
      return
    }
    setError('')
    setLoading(true)
    setProgress('Uploading document to server...')
    setProgressPct(10)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('subject', subject)
      form.append('grade_level', grade)
      form.append('topic', topic.trim())
      form.append('is_async', isAsync ? 'true' : 'false')

      const data = await api('/rag/ingest', {
        method: 'POST',
        body: form,
      })

      if (data.status === 'queued' && data.job_id) {
        const mb = (file.size / 1024 / 1024).toFixed(1)
        setProgress(`Ingesting in background (${mb} MB)...`)
        setProgressPct(15)
        try {
          localStorage.setItem('edusense_kb_ingest_job', JSON.stringify({
            jobId: data.job_id,
            filename: file.name,
          }))
        } catch (_) {}

        const pollInterval = setInterval(async () => {
          try {
            const statusRes = await api(`/rag/ingest/status/${data.job_id}`)
            if (statusRes.progress) setProgressPct(statusRes.progress)
            if (statusRes.message) setProgress(statusRes.message)

            if (statusRes.status === 'completed') {
              clearInterval(pollInterval)
              try { localStorage.removeItem('edusense_kb_ingest_job') } catch (_) {}
              setProgressPct(100)
              setProgress(`✓ Complete: ${statusRes.chunks_indexed || statusRes.result?.chunk_count || 0} chunks indexed!`)
              setTimeout(() => {
                onSuccess()
                onClose()
              }, 1400)
            } else if (statusRes.status === 'failed') {
              clearInterval(pollInterval)
              try { localStorage.removeItem('edusense_kb_ingest_job') } catch (_) {}
              setError(statusRes.error || 'Ingestion failed on server')
              setLoading(false)
            }
          } catch (err) {
            clearInterval(pollInterval)
            try { localStorage.removeItem('edusense_kb_ingest_job') } catch (_) {}
            setError(err.status === 404
              ? `Ingestion status for "${file.name}" is no longer available (the server may have restarted). Refresh the Knowledge Base to check whether it finished.`
              : err.message || 'Error tracking background status')
            setLoading(false)
          }
        }, 1200)
      } else {
        setProgressPct(100)
        setProgress(`✓ Indexed ${data.chunk_count || data.chunks_added || 0} chunks successfully`)
        setTimeout(() => {
          onSuccess()
          onClose()
        }, 1200)
      }
    } catch (e) {
      setError(e.message || 'Upload failed')
      setLoading(false)
      setProgress('')
      setProgressPct(0)
    }
  }

  function roundMb(bytes) {
    return (bytes / 1024 / 1024).toFixed(1)
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
            <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={(e) => handleFileSelection(e.target.files?.[0])} />
            {file ? (
              <>
                <CheckCircle2 size={32} className="text-teal-500" />
                <p className="text-center text-sm font-semibold text-teal-700 dark:text-teal-300">{file.name}</p>
                <p className="text-xs text-slate-500">{roundMb(file.size)} MB — click to change</p>
              </>
            ) : (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 dark:bg-slate-800">
                  <FileText size={24} className="text-slate-400" />
                </div>
                <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">Drop a PDF here, or click to browse</p>
                <Pill label="PDFs up to 100MB+" />
              </>
            )}
          </div>

          {/* Fields */}
          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">
              <span>Topic / Chapter *</span>
              <input id="kb-topic" className="input" placeholder="e.g. Photosynthesis, Chapter 4" value={topic} onChange={(e) => setTopic(e.target.value)} />
            </label>
          </div>
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 px-4 py-3 dark:border-slate-700">
            <input type="checkbox" className="h-4 w-4 rounded" checked={isAsync} onChange={(e) => setIsAsync(e.target.checked)} />
            <div>
              <p className="text-sm font-semibold">Process in background</p>
              <p className="text-xs text-slate-500">Non-blocking background queue (auto-enabled for &gt;1 MB)</p>
            </div>
          </label>

          {error   && <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}

          {loading && (
            <div className="space-y-2 rounded-2xl bg-teal-50/70 p-4 dark:bg-teal-950/30">
              <div className="flex justify-between text-xs font-semibold text-teal-800 dark:text-teal-200">
                <span className="truncate max-w-[280px]">{progress || 'Processing…'}</span>
                <span>{progressPct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-teal-200/60 dark:bg-teal-900/60">
                <div
                  className="h-full bg-gradient-to-r from-teal-500 to-cyan-500 transition-all duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          <button id="kb-upload-submit" type="button" disabled={loading}
            className="btn-primary w-full justify-center gap-2 py-3"
            onClick={submit}>
            {loading ? <><Loader2 size={18} className="animate-spin" />Processing ({progressPct}%)…</> : <><Zap size={18} />Upload & Index</>}
          </button>
        </div>
      </div>
    </div>
  )
}

function SourceCard({ src, onDelete, onPreview, onAsk }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow hover:shadow-md dark:border-slate-700 dark:bg-slate-900/70">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 text-white">
          <FileText size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-bold text-sm">{src.source_file}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {src.topic && <Pill label={src.topic} color="teal" />}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button type="button"
            className="btn-soft p-1.5 text-ocean hover:bg-ocean/10 dark:text-mint"
            title="Preview or view document"
            onClick={() => onPreview({ ...src, initialTab: 'doc' })}>
            <Eye size={15} />
          </button>
          <button type="button"
            className="btn-soft p-1.5 text-teal-600 hover:bg-teal-50 dark:hover:bg-teal-950/30"
            title="Inspect semantic chunks"
            onClick={() => onPreview({ ...src, initialTab: 'chunks' })}>
            <Search size={15} />
          </button>
          <button type="button"
            className="btn-soft p-1.5 text-violet-600 hover:bg-violet-50 dark:text-violet-300 dark:hover:bg-violet-950/30"
            title="Ask a question about only this file"
            onClick={() => onAsk && onAsk(src)}>
            <MessageSquare size={15} />
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
        </div>
      )}
    </div>
  )
}

// ─── Preview Panel ────────────────────────────────────────────────────────────
function PreviewPanel({ src, onClose }) {
  const [tab, setTab]         = useState(src?.initialTab || (src?.file_url ? 'doc' : 'chunks'))
  const [query, setQuery]     = useState(src?.topic || '')
  const [chunks, setChunks]   = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const docUrl = src?.file_url || `/api/rag/sources/${encodeURIComponent(src?.source_id || src?.source_file || '')}/file`

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex w-full max-w-4xl flex-col rounded-3xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
           style={{ maxHeight: '90vh', height: '820px', animation: 'modalRise .3s ease-out' }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white">
              <FileText size={20} />
            </div>
            <div className="min-w-0">
              <h2 className="font-black text-lg truncate">{src?.filename || src?.source_file}</h2>
              <p className="text-xs text-slate-500">{src?.subject} · Grade {src?.grade_level || 'All'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href={docUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-soft gap-1.5 text-xs py-1.5 px-3 text-teal-700 dark:text-mint"
              title="Open document in a new tab"
            >
              <ExternalLink size={14} />Open in New Tab
            </a>
            <button type="button" className="btn-soft p-1.5" onClick={onClose}><X size={18} /></button>
          </div>
        </div>

        {/* Tab switch */}
        <div className="flex border-b border-slate-100 px-6 pt-2 dark:border-slate-800 gap-2 bg-slate-50/50 dark:bg-slate-900/50">
          <button
            type="button"
            className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-semibold transition ${tab === 'doc' ? 'border-teal-600 text-teal-700 dark:border-mint dark:text-mint' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
            onClick={() => setTab('doc')}
          >
            <Eye size={16} />Document Preview
          </button>
          <button
            type="button"
            className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-semibold transition ${tab === 'chunks' ? 'border-teal-600 text-teal-700 dark:border-mint dark:text-mint' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
            onClick={() => setTab('chunks')}
          >
            <Layers size={16} />Semantic Chunks
          </button>
        </div>

        {/* Tab Content */}
        {tab === 'doc' ? (
          <div className="flex-1 overflow-hidden p-6 flex flex-col">
            <div className="flex-1 w-full rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-950">
              <iframe
                src={docUrl}
                className="w-full h-full min-h-[500px] border-0"
                title="Document PDF Preview"
              />
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex gap-2 border-b border-slate-100 px-6 py-3 dark:border-slate-800">
              <input id="preview-query" className="input flex-1" placeholder="Search topic or keywords in this source…"
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
                  <p className="text-sm">No chunks match query. Try searching for broader terms.</p>
                </div>
              )}
              {chunks.map((c, i) => (
                <div key={i} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/60">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <FileText size={13} />
                      <span>{c.source_file || src?.filename} · page {c.page}</span>
                    </div>
                    {c.score != null && (
                      <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-bold text-teal-700 dark:bg-teal-900/40 dark:text-teal-300">
                        score {c.score?.toFixed(3)}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{c.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function QAPanel({ scopedSource = null, scopedSourceLabel = null, onClearScope = null }) {
  const GREETING = {
    sender: 'ai',
    text: 'Hello! I am your EduSense AI Assistant. Ask me anything about your uploaded course materials.',
    sources: [],
    chunks_used: 0,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  const [messages, setMessages]   = useState([GREETING])
  const [input, setInput]         = useState('')
  const [subject, setSubject]     = useState('')
  const [grade, setGrade]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId]   = useState(null)
  const [convSearch, setConvSearch]       = useState('')
  const [sidebarOpen, setSidebarOpen]     = useState(false)
  const [listLoading, setListLoading]     = useState(false)
  const [attachOpen, setAttachOpen]       = useState(false)
  const [sourceList, setSourceList]       = useState([])
  const [selectedSources, setSelectedSources] = useState([])
  const [focusMode, setFocusMode] = useState(false)
  // Engine tier for KB answers: auto | private | cloud (addendum #11 §1.7)
  const [engine, setEngine] = useState('auto')
  const [engineInfo, setEngineInfo] = useState(null)
  const chatEndRef              = useRef(null)

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') setFocusMode(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const loadConversations = useCallback(async () => {
    setListLoading(true)
    try {
      const data = await api('/rag/chat/conversations')
      setConversations(Array.isArray(data) ? data : [])
    } catch (_) {
      setConversations([])
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => { loadConversations() }, [loadConversations])
  useEffect(() => {
    api('/rag/sources').then(d => setSourceList(Array.isArray(d) ? d : (d.sources || []))).catch(() => {})
    api('/rag/engine').then(d => {
      if (d?.engine) setEngine(d.engine)
      setEngineInfo(d || null)
    }).catch(() => {})
  }, [])

  async function openConversation(convId) {
    if (convId === activeConvId) { setSidebarOpen(false); return }
    setError('')
    try {
      const data = await api(`/rag/chat/conversations/${encodeURIComponent(convId)}`)
      const loaded = (data.messages || []).map(m => ({
        sender: m.role === 'user' ? 'user' : 'ai',
        text: m.content,
        sources: m.metadata?.sources || [],
        chunks_used: m.metadata?.chunks_used || 0,
        timestamp: m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
      }))
      setMessages(loaded.length ? loaded : [GREETING])
      setActiveConvId(convId)
      setSidebarOpen(false)
    } catch (e) {
      setError(e.message || 'Failed to load conversation')
    }
  }

  function newChat() {
    setMessages([GREETING])
    setActiveConvId(null)
    setError('')
    setSidebarOpen(false)
  }

  async function renameConversation(conv) {
    const title = window.prompt('Rename conversation', conv.title || '')
    if (!title || !title.trim()) return
    try {
      await api(`/rag/chat/conversations/${encodeURIComponent(conv.conversation_id)}`, {
        method: 'PATCH',
        body: { title: title.trim() },
      })
      setConversations(prev => prev.map(c =>
        c.conversation_id === conv.conversation_id ? { ...c, title: title.trim(), is_renamed: true } : c))
    } catch (e) {
      setError(e.message || 'Rename failed')
    }
  }

  async function deleteConversation(conv) {
    if (!window.confirm(`Delete conversation "${conv.title}"? This cannot be undone.`)) return
    try {
      await api(`/rag/chat/conversations/${encodeURIComponent(conv.conversation_id)}`, { method: 'DELETE' })
      setConversations(prev => prev.filter(c => c.conversation_id !== conv.conversation_id))
      if (activeConvId === conv.conversation_id) newChat()
    } catch (e) {
      setError(e.message || 'Delete failed')
    }
  }

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
        body: {
          question: q,
          top_k: 5,
          source_file: scopedSource || null,
          source_ids: selectedSources.length ? selectedSources : null,
          conversation_id: activeConvId,
          persist: true,
          engine,
        }
      })

      const aiMsg = {
        sender: 'ai',
        text: data.answer,
        sources: data.sources || [],
        chunks_used: data.chunks_used || 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      setMessages(prev => [...prev, aiMsg])
      if (data.conversation_id && data.conversation_id !== activeConvId) {
        setActiveConvId(data.conversation_id)
      }
      loadConversations()
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

  const filteredConvs = conversations.filter(c =>
    !convSearch || (c.title || '').toLowerCase().includes(convSearch.toLowerCase()))

  return (
    <div className={`flex h-full min-h-0 items-stretch gap-4 ${focusMode ? 'fixed inset-0 z-[70] bg-white p-3 dark:bg-slate-950' : ''}`}>
      {/* ── Conversation sidebar (desktop: inline, mobile: overlay) ── */}
      <aside className={`${focusMode ? 'hidden' : sidebarOpen ? 'fixed inset-x-3 top-32 z-30 flex' : 'hidden'} lg:static lg:z-auto lg:flex w-full lg:w-64 shrink-0 flex-col gap-2 h-full min-h-0 overflow-hidden`}>
        <div className="panel flex flex-col gap-2 p-3 h-full min-h-0">
          <div className="flex shrink-0 items-center justify-between">
            <p className="text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">Chats</p>
            <button type="button" onClick={newChat}
              className="flex items-center gap-1 rounded-lg bg-teal-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-teal-700">
              <Plus size={12} /> New
            </button>
          </div>
          <div className="shrink-0">
            <SearchInput value={convSearch} onChange={(e) => setConvSearch(e.target.value)}
              placeholder="Search chats…" className="[&_input]:py-1.5 [&_input]:text-xs" />
          </div>
          <div className="flex-1 min-h-0 space-y-1 overflow-y-auto pr-1">
            {listLoading && <p className="px-2 py-3 text-center text-xs text-slate-400"><Loader2 size={13} className="inline animate-spin" /></p>}
            {!listLoading && filteredConvs.length === 0 && (
              <p className="px-2 py-3 text-center text-xs text-slate-400">
                {conversations.length === 0 ? 'No saved chats yet' : 'No chats match'}
              </p>
            )}
            {filteredConvs.map(c => (
              <div key={c.conversation_id}
                className={`group flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs cursor-pointer transition
                  ${activeConvId === c.conversation_id
                    ? 'bg-teal-50 text-teal-800 dark:bg-teal-950/40 dark:text-teal-200'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'}`}
                onClick={() => openConversation(c.conversation_id)}>
                <MessageSquare size={12} className="shrink-0 opacity-60" />
                <span className="min-w-0 flex-1 truncate font-medium">{c.title}</span>
                <span className="hidden shrink-0 items-center gap-0.5 group-hover:flex">
                  <button type="button" title="Rename" onClick={(e) => { e.stopPropagation(); renameConversation(c) }}
                    className="rounded p-0.5 hover:bg-slate-200 dark:hover:bg-slate-700"><Pencil size={11} /></button>
                  <button type="button" title="Delete" onClick={(e) => { e.stopPropagation(); deleteConversation(c) }}
                    className="rounded p-0.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40"><Trash2 size={11} /></button>
                </span>
              </div>
            ))}
          </div>
        </div>
      </aside>

    <div className="panel flex flex-1 min-h-0 min-w-0 flex-col h-full overflow-hidden p-0">
      {/* Header & Controls */}
      <div className="shrink-0 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <button type="button" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800"
            onClick={() => setSidebarOpen(v => !v)} title="Chats">
            {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
          </button>
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-600 text-white shadow-sm">
            <Sparkles size={20} />
          </div>
          <div>
            <h2 className="text-base font-black">Knowledge Base Chat</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">Answers from your uploaded documents only — never the web</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500" title={engineInfo?.privacy_source || ''}>
            Engine
            <select
              className="input h-8 min-w-[210px] w-auto py-1 text-xs"
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
            >
              {(engineInfo?.options || [
                { value: 'auto', label: 'Auto' },
                { value: 'private', label: 'Private (local)' },
                { value: 'cloud', label: 'Cloud' },
              ]).map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
            </select>
          </label>
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${engine === 'private' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
            {engine === 'private' ? 'Private: stays on this computer' : `Privacy: no training on your files (${engineInfo?.embeddings ? 'local embeddings' : 'embeddings local'})`}
          </span>
          <button type="button" className="btn-soft text-xs py-1.5 px-3" onClick={() => setFocusMode(v => !v)}>
            {focusMode ? <><Minimize2 size={13} /> Exit focus</> : <><Maximize2 size={13} /> Focus mode</>}
          </button>
          <button type="button" className="btn-soft text-xs py-1.5 px-3" onClick={newChat}>
            New Chat
          </button>
        </div>
      </div>

      {scopedSource && (
        <div className="mx-4 mt-2 flex items-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-800 dark:border-violet-900/50 dark:bg-violet-950/30 dark:text-violet-200">
          <FileText size={13} className="shrink-0" />
          <span className="font-semibold">Asking about only:</span>
          <span className="truncate font-medium">{scopedSourceLabel || scopedSource}</span>
          <button type="button" className="ml-auto shrink-0 rounded-full p-0.5 hover:bg-violet-200/60 dark:hover:bg-violet-900/50" onClick={onClearScope} title="Clear file scope">
            <X size={13} />
          </button>
        </div>
      )}

      {/* Messages Feed */}
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3 min-h-0">
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
                    {normalizeSources(m.sources).map((s, i) => (
                      <span key={i} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-slate-700 shadow-xs dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <FileText size={11} className="text-teal-500" />
                        {s.label}{s.page != null ? ` (p.${s.page})` : ''}
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

      {/* Selected source chips */}
      {selectedSources.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pb-1">
          {selectedSources.map((sid) => {
            const src = sourceList.find(x => (x.source_id || x.source_file) === sid)
            return (
              <span key={sid} className="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2.5 py-1 text-xs font-medium text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
                <FileText size={11} /> {src?.source_file || src?.filename || sid}
                <button type="button" onClick={() => setSelectedSources(prev => prev.filter(x => x !== sid))} className="hover:text-red-500"><X size={11} /></button>
              </span>
            )
          })}
        </div>
      )}

      {/* Attach-from-uploads picker */}
      {attachOpen && (
        <div className="max-h-44 overflow-y-auto rounded-xl border border-slate-200 p-2 dark:border-slate-700">
          {sourceList.length === 0 && <p className="px-2 py-3 text-xs text-slate-400">No uploaded sources yet.</p>}
          {sourceList.map((src) => {
            const sid = src.source_id || src.source_file
            const checked = selectedSources.includes(sid)
            return (
              <label key={sid} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-slate-50 dark:hover:bg-slate-800">
                <input type="checkbox" className="rounded" checked={checked}
                  onChange={() => setSelectedSources(prev => checked ? prev.filter(x => x !== sid) : [...prev, sid])} />
                <span className="truncate font-medium">{src.source_file || src.filename || sid}</span>
                <span className="text-slate-400">{src.chunk_count ? `${src.chunk_count} chunks` : ''}</span>
              </label>
            )
          })}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={(e) => { e.preventDefault(); sendMessage(); }} className="flex shrink-0 items-center gap-2 border-t border-slate-100 px-4 py-3 dark:border-slate-800">
        <button type="button" onClick={() => setAttachOpen(o => !o)} title="Attach from uploaded files"
          className={attachOpen || selectedSources.length ? 'bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300' : 'text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}>
          <Paperclip size={16} />
        </button>
        <input
          id="qa-question"
          className="input flex-1 py-2.5"
          placeholder="Ask about your uploaded documents…"
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
  const [deleting, setDeleting]       = useState(null)
  const [activeTab, setActiveTab]     = useState('library')
  const [qaSource, setQaSource]       = useState(null)
  const [activeJob, setActiveJob]     = useState(null)

  useEffect(() => {
    try {
      const stored = localStorage.getItem('edusense_kb_ingest_job')
      if (stored) {
        const parsed = JSON.parse(stored)
        if (parsed?.jobId) {
          setActiveJob(parsed)
          pollActiveJob(parsed.jobId)
        }
      }
    } catch (_) {}
  }, [])

  const pollActiveJob = (jobId) => {
    const interval = setInterval(async () => {
      try {
        const res = await api(`/rag/ingest/status/${jobId}`)
        setActiveJob(curr => curr ? { ...curr, progress: res.progress, message: res.message, status: res.status } : null)
        if (res.status === 'completed') {
          clearInterval(interval)
          try { localStorage.removeItem('edusense_kb_ingest_job') } catch (_) {}
          setTimeout(() => {
            setActiveJob(null)
            loadSources()
          }, 2000)
        } else if (res.status === 'failed') {
          clearInterval(interval)
          try { localStorage.removeItem('edusense_kb_ingest_job') } catch (_) {}
        }
      } catch (err) {
        clearInterval(interval)
        try { localStorage.removeItem('edusense_kb_ingest_job') } catch (_) {}
        setActiveJob(curr => curr ? {
          ...curr,
          status: err.status === 404 ? 'stale' : 'failed',
          message: err.status === 404
            ? 'Ingestion status is unavailable after a server restart. Refresh the Knowledge Base to check whether the document finished indexing.'
            : err.message || 'Could not track ingestion status.',
        } : null)
      }
    }, 1500)
  }

  async function loadSources() {
    setLoading(true)
    setError('')
    try {
      const data = await api('/rag/sources')
      setSources(Array.isArray(data) ? data : [])
    } catch (e) {
      // Distinguish a network failure (api.js already names the real API base
      // URL) from an HTTP error, and always show the real status + detail.
      setError(e.status
        ? `The Knowledge Base request failed with HTTP ${e.status}: ${e.message}`
        : e.message)
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
    return !q || s.source_file?.toLowerCase().includes(q)
      || s.topic?.toLowerCase().includes(q)
  })

  return (
    <div className="flex flex-col h-full min-h-0 w-full overflow-hidden p-3 sm:p-4 gap-3">
      {/* ── Page Header ── */}
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white">
              <Database size={18} />
            </div>
            <h1 className="text-2xl font-black">Knowledge Base</h1>
            <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-bold text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
              {sources.length} documents
            </span>
          </div>
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

      {/* Background ingestion banner */}
      {activeJob && activeJob.status !== 'completed' && (
        <div className={`shrink-0 flex items-center justify-between gap-4 rounded-2xl border p-3 ${
          ['stale', 'failed'].includes(activeJob.status)
            ? 'border-amber-200 bg-amber-50/80 dark:border-amber-900/50 dark:bg-amber-950/30'
            : 'border-teal-200 bg-teal-50/80 dark:border-teal-900/50 dark:bg-teal-950/30'
        }`}>
          <div className="flex items-center gap-3 min-w-0">
            {['stale', 'failed'].includes(activeJob.status)
              ? <AlertCircle size={18} className="text-amber-600 shrink-0" />
              : <Loader2 size={18} className="animate-spin text-teal-600 shrink-0" />}
            <div className="min-w-0">
              <p className={`text-sm font-bold truncate ${
                ['stale', 'failed'].includes(activeJob.status)
                  ? 'text-amber-900 dark:text-amber-200'
                  : 'text-teal-900 dark:text-teal-200'
              }`}>
                {activeJob.status === 'stale'
                  ? `Ingestion status unavailable for ${activeJob.filename || 'document'}`
                  : activeJob.status === 'failed'
                    ? `Ingestion failed for ${activeJob.filename || 'document'}`
                    : `Ingesting ${activeJob.filename || 'document'}... (${activeJob.progress || 0}%)`}
              </p>
              <p className={`text-xs truncate ${
                ['stale', 'failed'].includes(activeJob.status)
                  ? 'text-amber-800 dark:text-amber-300'
                  : 'text-teal-700 dark:text-teal-300'
              }`}>
                {activeJob.message || 'Processing pages and generating semantic embeddings...'}
              </p>
            </div>
          </div>
          {!['stale', 'failed'].includes(activeJob.status) && (
            <div className="w-32 bg-teal-200 dark:bg-teal-900/60 rounded-full h-2 overflow-hidden shrink-0">
              <div className="bg-teal-600 h-2 transition-all duration-300" style={{ width: `${activeJob.progress || 10}%` }} />
            </div>
          )}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="shrink-0 flex gap-1 rounded-2xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-900/50 w-fit">
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
        <div className="flex flex-col flex-1 min-h-0 gap-3 overflow-hidden">
          {/* Filter bar */}
          <div className="panel shrink-0 flex flex-wrap items-center gap-3">
            <SearchInput id="kb-search" className="flex-1 min-w-48" value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)} placeholder="Search by filename or topic…" />
            {searchQ && (
              <button type="button" className="btn-soft gap-1.5 text-sm"
                onClick={() => setSearchQ('')}>
                <X size={14} />Clear
              </button>
            )}
            <p className="ms-auto text-xs text-slate-400">{filtered.length} of {sources.length}</p>
          </div>

          {/* Error */}
          {error && (
            <div className="shrink-0 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900/40 dark:bg-red-950/20">
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
                    : 'Try clearing your search query.'}
                </p>
              </div>
              {sources.length === 0 && (
                <button type="button" className="btn-primary gap-2" onClick={() => setShowUpload(true)}>
                  <Upload size={16} />Upload your first PDF
                </button>
              )}
            </div>
          )}

          {/* Source list with internal scroll */}
          {!loading && filtered.length > 0 && (
            <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
              {filtered.map(src => (
                deleting === src.source_file ? (
                  <div key={src.source_file} className="flex h-16 items-center justify-center rounded-2xl border border-red-200 bg-red-50 text-sm text-red-600 dark:border-red-900/40 dark:bg-red-950/20">
                    <Loader2 size={16} className="animate-spin mr-2" />Deleting {src.source_file}…
                  </div>
                ) : (
                  <SourceCard key={src.source_file} src={src}
                    onDelete={deleteSource}
                    onPreview={(s) => setPreviewSrc(s)}
                    onAsk={(s) => { setQaSource(s.source_id || s.source_file); setActiveTab('qa') }} />
                )
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Q&A Tab ── */}
      {activeTab === 'qa' && (
        <div className="flex-1 min-h-0 h-full overflow-hidden">
          <QAPanel
            scopedSource={qaSource}
            scopedSourceLabel={sources.find(s => (s.source_id || s.source_file) === qaSource)?.source_file || qaSource}
            onClearScope={() => setQaSource(null)}
          />
        </div>
      )}

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
