import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Mic, MicOff, MonitorUp, PhoneOff, Users, Video, VideoOff } from 'lucide-react'
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

  const localVideo = useRef(null)
  const shareVideo = useRef(null)
  const shareStream = useRef(null)
  const camStream = useRef(null)
  const shareInterval = useRef(null)
  const emotionInterval = useRef(null)

  useEffect(() => {
    api(`/sessions/${sessionId}/live`).then(setSession).catch((err) => setError(err.message))
    if (isInstructor) {
      api(`/sessions/${sessionId}/attendees`).then(setAttendees).catch(() => {})
      const poll = setInterval(async () => {
        try {
          setEmotions(await api(`/emotions/session/${sessionId}`))
          setDistribution(await api(`/emotions/session/${sessionId}/distribution`))
          setAttendees(await api(`/sessions/${sessionId}/attendees`))
        } catch { /* ignore */ }
      }, 3000)
      return () => clearInterval(poll)
    } else {
      api(`/sessions/${sessionId}/join-live`, { method: 'POST' }).catch(() => {})
    }
    const pollShare = setInterval(() => {
      setSharePreview(`${staticUrl(`/static/live/session-${sessionId}.jpg`)}?t=${Date.now()}`)
    }, 2000)
    return () => clearInterval(pollShare)
  }, [sessionId, isInstructor])

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

  async function endLive() {
    if (isInstructor) {
      await api(`/sessions/${sessionId}/end`, { method: 'POST' })
      stopShare()
      navigate('/instructor/sessions')
    } else {
      navigate('/student/upcoming')
    }
  }

  if (error && !session) {
    return (
      <div className="panel page-shell max-w-lg space-y-4">
        <p className="text-red-600">{error}</p>
        <Link className="btn-soft" to={isInstructor ? '/instructor/sessions' : '/student'}>{t('live.back')}</Link>
      </div>
    )
  }

  return (
    <div className="page-shell space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{t('live.room')}</p>
          <h1 className="text-xl font-black sm:text-2xl">{session?.title || t('live.loading')}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
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
