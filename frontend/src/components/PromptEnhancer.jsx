import { useState } from 'react'
import { Sparkles, Loader2, Check, X, RefreshCw } from 'lucide-react'
import { api } from '../services/api'

/**
 * "Enhance prompt" control for generation forms.
 * Sends the current prompt + form context to /api/ai/enhance-prompt and
 * shows an editable preview with Accept / Edit / Revert / Regenerate.
 * Never auto-submits — the parent decides when to use the result.
 */
export default function PromptEnhancer({ value, context = {}, onAccept, label = 'Enhance prompt' }) {
  const [state, setState] = useState('idle') // idle | loading | preview | error
  const [draft, setDraft] = useState('')
  const [original, setOriginal] = useState('')
  const [error, setError] = useState('')

  const run = async () => {
    const prompt = (value || '').trim()
    if (!prompt) { setError('Write a prompt first'); setState('error'); return }
    setState('loading'); setError('')
    try {
      const res = await api('/ai/enhance-prompt', {
        method: 'POST',
        body: { prompt, context },
      })
      setOriginal(prompt)
      setDraft(res?.prompt || '')
      setState('preview')
    } catch (e) {
      setError(e?.message || 'Enhancement failed')
      setState('error')
    }
  }

  const accept = () => { onAccept?.(draft); setState('idle') }
  const revert = () => { setDraft(original); setState('idle') }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={run}
        disabled={state === 'loading'}
        className="inline-flex items-center gap-1.5 rounded-md border border-teal-200 px-2.5 py-1 text-xs font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-50 dark:border-teal-800 dark:text-teal-300 dark:hover:bg-teal-950"
      >
        {state === 'loading' ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
        {state === 'loading' ? 'Enhancing…' : label}
      </button>

      {state === 'error' && (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      )}

      {state === 'preview' && (
        <div className="rounded-md border border-teal-200 bg-teal-50/50 p-3 dark:border-teal-800 dark:bg-teal-950/30">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wide text-teal-700 dark:text-teal-300">Enhanced prompt</span>
            <div className="flex gap-1">
              <button type="button" onClick={run} title="Regenerate" className="rounded p-1 hover:bg-teal-100 dark:hover:bg-teal-900"><RefreshCw size={13} /></button>
              <button type="button" onClick={revert} title="Revert" className="rounded p-1 hover:bg-teal-100 dark:hover:bg-teal-900"><X size={13} /></button>
            </div>
          </div>
          <textarea
            className="input min-h-24 w-full text-sm"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            dir="auto"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={revert} className="btn-ghost text-xs">Revert</button>
            <button type="button" onClick={accept} className="btn-primary text-xs inline-flex items-center gap-1"><Check size={13} /> Accept</button>
          </div>
        </div>
      )}
    </div>
  )
}
