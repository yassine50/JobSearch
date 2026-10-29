import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import client from '../api/client.js'
import {
  ShieldCheck, Users, Briefcase, Mail, Database, Settings,
  RefreshCw, Trash2, Plus, Search, CheckCircle2, AlertTriangle,
  HardDrive, Sparkles, Send, Eye, EyeOff, Save, ExternalLink,
  Ban, Radar, Layers, Lock, Activity
} from 'lucide-react'

const TABS = [
  { id: 'overview',     label: 'Overview & Health', icon: Activity },
  { id: 'users',        label: 'Users & Roles',     icon: Users },
  { id: 'applications', label: 'Applications & Mail', icon: Briefcase },
  { id: 'index',        label: 'Scraper & Blacklist', icon: Radar },
  { id: 'config',       label: 'API Keys & Backups',  icon: Settings },
]

const STATUS_BADGE = {
  saved:     'bg-slate-500/15 text-slate-300 border-slate-500/30',
  applied:   'bg-blue-500/15 text-blue-300 border-blue-500/30',
  review:    'bg-amber-500/15 text-amber-300 border-amber-500/30',
  interview: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  offer:     'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  accepted:  'bg-emerald-500/20 text-emerald-200 border-emerald-400/40',
  rejected:  'bg-rose-500/15 text-rose-300 border-rose-500/30',
}

const ALLOWED_ADMIN_EMAILS = [
  'yassineyoussefwx@gmail.com',
  'yassine@test.com',
  'yassineyoussef@gmail.com',
  'yassine.demo@cvtomatch.com',
  'cvtomatch1@gmail.com',
]

export default function BackOffice() {
  const { user, login } = useAuth()
  const toast = useToast()

  const isUserAdmin = Boolean(
    user && (user.is_admin || user.role === 'admin' || ALLOWED_ADMIN_EMAILS.includes((user.email || '').toLowerCase()))
  )
  const [boUnlocked, setBoUnlocked] = useState(() => sessionStorage.getItem('bo_gate_unlocked') === '1' && isUserAdmin)
  const [gateEmail, setGateEmail] = useState(user?.email || 'yassineyoussefwx@gmail.com')
  const [gatePassword, setGatePassword] = useState('')
  const [gateLoading, setGateLoading] = useState(false)
  const [gateError, setGateError] = useState('')
  const [apiTarget, setApiTarget] = useState(() => localStorage.getItem('bo_react_target') || 'http://34.41.44.162')

  const [activeTab, setActiveTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState(null)

  // Users state
  const [users, setUsers] = useState([])
  const [userSearch, setUserSearch] = useState('')
  const [userRoleFilter, setUserRoleFilter] = useState('all')
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '', role: 'seeker' })
  const [resetPwdUser, setResetPwdUser] = useState(null)
  const [resetPwdVal, setResetPwdVal] = useState('')
  const [sendingDigestId, setSendingDigestId] = useState(null)

  // Applications & Emails state
  const [subViewApp, setSubViewApp] = useState('applications') // 'applications' | 'emails'
  const [apps, setApps] = useState([])
  const [appSearch, setAppSearch] = useState('')
  const [appStatus, setAppStatus] = useState('all')
  const [emails, setEmails] = useState([])
  const [emailSearch, setEmailSearch] = useState('')
  const [emailStatus, setEmailStatus] = useState('all')

  // Index & Blacklist state
  const [subViewIndex, setSubViewIndex] = useState('posts') // 'posts' | 'blacklist'
  const [posts, setPosts] = useState([])
  const [postSearch, setPostSearch] = useState('')
  const [blacklist, setBlacklist] = useState([])
  const [blSearch, setBlSearch] = useState('')
  const [newBlEmail, setNewBlEmail] = useState('')
  const [newBlReason, setNewBlReason] = useState('Blocked by Admin')

  // Config state
  const [cfg, setCfg] = useState({
    serper_api_key: '',
    scraper_proxy: '',
    adzuna_app_id: '',
    adzuna_app_key: '',
    jooble_api_key: '',
    careerjet_affid: '',
    google_client_id: '',
    google_client_secret: '',
  })
  const [showSecrets, setShowSecrets] = useState(false)
  const [savingCfg, setSavingCfg] = useState(false)
  const [runningMaint, setRunningMaint] = useState('')

  const getAdminApiPrefix = () => {
    if (!apiTarget || apiTarget === 'local') return '/api'
    return `${apiTarget.replace(/\/+$/, '')}/api`
  }

  const handleAdminGateLogin = async (e) => {
    e.preventDefault()
    setGateError('')
    setGateLoading(true)
    try {
      const targetBase = apiTarget === 'local' ? '' : apiTarget.replace(/\/+$/, '')
      const url = targetBase ? `${targetBase}/api/admin/login` : '/admin/login'
      const res = targetBase
        ? await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: gateEmail.trim(), password: gatePassword }),
          }).then(async r => {
            const d = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
            return d
          })
        : (await client.post('/admin/login', { email: gateEmail.trim(), password: gatePassword })).data

      const u = res.user || {}
      const emailLower = (u.email || gateEmail).trim().toLowerCase()
      if (!u.is_admin && u.role !== 'admin' && !ALLOWED_ADMIN_EMAILS.includes(emailLower)) {
        throw new Error(`Access denied: ${emailLower} is not an authorized administrator.`)
      }
      login(res.access_token, { ...u, is_admin: true })
      sessionStorage.setItem('bo_gate_unlocked', '1')
      setBoUnlocked(true)
      setGatePassword('')
      toast(`Back Office unlocked as ${u.email}`, 'success')
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Invalid admin credentials'
      setGateError(msg)
      toast(msg, 'error')
    } finally {
      setGateLoading(false)
    }
  }

  const handleLockBackOffice = () => {
    sessionStorage.removeItem('bo_gate_unlocked')
    setBoUnlocked(false)
    toast('Back Office locked', 'info')
  }

  const loadOverview = async (force = false) => {
    setLoading(true)
    try {
      const { data } = await client.get('/admin/overview', { forceRefresh: force })
      setOverview(data)
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load Back Office overview', 'error')
    } finally {
      setLoading(false)
    }
  }

  const loadUsers = async () => {
    try {
      const { data } = await client.get('/admin/users', {
        params: { search: userSearch, role: userRoleFilter },
        forceRefresh: true,
      })
      setUsers(data.users || [])
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load users', 'error')
    }
  }

  const loadApps = async () => {
    try {
      const { data } = await client.get('/admin/applications', {
        params: { search: appSearch, status: appStatus, limit: 150 },
        forceRefresh: true,
      })
      setApps(data.applications || [])
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load applications', 'error')
    }
  }

  const loadEmails = async () => {
    try {
      const { data } = await client.get('/admin/emails', {
        params: { search: emailSearch, status: emailStatus, limit: 150 },
        forceRefresh: true,
      })
      setEmails(data.emails || [])
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load email logs', 'error')
    }
  }

  const loadPosts = async () => {
    try {
      const { data } = await client.get('/admin/recruiter-posts', {
        params: { search: postSearch, limit: 120 },
        forceRefresh: true,
      })
      setPosts(data.posts || [])
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load recruiter posts', 'error')
    }
  }

  const loadBlacklist = async () => {
    try {
      const { data } = await client.get('/admin/blacklist', {
        params: { search: blSearch, limit: 200 },
        forceRefresh: true,
      })
      setBlacklist(data.blacklist || [])
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load blacklist', 'error')
    }
  }

  const loadConfig = async () => {
    try {
      const { data } = await client.get('/admin/config', { forceRefresh: true })
      setCfg(prev => ({ ...prev, ...data }))
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load config', 'error')
    }
  }

  useEffect(() => {
    if (boUnlocked) loadOverview(true)
  }, [boUnlocked])

  useEffect(() => {
    if (!boUnlocked) return
    if (activeTab === 'users') loadUsers()
    if (activeTab === 'applications') {
      if (subViewApp === 'applications') loadApps()
      else loadEmails()
    }
    if (activeTab === 'index') {
      if (subViewIndex === 'posts') loadPosts()
      else loadBlacklist()
    }
    if (activeTab === 'config') loadConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, subViewApp, subViewIndex])

  // ─── Actions ───────────────────────────────────────────────────────────────

  const handleMaintenance = async (action) => {
    setRunningMaint(action)
    try {
      const { data } = await client.post(`/admin/maintenance/${action}`)
      toast(data.message || 'Maintenance complete', 'success')
      loadOverview(true)
    } catch (e) {
      toast(e.response?.data?.detail || 'Maintenance action failed', 'error')
    } finally {
      setRunningMaint('')
    }
  }

  const handleCreateUser = async () => {
    if (!newUser.name.trim() || !newUser.email.trim() || !newUser.password.trim()) {
      return toast('Name, email, and password are required', 'error')
    }
    try {
      const { data } = await client.post('/admin/users', newUser)
      toast(data.message || 'User created', 'success')
      setNewUser({ name: '', email: '', password: '', role: 'seeker' })
      setShowCreateUser(false)
      loadUsers()
      loadOverview(true)
    } catch (e) {
      toast(e.response?.data?.detail || 'Could not create user', 'error')
    }
  }

  const handleUpdateUser = async (uid, patch) => {
    try {
      const { data } = await client.patch(`/admin/users/${uid}`, patch)
      toast(data.message || 'User updated', 'success')
      loadUsers()
    } catch (e) {
      toast(e.response?.data?.detail || 'Update failed', 'error')
    }
  }

  const handleDeleteUser = async (u) => {
    if (!window.confirm(`Delete user "${u.name}" (${u.email}) and all their applications & logs?`)) return
    try {
      const { data } = await client.delete(`/admin/users/${u.id}`)
      toast(data.message || 'User deleted', 'info')
      loadUsers()
      loadOverview(true)
    } catch (e) {
      toast(e.response?.data?.detail || 'Delete failed', 'error')
    }
  }

  const handleTriggerDigest = async (u) => {
    setSendingDigestId(u.id)
    try {
      const { data } = await client.post(`/admin/users/${u.id}/send-digest`)
      if (data.sent === false) {
        toast(`Digest NOT delivered: ${data.error || 'Email provider error'}`, 'error')
      } else {
        toast(data.message || `Digest delivered to ${u.email} (${data.matches_count || 0} matches)`, 'success')
      }
      loadUsers()
    } catch (e) {
      toast(e.response?.data?.detail || 'Digest failed', 'error')
    } finally {
      setSendingDigestId(null)
    }
  }

  const handleAppStatusChange = async (appId, newStatus) => {
    try {
      await client.patch(`/admin/applications/${appId}`, { status: newStatus })
      setApps(prev => prev.map(a => a.id === appId ? { ...a, status: newStatus } : a))
      toast(`Updated application #${appId} to ${newStatus}`, 'success')
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to update status', 'error')
    }
  }

  const handleDeleteApp = async (appId) => {
    try {
      await client.delete(`/admin/applications/${appId}`)
      setApps(prev => prev.filter(a => a.id !== appId))
      toast(`Application #${appId} removed`, 'info')
    } catch (e) {
      toast(e.response?.data?.detail || 'Could not delete application', 'error')
    }
  }

  const handleDeleteEmailLog = async (logId) => {
    try {
      await client.delete(`/admin/emails/${logId}`)
      setEmails(prev => prev.filter(l => l.id !== logId))
      toast(`Email log #${logId} deleted`, 'info')
    } catch (e) {
      toast(e.response?.data?.detail || 'Delete failed', 'error')
    }
  }

  const handleDeletePost = async (postId) => {
    try {
      await client.delete(`/admin/recruiter-posts/${postId}`)
      setPosts(prev => prev.filter(p => p.id !== postId))
      toast('Recruiter post removed from index', 'info')
    } catch (e) {
      toast(e.response?.data?.detail || 'Delete failed', 'error')
    }
  }

  const handleAddBlacklist = async () => {
    if (!newBlEmail.trim() || !newBlEmail.includes('@')) {
      return toast('Enter a valid email address', 'error')
    }
    try {
      const { data } = await client.post('/admin/blacklist', {
        email: newBlEmail.trim(),
        reason: newBlReason.trim() || 'Blocked by Admin',
      })
      toast(data.message || 'Added to blacklist', 'success')
      setNewBlEmail('')
      loadBlacklist()
      loadOverview(true)
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to block email', 'error')
    }
  }

  const handleRemoveBlacklist = async (id) => {
    try {
      const { data } = await client.delete(`/admin/blacklist/${id}`)
      setBlacklist(prev => prev.filter(b => b.id !== id))
      toast(data.message || 'Unblocked email', 'info')
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to unblock', 'error')
    }
  }

  const handleSaveConfig = async () => {
    setSavingCfg(true)
    try {
      const { data } = await client.post('/admin/config', {
        serper_api_key: cfg.serper_api_key,
        scraper_proxy: cfg.scraper_proxy,
        adzuna_app_id: cfg.adzuna_app_id,
        adzuna_app_key: cfg.adzuna_app_key,
        jooble_api_key: cfg.jooble_api_key,
        careerjet_affid: cfg.careerjet_affid,
        google_client_id: cfg.google_client_id,
        google_client_secret: cfg.google_client_secret,
      })
      toast(data.message || 'Configuration saved!', 'success')
      loadOverview(true)
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to save config', 'error')
    } finally {
      setSavingCfg(false)
    }
  }

  const uStats = overview?.users || {}
  const aStats = overview?.applications || {}
  const eStats = overview?.emails || {}
  const iStats = overview?.index || {}
  const sStats = overview?.system || {}

  if (!boUnlocked) {
    return (
      <PageWrapper>
        <div className="flex min-h-screen bg-[#050811] text-white">
          <Sidebar />
          <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 pt-20 md:pt-12 pb-16 flex items-center justify-center">
            <div className="glass-panel rounded-3xl p-7 sm:p-8 w-full max-w-md border border-white/[0.12] shadow-2xl relative overflow-hidden">
              <div className="glow-line-top" />
              <div className="flex items-center gap-3.5 mb-5">
                <div className="w-12 h-12 rounded-2xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
                  <Lock size={20} />
                </div>
                <div>
                  <span className="text-[10px] font-extrabold uppercase tracking-widest text-rose-400">Protected Console</span>
                  <h1 className="text-lg font-black text-white leading-tight">Back Office Admin Login</h1>
                  <p className="text-xs text-slate-400">Authenticate to access platform controls</p>
                </div>
              </div>

              <div className="mb-4 p-3 rounded-2xl bg-slate-950/70 border border-white/[0.08]">
                <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-400 mb-2">
                  Target Environment
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => { setApiTarget('http://34.41.44.162'); localStorage.setItem('bo_react_target', 'http://34.41.44.162') }}
                    className={`py-2 px-3 rounded-xl text-xs font-extrabold border transition cursor-pointer ${
                      apiTarget === 'http://34.41.44.162'
                        ? 'bg-blue-600/25 border-blue-500/50 text-white'
                        : 'bg-white/[0.04] border-white/[0.08] text-slate-400 hover:text-white'
                    }`}
                  >
                    🌐 VPS (34.41.44.162)
                  </button>
                  <button
                    type="button"
                    onClick={() => { setApiTarget('local'); localStorage.setItem('bo_react_target', 'local') }}
                    className={`py-2 px-3 rounded-xl text-xs font-extrabold border transition cursor-pointer ${
                      apiTarget === 'local'
                        ? 'bg-blue-600/25 border-blue-500/50 text-white'
                        : 'bg-white/[0.04] border-white/[0.08] text-slate-400 hover:text-white'
                    }`}
                  >
                    💻 Local Server
                  </button>
                </div>
              </div>

              <form onSubmit={handleAdminGateLogin} className="space-y-4">
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-300 mb-1.5">
                    Admin Email
                  </label>
                  <input
                    type="email"
                    required
                    value={gateEmail}
                    onChange={e => setGateEmail(e.target.value)}
                    placeholder="yassineyoussefwx@gmail.com"
                    className="glass-input w-full rounded-xl px-3.5 py-2.5 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-300 mb-1.5">
                    Admin Password
                  </label>
                  <input
                    type="password"
                    required
                    value={gatePassword}
                    onChange={e => setGatePassword(e.target.value)}
                    placeholder="Enter your admin password"
                    className="glass-input w-full rounded-xl px-3.5 py-2.5 text-xs text-white"
                  />
                </div>

                {gateError && (
                  <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-xs text-rose-200 font-medium">
                    {gateError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={gateLoading}
                  className="shimmer-btn w-full py-3 px-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-xs font-extrabold text-white shadow-lg shadow-blue-600/25 transition cursor-pointer"
                >
                  {gateLoading ? 'Verifying Credentials…' : '🔓 Authenticate & Unlock Back Office'}
                </button>
              </form>
            </div>
          </main>
        </div>
      </PageWrapper>
    )
  }

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-16 w-full">

          {/* Back Office Executive Header */}
          <div className="glass-panel rounded-3xl p-6 mb-6 relative overflow-hidden flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="glow-line-top" />
            <div>
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300 text-[11px] font-bold mb-1.5">
                <ShieldCheck size={12} className="text-emerald-400" />
                <span>Admin Control Center · CVtoMatch v2.0</span>
              </div>
              <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white">
                Platform <span className="text-gradient-blue">Back Office</span>
              </h1>
              <p className="text-xs text-slate-400 mt-1">
                Signed in as <strong className="text-slate-200">{user?.email}</strong> · Manage users, applications, recruiter index, bounce protection &amp; API keys.
              </p>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap">
              <button
                onClick={handleLockBackOffice}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 text-xs font-bold text-rose-300 transition cursor-pointer"
              >
                <Lock size={14} />
                <span>Lock Session</span>
              </button>
              <button
                onClick={() => loadOverview(true)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.1] text-xs font-bold text-slate-200 transition cursor-pointer"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin text-blue-400' : 'text-blue-400'} />
                <span>Refresh Data</span>
              </button>
              <button
                onClick={() => handleMaintenance('backup-db')}
                disabled={runningMaint === 'backup-db'}
                className="shimmer-btn flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-xs font-extrabold text-white shadow-lg shadow-blue-600/20 transition cursor-pointer"
              >
                <HardDrive size={14} />
                <span>{runningMaint === 'backup-db' ? 'Backing up…' : 'Backup SQLite DB'}</span>
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-6">
            {TABS.map(t => {
              const Icon = t.icon
              const active = activeTab === t.id
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-extrabold whitespace-nowrap transition cursor-pointer border ${
                    active
                      ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white border-blue-400/40 shadow-lg shadow-blue-600/20'
                      : 'bg-white/[0.03] hover:bg-white/[0.07] text-slate-400 hover:text-white border-white/[0.07]'
                  }`}
                >
                  <Icon size={14} />
                  <span>{t.label}</span>
                </button>
              )
            })}
          </div>

          {/* ───────────────────────────────────────────────────────────────────
              TAB 1: OVERVIEW & SYSTEM HEALTH
             ─────────────────────────────────────────────────────────────────── */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Top 4 KPI Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div
                  onClick={() => setActiveTab('users')}
                  className="glass-card rounded-2xl p-5 cursor-pointer hover:border-blue-500/40 transition"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400">
                      <Users size={18} />
                    </div>
                    <span className="text-[11px] font-bold text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                      {uStats.with_cv || 0} with CV
                    </span>
                  </div>
                  <div className="text-3xl font-black text-white">{uStats.total || 0}</div>
                  <div className="text-xs font-bold text-slate-300 mt-1">Registered Users</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    {uStats.with_smtp || 0} SMTP connected · {uStats.digest_enabled || 0} Daily Digest
                  </div>
                </div>

                <div
                  onClick={() => { setActiveTab('applications'); setSubViewApp('applications') }}
                  className="glass-card rounded-2xl p-5 cursor-pointer hover:border-blue-500/40 transition"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                      <Briefcase size={18} />
                    </div>
                    <span className="text-[11px] font-bold text-blue-300 bg-blue-500/15 border border-blue-500/30 px-2 py-0.5 rounded-full">
                      Avg {aStats.avg_match_score || 0}% Fit
                    </span>
                  </div>
                  <div className="text-3xl font-black text-white">{aStats.total || 0}</div>
                  <div className="text-xs font-bold text-slate-300 mt-1">Tracked Applications</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    {aStats.by_status?.interview || 0} interviews · {aStats.by_status?.review || 0} in review
                  </div>
                </div>

                <div
                  onClick={() => { setActiveTab('applications'); setSubViewApp('emails') }}
                  className="glass-card rounded-2xl p-5 cursor-pointer hover:border-blue-500/40 transition"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-500/15 border border-purple-500/30 flex items-center justify-center text-purple-400">
                      <Mail size={18} />
                    </div>
                    <span className="text-[11px] font-bold text-purple-300 bg-purple-500/15 border border-purple-500/30 px-2 py-0.5 rounded-full">
                      {eStats.recruiter_replies || 0} Replies
                    </span>
                  </div>
                  <div className="text-3xl font-black text-white">{eStats.sent || 0}</div>
                  <div className="text-xs font-bold text-slate-300 mt-1">Delivered Outreach Emails</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    {eStats.follow_ups || 0} follow-ups · {eStats.bounced || 0} historical bounces
                  </div>
                </div>

                <div
                  onClick={() => setActiveTab('index')}
                  className="glass-card rounded-2xl p-5 cursor-pointer hover:border-blue-500/40 transition"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                      <Database size={18} />
                    </div>
                    <span className="text-[11px] font-bold text-amber-300 bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded-full">
                      {sStats.db_size_mb || 0} MB DB
                    </span>
                  </div>
                  <div className="text-3xl font-black text-white">{iStats.verified_recruiter_posts || 0}</div>
                  <div className="text-xs font-bold text-slate-300 mt-1">Indexed Recruiter Posts</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    {iStats.job_sightings || 0} job sightings · {iStats.blacklisted_emails || 0} blacklisted
                  </div>
                </div>
              </div>

              {/* Pipeline Status Breakdown + 1-Click Maintenance */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Application Pipeline Distribution */}
                <div className="glass-panel rounded-2xl p-6">
                  <h2 className="text-sm font-extrabold text-white mb-1">Global Application Pipeline</h2>
                  <p className="text-xs text-slate-400 mb-4">Distribution across all {aStats.total || 0} tracked candidate applications</p>
                  <div className="space-y-3">
                    {[
                      { key: 'applied',   label: 'Applied / Sent', color: 'bg-blue-500' },
                      { key: 'review',    label: 'Under Review',   color: 'bg-amber-500' },
                      { key: 'interview', label: 'Interview',      color: 'bg-purple-500' },
                      { key: 'offer',     label: 'Offer / Accepted', color: 'bg-emerald-500' },
                      { key: 'saved',     label: 'Saved Queue',    color: 'bg-slate-500' },
                      { key: 'rejected',  label: 'Rejected / Closed', color: 'bg-rose-500' },
                    ].map(row => {
                      const cnt = row.key === 'offer'
                        ? (aStats.by_status?.offer || 0) + (aStats.by_status?.accepted || 0)
                        : (aStats.by_status?.[row.key] || 0)
                      const pct = aStats.total ? Math.round((cnt / aStats.total) * 100) : 0
                      return (
                        <div key={row.key} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="font-bold text-slate-300">{row.label}</span>
                            <span className="text-slate-400 font-semibold">{cnt} ({pct}%)</span>
                          </div>
                          <div className="w-full h-2 rounded-full bg-slate-900 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${row.color}`}
                              style={{ width: `${Math.max(cnt > 0 ? 4 : 0, pct)}%` }}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* 1-Click Maintenance & Operations */}
                <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
                  <div>
                    <h2 className="text-sm font-extrabold text-white mb-1">1-Click System Maintenance</h2>
                    <p className="text-xs text-slate-400 mb-4">
                      Database health: <code className="text-blue-300">{sStats.db_size_mb || 0} MB</code> ·{' '}
                      Backups: <code className="text-emerald-300">{sStats.backups_count || 0}</code> ·{' '}
                      Serper Key: <code className={sStats.has_serper ? 'text-emerald-300' : 'text-rose-300'}>{sStats.has_serper ? 'Active' : 'Missing'}</code>
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      <button
                        onClick={() => handleMaintenance('clear-cache')}
                        disabled={Boolean(runningMaint)}
                        className="flex items-center justify-between p-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-left transition cursor-pointer"
                      >
                        <div>
                          <div className="text-xs font-extrabold text-white">Clear Search Caches</div>
                          <div className="text-[11px] text-slate-400">Reset job &amp; feed TTL memory</div>
                        </div>
                        <RefreshCw size={15} className="text-blue-400 shrink-0" />
                      </button>

                      <button
                        onClick={() => handleMaintenance('purge-blacklisted')}
                        disabled={Boolean(runningMaint)}
                        className="flex items-center justify-between p-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-left transition cursor-pointer"
                      >
                        <div>
                          <div className="text-xs font-extrabold text-white">Purge Blacklisted Apps</div>
                          <div className="text-[11px] text-slate-400">Clean bounced apps from Tracker</div>
                        </div>
                        <Ban size={15} className="text-amber-400 shrink-0" />
                      </button>

                      <button
                        onClick={() => handleMaintenance('auto-reject-stale')}
                        disabled={Boolean(runningMaint)}
                        className="flex items-center justify-between p-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-left transition cursor-pointer"
                      >
                        <div>
                          <div className="text-xs font-extrabold text-white">Auto-Close Stale (3d+)</div>
                          <div className="text-[11px] text-slate-400">Reject unanswered follow-ups</div>
                        </div>
                        <CheckCircle2 size={15} className="text-purple-400 shrink-0" />
                      </button>

                      <button
                        onClick={() => handleMaintenance('purge-bounced-logs')}
                        disabled={Boolean(runningMaint)}
                        className="flex items-center justify-between p-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-left transition cursor-pointer"
                      >
                        <div>
                          <div className="text-xs font-extrabold text-white">Clean Bounced Logs</div>
                          <div className="text-[11px] text-slate-400">Remove {eStats.bounced || 0} bounced log rows</div>
                        </div>
                        <Trash2 size={15} className="text-rose-400 shrink-0" />
                      </button>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-white/[0.07] flex items-center justify-between text-xs text-slate-400">
                    <span>Demo/test accounts (@example.com, @test.com)</span>
                    <button
                      onClick={() => handleMaintenance('purge-test-users')}
                      disabled={Boolean(runningMaint)}
                      className="text-rose-400 hover:text-rose-300 font-bold underline cursor-pointer"
                    >
                      Purge Demo Users
                    </button>
                  </div>
                </div>
              </div>

              {/* Recent Activity Stream */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <div className="glass-panel rounded-2xl p-6">
                  <h3 className="text-sm font-extrabold text-white mb-3">Latest Tracked Applications</h3>
                  <div className="space-y-2">
                    {(overview?.recent_activity?.applications || []).map(a => (
                      <div key={a.id} className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] text-xs">
                        <div className="min-w-0">
                          <div className="font-bold text-white truncate">{a.title} · <span className="text-blue-400">{a.company}</span></div>
                          <div className="text-[11px] text-slate-400 truncate">User: {a.user_email} · {a.applied_at?.slice(0, 16)}</div>
                        </div>
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase border shrink-0 ${STATUS_BADGE[a.status] || STATUS_BADGE.applied}`}>
                          {a.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="glass-panel rounded-2xl p-6">
                  <h3 className="text-sm font-extrabold text-white mb-3">Latest Outreach &amp; Replies</h3>
                  <div className="space-y-2">
                    {(overview?.recent_activity?.emails || []).map(l => (
                      <div key={l.id} className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] text-xs">
                        <div className="min-w-0">
                          <div className="font-bold text-white truncate">{l.subject}</div>
                          <div className="text-[11px] text-slate-400 truncate">To: {l.to_email} · From: {l.user_email}</div>
                        </div>
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase shrink-0 ${
                          l.status === 'sent' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'
                        }`}>
                          {l.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────────────
              TAB 2: USERS & ROLES MANAGEMENT
             ─────────────────────────────────────────────────────────────────── */}
          {activeTab === 'users' && (
            <div className="glass-panel rounded-3xl p-6 space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2 flex-1">
                  <div className="relative flex-1 max-w-md">
                    <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      value={userSearch}
                      onChange={e => setUserSearch(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && loadUsers()}
                      placeholder="Search users by name or email..."
                      className="w-full glass-input rounded-xl pl-9 pr-3.5 py-2 text-xs"
                    />
                  </div>
                  <select
                    value={userRoleFilter}
                    onChange={e => { setUserRoleFilter(e.target.value); setTimeout(loadUsers, 20) }}
                    className="glass-input rounded-xl px-3 py-2 text-xs bg-[#0b1120]"
                  >
                    <option value="all">All Roles</option>
                    <option value="seeker">Seeker</option>
                    <option value="recruiter">Recruiter</option>
                    <option value="both">Both</option>
                    <option value="admin">Admin</option>
                  </select>
                  <button
                    onClick={loadUsers}
                    className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.1] text-xs font-bold cursor-pointer"
                  >
                    Filter
                  </button>
                </div>

                <button
                  onClick={() => setShowCreateUser(v => !v)}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-extrabold cursor-pointer"
                >
                  <Plus size={14} />
                  <span>Create User</span>
                </button>
              </div>

              {/* Create User Drawer */}
              <AnimatePresence>
                {showCreateUser && (
                  <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="p-4 rounded-2xl bg-slate-950/80 border border-blue-500/30 grid grid-cols-1 sm:grid-cols-5 gap-3"
                  >
                    <input
                      value={newUser.name}
                      onChange={e => setNewUser(u => ({ ...u, name: e.target.value }))}
                      placeholder="Full Name"
                      className="glass-input rounded-xl px-3 py-2 text-xs"
                    />
                    <input
                      value={newUser.email}
                      onChange={e => setNewUser(u => ({ ...u, email: e.target.value }))}
                      placeholder="Email Address"
                      className="glass-input rounded-xl px-3 py-2 text-xs"
                    />
                    <input
                      type="password"
                      value={newUser.password}
                      onChange={e => setNewUser(u => ({ ...u, password: e.target.value }))}
                      placeholder="Password (min 6 chars)"
                      className="glass-input rounded-xl px-3 py-2 text-xs"
                    />
                    <select
                      value={newUser.role}
                      onChange={e => setNewUser(u => ({ ...u, role: e.target.value }))}
                      className="glass-input rounded-xl px-3 py-2 text-xs bg-[#0b1120]"
                    >
                      <option value="seeker">Seeker</option>
                      <option value="recruiter">Recruiter</option>
                      <option value="both">Both</option>
                      <option value="admin">Admin</option>
                    </select>
                    <button
                      onClick={handleCreateUser}
                      className="rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-extrabold text-xs px-4 py-2 cursor-pointer"
                    >
                      Save Account
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Password Reset Modal */}
              {resetPwdUser && (
                <div className="p-4 rounded-2xl bg-slate-950/90 border border-amber-500/40 flex items-center justify-between gap-3 flex-wrap">
                  <div className="text-xs">
                    <span className="font-bold text-amber-300">Reset Password for {resetPwdUser.email}:</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="password"
                      value={resetPwdVal}
                      onChange={e => setResetPwdVal(e.target.value)}
                      placeholder="New password (6+ chars)"
                      className="glass-input rounded-xl px-3 py-1.5 text-xs"
                    />
                    <button
                      onClick={() => {
                        handleUpdateUser(resetPwdUser.id, { password: resetPwdVal })
                        setResetPwdUser(null)
                        setResetPwdVal('')
                      }}
                      className="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold cursor-pointer"
                    >
                      Update Password
                    </button>
                    <button
                      onClick={() => { setResetPwdUser(null); setResetPwdVal('') }}
                      className="px-3 py-1.5 rounded-xl bg-white/10 text-xs font-bold cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Users Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="text-slate-400 border-b border-white/[0.08] uppercase text-[10px] tracking-wider">
                      <th className="py-3 pr-3">ID / User</th>
                      <th className="py-3 pr-3">Role</th>
                      <th className="py-3 pr-3">Resume (CV)</th>
                      <th className="py-3 pr-3">Outreach Setup</th>
                      <th className="py-3 pr-3">Activity</th>
                      <th className="py-3 pr-3">Daily Digest</th>
                      <th className="py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.05]">
                    {users.map(u => (
                      <tr key={u.id} className="hover:bg-white/[0.02] transition">
                        <td className="py-3.5 pr-3">
                          <div className="font-extrabold text-white flex items-center gap-1.5">
                            <span>#{u.id} {u.name}</span>
                            {u.is_admin && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-black">
                                ADMIN
                              </span>
                            )}
                          </div>
                          <div className="text-slate-400 font-mono text-[11px]">{u.email}</div>
                          <div className="text-[10px] text-slate-500">Joined {u.created_at?.slice(0, 10)}</div>
                        </td>

                        <td className="py-3.5 pr-3">
                          <select
                            value={u.role}
                            onChange={e => handleUpdateUser(u.id, { role: e.target.value })}
                            className="glass-input rounded-lg px-2.5 py-1 text-xs bg-[#0b1120] font-bold"
                          >
                            <option value="seeker">seeker</option>
                            <option value="recruiter">recruiter</option>
                            <option value="both">both</option>
                            <option value="admin">admin</option>
                          </select>
                        </td>

                        <td className="py-3.5 pr-3">
                          {u.active_cv_filename ? (
                            <div className="space-y-1">
                                <button
                                  type="button"
                                  onClick={() => {
                                    const tok = localStorage.getItem('token') || ''
                                    window.open(`${getAdminApiPrefix()}/admin/users/${u.id}/cv/download?token=${encodeURIComponent(tok)}`, '_blank')
                                  }}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/30 border border-emerald-500/35 text-emerald-300 font-bold text-[11px] truncate max-w-[200px] cursor-pointer transition"
                                  title={`Download ${u.active_cv_filename}`}
                                >
                                  <span>📥 {u.active_cv_filename}</span>
                                </button>
                              <span className="text-[10px] text-slate-400 block">
                                {u.active_cv_words} words · {u.cv_count} persona(s)
                              </span>
                            </div>
                          ) : (
                            <span className="text-slate-500">No CV uploaded</span>
                          )}
                        </td>

                        <td className="py-3.5 pr-3">
                          {u.smtp_configured ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold">
                              ✓ {u.smtp_user || 'OAuth Connected'}
                            </span>
                          ) : (
                            <span className="text-slate-500 text-[11px]">Not configured</span>
                          )}
                        </td>

                        <td className="py-3.5 pr-3">
                          <div className="font-bold text-slate-200">{u.applications_count} apps</div>
                          <div className="text-[11px] text-slate-400">{u.emails_sent_count} emails sent</div>
                        </td>

                        <td className="py-3.5 pr-3">
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={u.daily_digest_enabled}
                              onChange={e => handleUpdateUser(u.id, { daily_digest_enabled: e.target.checked })}
                              className="accent-blue-500 cursor-pointer"
                            />
                            <button
                              onClick={() => handleTriggerDigest(u)}
                              disabled={sendingDigestId === u.id}
                              className="px-2.5 py-1 rounded-lg bg-blue-500/15 hover:bg-blue-500/25 border border-blue-500/30 text-blue-300 text-[10px] font-bold cursor-pointer flex items-center gap-1"
                              title="Send Daily Top 5 Digest email now"
                            >
                              <Send size={10} />
                              <span>{sendingDigestId === u.id ? 'Sending…' : 'Send Now'}</span>
                            </button>
                          </div>
                        </td>

                        <td className="py-3.5 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => setResetPwdUser(u)}
                              className="p-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.12] text-slate-300 hover:text-amber-300 transition cursor-pointer"
                              title="Reset User Password"
                            >
                              <Lock size={13} />
                            </button>
                            <button
                              onClick={() => handleDeleteUser(u)}
                              className="p-1.5 rounded-lg bg-white/[0.05] hover:bg-rose-500/15 text-slate-400 hover:text-rose-400 transition cursor-pointer"
                              title="Delete User"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────────────
              TAB 3: APPLICATIONS & OUTREACH LOGS
             ─────────────────────────────────────────────────────────────────── */}
          {activeTab === 'applications' && (
            <div className="glass-panel rounded-3xl p-6 space-y-5">
              <div className="flex items-center justify-between gap-3 flex-wrap border-b border-white/[0.08] pb-4">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSubViewApp('applications')}
                    className={`px-4 py-2 rounded-xl text-xs font-extrabold cursor-pointer transition ${
                      subViewApp === 'applications'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white/[0.04] text-slate-400 hover:text-white'
                    }`}
                  >
                    All Applications ({aStats.total || apps.length})
                  </button>
                  <button
                    onClick={() => setSubViewApp('emails')}
                    className={`px-4 py-2 rounded-xl text-xs font-extrabold cursor-pointer transition ${
                      subViewApp === 'emails'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white/[0.04] text-slate-400 hover:text-white'
                    }`}
                  >
                    Outreach Email Logs ({eStats.total || emails.length})
                  </button>
                </div>

                {subViewApp === 'applications' ? (
                  <div className="flex items-center gap-2">
                    <input
                      value={appSearch}
                      onChange={e => setAppSearch(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && loadApps()}
                      placeholder="Search company, role, user..."
                      className="glass-input rounded-xl px-3.5 py-2 text-xs w-56"
                    />
                    <select
                      value={appStatus}
                      onChange={e => { setAppStatus(e.target.value); setTimeout(loadApps, 20) }}
                      className="glass-input rounded-xl px-3 py-2 text-xs bg-[#0b1120]"
                    >
                      <option value="all">All Stages</option>
                      <option value="saved">Saved</option>
                      <option value="applied">Applied</option>
                      <option value="review">Under Review</option>
                      <option value="interview">Interview</option>
                      <option value="offer">Offer</option>
                      <option value="rejected">Rejected</option>
                    </select>
                    <button
                      onClick={loadApps}
                      className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-xs font-bold cursor-pointer"
                    >
                      Search
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <input
                      value={emailSearch}
                      onChange={e => setEmailSearch(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && loadEmails()}
                      placeholder="Search recipient, subject, user..."
                      className="glass-input rounded-xl px-3.5 py-2 text-xs w-56"
                    />
                    <select
                      value={emailStatus}
                      onChange={e => { setEmailStatus(e.target.value); setTimeout(loadEmails, 20) }}
                      className="glass-input rounded-xl px-3 py-2 text-xs bg-[#0b1120]"
                    >
                      <option value="all">All Statuses</option>
                      <option value="sent">Sent</option>
                      <option value="bounced">Bounced</option>
                      <option value="review">Review Reply</option>
                      <option value="interview">Interview Reply</option>
                      <option value="rejected">Rejected Reply</option>
                    </select>
                    <button
                      onClick={loadEmails}
                      className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-xs font-bold cursor-pointer"
                    >
                      Search
                    </button>
                  </div>
                )}
              </div>

              {subViewApp === 'applications' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-slate-400 border-b border-white/[0.08] uppercase text-[10px]">
                        <th className="py-3 pr-3">ID / Candidate</th>
                        <th className="py-3 pr-3">Role &amp; Company</th>
                        <th className="py-3 pr-3">Fit</th>
                        <th className="py-3 pr-3">Stage</th>
                        <th className="py-3 pr-3">Applied Date</th>
                        <th className="py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05]">
                      {apps.map(a => (
                        <tr key={a.id} className="hover:bg-white/[0.02]">
                          <td className="py-3 pr-3">
                            <div className="font-bold text-slate-200">#{a.id} · {a.user_name}</div>
                            <div className="text-[11px] text-slate-400 font-mono">{a.user_email}</div>
                          </td>
                          <td className="py-3 pr-3 max-w-xs">
                            <div className="font-extrabold text-white truncate">{a.title}</div>
                            <div className="text-blue-400 font-semibold truncate">{a.company} · <span className="text-slate-400">{a.location}</span></div>
                          </td>
                          <td className="py-3 pr-3 font-extrabold text-emerald-400">{a.match_score || 0}%</td>
                          <td className="py-3 pr-3">
                            <select
                              value={a.status}
                              onChange={e => handleAppStatusChange(a.id, e.target.value)}
                              className="glass-input rounded-lg px-2.5 py-1 text-xs bg-[#0b1120] font-bold"
                            >
                              <option value="saved">saved</option>
                              <option value="applied">applied</option>
                              <option value="review">review</option>
                              <option value="interview">interview</option>
                              <option value="offer">offer</option>
                              <option value="accepted">accepted</option>
                              <option value="rejected">rejected</option>
                            </select>
                          </td>
                          <td className="py-3 pr-3 text-slate-400">{a.applied_at?.slice(0, 16)}</td>
                          <td className="py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  const tok = localStorage.getItem('token') || ''
                                  window.open(`${getAdminApiPrefix()}/admin/applications/${a.id}/cv?token=${encodeURIComponent(tok)}`, '_blank')
                                }}
                                className="px-2 py-0.5 rounded bg-emerald-500/15 hover:bg-emerald-500/30 border border-emerald-500/35 text-emerald-300 text-[10px] font-bold cursor-pointer"
                                title="Download candidate CV for this application"
                              >
                                📥 CV
                              </button>
                              {a.url && (
                                <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300">
                                  <ExternalLink size={13} />
                                </a>
                              )}
                              <button
                                onClick={() => handleDeleteApp(a.id)}
                                className="text-slate-400 hover:text-rose-400 cursor-pointer"
                                title="Delete application"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-slate-400 border-b border-white/[0.08] uppercase text-[10px]">
                        <th className="py-3 pr-3">ID / Sender</th>
                        <th className="py-3 pr-3">Recipient</th>
                        <th className="py-3 pr-3">Subject &amp; Type</th>
                        <th className="py-3 pr-3">Status</th>
                        <th className="py-3 pr-3">Timestamp</th>
                        <th className="py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05]">
                      {emails.map(l => (
                        <tr key={l.id} className="hover:bg-white/[0.02]">
                          <td className="py-3 pr-3">
                            <div className="font-bold text-slate-200">#{l.id}</div>
                            <div className="text-[11px] text-slate-400 font-mono">{l.user_email}</div>
                          </td>
                          <td className="py-3 pr-3">
                            <div className="font-mono font-bold text-blue-300">{l.to_email}</div>
                            <div className="text-[11px] text-slate-400">{l.to_name}</div>
                          </td>
                          <td className="py-3 pr-3 max-w-sm">
                            <div className="font-bold text-white truncate">{l.subject}</div>
                            <div className="text-[11px] text-slate-400 truncate">{l.template_type} · {l.body_preview}</div>
                          </td>
                          <td className="py-3 pr-3">
                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase ${
                              l.status === 'sent'
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : l.status === 'bounced'
                                ? 'bg-rose-500/15 text-rose-300'
                                : 'bg-purple-500/15 text-purple-300'
                            }`}>
                              {l.status}
                            </span>
                          </td>
                          <td className="py-3 pr-3 text-slate-400">{l.sent_at?.slice(0, 16)}</td>
                          <td className="py-3 text-right">
                            <button
                              onClick={() => handleDeleteEmailLog(l.id)}
                              className="text-slate-400 hover:text-rose-400 cursor-pointer"
                              title="Delete log"
                            >
                              <Trash2 size={13} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────────────
              TAB 4: SCRAPER INDEX & BOUNCE BLACKLIST
             ─────────────────────────────────────────────────────────────────── */}
          {activeTab === 'index' && (
            <div className="glass-panel rounded-3xl p-6 space-y-5">
              <div className="flex items-center justify-between gap-3 flex-wrap border-b border-white/[0.08] pb-4">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSubViewIndex('posts')}
                    className={`px-4 py-2 rounded-xl text-xs font-extrabold cursor-pointer transition ${
                      subViewIndex === 'posts'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white/[0.04] text-slate-400 hover:text-white'
                    }`}
                  >
                    Verified Recruiter Posts ({iStats.verified_recruiter_posts || posts.length})
                  </button>
                  <button
                    onClick={() => setSubViewIndex('blacklist')}
                    className={`px-4 py-2 rounded-xl text-xs font-extrabold cursor-pointer transition ${
                      subViewIndex === 'blacklist'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white/[0.04] text-slate-400 hover:text-white'
                    }`}
                  >
                    Global Email Blacklist ({iStats.blacklisted_emails || blacklist.length})
                  </button>
                </div>

                {subViewIndex === 'posts' ? (
                  <div className="flex items-center gap-2">
                    <input
                      value={postSearch}
                      onChange={e => setPostSearch(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && loadPosts()}
                      placeholder="Search role, company, email..."
                      className="glass-input rounded-xl px-3.5 py-2 text-xs w-60"
                    />
                    <button
                      onClick={loadPosts}
                      className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-xs font-bold cursor-pointer"
                    >
                      Search
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <input
                      value={blSearch}
                      onChange={e => setBlSearch(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && loadBlacklist()}
                      placeholder="Filter blocked emails..."
                      className="glass-input rounded-xl px-3.5 py-2 text-xs w-60"
                    />
                    <button
                      onClick={loadBlacklist}
                      className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-xs font-bold cursor-pointer"
                    >
                      Filter
                    </button>
                  </div>
                )}
              </div>

              {subViewIndex === 'posts' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-slate-400 border-b border-white/[0.08] uppercase text-[10px]">
                        <th className="py-3 pr-3">Role &amp; Company</th>
                        <th className="py-3 pr-3">Author / Location</th>
                        <th className="py-3 pr-3">Extracted Emails</th>
                        <th className="py-3 pr-3">Published</th>
                        <th className="py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05]">
                      {posts.map(p => (
                        <tr key={p.id} className="hover:bg-white/[0.02]">
                          <td className="py-3 pr-3 max-w-xs">
                            <div className="font-extrabold text-white truncate">{p.role_title}</div>
                            <div className="text-blue-400 font-semibold truncate">{p.company}</div>
                          </td>
                          <td className="py-3 pr-3">
                            <div className="font-semibold text-slate-200">{p.author_name}</div>
                            <div className="text-[11px] text-slate-400">{p.location}</div>
                          </td>
                          <td className="py-3 pr-3 font-mono text-[11px] text-emerald-300">
                            {(p.emails || []).map(e => typeof e === 'string' ? e : e.email).join(', ') || '—'}
                          </td>
                          <td className="py-3 pr-3 text-slate-400">{p.date_published?.slice(0, 10) || p.discovered_at?.slice(0, 10)}</td>
                          <td className="py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {p.post_url && (
                                <a href={p.post_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300">
                                  <ExternalLink size={13} />
                                </a>
                              )}
                              <button
                                onClick={() => handleDeletePost(p.id)}
                                className="text-slate-400 hover:text-rose-400 cursor-pointer"
                                title="Delete indexed post"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex gap-2 flex-wrap">
                    <input
                      value={newBlEmail}
                      onChange={e => setNewBlEmail(e.target.value)}
                      placeholder="Block dead/bounced email globally (e.g. dead@domain.com)"
                      className="flex-1 glass-input rounded-xl px-3.5 py-2 text-xs"
                    />
                    <input
                      value={newBlReason}
                      onChange={e => setNewBlReason(e.target.value)}
                      placeholder="Reason"
                      className="w-52 glass-input rounded-xl px-3.5 py-2 text-xs"
                    />
                    <button
                      onClick={handleAddBlacklist}
                      className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-extrabold cursor-pointer"
                    >
                      Block Globally &amp; Purge
                    </button>
                  </div>

                  <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="text-slate-400 border-b border-white/[0.08] uppercase text-[10px]">
                          <th className="py-2.5 pr-3">Blocked Email</th>
                          <th className="py-2.5 pr-3">Reason</th>
                          <th className="py-2.5 pr-3">Source</th>
                          <th className="py-2.5 pr-3">Date Added</th>
                          <th className="py-2.5 text-right">Unblock</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.05]">
                        {blacklist.map(b => (
                          <tr key={b.id} className="hover:bg-white/[0.02]">
                            <td className="py-2.5 pr-3 font-mono font-bold text-rose-300">{b.email}</td>
                            <td className="py-2.5 pr-3 text-slate-300">{b.reason}</td>
                            <td className="py-2.5 pr-3 text-slate-400">{b.source}</td>
                            <td className="py-2.5 pr-3 text-slate-500">{b.created_at?.slice(0, 10)}</td>
                            <td className="py-2.5 text-right">
                              <button
                                onClick={() => handleRemoveBlacklist(b.id)}
                                className="text-slate-400 hover:text-emerald-400 cursor-pointer"
                                title="Unblock email"
                              >
                                <Trash2 size={13} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────────────
              TAB 5: PLATFORM CONFIG, API KEYS & BACKUPS
             ─────────────────────────────────────────────────────────────────── */}
          {activeTab === 'config' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 glass-panel rounded-3xl p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
                  <div>
                    <h2 className="text-base font-extrabold text-white">Scraper &amp; OAuth API Keys</h2>
                    <p className="text-xs text-slate-400">Stored atomically in <code className="text-blue-300">web/backend/scraper_config.json</code></p>
                  </div>
                  <button
                    onClick={() => setShowSecrets(s => !s)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.06] text-xs font-bold text-slate-300 cursor-pointer"
                  >
                    {showSecrets ? <EyeOff size={13} /> : <Eye size={13} />}
                    <span>{showSecrets ? 'Hide Keys' : 'Reveal Keys'}</span>
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[
                    { key: 'serper_api_key', label: 'Serper.dev API Key (Google Jobs & ATS)' },
                    { key: 'scraper_proxy', label: 'Scraper Proxy URL (Optional HTTP/SOCKS)' },
                    { key: 'adzuna_app_id', label: 'Adzuna App ID' },
                    { key: 'adzuna_app_key', label: 'Adzuna App Key' },
                    { key: 'jooble_api_key', label: 'Jooble API Key' },
                    { key: 'careerjet_affid', label: 'Careerjet Affiliate ID' },
                    { key: 'google_client_id', label: 'Google OAuth Client ID' },
                    { key: 'google_client_secret', label: 'Google OAuth Client Secret' },
                  ].map(field => (
                    <div key={field.key}>
                      <label className="text-xs font-bold text-slate-300 mb-1.5 block">{field.label}</label>
                      <input
                        type={showSecrets ? 'text' : 'password'}
                        value={cfg[field.key] || ''}
                        onChange={e => setCfg(c => ({ ...c, [field.key]: e.target.value }))}
                        placeholder={`Enter ${field.key}...`}
                        className="w-full glass-input rounded-xl px-3.5 py-2.5 text-xs font-mono"
                      />
                    </div>
                  ))}
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleSaveConfig}
                    disabled={savingCfg}
                    className="shimmer-btn flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-xs font-extrabold shadow-lg cursor-pointer"
                  >
                    <Save size={14} />
                    <span>{savingCfg ? 'Saving Configuration…' : 'Save Platform Keys'}</span>
                  </button>
                </div>
              </div>

              {/* SQLite Backups Vault */}
              <div className="glass-panel rounded-3xl p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
                  <div>
                    <h2 className="text-base font-extrabold text-white">SQLite Hot Backups</h2>
                    <p className="text-xs text-slate-400">Rolling 14-day snapshots</p>
                  </div>
                  <button
                    onClick={() => handleMaintenance('backup-db')}
                    className="px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold cursor-pointer"
                  >
                    + Snapshot
                  </button>
                </div>

                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {(sStats.backups || cfg.backups || []).length === 0 ? (
                    <p className="text-xs text-slate-500 text-center py-6">No backups created yet.</p>
                  ) : (
                    (sStats.backups || cfg.backups || []).map(b => (
                      <div key={b.filename} className="flex items-center justify-between p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] text-xs">
                        <div>
                          <div className="font-mono font-bold text-slate-200">{b.filename}</div>
                          <div className="text-[10px] text-slate-400">{b.modified_at}</div>
                        </div>
                        <span className="px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 font-bold text-[11px]">
                          {b.size_mb} MB
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

        </main>
      </div>
    </PageWrapper>
  )
}
