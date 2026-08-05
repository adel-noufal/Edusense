import React from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate, Route, Routes } from 'react-router-dom'
import './styles/index.css'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LanguageProvider } from './context/LanguageContext'
import Landing from './pages/Landing'
import { Login, Register, ForgotPassword, ResetPassword } from './pages/Auth'
import { About, InstructorDashboard, NotFound, Settings, StudentDashboard, Support } from './pages/Dashboard'
import Sessions from './pages/Sessions'
import { LessonGenerator, QuizGenerator, VideoLibrary, FlashcardGenerator } from './pages/AITools'
import Reports from './pages/Reports'
import Profile from './pages/Profile'
import LiveSessionRoom from './pages/LiveSessionRoom'
import DatabasePreview from './pages/DatabasePreview'

function Protected({ role, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={user.role === 'instructor' ? '/instructor' : '/student'} replace />
  return children
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Landing />,
  },
  {
    path: "/about",
    element: <About />,
  },
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/register",
    element: <Register />,
  },
  {
    path: "/forgot-password",
    element: <ForgotPassword />,
  },
  {
    path: "/reset-password",
    element: <ResetPassword />,
  },
  {
    element: <Layout />,
    children: [
      { path: "/student", element: <Protected role="student"><StudentDashboard /></Protected> },
      { path: "/student/upcoming", element: <Protected role="student"><StudentDashboard /></Protected> },
      { path: "/student/browse", element: <Protected role="student"><StudentDashboard /></Protected> },
      { path: "/student/history", element: <Protected role="student"><StudentDashboard /></Protected> },
      { path: "/student/profile", element: <Protected role="student"><Profile /></Protected> },
      { path: "/instructor", element: <Protected role="instructor"><InstructorDashboard /></Protected> },
      { path: "/instructor/sessions", element: <Protected role="instructor"><Sessions /></Protected> },
      { path: "/instructor/sessions/:sessionId/live", element: <Protected role="instructor"><LiveSessionRoom /></Protected> },
      { path: "/student/sessions/:sessionId/live", element: <Protected role="student"><LiveSessionRoom /></Protected> },
      { path: "/instructor/reports", element: <Protected role="instructor"><Reports /></Protected> },
      { path: "/instructor/lessons", element: <Protected role="instructor"><LessonGenerator /></Protected> },
      { path: "/instructor/quizzes", element: <Protected role="instructor"><QuizGenerator /></Protected> },
      { path: "/instructor/flashcards", element: <Protected role="instructor"><FlashcardGenerator /></Protected> },
      { path: "/instructor/videos", element: <Protected role="instructor"><VideoLibrary /></Protected> },
      { path: "/instructor/database", element: <Protected role="instructor"><DatabasePreview /></Protected> },
      { path: "/settings", element: <Protected><Settings /></Protected> },
      { path: "/support", element: <Protected><Support /></Protected> },
    ],
  },
  {
    path: "*",
    element: <NotFound />,
  },
], {
  future: {
    v7_startTransition: true,
    v7_relativeSplatPath: true,
  }
})

function App() {
  return <LanguageProvider><AuthProvider><RouterProvider router={router} /></AuthProvider></LanguageProvider>
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
