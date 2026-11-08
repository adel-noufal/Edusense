import { useEffect, useState, useRef, useCallback } from 'react'
import { CheckCircle2, Clock3, Download, FileQuestion, Layers, Sparkles, Trash2, Video, Volume2, ShieldCheck, AlertTriangle, Send, Bot, Loader2, Zap, Globe, Database, Shield, Lock, Camera, X } from 'lucide-react'
import { api, downloadAuthenticatedRequest, staticUrl } from '../services/api'
import { downloadBlob, downloadText, flashcardsToHtml, lessonToMarkdown, downloadLessonAsDoc, downloadLessonAsHtml, downloadLessonAsPdf, downloadLessonAsPptxHtml, downloadQuizAsDoc, downloadQuizAsHtml, downloadQuizAsPdf, downloadFlashcardsAsDoc, downloadFlashcardsAsPdf } from '../utils/download'
import { useLanguage } from '../context/LanguageContext'
import { useGenerationJobs } from '../context/GenerationJobContext'
import { SessionPickerFields, useInstructorSessions } from '../components/SessionPickerFields'
import { useToast } from '../context/ToastContext'

const languages = ['English', 'Arabic', 'French', 'Spanish']
const styles = ['Formal', 'Friendly', 'Interactive', 'Storytelling', 'Professional']
const difficulties = ['Easy', 'Medium', 'Hard']
const aiModels = ['Gemini 2.0 Flash (Internet Required)', 'Local Ollama - Mistral / Llama 3.2 (Offline)']

function checkInternetAndModel(selectedModel, setForm) {
  if (selectedModel && (selectedModel.includes('Gemini') || selectedModel.includes('Internet Required'))) {
    const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true
    if (!isOnline) {
      if (setForm) {
        setForm((prev) => ({ ...prev, model: aiModels[1] }))
      }
      alert("No Internet Connection\n\nGemini requires an active internet connection. Automatically switching your model to Local Ollama (Offline mode) to proceed.")
      return aiModels[1]
    }
  }
  return selectedModel
}

/** Strip UI-only fields and normalize session IDs for the API. */
function buildAiPayload(form) {
  const { model, session_id, source_session_id, ...rest } = form
  return {
    ...rest,
    session_id: session_id ? Number(session_id) : null,
    source_session_id: source_session_id ? Number(source_session_id) : null,
  }
}

/** Sync local generator UI with a background job that keeps running across tab changes. */
function useBackgroundGeneration(type) {
  const { startJob, job, removeJob } = useGenerationJobs(type)
  const [loading, setLoading] = useState(() => job?.status === 'pending')
  const [error, setError] = useState(() => (job?.status === 'error' ? job.error : ''))

  useEffect(() => {
    if (!job) {
      setLoading(false)
      return
    }
    if (job.status === 'pending') {
      setLoading(true)
      setError('Generation running in background — you can navigate away and come back later.')
      return
    }
    if (job.status === 'error') {
      setLoading(false)
      setError(job.error || 'Generation failed')
      return
    }
    setLoading(false)
    setError('')
  }, [job])

  async function queue(endpoint, payload, label) {
    setLoading(true)
    setError('')
    try {
      await startJob({ type, endpoint, payload, label })
      setError('Generation running in background — you can navigate away and come back later.')
    } catch (err) {
      setLoading(false)
      setError(err.message || 'Could not start generation')
      throw err
    }
  }

  function clearCompletedJob() {
    if (job?.jobId) removeJob(job.jobId)
  }

  return { loading, error, setError, queue, job, clearCompletedJob }
}

export function LessonGenerator() {
  const { t } = useLanguage()
  const [form, setForm] = useState({
    topic: 'Neural Networks',
    prompt: 'Teach beginners with examples',
    language: 'English',
    teaching_style: 'Interactive',
    duration: 5,
    additional_notes: '',
    session_id: '',
    source_session_id: '',
    model: aiModels[0],
  })
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const { loading, error, setError, queue, job, clearCompletedJob } = useBackgroundGeneration('lesson')

  async function loadHistory() {
    try {
      const data = await api('/ai/generations?type=lesson')
      setHistory(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  useEffect(() => {
    if (job?.status === 'done' && job.result) {
      setResult(job.result)
      loadHistory()
      clearCompletedJob()
    }
  }, [job])

  async function submit(e) {
    e.preventDefault()
    checkInternetAndModel(form.model, setForm)
    if (form.topic.trim().length < 3) {
      setError(t('ai.topicMin'))
      return
    }
    try {
      const { model, ...payload } = form
      await queue('/ai/lessons/queue', buildAiPayload(payload), form.topic)
    } catch { /* handled in hook */ }
  }

  async function deleteHistory(id, e) {
    e.stopPropagation()
    try {
      await api(`/ai/generations/${id}`, { method: 'DELETE' })
      await loadHistory()
      if (result && result.id === id) setResult(null)
    } catch { /* ignore */ }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
      <div className="space-y-6">
        <ToolShell title={t('ai.lessonTitle')} icon={<Sparkles />} onSubmit={submit} loading={loading} error={error}>
          <div className="grid gap-4 md:grid-cols-2">
            <SelectField label="AI Model" value={form.model} options={aiModels} onChange={(value) => setForm({ ...form, model: value })} />
            <Field label={t('ai.topic')} value={form.topic} onChange={(value) => setForm({ ...form, topic: value })} />
            <Field label={t('ai.prompt')} value={form.prompt} onChange={(value) => setForm({ ...form, prompt: value })} />
            <SelectField label={t('ai.language')} value={form.language} options={languages} onChange={(value) => setForm({ ...form, language: value })} />
            <SelectField label={t('ai.style')} value={form.teaching_style} options={styles} onChange={(value) => setForm({ ...form, teaching_style: value })} />
            <Field label={t('ai.duration')} type="number" value={form.duration} onChange={(value) => setForm({ ...form, duration: Number(value) || 5 })} />
            <Field label={t('ai.notes')} value={form.additional_notes} onChange={(value) => setForm({ ...form, additional_notes: value })} textarea />
            <SessionPickerFields form={form} setForm={setForm} />
          </div>
          <button className="btn-primary" disabled={loading}>{loading ? t('ai.generatingLesson') : t('ai.generateLesson')}</button>
        </ToolShell>
        {result && <LessonResult result={result} request={form} />}
      </div>

      <div className="panel space-y-4">
        <h2 className="text-lg font-bold">Recent Lessons</h2>
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          {history.map((h) => (
            <div 
              key={h.id} 
              onClick={async () => {
                try {
                  const latest = await api(`/ai/generations/${h.id}`)
                  setResult(latest.data)
                  setForm(prev => ({
                    ...prev,
                    topic: latest.topic || h.topic,
                    prompt: latest.prompt || h.prompt,
                    language: latest.data?.language || h.data?.language || 'English',
                    teaching_style: latest.data?.style || h.data?.style || 'Interactive',
                    duration: latest.data?.duration || h.data?.duration || 5,
                    session_id: latest.session_id ? String(latest.session_id) : (prev.session_id || ''),
                    additional_notes: '',
                  }))
                } catch {
                  setResult(h.data)
                  setForm(prev => ({
                    ...prev,
                    topic: h.topic,
                    prompt: h.prompt,
                    language: h.data?.language || 'English',
                    teaching_style: h.data?.style || 'Interactive',
                    duration: h.data?.duration || 5,
                    additional_notes: '',
                  }))
                }
              }}
              className="group cursor-pointer rounded-2xl border border-slate-200 p-4 hover:bg-slate-50/50 transition dark:border-slate-700 dark:hover:bg-slate-800/50"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-bold text-sm truncate block max-w-[180px]">{h.topic}</span>
                <button 
                  onClick={(e) => deleteHistory(h.id, e)}
                  className="text-slate-400 hover:text-red-500 transition opacity-0 group-hover:opacity-100"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-1">{new Date(h.created_at).toLocaleDateString()}</p>
            </div>
          ))}
          {!history.length && <p className="text-sm text-slate-500">No lessons generated yet.</p>}
        </div>
      </div>

      {publishModalQuiz && (
        <PublishExamModal
          quiz={publishModalQuiz}
          onClose={() => setPublishModalQuiz(null)}
          onPublished={(updated) => {
            if (result && result.id === updated.id) {
              setResult({ ...result, ...updated })
            }
            loadHistory()
          }}
        />
      )}
    </div>
  )
}

export function FlashcardGenerator() {
  const { t } = useLanguage()
  const [form, setForm] = useState({
    topic: 'Neural Networks',
    prompt: 'Focus on key definitions, formulas, and practical examples',
    count: 10,
    language: 'English',
    session_id: '',
    source_session_id: '',
    model: aiModels[0],
  })
  const [result, setResult] = useState(null)
  const [flipped, setFlipped] = useState({})
  const [history, setHistory] = useState([])
  const { loading, error, setError, queue, job, clearCompletedJob } = useBackgroundGeneration('flashcard')

  async function loadHistory() {
    try {
      const data = await api('/ai/generations?type=flashcard')
      setHistory(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  useEffect(() => {
    if (job?.status === 'done' && job.result) {
      setResult(job.result)
      loadHistory()
      clearCompletedJob()
    }
  }, [job])

  async function submit(e) {
    e.preventDefault()
    checkInternetAndModel(form.model, setForm)
    if (form.topic.trim().length < 3) {
      setError(t('ai.topicMin'))
      return
    }
    setFlipped({})
    try {
      const { model, ...payload } = form
      await queue('/ai/flashcards/queue', buildAiPayload({ ...payload, count: Number(form.count) || 10 }), form.topic)
    } catch { /* handled in hook */ }
  }

  async function deleteHistory(id, e) {
    e.stopPropagation()
    try {
      await api(`/ai/generations/${id}`, { method: 'DELETE' })
      await loadHistory()
      if (result && result.id === id) setResult(null)
    } catch { /* ignore */ }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
      <div className="space-y-6">
        <ToolShell title={t('ai.flashcardTitle')} icon={<Layers />} onSubmit={submit} loading={loading} error={error}>
          <div className="grid gap-4 md:grid-cols-2">
            <SelectField label="AI Model" value={form.model} options={aiModels} onChange={(value) => setForm({ ...form, model: value })} />
            <Field label={t('ai.topic')} value={form.topic} onChange={(value) => setForm({ ...form, topic: value })} />
            <Field label={t('ai.cardCount')} type="number" value={form.count} onChange={(value) => setForm({ ...form, count: value })} />
            <SelectField label={t('ai.language')} value={form.language} options={languages} onChange={(value) => setForm({ ...form, language: value })} />
            <div className="md:col-span-2">
              <Field label={t('ai.prompt')} value={form.prompt} onChange={(value) => setForm({ ...form, prompt: value })} textarea />
            </div>
            <SessionPickerFields form={form} setForm={setForm} />
          </div>
          <button className="btn-primary" disabled={loading}>{loading ? t('ai.generatingLesson') : t('ai.generateFlashcards')}</button>
        </ToolShell>
        {result && <FlashcardResult result={result} request={form} flipped={flipped} onFlip={setFlipped} />}
      </div>

      <div className="panel space-y-4">
        <h2 className="text-lg font-bold">Recent Flashcards</h2>
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          {history.map((h) => (
            <div 
              key={h.id} 
              onClick={() => {
                setResult(h.data)
                setForm({
                  topic: h.topic,
                  prompt: h.prompt || h.data.prompt || '',
                  count: h.data.cards?.length || 10,
                  language: h.data.language || 'English',
                  model: aiModels[0],
                })
                setFlipped({})
              }}
              className="group cursor-pointer rounded-2xl border border-slate-200 p-4 hover:bg-slate-50/50 transition dark:border-slate-700 dark:hover:bg-slate-800/50"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-bold text-sm truncate block max-w-[180px]">{h.topic}</span>
                <button 
                  onClick={(e) => deleteHistory(h.id, e)}
                  className="text-slate-400 hover:text-red-500 transition opacity-0 group-hover:opacity-100"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-1">{new Date(h.created_at).toLocaleDateString()}</p>
              {h.prompt && <p className="text-xs text-slate-400 mt-1 truncate">{h.prompt}</p>}
            </div>
          ))}
          {!history.length && <p className="text-sm text-slate-500">No flashcards generated yet.</p>}
        </div>
      </div>
    </div>
  )
}

export function QuizGenerator() {
  const { t } = useLanguage()
  const [form, setForm] = useState({
    topic: 'Neural Networks',
    prompt: 'Focus on conceptual understanding and real-world applications',
    difficulty: 'Medium',
    count: 5,
    session_id: '',
    source_session_id: '',
    model: aiModels[0],
  })
  const [result, setResult] = useState(null)
  const [answers, setAnswers] = useState({})
  const [revealed, setRevealed] = useState({})
  const [history, setHistory] = useState([])
  const [publishModalQuiz, setPublishModalQuiz] = useState(null)
  const { loading, error, setError, queue, job, clearCompletedJob } = useBackgroundGeneration('quiz')

  async function loadHistory() {
    try {
      const data = await api('/ai/quizzes')
      setHistory(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  useEffect(() => {
    if (job?.status === 'done' && job.result) {
      setResult(job.result)
      loadHistory()
      clearCompletedJob()
    }
  }, [job])

  async function submit(e) {
    e.preventDefault()
    checkInternetAndModel(form.model, setForm)
    if (form.topic.trim().length < 3) {
      setError(t('ai.topicMin'))
      return
    }
    setAnswers({})
    setRevealed({})
    try {
      const { model, ...payload } = form
      await queue('/ai/quizzes/queue', buildAiPayload({ ...payload, count: Number(form.count) || 5 }), form.topic)
    } catch { /* handled in hook */ }
  }

  async function deleteHistory(id, e) {
    e.stopPropagation()
    try {
      await api(`/ai/quizzes/${id}`, { method: 'DELETE' })
      await loadHistory()
      if (result && result.id === id) setResult(null)
    } catch { /* ignore */ }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
      <div className="space-y-6">
        <ToolShell title={t('ai.quizTitle')} icon={<FileQuestion />} onSubmit={submit} loading={loading} error={error}>
          <div className="grid gap-4 md:grid-cols-2">
            <SelectField label="AI Model" value={form.model} options={aiModels} onChange={(value) => setForm({ ...form, model: value })} />
            <Field label={t('ai.topic')} value={form.topic} onChange={(value) => setForm({ ...form, topic: value })} />
            <SelectField label={t('ai.difficulty')} value={form.difficulty} options={difficulties} onChange={(value) => setForm({ ...form, difficulty: value })} />
            <Field label={t('ai.questionCount')} type="number" value={form.count} onChange={(value) => setForm({ ...form, count: value })} />
            <div className="md:col-span-2">
              <Field label={t('ai.prompt')} value={form.prompt} onChange={(value) => setForm({ ...form, prompt: value })} textarea />
            </div>
            <SessionPickerFields form={form} setForm={setForm} />
          </div>
          <button className="btn-primary" disabled={loading}>{loading ? t('ai.generatingLesson') : t('ai.generateQuiz')}</button>
        </ToolShell>
        {result && <QuizResult result={result} answers={answers} revealed={revealed} onAnswer={setAnswers} onReveal={setRevealed} onPublishExam={setPublishModalQuiz} />}
      </div>

      <div className="panel space-y-4">
        <h2 className="text-lg font-bold">Recent Quizzes</h2>
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          {history.map((h) => (
            <div 
              key={h.id} 
              onClick={() => {
                setResult(h)
                setForm({
                  topic: h.title,
                  prompt: '',
                  difficulty: h.difficulty,
                  count: h.questions?.length || 5,
                  session_id: h.session_id ? String(h.session_id) : '',
                  source_session_id: '',
                  model: aiModels[0],
                })
                setAnswers({})
                setRevealed({})
              }}
              className="group cursor-pointer rounded-2xl border border-slate-200 p-4 hover:bg-slate-50/50 transition dark:border-slate-700 dark:hover:bg-slate-800/50"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-bold text-sm truncate block max-w-[180px]">{h.title}</span>
                  {h.is_exam && (
                    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
                      <Shield size={9} /> Published Exam
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setPublishModalQuiz(h) }}
                    className="rounded-lg p-1 text-slate-400 hover:bg-purple-50 hover:text-purple-600 transition"
                    title="Publish as Exam"
                  >
                    <Shield size={14} />
                  </button>
                  <button 
                    onClick={(e) => deleteHistory(h.id, e)}
                    className="text-slate-400 hover:text-red-500 transition opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-slate-500 mt-1">{new Date(h.created_at).toLocaleDateString()}</p>
            </div>
          ))}
          {!history.length && <p className="text-sm text-slate-500">No quizzes generated yet.</p>}
        </div>
      </div>
    </div>
  )
}

export function VideoLibrary() {
  const { t } = useLanguage()
  const [form, setForm] = useState({
    title: 'Backpropagation Basics',
    prompt: 'Create a short educational video',
    language: 'English',
    style: 'Friendly',
    duration: 5,
    notes: '',
    session_id: '',
    source_session_id: '',
    model: aiModels[0],
  })
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const { loading, error, setError, queue, job, clearCompletedJob } = useBackgroundGeneration('video')

  async function loadHistory() {
    try {
      const data = await api('/ai/videos')
      setHistory(Array.isArray(data) ? data : [])
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  useEffect(() => {
    if (job?.status === 'done' && job.result) {
      setResult(job.result)
      loadHistory()
      clearCompletedJob()
    }
  }, [job])

  async function submit(e) {
    e.preventDefault()
    checkInternetAndModel(form.model, setForm)
    if (form.title.trim().length < 3) {
      setError(t('ai.titleMin'))
      return
    }
    try {
      const { model, ...payload } = form
      await queue('/ai/videos/queue', buildAiPayload(payload), form.title)
    } catch { /* handled in hook */ }
  }

  async function deleteHistory(id, e) {
    e.stopPropagation()
    try {
      await api(`/ai/videos/${id}`, { method: 'DELETE' })
      await loadHistory()
      if (result?.id === id) setResult(null)
    } catch { /* ignore */ }
  }

  async function openHistoryItem(item) {
    try {
      const detail = await api(`/ai/videos/${item.id}`)
      setResult(detail)
      setForm({
        title: detail.title || item.title,
        prompt: detail.prompt || '',
        language: detail.language || 'English',
        style: detail.style || 'Friendly',
        duration: detail.duration || 5,
        notes: detail.notes || '',
        session_id: '',
        source_session_id: '',
        model: aiModels[0],
      })
    } catch {
      setResult(item)
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
      <div className="space-y-6">
        <ToolShell title={t('ai.videoTitle')} icon={<Video />} onSubmit={submit} loading={loading} error={error}>
          <div className="grid gap-4 md:grid-cols-2">
            <SelectField label="AI Model" value={form.model} options={aiModels} onChange={(value) => setForm({ ...form, model: value })} />
            <Field label={t('sessions.titleField')} value={form.title} onChange={(value) => setForm({ ...form, title: value })} />
            <Field label={t('ai.prompt')} value={form.prompt} onChange={(value) => setForm({ ...form, prompt: value })} />
            <SelectField label={t('ai.language')} value={form.language} options={languages} onChange={(value) => setForm({ ...form, language: value })} />
            <SelectField label={t('ai.videoStyle')} value={form.style} options={styles} onChange={(value) => setForm({ ...form, style: value })} />
            <Field label={t('ai.duration')} type="number" value={form.duration} onChange={(value) => setForm({ ...form, duration: Number(value) || 5 })} />
            <Field label={t('ai.videoNotes')} value={form.notes} onChange={(value) => setForm({ ...form, notes: value })} textarea />
            <SessionPickerFields form={form} setForm={setForm} />
          </div>
          <button className="btn-primary" disabled={loading}>{loading ? t('ai.buildingVideo') : t('ai.generateVideo')}</button>
        </ToolShell>
        {loading && (
          <div className="panel flex items-center gap-3 border border-teal-200 bg-teal-50/70 text-sm text-teal-900 dark:border-teal-800 dark:bg-teal-950/30 dark:text-teal-100">
            <Clock3 className="animate-pulse shrink-0" size={18} />
            Building your video in the background. You can browse other tabs — come back here when it finishes.
          </div>
        )}
        {result && <VideoResult result={result} initialForm={form} onReplace={setResult} onHistoryRefresh={loadHistory} />}
      </div>

      <div className="panel space-y-4">
        <h2 className="text-lg font-bold">Recent Videos</h2>
        <div className="space-y-3 max-h-[640px] overflow-y-auto">
          {history.map((h) => (
            <div
              key={h.id}
              onClick={() => openHistoryItem(h)}
              className={`group cursor-pointer rounded-2xl border p-4 transition hover:bg-slate-50/50 dark:hover:bg-slate-800/50 ${result?.id === h.id ? 'border-teal-300 bg-teal-50/70 dark:border-teal-700 dark:bg-slate-800' : 'border-slate-200 dark:border-slate-700'}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-bold text-sm truncate block max-w-[180px]">{h.title}</span>
                <button
                  onClick={(e) => deleteHistory(h.id, e)}
                  className="text-slate-400 hover:text-red-500 transition opacity-0 group-hover:opacity-100"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-1">{new Date(h.created_at).toLocaleDateString()} · {h.status}</p>
              {h.scenes?.length > 0 && <p className="text-xs text-slate-400 mt-1">{h.scenes.length} scenes</p>}
            </div>
          ))}
          {!history.length && <p className="text-sm text-slate-500">No videos generated yet.</p>}
        </div>
      </div>
    </div>
  )
}

function ToolShell({ title, icon, onSubmit, loading, error, children }) {
  const { t } = useLanguage()
  return (
    <form className="panel space-y-5" onSubmit={onSubmit}>
      <div className="flex items-center gap-3 text-xl font-black">{icon}{title}</div>
      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
      {children}
      {loading && <p className="text-sm text-slate-500">{t('ai.working')}</p>}
    </form>
  )
}

function Field({ label, value, onChange, type = 'text', textarea = false }) {
  return (
    <label className="space-y-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
      <span>{label}</span>
      {textarea ? (
        <textarea className="input min-h-28" value={value} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input className="input" type={type} value={value} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  )
}

function SelectField({ label, value, options, onChange }) {
  return (
    <label className="space-y-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
      <span>{label}</span>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  )
}

function LessonResult({ result, request }) {
  const { t } = useLanguage()
  const slug = (result.topic || 'lesson').replace(/\s+/g, '-').toLowerCase()
  return (
    <div className="space-y-5 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.topic} subtitle={`${result.language} · ${result.style} · ${result.duration} min`} model={request?.model} sources={result.sources} unverified={result.unverified} />
      <DownloadBar
        items={[
          {
            label: 'Word (.doc)',
            onClick: () => downloadLessonAsDoc(result, `${slug}.doc`),
          },
          {
            label: 'PowerPoint (.pptx)',
            onClick: () => downloadLessonAsPptxHtml(result, `${slug}.pptx.html`),
          },
          {
            label: 'PDF Document (.pdf)',
            onClick: () => downloadLessonAsPdf(result, slug),
          },
          {
            label: 'HTML (.html)',
            onClick: () => downloadLessonAsHtml(result, `${slug}.html`),
          },
          {
            label: 'Markdown (.md)',
            onClick: () => downloadText(lessonToMarkdown(result), `${slug}.md`, 'text/markdown'),
          },
        ]}
      />
      {result.overview && (
        <Section title={t('ai.overview')}>
          <p className="text-sm leading-7 text-slate-700 dark:text-slate-300">{result.overview}</p>
        </Section>
      )}
      <Section title={t('ai.objectives')}>
        <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
          {result.learning_objectives?.map((objective) => <li key={objective}>• {objective}</li>)}
        </ul>
      </Section>
      {result.sections?.length > 0 && (
        <Section title={t('ai.sections')}>
          <div className="grid gap-3">
            {result.sections.map((section) => (
              <article key={section.heading} className="rounded-md bg-slate-100 p-4 dark:bg-slate-800">
                <p className="font-bold">{section.heading}</p>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{section.content}</p>
                {section.example && <p className="mt-2 text-xs uppercase tracking-wide text-ocean dark:text-mint">Example: {section.example}</p>}
              </article>
            ))}
          </div>
        </Section>
      )}
      <Section title={t('ai.slides')}>
        <div className="grid gap-3 md:grid-cols-2">
          {result.slides?.map((slide) => (
            <article key={slide.title} className="rounded-md bg-slate-100 p-4 dark:bg-slate-800">
              <p className="font-bold">{slide.title}</p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{slide.content}</p>
              {slide.diagram && <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">{slide.diagram}</p>}
            </article>
          ))}
        </div>
      </Section>
      {result.key_points?.length > 0 && (
        <Section title={t('ai.keyPoints')}>
          <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            {result.key_points.map((point) => <li key={point}>• {point}</li>)}
          </ul>
        </Section>
      )}
      {result.summary && (
        <Section title={t('ai.summary')}>
          <p className="text-sm leading-7 text-slate-700 dark:text-slate-300">{result.summary}</p>
        </Section>
      )}
    </div>
  )
}


function PublishExamModal({ quiz, onClose, onPublished }) {
  const { sessions, loading: loadingSessions } = useInstructorSessions()
  const toast = useToast()
  const [sessionId, setSessionId] = useState(quiz.session_id ? String(quiz.session_id) : '')
  const [timeLimitMins, setTimeLimitMins] = useState(quiz.time_limit_seconds ? String(Math.floor(quiz.time_limit_seconds / 60)) : '30')
  const [perQuestionSecs, setPerQuestionSecs] = useState(quiz.time_limit_per_question_seconds ? String(quiz.time_limit_per_question_seconds) : '')
  const [lockBackNavigation, setLockBackNavigation] = useState(quiz.lock_back_navigation ?? true)
  const [fullscreenLock, setFullscreenLock] = useState(quiz.fullscreen_lock ?? true)
  const [cameraMonitoring, setCameraMonitoring] = useState(quiz.camera_monitoring ?? false)
  const [dueDate, setDueDate] = useState(quiz.due_date ? quiz.due_date.substring(0, 16) : '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handlePublish(e) {
    e.preventDefault()
    if (!sessionId) {
      setError('Please select a target session to publish this exam to.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const payload = {
        session_id: Number(sessionId),
        time_limit_seconds: timeLimitMins ? Number(timeLimitMins) * 60 : null,
        time_limit_per_question_seconds: perQuestionSecs ? Number(perQuestionSecs) : null,
        lock_back_navigation: lockBackNavigation,
        fullscreen_lock: fullscreenLock,
        camera_monitoring: cameraMonitoring,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
      }
      const updated = await api(`/quizzes/${quiz.id}/publish-as-exam`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      toast.success('Exam published successfully! Enrolled students can now take it from their Exams tab.')
      onPublished(updated)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to publish exam')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900" style={{ animation: 'modalRise .25s ease-out' }}>
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
              <Shield size={18} />
            </div>
            <h2 className="text-lg font-bold">Publish as Exam</h2>
          </div>
          <button type="button" className="btn-soft p-1.5" onClick={onClose}><X size={18} /></button>
        </div>

        <form onSubmit={handlePublish} className="mt-4 space-y-4 text-sm">
          {error && <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">{error}</p>}

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Target Session *</label>
            <select className="input mt-1 w-full" value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
              <option value="">Select a session...</option>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>{s.title} ({s.date})</option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-slate-500">Only students enrolled in this session can take the exam.</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Overall Time Limit (mins)</label>
              <input type="number" min="1" max="300" className="input mt-1 w-full" value={timeLimitMins} onChange={(e) => setTimeLimitMins(e.target.value)} placeholder="e.g. 30" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Per-Question Time (sec)</label>
              <input type="number" min="5" max="600" className="input mt-1 w-full" value={perQuestionSecs} onChange={(e) => setPerQuestionSecs(e.target.value)} placeholder="Optional (e.g. 60)" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Exam Due Date & Time</label>
            <input type="datetime-local" className="input mt-1 w-full" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>

          <div className="space-y-2 rounded-2xl border border-slate-200/80 bg-slate-50/70 p-3.5 dark:border-slate-800 dark:bg-slate-800/40">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Security & Navigation Lockdown</p>

            <label className="flex items-start gap-2.5 cursor-pointer">
              <input type="checkbox" className="mt-0.5 rounded border-slate-300 text-ocean focus:ring-ocean" checked={lockBackNavigation} onChange={(e) => setLockBackNavigation(e.target.checked)} />
              <div>
                <span className="font-semibold text-xs flex items-center gap-1"><Lock size={12} /> Lock Back Navigation</span>
                <p className="text-[11px] text-slate-500">Answers are permanently locked once moved past. Student cannot go back to previous questions.</p>
              </div>
            </label>

            <label className="flex items-start gap-2.5 cursor-pointer">
              <input type="checkbox" className="mt-0.5 rounded border-slate-300 text-ocean focus:ring-ocean" checked={fullscreenLock} onChange={(e) => setFullscreenLock(e.target.checked)} />
              <div>
                <span className="font-semibold text-xs flex items-center gap-1"><Shield size={12} /> Fullscreen Lockdown</span>
                <p className="text-[11px] text-slate-500">Enforces fullscreen mode. Tab switches or exits trigger anti-cheat violations and lock attempts.</p>
              </div>
            </label>

            <label className="flex items-start gap-2.5 cursor-pointer">
              <input type="checkbox" className="mt-0.5 rounded border-slate-300 text-ocean focus:ring-ocean" checked={cameraMonitoring} onChange={(e) => setCameraMonitoring(e.target.checked)} />
              <div>
                <span className="font-semibold text-xs flex items-center gap-1"><Camera size={12} /> Camera Monitoring</span>
                <p className="text-[11px] text-slate-500">Prompts for anti-cheat webcam consent to detect presence and second screen activity.</p>
              </div>
            </label>
          </div>

          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={submitting} className="btn-primary flex-1 justify-center gap-2">
              {submitting ? <Loader2 size={16} className="animate-spin" /> : <Shield size={16} />}
              {submitting ? 'Publishing Exam...' : 'Confirm & Publish Exam'}
            </button>
            <button type="button" className="btn-soft" onClick={onClose} disabled={submitting}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function QuizResult({ result, answers, revealed, onAnswer, onReveal, onPublishExam }) {
  const { t } = useLanguage()
  const slug = (result.title || 'quiz').replace(/\s+/g, '-').toLowerCase()
  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.title} subtitle={result.difficulty} sources={result.sources} unverified={result.unverified} />
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
        <DownloadBar
          items={[
            { label: 'Word (.doc)', onClick: () => downloadQuizAsDoc(result, `${slug}.doc`) },
            { label: 'PDF Document (.pdf)', onClick: () => downloadQuizAsPdf(result, slug) },
            { label: 'HTML (.html)', onClick: () => downloadQuizAsHtml(result, `${slug}.html`) },
          ]}
        />
        {result.id && (
          <button
            type="button"
            onClick={() => onPublishExam?.(result)}
            className="btn-primary gap-1.5 text-xs py-1.5 px-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white"
          >
            <Shield size={14} />
            {result.is_exam ? 'Update Exam Settings' : 'Publish as Exam'}
          </button>
        )}
      </div>
      <div className="space-y-4">
        {result.questions?.map((question, index) => {
          const selected = answers[index]
          const show = revealed[index]
          const correct = selected === question.answer
          return (
            <article key={`${question.question}-${index}`} className="rounded-md bg-slate-100 p-4 dark:bg-slate-800">
              <p className="font-semibold">{index + 1}. {question.question}</p>
              {question.options ? (
                <div className="mt-3 space-y-2">
                  {question.options.map((option) => (
                    <label key={option} className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900">
                      <input
                        type="radio"
                        name={`question-${index}`}
                        checked={selected === option.slice(0, 1) || selected === option}
                        onChange={() => onAnswer({ ...answers, [index]: option.slice(0, 1) })}
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <input
                  className="input mt-3"
                  placeholder={t('ai.typeAnswer')}
                  value={selected || ''}
                  onChange={(e) => onAnswer({ ...answers, [index]: e.target.value })}
                />
              )}
              <div className="mt-3 flex items-center gap-3">
                <button type="button" className="btn-soft" onClick={() => onReveal({ ...revealed, [index]: true })}>{t('ai.checkAnswer')}</button>
                {show && (
                  <p className={`text-sm ${correct ? 'text-emerald-600' : 'text-red-600'}`}>
                    {correct ? t('ai.correct') : `${t('ai.answer')}: ${question.answer}`}
                    {question.explanation ? ` — ${question.explanation}` : ''}
                  </p>
                )}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}

function VideoResult({ result, initialForm, onReplace, onHistoryRefresh }) {
  const { t } = useLanguage()
  const { startJob, job: editJob, removeJob } = useGenerationJobs('video-edit')
  const playerUrl = result.video_url ? staticUrl(result.video_url) : null
  const mp4Url = result.mp4_url ? staticUrl(result.mp4_url) : null
  const [editForm, setEditForm] = useState({
    title: initialForm.title,
    prompt: initialForm.prompt,
    language: initialForm.language,
    style: initialForm.style,
    duration: initialForm.duration,
    notes: initialForm.notes,
    session_id: initialForm.session_id || '',
    source_session_id: initialForm.source_session_id || '',
  })
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    if (editJob?.status === 'done' && editJob.result) {
      onReplace(editJob.result)
      onHistoryRefresh?.()
      removeJob(editJob.jobId)
      setEditing(false)
    }
    if (editJob?.status === 'error') {
      setEditing(false)
    }
  }, [editJob])

  async function downloadStatic(url, filename) {
    const response = await fetch(url)
    downloadBlob(await response.blob(), filename)
  }

  async function editVideo(e) {
    e.preventDefault()
    setEditing(true)
    try {
      await startJob({
        type: 'video-edit',
        endpoint: `/ai/videos/${result.id}/edit/queue`,
        payload: buildAiPayload(editForm),
        label: editForm.title,
      })
    } catch {
      setEditing(false)
    }
  }

  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.title || t('ai.videoReady')} subtitle={result.status} />
      <DownloadBar
        items={[
          ...(mp4Url ? [{ label: t('ai.downloadMp4'), onClick: () => downloadStatic(mp4Url, `${(result.lesson?.topic || result.id || 'video').toString().replace(/\s+/g, '-').toLowerCase()}.mp4`) }] : []),
        ]}
      />
      {result.fallback && (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          MP4 export depends on FFmpeg being available on the backend. The interactive player remains available even when a full MP4 is not generated.
        </p>
      )}
      {playerUrl && (
        <Section title={t('ai.player')}>
          <iframe title="Lesson video player" src={playerUrl} className="h-[min(420px,60vh)] w-full rounded-md border border-slate-200 dark:border-slate-700" />
          <a className="btn-soft mt-3 inline-flex" href={playerUrl} target="_blank" rel="noreferrer">{t('ai.openPlayer')}</a>
        </Section>
      )}
      {mp4Url && (
        <Section title={t('ai.downloadMp4')}>
          <video controls className="w-full rounded-md" src={mp4Url} />
        </Section>
      )}
      <Section title="Edit Video Prompt">
        <form className="grid gap-4 md:grid-cols-2" onSubmit={editVideo}>
          <Field label="Title" value={editForm.title} onChange={(value) => setEditForm({ ...editForm, title: value })} />
          <Field label="Prompt" value={editForm.prompt} onChange={(value) => setEditForm({ ...editForm, prompt: value })} />
          <SelectField label="Language" value={editForm.language} options={languages} onChange={(value) => setEditForm({ ...editForm, language: value })} />
          <SelectField label="Style" value={editForm.style} options={styles} onChange={(value) => setEditForm({ ...editForm, style: value })} />
          <Field label="Duration" type="number" value={editForm.duration} onChange={(value) => setEditForm({ ...editForm, duration: Number(value) || 5 })} />
          <Field label="Edit prompt" value={editForm.notes || ''} onChange={(value) => setEditForm({ ...editForm, notes: value })} textarea />
          <SessionPickerFields form={editForm} setForm={setEditForm} />
          <button type="submit" className="btn-primary md:col-span-2">{editing ? 'Updating video in background...' : 'Apply prompt edit'}</button>
        </form>
      </Section>
      {result.scenes?.length > 0 && (
        <Section title={t('ai.scenes')}>
          <div className="grid gap-3 md:grid-cols-2">
            {result.scenes.map((scene) => (
              <article key={scene.title} className="rounded-md bg-slate-100 p-4 dark:bg-slate-800">
                <div className="flex items-center gap-2 font-bold"><Volume2 size={16} />{scene.title}</div>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{scene.narration}</p>
              </article>
            ))}
          </div>
        </Section>
      )}
      {result.lesson?.summary && (
        <Section title={t('ai.lessonSummary')}>
          <p className="text-sm text-slate-700 dark:text-slate-300">{result.lesson.summary}</p>
        </Section>
      )}
    </div>
  )
}

function FlashcardResult({ result, request, flipped, onFlip }) {
  const { t } = useLanguage()
  const slug = (result.title || 'flashcards').replace(/\s+/g, '-').toLowerCase()
  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.title} subtitle={`${result.cards?.length || 0} cards · ${result.language}`} model={request?.model} sources={result.sources} unverified={result.unverified} />
      <DownloadBar
        items={[
          {
            label: 'Word (.doc)',
            onClick: () => downloadFlashcardsAsDoc(result, `${slug}.doc`),
          },
          {
            label: 'PDF Document (.pdf)',
            onClick: () => downloadFlashcardsAsPdf(result, slug),
          },
          { label: t('ai.downloadHtml'), onClick: () => downloadText(flashcardsToHtml(result), `${slug}.html`, 'text/html') },
        ]}
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {result.cards?.map((card, index) => (
          <button
            key={`${card.front}-${index}`}
            type="button"
            className="min-h-40 rounded-xl border border-slate-200 bg-gradient-to-br from-white to-teal-50 p-4 text-start shadow-sm transition hover:-translate-y-1 hover:shadow-md dark:border-slate-700 dark:from-slate-900 dark:to-slate-800"
            onClick={() => onFlip({ ...flipped, [index]: !flipped[index] })}
          >
            <p className="text-xs uppercase tracking-wide text-slate-500">{flipped[index] ? t('ai.back') : t('ai.front')}</p>
            <p className="mt-3 text-sm font-semibold leading-6">{flipped[index] ? card.back : card.front}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

function DownloadBar({ items }) {
  if (!items.length) return null
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <button key={item.label} type="button" className="btn-download" onClick={item.onClick}>
          <Download size={16} />{item.label}
        </button>
      ))}
    </div>
  )
}

function ResultHeader({ title, subtitle, model, sources, unverified }) {
  const hasSources = Array.isArray(sources) && sources.length > 0
  const isUnverified = unverified === true

  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-lg font-bold">{title}</p>
        <p className="text-sm text-slate-500">{subtitle}</p>
        {model && (
          <span className="mt-1 inline-block rounded-full bg-teal-50 px-2.5 py-0.5 text-xs font-semibold text-ocean dark:bg-slate-800 dark:text-mint">
            ⚡ {model}
          </span>
        )}
        <div className="mt-2 flex items-center gap-2">
          {hasSources && !isUnverified && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
              <ShieldCheck size={12} /> RAG Verified
            </span>
          )}
          {isUnverified && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
              <AlertTriangle size={12} /> Unverified
            </span>
          )}
        </div>
      </div>
      <CheckCircle2 className="text-emerald-500 shrink-0" size={20} />
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </section>
  )
}

export function ChatbotGenerator() {
  const { t } = useLanguage()
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hello! I'm your EduSense AI assistant. Ask me anything about your course materials, or I can search the web for current information." }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [subject, setSubject] = useState('')
  const [gradeLevel, setGradeLevel] = useState('')
  const messagesEndRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const modeLabels = {
    'online_rag_web_llm': { label: 'RAG + Web + LLM', icon: <Zap className="w-3 h-3" />, color: 'bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300' },
    'online_rag_only': { label: 'RAG Only (Web Failed)', icon: <Database className="w-3 h-3" />, color: 'bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300' },
    'offline_rag_template': { label: 'RAG + Template (Offline)', icon: <Bot className="w-3 h-3" />, color: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' },
    'offline_template_only': { label: 'Template Only (Offline)', icon: <Bot className="w-3 h-3" />, color: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300' },
  }

  async function sendMessage() {
    if (!input.trim() || loading) return
    const userMessage = input.trim()
    setInput('')
    setLoading(true)
    setError('')

    // Add user message immediately
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])

    try {
      const response = await api('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage,
          conversation_history: messages.slice(-6).map(m => ({ role: m.role, content: m.content })),
          subject: subject || undefined,
          grade_level: gradeLevel || undefined,
        })
      })

      // Add assistant response with metadata
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.answer,
        metadata: {
          sources: response.sources,
          web_sources: response.web_sources,
          mode: response.mode,
          rag_chunks_used: response.rag_chunks_used,
          web_results_used: response.web_results_used,
        }
      }])
    } catch (err) {
      setError(err.message || 'Failed to get response')
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
      }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
      <div className="space-y-6">
        <ToolShell title={t('ai.chatbot') || 'AI Chatbot'} icon={<Bot />} onSubmit={sendMessage} loading={loading} error={error}>
          <div className="rounded-xl border border-teal-200 bg-teal-50/60 p-3 text-xs text-teal-900 dark:border-teal-900/40 dark:bg-teal-950/20 dark:text-teal-200">
            <p className="font-semibold flex items-center gap-1.5"><Bot size={14} /> Multi-Source Teaching Assistant</p>
            <p className="mt-0.5 text-slate-600 dark:text-slate-300">
              Unlike the static Document Repository in Knowledge Base, this assistant dynamically queries your indexed materials, falls back to live web search, and uses Gemini to synthesize lesson ideas, answer student doubts, or explain complex concepts.
            </p>
          </div>
          <div className="space-y-4">
            {/* Chat Messages */}
            <div className="h-[500px] overflow-y-auto space-y-4 p-4 rounded-xl border border-slate-200 bg-white/50 dark:border-slate-700 dark:bg-slate-900/50">
              {messages.map((msg, idx) => (
                <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                  <div className={`max-w-[75%] ${msg.role === 'user' ? 'order-2' : ''}`}>
                    <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-ocean text-white rounded-br-none'
                        : 'bg-slate-100 dark:bg-slate-800 rounded-bl-none'
                    }`}>
                      {msg.content}
                    </div>
                    {msg.metadata && (
                      <div className="mt-2 flex items-center gap-2 text-xs">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${modeLabels[msg.metadata.mode]?.color || 'bg-slate-100 text-slate-700'}`}>
                          {modeLabels[msg.metadata.mode]?.icon || <Bot size={10} />}
                          {modeLabels[msg.metadata.mode]?.label || msg.metadata.mode}
                        </span>
                        {msg.metadata.rag_chunks_used > 0 && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                            <Database size={10} /> {msg.metadata.rag_chunks_used} RAG
                          </span>
                        )}
                        {msg.metadata.web_results_used > 0 && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
                            <Globe size={10} /> {msg.metadata.web_results_used} Web
                          </span>
                        )}
                      </div>
                    )}
                    {msg.metadata && (msg.metadata.sources?.length > 0 || msg.metadata.web_sources?.length > 0) && (
                      <details className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                        <summary className="cursor-pointer select-none">Sources</summary>
                        <div className="mt-1 space-y-1">
                          {msg.metadata.sources?.map((s, i) => (
                            <div key={i} className="font-mono">{s}</div>
                          ))}
                          {msg.metadata.web_sources?.map((w, i) => (
                            <div key={i} className="font-mono">
                              <a href={w.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-ocean">{w.title}</a>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                    msg.role === 'user' ? 'bg-ocean/20 text-ocean' : 'bg-teal-100 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300'
                  }`}>
                    {msg.role === 'user' ? 'U' : 'AI'}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="space-y-3">
              <div className="grid gap-2 md:grid-cols-3">
                <Field label="Subject (optional)" value={subject} onChange={(v) => setSubject(v)} placeholder="e.g., Computer Science" />
                <Field label="Grade Level (optional)" value={gradeLevel} onChange={(v) => setGradeLevel(v)} placeholder="e.g., 12, University" />
              </div>
              <div className="flex gap-2">
                <textarea
                  className="input flex-1 min-h-[80px] max-h-[200px] resize-none"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask me anything about your courses..."
                  disabled={loading}
                  rows={3}
                />
                <button
                  type="button"
                  className="btn-primary self-end px-6"
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                >
                  {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send size={20} />}
                </button>
              </div>
            </div>
          </div>
        </ToolShell>
      </div>

      <div className="panel space-y-4">
        <h2 className="text-lg font-bold">How It Works</h2>
        <div className="space-y-3 text-sm text-slate-600 dark:text-slate-400">
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
            <p className="font-semibold flex items-center gap-2"><Zap className="w-4 h-4" /> Online Mode</p>
            <p className="mt-1">RAG + Web Search + LLM (Gemini/Ollama) for comprehensive answers with citations.</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
            <p className="font-semibold flex items-center gap-2"><Database className="w-4 h-4" /> RAG Only</p>
            <p className="mt-1">If web search fails, uses knowledge base + LLM.</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
            <p className="font-semibold flex items-center gap-2"><Bot className="w-4 h-4" /> Offline Mode</p>
            <p className="mt-1">RAG + Template fallback when LLM unavailable.</p>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
            <p className="font-semibold flex items-center gap-2"><Bot className="w-4 h-4" /> Template Only</p>
            <p className="mt-1">Final fallback using local templates only.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
