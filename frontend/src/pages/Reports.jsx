import { useEffect, useMemo, useRef, useState } from 'react'
import { BarChart3, BookOpen, ChevronRight, FileDown, FileText, Trash2, Upload, Users } from 'lucide-react'
import { api } from '../services/api'
import { EmotionDistribution, EngagementLine, StatsBars } from '../components/Charts'
import { staticUrl } from '../services/api'

export default function Reports() {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [activeStudentId, setActiveStudentId] = useState(null)
  const [sessionDetail, setSessionDetail] = useState(null)
  const [studentDetail, setStudentDetail] = useState(null)
  const [resources, setResources] = useState([])
  const [uploadingResource, setUploadingResource] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const resourceInputRef = useRef(null)

  async function loadSessions() {
    setLoading(true)
    try {
      const data = await api('/reports/sessions')
      setSessions(Array.isArray(data) ? data : [])
      setActiveSessionId((current) => current || data?.[0]?.id || null)
      setError('')
    } catch (err) {
      setError(err.message)
      setSessions([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadSessions() }, [])

  useEffect(() => {
    if (!activeSessionId) return
    api(`/reports/sessions/${activeSessionId}`)
      .then((data) => {
        setSessionDetail(data)
        setActiveStudentId((current) => current || data.attendees?.[0]?.id || null)
      })
      .catch((err) => setError(err.message))
    api(`/sessions/${activeSessionId}/resources`)
      .then((data) => setResources(Array.isArray(data) ? data : []))
      .catch(() => setResources([]))
  }, [activeSessionId])

  useEffect(() => {
    if (!activeSessionId || !activeStudentId) return
    api(`/reports/sessions/${activeSessionId}/students/${activeStudentId}`)
      .then(setStudentDetail)
      .catch((err) => setError(err.message))
  }, [activeSessionId, activeStudentId])

  const stats = useMemo(() => {
    if (!sessionDetail?.session) return []
    return [
      { name: 'Engagement', value: sessionDetail.session.engagement_percentage || 0 },
      { name: 'Attendees', value: sessionDetail.session.attendee_count || 0 },
      { name: 'Emotion Samples', value: sessionDetail.session.emotion_samples || 0 },
      { name: 'Quizzes', value: sessionDetail.session.quiz_count || 0 },
    ]
  }, [sessionDetail])

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
      const list = await api(`/sessions/${activeSessionId}/resources`)
      setResources(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploadingResource(false)
      if (resourceInputRef.current) resourceInputRef.current.value = ''
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

  return (
    <div className="page-shell space-y-6">
      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black">Reports Center</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              Select a session to inspect attendees, reactions, linked quizzes, stored reports, and database-relevant records.
            </p>
          </div>
          <button className="btn-soft" type="button" onClick={loadSessions}>Refresh</button>
        </div>
        {stats.length > 0 && (
          <div className="mt-6">
            <StatsBars data={stats} />
          </div>
        )}
      </div>

      {error && <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200">{error}</p>}
      {loading && <div className="panel text-sm text-slate-500">Loading reports...</div>}

      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <div className="panel space-y-3">
          <div className="flex items-center gap-3 text-lg font-bold"><FileText size={20} />Sessions</div>
          {!loading && sessions.length === 0 && <p className="text-sm text-slate-500">No sessions available yet.</p>}
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              className={`block w-full rounded-2xl border px-4 py-4 text-left transition ${activeSessionId === session.id ? 'border-teal-300 bg-teal-50/80 dark:border-teal-700 dark:bg-slate-800' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/70'}`}
              onClick={() => {
                setActiveSessionId(session.id)
                setActiveStudentId(null)
                setStudentDetail(null)
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-bold">{session.title}</p>
                  <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">{session.status}</p>
                </div>
                <ChevronRight size={18} className="text-slate-400" />
              </div>
              <p className="mt-3 text-sm text-slate-500">{session.date} | {session.start_time}</p>
              <p className="mt-2 text-xs text-slate-500">{session.attendee_count} attendees · {session.quiz_count} quizzes</p>
            </button>
          ))}
        </div>

        <div className="space-y-6">
          {sessionDetail?.session && (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="panel space-y-4">
                  <div className="flex items-center gap-3 text-lg font-bold"><BarChart3 size={20} />{sessionDetail.session.title}</div>
                  <p className="text-sm text-slate-600 dark:text-slate-300">{sessionDetail.session.description || 'No session description was provided.'}</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <InfoPill label="Date" value={String(sessionDetail.session.date)} />
                    <InfoPill label="Status" value={sessionDetail.session.status} />
                    <InfoPill label="Duration" value={`${sessionDetail.session.duration} min`} />
                    <InfoPill label="Engagement" value={`${sessionDetail.session.engagement_percentage}%`} />
                  </div>
                  <div className="rounded-2xl bg-slate-100 p-4 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    Dominant emotions: {sessionDetail.session.dominant_emotions?.join(', ') || 'No samples yet'}
                  </div>
                </div>
                <div className="panel">
                  <EmotionDistribution data={sessionDetail.session.emotion_distribution} />
                </div>
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <div className="panel">
                  <div className="mb-4 flex items-center gap-3 text-lg font-bold"><Users size={20} />Attendees</div>
                  <div className="space-y-3">
                    {sessionDetail.attendees?.map((student) => (
                      <button
                        key={student.id}
                        type="button"
                        className={`flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition ${activeStudentId === student.id ? 'border-ocean bg-ocean/5 dark:border-mint dark:bg-mint/10' : 'border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800'}`}
                        onClick={() => setActiveStudentId(student.id)}
                      >
                        <div>
                          <p className="font-semibold">{student.name}</p>
                          <p className="text-sm text-slate-500">{student.email}</p>
                        </div>
                        <div className="text-right text-xs text-slate-500">
                          <p>{student.emotion_samples} samples</p>
                          <p>{student.dominant_emotion}</p>
                        </div>
                      </button>
                    ))}
                    {!sessionDetail.attendees?.length && <p className="text-sm text-slate-500">No attendees registered for this session yet.</p>}
                  </div>
                </div>
                <div className="panel">
                  <div className="mb-4 flex items-center gap-3 text-lg font-bold"><BookOpen size={20} />Session Quizzes</div>
                  <div className="space-y-3">
                    {sessionDetail.quizzes?.map((quiz) => (
                      <div key={quiz.id} className="rounded-2xl border border-slate-200 p-4 dark:border-slate-700">
                        <p className="font-semibold">{quiz.title}</p>
                        <p className="mt-1 text-sm text-slate-500">{quiz.difficulty} · {quiz.question_count} questions</p>
                      </div>
                    ))}
                    {!sessionDetail.quizzes?.length && <p className="text-sm text-slate-500">No quizzes are linked to this session yet.</p>}
                  </div>
                </div>
              </div>

              <div className="panel space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 text-lg font-bold"><Upload size={20} />Preparation Sources</div>
                  <button type="button" className="btn-soft" onClick={() => resourceInputRef.current?.click()}>
                    Upload Source
                  </button>
                </div>
                <input
                  ref={resourceInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.pptx,.ppt,.doc,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.mp4,.zip"
                  onChange={uploadResource}
                />
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  Upload slides, PDFs, notes, or any materials you already prepared. Students enrolled in this session can access them from their resources page.
                </p>
                {uploadingResource && <p className="text-sm text-teal-700 dark:text-teal-300">Uploading...</p>}
                <div className="space-y-2 max-h-72 overflow-y-auto">
                  {resources.map((resource) => (
                    <div key={resource.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 px-4 py-3 dark:border-slate-700">
                      <FileDown size={18} className="text-purple-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm truncate">{resource.name}</p>
                        <p className="text-xs text-slate-500">{formatBytes(resource.file_size)} · {new Date(resource.uploaded_at).toLocaleDateString()}</p>
                      </div>
                      <a href={staticUrl(resource.url)} target="_blank" rel="noreferrer" className="btn-soft p-1.5" title="Open">
                        <FileDown size={16} />
                      </a>
                      <button type="button" className="btn-soft p-1.5 text-red-500" onClick={() => deleteResource(resource.id)} title="Delete">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                  {!resources.length && !uploadingResource && (
                    <p className="text-sm text-slate-500">No preparation files uploaded for this session yet.</p>
                  )}
                </div>
              </div>

              <div className="grid gap-6">
                <div className="panel">
                  <div className="mb-4 flex items-center gap-3 text-lg font-bold"><Users size={20} />Student Analysis</div>
                  {studentDetail ? (
                    <div className="space-y-4">
                      <div className="flex items-center gap-4 rounded-2xl bg-slate-100 p-4 dark:bg-slate-800">
                        <Avatar src={studentDetail.student.avatar} name={studentDetail.student.name} />
                        <div>
                          <p className="text-lg font-bold">{studentDetail.student.name}</p>
                          <p className="text-sm text-slate-500">{studentDetail.student.email}</p>
                          <p className="text-xs text-slate-500">{studentDetail.student.university || 'University not set'} · {studentDetail.student.department || 'Department not set'}</p>
                        </div>
                      </div>
                      <p className="text-sm leading-7 text-slate-600 dark:text-slate-300">{studentDetail.analysis.summary}</p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <InfoPill label="Dominant Emotion" value={studentDetail.attendance.dominant_emotion} />
                        <InfoPill label="Average Confidence" value={`${Math.round((studentDetail.attendance.average_confidence || 0) * 100)}%`} />
                      </div>
                      <div>
                        <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Reaction Breakdown</p>
                        <div className="space-y-2">
                          {studentDetail.analysis.reactions.map((reaction) => (
                            <div key={reaction.emotion} className="flex items-center justify-between rounded-2xl bg-slate-100 px-4 py-3 text-sm dark:bg-slate-800">
                              <span className="capitalize">{reaction.emotion}</span>
                              <span className="font-semibold">{reaction.count}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700">
                        {studentDetail.analysis.notes_status}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">Select a student to view details.</p>
                  )}
                </div>
              </div>

              {studentDetail?.analysis?.timeline?.length > 0 && (
                <div className="panel">
                  <div className="mb-4 text-lg font-bold">Student Emotion Timeline</div>
                  <EngagementLine data={studentDetail.analysis.timeline.map((entry) => ({ emotion: entry.emotion, score: Math.round(entry.confidence * 100) }))} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function InfoPill({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 px-4 py-3 dark:border-slate-700">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 font-semibold">{value}</p>
    </div>
  )
}

function Avatar({ src, name }) {
  if (src) {
    return <img src={src.startsWith('http') ? src : staticUrl(src)} alt={name} className="h-16 w-16 rounded-2xl object-cover shadow-md" />
  }
  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-ocean to-teal-500 text-lg font-black text-white">
      {name?.slice(0, 1)?.toUpperCase() || '?'}
    </div>
  )
}
