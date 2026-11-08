/**
 * StudentAssignments — Section 3
 * Lists all assignments from the student's enrolled sessions.
 * Allows uploading a submission file per assignment (PDF, Word, image, etc.).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle, CalendarDays, CheckCircle2, ClipboardList,
  Loader2, Paperclip, Upload, X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

function formatDate(dt) {
  if (!dt) return 'No due date'
  return new Date(dt).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function isPast(dt) {
  return dt && new Date(dt) < new Date()
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

/** Single assignment card with inline file upload. */
function AssignmentCard({ assignment, submission, onSubmitted }) {
  const { token } = useAuth()
  const fileInput = useRef(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  const hasSubmission = !!(submission)
  const overdue = isPast(assignment.due_date) && !hasSubmission

  function handleFileChange(e) {
    setSelectedFile(e.target.files[0] ?? null)
    setError(null)
    setSuccess(false)
  }

  async function handleUpload() {
    if (!selectedFile) return
    setUploading(true)
    setError(null)
    setSuccess(false)

    const formData = new FormData()
    formData.append('file', selectedFile)

    try {
      const r = await fetch(`${API}/assignments/${assignment.id}/submit`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      let data
      try { data = await r.json() } catch { data = null }
      if (!r.ok) {
        throw new Error(data?.detail ?? `Upload failed (HTTP ${r.status})`)
      }
      setSuccess(true)
      setSelectedFile(null)
      if (fileInput.current) fileInput.current.value = ''
      onSubmitted(assignment.id, data)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className={`rounded-2xl border p-4 shadow-sm transition-colors ${
      overdue
        ? 'border-red-200 bg-red-50/50 dark:border-red-800/50 dark:bg-red-950/20'
        : 'border-slate-200/80 bg-white dark:border-slate-700/60 dark:bg-slate-900'
    }`}>
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold leading-snug">{assignment.title}</h3>
          {assignment.description && (
            <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
              {assignment.description}
            </p>
          )}
        </div>

        {/* Status badge */}
        {hasSubmission ? (
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            <CheckCircle2 size={12} /> Submitted
          </span>
        ) : overdue ? (
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700 dark:bg-red-900/40 dark:text-red-300">
            <AlertCircle size={12} /> Overdue
          </span>
        ) : (
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
            <ClipboardList size={12} /> Not submitted
          </span>
        )}
      </div>

      {/* Meta: due date + points */}
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400">
        <span className="inline-flex items-center gap-1">
          <CalendarDays size={11} />
          Due: {formatDate(assignment.due_date)}
        </span>
        <span>Max points: {assignment.max_points}</span>
      </div>

      {/* Submitted file info */}
      {hasSubmission && (
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2 text-xs text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
          <Paperclip size={12} />
          <span className="font-medium">{submission.file_name}</span>
          <span className="text-emerald-600 dark:text-emerald-400">
            ({formatFileSize(submission.file_size)})
          </span>
          <span className="ml-auto shrink-0">
            Submitted {formatDate(submission.submitted_at)}
          </span>
        </div>
      )}

      {/* Instructor feedback (if any) */}
      {hasSubmission && submission.feedback && (
        <div className="mt-2 rounded-xl bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
          <span className="font-semibold">Instructor feedback: </span>{submission.feedback}
        </div>
      )}
      {hasSubmission && submission.score != null && (
        <div className="mt-1 rounded-xl bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
          Score: {submission.score} / {assignment.max_points}
        </div>
      )}

      {/* Upload section — always shown so student can re-submit */}
      {!overdue && (
        <div className="mt-3 space-y-2">
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
            {hasSubmission ? 'Replace submission' : 'Upload submission'}
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileInput}
              type="file"
              className="hidden"
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.gif,.webp,.txt,.zip"
              onChange={handleFileChange}
            />
            <button
              type="button"
              className="btn-soft gap-1.5 text-xs"
              onClick={() => fileInput.current?.click()}
            >
              <Paperclip size={13} /> Choose file
            </button>
            {selectedFile && (
              <>
                <span className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  {selectedFile.name}
                  <button
                    type="button"
                    className="ml-1 text-slate-400 hover:text-slate-600"
                    onClick={() => { setSelectedFile(null); if (fileInput.current) fileInput.current.value = '' }}
                  >
                    <X size={11} />
                  </button>
                </span>
                <button
                  type="button"
                  disabled={uploading}
                  className="btn-primary gap-1.5 text-xs disabled:opacity-60"
                  onClick={handleUpload}
                >
                  {uploading
                    ? <><Loader2 size={13} className="animate-spin" /> Uploading…</>
                    : <><Upload size={13} /> Submit</>}
                </button>
              </>
            )}
          </div>
          {error && (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          )}
          {success && (
            <p className="text-xs text-emerald-600 dark:text-emerald-400">
              ✓ Submission uploaded successfully!
            </p>
          )}
          <p className="text-xs text-slate-400">
            Accepted formats: PDF, Word (.doc/.docx), images, .txt, .zip · Max 50 MB
          </p>
        </div>
      )}
    </div>
  )
}

export default function StudentAssignments() {
  const { token } = useAuth()
  const [assignments, setAssignments] = useState([])
  const [submissions, setSubmissions] = useState({})  // assignmentId -> submission
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!token) return
    setLoading(true)
    setError(null)

    fetch(`${API}/assignments/student`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setAssignments(data)
        // Fetch submission status for each assignment
        return Promise.all(
          data.map(a =>
            fetch(`${API}/assignments/${a.id}/submission`, {
              headers: { Authorization: `Bearer ${token}` },
            })
              .then(r => r.ok ? r.json() : null)
              .then(sub => ({ id: a.id, sub }))
              .catch(() => ({ id: a.id, sub: null }))
          )
        )
      })
      .then(subData => {
        const map = {}
        subData.forEach(({ id, sub }) => { map[id] = sub })
        setSubmissions(map)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [token])

  const handleSubmitted = useCallback((assignmentId, submissionData) => {
    setSubmissions(prev => ({ ...prev, [assignmentId]: submissionData }))
  }, [])

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
        <p className="font-semibold">Could not load assignments</p>
        <p className="mt-1 text-sm">{error}</p>
      </div>
    )
  }

  if (assignments.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-20 text-slate-500 dark:text-slate-400">
        <ClipboardList size={48} className="opacity-30" />
        <p className="text-lg font-semibold">No assignments yet</p>
        <p className="text-sm">Your instructor hasn't created any assignments for your sessions.</p>
      </div>
    )
  }

  // Group by session_id (use session_id as key; we don't have session name from this endpoint)
  const bySession = {}
  assignments.forEach(a => {
    const key = a.session_id
    if (!bySession[key]) bySession[key] = []
    bySession[key].push(a)
  })

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">My Assignments</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Assignments from your enrolled sessions. Upload your work before the due date.
        </p>
      </div>

      {Object.entries(bySession).map(([sessionId, sessionAssignments]) => (
        <section key={sessionId}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Session #{sessionId}
          </h2>
          <div className="space-y-3">
            {sessionAssignments.map(a => (
              <AssignmentCard
                key={a.id}
                assignment={a}
                submission={submissions[a.id] ?? null}
                onSubmitted={handleSubmitted}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
