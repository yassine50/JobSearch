import { useEffect, useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import client, { getCached } from '../api/client.js'
import {
  Settings as SettingsIcon, Mail, User, Trash2, Plus, Eye, EyeOff,
  Save, Send, ShieldAlert, RefreshCw, Search, Loader2, Sparkles, Puzzle, Download
} from 'lucide-react'

function Section({ title, sub, icon: Icon, children }) {
  return (
    <div className="glass-panel rounded-3xl p-6 mb-5 relative overflow-hidden">
      <div className="glow-line-top" />
      <div className="flex items-center gap-3 mb-5 pb-4 border-b border-white/[0.07]">
        <div className="w-9 h-9 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0">
          <Icon size={17} />
        </div>
        <div>
          <h2 className="font-extrabold text-base text-white">{title}</h2>
          {sub && <p className="text-xs text-slate-400">{sub}</p>}
        </div>
      </div>
      {children}
    </div>
  )
}

export default function Settings() {
  const { user, updateUser } = useAuth()
  const toast = useToast()

  // SMTP
  const [smtp, setSmtp]          = useState(() => {
    const cached = getCached('/email/settings', null)
    const defaults = { smtp_host:'smtp.gmail.com', smtp_port:587, smtp_user:'', smtp_password:'', sender_name:'' }
    return cached?.configured ? { ...defaults, ...cached } : defaults
  })
  const [showPass, setShowPass]  = useState(false)
  const [smtpSaving, setSmtpSaving] = useState(false)
  const [testing, setTesting]    = useState(false)

  // Profile
  const [profile, setProfile]    = useState({ name: user?.name || '', password:'', confirm:'' })
  const [profSaving, setProfSaving] = useState(false)

  // Custom templates
  const [templates, setTemplates] = useState(() => getCached('/email/custom-templates', []))
  const [newTpl, setNewTpl]       = useState({ name:'', subject:'', body:'' })
  const [addingTpl, setAddingTpl] = useState(false)
  const [tplSaving, setTplSaving] = useState(false)

  // Blacklist & Bounces
  const [blacklist, setBlacklist] = useState(() => getCached('/email/blacklist', []))
  const [blSearch, setBlSearch]   = useState('')
  const [blLoading, setBlLoading] = useState(false)
  const [syncingBounces, setSyncingBounces] = useState(false)
  const [newBlEmail, setNewBlEmail] = useState('')
  const [newBlReason, setNewBlReason] = useState('Manual entry')

  // Connect Gmail (Google OAuth — temporarily disabled until Google verification completes)
  const [gmail, setGmail] = useState(() => getCached('/email/google/status', { available: false, connected: false, email: '' }))
  const [gmailConnecting, setGmailConnecting] = useState(false)
  const [showAdvancedSmtp, setShowAdvancedSmtp] = useState(true)
  const loadGmail = () => client.get('/email/google/status').then(r => setGmail(r.data)).catch(() => {})

  const connectGmail = async () => {
    setGmailConnecting(true)
    try {
      const { data } = await client.get('/email/google/auth-url', {
        params: { origin: window.location.origin }
      })
      window.location.href = data.url
    } catch (e) {
      toast(e.response?.data?.detail || 'Could not start Google sign-in', 'error')
      setGmailConnecting(false)
    }
  }

  const disconnectGmail = async () => {
    try {
      await client.post('/email/google/disconnect')
      toast('Gmail disconnected', 'success')
    } catch (e) {
      toast(e.response?.data?.detail || 'Could not disconnect Gmail', 'error')
    }
    loadGmail()
  }

  useEffect(() => {
    loadGmail()
    const params = new URLSearchParams(window.location.search)
    const g = params.get('gmail')
    if (g) {
      const reasons = {
        permission: 'Please tick the "Send email on your behalf" box when Google asks.',
        no_refresh: 'Google did not grant offline access. Please try again.',
        expired: 'The sign-in link expired. Please try again.',
        access_denied: 'You cancelled the Google sign-in.',
      }
      if (g === 'connected') toast('✅ Gmail connected! Applications will be sent from your Gmail.', 'success')
      else toast(`Gmail connection failed. ${reasons[params.get('reason')] || 'Please try again.'}`, 'error')
      window.history.replaceState({}, '', window.location.pathname)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadBlacklist = () => {
    setBlLoading(true)
    client.get('/email/blacklist')
      .then(r => setBlacklist(r.data))
      .catch(() => {})
      .finally(() => setBlLoading(false))
  }

  useEffect(() => {
    client.get('/email/settings').then(r => {
      if (r.data.configured) setSmtp(s => ({ ...s, ...r.data }))
    }).catch(() => {})
    client.get('/email/custom-templates').then(r => setTemplates(r.data)).catch(() => {})
    loadBlacklist()
  }, [])

  const saveSmtp = async () => {
    if (!smtp.smtp_user || !smtp.smtp_password) return toast('Fill all email fields', 'error')
    setSmtpSaving(true)
    try {
      await client.post('/email/settings', smtp)
      toast('Email settings saved!', 'success')
    } catch (e) { toast(e.response?.data?.detail || 'Save failed', 'error') }
    setSmtpSaving(false)
  }

  const testEmail = async () => {
    setTesting(true)
    try {
      await client.post('/email/test')
      toast('Test email sent to your inbox! ✅', 'success')
    } catch (e) { toast(e.response?.data?.detail || 'Test failed', 'error') }
    setTesting(false)
  }

  const saveProfile = async () => {
    if (!profile.name.trim()) return toast('Name cannot be empty', 'error')
    if (profile.password && profile.password !== profile.confirm)
      return toast('Passwords do not match', 'error')
    setProfSaving(true)
    try {
      const payload = { name: profile.name.trim() }
      if (profile.password) payload.password = profile.password
      const { data } = await client.patch('/auth/profile', payload)
      if (updateUser) updateUser({ name: data.name })
      toast('Profile updated!', 'success')
      setProfile(p => ({ ...p, password: '', confirm: '' }))
    } catch (e) { toast(e.response?.data?.detail || 'Update failed', 'error') }
    setProfSaving(false)
  }

  const saveTemplate = async () => {
    if (!newTpl.name.trim() || !newTpl.body.trim()) return toast('Name and body required', 'error')
    setTplSaving(true)
    try {
      const { data } = await client.post('/email/custom-templates', newTpl)
      setTemplates(t => [data, ...t])
      setNewTpl({ name: '', subject: '', body: '' })
      setAddingTpl(false)
      toast('Template saved!', 'success')
    } catch (e) { toast('Failed to save template', 'error') }
    setTplSaving(false)
  }

  const deleteTemplate = async (id) => {
    try {
      await client.delete(`/email/custom-templates/${id}`)
      setTemplates(t => t.filter(x => x.id !== id))
      toast('Template deleted', 'info')
    } catch { toast('Delete failed', 'error') }
  }

  const handleSyncBounces = async () => {
    setSyncingBounces(true)
    try {
      const { data } = await client.post('/email/sync-bounces', { delete_from_gmail: true })
      const sentMsg = data.deleted_from_sent > 0 ? `, purged ${data.deleted_from_sent} dead emails from Sent box` : ''
      toast(`✅ Scanned ${data.scanned_messages} messages: Blacklisted ${data.blacklisted_added} dead emails${sentMsg}, purged ${data.tracker_purged} dead applications from Tracker!`, 'success')
      loadBlacklist()
    } catch (e) {
      toast(e.response?.data?.detail || 'Sync failed', 'error')
    } finally {
      setSyncingBounces(false)
    }
  }

  const handleAddBlacklist = async () => {
    if (!newBlEmail.trim() || !newBlEmail.includes('@')) return toast('Enter a valid email', 'error')
    try {
      await client.post('/email/blacklist', { email: newBlEmail.trim(), reason: newBlReason })
      toast('Email added to blacklist', 'success')
      setNewBlEmail('')
      loadBlacklist()
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to add', 'error')
    }
  }

  const handleRemoveBlacklist = async (id) => {
    try {
      await client.delete(`/email/blacklist/${id}`)
      setBlacklist(prev => prev.filter(b => b.id !== id))
      toast('Email unblocked and removed from blacklist', 'info')
    } catch {
      toast('Failed to unblock', 'error')
    }
  }

  const filteredBlacklist = useMemo(() => {
    const q = blSearch.trim().toLowerCase()
    const list = !q
      ? blacklist
      : blacklist.filter(b => b.email?.toLowerCase().includes(q) || (b.reason || '').toLowerCase().includes(q))
    return list.slice(0, 80)
  }, [blacklist, blSearch])

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-12 pt-20 md:pt-8 lg:pt-10 pb-14 w-full">

          {/* Hero Header */}
          <div className="glass-panel rounded-3xl p-6 mb-6 relative overflow-hidden">
            <div className="glow-line-top" />
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300 text-[11px] font-bold mb-1.5">
              <Sparkles size={11} className="text-amber-400" />
              <span>Workspace Configuration</span>
            </div>
            <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white flex items-center gap-2.5">
              <span>Account &amp;</span>
              <span className="text-gradient-blue">Outreach Settings</span>
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Manage your identity, 1-click Gmail OAuth connection, custom outreach templates, and global bounce protection.
            </p>
          </div>

          {/* Profile */}
          <Section title="Account Profile" sub="Update your display name and security credentials" icon={User}>
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-300 mb-1.5 block">Display Name</label>
                  <input
                    value={profile.name}
                    onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-300 mb-1.5 block">Email (read only)</label>
                  <input
                    value={user?.email || ''}
                    disabled
                    className="w-full bg-[#050811]/50 border border-white/[0.06] rounded-xl px-3.5 py-2.5 text-sm text-slate-500 cursor-not-allowed"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-300 mb-1.5 block">New Password</label>
                  <input
                    type="password"
                    value={profile.password}
                    onChange={e => setProfile(p => ({ ...p, password: e.target.value }))}
                    placeholder="Leave blank to keep current"
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm placeholder-slate-600"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-300 mb-1.5 block">Confirm Password</label>
                  <input
                    type="password"
                    value={profile.confirm}
                    onChange={e => setProfile(p => ({ ...p, confirm: e.target.value }))}
                    placeholder="Repeat new password"
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm placeholder-slate-600"
                  />
                </div>
              </div>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={saveProfile}
                disabled={profSaving}
                className="shimmer-btn flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-extrabold px-5 py-2.5 rounded-xl text-xs shadow-lg shadow-blue-600/20 transition cursor-pointer"
              >
                <Save size={14} /> {profSaving ? 'Saving…' : 'Save Profile'}
              </motion.button>
            </div>
          </Section>

          {/* Email: Gmail App Password + Connect Gmail (temporarily disabled pending verification) */}
          <Section title="Email / Gmail Setup" sub="Dispatch tailored applications directly from your inbox" icon={Mail}>
            <div className="space-y-4">
              {gmail.connected ? (
                <div className="flex items-center justify-between gap-3 flex-wrap bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-4">
                  <div className="text-sm">
                    <p className="font-extrabold text-emerald-300">✅ Gmail Connected</p>
                    <p className="text-xs text-slate-300 mt-0.5">
                      Applications are sent from <strong>{gmail.email}</strong>. Replies arrive in your Gmail inbox.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={testEmail}
                      disabled={testing}
                      className="flex items-center gap-2 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.1] disabled:opacity-50 font-bold px-4 py-2 rounded-xl text-xs transition cursor-pointer"
                    >
                      <Send size={13} /> {testing ? 'Sending…' : 'Send Test Email'}
                    </button>
                    <button
                      onClick={disconnectGmail}
                      className="px-4 py-2 rounded-xl text-xs font-bold border border-white/[0.1] text-slate-300 hover:text-white hover:bg-white/[0.06] transition cursor-pointer"
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-start gap-2.5 bg-[#050811]/70 border border-white/[0.08] rounded-2xl p-4 opacity-75">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-slate-300">
                      Send applications from your own Gmail in one click. No passwords or setup needed.
                    </p>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                      Google Verification Pending
                    </span>
                  </div>
                  <button
                    type="button"
                    disabled={true}
                    title="Temporarily disabled while Google OAuth verification is in progress. Please use a Gmail App Password below."
                    className="flex items-center gap-2.5 bg-white/80 text-slate-900 font-extrabold px-5 py-2.5 rounded-xl text-xs shadow-md opacity-50 cursor-not-allowed select-none"
                  >
                    <svg width="16" height="16" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>
                    Connect Gmail (Coming Soon)
                  </button>
                  <p className="text-[11px] text-slate-400">
                    🔒 Temporarily disabled during Google OAuth review — please configure your <strong>Gmail App Password</strong> below.
                  </p>
                </div>
              )}

              {!gmail.connected && (
                <>
                  <div className="bg-blue-500/10 border border-blue-500/25 rounded-2xl p-3.5 text-xs text-blue-200">
                    💡 Use a Gmail <strong>App Password</strong> (not your regular password). Go to{' '}
                    <a href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer" className="underline font-bold text-blue-300">
                      Google Account → Security → App Passwords
                    </a>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-bold text-slate-300 mb-1.5 block">Sender Name</label>
                      <input
                        value={smtp.sender_name}
                        onChange={e => setSmtp(s => ({ ...s, sender_name: e.target.value }))}
                        placeholder="Your Full Name"
                        className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm placeholder-slate-600"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold text-slate-300 mb-1.5 block">Gmail Address</label>
                      <input
                        value={smtp.smtp_user}
                        type="email"
                        onChange={e => setSmtp(s => ({ ...s, smtp_user: e.target.value }))}
                        placeholder="you@gmail.com"
                        className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm placeholder-slate-600"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-300 mb-1.5 block">App Password</label>
                    <div className="relative">
                      <input
                        value={smtp.smtp_password}
                        type={showPass ? 'text' : 'password'}
                        onChange={e => setSmtp(s => ({ ...s, smtp_password: e.target.value }))}
                        placeholder="xxxx xxxx xxxx xxxx"
                        className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm placeholder-slate-600 pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPass(v => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition cursor-pointer"
                      >
                        {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={saveSmtp}
                      disabled={smtpSaving}
                      className="shimmer-btn flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-extrabold px-5 py-2.5 rounded-xl text-xs shadow-lg shadow-blue-600/20 transition cursor-pointer"
                    >
                      <Save size={14} /> {smtpSaving ? 'Saving…' : 'Save Settings'}
                    </motion.button>
                    {!gmail.connected && (
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.97 }}
                        onClick={testEmail}
                        disabled={testing}
                        className="flex items-center gap-2 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] disabled:opacity-50 font-bold px-5 py-2.5 rounded-xl text-xs transition cursor-pointer"
                      >
                        <Send size={14} /> {testing ? 'Sending…' : 'Send Test Email'}
                      </motion.button>
                    )}
                  </div>
                </>
              )}
            </div>
          </Section>

          {/* Custom Email Templates */}
          <Section title="Custom Email Templates" sub="Reusable outreach templates for direct recruiter pitches" icon={Mail}>
            <div className="space-y-2.5 mb-4">
              {templates.length === 0 && !addingTpl && (
                <p className="text-slate-500 text-xs text-center py-4">
                  No custom templates yet. Create one below!
                </p>
              )}
              <AnimatePresence>
                {templates.map(t => (
                  <motion.div
                    key={t.id}
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-center gap-3 p-3.5 glass-card rounded-2xl"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-bold text-xs text-white truncate">{t.name}</p>
                      <p className="text-xs text-slate-400 truncate mt-0.5">{t.subject}</p>
                    </div>
                    <button
                      onClick={() => deleteTemplate(t.id)}
                      className="text-slate-400 hover:text-rose-400 transition p-1.5 rounded-lg hover:bg-rose-500/10 cursor-pointer"
                    >
                      <Trash2 size={14} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>

            <AnimatePresence>
              {addingTpl && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="bg-[#050811]/70 border border-white/[0.08] rounded-2xl p-4 space-y-3 mb-4"
                >
                  <input
                    value={newTpl.name}
                    onChange={e => setNewTpl(t => ({ ...t, name: e.target.value }))}
                    placeholder="Template name (e.g. 'Startup Outreach')"
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
                  />
                  <input
                    value={newTpl.subject}
                    onChange={e => setNewTpl(t => ({ ...t, subject: e.target.value }))}
                    placeholder="Subject line"
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
                  />
                  <textarea
                    value={newTpl.body}
                    onChange={e => setNewTpl(t => ({ ...t, body: e.target.value }))}
                    rows={6}
                    placeholder="Email body..."
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm resize-none font-mono"
                  />
                  <div className="flex gap-2">
                    <motion.button
                      whileTap={{ scale: 0.96 }}
                      onClick={saveTemplate}
                      disabled={tplSaving}
                      className="shimmer-btn flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-extrabold px-4 py-2 rounded-xl text-xs transition cursor-pointer"
                    >
                      <Save size={13} /> {tplSaving ? 'Saving…' : 'Save Template'}
                    </motion.button>
                    <button
                      onClick={() => setAddingTpl(false)}
                      className="px-4 py-2 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] rounded-xl text-xs font-bold transition cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {!addingTpl && (
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setAddingTpl(true)}
                className="flex items-center gap-2 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] px-4 py-2.5 rounded-xl text-xs font-bold transition cursor-pointer"
              >
                <Plus size={14} className="text-blue-400" /> New Template
              </motion.button>
            )}
          </Section>

          {/* Chrome Extension Autofill Card */}
          <Section
            title="1-Click Chrome Autofill Extension"
            sub="Automatically fill job application forms & attach your tailored CV on Workday, Greenhouse, Lever, Ashby & LinkedIn"
            icon={Puzzle}
          >
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/70 border border-blue-500/30 rounded-2xl p-4">
                <div className="space-y-1">
                  <p className="text-sm font-extrabold text-white flex items-center gap-2">
                    <span>⚡ CVtoMatch Autofill for Chrome / Brave / Edge</span>
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Fills your name, email, phone, LinkedIn, GitHub, screening questions, and directly injects your tailored PDF resume into file upload boxes in 1 click.
                  </p>
                </div>
                <a
                  href="/api/extension/download.zip"
                  download="CVtoMatch-Autofill-Extension.zip"
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-extrabold transition shrink-0 shadow-md shadow-blue-500/20"
                >
                  <Download size={14} />
                  <span>Download Extension (.zip)</span>
                </a>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800">
                  <span className="font-extrabold text-blue-400">1. Unzip Archive</span>
                  <p className="text-slate-400 mt-1 text-[11px]">Download and extract <code className="text-slate-200">CVtoMatch-Autofill-Extension.zip</code> on your computer.</p>
                </div>
                <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800">
                  <span className="font-extrabold text-blue-400">2. Open Extensions</span>
                  <p className="text-slate-400 mt-1 text-[11px]">Visit <code className="text-slate-200">chrome://extensions</code> and toggle on <b>Developer mode</b> in the top-right corner.</p>
                </div>
                <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800">
                  <span className="font-extrabold text-blue-400">3. Load Unpacked</span>
                  <p className="text-slate-400 mt-1 text-[11px]">Click <b>Load unpacked</b>, select the extracted folder, and refresh this page to auto-sync your account.</p>
                </div>
              </div>
            </div>
          </Section>

          {/* Official Support & Contact Card */}
          <Section title="Help & Official Support" icon={Mail} badge="support@cvtomatch.com">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <p className="text-sm font-bold text-white">Need help with CV tailoring, recruiter outreach, or your account?</p>
                <p className="text-xs text-slate-400 mt-1">
                  Reach our team directly at{' '}
                  <a href="mailto:support@cvtomatch.com" className="text-blue-400 font-bold hover:underline">
                    support@cvtomatch.com
                  </a>
                  {' '}and we will get back to you promptly.
                </p>
              </div>
              <a
                href="mailto:support@cvtomatch.com"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-extrabold transition shrink-0 shadow-sm"
              >
                <Mail size={14} />
                <span>Email support@cvtomatch.com</span>
              </a>
            </div>
          </Section>

        </main>
      </div>
    </PageWrapper>
  )
}
