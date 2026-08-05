import { Link } from 'react-router-dom'
import {
  BarChart3, BookOpen, BrainCircuit, Clapperboard, Globe, Layers,
  MessageCircle, MonitorPlay, ShieldCheck, Sparkles, Users, Video,
} from 'lucide-react'
import AnimatedBackground from '../components/AnimatedBackground'
import { useLanguage } from '../context/LanguageContext'

export default function Landing() {
  const { t, toggleLang } = useLanguage()

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
    <div className="relative min-h-screen overflow-x-hidden bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-white">
      <AnimatedBackground />
      <header className="relative z-20 mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <p className="text-xl font-black text-ocean dark:text-mint">{t('appName')}</p>
        <div className="flex gap-2">
          <button type="button" className="btn-soft" onClick={toggleLang}><Globe size={18} /><span className="hidden sm:inline">{t('langToggle')}</span></button>
          <Link className="btn-soft hidden sm:inline-flex" to="/login">{t('login')}</Link>
        </div>
      </header>

      <section className="relative overflow-hidden bg-[url('https://images.unsplash.com/photo-1523580846011-d3a5bc25702b?auto=format&fit=crop&w=1800&q=80')] bg-cover bg-center">
        <div className="absolute inset-0 bg-slate-950/70" />
        <div className="relative mx-auto flex min-h-[70vh] max-w-6xl flex-col justify-center px-4 py-12 sm:px-6 sm:py-16">
          <p className="mb-3 animate-float text-sm font-semibold uppercase tracking-wide text-mint">{t('landing.tagline')}</p>
          <h1 className="max-w-4xl text-3xl font-black leading-tight sm:text-5xl md:text-6xl lg:text-7xl">{t('landing.heroTitle')}</h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-slate-100 sm:text-lg">{t('landing.subtitle')}</p>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300 sm:text-base">{t('landing.heroDetail')}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="btn-primary" to="/register">{t('landing.getStarted')}</Link>
            <Link className="btn-soft bg-white/15 text-white hover:bg-white/25" to="/login">{t('login')}</Link>
          </div>
          <div className="mt-10 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-4">
            {[['landing.stat1', '12+'], ['landing.stat2', 'Gemini'], ['landing.stat3', '100%'], ['landing.stat4', 'AR/EN']].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-white/10 p-3 backdrop-blur sm:p-4">
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
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ key, desc, icon: Icon }) => (
            <article className="panel animate-float" key={key}>
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
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(([num, key]) => (
              <div className="panel" key={num}>
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ocean text-lg font-black text-white">{num}</span>
                <p className="mt-4 text-sm leading-relaxed">{t(key)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-4 py-12 sm:grid-cols-2 sm:px-6 xl:grid-cols-4">
        {[['landing.agents', BrainCircuit], ['landing.charts', BarChart3], ['landing.videoTools', Clapperboard], ['landing.auth', ShieldCheck]].map(([key, Icon]) => (
          <div className="panel flex items-center gap-3" key={key}>
            <Icon className="shrink-0 text-ocean dark:text-mint" />
            <h2 className="font-bold">{t(key)}</h2>
          </div>
        ))}
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <div className="panel flex flex-col items-start justify-between gap-6 bg-gradient-to-r from-ocean to-teal-700 p-6 text-white sm:flex-row sm:items-center sm:p-8">
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
