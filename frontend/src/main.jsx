import React, { lazy, Suspense, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import './styles/index.css'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LanguageProvider } from './context/LanguageContext'
import { GenerationJobProvider } from './context/GenerationJobContext'
import { ToastProvider } from './context/ToastContext'

// ── Lazy-load every page chunk (each becomes a separate JS file on build) ────
const Layout          = lazy(() => import('./components/Layout'))
const ErrorBoundary   = lazy(() => import('./components/ErrorBoundary'))
const Landing         = lazy(() => import('./pages/Landing'))
const Sessions        = lazy(() => import('./pages/Sessions'))
const Reports         = lazy(() => import('./pages/Reports'))
const InstructorSources = lazy(() => import('./pages/InstructorSources'))
const Profile         = lazy(() => import('./pages/Profile'))
const LiveSessionRoom = lazy(() => import('./pages/LiveSessionRoom'))
const DatabasePreview = lazy(() => import('./pages/DatabasePreview'))

// Named exports from multi-component modules resolved lazily
const Login               = lazy(() => import('./pages/Auth').then(m => ({ default: m.Login })))
const Register            = lazy(() => import('./pages/Auth').then(m => ({ default: m.Register })))
const ForgotPassword      = lazy(() => import('./pages/Auth').then(m => ({ default: m.ForgotPassword })))
const ResetPassword       = lazy(() => import('./pages/Auth').then(m => ({ default: m.ResetPassword })))
const StudentDashboard    = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.StudentDashboard })))
const InstructorDashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.InstructorDashboard })))
const Settings            = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Settings })))
const Support             = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Support })))
const NotFound            = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.NotFound })))
const LessonGenerator     = lazy(() => import('./pages/AITools').then(m => ({ default: m.LessonGenerator })))
const QuizGenerator       = lazy(() => import('./pages/AITools').then(m => ({ default: m.QuizGenerator })))
const FlashcardGenerator  = lazy(() => import('./pages/AITools').then(m => ({ default: m.FlashcardGenerator })))
const VideoLibrary        = lazy(() => import('./pages/AITools').then(m => ({ default: m.VideoLibrary })))
const StudentResources    = lazy(() => import('./pages/StudentResources'))

// ── Branded page loader with smooth entrance ─────────────────────────────────
function PageLoader() {
  return (
    <div className="loader-screen">
      <div className="loader-orb loader-orb-a" />
      <div className="loader-orb loader-orb-b" />
      <div className="loader-core">
        <div className="loader-ring" />
        <div className="loader-dot" />
      </div>
      <p className="loader-label">EduSense</p>
      <p className="loader-sub">Loading your workspace...</p>
    </div>
  )
}

// ── Short helper so each route doesn't repeat Suspense boilerplate ───────────
const S = ({ children }) => <Suspense fallback={<PageLoader />}>{children}</Suspense>

function RouteEnter({ children }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div className={`route-enter ${visible ? 'route-enter-visible' : ''} min-h-full`}>
      {children}
    </div>
  )
}

function Protected({ role, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role && user.role !== 'admin') {
    return <Navigate to={user.role === 'instructor' || user.role === 'admin' ? '/instructor' : '/student'} replace />
  }
  return children
}

const router = createBrowserRouter([
  { path: "/",                element: <S><RouteEnter><Landing /></RouteEnter></S> },
  { path: "/login",           element: <S><RouteEnter><Login /></RouteEnter></S> },
  { path: "/register",        element: <S><RouteEnter><Register /></RouteEnter></S> },
  { path: "/forgot-password", element: <S><RouteEnter><ForgotPassword /></RouteEnter></S> },
  { path: "/reset-password",  element: <S><RouteEnter><ResetPassword /></RouteEnter></S> },
  {
    element: <S><Layout /></S>,
    children: [
      { path: "/student",          element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/upcoming", element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/browse",   element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/history",  element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/profile",    element: <Protected><S><Profile /></S></Protected> },
      { path: "/student/resources",   element: <Protected role="student"><S><StudentResources /></S></Protected> },
      { path: "/student/sessions/:sessionId/live", element: <Protected><S><LiveSessionRoom /></S></Protected> },
      { path: "/instructor",       element: <Protected role="instructor"><S><InstructorDashboard /></S></Protected> },
      { path: "/instructor/sessions", element: <Protected role="instructor"><S><Sessions /></S></Protected> },
      { path: "/instructor/sessions/:sessionId/live", element: <Protected role="instructor"><S><LiveSessionRoom /></S></Protected> },
      { path: "/instructor/reports",    element: <Protected role="instructor"><S><Reports /></S></Protected> },
      { path: "/instructor/sources",    element: <Protected role="instructor"><S><InstructorSources /></S></Protected> },
      { path: "/instructor/lessons",    element: <Protected role="instructor"><S><LessonGenerator /></S></Protected> },
      { path: "/instructor/quizzes",    element: <Protected role="instructor"><S><QuizGenerator /></S></Protected> },
      { path: "/instructor/flashcards", element: <Protected role="instructor"><S><FlashcardGenerator /></S></Protected> },
      { path: "/instructor/videos",     element: <Protected role="instructor"><S><VideoLibrary /></S></Protected> },
      { path: "/instructor/database",   element: <Protected><S><DatabasePreview /></S></Protected> },
      { path: "/admin/database",        element: <Protected><S><DatabasePreview /></S></Protected> },
      { path: "/settings", element: <Protected><S><Settings /></S></Protected> },
      { path: "/support",  element: <Protected><S><Support /></S></Protected> },
    ],
  },
  { path: "*", element: <S><NotFound /></S> },
], {
  future: { v7_startTransition: true, v7_relativeSplatPath: true }
})

function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <ToastProvider>
          <GenerationJobProvider>
            <RouterProvider router={router} />
          </GenerationJobProvider>
        </ToastProvider>
      </AuthProvider>
    </LanguageProvider>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Suspense fallback={<PageLoader />}>
      <App />
    </Suspense>
  </React.StrictMode>,
)
