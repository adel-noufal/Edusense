import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Calendar, Clock, Info, Mic, MicOff, MonitorUp, PhoneOff, Play, Users, Video, VideoOff, XCircle } from 'lucide-react'
import { api, staticUrl } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'

export default function LiveSessionRoom() {
  const { sessionId } = useParams()
  const { user } = useAuth()
  const { t } = useLanguage()
  const navigate = useNavigate()
  const isInstructor = user?.role === 'instructor'

  const [session, setSession] = useState(null)
  const [emotions, setEmotions] = useState([])
  const [distribution, setDistribution] = useState(null)
  const [error, setError] = useState('')
  const [sharing, setSharing] = useState(false)
  const [camOn, setCamOn] = useState(false)
  const [micOn, setMicOn] = useState(true)
  const [lastEmotion, setLastEmotion] = useState(null)
  const [sharePreview, setSharePreview] = useState('')
  const [attendees, setAttendees] = useState([])
  const [cancelling, setCancelling] = useState(false)
  const [prepSeconds, setPrepSeconds] = useState(null)

  const localVideo = useRef(null)
  const shareVideo = useRef(null)
  const shareStream = useRef(null)
  const camStream = useRef(null)
  const shareInterval = useRef(null)
  const emotionInterval = useRef(null)

  async function fetchSession() {
    try {
      const data = await api(`/sessions/${sessionId}/live`)
      setSession(data)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    fetchSession()
    const sessionPoll = setInterval(fetchSession, 3000)
    
    if (isInstructor) {
      api(`/sessions/${sessionId}/attendees`).then(setAttendees).catch(() => {})
      const poll = setInterval(async () => {
        try {
          setEmotions(await api(`/emotions/session/${sessionId}`))
          setDistribution(await api(`/emotions/session/${sessionId}/distribution`))
          setAttendees(await api(`/sessions/${sessionId}/attendees`))
        } catch { /* ignore */ }
      }, 3000)
      return () => {
        clearInterval(poll)
        clearInterval(sessionPoll)
      }
    } else {
      api(`/sessions/${sessionId}/join-live`).catch(() => {})
    }

    const pollShare = setInterval(() => {
      setSharePreview(`${staticUrl(`/static/live/session-${sessionId}.jpg`)}?t=${Date.now()}`)
    }, 2000)

    return () => {
      clearInterval(pollShare)
      clearInterval(sessionPoll)
    }
  }, [sessionId, isInstructor])

  // Countdown timer for 15-minute preparation window
  useEffect(() => {
    if (!session || session.status !== 'preparing' || !session.prep_start_time) {
      setPrepSeconds(null)
      return
    }

    function calculateRemaining() {
      const prepStart = new Date(session.prep_start_time).getTime()
      const now = Date.now()
      const elapsedSeconds = Math.floor((now - prepStart) / 1000)
      const remaining = Math.max(0, 900 - elapsedSeconds)
      setPrepSeconds(remaining)

      if (remaining <= 0 && isInstructor) {
        // Force session live when timer expires
        api(`/sessions/${sessionId}/start?force_go_live=true`, { method: 'POST' }).then(fetchSession).catch(() => {})
      }
    }

    calculateRemaining()
    const timer = setInterval(calculateRemaining, 1000)
    return () => clearInterval(timer)
  }, [session?.status, session?.prep_start_time, sessionId, isInstructor])

  useEffect(() => () => {
    clearInterval(shareInterval.current)
    clearInterval(emotionInterval.current)
    shareStream.current?.getTracks().forEach((track) => track.stop())
    camStream.current?.getTracks().forEach((track) => track.stop())
  }, [])

  async function startShare() {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false })
      shareStream.current = stream
      if (shareVideo.current) shareVideo.current.srcObject = stream
      setSharing(true)
      shareInterval.current = setInterval(captureShareFrame, 2000)
      stream.getVideoTracks()[0].onended = () => stopShare()
    } catch (err) {
      setError(err.message || t('live.shareFailed'))
    }
  }

  async function captureShareFrame() {
    if (!shareVideo.current) return
    const canvas = document.createElement('canvas')
    canvas.width = 1280
    canvas.height = 720
    canvas.getContext('2d').drawImage(shareVideo.current, 0, 0, canvas.width, canvas.height)
    await api(`/sessions/${sessionId}/share-frame`, {
      method: 'POST',
      body: JSON.stringify({ image: canvas.toDataURL('image/jpeg', 0.7) }),
    })
  }

  function stopShare() {
    clearInterval(shareInterval.current)
    shareStream.current?.getTracks().forEach((track) => track.stop())
    setSharing(false)
  }

  async function toggleCam() {
    if (camOn) {
      camStream.current?.getTracks().forEach((track) => track.stop())
      setCamOn(false)
      clearInterval(emotionInterval.current)
      return
    }
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
    camStream.current = stream
    if (localVideo.current) localVideo.current.srcObject = stream
    setCamOn(true)
    if (!isInstructor) {
      emotionInterval.current = setInterval(analyzeEmotion, 5000)
      analyzeEmotion()
    }
  }

  async function analyzeEmotion() {
    if (!localVideo.current || !camOn) return
    const canvas = document.createElement('canvas')
    canvas.width = 480
    canvas.height = 360
    canvas.getContext('2d').drawImage(localVideo.current, 0, 0, 480, 360)
    const result = await api('/emotions/analyze', {
      method: 'POST',
      body: JSON.stringify({ session_id: Number(sessionId), image: canvas.toDataURL('image/jpeg') }),
    })
    setLastEmotion(result)
  }

  async function handleInstructorStartPrep() {
    try {
      await api(`/sessions/${sessionId}/start`, { method: 'POST' })
      await fetchSession()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleGoLiveNow() {
    try {
      await api(`/sessions/${sessionId}/start?force_go_live=true`, { method: 'POST' })
      await fetchSession()
    } catch (err) {
      setError(err.message)
    }
  }

  async function cancelStudentEnrollment() {
    if (!window.confirm('Are you sure you want to cancel your enrollment for this session?')) return
    setCancelling(true)
    try {
      await api(`/sessions/${sessionId}/join`, { method: 'DELETE' })
      navigate('/student/upcoming')
    } catch (err) {
      setError(err.message)
      setCancelling(false)
    }
  }

  async function endLive() {
    if (isInstructor) {
      await api(`/sessions/${sessionId}/end`, { method: 'POST' })
      stopShare()
      navigate('/instructor/sessions')
    } else {
      navigate('/student/upcoming')
    }
  }

  function formatTimer(totalSecs) {
    if (totalSecs == null) return '15:00'
    const mins = Math.floor(totalSecs / 60)
    const secs = totalSecs % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }

  if (error && !session) {
    return (
      <div className="panel page-shell max-w-lg space-y-4">
        <p className="text-red-600">{error}</p>
        <Link className="btn-soft" to={isInstructor ? '/instructor/sessions' : '/student'}>{t('live.back')}</Link>
      </div>
    )
  }

  const isSessionLive = session?.status === 'ongoing'
  const isPreparing = session?.status === 'preparing'

  // STUDENT VIEW BEFORE MEETING STARTS (or during prep timer)
  if (!isInstructor && !isSessionLive) {
    return (
      <div className="page-shell max-w-3xl space-y-6 mx-auto">
        <div className="flex items-center justify-between">
          <Link className="btn-soft" to="/student/upcoming">&larr; Back to Dashboard</Link>
          <span className="rounded-full bg-amber-100 dark:bg-amber-950/50 px-3 py-1 text-xs font-bold text-amber-800 dark:text-amber-300 uppercase tracking-wide">
            {isPreparing ? 'Preparation Phase' : 'Session Not Started'}
          </span>
        </div>

        {/* Dynamic status banner */}
        {isPreparing ? (
          <div className="rounded-2xl border border-emerald-300 bg-gradient-to-r from-emerald-50 to-teal-50 p-6 text-emerald-950 shadow-md dark:border-emerald-800 dark:from-emerald-950/40 dark:to-teal-950/40 dark:text-emerald-100">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="space-y-1 text-center sm:text-start">
                <p className="text-xs uppercase font-extrabold tracking-wider text-emerald-700 dark:text-emerald-300">Instructor is preparing the room</p>
                <h2 className="text-xl font-black">Session starts in {formatTimer(prepSeconds)}</h2>
                <p className="text-xs text-emerald-700 dark:text-emerald-300">The instructor is setting up cameras, slides, and microphones. Stay on this page — the meeting will open automatically!</p>
              </div>
              <div className="rounded-2xl bg-emerald-600 px-6 py-4 text-center font-mono text-3xl font-black text-white shadow-inner shrink-0">
                {formatTimer(prepSeconds)}
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-5 text-blue-900 shadow-sm dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-200">
            <div className="flex items-start gap-3">
              <Info className="shrink-0 text-blue-600 dark:text-blue-400 mt-0.5" size={20} />
              <div>
                <h3 className="font-bold text-base">The session still didn't start</h3>
                <p className="mt-1 text-xs leading-5">The instructor has not started the session yet. You can review the details below while you wait, or cancel your enrollment if you cannot make it.</p>
              </div>
            </div>
          </div>
        )}

        {/* Session details panel */}
        <div className="panel space-y-6">
          <div>
            <span className="inline-block rounded-md bg-ocean/10 px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-ocean dark:bg-mint/10 dark:text-mint mb-2">Enrolled Session</span>
            <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-slate-100">{session?.title}</h1>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
              <p className="text-xs text-slate-500 font-semibold flex items-center gap-1.5"><Users size={14} />Instructor</p>
              <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">{session?.instructor_name || 'Assigned Instructor'}</p>
            </div>
            <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
              <p className="text-xs text-slate-500 font-semibold flex items-center gap-1.5"><Users size={14} />Enrolled Students</p>
              <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">{session?.registration_count || 1} {session?.max_students ? `/ ${session.max_students}` : ''} Enrolled</p>
            </div>
            <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
              <p className="text-xs text-slate-500 font-semibold flex items-center gap-1.5"><Calendar size={14} />Scheduled Time</p>
              <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">{session?.date} @ {session?.start_time}</p>
            </div>
          </div>

          <div className="space-y-2 border-t border-slate-100 dark:border-slate-800 pt-4">
            <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">About the Session</h3>
            <p className="text-sm leading-6 text-slate-600 dark:text-slate-400">
              {session?.description || 'No detailed explanation provided for this session yet.'}
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 dark:border-slate-800 pt-4">
            <p className="text-xs text-slate-500">You can cancel your enrollment at any time before the session starts.</p>
            <button
              type="button"
              onClick={cancelStudentEnrollment}
              disabled={cancelling}
              className="btn-soft text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center gap-2"
            >
              <XCircle size={16} />
              {cancelling ? 'Cancelling...' : 'Cancel Session Enroll'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-shell space-y-4">
      {/* 15-Minute Instructor Prep Mode Notification Banner */}
      {isInstructor && isPreparing && (
        <div className="rounded-2xl border border-teal-300 bg-gradient-to-r from-teal-500 to-ocean p-4 text-white shadow-lg flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-extrabold uppercase tracking-widest text-teal-100">15-Minute Preparation Mode Active</p>
            <h3 className="text-lg font-black">Prepare presentations, cameras & mic ({formatTimer(prepSeconds)})</h3>
            <p className="text-xs text-teal-100">Students viewing the room see the 15-minute countdown clock. When ready, click Go Live Now to start immediately.</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-2xl font-black bg-black/30 px-3 py-1.5 rounded-xl border border-white/20">
              {formatTimer(prepSeconds)}
            </span>
            <button type="button" className="btn-primary bg-white text-ocean hover:bg-teal-50 font-bold text-xs py-2.5 px-4" onClick={handleGoLiveNow}>
              <Play size={14} className="fill-ocean inline me-1" /> Go Live Now
            </button>
          </div>
        </div>
      )}

      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{t('live.room')}</p>
          <h1 className="text-xl font-black sm:text-2xl">{session?.title || t('live.loading')}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {isInstructor && !isPreparing && !isSessionLive && (
            <button type="button" className="btn-primary py-2 px-4 text-xs font-bold" onClick={handleInstructorStartPrep}>
              <Play size={16} className="inline me-1" /> Start Session (15-min Prep)
            </button>
          )}
          {isInstructor && (
            <button type="button" className={`btn-soft ${sharing ? 'ring-2 ring-mint' : ''}`} onClick={sharing ? stopShare : startShare}>
              <MonitorUp size={18} />{sharing ? t('live.stopShare') : t('live.shareScreen')}
            </button>
          )}
          <button type="button" className="btn-soft" onClick={toggleCam}>
            {camOn ? <VideoOff size={18} /> : <Video size={18} />}{camOn ? t('live.camOff') : t('live.camOn')}
          </button>
          <button type="button" className="btn-soft" onClick={() => setMicOn(!micOn)}>
            {micOn ? <Mic size={18} /> : <MicOff size={18} />}
          </button>
          <button type="button" className="btn-primary bg-red-600 hover:bg-red-700" onClick={endLive}>
            <PhoneOff size={18} />{isInstructor ? t('live.endSession') : t('live.leave')}
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="panel space-y-3 p-0 overflow-hidden">
          {isInstructor ? (
            <>
              <video ref={shareVideo} autoPlay muted playsInline className="aspect-video w-full bg-slate-950 object-contain" />
              {!sharing && (
                <p className="p-4 text-sm text-slate-500">{t('live.shareHint')}</p>
              )}
            </>
          ) : (
            <>
              {sharePreview ? (
                <img src={sharePreview} alt={t('live.instructorScreen')} className="aspect-video w-full bg-slate-950 object-contain" onError={() => setSharePreview('')} />
              ) : (
                <div className="flex aspect-video items-center justify-center bg-slate-950 text-slate-400">{t('live.waitingShare')}</div>
              )}
            </>
          )}
        </div>

        <aside className="space-y-4">
          <div className="panel space-y-3">
            <div className="flex items-center gap-2 font-bold"><Users size={18} />{t('live.participants')}</div>
            <video ref={localVideo} autoPlay muted playsInline className="aspect-video w-full rounded-lg bg-slate-900 object-cover" />
            {!isInstructor && lastEmotion && (
              <p className="rounded-md bg-teal-50 p-2 text-sm text-ocean dark:bg-slate-800 dark:text-mint">
                {lastEmotion.emotion} · {(lastEmotion.confidence * 100).toFixed(0)}%
              </p>
            )}
            {!isInstructor && <p className="text-xs text-slate-500">{t('live.studentHint')}</p>}
          </div>

          {isInstructor && (
            <>
              <div className="panel max-h-[220px] space-y-3 overflow-auto">
                <p className="font-bold flex items-center gap-2"><Users size={18} />Attending Students ({attendees.length})</p>
                <div className="space-y-1">
                  {attendees.map((student) => (
                    <div key={student.id} className="text-sm py-1.5 border-b border-slate-100 dark:border-slate-800 last:border-0 font-medium">
                      {student.name} <span className="text-xs text-slate-400">({student.email})</span>
                    </div>
                  ))}
                  {!attendees.length && <p className="text-sm text-slate-500">No students joined yet.</p>}
                </div>
              </div>

              <div className="panel max-h-[420px] space-y-3 overflow-auto">
                <p className="font-bold">{t('live.studentAnalysis')}</p>
                {distribution && (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(distribution.distribution || {}).map(([emotion, value]) => (
                      <div key={emotion} className="rounded-md bg-slate-100 p-2 dark:bg-slate-800">
                        <span className="font-semibold capitalize">{emotion}</span>
                        <span className="float-end">{value}%</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="space-y-2">
                  {emotions.slice(-12).reverse().map((log) => (
                    <div key={log.id} className="rounded-md border border-slate-200 p-2 text-sm dark:border-slate-700">
                      <span className="font-semibold capitalize">{log.emotion}</span>
                      <span className="text-slate-500"> · {(log.confidence * 100).toFixed(0)}%</span>
                      <span className="block text-xs text-slate-400">{new Date(log.timestamp).toLocaleTimeString()}</span>
                    </div>
                  ))}
                  {!emotions.length && <p className="text-sm text-slate-500">{t('live.noEmotions')}</p>}
                </div>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}

