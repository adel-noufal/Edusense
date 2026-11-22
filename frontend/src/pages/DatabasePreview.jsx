import { useEffect, useState } from 'react'
import { Database, RefreshCw } from 'lucide-react'
import { api } from '../services/api'
import { useLanguage } from '../context/LanguageContext'

export default function DatabasePreview() {
  const { t } = useLanguage()
  const [tables, setTables] = useState([])
  const [meta, setMeta] = useState(null)
  const [activeTable, setActiveTable] = useState('')
  const [rows, setRows] = useState([])
  const [totalRows, setTotalRows] = useState(0)
  const [selectedRow, setSelectedRow] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [resetting, setResetting] = useState(false)
  const [resetMessage, setResetMessage] = useState('')

  async function loadTables() {
    setLoading(true)
    setError('')
    try {
      const data = await api('/admin/db/tables')
      setMeta(data)
      setTables(data.tables || [])
      if (data.tables?.length) {
        await loadPreview(data.tables[0])
      }
    } catch (err) {
      setError(err.message || 'Could not load database preview')
    } finally {
      setLoading(false)
    }
  }

  async function handleResetData() {
    if (!window.confirm('Are you sure you want to delete all created sessions, emotion logs, quizzes, reports, and generated content? User & Admin accounts will remain intact.')) {
      return
    }
    setResetting(true)
    setError('')
    setResetMessage('')
    try {
      const res = await api('/admin/reset-data', { method: 'POST' })
      setResetMessage(res.message)
      await loadTables()
    } catch (err) {
      setError(err.message || 'Failed to reset platform data.')
    } finally {
      setResetting(false)
    }
  }

  async function loadPreview(tableName) {
    setActiveTable(tableName)
    setError('')
    try {
      const data = await api(`/admin/db/preview/${tableName}?limit=25`)
      setRows(data.preview_rows || [])
      setTotalRows(data.total_rows || 0)
      setSelectedRow(data.preview_rows?.[0] || null)
    } catch (err) {
      setError(err.message || 'Could not preview table')
      setRows([])
      setSelectedRow(null)
    }
  }

  useEffect(() => {
    loadTables()
  }, [])

  const columns = rows[0] ? Object.keys(rows[0]) : []

  return (
    <div className="page-shell space-y-6">
      <div className="panel space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Database className="text-ocean dark:text-mint" />
            <div>
              <h1 className="text-2xl font-black">{t('database.title')}</h1>
              <p className="text-sm text-slate-500">{t('database.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn-soft text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20" onClick={handleResetData} disabled={resetting}>
              {resetting ? 'Resetting...' : 'Reset Platform Data (Keep Admins)'}
            </button>
            <button type="button" className="btn-soft" onClick={loadTables}><RefreshCw size={18} />{t('database.refresh')}</button>
          </div>
        </div>
        {resetMessage && <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">{resetMessage}</p>}

        {meta && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <InfoCard label={t('database.engine')} value={meta.engine === 'postgresql' ? 'PostgreSQL' : 'SQLite'} />
            <InfoCard label={t('database.file')} value={meta.database_file} />
            <InfoCard label={t('database.tables')} value={String(meta.tables?.length || 0)} />
          </div>
        )}

        <div className="rounded-md bg-slate-100 p-4 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          <p className="font-bold">{t('database.savedTitle')}</p>
          <p className="mt-2">{t('database.savedList')}</p>
        </div>

        <div className="rounded-md border border-teal-200 bg-teal-50/50 p-4 text-sm dark:border-teal-900 dark:bg-teal-950/20">
          <p className="font-bold text-ocean dark:text-mint">{t('database.pgAdminTitle')}</p>
          <p className="mt-2 text-slate-700 dark:text-slate-300">{meta?.engine === 'postgresql' ? t('database.pgAdminSteps') : t('database.sqlitePgAdmin')}</p>
        </div>

        <div className="rounded-md bg-slate-100 p-4 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {meta?.engine === 'postgresql' ? t('database.postgresInfo') : t('database.sqliteInfo')}
        </div>

        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
      </div>

      <div className="grid gap-6 xl:grid-cols-[240px_1fr_340px]">
        <div className="panel space-y-2">
          <h2 className="font-bold">Tables</h2>
          {loading && <p className="text-sm text-slate-500">Loading...</p>}
          {tables.map((table) => (
            <button
              key={table}
              type="button"
              className={`block w-full rounded-md px-3 py-2 text-left text-sm font-semibold ${activeTable === table ? 'bg-teal-50 text-ocean dark:bg-slate-800 dark:text-mint' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}`}
              onClick={() => loadPreview(table)}
            >
              {table}
            </button>
          ))}
        </div>

        <div className="panel overflow-hidden">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-bold">{activeTable || 'Select a table'}</h2>
            {activeTable && <span className="text-sm text-slate-500">{totalRows} total rows</span>}
          </div>
          <div className="table-scroll overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700">
                  {columns.map((column) => <th key={column} className="px-3 py-2 font-semibold">{column}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index} className="cursor-pointer border-b border-slate-100 transition hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900" onClick={() => setSelectedRow(row)}>
                    {columns.map((column) => (
                      <td key={column} className="max-w-xs truncate px-3 py-2 align-top text-slate-700 dark:text-slate-300">
                        {formatCell(row[column])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && !loading && <p className="text-sm text-slate-500">No rows to display.</p>}
          </div>
        </div>
        <div className="panel">
          <h2 className="font-bold">{selectedRow ? 'Row Details' : 'Select a row'}</h2>
          {selectedRow ? (
            <div className="mt-4 space-y-3">
              {Object.entries(selectedRow).map(([key, value]) => (
                <div key={key} className="rounded-2xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-xs uppercase tracking-wide text-slate-500">{key}</p>
                  <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-700 dark:text-slate-300">{formatCellFull(value)}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-500">Click any row to inspect its stored values in a readable format.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function InfoCard({ label, value }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 break-all font-semibold">{value}</p>
    </div>
  )
}

function formatCell(value) {
  if (value == null) return '—'
  if (typeof value === 'object') return Array.isArray(value) ? `${value.length} items` : 'Structured data'
  return String(value)
}

function formatCellFull(value) {
  if (value == null) return '—'
  if (Array.isArray(value)) return value.map((item) => formatCellFull(item)).join('\n')
  if (typeof value === 'object') {
    return Object.entries(value).map(([key, entry]) => `${key}: ${formatCellFull(entry)}`).join('\n')
  }
  return String(value)
}
