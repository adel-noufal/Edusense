import { useEffect, useState } from 'react'
import { Camera, Save, Sparkles, Upload } from 'lucide-react'
import { api, staticUrl, token } from '../services/api'
import { useLanguage } from '../context/LanguageContext'

export default function Profile() {
  const { t } = useLanguage()
  const [form, setForm] = useState({ phone: '', university: '', department: '', avatar: '' })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    api('/users/profile')
      .then((profile) => setForm({ phone: '', university: '', department: '', avatar: '', ...profile }))
      .catch(() => {})
  }, [])

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    setMessage('')
    try {
      await api('/users/profile', { method: 'PUT', body: JSON.stringify(form) })
      setMessage('Profile updated successfully.')
    } finally {
      setSaving(false)
    }
  }

  async function uploadAvatar(file) {
    if (!file) return
    setUploading(true)
    setMessage('')
    try {
      const body = new FormData()
      body.append('file', file)
      const response = await fetch('http://localhost:8000/api/users/profile/avatar', {
        method: 'POST',
        headers: token() ? { Authorization: `Bearer ${token()}` } : {},
        body,
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Could not upload image')
      setForm((current) => ({ ...current, avatar: result.avatar }))
      setMessage('Profile photo uploaded.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setUploading(false)
    }
  }

  const fields = [
    ['phone', t('profile.phone')],
    ['university', t('profile.university')],
    ['department', t('profile.department')],
  ]

  return (
    <form className="page-shell grid gap-6 xl:grid-cols-[340px_1fr]" onSubmit={submit}>
      <div className="panel overflow-hidden">
        <div className="absolute" />
        <div className="rounded-[1.75rem] bg-gradient-to-br from-ocean via-teal-600 to-coral p-6 text-white shadow-xl">
          <p className="text-sm uppercase tracking-[0.2em] text-teal-50">EduSense</p>
          <h1 className="mt-3 text-3xl font-black">{t('profile.title')}</h1>
          <p className="mt-2 text-sm text-teal-50">Make your profile feel more personal with a photo and polished details.</p>
        </div>
        <div className="-mt-10 rounded-[1.75rem] bg-white p-6 shadow-xl dark:bg-slate-900">
          <div className="mx-auto flex h-40 w-40 items-center justify-center overflow-hidden rounded-[2rem] border-4 border-white bg-slate-100 shadow-lg dark:border-slate-900 dark:bg-slate-800">
            {form.avatar ? (
              <img src={form.avatar.startsWith('http') ? form.avatar : staticUrl(form.avatar)} alt="Profile avatar" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-ocean to-mint text-4xl font-black text-white">
                <Camera size={42} />
              </div>
            )}
          </div>
          <label className="mt-5 flex cursor-pointer items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-300 px-4 py-3 text-sm font-semibold text-slate-600 transition hover:border-ocean hover:text-ocean dark:border-slate-700 dark:text-slate-300 dark:hover:border-mint dark:hover:text-mint">
            <Upload size={18} />
            {uploading ? 'Uploading...' : 'Upload profile photo'}
            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadAvatar(e.target.files?.[0])} />
          </label>
          <p className="mt-4 text-center text-xs text-slate-500">Best results: square photo, PNG or JPG.</p>
        </div>
      </div>

      <div className="panel space-y-5">
        <div className="flex items-center gap-3 text-xl font-black"><Sparkles size={20} />Profile Details</div>
        <p className="text-sm text-slate-600 dark:text-slate-300">Update your academic details and how you appear across the platform.</p>
        {message && <p className="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">{message}</p>}
        <div className="grid gap-4 md:grid-cols-2">
          {fields.map(([key, label]) => (
            <label key={key} className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{label}</span>
              <input className="input" value={form[key] || ''} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
            </label>
          ))}
        </div>
        <label className="space-y-2">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('profile.avatar')}</span>
          <input className="input" value={form.avatar || ''} onChange={(e) => setForm({ ...form, avatar: e.target.value })} placeholder="https://..." />
        </label>
        <div className="flex flex-wrap gap-3">
          <button className="btn-primary" disabled={saving}>
            <Save size={18} />
            {saving ? 'Saving...' : t('profile.save')}
          </button>
        </div>
      </div>
    </form>
  )
}
