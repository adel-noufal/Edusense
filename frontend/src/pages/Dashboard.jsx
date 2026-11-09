import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Activity, BellRing, BookMarked, BookOpen, CheckCircle2, Clock3, Download, Eye, FileText, FolderOpen, Palette, Search, Sparkles, Users, Video, XCircle } from 'lucide-react'
import { EmotionDistribution, EngagementLine } from '../components/Charts'
import { api, staticUrl } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'

export function StudentDashboard() {
  const { t } = useLanguage()
  const location = useLocation()
  const mode = location.pathname.includes('/history') ? 'history' : location.pathname.includes('/upcoming') ? 'upcoming' : location.pathname.includes('/browse') ? 'browse' : 'all'
  const [enrolledSessions, setEnrolledSessions] = useState([])
  const [browseData, setBrowseData] = useState({ sessions: [], summary: null })
  const [error, setError] = useState('')

  async function loadSessions() {
    try {
      const [mySessions, browse] = await Promise.all([
        api('/sessions/student/my-sessions'),
        api('/sessions/browse'),
      ])
      setEnrolledSessions(Array.isArray(mySessions) ? mySessions : [])
      setBrowseData(browse || { sessions: [], summary: null })
      setError('')
    } catch (err) {
      setEnrolledSessions([])
      setBrowseData({ sessions: [], summary: null })
      setError(err.message)
    }
  }

  useEffect(() => { loadSessions() }, [])

  const filtered = enrolledSessions.filter((session) => {
    if (mode === 'upcoming') return ['pending', 'ongoing', 'preparing', 'scheduled', 'upcoming'].includes(session.status)
    if (mode === 'history') return true
    return true
  })

  const upcomingSessions = useMemo(
    () => enrolledSessions.filter((session) => ['pending', 'ongoing', 'preparing', 'scheduled', 'upcoming'].includes(session.status)),
    [enrolledSessions],
  )
  const openCatalog = useMemo(
    () => browseData.sessions.filter((session) => !session.is_registered),
    [browseData.sessions],
  )

  const titles = { all: t('dashboard.student'), upcoming: t('dashboard.upcoming'), history: t('dashboard.historyTitle'), browse: t('nav.browse') }
  const upcomingCount = upcomingSessions.length
  const completedCount = enrolledSessions.filter((session) => session.attended || ['ended', 'cancelled'].includes(session.status)).length
  const liveCount = enrolledSessions.filter((session) => session.status === 'ongoing').length

  return (
    <div className="page-shell space-y-6">
      <Hero title={titles[mode]} />
      <StudentStats enrolled={enrolledSessions.length} upcoming={upcomingCount} completed={completedCount} live={liveCount} />
      {mode === 'upcoming' && browseData.summary && (
        <div className="grid gap-4 md:grid-cols-3">
          <HighlightCard icon={BookMarked} label="Available Sessions" value={browseData.summary.available} />
          <HighlightCard icon={Sparkles} label="Registered" value={browseData.summary.registered} />
          <HighlightCard icon={Clock3} label="Live Now" value={browseData.summary.live_now} />
        </div>
      )}
      {error && <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200">{error}</p>}

      {mode === 'history' ? (
        <StudentHistoryView sessions={enrolledSessions} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-2">
          <div className="panel">
            <h2 className="mb-4 text-lg font-bold">{mode === 'upcoming' ? 'Your Registered Sessions' : titles[mode]}</h2>
            {mode !== 'browse' && (
              <SessionList sessions={mode === 'upcoming' ? upcomingSessions : filtered} join={mode !== 'history'} showUnregister={mode === 'upcoming'} emptyLabel="You have not registered for any sessions yet." onReload={loadSessions} />
            )}
            {mode === 'browse' && (
              <SessionCatalog sessions={openCatalog} onReload={loadSessions} />
            )}
          </div>
          {mode === 'upcoming' ? (
            <div className="panel">
              <div className="mb-4 flex items-center justify-between gap-2">
                <h2 className="text-lg font-bold">Recommended for you</h2>
                <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-ocean dark:bg-slate-800 dark:text-mint">Course-style registration</span>
              </div>
              <SessionCatalog sessions={openCatalog.slice(0, 3)} onReload={loadSessions} />
            </div>
          ) : mode === 'browse' ? (
            <div className="panel space-y-4">
              <div className="mb-4 flex items-center justify-between gap-2">
                <h2 className="text-lg font-bold">Enrollment Guidelines</h2>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">How It Works</span>
              </div>
              <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
                <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
                  <p className="font-bold text-slate-800 dark:text-slate-200">1. Browse &amp; Select</p>
                  <p className="text-xs text-slate-500 mt-1">Review upcoming scheduled sessions by instructors. Check topics, date, and seat availability.</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
                  <p className="font-bold text-slate-800 dark:text-slate-200">2. Explicit Enrollment</p>
                  <p className="text-xs text-slate-500 mt-1">Click &quot;Enroll in Session&quot; to register. Sessions will only appear in your Upcoming schedule after you enroll.</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
                  <p className="font-bold text-slate-800 dark:text-slate-200">3. Live Join Notification</p>
                  <p className="text-xs text-slate-500 mt-1">When the instructor starts the session, you will receive an email with a direct join link, and a &quot;Join Live Now&quot; button will activate in Upcoming.</p>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function StudentHistoryView({ sessions }) {
  const [selectedSession, setSelectedSession] = useState(null)
  const [resources, setResources] = useState([])
  const [loadingResources, setLoadingResources] = useState(false)
  const [filterAttended, setFilterAttended] = useState('all')

  const filtered = useMemo(() => {
    if (filterAttended === 'attended') return sessions.filter((s) => s.attended)
    if (filterAttended === 'absent') return sessions.filter((s) => !s.attended)
    return sessions
  }, [sessions, filterAttended])

  async function openSessionResources(session) {
    if (selectedSession?.id === session.id) {
      setSelectedSession(null)
      return
    }
    setSelectedSession(session)
    setLoadingResources(true)
    try {
      const data = await api(`/sessions/${session.id}/resources`)
      setResources(Array.isArray(data) ? data : [])
    } catch (err) {
      setResources([])
    } finally {
      setLoadingResources(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="panel space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">Enrolled Session History</h2>
            <p className="text-sm text-slate-500">Track your attendance and access class materials &amp; resources.</p>
          </div>
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setFilterAttended('all')}
              className={`py-1.5 px-3 rounded-lg transition ${filterAttended === 'all' ? 'bg-white shadow text-ocean dark:bg-slate-700 dark:text-mint' : 'text-slate-500 hover:text-slate-700'}`}
            >
              All ({sessions.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterAttended('attended')}
              className={`py-1.5 px-3 rounded-lg transition ${filterAttended === 'attended' ? 'bg-white shadow text-emerald-700 dark:bg-slate-700 dark:text-emerald-400' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Attended ({sessions.filter(s => s.attended).length})
            </button>
            <button
              type="button"
              onClick={() => setFilterAttended('absent')}
              className={`py-1.5 px-3 rounded-lg transition ${filterAttended === 'absent' ? 'bg-white shadow text-slate-700 dark:bg-slate-700 dark:text-slate-300' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Absent ({sessions.filter(s => !s.attended).length})
            </button>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 dark:border-slate-800 p-8 text-center text-slate-400">
            No enrolled sessions found matching this filter.
          </div>
        ) : (
          <div className="grid gap-4">
            {filtered.map((s) => {
              const isSelected = selectedSession?.id === s.id
              return (
                <div
                  key={s.id}
                  className={`rounded-2xl border p-4 transition ${isSelected ? 'border-ocean/40 bg-teal-50/20 shadow dark:border-mint/30 dark:bg-slate-800/40' : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900/60'}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{s.title}</h3>
                        {s.attended ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                            <CheckCircle2 size={13} /> Attended
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                            <XCircle size={13} /> Absent
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Instructor: <span className="font-medium text-slate-700 dark:text-slate-300">{s.instructor_name || 'Assigned Instructor'}</span> &bull; Status: <span className="capitalize">{s.status}</span>
                      </p>
                      {s.description && (
                        <p className="text-sm text-slate-600 dark:text-slate-300 mt-1">{s.description}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => openSessionResources(s)}
                      className={`btn-soft text-xs py-2 px-3 flex items-center gap-1.5 font-semibold ${isSelected ? 'bg-ocean text-white hover:bg-ocean/90 dark:bg-mint dark:text-slate-950' : ''}`}
                    >
                      <FolderOpen size={15} />
                      {isSelected ? 'Hide Resources' : 'Session Resources'}
                    </button>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800/80 pt-2.5">
                    <span>Date: <strong className="text-slate-700 dark:text-slate-200">{s.date}</strong></span>
                    <span>Time: <strong className="text-slate-700 dark:text-slate-200">{s.start_time}</strong></span>
                    <span>Duration: <strong className="text-slate-700 dark:text-slate-200">{s.duration} min</strong></span>
                  </div>

                  {/* Expanded Resources Drawer */}
                  {isSelected && (
                    <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-700/60 dark:bg-slate-950/60 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-bold flex items-center gap-2 text-slate-800 dark:text-slate-200">
                          <FolderOpen size={16} className="text-ocean dark:text-mint" />
                          Session Attached Resources &amp; Downloads
                        </h4>
                        <span className="text-xs text-slate-400">
                          {loadingResources ? 'Loading...' : `${resources.length} file${resources.length === 1 ? '' : 's'}`}
                        </span>
                      </div>

                      {loadingResources ? (
                        <p className="text-xs text-slate-500 py-3 text-center">Loading resources for this session...</p>
                      ) : resources.length === 0 ? (
                        <p className="text-xs text-slate-500 py-2">
                          No downloadable materials or presentations were attached to this session by the instructor.
                        </p>
                      ) : (
                        <div className="grid gap-2">
                          {resources.map((res) => (
                            <div
                              key={res.id}
                              className="flex items-center justify-between rounded-lg bg-white p-3 border border-slate-200/80 dark:bg-slate-900 dark:border-slate-800 text-xs"
                            >
                              <div className="flex items-center gap-2.5 min-w-0">
                                <FileText size={16} className="text-ocean dark:text-mint shrink-0" />
                                <div className="truncate">
                                  <p className="font-semibold text-slate-800 dark:text-slate-100 truncate">{res.name}</p>
                                  <p className="text-[11px] text-slate-400">
                                    {res.file_size ? `${(res.file_size / 1024).toFixed(1)} KB` : 'Resource File'} &bull; Uploaded {res.uploaded_at?.slice(0, 10)}
                                  </p>
                                </div>
                              </div>
                              <a
                                href={staticUrl(res.url)}
                                target="_blank"
                                rel="noreferrer"
                                download
                                className="btn-soft text-xs py-1.5 px-3 flex items-center gap-1 shrink-0 font-medium"
                              >
                                <Download size={13} /> Download
                              </a>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

const DASHBOARD_JOB_KEY = 'edusense_dashboard_analysis_job'
const DASHBOARD_REPORT_KEY = 'edusense_dashboard_last_report'

export function InstructorDashboard() {
  const { t } = useLanguage()
  const [sessions, setSessions] = useState([])
  const [selectedSessionId, setSelectedSessionId] = useState('all')
  const [report, setReport] = useState(() => {
    try {
      const saved = sessionStorage.getItem(DASHBOARD_REPORT_KEY)
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  const [analyzing, setAnalyzing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMessage, setProgressMessage] = useState('')
  const [error, setError] = useState('')

  async function loadSessions() {
    try {
      const res = await api('/sessions')
      setSessions(Array.isArray(res) ? res : [])
    } catch (e) {
      setSessions([])
    }
  }

  useEffect(() => { loadSessions() }, [])

  const endedSessions = useMemo(() => sessions.filter((s) => s.status === 'ended'), [sessions])

  // Resume polling if an analysis job is running in background
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DASHBOARD_JOB_KEY)
      if (raw) {
        const stored = JSON.parse(raw)
        if (stored?.jobId) {
          pollAnalysisJob(stored.jobId)
        }
      }
    } catch {
      // ignore
    }
  }, [])

  async function pollAnalysisJob(jobId) {
    setAnalyzing(true)
    setError('')

    const MAX_ATTEMPTS = 120
    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      try {
        const res = await api(`/ai/job/${jobId}`)
        if (res.progress != null) setProgress(res.progress)
        if (res.message) setProgressMessage(res.message)

        if (res.status === 'done' && res.result) {
          setReport(res.result)
          try {
            sessionStorage.setItem(DASHBOARD_REPORT_KEY, JSON.stringify(res.result))
          } catch {}
          localStorage.removeItem(DASHBOARD_JOB_KEY)
          setAnalyzing(false)
          setProgress(100)
          return
        }
        if (res.status === 'error') {
          setError(res.error || 'Feedback loop analysis failed.')
          localStorage.removeItem(DASHBOARD_JOB_KEY)
          setAnalyzing(false)
          return
        }
      } catch (err) {
        if (attempt > 3) {
          setError(err.message || 'Error tracking background analysis.')
          localStorage.removeItem(DASHBOARD_JOB_KEY)
          setAnalyzing(false)
          return
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 1500))
    }

    setError('Analysis timed out. Please try again.')
    localStorage.removeItem(DASHBOARD_JOB_KEY)
    setAnalyzing(false)
  }

  async function analyze() {
    if (!sessions.length) {
      setError('No sessions found to run feedback loop.')
      return
    }

    // Enforce rule: feedback loop can ONLY be run on ended sessions
    if (selectedSessionId === 'all') {
      if (!endedSessions.length) {
        setError('Feedback loop is only available for ended sessions. None of your sessions have ended yet.')
        return
      }
    } else {
      const targetSession = sessions.find((s) => String(s.id) === String(selectedSessionId))
      if (targetSession && targetSession.status !== 'ended') {
        setError(`Feedback loop is only available for ended sessions. Session "${targetSession.title}" is currently ${targetSession.status}.`)
        return
      }
    }

    setAnalyzing(true)
    setProgress(10)
    setProgressMessage('Initializing background analysis...')
    setError('')

    try {
      const res = await api('/ai/recommendations/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: selectedSessionId }),
      })

      if (res.status === 'done' && res.result) {
        setReport(res.result)
        try {
          sessionStorage.setItem(DASHBOARD_REPORT_KEY, JSON.stringify(res.result))
        } catch {}
        setAnalyzing(false)
        setProgress(100)
        return
      }

      if (res.job_id) {
        localStorage.setItem(DASHBOARD_JOB_KEY, JSON.stringify({ jobId: res.job_id, startedAt: Date.now() }))
        pollAnalysisJob(res.job_id)
      } else {
        throw new Error('Could not queue feedback loop analysis.')
      }
    } catch (err) {
      setError(err.message || 'Failed to start feedback loop analysis.')
      setAnalyzing(false)
    }
  }

  return (
    <div className="page-shell space-y-6">
      <Hero title={t('dashboard.instructor')} />
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="panel space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-lg font-bold">{t('dashboard.managed')}</h2>
            <div className="flex flex-wrap items-center gap-2 sm:ms-auto">
              <select
                className="input py-1.5 text-xs min-w-[180px] flex-1 sm:flex-none"
                value={selectedSessionId}
                onChange={(e) => {
                  setSelectedSessionId(e.target.value)
                  setError('')
                }}
              >
                <option value="all">All Ended Sessions ({endedSessions.length})</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title} ({s.status})
                  </option>
                ))}
              </select>
              <button className="btn-primary py-1.5 px-4 text-xs whitespace-nowrap" type="button" onClick={analyze} disabled={analyzing}>
                {analyzing ? 'Analyzing...' : t('dashboard.feedbackLoop')}
              </button>
            </div>
          </div>
          {error && <p className="rounded-md bg-red-50 p-2.5 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-200">{error}</p>}
          <SessionList sessions={sessions} showEdit={true} onReload={loadSessions} />
        </div>
        <div className="panel">
          <h2 className="mb-4 text-lg font-bold">{t('dashboard.recommendations')}</h2>
          {analyzing ? (
            <div className="space-y-3 rounded-xl border border-teal-200 bg-teal-50/50 p-4 dark:border-teal-900/40 dark:bg-slate-800/40">
              <div className="flex items-center justify-between text-xs font-semibold text-ocean dark:text-mint">
                <span className="flex items-center gap-1.5"><Sparkles size={14} className="animate-spin text-teal-600" />{progressMessage || 'Analyzing student telemetry...'}</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                <div className="h-full bg-gradient-to-r from-ocean to-mint transition-all duration-300" style={{ width: `${Math.max(progress, 5)}%` }} />
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Running in background. You can navigate away to other tabs; your report will load automatically.
              </p>
            </div>
          ) : report ? (
            <ul className="space-y-2">
              {report.recommendations.recommendations.map((item) => (
                <li className="rounded-md bg-slate-100 p-3 text-sm dark:bg-slate-800" key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">{t('dashboard.runLoopHint')}</p>
          )}
        </div>
      </div>
      {report && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="panel"><EmotionDistribution data={report.emotion_report.distribution} /></div>
          <div className="panel"><EngagementLine data={report.engagement_report.attention_timeline} /></div>
        </div>
      )}
    </div>
  )
}

function Hero({ title }) {
  const { user } = useAuth()
  const { t } = useLanguage()
  return (
    <div className="rounded-lg bg-ocean p-6 text-white">
      <p className="text-sm text-teal-100">{title}</p>
      <h1 className="mt-1 text-3xl font-black">{t('dashboard.hello')}, {user?.name}</h1>
    </div>
  )
}

function Stats({ cards }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4">
      {cards.map(([label, value, Icon]) => (
        <div className="panel" key={label}>
          <Icon className="text-coral" />
          <p className="mt-3 text-2xl font-black">{value}</p>
          <p className="text-sm text-slate-500">{label}</p>
        </div>
      ))}
    </div>
  )
}

function HighlightCard({ icon: Icon, label, value }) {
  return (
    <div className="panel relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-ocean via-mint to-coral" />
      <Icon className="text-ocean dark:text-mint" />
      <p className="mt-3 text-2xl font-black">{value}</p>
      <p className="text-sm text-slate-500">{label}</p>
    </div>
  )
}

function SessionList({ sessions, join = false, emptyLabel = '', onReload, showUnregister = false, showEdit = false }) {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [editingSession, setEditingSession] = useState(null)
  const [editForm, setEditForm] = useState({})

  async function joinSession(id) {
    await api(`/sessions/${id}/join`, { method: 'POST' })
    onReload?.()
    navigate(`/student/sessions/${id}/live`)
  }

  async function unregister(sessionId) {
    await api(`/sessions/${sessionId}/join`, { method: 'DELETE' })
    onReload?.()
  }

  function handleEdit(e, session) {
    e.preventDefault()
    e.stopPropagation()
    setEditingSession(session)
    setEditForm({
      title: session.title,
      description: session.description || '',
      date: session.date,
      start_time: session.start_time,
      duration: session.duration,
      max_students: session.max_students
    })
  }

  async function saveEdit(e) {
    e.preventDefault()
    await api(`/sessions/${editingSession.id}`, { method: 'PUT', body: editForm })
    setEditingSession(null)
    onReload?.()
  }

  if (!sessions.length) return <p className="mt-4 text-sm text-slate-500">{emptyLabel}</p>
  return (
    <div className="mt-4 space-y-3">
      {sessions.map((session) => (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-200 bg-white/70 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/50" key={session.id}>
          <div>
            <p className="font-bold">{session.title}</p>
            <p className="text-sm text-slate-500">{session.date} | {session.start_time} | <span className="capitalize font-semibold text-ocean dark:text-mint">{session.status}</span></p>
            {session.description && <p className="mt-2 max-w-xl text-sm text-slate-600 dark:text-slate-300">{session.description}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {showEdit && session.status === 'pending' && (
              <button className="btn-soft" type="button" onClick={(e) => handleEdit(e, session)}>Edit</button>
            )}
            {showUnregister && session.status !== 'ongoing' && (
              <button className="btn-soft text-xs text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20" type="button" onClick={() => unregister(session.id)}>Unenroll</button>
            )}
            {join && session.status === 'ongoing' && (
              <button className="btn-primary text-xs flex items-center gap-1.5 py-1.5 px-3 font-bold" type="button" onClick={() => joinSession(session.id)}>
                <Video size={14} /> Join Live Now
              </button>
            )}
            {join && session.status !== 'ongoing' && (
              <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-500">
                Not Started Yet
              </span>
            )}
          </div>
        </div>
      ))}
      {editingSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setEditingSession(null)}>
          <form className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 dark:text-slate-100" onSubmit={saveEdit} onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold">Edit Session</h3>
            <input className="input w-full dark:bg-slate-800 dark:border-slate-700" placeholder="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} required />
            <textarea className="input w-full dark:bg-slate-800 dark:border-slate-700" placeholder="Description" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={3} />
            <input className="input w-full dark:bg-slate-800 dark:border-slate-700" type="date" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} required />
            <input className="input w-full dark:bg-slate-800 dark:border-slate-700" type="time" value={editForm.start_time} onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })} required />
            <input className="input w-full dark:bg-slate-800 dark:border-slate-700" type="number" placeholder="Duration (minutes)" value={editForm.duration} onChange={(e) => setEditForm({ ...editForm, duration: parseInt(e.target.value) })} />
            <input className="input w-full dark:bg-slate-800 dark:border-slate-700" type="number" placeholder="Max students" value={editForm.max_students || ''} onChange={(e) => setEditForm({ ...editForm, max_students: e.target.value ? parseInt(e.target.value) : null })} />
            <div className="flex gap-2 pt-2">
              <button className="btn-primary flex-1" type="submit">Save Changes</button>
              <button className="btn-soft flex-1" type="button" onClick={() => setEditingSession(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

function SessionCatalog({ sessions, onReload }) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  async function enroll(sessionId) {
    await api(`/sessions/${sessionId}/join`, { method: 'POST' })
    await onReload?.()
  }

  const filtered = sessions.filter(s => 
    s.title.toLowerCase().includes(search.toLowerCase()) || 
    (s.description && s.description.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <div className="grid gap-4">
      <div className="relative">
        <Search className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
        <input 
          type="text" 
          placeholder="Search for a topic or session name..." 
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input ps-10 w-full"
        />
      </div>
      
      {!sessions.length ? (
        <p className="text-sm text-slate-500 mt-2">All open sessions are already in your list.</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-slate-500 mt-2">No sessions match your search.</p>
      ) : (
        filtered.map((session) => (
        <article key={session.id} className="group overflow-hidden rounded-[1.5rem] border border-slate-200 bg-gradient-to-br from-white via-white to-teal-50/60 p-5 shadow-sm transition hover:-translate-y-1 hover:shadow-xl dark:border-slate-700 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-2">
              <div className="inline-flex rounded-full bg-ocean/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-ocean dark:bg-mint/10 dark:text-mint">{session.status}</div>
              <h3 className="text-xl font-black">{session.title}</h3>
              <p className="max-w-2xl text-sm text-slate-600 dark:text-slate-300">{session.description || 'A live learning session ready for registration.'}</p>
            </div>
            {session.max_students != null && Number(session.max_students) > 0 && (
              <div className="rounded-2xl bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-200">
                {session.available_seats} seats left
              </div>
            )}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-500">
            <span>{session.date}</span>
            <span>{session.start_time}</span>
            <span>{session.duration} min</span>
            <span>{session.registration_count} registered</span>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button className="btn-primary flex items-center gap-2 py-2 px-4 text-sm font-bold" type="button" onClick={() => enroll(session.id)}>
              <BookOpen size={16} /> Enroll in Session
            </button>
            <span className="text-xs text-slate-500">Clicking enroll adds this session to your Upcoming list</span>
          </div>
        </article>
      )))}
    </div>
  )
}

export function About() { return <Info titleKey="appName" textKey="landing.subtitle" /> }
export function Settings() {
  const { t, lang, setLang } = useLanguage()
  const [prefs, setPrefs] = useState(() => ({
    emailNotifications: localStorage.getItem('edusense_email_notifications') !== 'false',
    ambientMotion: localStorage.getItem('edusense_ambient_motion') !== 'false',
    compactCards: localStorage.getItem('edusense_compact_cards') === 'true',
    accent: localStorage.getItem('edusense_accent') || 'teal',
  }))

  useEffect(() => {
    localStorage.setItem('edusense_email_notifications', String(prefs.emailNotifications))
    localStorage.setItem('edusense_ambient_motion', String(prefs.ambientMotion))
    localStorage.setItem('edusense_compact_cards', String(prefs.compactCards))
    localStorage.setItem('edusense_accent', prefs.accent)
    document.documentElement.dataset.compact = prefs.compactCards ? 'true' : 'false'
  }, [prefs])

  return (
    <div className="page-shell max-w-4xl space-y-6">
      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black">{t('settingsPage.title')}</h1>
            <p className="mt-2 max-w-2xl text-slate-600 dark:text-slate-300">{t('settingsPage.text')}</p>
          </div>
          <div className="rounded-2xl bg-gradient-to-br from-ocean to-teal-600 px-5 py-4 text-white shadow-lg">
            <p className="text-xs uppercase tracking-[0.2em] text-teal-100">EduSense</p>
            <p className="mt-1 text-lg font-bold">Personalized experience</p>
          </div>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="panel space-y-4">
          <div className="flex items-center gap-3 text-lg font-bold"><Palette size={20} />Appearance</div>
          <label className="block space-y-2">
            <span className="text-sm font-semibold">{t('settingsPage.language')}</span>
            <select className="input" value={lang} onChange={(e) => setLang(e.target.value)}>
              <option value="en">English</option>
              <option value="ar">العربية</option>
            </select>
            <p className="text-xs text-slate-500">{t('settingsPage.languageHint')}</p>
          </label>
          <label className="space-y-2">
            <span className="text-sm font-semibold">Accent</span>
            <select className="input" value={prefs.accent} onChange={(e) => setPrefs({ ...prefs, accent: e.target.value })}>
              <option value="teal">Teal Ocean</option>
              <option value="blue">Calm Blue</option>
              <option value="sunset">Sunset Coral</option>
            </select>
          </label>
          <ToggleRow icon={Sparkles} label="Animated background" checked={prefs.ambientMotion} onChange={(value) => setPrefs({ ...prefs, ambientMotion: value })} />
          <ToggleRow icon={BookOpen} label="Compact cards" checked={prefs.compactCards} onChange={(value) => setPrefs({ ...prefs, compactCards: value })} />
        </div>
        <div className="panel space-y-4">
          <div className="flex items-center gap-3 text-lg font-bold"><BellRing size={20} />Preferences</div>
          <ToggleRow icon={BellRing} label="Email notifications" checked={prefs.emailNotifications} onChange={(value) => setPrefs({ ...prefs, emailNotifications: value })} />
        </div>
      </div>
    </div>
  )
}
export function Support() { return <Info titleKey="nav.reports" textKey="settingsPage.text" /> }
export function NotFound() { return <Info titleKey="error.somethingWrong" textKey="error.goHome" /> }

function ToggleRow({ icon: Icon, label, checked, onChange }) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 px-4 py-3 dark:border-slate-700">
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800"><Icon size={18} /></div>
        <span className="font-semibold">{label}</span>
      </div>
      <button
        type="button"
        aria-pressed={checked}
        className={`relative h-8 w-14 rounded-full transition ${checked ? 'bg-ocean dark:bg-mint' : 'bg-slate-300 dark:bg-slate-700'}`}
        onClick={() => onChange(!checked)}
      >
        <span className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow transition ${checked ? 'end-1' : 'start-1'}`} />
      </button>
    </label>
  )
}

function StudentStats({ enrolled, upcoming, completed, live }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div className="panel">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Enrolled sessions</p>
        <p className="mt-3 text-3xl font-black">{enrolled}</p>
      </div>
      <div className="panel">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Upcoming</p>
        <p className="mt-3 text-3xl font-black">{upcoming}</p>
      </div>
      <div className="panel">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Completed</p>
        <p className="mt-3 text-3xl font-black">{completed}</p>
      </div>
      <div className="panel">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Live now</p>
        <p className="mt-3 text-3xl font-black">{live}</p>
      </div>
    </div>
  )
}

function Info({ titleKey, textKey }) {
  const { t } = useLanguage()
  return (
    <div className="panel page-shell">
      <h1 className="text-2xl font-black">{t(titleKey)}</h1>
      <p className="mt-3 text-slate-600 dark:text-slate-300">{t(textKey)}</p>
    </div>
  )
}
