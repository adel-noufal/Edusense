import { Camera, Send } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '../services/api'

export default function WebcamEmotion({ sessionId }) {
  const video = useRef(null)
  const [result, setResult] = useState(null)

  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true })
    video.current.srcObject = stream
  }

  async function capture() {
    const canvas = document.createElement('canvas')
    canvas.width = 480
    canvas.height = 360
    canvas.getContext('2d').drawImage(video.current, 0, 0, 480, 360)
    const image = canvas.toDataURL('image/jpeg')
    const response = await api('/emotions/analyze', { method: 'POST', body: JSON.stringify({ session_id: sessionId, image }) })
    setResult(response)
  }

  return (
    <div className="panel space-y-4">
      <div className="flex items-center justify-between"><h2 className="text-lg font-bold">Live Emotion Analysis</h2><Camera /></div>
      <video ref={video} autoPlay muted className="aspect-video w-full rounded-md bg-slate-900 object-cover" />
      <div className="flex gap-2"><button className="btn-soft" onClick={start}><Camera size={18} />Open Webcam</button><button className="btn-primary" onClick={capture}><Send size={18} />Analyze Frame</button></div>
      {result && <p className="rounded-md bg-teal-50 p-3 text-sm text-ocean dark:bg-slate-800 dark:text-mint">{result.emotion} at {(result.confidence * 100).toFixed(0)}% confidence</p>}
    </div>
  )
}
