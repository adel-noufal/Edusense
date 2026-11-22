import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const ToastContext = createContext(null)

let toastId = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback((message, type = 'info', durationMs = 4500) => {
    const id = ++toastId
    setToasts((current) => [...current.slice(-4), { id, message, type }])
    if (durationMs > 0) {
      setTimeout(() => dismiss(id), durationMs)
    }
    return id
  }, [dismiss])

  const value = useMemo(() => ({
    toasts,
    push,
    dismiss,
    success: (message, durationMs) => push(message, 'success', durationMs),
    error: (message, durationMs) => push(message, 'error', durationMs),
    info: (message, durationMs) => push(message, 'info', durationMs),
  }), [toasts, push, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.type}`} role="status">
            <span>{toast.message}</span>
            <button type="button" className="toast-close" onClick={() => dismiss(toast.id)} aria-label="Dismiss">×</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
