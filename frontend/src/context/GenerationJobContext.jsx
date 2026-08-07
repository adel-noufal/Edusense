import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../services/api'
import { useToast } from './ToastContext'
import { useAuth } from './AuthContext'

const STORAGE_KEY = 'edusense_generation_jobs'
const POLL_MS = 2000
const MAX_POLLS = 180

const GenerationJobContext = createContext(null)

function loadStoredJobs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((job) => job?.jobId && job?.type) : []
  } catch {
    return []
  }
}

function saveStoredJobs(jobs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs))
}

export function GenerationJobProvider({ children }) {
  const { user } = useAuth()
  const toast = useToast()
  const [jobs, setJobs] = useState(() => loadStoredJobs())
  const pollingRef = useRef(new Set())
  const notifiedRef = useRef(new Set())

  const updateJob = useCallback((jobId, patch) => {
    setJobs((current) => {
      const next = current.map((job) => (job.jobId === jobId ? { ...job, ...patch } : job))
      saveStoredJobs(next.filter((job) => job.status === 'pending'))
      return next
    })
  }, [])

  const removeJob = useCallback((jobId) => {
    setJobs((current) => {
      const next = current.filter((job) => job.jobId !== jobId)
      saveStoredJobs(next.filter((job) => job.status === 'pending'))
      return next
    })
    pollingRef.current.delete(jobId)
    notifiedRef.current.delete(jobId)
  }, [])

  const notifyComplete = useCallback((jobId, label, status, error) => {
    if (notifiedRef.current.has(jobId)) return
    notifiedRef.current.add(jobId)
    if (status === 'done') {
      toast.success(`"${label}" is ready!`)
    } else if (status === 'error') {
      toast.error(error || `Failed to generate "${label}"`)
    }
  }, [toast])

  const pollJob = useCallback(async (jobId, label) => {
    if (pollingRef.current.has(jobId)) return
    pollingRef.current.add(jobId)

    for (let attempt = 0; attempt < MAX_POLLS; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS))
      try {
        const status = await api(`/ai/job/${jobId}`)
        if (status.status === 'done') {
          updateJob(jobId, { status: 'done', result: status.result, error: '' })
          notifyComplete(jobId, label, 'done')
          pollingRef.current.delete(jobId)
          return
        }
        if (status.status === 'error') {
          updateJob(jobId, { status: 'error', error: status.error || 'Generation failed' })
          notifyComplete(jobId, label, 'error', status.error)
          pollingRef.current.delete(jobId)
          return
        }
      } catch (err) {
        updateJob(jobId, { status: 'error', error: err.message || 'Could not check job status' })
        notifyComplete(jobId, label, 'error', err.message)
        pollingRef.current.delete(jobId)
        return
      }
    }

    updateJob(jobId, { status: 'error', error: 'Generation timed out after 6 minutes' })
    notifyComplete(jobId, label, 'error', 'Generation timed out')
    pollingRef.current.delete(jobId)
  }, [updateJob, notifyComplete])

  const startJob = useCallback(async ({ type, endpoint, payload, label }) => {
    const { job_id } = await api(endpoint, { method: 'POST', body: JSON.stringify(payload) })
    const job = {
      jobId: job_id,
      type,
      label: label || type,
      status: 'pending',
      startedAt: Date.now(),
      result: null,
      error: '',
    }
    setJobs((current) => {
      const withoutType = current.filter((item) => item.type !== type || item.status !== 'pending')
      const next = [job, ...withoutType]
      saveStoredJobs(next.filter((item) => item.status === 'pending'))
      return next
    })
    pollJob(job_id, job.label)
    return job
  }, [pollJob])

  useEffect(() => {
    if (!user || user.role === 'student') return
    api('/ai/jobs/pending')
      .then((pending) => {
        if (!Array.isArray(pending) || !pending.length) return
        setJobs((current) => {
          const merged = [...current]
          pending.forEach((item) => {
            if (!merged.some((j) => j.jobId === item.job_id)) {
              merged.push({
                jobId: item.job_id,
                type: item.type,
                label: item.label,
                status: 'pending',
                startedAt: Date.parse(item.startedAt) || Date.now(),
                result: null,
                error: '',
              })
            }
          })
          saveStoredJobs(merged.filter((j) => j.status === 'pending'))
          return merged
        })
        pending.forEach((item) => pollJob(item.job_id, item.label))
      })
      .catch(() => {})
  }, [user, pollJob])

  useEffect(() => {
    loadStoredJobs().filter((job) => job.status === 'pending').forEach((job) => pollJob(job.jobId, job.label))
  }, [pollJob])

  const value = useMemo(() => ({
    jobs,
    startJob,
    removeJob,
    pendingCount: jobs.filter((job) => job.status === 'pending').length,
    getJobByType: (type) => jobs.find((job) => job.type === type),
  }), [jobs, startJob, removeJob])

  return (
    <GenerationJobContext.Provider value={value}>
      {children}
    </GenerationJobContext.Provider>
  )
}

export function useGenerationJobs(type) {
  const ctx = useContext(GenerationJobContext)
  if (!ctx) throw new Error('useGenerationJobs must be used within GenerationJobProvider')
  const job = type ? ctx.getJobByType(type) : null
  return { ...ctx, job }
}
