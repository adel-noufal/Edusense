import { useEffect, useState } from 'react'
import { FileText, Check, X } from 'lucide-react'
import { api } from '../services/api'

export function useInstructorSessions() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/sessions')
      .then((data) => setSessions(Array.isArray(data) ? data : []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false))
  }, [])

  return { sessions, loading }
}

export function useInstructorLibraryResources() {
  const [resources, setResources] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/sessions/resources/library')
      .then((data) => setResources(Array.isArray(data) ? data : []))
      .catch(() => setResources([]))
      .finally(() => setLoading(false))
  }, [])

  return { resources, loading }
}

export function SessionPickerFields({ form, setForm, showLinkSession = true, showSourceSession = true }) {
  const { sessions, loading: sessionsLoading } = useInstructorSessions()
  const { resources, loading: resourcesLoading } = useInstructorLibraryResources()
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const selectedFileIds = form.source_resource_ids || []

  function toggleFile(fileId) {
    const next = selectedFileIds.includes(fileId)
      ? selectedFileIds.filter(id => id !== fileId)
      : [...selectedFileIds, fileId]
    setForm({ ...form, source_resource_ids: next })
  }

  const options = [
    { value: '', label: sessionsLoading ? 'Loading sessions...' : 'None' },
    ...sessions.map((s) => ({ value: String(s.id), label: `${s.title} (${s.date})` })),
  ]

  return (
    <>
      {showLinkSession && (
        <label className="space-y-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
          <span>Link to session</span>
          <p className="text-xs font-normal text-slate-500">Students enrolled in this session can access the generated content.</p>
          <select
            className="input"
            value={form.session_id ?? ''}
            onChange={(e) => setForm({ ...form, session_id: e.target.value })}
          >
            {options.map((opt) => (
              <option key={`sess-${opt.value || 'none'}`} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
      )}

      {showSourceSession && (
        <div className="space-y-2 text-sm font-semibold text-slate-600 dark:text-slate-300 md:col-span-2">
          <div className="flex items-center justify-between">
            <span>Attach preparation files (Library)</span>
            {selectedFileIds.length > 0 && (
              <button
                type="button"
                className="text-xs font-normal text-teal-600 dark:text-teal-400 hover:underline"
                onClick={() => setForm({ ...form, source_resource_ids: [] })}
              >
                Clear all ({selectedFileIds.length})
              </button>
            )}
          </div>
          <p className="text-xs font-normal text-slate-500">
            Multi-select files from your library to ground this generation.
          </p>

          <div className="relative">
            <button
              type="button"
              className="input flex w-full items-center justify-between text-start"
              onClick={() => setDropdownOpen(!dropdownOpen)}
            >
              <span className="truncate">
                {selectedFileIds.length === 0
                  ? (resourcesLoading ? 'Loading library files...' : 'Select preparation files...')
                  : `${selectedFileIds.length} file(s) selected`}
              </span>
              <span className="ms-2 text-xs text-slate-400">{dropdownOpen ? '▲' : '▼'}</span>
            </button>

            {dropdownOpen && (
              <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-900">
                {resources.length === 0 ? (
                  <p className="p-3 text-center text-xs text-slate-400">No files in library yet. Upload in Sources tab.</p>
                ) : (
                  resources.map((res) => {
                    const checked = selectedFileIds.includes(res.id)
                    return (
                      <label
                        key={res.id}
                        className={`flex cursor-pointer items-center justify-between rounded-lg p-2 text-xs transition hover:bg-slate-50 dark:hover:bg-slate-800 ${checked ? 'bg-teal-50/70 font-semibold text-teal-900 dark:bg-teal-950/40 dark:text-teal-200' : ''}`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <FileText size={14} className="shrink-0 text-slate-400" />
                          <span className="truncate">{res.name}</span>
                          <span className="text-[10px] text-slate-400">({res.session_title})</span>
                        </div>
                        <input
                          type="checkbox"
                          className="ms-2 rounded border-slate-300"
                          checked={checked}
                          onChange={() => toggleFile(res.id)}
                        />
                      </label>
                    )
                  })
                )}
              </div>
            )}
          </div>

          {/* Chips of selected files */}
          {selectedFileIds.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {selectedFileIds.map((id) => {
                const res = resources.find((r) => r.id === id)
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2.5 py-1 text-xs font-medium text-teal-800 dark:bg-teal-950/40 dark:text-teal-200"
                  >
                    <FileText size={12} />
                    <span className="max-w-[150px] truncate">{res?.name || `File #${id}`}</span>
                    <button
                      type="button"
                      onClick={() => toggleFile(id)}
                      className="ms-1 hover:text-red-500"
                    >
                      <X size={12} />
                    </button>
                  </span>
                )
              })}
            </div>
          )}
        </div>
      )}
    </>
  )
}
