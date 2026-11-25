import { useCallback, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

/**
 * Issue U1: a dialog is centered in the VIEWPORT, never in the middle of a long
 * page. Rendered in a portal so no ancestor transform/overflow can move it,
 * with body scroll lock, Esc and overlay-click close, and a focus trap.
 */
export default function Modal({ open, onClose, title, subtitle, children, maxWidth = 'max-w-lg', footer }) {
  const panelRef = useRef(null)
  const previouslyFocused = useRef(null)

  const close = useCallback(() => { if (onClose) onClose() }, [onClose])

  useEffect(() => {
    if (!open) return undefined
    previouslyFocused.current = document.activeElement
    const { overflow, paddingRight } = document.body.style
    const scrollbar = window.innerWidth - document.documentElement.clientWidth
    document.body.style.overflow = 'hidden'
    if (scrollbar > 0) document.body.style.paddingRight = `${scrollbar}px`

    const focusables = () => Array.from(
      panelRef.current?.querySelectorAll(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      ) || [],
    ).filter((el) => el.offsetParent !== null)

    const first = focusables()[0]
    if (first) first.focus()

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        close()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusables()
      if (items.length === 0) return
      const firstItem = items[0]
      const lastItem = items[items.length - 1]
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault()
        lastItem.focus()
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault()
        firstItem.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      document.body.style.overflow = overflow
      document.body.style.paddingRight = paddingRight
      if (previouslyFocused.current && previouslyFocused.current.focus) {
        previouslyFocused.current.focus()
      }
    }
  }, [open, close])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm"
      style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0 }}
      data-testid="modal-overlay"
      onMouseDown={(event) => { if (event.target === event.currentTarget) close() }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        data-testid="modal-panel"
        className={`modal-panel w-full ${maxWidth} rounded-2xl bg-white shadow-2xl dark:bg-slate-900 dark:text-slate-100 flex flex-col max-h-[85vh]`}
        style={{ maxHeight: '85vh' }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-6 py-4 dark:border-slate-700">
          <div className="min-w-0">
            {title ? <h3 className="text-lg font-bold">{title}</h3> : null}
            {subtitle ? <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p> : null}
          </div>
          <button className="btn-soft p-1.5" type="button" onClick={close} aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
        {footer ? <div className="border-t border-slate-200 px-6 py-3 dark:border-slate-700">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  )
}
