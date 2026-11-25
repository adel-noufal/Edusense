import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, Camera, CheckCircle2, Clock, Eye, EyeOff, Flag, Home, Loader2, Maximize, Minimize, RefreshCw, Shield, User, X } from 'lucide-react'
import { api } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import { useToast } from '../context/ToastContext'
import { ConsentModal } from '../components/ConsentModal'
import { analyseFrame } from '../services/faceEmotion'

const WATERMARK_OPACITY = 0.08
const VIOLATION_CHECK_INTERVAL = 500

export default function Quiz() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const { user, hasConsent, giveConsent } = useAuth()
  const { quizId } = useParams()
  const toast = useToast()

  // Quiz state
  const [quiz, setQuiz] = useState(null)
  const [attempt, setAttempt] = useState(null)
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [answers, setAnswers] = useState({})
  const [timeRemaining, setTimeRemaining] = useState(null)
  const [timeLimit, setTimeLimit] = useState(null)
  const [perQuestionLimit, setPerQuestionLimit] = useState(null)
  const [expiredQuestions, setExpiredQuestions] = useState({})
  const [questionStartTime, setQuestionStartTime] = useState(Date.now())
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [showResults, setShowResults] = useState(false)
  const [results, setResults] = useState(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [fullscreenLocked, setFullscreenLocked] = useState(false)
  const [fullscreenError, setFullscreenError] = useState('')
  const [cameraMonitoring, setCameraMonitoring] = useState(false)
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraStream, setCameraStream] = useState(null)
  const [violationCount, setViolationCount] = useState(0)
  const [watermarkText, setWatermarkText] = useState('')

  // Consent modal state
  const [consentModalOpen, setConsentModalOpen] = useState(false)
  const [pendingConsentType, setPendingConsentType] = useState(null)

  // Refs
  const timerRef = useRef(null)
  const questionTimerRef = useRef(null)
  const violationCheckRef = useRef(null)
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const submittedRef = useRef(false)
  const serverStartTimeRef = useRef(null)

  // Server timestamps are naive UTC ("2026-11-20 12:32:16"). new Date() would
  // parse them as LOCAL time, inflating elapsed by the UTC offset and zeroing
  // the timer for anyone east of UTC. Always interpret as UTC.
  function parseServerTime(value) {
    if (!value) return Date.now()
    const s = String(value).trim().replace(' ', 'T')
    return new Date(/Z$|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z').getTime()
  }

  // Initialize watermark
  useEffect(() => {
    if (user?.email) {
      setWatermarkText(`${user.email} • ${new Date().toLocaleString()}`)
    }
  }, [user])

  // Handle consent modal accept
  const handleConsentAccept = async (consentType) => {
    await giveConsent(consentType)
    setConsentModalOpen(false)
    setPendingConsentType(null)
    // After consent given, start camera if it was quiz_anti_cheat
    if (consentType === 'quiz_anti_cheat' && quiz?.camera_monitoring) {
      setCameraMonitoring(true)
      await startCamera()
    }
  }

  // Handle consent modal decline
  const handleConsentDecline = (consentType) => {
    setConsentModalOpen(false)
    setPendingConsentType(null)
    // Continue without camera - quiz still works, just no camera monitoring
    if (consentType === 'quiz_anti_cheat') {
      toast.info('Continuing quiz without camera monitoring')
    }
  }

  // Fetch quiz and start attempt
  useEffect(() => {
    async function initQuiz() {
      setLoading(true)
      setError('')
      try {
        // Fetch quiz metadata
        const quizData = await api(`/quizzes/${quizId}`)
        setQuiz(quizData)
        setTimeLimit(quizData.time_limit_seconds)
        setPerQuestionLimit(quizData.time_limit_per_question_seconds)

        // Start attempt
        const attemptData = await api(`/quizzes/${quizId}/start`, { method: 'POST' })
        setAttempt(attemptData)

        // Set server start time for validation
        serverStartTimeRef.current = parseServerTime(attemptData.started_at)

        // Set initial time remaining accounting for elapsed attempt time on resumption,
        // and capping at the deadline min(timer end, deadline) exactly once (B13)
        let computedRemaining = null
        if (quizData.time_limit_seconds) {
          const serverStart = parseServerTime(attemptData?.started_at)
          const elapsed = Math.max(0, Math.floor((Date.now() - serverStart) / 1000))
          computedRemaining = Math.max(0, quizData.time_limit_seconds - elapsed)
        }
        if (quizData.due_date) {
          const deadlineTime = parseServerTime(quizData.due_date)
          const remainingUntilDeadline = Math.max(0, Math.floor((deadlineTime - Date.now()) / 1000))
          computedRemaining = computedRemaining != null
            ? Math.min(computedRemaining, remainingUntilDeadline)
            : remainingUntilDeadline
        }
        if (computedRemaining != null) {
          setTimeRemaining(computedRemaining)
        }

        // Enable fullscreen lock if required.
        // NOTE: requestFullscreen() must be triggered by a user gesture, so we
        // only flag the lock here — the "Enter fullscreen" overlay button
        // (a real click) performs the actual request.
        if (quizData.fullscreen_lock) {
          setFullscreenLocked(true)
        }

        // Enable camera monitoring if required - check consent first
        if (quizData.camera_monitoring) {
          if (hasConsent('quiz_anti_cheat')) {
            setCameraMonitoring(true)
            await startCamera()
          } else {
            // Show consent modal
            setPendingConsentType('quiz_anti_cheat')
            setConsentModalOpen(true)
          }
        }

        // Start violation monitoring
        startViolationMonitoring()

      } catch (err) {
        setError(err.message || 'Failed to load quiz')
        toast.error(err.message || 'Failed to load quiz')
      } finally {
        setLoading(false)
      }
    }

    if (quizId) {
      initQuiz()
    }

    // Cleanup on unmount
    return () => {
      cleanup()
    }
  }, [quizId, hasConsent, giveConsent])

  // Main timer countdown
  useEffect(() => {
    if (!quiz || !attempt || showResults || !timeLimit) return

    timerRef.current = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current)
          setTimeout(() => handleTimeUp(), 0)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [quiz, attempt, showResults, timeLimit])

  // Per-question timer (locks question permanently once expired)
  useEffect(() => {
    if (!perQuestionLimit || showResults || !quiz) return

    const qStart = Date.now()
    setQuestionStartTime(qStart)

    questionTimerRef.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - qStart) / 1000)
      if (elapsed >= perQuestionLimit) {
        if (questionTimerRef.current) clearInterval(questionTimerRef.current)
        toast.warning(`Question ${currentQuestion + 1} time limit reached!`)
        logViolation('per_question_time_exceeded', { questionIndex: currentQuestion, elapsed })
        setExpiredQuestions(prev => ({ ...prev, [currentQuestion]: true }))

        // Auto-advance or submit if on last question
        if (currentQuestion < quiz.questions.length - 1) {
          setCurrentQuestion(prev => prev + 1)
        } else {
          handleSubmit()
        }
      }
    }, 1000)

    return () => {
      if (questionTimerRef.current) clearInterval(questionTimerRef.current)
    }
  }, [currentQuestion, perQuestionLimit, showResults, quiz])

  // Fullscreen handling
  async function enterFullscreen() {
    try {
      const elem = document.documentElement
      if (!elem.requestFullscreen) throw new Error('Fullscreen is not supported by this browser.')
      await elem.requestFullscreen()
      setFullscreen(true)
      setFullscreenError('')
      return true
    } catch (err) {
      setFullscreen(false)
      setFullscreenError(err.message || 'Fullscreen could not be activated.')
      return false
    }
  }

  function exitFullscreen() {
    if (document.exitFullscreen) {
      document.exitFullscreen()
      setFullscreen(false)
    }
  }

  // Fullscreen change listener
  useEffect(() => {
    if (!fullscreenLocked) return

    const handler = () => {
      if (!document.fullscreenElement && attempt && !showResults) {
        // User exited fullscreen - violation! Re-entry requires a user
        // gesture, so the "Enter fullscreen" overlay handles it instead.
        logViolation('fullscreen_exit', { wasFullscreen: true })
      } else if (document.fullscreenElement) {
        setFullscreen(true)
        setFullscreenError('')
      } else {
        setFullscreen(false)
      }
    }

    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [fullscreenLocked, attempt, showResults])

  // Visibility/blur change listener (tab switch detection)
  useEffect(() => {
    if (!fullscreenLocked) return

    const handleVisibilityChange = () => {
      if (document.hidden && attempt && !showResults) {
        logViolation('tab_switch', { hidden: true })
      }
    }

    const handleBlur = () => {
      if (attempt && !showResults) {
        logViolation('window_blur', {})
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('blur', handleBlur)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('blur', handleBlur)
    }
  }, [fullscreenLocked, attempt, showResults])

  // Camera monitoring for second device detection
  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false
      })
      setCameraStream(stream)
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraActive(true)
      startCameraMonitoring()
    } catch (err) {
      console.warn('Camera access denied:', err)
      toast.error('Camera access required for monitoring')
    }
  }

  function startCameraMonitoring() {
    if (!cameraMonitoring || !cameraActive) return

    const detectFace = async () => {
      if (!videoRef.current) return
      try {
        // Face presence is detected in this browser tab; only the verdict and
        // label are sent, no image.
        const frame = await analyseFrame(videoRef.current)
        if (Math.random() < 0.5) { // ~1 report every 4 s
          await api('/emotions/event', {
            method: 'POST',
            body: {
              session_id: quiz.session_id,
              quiz_monitoring: true,
              attempt_id: attempt.id,
              face_detected: frame.status === 'result',
              emotion: frame.status === 'result' ? frame.rawEmotion || frame.emotion : null,
              confidence: frame.status === 'result' ? frame.confidence : 0,
            }
          })
        }
      } catch (err) {
        // Ignore errors - monitoring is best effort
      }
    }

    const interval = setInterval(detectFace, 2000)
    return () => clearInterval(interval)
  }

  // Violation monitoring
  function startViolationMonitoring() {
    violationCheckRef.current = setInterval(async () => {
      if (!attempt || showResults) return

      try {
        // Check if attempt was locked by server (due to violation from another tab)
        const attemptData = await api(`/quizzes/${quizId}/attempts/${attempt.id}`)
        if (attemptData.is_locked && !submittedRef.current) {
          handleLockedAttempt(attemptData.lock_reason)
        }
      } catch (err) {
        // Ignore
      }
    }, VIOLATION_CHECK_INTERVAL)
  }

  // Log violation to server
  async function logViolation(eventType, details) {
    if (submittedRef.current) return

    setViolationCount(prev => prev + 1)

    try {
      await api(`/quizzes/${quizId}/violations`, {
        method: 'POST',
        body: { event_type: eventType, details }
      })
    } catch (err) {
      console.error('Failed to log violation:', err)
    }

    // Auto-submit on critical violations
    if (['fullscreen_exit', 'tab_switch', 'time_exceeded'].includes(eventType)) {
      if (fullscreenLocked) {
        await autoSubmit('violation', eventType)
      }
    }
  }

  // Handle locked attempt (from another tab or server)
  async function handleLockedAttempt(reason) {
    if (submittedRef.current) return

    setError(`Quiz locked: ${reason}`)
    toast.error(`Quiz locked: ${reason}`)

    // Auto-submit with current answers
    await autoSubmit('locked', reason)
  }

  // Handle time up
  async function handleTimeUp() {
    if (submittedRef.current) return

    toast.error('Time is up! Auto-submitting...')
    await autoSubmit('time_up', 'time_limit_exceeded')
  }

  // Auto-submit quiz. submittedRef is set HERE (once) — callers must NOT set it
  // beforehand, and it is reset on failure so a manual retry can still submit.
  async function autoSubmit(reason, violationType) {
    if (submittedRef.current) return

    submittedRef.current = true
    setSubmitting(true)

    try {
      // Calculate elapsed time from server start
      const elapsedSeconds = Math.floor((Date.now() - serverStartTimeRef.current) / 1000)

      const result = await api(`/quizzes/${quizId}/submit`, {
        method: 'POST',
        body: {
          answers,
          elapsed_seconds: elapsedSeconds
        }
      })

      setResults(result)
      setShowResults(true)
      cleanup()
      toast.success(reason === 'time_up' ? 'Time is up — your quiz was submitted.' : 'Quiz submitted')
    } catch (err) {
      setError(err.message || 'Failed to submit quiz')
      toast.error(err.message || 'Failed to submit quiz')
      // Allow the manual Submit button to retry after a failed auto-submit.
      submittedRef.current = false
    } finally {
      setSubmitting(false)
    }
  }

  // Manual submit
  async function handleSubmit(e) {
    e?.preventDefault()
    if (submittedRef.current) return

    submittedRef.current = true
    setSubmitting(true)

    try {
      const elapsedSeconds = Math.floor((Date.now() - serverStartTimeRef.current) / 1000)

      const result = await api(`/quizzes/${quizId}/submit`, {
        method: 'POST',
        body: {
          answers,
          elapsed_seconds: elapsedSeconds
        }
      })

      setResults(result)
      setShowResults(true)
      cleanup()
      toast.success(results?.passed ? 'Quiz passed!' : 'Quiz submitted')
    } catch (err) {
      setError(err.message || 'Failed to submit quiz')
      toast.error(err.message || 'Failed to submit quiz')
      submittedRef.current = false
    } finally {
      setSubmitting(false)
    }
  }

  // Answer handling
  function handleAnswer(questionIndex, answer) {
    setAnswers(prev => ({ ...prev, [questionIndex]: answer }))
  }

  function nextQuestion() {
    if (currentQuestion < quiz.questions.length - 1) {
      setCurrentQuestion(prev => prev + 1)
      setQuestionStartTime(Date.now())
    }
  }

  function prevQuestion() {
    if (currentQuestion > 0) {
      setCurrentQuestion(prev => prev - 1)
      setQuestionStartTime(Date.now())
    }
  }

  // Cleanup
  function cleanup() {
    if (timerRef.current) clearInterval(timerRef.current)
    if (questionTimerRef.current) clearInterval(questionTimerRef.current)
    if (violationCheckRef.current) clearInterval(violationCheckRef.current)
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop())
    }
    if (fullscreen && document.fullscreenElement) {
      exitFullscreen()
    }
  }

  // Format time
  function formatTime(seconds) {
    if (seconds == null) return '--:--'
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // Render watermark overlay
  function renderWatermark() {
    if (!watermarkText) return null

    const watermarks = []
    const cols = 4
    const rows = 3
    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        watermarks.push(
          <div
            key={`${i}-${j}`}
            className="fixed pointer-events-none select-none text-slate-400 dark:text-slate-600"
            style={{
              opacity: WATERMARK_OPACITY,
              transform: `rotate(-15deg) translate(${j * 250}px, ${i * 200}px)`,
              fontSize: '14px',
              fontWeight: 500,
              whiteSpace: 'nowrap',
              zIndex: 9998,
              userSelect: 'none',
            }}
          >
            {watermarkText}
          </div>
        )
      }
    }
    return <div className="fixed inset-0 pointer-events-none z-[9998]">{watermarks}</div>
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-ocean mx-auto mb-4" />
          <p className="text-slate-600 dark:text-slate-400">Loading quiz...</p>
        </div>
      </div>
    )
  }

  if (error && !attempt) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-center p-8">
          <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">Unable to Load Quiz</h2>
          <p className="text-slate-600 dark:text-slate-400 mb-6">{error}</p>
          <button onClick={() => navigate('/student')} className="btn-primary">
            <Home className="w-4 h-4 mr-2" />
            Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  if (showResults && results) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 py-12 px-4">
        {renderWatermark()}
        <div className="max-w-3xl mx-auto">
          <div className="panel text-center space-y-6">
            <div className={`flex items-center justify-center gap-3 ${results.passed ? 'text-emerald-600' : 'text-red-600'}`}>
              {results.passed ? (
                <CheckCircle2 className="w-16 h-16" />
              ) : (
                <X className="w-16 h-16" />
              )}
            </div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">
              {results.passed ? 'Quiz Passed!' : 'Quiz Not Passed'}
            </h1>
            <div className="grid gap-4 md:grid-cols-3 text-center">
              <div className="rounded-2xl bg-slate-100 dark:bg-slate-800 p-6">
                <p className="text-3xl font-bold text-ocean">{results.percentage.toFixed(1)}%</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">Score</p>
              </div>
              <div className="rounded-2xl bg-slate-100 dark:bg-slate-800 p-6">
                <p className="text-3xl font-bold text-slate-900 dark:text-slate-100">{results.score}/{results.max_score}</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">Correct Answers</p>
              </div>
              <div className="rounded-2xl bg-slate-100 dark:bg-slate-800 p-6">
                <p className="text-3xl font-bold text-slate-900 dark:text-slate-100">{formatTime(Math.floor((Date.now() - serverStartTimeRef.current) / 1000))}</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">Time Taken</p>
              </div>
            </div>

            <div className="space-y-3 text-left">
              {results.details.map((detail, idx) => (
                <div key={idx} className="rounded-xl border p-4 dark:border-slate-700">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Q{detail.question_index + 1}</span>
                    <span className={`flex items-center gap-1 ${detail.correct ? 'text-emerald-600' : 'text-red-600'}`}>
                      {detail.correct ? <CheckCircle2 className="w-5 h-5" /> : <X className="w-5 h-5" />}
                    </span>
                  </div>
                  <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                    Your answer: {detail.student_answer || 'Not answered'} | Correct: {detail.correct_answer}
                  </p>
                  {detail.explanation && (
                    <p className="text-xs text-slate-500 dark:text-slate-500 mt-1">{detail.explanation}</p>
                  )}
                </div>
              ))}
            </div>

            <div className="flex gap-3 justify-center pt-4">
              <button onClick={() => navigate('/student')} className="btn-primary">
                <Home className="w-4 h-4 mr-2" />
                Back to Dashboard
              </button>
              <button onClick={() => navigate(`/student/sessions/${quiz.session_id}/live`)} className="btn-soft">
                View Session
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!quiz || !attempt) return null

  const question = quiz.questions[currentQuestion]
  // Generated questions may lack `type` — infer it from the payload shape.
  const questionType = question.type || (question.options?.length ? 'multiple_choice' : 'short_answer')
  const questionAnswered = answers[currentQuestion] !== undefined
  const progress = ((currentQuestion + 1) / quiz.questions.length) * 100

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 relative">
      {renderWatermark()}
      {fullscreenLocked && !fullscreen && !loading && !showResults && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/90 p-6 text-center">
          <div className="max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-8 text-white shadow-2xl">
            <Shield className="mx-auto h-10 w-10 text-amber-400" />
            <h2 className="mt-4 text-xl font-bold">Fullscreen is required for this exam</h2>
            <p className="mt-2 text-sm text-slate-300">
              Enter fullscreen to continue. Leaving fullscreen during the exam is recorded as a security violation.
            </p>
            {fullscreenError && <p className="mt-3 text-sm text-amber-300" role="alert">{fullscreenError}</p>}
            <button type="button" className="btn-primary mt-5 gap-2" onClick={enterFullscreen}>
              <Maximize className="h-4 w-4" /> Enter fullscreen
            </button>
          </div>
        </div>
      )}

      {/* Fullscreen/Camera indicator bar */}
      {(fullscreenLocked || cameraMonitoring) && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-slate-900/95 dark:bg-slate-950/95 border-b border-slate-700 px-4 py-2 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 text-sm text-slate-300">
            {fullscreenLocked && (
              <span className="flex items-center gap-1">
                <Shield className="w-4 h-4" />
                <span>Fullscreen Locked</span>
              </span>
            )}
            {fullscreenLocked && !fullscreen && (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-lg bg-amber-500 px-2 py-1 font-semibold text-slate-950"
                onClick={enterFullscreen}
              >
                <Maximize className="h-4 w-4" /> Enter fullscreen
              </button>
            )}
            {cameraMonitoring && (
              <span className="flex items-center gap-1">
                <Camera className="w-4 h-4" />
                <span>Camera Monitoring</span>
                <span className={`w-2 h-2 rounded-full ${cameraActive ? 'bg-emerald-500' : 'bg-red-500'}`} />
              </span>
            )}
            {violationCount > 0 && (
              <span className="flex items-center gap-1 text-amber-400">
                <Flag className="w-4 h-4" />
                <span>Violations: {violationCount}</span>
              </span>
            )}
          </div>

          {/* Timer display */}
          <div className="flex items-center gap-2 text-right">
            {timeLimit && (
              <div className={`flex items-center gap-1 ${timeRemaining <= 60 ? 'text-red-500 animate-pulse' : 'text-slate-100'}`}>
                <Clock className="w-5 h-5" />
                <span className="font-mono text-lg font-semibold tabular-nums">{formatTime(timeRemaining)}</span>
              </div>
            )}
            {perQuestionLimit && (
              <div className="flex items-center gap-1 text-slate-400">
                <span className="font-mono tabular-nums">
                  {formatTime(Math.max(0, perQuestionLimit - Math.floor((Date.now() - questionStartTime) / 1000)))}
                </span>
                <span className="text-xs">/Q</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Camera preview (hidden but active) */}
      {cameraMonitoring && (
        <div ref={videoRef} className="fixed bottom-4 right-4 w-32 h-24 rounded-lg overflow-hidden border border-slate-700 bg-slate-900 opacity-50 pointer-events-none z-40" style={{ display: 'none' }}>
          <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
          <canvas ref={canvasRef} className="hidden" />
        </div>
      )}

      <main className="max-w-3xl mx-auto px-4 py-6 pt-24 pb-24">
        {/* Quiz Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{quiz.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-1"><User className="w-4 h-4" />{quiz.difficulty}</span>
            <span className="flex items-center gap-1"><Flag className="w-4 h-4" />{quiz.questions.length} questions</span>
            {timeLimit && <span className="flex items-center gap-1"><Clock className="w-4 h-4" />{formatTime(timeLimit)} total</span>}
          </div>
          {quiz.is_exam && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold text-slate-600 dark:text-slate-300">Exam security:</span>
              <span className={`rounded-full px-2.5 py-1 ${quiz.fullscreen_lock ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}>
                {quiz.fullscreen_lock ? 'Fullscreen required' : 'Fullscreen not enabled'}
              </span>
              <span className={`rounded-full px-2.5 py-1 ${quiz.camera_monitoring ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}>
                {quiz.camera_monitoring ? 'Camera monitoring enabled' : 'Camera monitoring off'}
              </span>
              <span className={`rounded-full px-2.5 py-1 ${quiz.lock_back_navigation ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}>
                {quiz.lock_back_navigation ? 'Back navigation locked' : 'Back navigation allowed'}
              </span>
            </div>
          )}
          {fullscreenError && (
            <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200" role="alert">
              {fullscreenError} Use the “Enter fullscreen” button to retry.
            </p>
          )}

          {/* Progress bar */}
          <div className="mt-4 h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-ocean transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 text-right">
            Question {currentQuestion + 1} of {quiz.questions.length}
          </p>
        </div>

        {/* Error message */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-900/40 dark:bg-red-950/30">
            <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Question Card */}
        <div className="panel space-y-6">
          <div>
            <p className="text-lg font-medium text-slate-900 dark:text-slate-100 mb-2">
              Q{currentQuestion + 1}. {question.question}
            </p>
            {questionType === 'multiple_choice' && (
              <div className="space-y-3">
                {question.options?.map((option, optIdx) => (
                  <button
                    key={optIdx}
                    onClick={() => handleAnswer(currentQuestion, String(optIdx))}
                    className={`w-full text-left rounded-xl border-2 p-4 transition-all ${
                      answers[currentQuestion] === String(optIdx)
                        ? 'border-ocean bg-ocean/10 dark:bg-ocean/20'
                        : 'border-slate-200 dark:border-slate-700 hover:border-ocean/50 hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                  >
                    <span className="font-medium">{option}</span>
                  </button>
                ))}
              </div>
            )}
            {questionType === 'true_false' && (
              <div className="flex gap-4">
                {['True', 'False'].map(opt => (
                  <button
                    key={opt}
                    onClick={() => handleAnswer(currentQuestion, opt)}
                    className={`flex-1 rounded-xl border-2 py-4 px-6 text-center font-medium transition-all ${
                      answers[currentQuestion] === opt
                        ? 'border-ocean bg-ocean/10 dark:bg-ocean/20 text-ocean'
                        : 'border-slate-200 dark:border-slate-700 hover:border-ocean/50 hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            )}
            {questionType === 'short_answer' && (
              <textarea
                value={answers[currentQuestion] || ''}
                onChange={(e) => handleAnswer(currentQuestion, e.target.value)}
                placeholder="Type your answer here..."
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 text-slate-900 dark:text-slate-100 min-h-[120px] resize-y focus:outline-none focus:ring-2 focus:ring-ocean/50 focus:border-transparent"
                rows={4}
              />
            )}
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-200 dark:border-slate-700">
            <div className="flex gap-2">
              {currentQuestion > 0 && !quiz?.lock_back_navigation && (
                <button
                  onClick={prevQuestion}
                  className="btn-soft flex items-center gap-2"
                  disabled={submitting}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
                  Previous
                </button>
              )}
            </div>

            <div className="flex items-center gap-3">
              {/* Question indicators */}
              <div className="hidden md:flex gap-1">
                {quiz.questions.map((_, idx) => {
                  const isBlockedBack = quiz?.lock_back_navigation && idx < currentQuestion
                  return (
                    <button
                      key={idx}
                      onClick={() => {
                        if (isBlockedBack) return
                        setCurrentQuestion(idx)
                        setQuestionStartTime(Date.now())
                      }}
                      className={`w-8 h-8 rounded-lg text-xs font-medium transition-all ${
                        idx === currentQuestion
                          ? 'bg-ocean text-white'
                          : answers[idx] !== undefined
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                          : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                      } ${isBlockedBack ? 'opacity-40 cursor-not-allowed' : ''}`}
                      disabled={submitting || isBlockedBack}
                      title={isBlockedBack ? 'Back navigation is locked for this exam' : `Question ${idx + 1}`}
                    >
                      {idx + 1}
                    </button>
                  )
                })}
              </div>

              {currentQuestion < quiz.questions.length - 1 ? (
                <button
                  onClick={nextQuestion}
                  className="btn-primary flex items-center gap-2"
                  disabled={submitting || !questionAnswered}
                >
                  Next
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                </button>
              ) : (
                <button
                  onClick={handleSubmit}
                  className="btn-primary flex items-center gap-2"
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    <>
                      Submit Quiz
                      <Flag className="w-4 h-4" />
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Anti-cheat notice */}
        {(fullscreenLocked || cameraMonitoring) && (
          <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/40 dark:bg-amber-950/30">
            <div className="flex items-start gap-3">
              <Shield className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">Anti-Cheat Monitoring Active</p>
                <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                  {fullscreenLocked && 'Fullscreen mode is enforced. Exiting fullscreen, switching tabs, or minimizing the window will trigger a violation and may auto-submit your quiz.'}
                  {cameraMonitoring && fullscreenLocked ? ' ' : ''}
                  {cameraMonitoring && 'Camera is monitoring for second device detection. Ensure your face is visible.'}
                </p>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Consent Modal */}
      <ConsentModal
        isOpen={consentModalOpen}
        onClose={() => setConsentModalOpen(false)}
        consentType={pendingConsentType}
        onAccept={handleConsentAccept}
        onDecline={handleConsentDecline}
      />
    </div>
  )
}
