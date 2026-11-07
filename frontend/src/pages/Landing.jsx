import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart3, BookOpen, BrainCircuit, Clapperboard, Globe, Layers,
  MessageCircle, MonitorPlay, Moon, ShieldCheck, Sparkles, Sun, Users, Video,
} from 'lucide-react'
import AnimatedBackground from '../components/AnimatedBackground'
import { useLanguage } from '../context/LanguageContext'

export default function Landing() {
  const { t, toggleLang } = useLanguage()
  const [dark, setDark] = useState(() => localStorage.theme === 'dark' || document.documentElement.classList.contains('dark'))
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.theme = dark ? 'dark' : 'light'
  }, [dark])

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 40)
    return () => clearTimeout(timer)
  }, [])

  const features = [
    { key: 'landing.feat1Title', desc: 'landing.feat1Desc', icon: Sparkles },
    { key: 'landing.feat2Title', desc: 'landing.feat2Desc', icon: MessageCircle },
    { key: 'landing.feat3Title', desc: 'landing.feat3Desc', icon: Layers },
    { key: 'landing.feat4Title', desc: 'landing.feat4Desc', icon: Video },
    { key: 'landing.feat5Title', desc: 'landing.feat5Desc', icon: MonitorPlay },
    { key: 'landing.feat6Title', desc: 'landing.feat6Desc', icon: BarChart3 },
  ]

  const steps = [
    ['1', 'landing.step1'],
    ['2', 'landing.step2'],
    ['3', 'landing.step3'],
    ['4', 'landing.step4'],
  ]

  return (
    <div className={`landing-page relative min-h-screen overflow-x-hidden bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-white ${mounted ? 'opacity-100' : 'opacity-0'}`}>
      <AnimatedBackground />
      <header className="relative z-20 mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <p className="text-xl font-black text-ocean dark:text-mint">{t('appName')}</p>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-soft flex items-center gap-1.5" onClick={() => setDark(!dark)} title={dark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
            {dark ? <Sun size={18} className="text-amber-400" /> : <Moon size={18} className="text-indigo-600" />}
            <span className="hidden sm:inline text-xs font-semibold">{dark ? 'Light' : 'Dark'}</span>
          </button>
          <button type="button" className="btn-soft" onClick={toggleLang}><Globe size={18} /><span className="hidden sm:inline">{t('langToggle')}</span></button>
          <Link className="btn-soft hidden sm:inline-flex" to="/login">{t('login')}</Link>
        </div>
      </header>

      <section className="relative overflow-hidden hero-shimmer">
        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1523580846011-d3a5bc25702b?auto=format&fit=crop&w=1800&q=80')] bg-cover bg-center scale-105 transition-transform duration-[2s] ease-out" />
        <div className="absolute inset-0 bg-gradient-to-b from-slate-950/75 via-slate-950/65 to-slate-950/90" />
        <div className="hero-glow pointer-events-none absolute left-1/2 top-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-teal-400/20 blur-3xl" />
        <div className="relative mx-auto flex min-h-[72vh] max-w-6xl flex-col justify-center px-4 py-12 sm:px-6 sm:py-16 landing-hero-content">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-mint animate-float-soft">{t('landing.tagline')}</p>
          <h1 className="max-w-4xl text-3xl font-black leading-[1.08] sm:text-5xl md:text-6xl lg:text-7xl">{t('landing.heroTitle')}</h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-slate-100 sm:text-lg">{t('landing.subtitle')}</p>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300 sm:text-base">{t('landing.heroDetail')}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="btn-primary shadow-lg shadow-teal-500/20" to="/register">{t('landing.getStarted')}</Link>
            <Link className="btn-soft bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm" to="/login">{t('login')}</Link>
          </div>
          <div className="mt-10 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-4 landing-stagger">
            {[['landing.stat1', '12+'], ['landing.stat2', 'Gemini'], ['landing.stat3', '100%'], ['landing.stat4', 'AR/EN']].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-white/10 bg-white/10 p-3 backdrop-blur-md sm:p-4 transition hover:bg-white/15 hover:-translate-y-0.5">
                <p className="text-lg font-black text-mint sm:text-2xl">{value}</p>
                <p className="text-xs text-slate-200 sm:text-sm">{t(label)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <h2 className="text-2xl font-black sm:text-3xl">{t('landing.featuresTitle')}</h2>
        <p className="mt-2 max-w-2xl text-slate-600 dark:text-slate-300">{t('landing.featuresSubtitle')}</p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 landing-stagger">
          {features.map(({ key, desc, icon: Icon }) => (
            <article className="panel" key={key}>
              <Icon className="mb-3 text-ocean dark:text-mint" size={28} />
              <h3 className="font-bold">{t(key)}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{t(desc)}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-ocean/5 py-12 dark:bg-slate-900/50 sm:py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="text-2xl font-black sm:text-3xl">{t('landing.howTitle')}</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4 landing-stagger">
            {steps.map(([num, key]) => (
              <div className="panel" key={num}>
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-ocean to-teal-600 text-lg font-black text-white shadow-md">{num}</span>
                <p className="mt-4 text-sm leading-relaxed">{t(key)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-4 py-12 sm:grid-cols-2 sm:px-6 xl:grid-cols-4 landing-stagger">
        {[['landing.agents', BrainCircuit], ['landing.charts', BarChart3], ['landing.videoTools', Clapperboard], ['landing.auth', ShieldCheck]].map(([key, Icon]) => (
          <div className="panel flex items-center gap-3" key={key}>
            <Icon className="shrink-0 text-ocean dark:text-mint" />
            <h2 className="font-bold">{t(key)}</h2>
          </div>
        ))}
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <div className="panel flex flex-col items-start justify-between gap-6 bg-gradient-to-r from-ocean to-teal-700 p-6 text-white shadow-xl shadow-teal-900/20 sm:flex-row sm:items-center sm:p-8">
          <div>
            <h2 className="text-2xl font-black">{t('landing.ctaTitle')}</h2>
            <p className="mt-2 max-w-xl text-teal-50">{t('landing.ctaSubtitle')}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link className="btn-soft bg-white text-ocean hover:bg-teal-50" to="/register"><Users size={18} />{t('register')}</Link>
            <Link className="btn-soft bg-white/15 text-white hover:bg-white/25" to="/login"><BookOpen size={18} />{t('login')}</Link>
          </div>
        </div>
      </section>
    </div>
  )
}
