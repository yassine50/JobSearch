import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import { ToastProvider } from './context/ToastContext.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import SEOHead      from './components/SEOHead.jsx'
import Login        from './pages/Login.jsx'
import { prefetchWorkspaceData } from './api/client.js'

// Route-based code splitting for workspace pages
const Seeker       = lazy(() => import('./pages/Seeker.jsx'))
const Dashboard    = lazy(() => import('./pages/Dashboard.jsx'))
const Recruiter    = lazy(() => import('./pages/Recruiter.jsx'))
const Tracker      = lazy(() => import('./pages/Tracker.jsx'))
const CoverLetter  = lazy(() => import('./pages/CoverLetter.jsx'))
const EmailHistory = lazy(() => import('./pages/EmailHistory.jsx'))
const Settings     = lazy(() => import('./pages/Settings.jsx'))

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050811] text-white">
      <div className="flex items-center gap-3 px-5 py-3 rounded-2xl glass-panel text-xs font-bold text-slate-300">
        <div className="w-5 h-5 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
        <span>Loading workspace...</span>
      </div>
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
