import { useCallback, useEffect, useRef, useState } from 'react'
import { Camera, CameraOff, Loader2, ScanFace, ShieldCheck, Video } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { ConsentModal } from './ConsentModal'
import {
  analyseFrame,
  cameraErrorMessage,
  loadFaceModels,
  smoothEmotion,
} from '../services/faceEmotion'

const EMOTION_COLORS = {
  happy: 'bg-amber-100 text-amber-900 dark:bg-amber-900/60 dark:text-amber-100',
  neutral: 'bg-slate-100 text-slate-900 dark:bg-slate-700 dark:text-slate-50',
  sad: 'bg-blue-100 text-blue-900 dark:bg-blue-900/60 dark:text-blue-50',
  angry: 'bg-red-100 text-red-900 dark:bg-red-900/60 dark:text-red-50',
  surprise: 'bg-violet-100 text-violet-900 dark:bg-violet-900/60 dark:text-violet-50',
  fear: 'bg-indigo-100 text-indigo-900 dark:bg-indigo-900/60 dark:text-indigo-50',
  disgust: 'bg-green-100 text-green-900 dark:bg-green-900/60 dark:text-green-50',
  uncertain: 'bg-amber-300 text-slate-950',
}

const HINTS = {
  no_face: 'No face detected — move closer and face the camera.',
  too_dark: 'Too dark — add more light in front of you.',
  starting: 'Starting camera…',
}

export default function EmotionTrial({ onResult }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const timerRef = useRef(null)
  const busyRef = useRef(false)
  const historyRef = useRef([])
  const mountedRef = useRef(true)
  const { hasConsent, giveConsent } = useAuth()

  const [active, setActive] = useState(false)
  const [stream, setStream] = useState(null)
  const [starting, setStarting] = useState(false)
  const [engineReady, setEngineReady] = useState(false)
  const [frame, setFrame] = useState(null)
  const [error, setError] = useState('')
  const [errorKind, setErrorKind] = useState('')
  const [consentOpen, setConsentOpen] = useState(false)
  const [cameras, setCameras] = useState([])
  const [cameraId, setCameraId] = useState(() => localStorage.getItem('edusense_camera_id') || '')

  const stopCamera = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setStream(null)
    historyRef.current = []
    setActive(false)
    setFrame(null)
  }, [])

  // The <video> element only exists once the camera is active, so the stream is
  // attached in an effect after it mounts (attaching earlier hit a null ref and
  // left a black box).
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream
      videoRef.current.play().catch(() => {})
    }
  }, [stream, active])

  // Tracks are always released: component unmount and tab switch.
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      stopCamera()
    }
  }, [stopCamera])

  useEffect(() => {
    function handleVisibility() {
      if (document.hidden) stopCamera()
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [stopCamera])

  const runLoop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(async () => {
      const video = videoRef.current
      if (!video || busyRef.current || !streamRef.current) return
      busyRef.current = true
      try {
        const raw = await analyseFrame(video)
        if (!mountedRef.current) return
        const smoothed = smoothEmotion(historyRef.current, raw)
        historyRef.current = smoothed.history
        setFrame(smoothed.frame)
        if (smoothed.frame.status === 'result' && !smoothed.frame.uncertain) {
          onResult?.(smoothed.frame)
        }
      } catch (err) {
        if (mountedRef.current) setError(err?.message || 'The face model could not analyse this frame.')
      } finally {
        busyRef.current = false
      }
    }, 1000)
  }, [onResult])

  const acquireCamera = useCallback(async (deviceId) => {
    setStarting(true)
    setError('')
    setErrorKind('')
    try {
      // Warm the face model in parallel with the camera permission prompt.
      loadFaceModels().then(() => mountedRef.current && setEngineReady(true)).catch(() => {})
      const constraints = {
        audio: false,
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 15, max: 30 },
          facingMode: 'user',
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
        },
      }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      if (!mountedRef.current) {
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      streamRef.current = stream
      setActive(true)
      setStream(stream)
      await loadFaceModels()
      if (mountedRef.current) setEngineReady(true)

      const devices = await navigator.mediaDevices.enumerateDevices().catch(() => [])
      const cams = devices.filter((d) => d.kind === 'videoinput')
      if (mountedRef.current) {
        setCameras(cams)
        const chosen = cams.find((c) => c.deviceId === (deviceId || cameraId)) || cams[0]
        if (chosen) {
          setCameraId(chosen.deviceId)
          localStorage.setItem('edusense_camera_id', chosen.deviceId)
        }
      }
      runLoop()
    } catch (err) {
      const mapped = cameraErrorMessage(err)
      if (mountedRef.current) {
        setError(mapped.message)
        setErrorKind(mapped.kind)
        // A remembered device that disappeared must not block the first camera.
        if (mapped.kind === 'unavailable' && cameraId) {
          localStorage.removeItem('edusense_camera_id')
          setCameraId('')
        }
      }
    } finally {
      if (mountedRef.current) setStarting(false)
    }
  }, [cameraId, runLoop])

  async function startCamera() {
    setError('')
    if (!hasConsent('emotion_detection')) {
      setConsentOpen(true)
      return
    }
    await acquireCamera(cameraId)
  }

  async function handleConsentAccept(consentType) {
    await giveConsent(consentType)
    setConsentOpen(false)
    await acquireCamera(cameraId)
  }

  function switchCamera(nextId) {
    setCameraId(nextId)
    localStorage.setItem('edusense_camera_id', nextId)
    stopCamera()
    setTimeout(() => acquireCamera(nextId), 60)
  }

  const status = frame?.status
  const resultVisible = status === 'result' && !frame?.uncertain
  const label = resultVisible ? frame.emotion : ''
  const badgeClass = resultVisible
    ? (EMOTION_COLORS[label] || EMOTION_COLORS.neutral)
    : status === 'too_dark'
      ? 'bg-amber-400 text-slate-950'
      : status === 'no_face'
        ? 'bg-slate-800 text-white'
        : 'bg-teal-800 text-white'

  const badgeText = !active
    ? 'Camera off'
    : starting || !engineReady
      ? 'Starting camera and face model…'
      : status === 'too_dark'
        ? HINTS.too_dark
        : status === 'no_face'
          ? HINTS.no_face
          : resultVisible
            ? `${label} · ${Math.round((frame.confidence || 0) * 100)}%`
            : frame?.uncertain
              ? 'Reading your expression…'
              : HINTS.starting

  return (
    <div className="panel space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ScanFace size={18} className="text-teal-600" />
          <h2 className="text-lg font-bold">Emotion Recognition Trial</h2>
        </div>
        <span className="rounded-full bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
          Runs in your browser
        </span>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Your camera frame is analysed on this device. No image is uploaded or stored — only the
        emotion label and confidence are used for session analytics. Analysis runs once per second.
      </p>

      {!active ? (
        <button
          type="button"
          onClick={startCamera}
          disabled={starting}
          className="btn-primary w-full justify-center gap-2 py-2.5 text-sm"
        >
          {starting ? <Loader2 size={16} className="animate-spin" /> : <Camera size={16} />}
          {starting ? 'Starting camera…' : 'Start Camera'}
        </button>
      ) : (
        <div className="space-y-3">
          <div className="relative overflow-hidden rounded-xl border border-slate-300 bg-slate-900 dark:border-slate-700">
            <div
              role="status"
              aria-live="polite"
              className={`absolute inset-x-0 top-0 z-20 flex min-h-11 items-center justify-center px-3 py-2 text-center text-xs font-black tracking-wide shadow-md ${badgeClass}`}
            >
              {badgeText}
            </div>
            <div className="flex min-h-[46vh] max-h-[62vh] w-full items-center justify-center">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="h-full w-full -scale-x-100 object-contain"
              />
            </div>
            {engineReady && status !== 'result' && active && (
              <div className="pointer-events-none absolute left-1/2 top-[54%] z-10 h-[55%] w-[48%] -translate-x-1/2 -translate-y-1/2 rounded-[45%] border-2 border-teal-300/90" />
            )}
            {frame?.box && resultVisible && (
              <div
                className="pointer-events-none absolute z-10 rounded-lg border-2 border-emerald-400"
                style={{
                  left: `${(frame.box.x / (videoRef.current?.videoWidth || 1)) * 100}%`,
                  top: `${(frame.box.y / (videoRef.current?.videoHeight || 1)) * 100}%`,
                  width: `${(frame.box.width / (videoRef.current?.videoWidth || 1)) * 100}%`,
                  height: `${(frame.box.height / (videoRef.current?.videoHeight || 1)) * 100}%`,
                  transform: 'scaleX(-1)',
                }}
              />
            )}
            {resultVisible && (
              <div className="absolute bottom-3 left-1/2 z-20 flex w-[86%] max-w-sm -translate-x-1/2 flex-col gap-2 rounded-2xl bg-white/95 p-3 text-slate-900 shadow-xl dark:bg-slate-900/95 dark:text-slate-50">
                <div className="flex items-center justify-between">
                  <span className="text-base font-black capitalize">{label}</span>
                  <span className="text-sm font-bold">{Math.round((frame.confidence || 0) * 100)}%</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                  <div
                    className="h-full rounded-full bg-teal-600 dark:bg-teal-400"
                    style={{ width: `${Math.round((frame.confidence || 0) * 100)}%` }}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5 text-[11px] font-semibold">
                  {(frame.top3 || []).map((item) => (
                    <span key={item.emotion} className="rounded-full bg-slate-100 px-2 py-0.5 capitalize dark:bg-slate-800">
                      {item.emotion} {Math.round(item.confidence * 100)}%
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {cameras.length > 1 && (
              <select
                className="input flex-1 text-xs"
                value={cameraId}
                onChange={(e) => switchCamera(e.target.value)}
                aria-label="Camera device"
              >
                {cameras.map((c, i) => (
                  <option key={c.deviceId || i} value={c.deviceId}>
                    {c.label || `Camera ${i + 1}`}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              onClick={stopCamera}
              className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-bold text-red-700 transition hover:bg-red-50 dark:bg-slate-800 dark:text-red-300"
            >
              <CameraOff size={14} className="inline" /> Stop camera
            </button>
            <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
              <ShieldCheck size={13} /> frames stay on this device
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800 dark:bg-red-950/40 dark:text-red-200">
          <p>{error}</p>
          {errorKind && (
            <button type="button" onClick={startCamera} className="mt-1.5 font-bold underline underline-offset-2">
              Retry camera
            </button>
          )}
        </div>
      )}

      {!engineReady && active && (
        <p className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
          <Video size={13} /> Loading the face model from this app (no internet needed).
        </p>
      )}

      <ConsentModal
        isOpen={consentOpen}
        consentType="emotion_detection"
        onClose={() => setConsentOpen(false)}
        onAccept={handleConsentAccept}
        onDecline={() => {
          setConsentOpen(false)
          setError('Camera access needs emotion-detection consent. You can change it in Profile → Privacy.')
        }}
      />
    </div>
  )
}
