
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import Login      from './pages/Login.jsx'
import Dashboard  from './pages/Dashboard.jsx'
import Seeker     from './pages/Seeker.jsx'
import Recruiter  from './pages/Recruiter.jsx'

function PrivateRoute({ children }) {
  const { isAuth } = useAuth()
  return isAuth ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/"          element={<Login />} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/seeker"    element={<PrivateRoute><Seeker /></PrivateRoute>} />
          <Route path="/recruiter" element={<PrivateRoute><Recruiter /></PrivateRoute>} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
