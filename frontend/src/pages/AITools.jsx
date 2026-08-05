import { useEffect, useState } from 'react'
import { CheckCircle2, Download, FileQuestion, Layers, Sparkles, Trash2, Video, Volume2 } from 'lucide-react'
import { api, downloadAuthenticatedRequest, staticUrl } from '../services/api'
import { downloadBlob, downloadText, flashcardsToHtml } from '../utils/download'
import { useLanguage } from '../context/LanguageContext'

const languages = ['English', 'Arabic', 'French', 'Spanish']
const styles = ['Formal', 'Friendly', 'Interactive', 'Storytelling', 'Professional']
const difficulties = ['Easy', 'Medium', 'Hard']

export function LessonGenerator() {
  const { t } = useLanguage()
  const [form, setForm] = useState({
    topic: 'Neural Networks',
    prompt: 'Teach beginners with examples',
    language: 'English',
    teaching_style: 'Interactive',
    duration: 5,
    additional_notes: '',
  })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])

  async function loadHistory() {
    try {
      const data = await api('/ai/generations?type=lesson')
      setHistory(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  async function submit(e) {
    e.preventDefault()
    if (form.topic.trim().length < 3) {
      setError(t('ai.topicMin'))
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await api('/ai/lessons', { method: 'POST', body: JSON.stringify(form) })
      setResult(res)
      await loadHistory()
    } catch (err) {
      setError(err.message || 'Could not generate lesson')
    } finally {
      setLoading(false)
    }
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
            <Field label={t('ai.topic')} value={form.topic} onChange={(value) => setForm({ ...form, topic: value })} />
            <Field label={t('ai.prompt')} value={form.prompt} onChange={(value) => setForm({ ...form, prompt: value })} />
            <SelectField label={t('ai.language')} value={form.language} options={languages} onChange={(value) => setForm({ ...form, language: value })} />
            <SelectField label={t('ai.style')} value={form.teaching_style} options={styles} onChange={(value) => setForm({ ...form, teaching_style: value })} />
            <Field label={t('ai.duration')} type="number" value={form.duration} onChange={(value) => setForm({ ...form, duration: Number(value) || 5 })} />
            <Field label={t('ai.notes')} value={form.additional_notes} onChange={(value) => setForm({ ...form, additional_notes: value })} textarea />
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
              onClick={() => {
                setResult(h.data)
                setForm({
                  topic: h.topic,
                  prompt: h.prompt,
                  language: h.data.language || 'English',
                  teaching_style: h.data.style || 'Interactive',
                  duration: h.data.duration || 5,
                  additional_notes: '',
                })
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
  const [form, setForm] = useState({ topic: 'Neural Networks', count: 10, language: 'English' })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [flipped, setFlipped] = useState({})
  const [history, setHistory] = useState([])

  async function loadHistory() {
    try {
      const data = await api('/ai/generations?type=flashcard')
      setHistory(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  async function submit(e) {
    e.preventDefault()
    if (form.topic.trim().length < 3) {
      setError(t('ai.topicMin'))
      return
    }
    setLoading(true)
    setError('')
    setFlipped({})
    try {
      const res = await api('/ai/flashcards', { method: 'POST', body: JSON.stringify({ ...form, count: Number(form.count) || 10 }) })
      setResult(res)
      await loadHistory()
    } catch (err) {
      setError(err.message || 'Could not generate flashcards')
    } finally {
      setLoading(false)
    }
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
            <Field label={t('ai.topic')} value={form.topic} onChange={(value) => setForm({ ...form, topic: value })} />
            <Field label={t('ai.cardCount')} type="number" value={form.count} onChange={(value) => setForm({ ...form, count: value })} />
            <SelectField label={t('ai.language')} value={form.language} options={languages} onChange={(value) => setForm({ ...form, language: value })} />
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
                  count: h.data.cards?.length || 10,
                  language: h.data.language || 'English'
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
  const [form, setForm] = useState({ topic: 'Neural Networks', difficulty: 'Medium', count: 5, session_id: '' })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [answers, setAnswers] = useState({})
  const [revealed, setRevealed] = useState({})
  const [history, setHistory] = useState([])

  async function loadHistory() {
    try {
      const data = await api('/ai/quizzes')
      setHistory(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadHistory() }, [])

  async function submit(e) {
    e.preventDefault()
    if (form.topic.trim().length < 3) {
      setError(t('ai.topicMin'))
      return
    }
    setLoading(true)
    setError('')
    setAnswers({})
    setRevealed({})
    try {
      const payload = {
        ...form,
        count: Number(form.count) || 5,
        session_id: form.session_id === '' ? null : Number(form.session_id),
      }
      const res = await api('/ai/quizzes', { method: 'POST', body: JSON.stringify(payload) })
      setResult(res)
      await loadHistory()
    } catch (err) {
      setError(err.message || 'Could not generate quiz')
    } finally {
      setLoading(false)
    }
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
            <Field label={t('ai.topic')} value={form.topic} onChange={(value) => setForm({ ...form, topic: value })} />
            <SelectField label={t('ai.difficulty')} value={form.difficulty} options={difficulties} onChange={(value) => setForm({ ...form, difficulty: value })} />
            <Field label={t('ai.questionCount')} type="number" value={form.count} onChange={(value) => setForm({ ...form, count: value })} />
            <Field label={t('ai.sessionId')} value={form.session_id} onChange={(value) => setForm({ ...form, session_id: value })} />
          </div>
          <button className="btn-primary" disabled={loading}>{loading ? t('ai.generatingLesson') : t('ai.generateQuiz')}</button>
        </ToolShell>
        {result && <QuizResult result={result} answers={answers} revealed={revealed} onAnswer={setAnswers} onReveal={setRevealed} />}
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
                  difficulty: h.difficulty,
                  count: h.questions?.length || 5,
                  session_id: h.session_id || ''
                })
                setAnswers({})
                setRevealed({})
              }}
              className="group cursor-pointer rounded-2xl border border-slate-200 p-4 hover:bg-slate-50/50 transition dark:border-slate-700 dark:hover:bg-slate-800/50"
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
  })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (form.title.trim().length < 3) {
      setError(t('ai.titleMin'))
      return
    }
    setLoading(true)
    setError('')
    try {
      setResult(await api('/ai/videos', { method: 'POST', body: JSON.stringify(form) }))
    } catch (err) {
      setError(err.message || 'Could not generate video')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ToolShell title={t('ai.videoTitle')} icon={<Video />} onSubmit={submit} loading={loading} error={error}>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label={t('sessions.titleField')} value={form.title} onChange={(value) => setForm({ ...form, title: value })} />
        <Field label={t('ai.prompt')} value={form.prompt} onChange={(value) => setForm({ ...form, prompt: value })} />
        <SelectField label={t('ai.language')} value={form.language} options={languages} onChange={(value) => setForm({ ...form, language: value })} />
        <SelectField label={t('ai.videoStyle')} value={form.style} options={styles} onChange={(value) => setForm({ ...form, style: value })} />
        <Field label={t('ai.duration')} type="number" value={form.duration} onChange={(value) => setForm({ ...form, duration: Number(value) || 5 })} />
        <Field label={t('ai.videoNotes')} value={form.notes} onChange={(value) => setForm({ ...form, notes: value })} textarea />
      </div>
      <button className="btn-primary" disabled={loading}>{loading ? t('ai.buildingVideo') : t('ai.generateVideo')}</button>
      {result && <VideoResult result={result} initialForm={form} onReplace={setResult} />}
    </ToolShell>
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
  return (
    <div className="space-y-5 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.topic} subtitle={`${result.language} · ${result.style} · ${result.duration} min`} />
      <DownloadBar
        items={[
          {
            label: 'Word',
            onClick: () => downloadAuthenticatedRequest('/ai/lessons/export-word', `${(result.topic || 'lesson').replace(/\s+/g, '-').toLowerCase()}.doc`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(request),
            }),
          },
          {
            label: 'PowerPoint',
            onClick: () => downloadAuthenticatedRequest('/ai/lessons/export-pptx', `${(result.topic || 'lesson').replace(/\s+/g, '-').toLowerCase()}.pptx`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(request),
            }),
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

function QuizResult({ result, answers, revealed, onAnswer, onReveal }) {
  const { t } = useLanguage()
  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={result.title} subtitle={result.difficulty} />
      <DownloadBar
        items={[
          ...(result.id ? [{ label: 'Word', onClick: () => downloadAuthenticatedRequest(`/ai/quizzes/${result.id}/download-word`, `quiz-${result.id}.doc`) }] : []),
        ]}
      />
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

function VideoResult({ result, initialForm, onReplace }) {
  const { t } = useLanguage()
  const playerUrl = result.video_url ? staticUrl(result.video_url) : null
  const mp4Url = result.mp4_url ? staticUrl(result.mp4_url) : null
  const [editForm, setEditForm] = useState({
    title: initialForm.title,
    prompt: initialForm.prompt,
    language: initialForm.language,
    style: initialForm.style,
    duration: initialForm.duration,
    notes: initialForm.notes,
  })
  const [editing, setEditing] = useState(false)

  async function downloadStatic(url, filename) {
    const response = await fetch(url)
    downloadBlob(await response.blob(), filename)
  }

  async function editVideo(e) {
    e.preventDefault()
    setEditing(true)
    try {
      const updated = await api(`/ai/videos/${result.id}/edit`, { method: 'POST', body: JSON.stringify(editForm) })
      onReplace(updated)
    } finally {
      setEditing(false)
    }
  }

  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <ResultHeader title={t('ai.videoReady')} subtitle={result.status} />
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
          <button type="submit" className="btn-primary md:col-span-2">{editing ? 'Updating video...' : 'Apply prompt edit'}</button>
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
      <ResultHeader title={result.title} subtitle={`${result.cards?.length || 0} · ${result.language}`} />
      <DownloadBar
        items={[
          {
            label: 'Word',
            onClick: () => downloadAuthenticatedRequest('/ai/flashcards/export-word', `${(result.title || 'flashcards').replace(/\s+/g, '-').toLowerCase()}.doc`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ topic: request.topic, count: Number(request.count) || 10, language: request.language }),
            }),
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

function ResultHeader({ title, subtitle }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-lg font-bold">{title}</p>
        <p className="text-sm text-slate-500">{subtitle}</p>
      </div>
      <CheckCircle2 className="text-emerald-500" size={20} />
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
