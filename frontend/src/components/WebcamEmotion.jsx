import { Camera, Send, Download, X, Layers, Radio } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { downloadJson } from '../utils/download'
import { ConsentModal } from './ConsentModal'

export default function WebcamEmotion({ sessionId, title = 'Live Emotion Analysis' }) {
  const video = useRef(null)
  const streamRef = useRef(null)
  const autoCaptureRef = useRef(null)
  const lastUiUpdateRef = useRef(0)
  const { hasConsent, giveConsent } = useAuth()
  const [results, setResults] = useState([])
  const [streamStarted, setStreamStarted] = useState(false)
  const [capturedImage, setCapturedImage] = useState(null)
  const [error, setError] = useState('')
  const [infoMessage, setInfoMessage] = useState('')
  const [consentModalOpen, setConsentModalOpen] = useState(false)
  const [captureMode, setCaptureMode] = useState('continuous') // 'continuous' | 'single'
  const canAnalyze = Boolean(sessionId)

  async function start() {
    setError('')
    // Check for emotion_detection consent
    if (!hasConsent('emotion_detection')) {
      setConsentModalOpen(true)
      return
    }
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true })
      if (video.current) {
        video.current.srcObject = mediaStream
      }
      streamRef.current = mediaStream
      setStreamStarted(true)
      if (captureMode === 'continuous') {
        scheduleAutoCapture(mediaStream)
      }
    } catch (err) {
      setError(err.message || 'Unable to access your webcam.')
    }
  }

  const handleConsentAccept = async (consentType) => {
    await giveConsent(consentType)
    setConsentModalOpen(false)
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true })
      if (video.current) {
        video.current.srcObject = mediaStream
      }
      streamRef.current = mediaStream
      setStreamStarted(true)
      if (captureMode === 'continuous') {
        scheduleAutoCapture(mediaStream)
      }
    } catch (err) {
      setError(err.message || 'Unable to access your webcam.')
    }
  }

  const handleConsentDecline = () => {
    setConsentModalOpen(false)
    setInfoMessage('Camera access declined. You can grant consent later in Settings → Privacy.')
  }

  function stopCamera() {
    if (autoCaptureRef.current) {
      clearInterval(autoCaptureRef.current)
      autoCaptureRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (video.current) {
      video.current.srcObject = null
      video.current.pause()
    }
    setStreamStarted(false)
    setInfoMessage('Camera closed successfully.')
  }

  function scheduleAutoCapture(mediaStream) {
    if (autoCaptureRef.current) {
      clearInterval(autoCaptureRef.current)
    }
    lastUiUpdateRef.current = 0
    // Record at finer 1-second granularity for instructor reports
    autoCaptureRef.current = window.setInterval(() => {
      if (mediaStream && video.current) {
        const now = Date.now()
        // Update visible UI results every 5 seconds for readable live view
        const updateUi = (now - lastUiUpdateRef.current >= 4900)
        capture(updateUi)
        if (updateUi) lastUiUpdateRef.current = now
      }
    }, 1000)
  }

  function handleModeChange(newMode) {
    setCaptureMode(newMode)
    if (newMode === 'single') {
      if (autoCaptureRef.current) {
        clearInterval(autoCaptureRef.current)
        autoCaptureRef.current = null
      }
    } else if (newMode === 'continuous' && streamStarted && streamRef.current) {
      scheduleAutoCapture(streamRef.current)
    }
  }

  async function capture(updateUi = true) {
    if (!video.current) return
    setError('')

    const canvas = document.createElement('canvas')
    canvas.width = 480
    canvas.height = 360
    canvas.getContext('2d').drawImage(video.current, 0, 0, 480, 360)
    const image = canvas.toDataURL('image/jpeg')
    if (updateUi) setCapturedImage(image)

    if (!canAnalyze) {
      if (updateUi) setError('Select or register for a session before running the analysis.')
      return
    }

    try {
      const response = await api('/emotions/analyze', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, image }),
      })
      if (updateUi) {
        setResults((prev) => [
          {
            id: response.id,
            emotion: response.emotion,
            confidence: response.confidence,
            timestamp: response.timestamp,
            backend: response.backend,
          },
          ...prev.slice(0, 19),
        ])
      }
    } catch (err) {
      if (updateUi) setError(err.message || 'Failed to analyze the frame.')
    }
  }

  function downloadResults() {
    if (!results.length) {
      setError('No reactions recorded yet. Open your webcam and capture frames first before downloading.')
      return
    }
    const payload = {
      sessionId: sessionId || 'trial',
      note: 'EduSense student reaction analysis logs.',
      generatedAt: new Date().toISOString(),
      reactions: results,
    }
    downloadJson(payload, `edusense-reactions-${Date.now()}.json`)
  }

  useEffect(() => {
    return () => {
      if (autoCaptureRef.current) clearInterval(autoCaptureRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop())
    }
  }, [])

  return (
    <div className="panel space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">{title}</h2>
        <Camera />
      </div>
      <p className="text-sm text-slate-500">
        Webcam emotion &amp; attention capture. You can choose single photo analysis or continuous tracking.
      </p>

      {/* Mode selector */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-slate-500">Capture Mode:</span>
        <div className="inline-flex rounded-xl bg-slate-100 p-1 dark:bg-slate-800 text-xs font-semibold">
          <button
            type="button"
            onClick={() => handleModeChange('continuous')}
            className={`py-1 px-3 rounded-lg transition ${captureMode === 'continuous' ? 'bg-white shadow text-ocean dark:bg-slate-700 dark:text-mint' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Continuous (1s log / 5s UI)
          </button>
          <button
            type="button"
            onClick={() => handleModeChange('single')}
            className={`py-1 px-3 rounded-lg transition ${captureMode === 'single' ? 'bg-white shadow text-ocean dark:bg-slate-700 dark:text-mint' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Single Photo
          </button>
        </div>
        {captureMode === 'continuous' && streamStarted && (
          <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
            1s background logging active
          </span>
        )}
      </div>

      <video ref={video} autoPlay muted className="aspect-video w-full rounded-md bg-slate-900 object-cover" />
      <div className="flex flex-wrap gap-2">
        <button className="btn-soft" type="button" onClick={start} disabled={streamStarted}>
          <Camera size={18} />Open Webcam
        </button>
        <button className="btn-soft" type="button" onClick={stopCamera} disabled={!streamStarted}>
          <X size={18} />Close Camera
        </button>
        {captureMode === 'single' && (
          <button className="btn-primary" type="button" onClick={() => capture(true)} disabled={!streamStarted}>
            <Send size={18} />Analyze Single Frame
          </button>
        )}
        <button className="btn-soft" type="button" onClick={downloadResults}>
          <Download size={18} />Download Reactions {results.length > 0 ? `(${results.length})` : ''}
        </button>
      </div>

      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200">{error}</p>}
      {infoMessage && <p className="rounded-md bg-green-50 p-3 text-sm text-green-700 dark:bg-green-950/30 dark:text-green-200">{infoMessage}</p>}
      {capturedImage && (
        <div className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
          <p className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Captured frame preview</p>
          <img src={capturedImage} alt="Captured reaction frame" className="w-full rounded-lg" />
        </div>
      )}
      {results.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-bold text-slate-800 dark:text-slate-100">Recent reaction results</p>
            <span className="text-xs uppercase tracking-[0.18em] text-slate-500">{results.length} captures</span>
          </div>
          <div className="space-y-3">
            {results.map((item) => (
              <div key={item.id} className="rounded-2xl bg-white p-3 shadow-sm dark:bg-slate-900">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100 capitalize">{item.emotion}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Confidence {(item.confidence * 100).toFixed(1)}%</p>
                  </div>
                  <span className="text-xs text-slate-400">{item.timestamp?.slice(11, 19)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {consentModalOpen && (
        <ConsentModal
          consentType="emotion_detection"
          onAccept={() => handleConsentAccept('emotion_detection')}
          onDecline={handleConsentDecline}
        />
      )}
    </div>
  )
}
