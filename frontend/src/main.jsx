import React, { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import './styles/index.css'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LanguageProvider } from './context/LanguageContext'

// ── Lazy-load every page chunk (each becomes a separate JS file on build) ────
const Layout          = lazy(() => import('./components/Layout'))
const ErrorBoundary   = lazy(() => import('./components/ErrorBoundary'))
const Landing         = lazy(() => import('./pages/Landing'))
const Sessions        = lazy(() => import('./pages/Sessions'))
const Reports         = lazy(() => import('./pages/Reports'))
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

// ── Spinner & smooth fade transition shown during any lazy-chunk load ──────────
function PageLoader() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-slate-950/90 backdrop-blur-md transition-opacity duration-500 animate-fade-in">
      <div className="relative flex items-center justify-center">
        {/* Glowing aura ring */}
        <div className="absolute h-20 w-20 rounded-full bg-cyan-500/20 blur-xl animate-pulse" />
        {/* Smooth double spinning rings */}
        <div className="h-14 w-14 rounded-full border-4 border-cyan-500/20 border-t-cyan-400 border-r-indigo-500 animate-spin" />
        <div className="absolute h-8 w-8 rounded-full border-2 border-indigo-400/30 border-b-cyan-300 animate-spin-reverse" />
      </div>
      <p className="mt-4 text-sm font-semibold tracking-wider text-slate-300 animate-pulse">
        Loading EduSense...
      </p>
      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: scale(1); } }
        @keyframes spinReverse { from { transform: rotate(360deg); } to { transform: rotate(0deg); } }
        .animate-fade-in { animation: fadeIn 0.35s ease-out forwards; }
        .animate-spin-reverse { animation: spinReverse 1.2s linear infinite; }
      `}</style>
    </div>
  )
}

// ── Short helper so each route doesn't repeat Suspense boilerplate ───────────
const S = ({ children }) => <Suspense fallback={<PageLoader />}>{children}</Suspense>


function Protected({ role, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={user.role === 'instructor' ? '/instructor' : '/student'} replace />
  return children
}

const router = createBrowserRouter([
  { path: "/",                element: <S><Landing /></S> },
  { path: "/login",           element: <S><Login /></S> },
  { path: "/register",        element: <S><Register /></S> },
  { path: "/forgot-password", element: <S><ForgotPassword /></S> },
  { path: "/reset-password",  element: <S><ResetPassword /></S> },
  {
    element: <S><Layout /></S>,
    children: [
      { path: "/student",          element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/upcoming", element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/browse",   element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/history",  element: <Protected role="student"><S><StudentDashboard /></S></Protected> },
      { path: "/student/profile",  element: <Protected role="student"><S><Profile /></S></Protected> },
      { path: "/student/sessions/:sessionId/live", element: <Protected role="student"><S><LiveSessionRoom /></S></Protected> },
      { path: "/instructor",       element: <Protected role="instructor"><S><InstructorDashboard /></S></Protected> },
      { path: "/instructor/sessions", element: <Protected role="instructor"><S><Sessions /></S></Protected> },
      { path: "/instructor/sessions/:sessionId/live", element: <Protected role="instructor"><S><LiveSessionRoom /></S></Protected> },
      { path: "/instructor/reports",    element: <Protected role="instructor"><S><Reports /></S></Protected> },
      { path: "/instructor/lessons",    element: <Protected role="instructor"><S><LessonGenerator /></S></Protected> },
      { path: "/instructor/quizzes",    element: <Protected role="instructor"><S><QuizGenerator /></S></Protected> },
      { path: "/instructor/flashcards", element: <Protected role="instructor"><S><FlashcardGenerator /></S></Protected> },
      { path: "/instructor/videos",     element: <Protected role="instructor"><S><VideoLibrary /></S></Protected> },
      { path: "/instructor/database",   element: <Protected role="instructor"><S><DatabasePreview /></S></Protected> },
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
        <RouterProvider router={router} />
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
