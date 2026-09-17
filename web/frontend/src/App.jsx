
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import { ToastProvider } from './context/ToastContext.jsx'
import Login        from './pages/Login.jsx'
import Dashboard    from './pages/Dashboard.jsx'
import Seeker       from './pages/Seeker.jsx'
import Recruiter    from './pages/Recruiter.jsx'
import Tracker      from './pages/Tracker.jsx'
import CoverLetter  from './pages/CoverLetter.jsx'
import EmailHistory from './pages/EmailHistory.jsx'
import Settings     from './pages/Settings.jsx'

function PrivateRoute({ children }) {
  const { isAuth } = useAuth()
  return isAuth ? children : <Navigate to="/" replace />
}
const P = ({ C }) => <PrivateRoute><C /></PrivateRoute>

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/"            element={<Login />} />
        <Route path="/dashboard"   element={<P C={Dashboard}   />} />
        <Route path="/seeker"      element={<P C={Seeker}      />} />
        <Route path="/recruiter"   element={<P C={Recruiter}   />} />
        <Route path="/tracker"     element={<P C={Tracker}     />} />
        <Route path="/coverletter" element={<P C={CoverLetter} />} />
        <Route path="/email"       element={<P C={EmailHistory}/>} />
        <Route path="/settings"    element={<P C={Settings}    />} />
        <Route path="*"            element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <AnimatedRoutes />
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  )
}
