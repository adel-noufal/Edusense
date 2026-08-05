import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Activity, BellRing, BookMarked, BookOpen, Clock3, Eye, Palette, Search, Sparkles, Users, Video } from 'lucide-react'
import { EmotionDistribution, EngagementLine } from '../components/Charts'
import WebcamEmotion from '../components/WebcamEmotion'
import { api } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'

export function StudentDashboard() {
  const { t } = useLanguage()
  const location = useLocation()
  const mode = location.pathname.includes('/history') ? 'history' : location.pathname.includes('/upcoming') ? 'upcoming' : location.pathname.includes('/browse') ? 'browse' : 'all'
  const [sessions, setSessions] = useState([])
  const [browseData, setBrowseData] = useState({ sessions: [], summary: null })
  const [analytics, setAnalytics] = useState(null)
  const [error, setError] = useState('')

  async function loadSessions() {
    try {
      const [allSessions, browse] = await Promise.all([
        api('/sessions'),
        api('/sessions/browse'),
      ])
      setSessions(Array.isArray(allSessions) ? allSessions : [])
      setBrowseData(browse || { sessions: [], summary: null })
      setError('')
    } catch (err) {
      setSessions([])
      setBrowseData({ sessions: [], summary: null })
      setError(err.message)
    }
  }

  useEffect(() => { loadSessions() }, [])

  const filtered = sessions.filter((session) => {
    if (mode === 'upcoming') return ['pending', 'ongoing'].includes(session.status)
    if (mode === 'history') return ['ended', 'cancelled'].includes(session.status)
    return true
  })

  const registeredSessions = useMemo(
    () => browseData.sessions.filter((session) => session.is_registered),
    [browseData.sessions],
  )
  const openCatalog = useMemo(
    () => browseData.sessions.filter((session) => !session.is_registered),
    [browseData.sessions],
  )
  const firstLive = sessions.find((session) => session.status === 'ongoing') || registeredSessions[0] || filtered[0]
  useEffect(() => {
    if (firstLive) api(`/ai/engagement/${firstLive.id}`).then(setAnalytics).catch(() => setAnalytics(null))
  }, [firstLive])

  const titles = { all: t('dashboard.student'), upcoming: t('dashboard.upcoming'), history: t('dashboard.historyTitle'), browse: t('nav.browse') }

  return (
    <div className="page-shell space-y-6">
      <Hero title={titles[mode]} />
      <Stats sessions={mode === 'upcoming' ? browseData.summary?.available || 0 : sessions.length} />
      {mode === 'upcoming' && browseData.summary && (
        <div className="grid gap-4 md:grid-cols-3">
          <HighlightCard icon={BookMarked} label="Available Sessions" value={browseData.summary.available} />
          <HighlightCard icon={Sparkles} label="Registered" value={browseData.summary.registered} />
          <HighlightCard icon={Clock3} label="Live Now" value={browseData.summary.live_now} />
        </div>
      )}
      {error && <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200">{error}</p>}
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="panel">
          <h2 className="mb-4 text-lg font-bold">{mode === 'upcoming' ? 'Your Registered Sessions' : titles[mode]}</h2>
          {mode !== 'browse' && (
            <SessionList sessions={mode === 'upcoming' ? registeredSessions : filtered} join={mode !== 'history'} showUnregister={mode === 'upcoming'} emptyLabel={mode === 'history' ? t('dashboard.noHistory') : 'You have not registered for any sessions yet.'} onReload={loadSessions} />
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
          <RecommendedCourses sessions={browseData.sessions} onReload={loadSessions} />
        ) : (
          firstLive && mode !== 'history' && <WebcamEmotion sessionId={firstLive.id} />
        )}
      </div>
      {analytics && (
        <div className="panel">
          <h2 className="mb-4 text-lg font-bold">{t('dashboard.attention')}</h2>
          <EngagementLine data={analytics.attention_timeline} />
        </div>
      )}
    </div>
  )
}

export function InstructorDashboard() {
  const { t } = useLanguage()
  const [sessions, setSessions] = useState([])
  const [report, setReport] = useState(null)
  async function loadSessions() {
    try {
      const res = await api('/sessions')
      setSessions(Array.isArray(res) ? res : [])
    } catch (e) {
      setSessions([])
    }
  }

  useEffect(() => { loadSessions() }, [])

  async function analyze() {
    if (sessions[0]) setReport(await api(`/ai/recommendations/${sessions[0].id}`))
  }

  return (
    <div className="page-shell space-y-6">
      <Hero title={t('dashboard.instructor')} />
      <Stats sessions={sessions.length} />
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="panel">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-bold">{t('dashboard.managed')}</h2>
            <button className="btn-primary" type="button" onClick={analyze}>{t('dashboard.feedbackLoop')}</button>
          </div>
          <SessionList sessions={sessions} showEdit={true} onReload={loadSessions} />
        </div>
        <div className="panel">
          <h2 className="mb-4 text-lg font-bold">{t('dashboard.recommendations')}</h2>
          {report ? (
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

function Stats({ sessions }) {
  const { t } = useLanguage()
  const cards = [
    [t('dashboard.sessions'), sessions ?? 0, BookOpen],
    [t('dashboard.engagement'), 78, Activity],
    [t('dashboard.videos'), 9, Video],
    [t('dashboard.students'), 128, Users],
  ]
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

  async function handleEdit(session) {
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

  async function saveEdit() {
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
            <p className="text-sm text-slate-500">{session.date} | {session.start_time} | {session.status}</p>
            {session.description && <p className="mt-2 max-w-xl text-sm text-slate-600 dark:text-slate-300">{session.description}</p>}
          </div>
          <div className="flex gap-2">
            {showEdit && session.status === 'pending' && (
              <button className="btn-soft" type="button" onClick={() => handleEdit(session)}>Edit</button>
            )}
            {showUnregister && session.status !== 'ongoing' && (
              <button className="btn-soft text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20" type="button" onClick={() => unregister(session.id)}>Unregister</button>
            )}
            {join && ['ongoing', 'pending'].includes(session.status) ? (
              <button className="btn-soft" type="button" onClick={() => joinSession(session.id)}>{t('dashboard.join')}</button>
            ) : (
              <span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold uppercase text-slate-500 dark:bg-slate-800">Completed</span>
            )}
          </div>
        </div>
      ))}
      {editingSession && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-lg font-bold">Edit Session</h3>
            <input className="input w-full" placeholder="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
            <textarea className="input w-full" placeholder="Description" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={3} />
            <input className="input w-full" type="date" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} />
            <input className="input w-full" type="time" value={editForm.start_time} onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })} />
            <input className="input w-full" type="number" placeholder="Duration (minutes)" value={editForm.duration} onChange={(e) => setEditForm({ ...editForm, duration: parseInt(e.target.value) })} />
            <input className="input w-full" type="number" placeholder="Max students" value={editForm.max_students || ''} onChange={(e) => setEditForm({ ...editForm, max_students: e.target.value ? parseInt(e.target.value) : null })} />
            <div className="flex gap-2">
              <button className="btn-soft flex-1" onClick={saveEdit}>Save</button>
              <button className="btn-soft flex-1" onClick={() => setEditingSession(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SessionCatalog({ sessions, onReload }) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  async function register(sessionId, isLive) {
    await api(`/sessions/${sessionId}/join`, { method: 'POST' })
    await onReload?.()
    if (isLive) navigate(`/student/sessions/${sessionId}/live`)
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
            <div className="rounded-2xl bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-200">
              {session.max_students !== null ? `${session.available_seats} seats left` : 'Open seats'}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-500">
            <span>{session.date}</span>
            <span>{session.start_time}</span>
            <span>{session.duration} min</span>
            <span>{session.registration_count} registered</span>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <button className="btn-primary" type="button" onClick={() => register(session.id, session.status === 'ongoing')}>
              {session.status === 'ongoing' ? 'Join Live Now' : 'Register Session'}
            </button>
            <button className="btn-soft" type="button" onClick={() => navigate(`/student/sessions/${session.id}/live`)}>
              <Eye size={16} />Preview Room
            </button>
          </div>
        </article>
      )))}
    </div>
  )
}

function RecommendedCourses({ sessions, onReload }) {
  const navigate = useNavigate()
  
  async function register(sessionId) {
    await api(`/sessions/${sessionId}/join`, { method: 'POST' })
    await onReload?.()
  }

  // Curate recommendations from all sessions
  const recommendations = sessions.map((session, idx) => ({
    ...session,
    rating: (4.6 + (idx * 0.1) % 0.4).toFixed(1),
    reviews: 24 + (idx * 7) % 40,
    level: idx % 2 === 0 ? 'Beginner' : 'Intermediate',
  }))

  if (!recommendations.length) {
    return (
      <div className="panel space-y-4">
        <h2 className="text-lg font-bold">Recommended Courses</h2>
        <p className="text-sm text-slate-500">No courses available for recommendation at the moment.</p>
      </div>
    )
  }

  return (
    <div className="panel space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Recommended Courses</h2>
        <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-bold text-ocean dark:bg-slate-800 dark:text-mint">
          AI Curated
        </span>
      </div>
      <div className="space-y-4">
        {recommendations.slice(0, 3).map((course) => (
          <div key={course.id} className="relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white p-4 transition-all hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="inline-block rounded-md bg-teal-50 px-2 py-0.5 text-25xs font-bold uppercase tracking-wider text-ocean dark:bg-slate-850 dark:text-mint text-[10px]">
                  {course.level}
                </span>
                <h4 className="mt-1 font-bold text-slate-900 dark:text-slate-100">{course.title}</h4>
                <p className="mt-1 text-xs text-slate-500">Duration: {course.duration} mins &middot; ⭐ {course.rating} ({course.reviews} reviews)</p>
              </div>
              <div className="shrink-0">
                {course.is_registered ? (
                  <span className="inline-flex items-center rounded-full bg-teal-50 dark:bg-slate-800 px-2.5 py-0.5 text-xs font-semibold text-ocean dark:text-mint">
                    Enrolled
                  </span>
                ) : (
                  <button 
                    onClick={() => register(course.id)}
                    className="btn-soft text-xs py-1.5 px-3"
                    type="button"
                  >
                    Enroll
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
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
          <ToggleRow icon={Eye} label="Focus mode hints" checked={!prefs.compactCards} onChange={(value) => setPrefs({ ...prefs, compactCards: !value })} />
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

function Info({ titleKey, textKey }) {
  const { t } = useLanguage()
  return (
    <div className="panel page-shell">
      <h1 className="text-2xl font-black">{t(titleKey)}</h1>
      <p className="mt-3 text-slate-600 dark:text-slate-300">{t(textKey)}</p>
    </div>
  )
}
