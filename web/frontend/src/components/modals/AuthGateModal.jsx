import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Lock, Sparkles, ShieldCheck, Mail, CheckCircle2, ArrowRight, X, Loader2 } from 'lucide-react'
import client, { prefetchWorkspaceData } from '../../api/client.js'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'

export function AuthFormCard({
  title = 'Create a Free Account to Unlock Your Search Results',
  subtitle = 'Instant access to full job descriptions, verified recruiter emails, 100% ATS CV tailoring, and 1-click outreach.',
  badgeText = 'Search Results Ready',
  onClose = null,
  onSuccess = null,
}) {
  const { login } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [tab, setTab] = useState('register')
  const [busy, setBusy] = useState(false)
  const [googleBusy, setGoogleBusy] = useState(false)
  const [err, setErr] = useState('')
  const [googleClientId, setGoogleClientId] = useState(
    () => (import.meta.env.VITE_GOOGLE_CLIENT_ID || '351639376298-otgv89j6pf4mbtmpgibjg0l9l7bhllbt.apps.googleusercontent.com').trim()
  )

  const [rf, setRf] = useState({ name: '', email: '', password: '', role: 'seeker' })
  const [lf, setLf] = useState(() => ({
    email: localStorage.getItem('saved_login_email') || '',
    password: '',
  }))

  useEffect(() => {
    client.get('/auth/google-config').then(res => {
      if (res.data?.client_id) setGoogleClientId(res.data.client_id)
    }).catch(() => {})
  }, [])

  const finishAuth = (token, user, welcomeMsg) => {
    try { localStorage.setItem('saved_login_email', user?.email || '') } catch {}
    login(token, user)
    setTimeout(() => prefetchWorkspaceData(), 50)
    toast(welcomeMsg || `Welcome, ${user?.name || user?.email}! Search results unlocked.`, 'success')
    if (onSuccess) onSuccess(user)
    if (onClose) onClose()
    if (location.pathname !== '/seeker') {
      navigate('/seeker', { replace: true })
    }
  }

  const ensureGoogleScript = () =>
    new Promise((resolve, reject) => {
      if (window.google?.accounts?.oauth2) {
        resolve(window.google)
        return
      }
      const existing = document.querySelector('script[src*="accounts.google.com/gsi/client"]')
      if (existing) {
        let checks = 0
        const timer = setInterval(() => {
          checks += 1
          if (window.google?.accounts?.oauth2) {
            clearInterval(timer)
            resolve(window.google)
          } else if (checks > 40) {
            clearInterval(timer)
            reject(new Error('Google Sign-In script took too long to load.'))
          }
        }, 100)
        return
      }
      const s = document.createElement('script')
      s.src = 'https://accounts.google.com/gsi/client'
      s.async = true
      s.defer = true
      s.onload = () => resolve(window.google)
      s.onerror = () => reject(new Error('Failed to load Google Sign-In script.'))
      document.head.appendChild(s)
    })

  const doGoogleAuth = async () => {
    setErr('')
    setGoogleBusy(true)
    try {
      await ensureGoogleScript()
      if (!window.google?.accounts?.oauth2) {
        throw new Error('Google Sign-In is unavailable in this browser.')
      }
      const tokenClient = window.google.accounts.oauth2.initTokenClient({
        client_id: googleClientId,
        scope: 'openid email profile',
        callback: async (tokenResponse) => {
          if (tokenResponse?.error) {
            setGoogleBusy(false)
            if (tokenResponse.error !== 'popup_closed_by_user' && tokenResponse.error !== 'access_denied') {
              setErr(`Google Sign-In error: ${tokenResponse.error_description || tokenResponse.error}`)
            }
            return
          }
          const gToken = tokenResponse?.access_token
          if (!gToken) {
            setGoogleBusy(false)
            setErr('Did not receive an access token from Google.')
            return
          }
          try {
            const { data } = await client.post('/auth/google', {
              access_token: gToken,
              role: rf.role || 'seeker',
            })
            finishAuth(data.access_token, data.user, 'Signed in with Google! Search results unlocked.')
          } catch (apiErr) {
            setErr(apiErr?.response?.data?.detail || 'Google authentication failed.')
          } finally {
            setGoogleBusy(false)
          }
        },
        error_callback: () => setGoogleBusy(false),
      })
      tokenClient.requestAccessToken({ prompt: 'select_account' })
    } catch (e) {
      setGoogleBusy(false)
      setErr(e?.message || 'Could not start Google Sign-In.')
    }
  }

  const handleRegister = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    const email = (rf.email || '').trim().toLowerCase()
    const password = rf.password || ''
    const name = (rf.name || '').trim() || email.split('@')[0]
    if (!email || !email.includes('@')) {
      setErr('Please enter a valid email address.')
      return
    }
    if (password.length < 6) {
      setErr('Password must be at least 6 characters.')
      return
    }
    setBusy(true)
    setErr('')
    try {
      const { data } = await client.post('/auth/register', {
        name,
        email,
        password,
        role: rf.role || 'seeker',
      })
      finishAuth(data.access_token, data.user, 'Account created! Your search results are now unlocked.')
    } catch (regErr) {
      // If email is already registered, seamlessly try logging in with the entered password
      if (regErr?.response?.status === 400) {
        try {
          const { data } = await client.post('/auth/login', { email, password })
          finishAuth(data.access_token, data.user, 'Welcome back! Your search results are unlocked.')
          return
        } catch {}
      }
      setErr(regErr?.response?.data?.detail || 'Could not create account. Try signing in if you already have one.')
    } finally {
      setBusy(false)
    }
  }

  const handleLogin = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    const email = (lf.email || '').trim().toLowerCase()
    const password = lf.password || ''
    if (!email || !password) {
      setErr('Please enter your email and password.')
      return
    }
    setBusy(true)
    setErr('')
    try {
      const { data } = await client.post('/auth/login', { email, password })
      finishAuth(data.access_token, data.user, 'Signed in! Your search results are now unlocked.')
    } catch (loginErr) {
      if (loginErr?.response?.status === 401 && password.length >= 6 && email.includes('@')) {
        try {
          const autoName = email.split('@')[0].replace(/[._-]+/g, ' ').trim() || 'Candidate'
          const { data } = await client.post('/auth/register', {
            name: autoName,
            email,
            password,
            role: 'seeker',
          })
          finishAuth(data.access_token, data.user, 'Account created! Your search results are now unlocked.')
          return
        } catch {}
      }
      setErr(loginErr?.response?.data?.detail || 'Invalid email or password.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="w-full max-w-md mx-auto rounded-3xl bg-[#0A0F1F]/95 border border-blue-500/40 shadow-2xl shadow-blue-950/80 p-6 sm:p-7 relative overflow-hidden backdrop-blur-2xl"
    >
      <div className="glow-line-top" />

      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.1] transition cursor-pointer"
        >
          <X size={16} />
        </button>
      )}

      {/* Header */}
      <div className="text-center space-y-2 mb-5">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gradient-to-r from-blue-500/20 to-purple-500/20 border border-blue-400/35 text-blue-300 text-[11px] font-extrabold">
          <Lock size={12} className="text-amber-400" />
          <span>{badgeText}</span>
        </div>
        <h3 className="text-lg sm:text-xl font-black text-white tracking-tight leading-snug">
          {title}
        </h3>
        <p className="text-xs text-slate-300/90 leading-relaxed">
          {subtitle}
        </p>
      </div>

      {/* Feature Value Pills */}
      <div className="grid grid-cols-3 gap-2 mb-5">
        {[
          { icon: Mail, label: 'Verified Emails' },
          { icon: Sparkles, label: '100% CV Tailor' },
          { icon: ShieldCheck, label: '1-Click Apply' },
        ].map(({ icon: Icon, label }) => (
          <div
            key={label}
            className="flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-xl bg-white/[0.03] border border-white/[0.07] text-[11px] font-bold text-slate-200"
          >
            <Icon size={12} className="text-blue-400 shrink-0" />
            <span className="truncate">{label}</span>
          </div>
        ))}
      </div>

      {/* Google 1-Click Button */}
      <button
        type="button"
        onClick={doGoogleAuth}
        disabled={googleBusy || busy}
        className="w-full py-2.5 px-4 rounded-xl bg-white hover:bg-slate-100 border border-slate-200 text-slate-900 font-extrabold text-xs flex items-center justify-center gap-2.5 shadow-sm transition cursor-pointer disabled:opacity-60 mb-4"
      >
        {googleBusy ? (
          <Loader2 size={15} className="animate-spin text-slate-700" />
        ) : (
          <svg className="w-4 h-4" viewBox="0 0 24 24">
            <path fill="#EA4335" d="M12 5c1.6 0 3 .6 4.1 1.7l3.1-3.1C17.3 1.8 14.8 1 12 1 7.4 1 3.5 3.6 1.6 7.4l3.7 2.8C6.2 7.2 8.9 5 12 5z" />
            <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.6l3.7 2.9c2.2-2 3.7-5 3.7-8.7z" />
            <path fill="#FBBC05" d="M5.3 14.8c-.2-.8-.4-1.6-.4-2.5s.2-1.7.4-2.5L1.6 7C.6 9 0 11.2 0 13.5s.6 4.5 1.6 6.5l3.7-2.9z" />
            <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3.1 0-5.8-2.1-6.7-5l-3.7 2.8C3.5 21.4 7.4 24 12 24z" />
          </svg>
        )}
        <span>{googleBusy ? 'Connecting Google...' : 'Continue with Google (1-Click)'}</span>
      </button>

      <div className="flex items-center gap-3 my-3.5">
        <div className="h-px flex-1 bg-white/[0.08]" />
        <span className="text-[10px] uppercase tracking-widest font-bold text-slate-400">or with email</span>
        <div className="h-px flex-1 bg-white/[0.08]" />
      </div>

      {/* Mode Switcher Tabs */}
      <div className="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-slate-950/90 border border-white/[0.07] mb-4">
        <button
          type="button"
          onClick={() => { setTab('register'); setErr('') }}
          className={`py-2 rounded-lg text-xs font-extrabold transition cursor-pointer ${
            tab === 'register'
              ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Create Free Account
        </button>
        <button
          type="button"
          onClick={() => { setTab('login'); setErr('') }}
          className={`py-2 rounded-lg text-xs font-extrabold transition cursor-pointer ${
            tab === 'login'
              ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Sign In
        </button>
      </div>

      {err && (
        <div className="mb-3.5 p-2.5 rounded-xl bg-rose-500/15 border border-rose-500/35 text-rose-200 text-xs font-semibold text-center">
          {err}
        </div>
      )}

      {tab === 'register' ? (
        <form onSubmit={handleRegister} className="space-y-3">
          <input
            type="text"
            placeholder="Full Name"
            value={rf.name}
            onChange={e => setRf({ ...rf, name: e.target.value })}
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-white/[0.1] text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
          <input
            type="email"
            required
            placeholder="Work or Personal Email"
            value={rf.email}
            onChange={e => setRf({ ...rf, email: e.target.value })}
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-white/[0.1] text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
          <input
            type="password"
            required
            placeholder="Create Password (min. 6 chars)"
            value={rf.password}
            onChange={e => setRf({ ...rf, password: e.target.value })}
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-white/[0.1] text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={busy}
            className="shimmer-btn w-full py-3 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-extrabold text-xs shadow-lg shadow-blue-600/30 flex items-center justify-center gap-2 transition cursor-pointer disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
            <span>{busy ? 'Creating Account...' : 'Create Free Account & Unlock Results'}</span>
            <ArrowRight size={14} />
          </button>
        </form>
      ) : (
        <form onSubmit={handleLogin} className="space-y-3">
          <input
            type="email"
            required
            placeholder="Email Address"
            value={lf.email}
            onChange={e => setLf({ ...lf, email: e.target.value })}
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-white/[0.1] text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
          <input
            type="password"
            required
            placeholder="Password"
            value={lf.password}
            onChange={e => setLf({ ...lf, password: e.target.value })}
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-white/[0.1] text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={busy}
            className="shimmer-btn w-full py-3 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-extrabold text-xs shadow-lg shadow-blue-600/30 flex items-center justify-center gap-2 transition cursor-pointer disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
            <span>{busy ? 'Signing In...' : 'Sign In & Unlock Results'}</span>
          </button>
        </form>
      )}
    </motion.div>
  )
}

export function GuestBlurGate({ children, count = 0, itemLabel = 'Matching Jobs & Recruiter Emails' }) {
  const { isAuth } = useAuth()
  if (isAuth) return children

  return (
    <div className="relative min-h-[560px]">
      {/* Blurred Real Search Results Preview */}
      <div
        aria-hidden="true"
        className="filter blur-[7px] opacity-40 pointer-events-none select-none max-h-[680px] overflow-hidden rounded-3xl"
      >
        {children}
      </div>

      {/* Gradient Vignette + Floating Unlock Account Card */}
      <div className="guest-blur-overlay absolute inset-0 z-20 flex items-start sm:items-center justify-center pt-6 sm:pt-0 px-4 bg-gradient-to-b from-[#050811]/35 via-[#050811]/75 to-[#050811]/95 rounded-3xl">
        <AuthFormCard
          badgeText={count > 0 ? `🎉 Found ${count} ${itemLabel}` : 'Search Results Ready'}
          title={`Create a Free Account to Unlock All ${count > 0 ? count : ''} Search Results`}
          subtitle="Your live search results are ready behind this screen. Create a free account in 10 seconds to unlock all job details, verified recruiter emails, and 100% ATS CV tailoring."
        />
      </div>
    </div>
  )
}

export default function AuthGateModal({ isOpen, open, onClose, reason = '', title = '' }) {
  const visible = Boolean(isOpen || open)
  if (!visible) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md">
      <AuthFormCard
        badgeText="Free Account Required"
        title={reason || title || 'Create a Free Account to Continue'}
        subtitle="Unlock live search results, 100% ATS CV tailoring, direct recruiter email outreach, and automatic application tracking."
        onClose={onClose}
      />
    </div>
  )
}
