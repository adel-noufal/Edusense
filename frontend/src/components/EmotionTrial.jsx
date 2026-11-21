import { useEffect, useRef, useState } from 'react'
import { Camera, CameraOff, Loader2, ScanFace, Zap } from 'lucide-react'
import { api } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { ConsentModal } from './ConsentModal'

const EMOTION_COLORS = {
  happy: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
  sad: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  angry: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  surprise: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200',
  fear: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200',
  disgust: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
}

export default function EmotionTrial() {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const timerRef = useRef(null)
  const busyRef = useRef(false)
  const { hasConsent, giveConsent } = useAuth()

  const [mode, setMode] = useState('live') // 'live' | 'photo'
  const [active, setActive] = useState(false)
  const [stream, setStream] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [consentOpen, setConsentOpen] = useState(false)
  const [camErrorKind, setCamErrorKind] = useState('') // 'denied' | 'in_use' | 'unavailable' | ''
  const [cameras, setCameras] = useState([])
  const [cameraId, setCameraId] = useState(() => localStorage.getItem('edusense_camera_id') || '')
  const historyRef = useRef([]) // last N per-frame probability vectors for smoothing

  function cameraErrorMessage(err) {
    const name = err?.name || ''
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
      setCamErrorKind('denied')
      return 'Camera permission was denied. Allow camera access in your browser settings and try again.'
    }
    if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') {
      setCamErrorKind('in_use')
      return 'The camera is already in use by another app or browser tab. Close it and try again.'
    }
    setCamErrorKind('unavailable')
    return err?.message || 'Camera unavailable. Check that a camera is connected.'
  }

  function stopCamera() {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setStream((s) => {
      s?.getTracks().forEach((t) => t.stop())
      return null
    })
    streamRef.current = null
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setActive(false)
    setCamErrorKind('')
  }

  // Attach the MediaStream to the <video> element once it is actually mounted.
  // The video element only exists after `active` flips true, so assigning
  // srcObject inside acquireCamera() hit a null ref — the black-box bug.
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream
      videoRef.current.play().catch(() => {})
    }
  }, [stream, active])

  // Full cleanup on unmount
  useEffect(() => () => stopCamera(), [])

  async function startCamera() {
    setError('')
    setCamErrorKind('')
    setResult(null)
    if (!hasConsent('emotion_detection')) {
      setConsentOpen(true)
      return
    }
    try {
      await acquireCamera()
    } catch (err) {
      setError(cameraErrorMessage(err))
    }
  }

  // Enumerate cameras once permission is granted (labels need an active stream)
  useEffect(() => {
    if (!active || !navigator.mediaDevices?.enumerateDevices) return
    navigator.mediaDevices.enumerateDevices()
      .then((devices) => {
        const cams = devices.filter((d) => d.kind === 'videoinput')
        setCameras(cams)
        if (cams.length && !cams.some((c) => c.deviceId === cameraId)) {
          setCameraId(cams[0].deviceId)
        }
      })
      .catch(() => {})
  }, [active])

  async function acquireCamera() {
    const constraints = {
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        ...(cameraId ? { deviceId: { exact: cameraId } } : {}),
      },
    }
    const mediaStream = await navigator.mediaDevices.getUserMedia(constraints)
    streamRef.current = mediaStream
    setStream(mediaStream)
    setActive(true)
    if (mode === 'live') scheduleLoop(mediaStream)
  }

  async function handleConsentAccept(consentType) {
    await giveConsent(consentType)
    // Modal closes itself after onAccept resolves; start the camera now.
    try {
      await acquireCamera()
    } catch (err) {
      setError(cameraErrorMessage(err))
    }
  }

  function scheduleLoop(stream) {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(() => {
      if (streamRef.current === stream && videoRef.current && !busyRef.current) {
        captureFrame(false)
      }
    }, 1000)
  }

  function switchMode(next) {
    setMode(next)
    setResult(null)
    if (!active) return
    if (next === 'live') {
      if (streamRef.current) scheduleLoop(streamRef.current)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  async function captureFrame(showResult = true) {
    const video = videoRef.current
    if (!video || video.readyState < 2 || busyRef.current) return
    busyRef.current = true
    setAnalyzing(true)
    try {
      const canvas = document.createElement('canvas')
      canvas.width = 320
      canvas.height = 240
      canvas.getContext('2d').drawImage(video, 0, 0, 320, 240)
      const image = canvas.toDataURL('image/jpeg', 0.7)
      const res = await api('/emotions/analyze-trial', { method: 'POST', body: { image } })
      setResult(smoothResult(res))
      setError('')
    } catch (err) {
      if (showResult) setError(err.message || 'Analysis failed.')
    } finally {
      busyRef.current = false
      setAnalyzing(false)
    }
  }

  // Temporal smoothing: average per-emotion probabilities over the last 4
  // frames so a single noisy frame can't flip the displayed emotion.
  function smoothResult(res) {
    if (!res?.face_detected) {
      historyRef.current = []
      return { ...res, smoothed: true }
    }
    const top = res.top_emotions || []
    const vec = {}
    top.forEach((t) => { vec[t.emotion] = t.confidence })
    historyRef.current = [...historyRef.current, vec].slice(-4)
    const avg = {}
    historyRef.current.forEach((v) => {
      Object.entries(v).forEach(([k, val]) => { avg[k] = (avg[k] || 0) + val / historyRef.current.length })
    })
    const sorted = Object.entries(avg).sort((a, b) => b[1] - a[1])
    const best = sorted[0] || [res.emotion, res.confidence || 0]
    const uncertain = (best[1] || 0) < 0.45
    return {
      ...res,
      emotion: uncertain ? 'uncertain' : best[0],
      confidence: best[1] || 0,
      top_emotions: sorted.slice(0, 3).map(([emotion, confidence]) => ({ emotion, confidence })),
      uncertain,
      smoothed: true,
    }
  }

  const HINT_MESSAGES = {
    no_face: 'No face detected — move closer to the camera and face it directly.',
    too_dark: 'Face is too dark — add more light or move away from backlight.',
    too_bright: 'Face is overexposed — reduce lighting or move slightly away.',
    too_small: 'Face is too small — move closer to the camera.',
    blurry: 'Image is blurry — hold the camera steady.',
    detection_error: 'Detection failed for this frame — trying again…',
    bad_image: 'Could not read the camera frame.',
  }

  const displayEmotion = result?.emotion || ''
  const colorClass = EMOTION_COLORS[displayEmotion] || EMOTION_COLORS.neutral
  const noFace = result && result.face_detected === false
  const hintText = noFace ? (HINT_MESSAGES[result.hint] || HINT_MESSAGES.no_face) : null

  return (
    <div className="panel space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ScanFace size={18} className="text-teal-600" />
          <h2 className="text-lg font-bold">Emotion Recognition Trial</h2>
        </div>
        <span className="rounded-full bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">Demo</span>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Try the webcam emotion detector EduSense uses during live sessions. Frames are analyzed once per second in Live mode and are not stored.
      </p>

      {!active ? (
        <button type="button" onClick={startCamera} className="btn-primary w-full justify-center gap-2 py-2.5 text-sm">
          <Camera size={16} /> Start Camera
        </button>
      ) : (
        <div className="space-y-3">
          <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-900 dark:border-slate-700">
            <div className="flex min-h-[50vh] max-h-[65vh] w-full items-center justify-center">
              <video ref={videoRef} autoPlay playsInline muted className="h-full w-full -scale-x-100 object-contain" />
            </div>
            {analyzing && (
              <div className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2 py-1 text-[11px] text-white">
                <Loader2 size={11} className="animate-spin" /> Analyzing…
              </div>
            )}
            {result && !analyzing && !noFace && (
              <div className={`absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-3 rounded-2xl px-4 py-2.5 shadow-lg backdrop-blur ${colorClass} bg-opacity-95`}>
                <span className="text-base font-bold capitalize">{displayEmotion}</span>
                <span className="flex items-center gap-2">
                  <span className="h-2 w-24 overflow-hidden rounded-full bg-black/20">
                    <span className="block h-full rounded-full bg-current" style={{ width: `${Math.round((result.confidence || 0) * 100)}%` }} />
                  </span>
                  <span className="text-xs font-semibold opacity-90">{Math.round((result.confidence || 0) * 100)}%</span>
                </span>
              </div>
            )}
            {result && !analyzing && noFace && (
              <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-2xl bg-amber-500 px-4 py-2.5 text-sm font-bold text-slate-950 shadow-2xl border-2 border-white dark:border-slate-900">
                <CameraOff size={16} className="text-slate-950" /> <span>{hintText}</span>
              </div>
            )}
            {result && !analyzing && !noFace && result.top_emotions?.length > 1 && (
              <div className="absolute bottom-16 left-1/2 flex -translate-x-1/2 gap-2">
                {result.top_emotions.slice(0, 3).map((t) => (
                  <span key={t.emotion} className="rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white capitalize">
                    {t.emotion} {Math.round(t.confidence * 100)}%
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex gap-2">
            {cameras.length > 1 && (
              <select
                className="input flex-1 text-xs"
                value={cameraId}
                onChange={(e) => {
                  const id = e.target.value
                  setCameraId(id)
                  localStorage.setItem('edusense_camera_id', id)
                  if (active) {
                    stopCamera()
                    setTimeout(() => acquireCamera().catch((err) => setError(cameraErrorMessage(err))), 50)
                  }
                }}
                aria-label="Camera"
              >
                {cameras.map((c, i) => (
                  <option key={c.deviceId || i} value={c.deviceId}>
                    {c.label || `Camera ${i + 1}`}
                  </option>
                ))}
              </select>
            )}
            <button type="button" onClick={() => switchMode('live')}
              className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${mode === 'live' ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
              Live Webcam
            </button>
            <button type="button" onClick={() => switchMode('photo')}
              className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${mode === 'photo' ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
              Single Photo
            </button>
            <button type="button" onClick={stopCamera}
              className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-red-600 transition hover:bg-red-50 dark:bg-slate-800 dark:text-red-400">
              <CameraOff size={14} className="inline" />
            </button>
          </div>

          {mode === 'photo' && (
            <button type="button" onClick={() => captureFrame(true)} disabled={analyzing}
              className="btn-soft w-full justify-center gap-2 py-2 text-sm">
              {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />} Capture &amp; Analyze
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
          <p>{error}</p>
          {camErrorKind && (
            <button type="button" onClick={startCamera}
              className="mt-1.5 font-semibold text-red-800 underline underline-offset-2 dark:text-red-200">
              Retry camera
            </button>
          )}
        </div>
      )}

      <ConsentModal
        isOpen={consentOpen}
        consentType="emotion_detection"
        onClose={() => setConsentOpen(false)}
        onAccept={handleConsentAccept}
        onDecline={() => { setConsentOpen(false); setError('Camera access requires emotion-detection consent.') }}
      />
    </div>
  )
}
