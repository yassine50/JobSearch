import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import { ToastProvider } from './context/ToastContext.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import SEOHead      from './components/SEOHead.jsx'
import Login        from './pages/Login.jsx'
import Dashboard    from './pages/Dashboard.jsx'
import Seeker       from './pages/Seeker.jsx'
import Recruiter    from './pages/Recruiter.jsx'
import Tracker      from './pages/Tracker.jsx'
import CoverLetter  from './pages/CoverLetter.jsx'
import EmailHistory from './pages/EmailHistory.jsx'
import Settings     from './pages/Settings.jsx'

import { useEffect } from 'react'
import { prefetchWorkspaceData } from './api/client.js'

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
