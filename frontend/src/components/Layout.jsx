import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { BarChart3, BookOpen, Clapperboard, Compass, Database, FileText, FolderOpen, GraduationCap, Globe, Home, Layers, LogOut, Menu, MessageCircle, Moon, Sun, UserRound, Video, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import AnimatedBackground from './AnimatedBackground'
import PageTransition from './PageTransition'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import { useGenerationJobs } from '../context/GenerationJobContext'

function SidebarNav({ items, onNavigate }) {
  return (
    <nav className="mt-8 space-y-1">
      {items.map(({ label, path, Icon }) => (
        <NavLink
          key={path}
          to={path}
          end={path === '/student' || path === '/instructor'}
          onClick={onNavigate}
          className={({ isActive }) => `nav-link ${isActive ? 'active text-slate-600 dark:text-slate-100' : 'text-slate-600 dark:text-slate-300'}`}
        >
          <Icon size={18} />{label}
        </NavLink>
      ))}
    </nav>
  )
}

// Render settings label via `t` inside Layout (ensures hook call order)

export default function Layout() {
  const { user, logout } = useAuth()
  const { t, toggleLang, lang } = useLanguage()
  const { pendingCount } = useGenerationJobs()
  const navigate = useNavigate()
  const [dark, setDark] = useState(() => localStorage.theme === 'dark')
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.theme = dark ? 'dark' : 'light'
  }, [dark])

  const studentNav = [
    { label: t('nav.dashboard'), path: '/student', Icon: Home },
    { label: t('nav.upcoming'), path: '/student/upcoming', Icon: BookOpen },
    { label: t('nav.browse'), path: '/student/browse', Icon: Compass },
    { label: t('nav.history'), path: '/student/history', Icon: BarChart3 },
    { label: 'My Resources', path: '/student/resources', Icon: FolderOpen },
    { label: t('nav.profile'), path: '/student/profile', Icon: UserRound },
  ]
  const instructorNav = [
    { label: t('nav.dashboard'), path: '/instructor', Icon: Home },
    { label: t('nav.sessions'), path: '/instructor/sessions', Icon: BookOpen },
    { label: t('nav.reports'), path: '/instructor/reports', Icon: BarChart3 },
    { label: 'Sources', path: '/instructor/sources', Icon: FileText },
    { label: t('nav.lessons'), path: '/instructor/lessons', Icon: GraduationCap },
    { label: t('nav.quizzes'), path: '/instructor/quizzes', Icon: MessageCircle },
    { label: t('nav.flashcards'), path: '/instructor/flashcards', Icon: Layers },
    { label: t('nav.videos'), path: '/instructor/videos', Icon: Clapperboard },
    { label: t('nav.profile'), path: '/student/profile', Icon: UserRound },
  ]
  const adminNav = [
    ...instructorNav,
    { label: 'Database Preview', path: '/admin/database', Icon: Database },
  ]
  const nav = user?.role === 'admin' ? adminNav : user?.role === 'instructor' ? instructorNav : studentNav

  return (
    <div className="relative min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <AnimatedBackground />
      <aside className="fixed inset-y-0 start-0 z-20 hidden w-56 border-e border-slate-200/80 bg-white/95 p-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95 md:flex md:flex-col md:justify-between xl:w-64">
        <div>
          <Link to="/" className="flex items-center gap-3 text-xl font-black text-ocean dark:text-mint"><Video /> {t('appName')}</Link>
          <SidebarNav items={nav} />
        </div>
        
        {/* Sidebar Footer Controls */}
        <div className="border-t border-slate-200/80 pt-4 dark:border-slate-800 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <button type="button" className="btn-soft flex-1 justify-center" onClick={toggleLang} title={lang === 'ar' ? 'English' : 'العربية'}>
              <Globe size={18} />
              <span className="ms-2 text-sm">{lang === 'ar' ? 'En' : 'عربي'}</span>
            </button>
            <button type="button" className="btn-soft p-2" onClick={() => setDark(!dark)}>
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
          {user && (
            <button type="button" className="btn-soft w-full justify-center text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20" onClick={() => { logout(); navigate('/login') }}>
              <LogOut size={18} />
              <span className="ms-2 text-sm">{t('logout')}</span>
            </button>
          )}
          {pendingCount > 0 && (
            <p className="rounded-xl bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-800 dark:bg-teal-950/40 dark:text-teal-200">
              {pendingCount} AI job{pendingCount > 1 ? 's' : ''} running in background
            </p>
          )}
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="absolute inset-0 bg-black/40" aria-label="Close menu" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-72 border-e border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <Link to="/" className="flex items-center gap-3 text-xl font-black text-ocean dark:text-mint" onClick={() => setMobileOpen(false)}><Video /> {t('appName')}</Link>
                <button type="button" className="btn-soft" onClick={() => setMobileOpen(false)}><X size={18} /></button>
              </div>
              <SidebarNav items={nav} onNavigate={() => setMobileOpen(false)} />
            </div>
            
            {/* Mobile Footer Controls */}
            <div className="border-t border-slate-200/80 pt-4 dark:border-slate-800 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <button type="button" className="btn-soft flex-1 justify-center" onClick={() => { toggleLang(); setMobileOpen(false) }} title={lang === 'ar' ? 'English' : 'العربية'}>
                  <Globe size={18} />
                  <span className="ms-2 text-sm">{lang === 'ar' ? 'English' : 'العربية'}</span>
                </button>
                <button type="button" className="btn-soft p-2" onClick={() => setDark(!dark)}>
                  {dark ? <Sun size={18} /> : <Moon size={18} />}
                </button>
              </div>
              {user && (
                <button type="button" className="btn-soft w-full justify-center text-red-600" onClick={() => { logout(); navigate('/login'); setMobileOpen(false) }}>
                  <LogOut size={18} />
                  <span className="ms-2 text-sm">{t('logout')}</span>
                </button>
              )}
            </div>
          </aside>
        </div>
      )}

      <main className="min-w-0 md:ps-56 xl:ps-64">
        <header className="sticky top-0 z-10 flex min-h-16 flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 bg-white/90 px-3 py-2 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 sm:px-4 md:hidden">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" className="btn-soft md:hidden" onClick={() => setMobileOpen(true)}><Menu size={18} /></button>
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-wide text-slate-500">{t('platform')}</p>
              <h1 className="truncate font-bold">{user?.name || t('appName')}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {pendingCount > 0 && (
              <span className="rounded-full bg-teal-100 px-2.5 py-1 text-xs font-semibold text-teal-800 dark:bg-teal-950/50 dark:text-teal-200">
                {pendingCount} generating
              </span>
            )}
            <button type="button" className="btn-soft" onClick={toggleLang} title={lang === 'ar' ? 'English' : 'العربية'}>
              <Globe size={18} /><span className="hidden sm:inline">{t('langToggle')}</span>
            </button>
            <button type="button" className="btn-soft" onClick={() => setDark(!dark)}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
            {user && (
              <button type="button" className="btn-soft" onClick={() => { logout(); navigate('/login') }}>
                <LogOut size={18} /><span className="hidden sm:inline">{t('logout')}</span>
              </button>
            )}
          </div>
        </header>
        <div className="page-shell p-3 sm:p-4 md:p-6">
          <PageTransition>
            <Outlet />
          </PageTransition>
        </div>
      </main>
    </div>
  )
}
