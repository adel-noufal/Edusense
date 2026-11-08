/**
 * StudentExams — Section 3
 * Lists published exams (is_exam=true) for sessions the student is enrolled in.
 * "Take Exam" navigates to /student/quizzes/:quizId (existing Quiz.jsx with
 * fullscreen_lock / camera_monitoring / anti-cheat already wired in).
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, BookOpen, CheckCircle, Clock, FileText, Lock, Shield } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

function formatDate(dt) {
  if (!dt) return null
  return new Date(dt).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

function formatTimer(secs) {
  if (!secs) return null
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return s ? `${m}m ${s}s` : `${m}m`
}

function ExamStatusBadge({ isPast, dueDate }) {
  if (!dueDate) return null
  if (isPast) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-900/40 dark:text-red-300">
        <AlertTriangle size={10} /> Overdue
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
      <Clock size={10} /> Open
    </span>
  )
}

export default function StudentExams() {
  const { token } = useAuth()
  const navigate = useNavigate()
  const [exams, setExams] = useState([])
  const [attempts, setAttempts] = useState({})   // quizId -> attempt data
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!token) return
    setLoading(true)
    setError(null)
    fetch(`${API}/quizzes/student/exams`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setExams(data)
        // Fetch attempt history for each exam
        return Promise.all(
          data.map(exam =>
            fetch(`${API}/quizzes/${exam.id}/my-attempts`, {
              headers: { Authorization: `Bearer ${token}` },
            })
              .then(r => r.ok ? r.json() : [])
              .then(att => ({ quizId: exam.id, attempts: att }))
              .catch(() => ({ quizId: exam.id, attempts: [] }))
          )
        )
      })
      .then(attData => {
        const map = {}
        attData.forEach(({ quizId, attempts }) => { map[quizId] = attempts })
        setAttempts(map)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="loader-ring" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
        <p className="font-semibold">Could not load exams</p>
        <p className="mt-1 text-sm">{error}</p>
      </div>
    )
  }

  if (exams.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-20 text-slate-500 dark:text-slate-400">
        <FileText size={48} className="opacity-30" />
        <p className="text-lg font-semibold">No exams yet</p>
        <p className="text-sm">Your instructor hasn't published any exams for your enrolled sessions.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold">My Exams</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Exams published by your instructor for sessions you're enrolled in.
        </p>
      </div>

      <div className="space-y-4">
        {exams.map(exam => {
          const myAttempts = attempts[exam.id] ?? []
          const lastAttempt = myAttempts.length
            ? myAttempts.reduce((a, b) => (a.started_at > b.started_at ? a : b))
            : null
          const submitted = lastAttempt?.submitted_at != null
          const isPast = exam.due_date && new Date(exam.due_date) < new Date()
          const canTake = !isPast && !submitted

          return (
            <div
              key={exam.id}
              className="card rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-slate-700/60 dark:bg-slate-900"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold">{exam.title}</h2>
                    <ExamStatusBadge isPast={isPast} dueDate={exam.due_date} />
                    {submitted && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                        <CheckCircle size={10} /> Submitted
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {exam.questions.length} question{exam.questions.length !== 1 ? 's' : ''} ·{' '}
                    {exam.difficulty} difficulty
                    {exam.due_date ? ` · Due ${formatDate(exam.due_date)}` : ''}
                  </p>
                </div>

                {canTake ? (
                  <button
                    type="button"
                    className="btn-primary shrink-0 gap-1.5 text-sm"
                    onClick={() => navigate(`/student/quizzes/${exam.id}`)}
                  >
                    <BookOpen size={15} /> Take Exam
                  </button>
                ) : submitted ? (
                  <span className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    <CheckCircle size={13} className="text-emerald-500" /> Submitted
                  </span>
                ) : (
                  <span className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 dark:bg-red-900/20 dark:text-red-300">
                    <Lock size={13} /> Closed
                  </span>
                )}
              </div>

              {/* Anti-cheat / timer info row */}
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {exam.time_limit_seconds && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                    <Clock size={11} /> Timer: {formatTimer(exam.time_limit_seconds)}
                  </span>
                )}
                {exam.time_limit_per_question_seconds && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                    <Clock size={11} /> Per question: {formatTimer(exam.time_limit_per_question_seconds)}
                  </span>
                )}
                {exam.fullscreen_lock && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-2 py-0.5 text-red-700 dark:bg-red-900/30 dark:text-red-300">
                    <Shield size={11} /> Fullscreen lockdown
                  </span>
                )}
                {exam.camera_monitoring && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-purple-50 px-2 py-0.5 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                    <Shield size={11} /> Camera monitoring
                  </span>
                )}
                {exam.lock_back_navigation && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                    <Lock size={11} /> No back navigation
                  </span>
                )}
              </div>

              {/* Prior attempt result */}
              {submitted && lastAttempt?.score != null && (
                <div className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                  Your score: {lastAttempt.score} / {lastAttempt.max_score}{' '}
                  ({Math.round((lastAttempt.score / lastAttempt.max_score) * 100)}%)
                  {' '}· Submitted {formatDate(lastAttempt.submitted_at)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
