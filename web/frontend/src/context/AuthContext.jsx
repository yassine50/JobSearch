
import { createContext, useContext, useState } from 'react'
import { clearAllCache } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const parsed = JSON.parse(localStorage.getItem('user') || 'null')
      if (!parsed || !parsed.email || !String(parsed.email).trim()) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        return null
      }
      return parsed
    } catch {
      return null
    }
  })
  const [token, setToken] = useState(() => {
    const tok = localStorage.getItem('token')
    return tok && localStorage.getItem('user') ? tok : null
  })

  const login = (tok, usr) => {
    if (!tok || !usr?.email || !String(usr.email).trim()) return
    clearAllCache()
    localStorage.setItem('token', tok)
    localStorage.setItem('user', JSON.stringify(usr))
    setToken(tok); setUser(usr)
  }

  const logout = () => {
    clearAllCache()
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken(null); setUser(null)
  }

  const updateUser = (patch) => {
    const updated = { ...user, ...patch }
    localStorage.setItem('user', JSON.stringify(updated))
    setUser(updated)
  }

  const isAuth = Boolean(token && user?.email && String(user.email).trim())

  return (
    <AuthContext.Provider value={{ token, user, login, logout, updateUser, isAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
