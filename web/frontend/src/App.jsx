import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import { ToastProvider } from './context/ToastContext.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import SEOHead      from './components/SEOHead.jsx'
import Sidebar      from './components/Sidebar.jsx'
import Login        from './pages/Login.jsx'
import Seeker       from './pages/Seeker.jsx'
import Tracker      from './pages/Tracker.jsx'
import CoverLetter  from './pages/CoverLetter.jsx'
import EmailHistory from './pages/EmailHistory.jsx'
import Settings     from './pages/Settings.jsx'
import { prefetchWorkspaceData } from './api/client.js'

// Lazy-load secondary analytics pages while keeping core daily routes pre-bundled for zero CLS/INP
const Dashboard    = lazy(() => import('./pages/Dashboard.jsx'))
const Recruiter    = lazy(() => import('./pages/Recruiter.jsx'))
const BackOffice   = lazy(() => import('./pages/BackOffice.jsx'))

function RouteFallback() {
  return (
    <div className="flex min-h-screen bg-[#050811] text-white">
      <Sidebar />
      <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14 flex items-center justify-center">
        <div className="flex items-center gap-3 px-5 py-3 rounded-2xl glass-panel text-xs font-bold text-slate-300">
          <div className="w-5 h-5 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
          <span>Loading workspace...</span>
        </div>
      </main>
    </div>
  )
}

function PrivateRoute({ children }) {
  const { isAuth } = useAuth()
  useEffect(() => {
    if (isAuth) prefetchWorkspaceData()
  }, [isAuth])
  return isAuth ? children : <Navigate to="/" replace />
}
const P = ({ C }) => <PrivateRoute><C /></PrivateRoute>

function AnimatedRoutes() {
  const location = useLocation()
  const { isAuth } = useAuth()
  useEffect(() => {
    if (isAuth) prefetchWorkspaceData()
  }, [isAuth])
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes location={location}>
        {/* Public Landing Page with Live App Test Workbench + Guest Seeker Route */}
        <Route path="/"                           element={<Login />} />
        <Route path="/seeker"                     element={<Seeker />} />
        <Route path="/login"                      element={<Login />} />
        <Route path="/ats-resume-checker"         element={<Login />} />
        <Route path="/linkedin-recruiter-posts"   element={<Login />} />
        <Route path="/ai-cover-letter-generator"  element={<Login />} />
        <Route path="/job-application-tracker"    element={<Login />} />
        <Route path="/recruiter-talent-sourcing"  element={<Login />} />

        {/* Authenticated Workspace Routes */}
        <Route path="/dashboard"    element={<P C={Dashboard}   />} />
        <Route path="/recruiter"    element={<P C={Recruiter}   />} />
        <Route path="/tracker"      element={<P C={Tracker}     />} />
        <Route path="/coverletter"  element={<P C={CoverLetter} />} />
        <Route path="/cover-letter" element={<P C={CoverLetter} />} />
        <Route path="/email"        element={<P C={EmailHistory}/>} />
        <Route path="/settings"     element={<P C={Settings}    />} />
        <Route path="/backoffice"   element={<BackOffice />} />
        <Route path="/admin"        element={<BackOffice />} />
        <Route path="*"             element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
              <SEOHead />
              <CommandPalette />
              <AnimatedRoutes />
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
