import { useEffect, useState, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { CheckCircle2, Clock3, Download, FileQuestion, Layers, Sparkles, Trash2, Video, Volume2, ShieldCheck, AlertTriangle, Send, Bot, Loader2, Zap, Globe, Database, Shield, Lock, Camera, X, Edit3, Plus, Eye, EyeOff, Mic, MicOff, MessageCircle, Paperclip, RotateCcw, Square } from 'lucide-react'
import MarkdownText from '../utils/markdown'
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

/** Parse structured backend job errors ({code, stage, message}) into readable text. */
function formatJobError(raw) {
  if (!raw) return 'Generation failed'
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && parsed.message) {
      const stage = parsed.stage ? ` [${parsed.stage}]` : ''
      return `${parsed.message}${stage}`
    }
  } catch {
    // not JSON — plain error string
  }
  return raw
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
      setError(formatJobError(job.error))
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

  async function deleteHistory(id, e) {
    e.stopPropagation()
    try {
      await api('/ai/quizzes/' + id, { method: 'DELETE' })
      await loadHistory()
      if (result && result.id === id) setResult(null)
    } catch { /* ignore */ }
  }

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

  const [creationMode, setCreationMode] = useState('ai') // 'ai' or 'manual'
  const toast = useToast()
  const [manualSubmitting, setManualSubmitting] = useState(false)
  const [manualError, setManualError] = useState('')
  const [manualForm, setManualForm] = useState({
    title: '',
    difficulty: 'Medium',
    session_id: '',
    is_exam: false,
    time_limit_mins: '30',
    per_question_secs: '',
    lock_back_navigation: false,
    fullscreen_lock: false,
    camera_monitoring: false,
    due_date: '',
    questions: [
      {
        question: '',
        type: 'multiple_choice',
        options: ['Option A', 'Option B', 'Option C', 'Option D'],
        answer: 'Option A',
        explanation: '',
      },
    ],
  })

  function addQuestion() {
    setManualForm((prev) => ({
      ...prev,
      questions: [
        ...prev.questions,
        {
          question: '',
          type: 'multiple_choice',
          options: ['Option A', 'Option B', 'Option C', 'Option D'],
          answer: 'Option A',
          explanation: '',
        },
      ],
    }))
  }

  function removeQuestion(qIdx) {
    if (manualForm.questions.length <= 1) {
      setManualError('Quiz must contain at least one question.')
      return
    }
    setManualForm((prev) => ({
      ...prev,
      questions: prev.questions.filter((_, i) => i !== qIdx),
    }))
  }

  function updateQuestion(qIdx, patch) {
    setManualForm((prev) => {
      const nextQ = [...prev.questions]
      nextQ[qIdx] = { ...nextQ[qIdx], ...patch }
      return { ...prev, questions: nextQ }
    })
  }

  function addOption(qIdx) {
    const q = manualForm.questions[qIdx]
    const nextChar = String.fromCharCode(65 + q.options.length)
    updateQuestion(qIdx, { options: [...q.options, `Option ${nextChar}`] })
  }

  function removeOption(qIdx, optIdx) {
    const q = manualForm.questions[qIdx]
    if (q.options.length <= 2) return
    const removedOpt = q.options[optIdx]
    const newOptions = q.options.filter((_, i) => i !== optIdx)
    const newAnswer = q.answer === removedOpt ? newOptions[0] : q.answer
    updateQuestion(qIdx, { options: newOptions, answer: newAnswer })
  }

  async function submitManualQuiz(e) {
    e.preventDefault()
    if (!manualForm.title.trim()) {
      setManualError('Please provide a quiz title.')
      return
    }
    for (let i = 0; i < manualForm.questions.length; i++) {
      const q = manualForm.questions[i]
      if (!q.question.trim()) {
        setManualError(`Question ${i + 1} is missing question text.`)
        return
      }
      if (!q.answer.trim()) {
        setManualError(`Question ${i + 1} is missing a designated correct answer.`)
        return
      }
    }
    setManualError('')
    setManualSubmitting(true)
    try {
      let formattedDueDate = null
      if (manualForm.due_date && manualForm.due_date.trim()) {
        try {
          const d = new Date(manualForm.due_date)
          if (!isNaN(d.getTime())) formattedDueDate = d.toISOString()
        } catch (_) {}
      }

      const payload = {
        title: manualForm.title.trim(),
        difficulty: manualForm.difficulty,
        session_id: manualForm.session_id ? Number(manualForm.session_id) : null,
        is_exam: manualForm.is_exam,
        is_published: true,
        time_limit_seconds: manualForm.time_limit_mins ? Number(manualForm.time_limit_mins) * 60 : null,
        time_limit_per_question_seconds: manualForm.per_question_secs ? Number(manualForm.per_question_secs) : null,
        lock_back_navigation: manualForm.lock_back_navigation,
        fullscreen_lock: manualForm.fullscreen_lock,
        camera_monitoring: manualForm.camera_monitoring,
        due_date: formattedDueDate,
        questions: manualForm.questions.map((q) => ({
          question: q.question.trim(),
          type: q.type,
          options: q.type === 'multiple_choice' ? q.options.filter(Boolean) : (q.type === 'true_false' ? ['True', 'False'] : []),
          answer: q.answer.trim(),
          explanation: q.explanation?.trim() || '',
        })),
      }
      const created = await api('/quizzes', {
        method: 'POST',
        body: payload,
      })
      toast.success(manualForm.is_exam ? 'Manual Exam created & published successfully!' : 'Manual Quiz created successfully!')
      setResult(created)
      setAnswers({})
      setRevealed({})
      await loadHistory()
    } catch (err) {
      setManualError(err.message || 'Failed to create quiz.')
    } finally {
      setManualSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
      <div className="space-y-6">
        {/* Creation Mode Switcher: AI vs Manual */}
        <div className="flex items-center gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800 w-fit">
          <button
            type="button"
            onClick={() => setCreationMode('ai')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition ${creationMode === 'ai' ? 'bg-white text-ocean shadow-sm dark:bg-slate-700 dark:text-white' : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'}`}
          >
            <Sparkles size={14} /> AI Generation
          </button>
          <button
            type="button"
            onClick={() => setCreationMode('manual')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition ${creationMode === 'manual' ? 'bg-white text-ocean shadow-sm dark:bg-slate-700 dark:text-white' : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'}`}
          >
            <Edit3 size={14} /> Manual Authoring
          </button>
        </div>

        {creationMode === 'ai' ? (
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
        ) : (
          <div className="panel space-y-5">
            <div className="flex items-center gap-3 border-b border-slate-100 pb-4 dark:border-slate-800">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400">
                <Edit3 size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold">Manual Quiz & Exam Builder</h2>
                <p className="text-xs text-slate-500">Author custom questions, designate answers, and deploy with timer & anti-cheat locks.</p>
              </div>
            </div>

            <form onSubmit={submitManualQuiz} className="space-y-5 text-sm">
              {manualError && (
                <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
                  {manualError}
                </p>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Quiz Title *</label>
                  <input
                    type="text"
                    className="input mt-1 w-full"
                    value={manualForm.title}
                    onChange={(e) => setManualForm({ ...manualForm, title: e.target.value })}
                    placeholder="e.g. Calculus Midterm Examination"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Difficulty</label>
                  <select
                    className="input mt-1 w-full"
                    value={manualForm.difficulty}
                    onChange={(e) => setManualForm({ ...manualForm, difficulty: e.target.value })}
                  >
                    {difficulties.map((d) => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div className="md:col-span-2">
                  <SessionPickerFields form={manualForm} setForm={setManualForm} showSourceSession={false} />
                </div>
              </div>

              {/* Direct Exam Lockdown Settings */}
              <div className="space-y-3 rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-800/40">
                <label className="flex items-center gap-2 cursor-pointer font-bold text-xs uppercase tracking-wider text-purple-700 dark:text-purple-400">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300 text-purple-600 focus:ring-purple-600"
                    checked={manualForm.is_exam}
                    onChange={(e) => setManualForm((prev) => ({
                      ...prev,
                      is_exam: e.target.checked,
                      ...(e.target.checked ? { fullscreen_lock: true } : {}),
                    }))}
                  />
                  <span>Publish Directly as Exam (With Anti-Cheat & Timers)</span>
                </label>

                {manualForm.is_exam && (
                  <div className="space-y-3 pt-2">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Overall Time Limit (mins)</label>
                        <input
                          type="number"
                          min="1"
                          max="300"
                          className="input mt-1 w-full"
                          value={manualForm.time_limit_mins}
                          onChange={(e) => setManualForm({ ...manualForm, time_limit_mins: e.target.value })}
                          placeholder="e.g. 45"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Per-Question Time (sec)</label>
                        <input
                          type="number"
                          min="5"
                          max="600"
                          className="input mt-1 w-full"
                          value={manualForm.per_question_secs}
                          onChange={(e) => setManualForm({ ...manualForm, per_question_secs: e.target.value })}
                          placeholder="Optional (e.g. 60)"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">Exam Due Date & Time</label>
                      <input
                        type="datetime-local"
                        className="input mt-1 w-full"
                        value={manualForm.due_date}
                        onChange={(e) => setManualForm({ ...manualForm, due_date: e.target.value })}
                      />
                    </div>

                    <div className="grid gap-2 sm:grid-cols-3">
                      <label className="flex items-center gap-2 text-xs cursor-pointer">
                        <input
                          type="checkbox"
                          className="rounded border-slate-300 text-purple-600"
                          checked={manualForm.lock_back_navigation}
                          onChange={(e) => setManualForm({ ...manualForm, lock_back_navigation: e.target.checked })}
                        />
                        <span className="font-semibold flex items-center gap-1"><Lock size={12} /> Lock Back Nav</span>
                      </label>
                      <label className="flex items-center gap-2 text-xs cursor-pointer">
                        <input
                          type="checkbox"
                          className="rounded border-slate-300 text-purple-600"
                          checked={manualForm.fullscreen_lock}
                          onChange={(e) => setManualForm({ ...manualForm, fullscreen_lock: e.target.checked })}
                        />
                        <span className="font-semibold flex items-center gap-1"><Shield size={12} /> Fullscreen</span>
                      </label>
                      <label className="flex items-center gap-2 text-xs cursor-pointer">
                        <input
                          type="checkbox"
                          className="rounded border-slate-300 text-purple-600"
                          checked={manualForm.camera_monitoring}
                          onChange={(e) => setManualForm({ ...manualForm, camera_monitoring: e.target.checked })}
                        />
                        <span className="font-semibold flex items-center gap-1"><Camera size={12} /> Camera Lock</span>
                      </label>
                    </div>
                  </div>
                )}
              </div>

              {/* Questions List */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
                    Questions ({manualForm.questions.length})
                  </h3>
                  <button
                    type="button"
                    onClick={addQuestion}
                    className="btn-soft text-xs py-1.5 px-3 flex items-center gap-1 text-ocean font-semibold"
                  >
                    <Plus size={14} /> Add Question
                  </button>
                </div>

                {manualForm.questions.map((q, qIdx) => (
                  <div key={qIdx} className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3 dark:border-slate-800 dark:bg-slate-900/60">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                        Question {qIdx + 1}
                      </span>
                      {manualForm.questions.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeQuestion(qIdx)}
                          className="text-slate-400 hover:text-red-500 transition p-1"
                          title="Remove question"
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>

                    <div>
                      <input
                        type="text"
                        className="input w-full font-medium"
                        placeholder="Type question text..."
                        value={q.question}
                        onChange={(e) => updateQuestion(qIdx, { question: e.target.value })}
                        required
                      />
                    </div>

                    <div className="flex items-center gap-4 text-xs font-semibold">
                      <span className="text-slate-500">Type:</span>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="radio"
                          name={`qtype-${qIdx}`}
                          checked={q.type === 'multiple_choice'}
                          onChange={() => updateQuestion(qIdx, {
                            type: 'multiple_choice',
                            options: q.options?.length >= 2 ? q.options : ['Option A', 'Option B', 'Option C', 'Option D'],
                            answer: q.options?.[0] || 'Option A',
                          })}
                        />
                        <span>Multiple Choice</span>
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="radio"
                          name={`qtype-${qIdx}`}
                          checked={q.type === 'true_false'}
                          onChange={() => updateQuestion(qIdx, {
                            type: 'true_false',
                            options: ['True', 'False'],
                            answer: 'True',
                          })}
                        />
                        <span>True / False</span>
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="radio"
                          name={`qtype-${qIdx}`}
                          checked={q.type === 'short_answer'}
                          onChange={() => updateQuestion(qIdx, {
                            type: 'short_answer',
                            options: [],
                            answer: '',
                          })}
                        />
                        <span>Short Answer</span>
                      </label>
                    </div>

                    {/* Question Content based on type */}
                    {q.type === 'multiple_choice' && (
                      <div className="space-y-2 pt-1">
                        <p className="text-[11px] font-semibold text-slate-500">
                          Options (Select the radio button next to the correct answer):
                        </p>
                        {q.options.map((opt, optIdx) => (
                          <div key={optIdx} className="flex items-center gap-2">
                            <input
                              type="radio"
                              name={`correct-ans-${qIdx}`}
                              checked={q.answer === opt}
                              onChange={() => updateQuestion(qIdx, { answer: opt })}
                              title="Mark as correct answer"
                            />
                            <input
                              type="text"
                              className="input flex-1 py-1.5 text-xs"
                              value={opt}
                              onChange={(e) => {
                                const newOpts = [...q.options]
                                const wasAnswer = q.answer === opt
                                newOpts[optIdx] = e.target.value
                                updateQuestion(qIdx, {
                                  options: newOpts,
                                  answer: wasAnswer ? e.target.value : q.answer,
                                })
                              }}
                              placeholder={`Option ${optIdx + 1}`}
                              required
                            />
                            {q.options.length > 2 && (
                              <button
                                type="button"
                                onClick={() => removeOption(qIdx, optIdx)}
                                className="text-slate-400 hover:text-red-500 p-1"
                              >
                                <X size={14} />
                              </button>
                            )}
                          </div>
                        ))}
                        {q.options.length < 6 && (
                          <button
                            type="button"
                            onClick={() => addOption(qIdx)}
                            className="text-xs text-ocean hover:underline font-semibold flex items-center gap-1 mt-1"
                          >
                            <Plus size={12} /> Add Option
                          </button>
                        )}
                      </div>
                    )}

                    {q.type === 'true_false' && (
                      <div className="flex items-center gap-4 pt-1 text-xs">
                        <span className="font-semibold text-slate-500">Correct Answer:</span>
                        <label className="flex items-center gap-1 cursor-pointer">
                          <input
                            type="radio"
                            name={`tf-ans-${qIdx}`}
                            checked={q.answer === 'True'}
                            onChange={() => updateQuestion(qIdx, { answer: 'True' })}
                          />
                          <span>True</span>
                        </label>
                        <label className="flex items-center gap-1 cursor-pointer">
                          <input
                            type="radio"
                            name={`tf-ans-${qIdx}`}
                            checked={q.answer === 'False'}
                            onChange={() => updateQuestion(qIdx, { answer: 'False' })}
                          />
                          <span>False</span>
                        </label>
                      </div>
                    )}

                    {q.type === 'short_answer' && (
                      <div className="pt-1">
                        <label className="block text-[11px] font-semibold text-slate-500">Expected Correct Answer *</label>
                        <input
                          type="text"
                          className="input mt-1 w-full text-xs"
                          placeholder="e.g. 1 / Photosynthesis / Isaac Newton"
                          value={q.answer}
                          onChange={(e) => updateQuestion(qIdx, { answer: e.target.value })}
                          required
                        />
                      </div>
                    )}

                    <div>
                      <input
                        type="text"
                        className="input w-full text-xs text-slate-500"
                        placeholder="Explanation or rationale for the answer (optional)"
                        value={q.explanation || ''}
                        onChange={(e) => updateQuestion(qIdx, { explanation: e.target.value })}
                      />
                    </div>
                  </div>
                ))}

                <button
                  type="button"
                  onClick={addQuestion}
                  className="btn-soft w-full justify-center py-2 text-xs font-semibold flex items-center gap-1.5"
                >
                  <Plus size={14} /> Add Another Question
                </button>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={manualSubmitting}
                  className="btn-primary w-full justify-center py-2.5 text-sm font-bold flex items-center gap-2"
                >
                  {manualSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Shield size={16} />}
                  {manualSubmitting ? 'Saving Quiz...' : (manualForm.is_exam ? 'Save & Deploy Exam' : 'Save & Publish Quiz')}
                </button>
              </div>
            </form>
          </div>
        )}

        {result && (
          <QuizResult
            result={result}
            answers={answers}
            revealed={revealed}
            onAnswer={setAnswers}
            onReveal={setRevealed}
            onPublishExam={setPublishModalQuiz}
          />
        )}
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
  const lesson = (result?.data && !result?.topic ? result.data : result) || {}
  const language = lesson?.language || request?.language || ''
  const style = lesson?.style || request?.teaching_style || ''
  const duration = lesson?.duration ?? request?.duration
  const subtitle = [language, style, duration != null ? `${duration} min` : null].filter(Boolean).join(' · ')
  const slug = (lesson?.topic || 'lesson').replace(/\s+/g, '-').toLowerCase()
  return (
    <div className="space-y-5 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={lesson?.topic} subtitle={subtitle || undefined} model={request?.model} sources={lesson?.sources} unverified={lesson?.unverified} />
      <DownloadBar
        items={[
          {
            label: 'Word (.doc)',
            onClick: () => downloadLessonAsDoc(lesson, `${slug}.doc`),
          },
          {
            label: 'PowerPoint (.pptx)',
            onClick: () => downloadLessonAsPptxHtml(lesson, `${slug}.pptx.html`),
          },
          {
            label: 'PDF Document (.pdf)',
            onClick: () => downloadLessonAsPdf(lesson, slug),
          },
          {
            label: 'HTML (.html)',
            onClick: () => downloadLessonAsHtml(lesson, `${slug}.html`),
          },
          {
            label: 'Markdown (.md)',
            onClick: () => downloadText(lessonToMarkdown(lesson), `${slug}.md`, 'text/markdown'),
          },
        ]}
      />
      {lesson.overview && (
        <Section title={t('ai.overview')}>
          <p className="text-sm leading-7 text-slate-700 dark:text-slate-300">{lesson.overview}</p>
        </Section>
      )}
      <Section title={t('ai.objectives')}>
        <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
          {lesson.learning_objectives?.map((objective) => <li key={objective}>• {objective}</li>)}
        </ul>
      </Section>
      {lesson.sections?.length > 0 && (
        <Section title={t('ai.sections')}>
          <div className="grid gap-3">
            {lesson.sections.map((section) => (
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
          {lesson.slides?.map((slide) => (
            <article key={slide.title} className="rounded-md bg-slate-100 p-4 dark:bg-slate-800">
              <p className="font-bold">{slide.title}</p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{slide.content}</p>
              {slide.diagram && <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">{slide.diagram}</p>}
            </article>
          ))}
        </div>
      </Section>
      {lesson.key_points?.length > 0 && (
        <Section title={t('ai.keyPoints')}>
          <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            {lesson.key_points.map((point) => <li key={point}>• {point}</li>)}
          </ul>
        </Section>
      )}
      {lesson.summary && (
        <Section title={t('ai.summary')}>
          <p className="text-sm leading-7 text-slate-700 dark:text-slate-300">{lesson.summary}</p>
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
  const [fullscreenLock, setFullscreenLock] = useState(quiz.is_exam ? (quiz.fullscreen_lock ?? true) : true)
  const [cameraMonitoring, setCameraMonitoring] = useState(quiz.camera_monitoring ?? false)
  const [dueDate, setDueDate] = useState(() => {
    if (!quiz.due_date) return ''
    try {
      return new Date(quiz.due_date).toISOString().substring(0, 16)
    } catch (_) {
      return String(quiz.due_date).substring(0, 16)
    }
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handlePublish(e) {
    e.preventDefault()
    if (!sessionId && !quiz.session_id) {
      setError('Please select a target session for this exam.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      let formattedDueDate = null
      if (dueDate && dueDate.trim()) {
        try {
          const parsed = new Date(dueDate)
          if (!isNaN(parsed.getTime())) {
            formattedDueDate = parsed.toISOString()
          }
        } catch (_) {}
      }

      const payload = {
        session_id: sessionId ? Number(sessionId) : (quiz.session_id || null),
        time_limit_seconds: timeLimitMins ? Number(timeLimitMins) * 60 : null,
        time_limit_per_question_seconds: perQuestionSecs ? Number(perQuestionSecs) : null,
        lock_back_navigation: lockBackNavigation,
        fullscreen_lock: fullscreenLock,
        camera_monitoring: cameraMonitoring,
        due_date: formattedDueDate,
        is_published: true,
      }
      const updated = await api(`/quizzes/${quiz.id}/publish-as-exam`, {
        method: 'POST',
        body: payload,
      })
      toast.success(quiz.is_exam ? 'Exam settings updated successfully!' : 'Exam published successfully! Enrolled students can now take it from their Exams tab.')
      onPublished(updated)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to save exam settings')
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
            <h2 className="text-lg font-bold">{quiz.is_exam ? 'Update Exam Settings' : 'Publish as Exam'}</h2>
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
              {submitting ? (quiz.is_exam ? 'Saving Changes...' : 'Publishing Exam...') : (quiz.is_exam ? 'Save Settings Changes' : 'Confirm & Publish Exam')}
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
  const allRevealed = result.questions?.length > 0 && result.questions?.every((_, i) => revealed[i])

  const toggleAllAnswers = () => {
    const nextState = !allRevealed
    const updated = {}
    result.questions?.forEach((_, i) => {
      updated[i] = nextState
    })
    onReveal(updated)
  }

  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.title} subtitle={result.difficulty} sources={result.sources} unverified={result.unverified} />
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
        <div className="flex flex-wrap items-center gap-2">
          <DownloadBar
            items={[
              { label: 'Word (.doc)', onClick: () => downloadQuizAsDoc(result, `${slug}.doc`) },
              { label: 'PDF Document (.pdf)', onClick: () => downloadQuizAsPdf(result, slug) },
              { label: 'HTML (.html)', onClick: () => downloadQuizAsHtml(result, `${slug}.html`) },
            ]}
          />
          {result.questions?.length > 0 && (
            <button
              type="button"
              onClick={toggleAllAnswers}
              className="btn-soft text-xs py-1.5 px-3 flex items-center gap-1.5"
              title="Toggle correct answers visibility for all questions"
            >
              {allRevealed ? <EyeOff size={14} /> : <Eye size={14} />}
              {allRevealed ? 'Hide All Answers' : 'Show All Answers'}
            </button>
          )}
        </div>
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
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="btn-soft text-xs py-1.5 px-3"
                  onClick={() => onReveal({ ...revealed, [index]: !show })}
                >
                  {show ? 'Hide Answer' : t('ai.checkAnswer')}
                </button>
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
  const [playerReloadToken, setPlayerReloadToken] = useState(() => String(Date.now()))
  const basePlayerUrl = result.video_url ? staticUrl(result.video_url) : null
  const playerUrl = basePlayerUrl
    ? `${basePlayerUrl}${basePlayerUrl.includes('?') ? '&' : '?'}v=${playerReloadToken}`
    : null
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
  const [scenes, setScenes] = useState(result.scenes || [])
  const [sceneSaving, setSceneSaving] = useState(false)
  const [sceneError, setSceneError] = useState(null)

  useEffect(() => {
    setScenes(result.scenes || [])
  }, [result])

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

  function updateScene(idx, field, value) {
    setScenes(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s))
  }

  async function saveSceneEdits(e) {
    e.preventDefault()
    setSceneSaving(true)
    setSceneError(null)
    try {
      const payload = {
        title: result.title,
        language: initialForm.language || 'English',
        scenes: scenes.map(s => ({
          title: s.title,
          narration: s.narration,
          content: s.content || s.narration,
          highlight: s.highlight || '',
          bullets: s.bullets || [],
          duration_seconds: Number(s.duration_seconds) || 8,
        })),
      }
      const res = await api(`/ai/videos/${result.id}/scenes`, {
        method: 'PUT',
        body: payload,
      })
      setScenes(res.scenes || [])
      setPlayerReloadToken(String(Date.now()))
      onReplace(res)
      onHistoryRefresh?.()
    } catch (err) {
      setSceneError(err.message || 'Failed to save scene edits')
    } finally {
      setSceneSaving(false)
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
      {result.duration_warning && (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          {result.duration_warning}
        </p>
      )}
      {playerUrl && (
        <Section title={t('ai.player')}>
          <iframe key={playerReloadToken} title="Lesson video player" src={playerUrl} className="h-[min(420px,60vh)] w-full rounded-md border border-slate-200 dark:border-slate-700" />
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
      {scenes.length > 0 && (
        <Section title={t('ai.scenes')}>
          <form onSubmit={saveSceneEdits} className="space-y-4">
            {scenes.map((scene, idx) => (
              <div key={idx} className="rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  <Volume2 size={14} /> Scene {idx + 1}
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Scene Title</label>
                  <input
                    className="input w-full"
                    value={scene.title || ''}
                    onChange={e => updateScene(idx, 'title', e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Narration</label>
                  <textarea
                    className="input w-full min-h-[80px] resize-y"
                    value={scene.narration || ''}
                    onChange={e => updateScene(idx, 'narration', e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Duration (seconds)</label>
                  <input
                    type="number"
                    min={2}
                    max={300}
                    className="input w-32"
                    value={scene.duration_seconds || 8}
                    onChange={e => updateScene(idx, 'duration_seconds', Number(e.target.value))}
                  />
                </div>
              </div>
            ))}
            {sceneError && (
              <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{sceneError}</p>
            )}
            <button type="submit" className="btn-primary w-full" disabled={sceneSaving}>
              {sceneSaving ? 'Saving & Re-rendering...' : 'Save Scene Edits & Re-render'}
            </button>
          </form>
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
  const location = useLocation()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [subject, setSubject] = useState('')
  const [gradeLevel, setGradeLevel] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [chatbotName, setChatbotName] = useState('EduSense AI')
  const [conversations, setConversations] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [fileContext, setFileContext] = useState(null)
  const [fileUploading, setFileUploading] = useState(false)
  const [fileLabel, setFileLabel] = useState(null)
  const [ragSources, setRagSources] = useState([])
  const [selectedSourceId, setSelectedSourceId] = useState('')
  const [listening, setListening] = useState(false)
  const fileInputRef = useRef(null)
  const recognitionRef = useRef(null)
  const messagesEndRef = useRef(null)
  const abortRef = useRef(null)
  const pendingUserRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // Load chatbot settings + history list on mount
  useEffect(() => {
    api('/ai/chat/settings').then(r => {
      if (r?.chatbot_name) setChatbotName(r.chatbot_name)
    }).catch(() => {})
    loadConversations()
    api('/rag/sources')
      .then(data => setRagSources(Array.isArray(data) ? data : []))
      .catch(err => setError(err.message || 'Could not load indexed documents'))
  }, [])

  // Handle navigation state from InstructorSources (ask about document)
  useEffect(() => {
    if (location.state?.sourceId) {
      setSelectedSourceId(location.state.sourceId)
      setFileLabel(`📎 ${location.state.sourceName || 'Selected document'}`)
      // Clear the state to prevent re-triggering
      window.history.replaceState({}, document.title)
    }
  }, [location.state])

  useEffect(() => () => recognitionRef.current?.stop(), [])

  // Set initial greeting when chatbotName is known
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{
        role: 'assistant',
        content: `Hello! I'm ${chatbotName}, your educational assistant. Ask me anything about your course materials, or I can search the web for current information. You can also upload a file to discuss its contents.`
      }])
    }
  }, [chatbotName])

  async function loadConversations() {
    setHistoryLoading(true)
    try {
      const data = await api('/ai/chat/conversations?limit=20')
      setConversations(Array.isArray(data) ? data : [])
    } catch {
      // silently ignore
    } finally {
      setHistoryLoading(false)
    }
  }

  async function loadConversation(id) {
    try {
      const data = await api(`/ai/chat/conversations/${id}`)
      if (data?.messages) {
        const loaded = data.messages.map(m => ({
          role: m.role,
          content: m.content,
          metadata: m.metadata || undefined,
        }))
        setMessages(loaded)
        setConversationId(id)
        setFileContext(null)
        setFileLabel(null)
        setSelectedSourceId('')
      }
    } catch (err) {
      setError('Failed to load conversation')
    }
  }

  async function deleteConversation(id, e) {
    e.stopPropagation()
    try {
      await api(`/ai/chat/conversations/${id}`, { method: 'DELETE' })
      setConversations(prev => prev.filter(c => c.conversation_id !== id))
      if (conversationId === id) {
        setConversationId(null)
        setMessages([{
          role: 'assistant',
          content: `Hello! I'm ${chatbotName}. How can I help you today?`
        }])
      }
    } catch {
      setError('Failed to delete conversation')
    }
  }

  async function handleFileUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setFileUploading(true)
    setFileContext(null)
    setFileLabel(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const data = await api('/ai/chat/upload', {
        method: 'POST',
        body: formData,
      })
      setFileContext(data.text)
      setFileLabel(`📎 ${file.name}${data.truncated ? ' (truncated)' : ''} — ${data.char_count} chars`)
    } catch (err) {
      setError(err.message || 'File upload failed')
    } finally {
      setFileUploading(false)
      e.target.value = ''
    }
  }

  const modeLabels = {
    'online_rag_web_llm': { label: 'RAG + Web + LLM', icon: <Zap className="w-3 h-3" />, color: 'bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300' },
    'online_rag_only': { label: 'RAG Only (Web Failed)', icon: <Database className="w-3 h-3" />, color: 'bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300' },
    'online_general_llm': { label: 'General Knowledge + LLM', icon: <Bot className="w-3 h-3" />, color: 'bg-teal-100 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300' },
    'selected_source_empty': { label: 'Selected File (No Indexed Passages)', icon: <Database className="w-3 h-3" />, color: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' },
    'offline_rag_template': { label: 'RAG + Template (Offline)', icon: <Bot className="w-3 h-3" />, color: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' },
    'offline_template_only': { label: 'Template Only (Offline)', icon: <Bot className="w-3 h-3" />, color: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300' },
  }

  async function requestChat(userMessage) {
    setLoading(true)
    setError('')
    const controller = new AbortController()
    abortRef.current = controller
    pendingUserRef.current = userMessage
    try {
      const response = await api('/ai/chat', {
        method: 'POST',
        signal: controller.signal,
        body: {
          message: userMessage,
          conversation_id: conversationId || undefined,
          conversation_history: conversationId ? [] : messages.slice(-6).map(m => ({ role: m.role, content: m.content })),
          subject: subject || undefined,
          grade_level: gradeLevel || undefined,
          file_context: fileContext || undefined,
          source_id: selectedSourceId || undefined,
        }
      })

      if (response.conversation_id && !conversationId) {
        setConversationId(response.conversation_id)
        // Refresh history list
        loadConversations()
      }
      if (response.chatbot_name) setChatbotName(response.chatbot_name)

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
      if (err?.name === 'AbortError' || controller.signal.aborted) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '_Response stopped._',
        }])
      } else {
        setError(err.message || 'Failed to get response')
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `Sorry, I couldn't generate a response: ${err.message || 'please try again.'}`,
        }])
      }
    } finally {
      abortRef.current = null
      pendingUserRef.current = null
      setLoading(false)
    }
  }

  async function sendMessage() {
    const userMessage = input.trim()
    if (!userMessage || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    await requestChat(userMessage)
  }

  function stopGeneration() {
    abortRef.current?.abort()
  }

  async function regenerateLast() {
    if (loading) return
    // Find the last user message and re-request it
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        setMessages(prev => prev.slice(0, i + 1))
        await requestChat(messages[i].content)
        return
      }
    }
  }

  function startNewConversation() {
    setConversationId(null)
    setMessages([{
      role: 'assistant',
      content: `Hello! I'm ${chatbotName}. How can I help you today?`
    }])
    setFileContext(null)
    setFileLabel(null)
    setSelectedSourceId('')
    setError('')
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function startVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setError('Voice input is not supported by this browser. You can type your question instead.')
      return
    }
    if (listening) {
      recognitionRef.current?.stop()
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = navigator.language || 'en-US'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim()
      if (transcript) setInput(transcript)
    }
    recognition.onerror = (event) => {
      setError(event.error === 'not-allowed'
        ? 'Microphone access was denied. Allow microphone access to use voice input.'
        : `Voice input failed: ${event.error}`)
    }
    recognition.onend = () => setListening(false)
    recognitionRef.current = recognition
    setError('')
    try {
      recognition.start()
      setListening(true)
    } catch (err) {
      setError(err.message || 'Could not start voice input')
      setListening(false)
    }
  }

  const lastAssistantIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return i
    }
    return -1
  })()

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-stretch">
      {/* History Sidebar */}
      <aside className="panel flex w-full shrink-0 flex-col space-y-3 xl:w-64">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold"><MessageCircle size={16} className="text-ocean dark:text-mint" /> Conversations</h2>
          <button className="btn-soft text-xs px-2.5 py-1.5" onClick={startNewConversation}>+ New</button>
        </div>
        {historyLoading && <p className="text-xs text-slate-400">Loading...</p>}
        {!historyLoading && conversations.length === 0 && (
          <p className="text-xs text-slate-400 italic">No past conversations</p>
        )}
        <div className="max-h-56 space-y-1 overflow-y-auto xl:max-h-none xl:flex-1">
          {conversations.map(conv => (
            <div
              key={conv.conversation_id}
              className={`group flex items-start gap-1 rounded-lg px-2.5 py-2 cursor-pointer text-xs transition hover:bg-slate-100 dark:hover:bg-slate-800 ${conv.conversation_id === conversationId ? 'bg-teal-50 font-semibold text-teal-900 dark:bg-teal-950/30 dark:text-teal-200' : 'text-slate-600 dark:text-slate-300'}`}
              onClick={() => loadConversation(conv.conversation_id)}
            >
              <span className="flex-1 truncate">{conv.preview || conv.conversation_id.slice(0, 16)}</span>
              <button
                className="hidden flex-shrink-0 text-slate-400 hover:text-red-500 group-hover:block"
                onClick={(e) => deleteConversation(conv.conversation_id, e)}
                title="Delete conversation"
              >×</button>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Chat Panel */}
      <section className="panel flex min-h-[70vh] w-full flex-1 flex-col overflow-hidden xl:h-[calc(100dvh-9rem)]">
        {/* Chat header */}
        <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white shadow-sm">
            <Bot size={20} />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-base font-black">{chatbotName}</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">RAG + web search + uploaded file context</p>
          </div>
          {loading && <Loader2 size={16} className="ms-auto animate-spin text-teal-600" />}
        </div>

        {error && (
          <p className="mx-4 mt-3 rounded-xl bg-red-50 px-4 py-2.5 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300" role="alert">{error}</p>
        )}

        {/* Messages — fills remaining vertical space */}
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              <div className={`max-w-[85%] sm:max-w-[75%] ${msg.role === 'user' ? 'order-2' : ''}`}>
                <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                  msg.role === 'user'
                    ? 'rounded-br-md bg-ocean text-white'
                    : 'rounded-bl-md border border-slate-200 bg-slate-50 text-slate-800 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-200'
                }`}>
                  {msg.role === 'assistant'
                    ? <MarkdownText text={msg.content} />
                    : msg.content}
                </div>
                {msg.metadata && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${modeLabels[msg.metadata.mode]?.color || 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'}`}>
                      {modeLabels[msg.metadata.mode]?.icon || <Bot size={10} />}
                      {modeLabels[msg.metadata.mode]?.label || msg.metadata.mode}
                    </span>
                    {msg.metadata.rag_chunks_used > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                        <Database size={10} /> {msg.metadata.rag_chunks_used} RAG
                      </span>
                    )}
                    {msg.metadata.web_results_used > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
                        <Globe size={10} /> {msg.metadata.web_results_used} Web
                      </span>
                    )}
                    {msg.metadata.rag_chunks_used === 0 && msg.metadata.web_results_used === 0 && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                        <AlertTriangle size={10} /> Unverified
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
                {msg.role === 'assistant' && idx === lastAssistantIdx && !loading && messages.length > 1 && (
                  <button
                    type="button"
                    onClick={regenerateLast}
                    className="mt-1.5 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-teal-600"
                  >
                    <RotateCcw size={11} /> Regenerate
                  </button>
                )}
              </div>
              <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                msg.role === 'user' ? 'bg-ocean/15 text-ocean dark:bg-mint/15 dark:text-mint' : 'bg-teal-100 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300'
              }`}>
                {msg.role === 'user' ? 'U' : 'AI'}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
              <span className="flex items-center gap-2">
                <Loader2 size={14} className="animate-spin text-teal-600" />
                <span className="animate-pulse">{chatbotName} is thinking…</span>
              </span>
              <button
                type="button"
                onClick={stopGeneration}
                className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 font-medium text-red-600 hover:bg-red-100 dark:bg-red-950/40 dark:text-red-300"
              >
                <Square size={10} /> Stop
              </button>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Composer */}
        <div className="space-y-3 border-t border-slate-100 px-4 py-3 dark:border-slate-800">
          {fileLabel && (
            <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:bg-blue-950/30 dark:text-blue-200">
              <span className="flex-1 truncate">{fileLabel}</span>
              <button className="flex-shrink-0 text-blue-400 hover:text-blue-700" onClick={() => { setFileContext(null); setFileLabel(null) }}>✕</button>
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-3">
            <input className="input text-sm" placeholder="Subject (optional)" value={subject} onChange={(e) => setSubject(e.target.value)} disabled={loading} />
            <input className="input text-sm" placeholder="Grade level (optional)" value={gradeLevel} onChange={(e) => setGradeLevel(e.target.value)} disabled={loading} />
            <select
              className="input text-sm"
              value={selectedSourceId}
              onChange={(e) => setSelectedSourceId(e.target.value)}
              disabled={loading}
              title="Ask about one indexed document"
            >
              <option value="">All indexed documents</option>
              {ragSources.map((source) => (
                <option key={source.source_id || source.source_file} value={source.source_id || source.source_file}>
                  {source.source_file || source.source_id}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end gap-2">
            <textarea
              className="input max-h-40 min-h-[56px] flex-1 resize-none py-2.5"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask me anything about your courses..."
              disabled={loading}
              rows={2}
            />
            <div className="flex flex-shrink-0 items-center gap-1.5">
              <button
                type="button"
                className={`btn-soft h-10 w-10 justify-center p-0 ${listening ? 'text-red-600' : ''}`}
                title={listening ? 'Stop voice input' : 'Speak your question'}
                aria-label={listening ? 'Stop voice input' : 'Speak your question'}
                disabled={loading}
                onClick={startVoiceInput}
              >
                {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <button
                type="button"
                className="btn-soft h-10 w-10 justify-center p-0"
                title="Upload file for context"
                disabled={fileUploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {fileUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
              </button>
              <input ref={fileInputRef} type="file" className="hidden" accept=".txt,.md,.pdf,.docx,.csv" onChange={handleFileUpload} />
              <button
                type="button"
                className="btn-primary flex h-10 w-10 items-center justify-center p-0"
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                aria-label="Send message"
              >
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send size={18} />}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <aside className="panel w-full shrink-0 space-y-4 xl:w-72">
        <h2 className="text-base font-bold">How It Works</h2>
        <div className="space-y-2.5 text-sm text-slate-600 dark:text-slate-400">
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500"><Zap className="h-3.5 w-3.5 text-amber-500" /> Online Mode</p>
            <p className="mt-1 text-xs leading-relaxed">RAG + web search + LLM answers with citations.</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500"><Database className="h-3.5 w-3.5 text-teal-600" /> RAG Only</p>
            <p className="mt-1 text-xs leading-relaxed">If web search fails, uses your knowledge base + LLM.</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500"><Paperclip className="h-3.5 w-3.5 text-blue-600" /> File Upload</p>
            <p className="mt-1 text-xs leading-relaxed">Attach .txt, .pdf, .docx, .md — text is injected as context.</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500"><Clock3 className="h-3.5 w-3.5 text-violet-600" /> Persistent History</p>
            <p className="mt-1 text-xs leading-relaxed">Conversations are saved — resume any past chat from the sidebar.</p>
          </div>
        </div>
      </aside>
    </div>
  )
}
