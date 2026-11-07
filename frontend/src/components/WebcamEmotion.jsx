import { Camera, Send, Download, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api'
import { downloadJson } from '../utils/download'

export default function WebcamEmotion({ sessionId, title = 'Live Emotion Analysis' }) {
  const video = useRef(null)
  const streamRef = useRef(null)
  const autoCaptureRef = useRef(null)
  const [results, setResults] = useState([])
  const [streamStarted, setStreamStarted] = useState(false)
  const [capturedImage, setCapturedImage] = useState(null)
  const [error, setError] = useState('')
  const [infoMessage, setInfoMessage] = useState('')
  const canAnalyze = Boolean(sessionId)

  async function start() {
    setError('')
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true })
      if (video.current) {
        video.current.srcObject = mediaStream
      }
      streamRef.current = mediaStream
      setStreamStarted(true)
      scheduleAutoCapture(mediaStream)
    } catch (err) {
      setError(err.message || 'Unable to access your webcam.')
    }
  }

  function stopCamera() {
    if (!window.confirm('Close the camera? Your auto capture will stop.')) {
      return
    }
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
    autoCaptureRef.current = window.setInterval(() => {
      if (mediaStream && video.current) {
        capture()
      }
    }, 20000)
  }

  async function capture() {
    if (!streamStarted || !video.current) return
    setError('')

    const canvas = document.createElement('canvas')
    canvas.width = 480
    canvas.height = 360
    canvas.getContext('2d').drawImage(video.current, 0, 0, 480, 360)
    const image = canvas.toDataURL('image/jpeg')
    setCapturedImage(image)

    if (!canAnalyze) {
      setError('Select or register for a session before running the analysis.')
      return
    }

    try {
      const response = await api('/emotions/analyze', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, image }),
      })
      setResults((prev) => [
        {
          id: response.id,
          emotion: response.emotion,
          confidence: response.confidence,
          timestamp: response.timestamp,
          backend: response.backend,
        },
        ...prev,
      ])
    } catch (err) {
      setError(err.message || 'Failed to analyze the frame.')
    }
  }

  function downloadResults() {
    if (!results.length) return
    const payload = {
      sessionId: sessionId || 'trial',
      note: 'For best results, ensure your camera lens is clean and your lighting is good before running the analysis.',
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
      <div className="flex items-center justify-between"><h2 className="text-lg font-bold">{title}</h2><Camera /></div>
      <p className="text-sm text-slate-500">Use your webcam to test reaction analysis as part of the student experience. For best results, make sure your camera lens is clean and lighting is good.</p>
      <video ref={video} autoPlay muted className="aspect-video w-full rounded-md bg-slate-900 object-cover" />
      <div className="flex flex-wrap gap-2">
        <button className="btn-soft" type="button" onClick={start}><Camera size={18} />Open Webcam</button>
        <button className="btn-soft" type="button" onClick={stopCamera} disabled={!streamStarted}><X size={18} />Close Camera</button>
        <button className="btn-primary" type="button" onClick={capture} disabled={!streamStarted}><Send size={18} />Analyze Frame</button>
        <button className="btn-soft" type="button" onClick={downloadResults} disabled={!results.length}><Download size={18} />Download Reactions</button>
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
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.emotion}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Confidence {(item.confidence * 100).toFixed(1)}%</p>
                  </div>
                  <div className="text-right text-xs text-slate-500 dark:text-slate-400">
                    <p>{new Date(item.timestamp).toLocaleString()}</p>
                    <p>{item.backend}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
