import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, GraduationCap, Globe, ArrowLeft } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import AnimatedBackground from '../components/AnimatedBackground'
import { api } from '../services/api'

function validateAuthForm(form, isRegister, t) {
  if (isRegister && !form.name.trim()) return t('nameRequired')
  if (!form.email.trim()) return t('emailRequired')
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) return t('emailInvalid')
  if (!form.password) return t('passwordRequired')
  if (form.password.length < 6) return t('passwordMin')
  return ''
}

export function Login() {
  const { login } = useAuth()
  const { t, toggleLang } = useLanguage()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  async function submit(e) {
    e.preventDefault()
    const validationError = validateAuthForm(form, false, t)
    if (validationError) { setError(validationError); return }
    setError('')
    try {
      const user = await login(form.email.trim(), form.password)
      navigate(user.role === 'instructor' ? '/instructor' : '/student')
    } catch (err) {
      setError(err.message || t('loginFailed'))
    }
  }

  return (
    <AuthShell title={t('welcomeBack')} error={error} onSubmit={submit} toggleLang={toggleLang} langLabel={t('langToggle')}>
      <input className="input" placeholder={t('email')} value={form.email} autoComplete="email" onChange={(e) => setForm({ ...form, email: e.target.value })} />
      <div className="space-y-2">
        <PasswordField value={form.password} placeholder={t('password')} autoComplete="current-password" visible={showPassword} onToggle={() => setShowPassword((value) => !value)} onChange={(value) => setForm({ ...form, password: value })} />
        <p className="text-xs text-slate-500">{t('passwordHint')}</p>
      </div>
      <button className="btn-primary w-full">{t('login')}</button>
      <div className="flex flex-col items-center gap-2 mt-4">
        <Link className="text-sm font-semibold text-ocean dark:text-mint hover:underline" to="/forgot-password">{t('forgotPassword')}</Link>
        <Link className="text-sm text-slate-500 hover:underline" to="/register">{t('needAccount')}</Link>
        <Link className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-ocean dark:hover:text-mint transition-colors mt-1" to="/">
          <ArrowLeft size={14} />{t('backToHome')}
        </Link>
      </div>
    </AuthShell>
  )
}

export function Register() {
  const { register } = useAuth()
  const { t, toggleLang } = useLanguage()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'student' })
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  async function submit(e) {
    e.preventDefault()
    const validationError = validateAuthForm(form, true, t)
    if (validationError) { setError(validationError); return }
    setError('')
    try {
      const user = await register({ ...form, name: form.name.trim(), email: form.email.trim() })
      navigate(user.role === 'instructor' ? '/instructor' : '/student')
    } catch (err) {
      setError(err.message || t('registerFailed'))
    }
  }

  return (
    <AuthShell title={t('createAccount')} error={error} onSubmit={submit} toggleLang={toggleLang} langLabel={t('langToggle')}>
      <input className="input" placeholder={t('name')} value={form.name} autoComplete="name" onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <input className="input" placeholder={t('email')} value={form.email} autoComplete="email" onChange={(e) => setForm({ ...form, email: e.target.value })} />
      <div className="space-y-2">
        <PasswordField value={form.password} placeholder={t('password')} autoComplete="new-password" visible={showPassword} onToggle={() => setShowPassword((value) => !value)} onChange={(value) => setForm({ ...form, password: value })} />
        <p className="text-xs text-slate-500">{t('passwordHint')}</p>
      </div>
      <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
        <option value="student">{t('student')}</option>
        <option value="instructor">{t('instructor')}</option>
      </select>
      <button type="submit" className="btn-primary w-full">{t('register')}</button>
      <div className="flex flex-col items-center gap-2 mt-2">
        <Link className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-ocean dark:hover:text-mint transition-colors" to="/">
          <ArrowLeft size={14} />{t('backToHome')}
        </Link>
      </div>
    </AuthShell>
  )
}

function AuthShell({ title, error, onSubmit, children, toggleLang, langLabel }) {
  const { t } = useLanguage()
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-950">
      <AnimatedBackground />
      <form onSubmit={onSubmit} className="panel relative z-10 w-full max-w-md space-y-4 rounded-[1.75rem] border-white/50 bg-white/85 shadow-2xl backdrop-blur-xl dark:bg-slate-900/85">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-2xl font-black text-ocean dark:text-mint"><GraduationCap />{t('appName')}</div>
          <button type="button" className="btn-soft" onClick={toggleLang}><Globe size={16} />{langLabel}</button>
        </div>
        <h1 className="text-xl font-bold">{title}</h1>
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
        {children}
      </form>
    </div>
  )
}

function PasswordField({ value, onChange, placeholder, autoComplete, visible, onToggle }) {
  return (
    <label className="relative block">
      <input
        className="input pe-14"
        type={visible ? 'text' : 'password'}
        placeholder={placeholder}
        value={value}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        aria-label={visible ? 'Hide password' : 'Show password'}
        className="absolute end-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:scale-110 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        onClick={onToggle}
      >
        <span className={`transition-all duration-300 ${visible ? 'rotate-0 scale-100 opacity-100' : '-rotate-45 scale-90 opacity-100'}`}>
          {visible ? <EyeOff size={18} /> : <Eye size={18} />}
        </span>
      </button>
    </label>
  )
}

export function ForgotPassword() {
  const { t, toggleLang } = useLanguage()
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!email.trim()) { setError(t('emailRequired')); return }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError(t('emailInvalid')); return }
    
    setError('')
    setMessage('')
    setLoading(true)
    try {
      const res = await api('/auth/forgot-password', { method: 'POST', body: { email: email.trim() } })
      setMessage(res.message || t('checkEmail'))
    } catch (err) {
      setError(err.message || t('error.somethingWrong'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title={t('resetPassword')} error={error} onSubmit={submit} toggleLang={toggleLang} langLabel={t('langToggle')}>
      <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">{t('resetInstructions')}</p>
      
      {message ? (
        <div className="rounded-md bg-green-50 p-4 text-sm text-green-700 dark:bg-green-900/30 dark:text-green-300 border border-green-200 dark:border-green-800">
          {message}
        </div>
      ) : (
        <>
          <input className="input" placeholder={t('email')} value={email} autoComplete="email" onChange={(e) => setEmail(e.target.value)} disabled={loading} />
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? '...' : t('sendResetLink')}
          </button>
        </>
      )}
      <div className="text-center mt-4">
        <Link className="text-sm text-slate-500 hover:underline" to="/login">{t('backToLogin')}</Link>
      </div>
    </AuthShell>
  )
}

export function ResetPassword() {
  const { t, toggleLang } = useLanguage()
  const navigate = useNavigate()
  const [form, setForm] = useState({ password: '', confirm: '' })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  // Get token from URL query params manually to avoid relying on react-router useSearchParams if not imported
  const token = new URLSearchParams(window.location.search).get('token')

  async function submit(e) {
    e.preventDefault()
    if (!token) { setError("Invalid or missing reset token."); return }
    if (!form.password) { setError(t('passwordRequired')); return }
    if (form.password.length < 6) { setError(t('passwordMin')); return }
    if (form.password !== form.confirm) { setError(t('passwordsMatch')); return }
    
    setError('')
    setLoading(true)
    try {
      await api('/auth/reset-password', { method: 'POST', body: { token, new_password: form.password } })
      setMessage(t('resetSuccess'))
      setTimeout(() => navigate('/login'), 3000)
    } catch (err) {
      setError(err.message || t('error.somethingWrong'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title={t('resetPassword')} error={error} onSubmit={submit} toggleLang={toggleLang} langLabel={t('langToggle')}>
      {message ? (
        <div className="rounded-md bg-green-50 p-4 text-sm text-green-700 dark:bg-green-900/30 dark:text-green-300 text-center">
          {message}
        </div>
      ) : (
        <>
          <div className="space-y-4">
            <PasswordField value={form.password} placeholder={t('newPassword')} autoComplete="new-password" visible={showPassword} onToggle={() => setShowPassword((value) => !value)} onChange={(value) => setForm({ ...form, password: value })} />
            <PasswordField value={form.confirm} placeholder={t('confirmPassword')} autoComplete="new-password" visible={showPassword} onToggle={() => setShowPassword((value) => !value)} onChange={(value) => setForm({ ...form, confirm: value })} />
          </div>
          <button type="submit" className="btn-primary w-full mt-4" disabled={loading}>
            {loading ? '...' : t('resetPassword')}
          </button>
        </>
      )}
      <div className="text-center mt-4">
        <Link className="text-sm text-slate-500 hover:underline" to="/login">{t('backToLogin')}</Link>
      </div>
    </AuthShell>
  )
}
