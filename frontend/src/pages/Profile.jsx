import { useEffect, useState } from 'react'
import { BellRing, Camera, Eye, Palette, Save, Sparkles, Upload } from 'lucide-react'
import { api, staticUrl, token } from '../services/api'
import { useLanguage } from '../context/LanguageContext'
import { useAuth } from '../context/AuthContext'

export default function Profile() {
  const { t, lang, setLang } = useLanguage()
  const { user } = useAuth()
  const [accountForm, setAccountForm] = useState({ name: '', email: '', current_password: '', new_password: '' })
  const [profileForm, setProfileForm] = useState({ phone: '', university: '', department: '', avatar: '' })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)

  const [prefs, setPrefs] = useState(() => ({
    emailNotifications: localStorage.getItem('edusense_email_notifications') !== 'false',
    ambientMotion: localStorage.getItem('edusense_ambient_motion') !== 'false',
    compactCards: localStorage.getItem('edusense_compact_cards') === 'true',
    accent: localStorage.getItem('edusense_accent') || 'teal',
  }))

  useEffect(() => {
    localStorage.setItem('edusense_email_notifications', String(prefs.emailNotifications))
    localStorage.setItem('edusense_ambient_motion', String(prefs.ambientMotion))
    localStorage.setItem('edusense_compact_cards', String(prefs.compactCards))
    localStorage.setItem('edusense_accent', prefs.accent)
    document.documentElement.dataset.compact = prefs.compactCards ? 'true' : 'false'
  }, [prefs])

  useEffect(() => {
    if (user) {
      setAccountForm({ name: user.name || '', email: user.email || '', current_password: '', new_password: '' })
    }
    api('/users/profile')
      .then((profile) => setProfileForm({ phone: '', university: '', department: '', avatar: '', ...profile }))
      .catch(() => {})
  }, [user])

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    setMessage('')
    setError('')
    try {
      // 1. Update account credentials if changed
      const accountPayload = {}
      if (accountForm.name !== user?.name) accountPayload.name = accountForm.name
      if (accountForm.email !== user?.email) accountPayload.email = accountForm.email
      if (accountForm.new_password) {
        accountPayload.current_password = accountForm.current_password
        accountPayload.new_password = accountForm.new_password
      }

      if (Object.keys(accountPayload).length > 0) {
        await api('/users/me', { method: 'PUT', body: JSON.stringify(accountPayload) })
      }

      // 2. Update profile details
      await api('/users/profile', { method: 'PUT', body: JSON.stringify(profileForm) })
      
      setMessage('Profile and preference settings updated successfully.')
      setAccountForm((prev) => ({ ...prev, current_password: '', new_password: '' }))
    } catch (err) {
      setError(err.message || 'Could not update profile details')
    } finally {
      setSaving(false)
    }
  }

  async function uploadAvatar(file) {
    if (!file) return
    setUploading(true)
    setMessage('')
    setError('')
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
      setProfileForm((current) => ({ ...current, avatar: result.avatar }))
      setMessage('Profile photo uploaded.')
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <form className="page-shell grid gap-6 xl:grid-cols-[340px_1fr]" onSubmit={submit}>
      <div className="panel overflow-hidden">
        <div className="rounded-[1.75rem] bg-gradient-to-br from-ocean via-teal-600 to-coral p-6 text-white shadow-xl">
          <p className="text-sm uppercase tracking-[0.2em] text-teal-50">EduSense</p>
          <h1 className="mt-3 text-3xl font-black">{t('profile.title')}</h1>
          <p className="mt-2 text-sm text-teal-50">Manage account credentials, profile photo, academic profile, and app settings.</p>
        </div>
        <div className="-mt-10 rounded-[1.75rem] bg-white p-6 shadow-xl dark:bg-slate-900">
          <div className="mx-auto flex h-40 w-40 items-center justify-center overflow-hidden rounded-[2rem] border-4 border-white bg-slate-100 shadow-lg dark:border-slate-900 dark:bg-slate-800">
            {profileForm.avatar ? (
              <img src={profileForm.avatar.startsWith('http') ? profileForm.avatar : staticUrl(profileForm.avatar)} alt="Profile avatar" className="h-full w-full object-cover" />
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

      <div className="panel space-y-6">
        <div className="flex items-center gap-3 text-xl font-black"><Sparkles size={20} />Account & System Settings</div>
        {message && <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">{message}</p>}
        {error && <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
        
        {/* Section 1: Account Credentials */}
        <div className="space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-ocean dark:text-mint">1. Account Information</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('name')}</span>
              <input className="input" value={accountForm.name} onChange={(e) => setAccountForm({ ...accountForm, name: e.target.value })} required />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('email')}</span>
              <input className="input" type="email" value={accountForm.email} onChange={(e) => setAccountForm({ ...accountForm, email: e.target.value })} required />
            </label>
          </div>
          <div className="grid gap-4 md:grid-cols-2 pt-2">
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">Current Password (to change password)</span>
              <input className="input" type="password" placeholder="••••••••" value={accountForm.current_password} onChange={(e) => setAccountForm({ ...accountForm, current_password: e.target.value })} />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">New Password</span>
              <input className="input" type="password" placeholder="Min 6 characters" value={accountForm.new_password} onChange={(e) => setAccountForm({ ...accountForm, new_password: e.target.value })} />
            </label>
          </div>
        </div>

        <hr className="border-slate-200 dark:border-slate-800" />

        {/* Section 2: Personal & Academic Profile */}
        <div className="space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-ocean dark:text-mint">2. Personal & Academic Profile</h2>
          <div className="grid gap-4 md:grid-cols-3">
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('profile.phone')}</span>
              <input className="input" value={profileForm.phone || ''} onChange={(e) => setProfileForm({ ...profileForm, phone: e.target.value })} />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('profile.university')}</span>
              <input className="input" value={profileForm.university || ''} onChange={(e) => setProfileForm({ ...profileForm, university: e.target.value })} />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('profile.department')}</span>
              <input className="input" value={profileForm.department || ''} onChange={(e) => setProfileForm({ ...profileForm, department: e.target.value })} />
            </label>
          </div>
        </div>

        <hr className="border-slate-200 dark:border-slate-800" />

        {/* Section 3: System & Theme Preferences (Merged from Settings) */}
        <div className="space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-ocean dark:text-mint">3. App Preferences & Appearance</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">{t('settingsPage.language')}</span>
              <select className="input" value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="en">English</option>
                <option value="ar">العربية</option>
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">Accent Palette</span>
              <select className="input" value={prefs.accent} onChange={(e) => setPrefs({ ...prefs, accent: e.target.value })}>
                <option value="teal">Teal Ocean</option>
                <option value="blue">Calm Blue</option>
                <option value="sunset">Sunset Coral</option>
              </select>
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2 pt-2">
            <ToggleRow icon={Sparkles} label="Animated background" checked={prefs.ambientMotion} onChange={(value) => setPrefs({ ...prefs, ambientMotion: value })} />
            <ToggleRow icon={BellRing} label="Email notifications" checked={prefs.emailNotifications} onChange={(value) => setPrefs({ ...prefs, emailNotifications: value })} />
            <ToggleRow icon={Eye} label="Compact view" checked={prefs.compactCards} onChange={(value) => setPrefs({ ...prefs, compactCards: value })} />
          </div>
        </div>

        <div className="flex flex-wrap gap-3 pt-2">
          <button className="btn-primary" disabled={saving}>
            <Save size={18} />
            {saving ? 'Saving...' : t('profile.save')}
          </button>
        </div>
      </div>
    </form>
  )
}

function ToggleRow({ icon: Icon, label, checked, onChange }) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 px-4 py-3 dark:border-slate-700">
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800"><Icon size={18} /></div>
        <span className="font-semibold text-sm">{label}</span>
      </div>
      <button
        type="button"
        aria-pressed={checked}
        className={`relative h-7 w-12 rounded-full transition ${checked ? 'bg-ocean dark:bg-mint' : 'bg-slate-300 dark:bg-slate-700'}`}
        onClick={() => onChange(!checked)}
      >
        <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition ${checked ? 'end-0.5' : 'start-0.5'}`} />
      </button>
    </label>
  )
}
