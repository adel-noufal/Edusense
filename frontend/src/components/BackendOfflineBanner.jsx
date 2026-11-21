import React, { useEffect, useState } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { api } from '../services/api'

export default function BackendOfflineBanner() {
  const [offline, setOffline] = useState(false)
  const [checking, setChecking] = useState(false)
  const [targetUrl, setTargetUrl] = useState('')

  useEffect(() => {
    const handleStatus = (e) => {
      if (e?.detail) {
        setOffline(!e.detail.online)
        if (e.detail.url) setTargetUrl(e.detail.url)
      }
    }
    window.addEventListener('edusense-backend-status', handleStatus)

    // Initial silent check
    const checkHealth = async () => {
      try {
        await api('/health')
        setOffline(false)
      } catch (err) {
        // If it's a network error, mark offline
        if (/Cannot reach the backend/i.test(err?.message || '')) {
          setOffline(true)
        }
      }
    }
    checkHealth()

    // Poll health periodically every 15s if offline
    const interval = setInterval(() => {
      if (offline) checkHealth()
    }, 15000)

    return () => {
      window.removeEventListener('edusense-backend-status', handleStatus)
      clearInterval(interval)
    }
  }, [offline])

  const retryNow = async () => {
    setChecking(true)
    try {
      await api('/health')
      setOffline(false)
    } catch {
      setOffline(true)
    } finally {
      setChecking(false)
    }
  }

  if (!offline) return null

  return (
    <div
      role="alert"
      className="sticky top-0 z-50 flex items-center justify-between gap-3 bg-amber-500 px-4 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-md dark:bg-amber-600"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle size={18} className="shrink-0 text-amber-100" />
        <span>
          Backend server is offline or unreachable{targetUrl ? ` (${targetUrl})` : ''}.
          Please run <code className="rounded bg-amber-600/70 px-1 py-0.5 text-amber-50">start-backend.bat</code> or <code className="rounded bg-amber-600/70 px-1 py-0.5 text-amber-50">start-all.bat</code>.
        </span>
      </div>
      <button
        type="button"
        onClick={retryNow}
        disabled={checking}
        className="inline-flex shrink-0 items-center gap-1.5 rounded bg-white/20 px-2.5 py-1 text-xs font-bold text-white hover:bg-white/30 transition disabled:opacity-50"
      >
        <RefreshCw size={13} className={checking ? 'animate-spin' : ''} />
        {checking ? 'Checking...' : 'Retry'}
      </button>
    </div>
  )
}
