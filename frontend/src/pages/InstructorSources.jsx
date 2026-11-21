import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileDown, FolderOpen, MessageSquare, RefreshCw, Trash2, Upload, Tag, Search } from 'lucide-react'
import { api, staticUrl } from '../services/api'
import SearchInput from '../components/SearchInput'

export default function InstructorSources() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [resources, setResources] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploadingResource, setUploadingResource] = useState(false)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTagSessionIds, setSelectedTagSessionIds] = useState([])
  const [showTagModal, setShowTagModal] = useState(false)
  const [stagedFile, setStagedFile] = useState(null)
  const fileInputRef = useRef(null)

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [sessData, resData] = await Promise.all([
        api('/sessions').catch(() => []),
        api('/sessions/resources/library').catch(() => [])
      ])
      setSessions(Array.isArray(sessData) ? sessData : [])
      setResources(Array.isArray(resData) ? resData : [])
    } catch (err) {
      setError(err.message || 'Could not load library resources')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  function handleFileSelect(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setStagedFile(file)
    setSelectedTagSessionIds([])
    setShowTagModal(true)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function confirmUpload() {
    if (!stagedFile) return
    setUploadingResource(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', stagedFile)
      if (selectedTagSessionIds.length > 0) {
        formData.append('session_ids', selectedTagSessionIds.join(','))
      }
      await api('/sessions/resources/library', {
        method: 'POST',
        body: formData,
      })
      setShowTagModal(false)
      setStagedFile(null)
      await loadData()
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploadingResource(false)
    }
  }

  async function deleteResource(resourceId) {
    try {
      await api(`/sessions/resources/${resourceId}`, { method: 'DELETE' })
      setResources((current) => current.filter((item) => item.id !== resourceId))
    } catch (err) {
      setError(err.message || 'Could not delete resource')
    }
  }

  function askAboutDocument(resource) {
    navigate('/instructor/chatbot', { state: { sourceId: resource.id, sourceName: resource.name } })
  }

  function formatBytes(bytes) {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const filteredResources = useMemo(() => {
    if (!searchQuery.trim()) return resources
    const q = searchQuery.toLowerCase()
    return resources.filter(r =>
      r.name?.toLowerCase().includes(q) ||
      r.session_title?.toLowerCase().includes(q)
    )
  }, [resources, searchQuery])

  return (
    <div className="page-shell space-y-6">
      <div className="panel space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black">Instructor Sources Library</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              All files belong to your library and can be multi-selected in AI Lessons, Quizzes, Flashcards, and Videos. Optionally tag them with sessions for student access.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn-soft" onClick={() => loadData()}>
              <RefreshCw size={18} />Refresh
            </button>
            <button type="button" className="btn-primary" onClick={() => fileInputRef.current?.click()}>
              <Upload size={18} />Upload source
            </button>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.pptx,.ppt,.doc,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.mp4,.zip"
              onChange={handleFileSelect}
            />
          </div>
        </div>

        {error && (
          <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200">
            {error}
          </p>
        )}

        {/* Search Bar */}
        <div className="max-w-md">
          <SearchInput
            placeholder="Search library files by name or tagged session..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Library Files List */}
        <div className="rounded-2xl border border-slate-200 bg-white/70 p-5 dark:border-slate-800 dark:bg-slate-900/50">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
            <h2 className="text-base font-bold flex items-center gap-2">
              <FolderOpen size={18} className="text-teal-600 dark:text-teal-400" />
              Library Files ({filteredResources.length})
            </h2>
            {loading && <span className="text-xs text-slate-400 animate-pulse">Loading files...</span>}
          </div>

          <div className="mt-4 space-y-2">
            {filteredResources.length === 0 && !loading ? (
              <p className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800/60">
                {searchQuery ? 'No files match your search.' : 'No files uploaded to your library yet. Click "Upload source" above.'}
              </p>
            ) : (
              filteredResources.map((resource) => (
                <div
                  key={resource.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition hover:shadow-md dark:border-slate-700 dark:bg-slate-800/80"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <FileDown size={20} className="shrink-0 text-teal-600 dark:text-teal-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-sm">{resource.name}</p>
                      <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-slate-500">
                        <span>{formatBytes(resource.file_size)}</span>
                        <span>â€¢</span>
                        <span>{new Date(resource.uploaded_at).toLocaleDateString()}</span>
                        {resource.session_title && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                            <Tag size={10} /> {resource.session_title}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {resource.available ? (
                      <a
                        href={staticUrl(resource.url)}
                        target="_blank"
                        rel="noreferrer"
                        className="btn-soft p-2"
                        title="Download / Open file"
                      >
                        <FileDown size={16} />
                      </a>
                    ) : (
                      <span className="text-xs font-medium text-red-500">Unavailable</span>
                    )}
                    <button
                      type="button"
                      className="btn-soft p-2 text-ocean dark:text-mint"
                      onClick={() => askAboutDocument(resource)}
                      title="Ask AI Chatbot about this document"
                    >
                      <MessageSquare size={16} />
                    </button>
                    <button
                      type="button"
                      className="btn-soft p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                      onClick={() => deleteResource(resource.id)}
                      title="Delete from library"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Upload & Optional Tagging Modal */}
      {showTagModal && stagedFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="panel w-full max-w-lg space-y-4">
            <h2 className="text-lg font-bold">Upload to Library</h2>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800">
              <p className="font-semibold text-sm truncate">{stagedFile.name}</p>
              <p className="text-xs text-slate-500">{formatBytes(stagedFile.size)}</p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                Optional: Tag with Sessions (Many-to-Many)
              </label>
              <p className="text-xs text-slate-500">
                Files belong to your library. Tagging sessions enables enrolled students to see this file in their resources.
              </p>

              <div className="max-h-48 overflow-y-auto space-y-1.5 rounded-xl border border-slate-200 p-2 dark:border-slate-700">
                {sessions.length === 0 ? (
                  <p className="p-2 text-xs text-slate-400">No sessions available to tag.</p>
                ) : (
                  sessions.map((sess) => {
                    const checked = selectedTagSessionIds.includes(sess.id)
                    return (
                      <label
                        key={sess.id}
                        className={`flex cursor-pointer items-center justify-between rounded-lg p-2 text-xs transition hover:bg-slate-50 dark:hover:bg-slate-800 ${checked ? 'bg-teal-50 font-semibold text-teal-900 dark:bg-teal-950/40 dark:text-teal-200' : ''}`}
                      >
                        <span className="truncate">{sess.title} ({sess.date})</span>
                        <input
                          type="checkbox"
                          className="rounded border-slate-300"
                          checked={checked}
                          onChange={() => {
                            setSelectedTagSessionIds((prev) =>
                              prev.includes(sess.id)
                                ? prev.filter((id) => id !== sess.id)
                                : [...prev, sess.id]
                            )
                          }}
                        />
                      </label>
                    )
                  })
                )}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                className="btn-soft"
                onClick={() => {
                  setShowTagModal(false)
                  setStagedFile(null)
                }}
                disabled={uploadingResource}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={confirmUpload}
                disabled={uploadingResource}
              >
                {uploadingResource ? 'Uploading...' : 'Confirm Upload'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
