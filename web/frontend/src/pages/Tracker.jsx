import { useEffect, useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import InterviewPrepModal from '../components/modals/InterviewPrepModal.jsx'
import client, { getCached } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { 
  Plus, Trash2, ExternalLink, StickyNote, Mail, CheckCircle, XCircle,
  Download, Loader2, Sparkles, Inbox, Clock, 
  Send, CheckSquare, Square, FileText, MessageSquare, Building2, MapPin, 
  Check, Copy, Paperclip, Search, X, Video, KanbanSquare
} from 'lucide-react'

const COLUMNS = [
  { key: 'applied',   label: '📤 Sent / Applied', shortLabel: 'Applied',   color: 'border-blue-500/40',    topBar: 'from-blue-500 to-indigo-500',   dot: 'bg-blue-400',    text: 'text-blue-400'    },
  { key: 'review',    label: '👀 Under Review',   shortLabel: 'Review',    color: 'border-amber-500/40',   topBar: 'from-amber-400 to-orange-500',  dot: 'bg-amber-400',   text: 'text-amber-300'   },
  { key: 'interview', label: '📞 Interview',      shortLabel: 'Interview', color: 'border-purple-500/40',  topBar: 'from-purple-500 to-pink-500',   dot: 'bg-purple-400',  text: 'text-purple-300'  },
  { key: 'offer',     label: '🤝 Offer',          shortLabel: 'Offer',     color: 'border-emerald-500/40', topBar: 'from-emerald-400 to-teal-500',  dot: 'bg-emerald-400', text: 'text-emerald-300' },
  { key: 'rejected',  label: '❌ Rejected',       shortLabel: 'Rejected',  color: 'border-rose-500/40',    topBar: 'from-rose-500 to-red-600',      dot: 'bg-rose-400',    text: 'text-rose-400'    },
  { key: 'accepted',  label: '🏆 Accepted',       shortLabel: 'Accepted',  color: 'border-yellow-500/40',  topBar: 'from-yellow-400 to-amber-500',  dot: 'bg-yellow-400',  text: 'text-yellow-300'  },
]

function getMeetLink(app) {
  if (!app) return null
  if (app.notes) {
    const match = app.notes.match(/https?:\/\/meet\.google\.com\/[^\s<>"'\)]+/i)
    if (match) return match[0].replace(/[.,]+$/, '')
    const zoomMatch = app.notes.match(/https?:\/\/[a-zA-Z0-9-]+\.zoom\.us\/j\/[^\s<>"'\)]+/i)
    if (zoomMatch) return zoomMatch[0].replace(/[.,]+$/, '')
    const teamsMatch = app.notes.match(/https?:\/\/teams\.microsoft\.com\/[^\s<>"'\)]+/i)
    if (teamsMatch) return teamsMatch[0].replace(/[.,]+$/, '')
  }
  return null
}

function getPortalLink(app) {
  if (!app) return null
  if (app.notes) {
    const match = app.notes.match(/Portal \/ Position Link:\s*([^\s]+)/i)
    if (match && match[1]) return match[1].replace(/[.,]+$/, '')
    const urlMatch = app.notes.match(/https?:\/\/[^\s<>"'\)]+/i)
    if (urlMatch && (app.notes.toLowerCase().includes('career') || app.notes.toLowerCase().includes('apply') || app.notes.toLowerCase().includes('job'))) {
      return urlMatch[0].replace(/[.,]+$/, '')
    }
  }
  return app.url || null
}

function getAppEmails(app) {
  const emails = new Set()
  if (Array.isArray(app?.emails)) {
    app.emails.forEach(e => {
      if (e?.to_email) emails.add(e.to_email.trim().toLowerCase())
    })
  }
  if (app?.notes) {
    const matches = app.notes.match(/[\w.+-]+@[\w-]+\.[\w.-]+/gi) || []
    matches.forEach(m => emails.add(m.trim().toLowerCase()))
  }
  return Array.from(emails)
}

function getPrimaryEmail(app) {
  if (Array.isArray(app?.emails) && app.emails.length > 0 && app.emails[0]?.to_email) {
    return app.emails[0].to_email
  }
  if (app?.notes) {
    const match = app.notes.match(/[\w.+-]+@[\w-]+\.[\w.-]+/i)
    if (match) return match[0]
  }
  return null
}

function matchesAppSearch(app, query, emailOnly) {
  if (!query) return true
  const q = query.trim().toLowerCase()
  const appEmails = getAppEmails(app)

  const hasEmailMatch = appEmails.some(em => em.includes(q))
  if (hasEmailMatch) return true

  if (Array.isArray(app.emails)) {
    const logMatch = app.emails.some(e => 
      (e.to_name && e.to_name.toLowerCase().includes(q)) ||
      (e.subject && e.subject.toLowerCase().includes(q))
    )
    if (logMatch) return true
  }

  if (emailOnly) return false

  if (app.company && app.company.toLowerCase().includes(q)) return true
  if (app.title && app.title.toLowerCase().includes(q)) return true
  if (app.location && app.location.toLowerCase().includes(q)) return true
  if (app.notes && app.notes.toLowerCase().includes(q)) return true

  return false
}

export default function Tracker() {
  const [apps, setApps]       = useState(() => {
    const cached = getCached('/tracker', [])
    return Array.isArray(cached) ? cached : []
  })
  const [editing, setEditing] = useState(null)
  const [notes, setNotes]     = useState('')
  const [adding, setAdding]   = useState(false)
  const [form, setForm]       = useState({ title:'', company:'', location:'', url:'', notes:'' })
  const [syncingMailbox, setSyncingMailbox] = useState(false)
  const [searchQuery, setSearchQuery]       = useState('')
  const [emailOnly, setEmailOnly]           = useState(false)

  // Interactive Conversation Thread Modal State
  const [threadModal, setThreadModal]     = useState(null)
  const [threadData, setThreadData]       = useState(null)
  const [loadingThread, setLoadingThread] = useState(false)
  const [copiedEmail, setCopiedEmail]     = useState(null)

  // Recruiter Follow-up State
  const [followUpCandidates, setFollowUpCandidates] = useState(() => {
    const cached = getCached('/email/follow-up/candidates?days=3', [])
    return Array.isArray(cached) ? cached : []
  })
  const [followUpModal, setFollowUpModal]           = useState(null)
  const [followUpForm, setFollowUpForm]             = useState({ custom_subject: '', custom_body: '', attach_cv: true, recipients: [] })
  const [sendingFollowUp, setSendingFollowUp]       = useState(false)
  const [batchFollowUpOpen, setBatchFollowUpOpen]   = useState(false)
  const [selectedBatchIds, setSelectedBatchIds]     = useState(() => {
    const cached = getCached('/email/follow-up/candidates?days=3', [])
    return Array.isArray(cached) ? cached.map(c => c.application_id) : []
  })
  const [prepApp, setPrepApp]                       = useState(null)

  const toast = useToast()

  const loadFollowUps = () => {
    client.get('/email/follow-up/candidates?days=3')
      .then(r => {
        const cands = r.data || []
        setFollowUpCandidates(cands)
        setSelectedBatchIds(cands.map(c => c.application_id))
      })
      .catch(() => {})
  }

  const load = () => {
    client.get('/tracker')
      .then(r => {
        if (Array.isArray(r.data)) {
          setApps(r.data)
        }
      })
      .catch(err => {
        console.error('Failed to load applications:', err)
        toast('Unable to load tracker applications. Please ensure backend is running.', 'error')
      })
    loadFollowUps()
  }
  useEffect(() => { load() }, [])

  const openThreadModal = async (app) => {
    setThreadModal(app)
    setLoadingThread(true)
    setThreadData(null)
    try {
      const { data } = await client.get(`/tracker/${app.id}/thread`)
      setThreadData(data)
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to load conversation thread', 'error')
    } finally {
      setLoadingThread(false)
    }
  }

  const handleDownloadCv = async (appId, filename) => {
    try {
      const response = await client.get(`/tracker/${appId}/cv`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || 'Tailored_CV.pdf'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      toast('CV download failed or no CV attached', 'error')
    }
  }

  const exportCsv = async () => {
    try {
      const response = await client.get('/tracker/export', { responseType: 'blob' })
      const url = window.URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = 'applications.csv'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      toast('Exported applications to CSV!', 'success')
    } catch (e) {
      toast('Failed to export CSV', 'error')
    }
  }

  const copyToClipboard = (text) => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedEmail(text)
    toast(`Copied ${text}`, 'success')
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  const openFollowUpModal = (app) => {
    const existing = followUpCandidates.find(c => c.application_id === app.id)
    const subject = existing?.preview_subject || `Follow-up: Application for ${app.title}`
    const body = existing?.preview_body || `Dear Hiring Team,\n\nI am following up on my application for the ${app.title} position at ${app.company}. I remain very interested in the role and would welcome the opportunity to discuss my qualifications.\n\nBest regards`
    setFollowUpForm({
      custom_subject: subject,
      custom_body: body,
      attach_cv: true,
      recipients: existing?.recipients || []
    })
    setFollowUpModal(app)
  }

  const handleSendFollowUp = async () => {
    if (!followUpModal) return
    setSendingFollowUp(true)
    try {
      const { data } = await client.post('/email/follow-up/send', {
        application_id: followUpModal.id,
        custom_subject: followUpForm.custom_subject,
        custom_body: followUpForm.custom_body,
        attach_cv: followUpForm.attach_cv
      })
      toast(data.message || 'Follow-up sent successfully!', 'success')
      setFollowUpModal(null)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || 'Failed to send follow-up', 'error')
    } finally {
      setSendingFollowUp(false)
    }
  }

  const handleSendBatchFollowUp = async () => {
    if (selectedBatchIds.length === 0) return
    setSendingFollowUp(true)
    try {
      const { data } = await client.post('/email/follow-up/send-all', {
        application_ids: selectedBatchIds,
        attach_cv: true
      })
      toast(data.message || `Sent ${data.sent_count} follow-up email(s)!`, 'success')
      setBatchFollowUpOpen(false)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || 'Batch follow-up failed', 'error')
    } finally {
      setSendingFollowUp(false)
    }
  }

  const handleSyncMailbox = async () => {
    setSyncingMailbox(true)
    try {
      const { data } = await client.post('/tracker/sync-mailbox')
      const summary = data.summary || {}
      const b = summary.breakdown || {}
      const parts = []
      if (summary.replies_updated > 0) parts.push(`${summary.replies_updated} status update${summary.replies_updated > 1 ? 's' : ''}`)
      if (b.interview) parts.push(`📞 ${b.interview} interview`)
      if (b.offer) parts.push(`🤝 ${b.offer} offer`)
      if (b.review) parts.push(`👀 ${b.review} under review`)
      if (b.rejected) parts.push(`❌ ${b.rejected} rejection`)
      if (summary.restored > 0) parts.push(`♻️ ${summary.restored} restored`)
      if (summary.reclassified > 0) parts.push(`🔎 ${summary.reclassified} corrected`)
      if (summary.follow_ups_sent > 0) parts.push(`${summary.follow_ups_sent} follow-ups sent`)
      if (summary.auto_rejected > 0) parts.push(`${summary.auto_rejected} auto-closed (3d no reply)`)
      if (summary.saved_sent > 0) parts.push(`${summary.saved_sent} queued jobs dispatched`)
      if (summary.dead_purged > 0) parts.push(`${summary.dead_purged} bounces cleaned`)
      if (summary.reply_error) toast(`Reply scan issue: ${summary.reply_error}`, 'error')

      let msg = '✨ Mailbox Synced!'
      if (parts.length > 0) {
        msg += ` (${parts.join(' · ')})`
      } else {
        msg += ' (all correspondence and queue are up to date)'
      }

      if (summary.quota_reached) {
        msg += ` · ⚠️ Daily Gmail quota reached (${summary.remaining_saved} jobs remaining in queue)`
      }

      toast(msg, summary.quota_reached ? 'info' : 'success')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || 'Mailbox sync failed', 'error')
    } finally {
      setSyncingMailbox(false)
    }
  }

  const addApp = async () => {
    if (!form.title) return
    await client.post('/tracker', form)
    setForm({ title:'', company:'', location:'', url:'', notes:'' })
    setAdding(false); load()
  }

  const moveStatus = async (id, status) => {
    await client.patch(`/tracker/${id}`, { status })
    setApps(a => a.map(x => x.id === id ? { ...x, status } : x))
  }

  const saveNotes = async () => {
    await client.patch(`/tracker/${editing}`, { notes })
    setApps(a => a.map(x => x.id === editing ? { ...x, notes } : x))
    setEditing(null)
  }

  const del = async (id) => {
    await client.delete(`/tracker/${id}`)
    setApps(a => a.filter(x => x.id !== id))
  }

  const filteredApps = useMemo(() => {
    return apps.filter(a => matchesAppSearch(a, searchQuery, emailOnly))
  }, [apps, searchQuery, emailOnly])

  const byStatus = key => filteredApps.filter(a => (a.status === 'saved' ? 'applied' : a.status) === key)
  const totalEmails = apps.reduce((sum, a) => sum + (a.emails?.length || 0), 0)
  const totalFiltered = filteredApps.length

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14 w-full">

          {/* Hero Command Header */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-panel rounded-3xl p-5 md:p-6 mb-5 relative overflow-hidden flex flex-col lg:flex-row lg:items-center justify-between gap-4"
          >
            <div className="glow-line-top" />
            <div className="space-y-1 relative z-10">
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300 text-[11px] font-bold">
                <KanbanSquare size={11} className="text-blue-400" />
                <span>CRM Application Pipeline</span>
              </div>
              <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white">
                Applications &amp; <span className="text-gradient-blue">Recruiter Threads</span>
              </h1>
              <div className="flex items-center gap-2 text-slate-400 text-xs pt-0.5 flex-wrap">
                <span className="font-semibold text-slate-300">{apps.length} tracked roles</span>
                <span>·</span>
                <a 
                  href="/email" 
                  className="text-blue-400 hover:text-blue-300 transition flex items-center gap-1 font-bold"
                  title="View full audit log of all sent emails"
                >
                  <span>{totalEmails} outreach emails dispatched</span>
                  <ExternalLink size={11} />
                </a>
              </div>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap relative z-10">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleSyncMailbox}
                disabled={syncingMailbox}
                title="1-Click Mailbox Sync: Purges dead/bounced emails from Sent box and syncs incoming recruiter replies"
                className="shimmer-btn flex items-center gap-2 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 text-white font-extrabold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-blue-600/25 transition cursor-pointer"
              >
                {syncingMailbox ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} className="text-amber-300" />}
                <span>{syncingMailbox ? 'Syncing Mailbox...' : '⚡ Sync Mailbox'}</span>
              </motion.button>
              <button
                onClick={exportCsv}
                className="flex items-center gap-1.5 bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 border border-white/[0.08] text-xs font-bold px-3.5 py-2.5 rounded-xl transition cursor-pointer"
                title="Download all applications as CSV"
              >
                <Download size={14} className="text-blue-400" /> Export CSV
              </button>
              <button
                onClick={() => setAdding(true)}
                className="flex items-center gap-1.5 bg-white/[0.04] hover:bg-white/[0.08] text-white border border-white/[0.08] hover:border-blue-500/40 text-xs font-bold px-3.5 py-2.5 rounded-xl transition cursor-pointer"
              >
                <Plus size={15} className="text-emerald-400" /> Add Manually
              </button>
            </div>
          </motion.div>

          {/* Follow-up Assistant Alert Bar */}
          <AnimatePresence>
            {followUpCandidates.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mb-5 bg-gradient-to-r from-amber-950/60 via-slate-900/90 to-amber-950/60 border border-amber-500/35 rounded-2xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg backdrop-blur-xl"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-amber-500/15 border border-amber-500/35 flex items-center justify-center text-amber-400 shrink-0">
                    <Clock size={16} />
                  </div>
                  <div>
                    <p className="text-xs sm:text-sm font-extrabold text-amber-200">
                      ⚡ Follow-Up Assistant: {followUpCandidates.length} application{followUpCandidates.length > 1 ? 's' : ''} awaiting recruiter response (&gt;3 days)
                    </p>
                    <p className="text-xs text-amber-300/75 mt-0.5">
                      Following up increases recruiter response rates. Review candidates and dispatch follow-ups in 1 click.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setBatchFollowUpOpen(true)}
                  className="shimmer-btn flex items-center gap-1.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-xs px-4 py-2 rounded-xl transition shadow-md cursor-pointer shrink-0"
                >
                  <Send size={13} />
                  <span>Review &amp; Follow Up ({followUpCandidates.length})</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Stage KPI Ribbon */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 mb-5">
            {COLUMNS.map((c, idx) => {
              const count = byStatus(c.key).length
              return (
                <motion.div
                  key={c.key}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.04, duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                  whileHover={{ y: -3, scale: 1.015 }}
                  className={`glass-card border ${c.color} rounded-2xl px-3.5 py-3 relative overflow-hidden`}
                >
                  <div className={`absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r ${c.topBar}`} />
                  <div className="flex items-center justify-between">
                    <span className="text-xl font-black text-white">{count}</span>
                    <span className={`w-2 h-2 rounded-full ${c.dot} ${count > 0 ? 'animate-pulse' : ''}`} />
                  </div>
                  <div className="text-[11px] font-bold text-slate-400 mt-0.5 truncate">{c.shortLabel}</div>
                </motion.div>
              )
            })}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: COLUMNS.length * 0.04, duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
              whileHover={{ y: -3, scale: 1.015 }}
              className="glass-card border border-blue-500/40 rounded-2xl px-3.5 py-3 relative overflow-hidden"
            >
              <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-400 to-purple-500" />
              <div className="flex items-center justify-between">
                <span className="text-xl font-black text-blue-400">{totalEmails}</span>
                <Mail size={13} className="text-blue-400" />
              </div>
              <div className="text-[11px] font-bold text-slate-400 mt-0.5 truncate">Emails Sent</div>
            </motion.div>
          </div>

          {/* Search & Filter Bar */}
          <div className="mb-5 glass-panel rounded-2xl p-3">
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
              <div className="relative flex-1 flex items-center">
                <Search size={16} className="absolute left-3.5 text-blue-400 pointer-events-none" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search by recruiter email (e.g. tiffany@adp.com, @google.com), company, or role..."
                  className="w-full glass-input rounded-xl pl-10 pr-9 py-2.5 text-xs text-white placeholder-slate-500 font-medium"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    className="absolute right-3 text-slate-400 hover:text-white p-0.5 rounded cursor-pointer transition"
                    title="Clear search"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              {/* Email Only Filter Chip */}
              <button
                type="button"
                onClick={() => setEmailOnly(!emailOnly)}
                className={`flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl text-xs font-bold border transition cursor-pointer shrink-0 ${
                  emailOnly
                    ? 'bg-blue-600 border-blue-400/50 text-white shadow-lg shadow-blue-600/25'
                    : 'bg-[#050811]/80 hover:bg-white/[0.06] border-white/[0.08] text-slate-300'
                }`}
                title="Filter exclusively by recruiter email addresses"
              >
                <Mail size={13} className={emailOnly ? 'text-white' : 'text-blue-400'} />
                <span>Email Only</span>
              </button>

              {/* Live Filter Indicator */}
              {searchQuery && (
                <div className="flex items-center gap-2 text-xs text-slate-400 pl-1 shrink-0">
                  <span className="bg-[#050811] px-2.5 py-1.5 rounded-xl border border-white/[0.08] text-[11px] font-bold text-slate-300">
                    <strong className="text-blue-400">{totalFiltered}</strong> of {apps.length}
                  </span>
                  <button
                    type="button"
                    onClick={() => { setSearchQuery(''); setEmailOnly(false); }}
                    className="text-xs text-slate-400 hover:text-white underline cursor-pointer font-semibold"
                  >
                    Reset
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Global Empty Search State */}
          {searchQuery && totalFiltered === 0 && (
            <div className="mb-6 p-8 text-center glass-panel rounded-3xl max-w-md mx-auto space-y-3">
              <div className="w-11 h-11 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto">
                <Mail size={20} />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-extrabold text-white">No applications match "{searchQuery}"</p>
                <p className="text-xs text-slate-400">
                  {emailOnly ? 'No sent emails or recruiter contacts match this email query.' : 'Try checking the spelling or unchecking "Email Only".'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => { setSearchQuery(''); setEmailOnly(false); }}
                className="px-4 py-2 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.1] text-white rounded-xl text-xs font-bold transition cursor-pointer"
              >
                Clear Search Query
              </button>
            </div>
          )}

          {/* 7-Column Glass Kanban Board */}
          <div className="flex gap-4 overflow-x-auto pb-4 items-start">
            {COLUMNS.map((col, colIdx) => (
              <motion.div
                key={col.key}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 + colIdx * 0.05, duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
                className={`glass-panel border ${col.color} rounded-2xl p-3.5 w-[285px] min-w-[285px] shrink-0 max-h-[calc(100vh-270px)] min-h-[420px] relative overflow-hidden flex flex-col`}
              >
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${col.topBar}`} />
                <h3 className="font-extrabold text-xs uppercase tracking-wider mb-3 pt-1 flex items-center justify-between text-slate-200 shrink-0">
                  <span className="truncate">{col.label}</span>
                  <span className="text-slate-300 text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.08]">
                    {searchQuery ? `${byStatus(col.key).length}/${apps.filter(a => a.status === col.key).length}` : byStatus(col.key).length}
                  </span>
                </h3>

                <div className="space-y-2.5 flex-1 overflow-y-auto pr-1">
                  {byStatus(col.key).map((a, cardIdx) => (
                    <motion.div
                      key={a.id}
                      layout
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(cardIdx * 0.03, 0.2), duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                      whileHover={{ y: -3, scale: 1.01 }}
                      whileTap={{ scale: 0.99 }}
                      onClick={() => openThreadModal(a)}
                      className="glass-card hover:border-blue-500/50 rounded-xl p-3 transition cursor-pointer group relative"
                    >
                      {/* Header */}
                      <div className="flex items-start justify-between gap-1.5 mb-1">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-extrabold text-white truncate group-hover:text-blue-200 transition">{a.title}</p>
                          <p className="text-[11px] font-semibold text-blue-300/90 truncate">{a.company}</p>
                        </div>
                        {a.match_score > 0 && <ScoreBadge score={a.match_score} />}
                      </div>

                      {/* Primary Recruiter Email Pill */}
                      {(() => {
                        const primaryEmail = getPrimaryEmail(a)
                        if (!primaryEmail) return null
                        const allEmails = getAppEmails(a)
                        const extraCount = allEmails.length > 1 ? allEmails.length - 1 : 0
                        const qLower = searchQuery.trim().toLowerCase()
                        const isEmailMatched = qLower && (primaryEmail.toLowerCase().includes(qLower) || allEmails.some(em => em.includes(qLower)))
                        return (
                          <div 
                            onClick={(e) => { e.stopPropagation(); copyToClipboard(primaryEmail); }}
                            className={`mt-1.5 flex items-center justify-between gap-1.5 text-[10px] px-2 py-1 rounded-lg font-mono truncate transition cursor-pointer border ${
                              isEmailMatched
                                ? 'bg-blue-950/90 border-blue-500/80 text-blue-200 shadow-sm ring-1 ring-blue-500/50'
                                : 'bg-[#050811]/70 hover:bg-[#050811] border-white/[0.08] text-slate-300 hover:text-white'
                            }`}
                            title={`Recruiter Email: ${primaryEmail} (Click to copy)`}
                          >
                            <div className="flex items-center gap-1.5 truncate">
                              <Mail size={10} className="text-blue-400 shrink-0" />
                              <span className="truncate">{primaryEmail}</span>
                              {extraCount > 0 && (
                                <span className="text-[9px] bg-white/[0.06] text-slate-300 px-1 py-0.2 rounded font-sans shrink-0" title={`${allEmails.length} total contacts`}>
                                  +{extraCount}
                                </span>
                              )}
                            </div>
                            {copiedEmail === primaryEmail ? (
                              <span className="text-[9px] text-emerald-400 font-sans font-bold shrink-0">Copied!</span>
                            ) : (
                              <Copy size={10} className="shrink-0 text-slate-500 hover:text-slate-200 transition" />
                            )}
                          </div>
                        )
                      })()}

                      {/* Tailored CV badge */}
                      {a.tailored_cv_filename && (
                        <div 
                          onClick={(e) => { e.stopPropagation(); handleDownloadCv(a.id, a.tailored_cv_filename); }}
                          className="mt-1.5 flex items-center justify-between gap-1 text-[10px] text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/25 px-2 py-0.5 rounded-lg font-mono truncate transition cursor-pointer" 
                          title={`Click to download ${a.tailored_cv_filename}`}
                        >
                          <div className="flex items-center gap-1 truncate">
                            <FileText size={10} className="shrink-0 text-emerald-400" />
                            <span className="truncate">{a.tailored_cv_filename}</span>
                          </div>
                          <Download size={10} className="shrink-0 opacity-70 group-hover:opacity-100" />
                        </div>
                      )}

                      {/* Notes preview & Recruiter Response highlight */}
                      {a.notes && (
                        <div className="mt-1.5">
                          {a.notes.includes('📥 Recruiter Reply') ? (
                            <div className="bg-purple-500/15 border border-purple-500/35 rounded-lg p-2 my-1 text-[10px] text-purple-200">
                              <div className="flex items-center gap-1 text-purple-300 font-extrabold mb-0.5">
                                <Sparkles size={10} className="text-purple-400 shrink-0" />
                                <span>Recruiter Response:</span>
                              </div>
                              <p className="line-clamp-2 italic text-slate-200">
                                {a.notes.split('📥 Recruiter Reply:').slice(-1)[0].replace(/^[^"]*"|"[^"]*$/g, '').trim()}
                              </p>
                            </div>
                          ) : (
                            <p className="text-[11px] text-slate-400 italic line-clamp-2">{a.notes}</p>
                          )}
                        </div>
                      )}

                      {/* Official Portal / Position Quick Link */}
                      {(() => {
                        const portalLink = getPortalLink(a)
                        if (portalLink && (a.status === 'review' || a.notes?.includes('Portal / Position Link:'))) {
                          return (
                            <a
                              href={portalLink}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              className="mt-2 flex items-center justify-center gap-1.5 w-full bg-blue-500/15 hover:bg-blue-500/25 text-blue-300 border border-blue-500/30 rounded-lg py-1 px-2 text-[11px] font-bold transition"
                              title="Open official career site / position link to complete application"
                            >
                              <ExternalLink size={11} className="shrink-0 text-blue-400" />
                              <span>Apply on Official Site</span>
                            </a>
                          )
                        }
                        return null
                      })()}

                      {/* Google Meet / Video Interview Call Quick Link */}
                      {(() => {
                        const meetLink = getMeetLink(a)
                        if (meetLink || a.status === 'interview') {
                          const targetUrl = meetLink || (a.notes?.match(/meet\.google\.com\/[^\s<>"'\)]+/i) ? `https://${a.notes.match(/meet\.google\.com\/[^\s<>"'\)]+/i)[0]}` : null)
                          if (targetUrl) {
                            return (
                              <a
                                href={targetUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={e => e.stopPropagation()}
                                className="mt-2 flex items-center justify-center gap-1.5 w-full bg-gradient-to-r from-emerald-600/30 to-teal-600/30 hover:from-emerald-600/50 hover:to-teal-600/50 text-emerald-200 hover:text-white border border-emerald-500/40 rounded-lg py-1.5 px-2.5 text-[11px] font-extrabold transition"
                                title="Join Google Meet Video Interview"
                              >
                                <Video size={12} className="shrink-0 text-emerald-400" />
                                <span>📹 Join Google Meet</span>
                              </a>
                            )
                          }
                        }
                        return null
                      })()}

                      {/* Quick Thread & AI Interview Prep bar */}
                      <div className="mt-2 pt-1.5 border-t border-white/[0.05] flex items-center justify-between gap-2 text-[10px] text-blue-400 group-hover:text-blue-300 font-bold transition">
                        <span className="flex items-center gap-1 truncate">
                          <MessageSquare size={10} />
                          <span>Thread ({a.emails?.length || 0})</span>
                        </span>
                        <button
                          type="button"
                          onClick={e => {
                            e.stopPropagation()
                            setPrepApp(a)
                          }}
                          className="px-2 py-0.5 rounded-md bg-purple-500/15 hover:bg-purple-500/30 border border-purple-500/30 text-purple-300 hover:text-white text-[10px] font-extrabold flex items-center gap-1 transition cursor-pointer shrink-0"
                          title="Generate tailored AI Interview Prep Q&A, STAR stories & salary script"
                        >
                          <Sparkles size={9} className="text-amber-400" />
                          <span>Interview Prep</span>
                        </button>
                      </div>

                      {/* Follow-up trigger button for Applied cards */}
                      {col.key === 'applied' && !a.notes?.includes('📥 Recruiter Reply') && (
                        <div className="mt-1.5 pt-1.5 border-t border-white/[0.05] flex items-center justify-between gap-1">
                          {(() => {
                            const daysWaiting = Math.floor((new Date() - new Date(a.applied_at || Date.now())) / (1000 * 60 * 60 * 24))
                            const isWaitingLong = daysWaiting >= 3
                            return (
                              <>
                                <span className={`text-[10px] flex items-center gap-1 font-semibold ${isWaitingLong ? 'text-amber-400' : 'text-slate-400'}`}>
                                  <Clock size={10} />
                                  {daysWaiting === 0 ? 'Applied today' : `${daysWaiting}d waiting`}
                                </span>
                                <button
                                  onClick={(e) => { e.stopPropagation(); openFollowUpModal(a); }}
                                  className={`flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md transition cursor-pointer ${
                                    isWaitingLong
                                      ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40'
                                      : 'bg-white/[0.05] hover:bg-white/[0.1] text-slate-300 border border-white/[0.08]'
                                  }`}
                                  title="Send a polite follow-up email to the recruiter"
                                >
                                  <Send size={9} />
                                  <span>Follow Up</span>
                                </button>
                              </>
                            )
                          })()}
                        </div>
                      )}

                      {/* Queued badge for Saved / Quota cards */}
                      {col.key === 'saved' && (
                        <div className="mt-1.5 pt-1.5 border-t border-white/[0.05] flex items-center justify-between">
                          <span className="text-[10px] flex items-center gap-1 font-bold text-amber-400">
                            <Clock size={10} />
                            Queued (Quota Resets Daily)
                          </span>
                        </div>
                      )}

                      {/* Action buttons & minimal footer */}
                      <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-white/[0.05] text-xs">
                        <div className="flex items-center gap-2.5">
                          {a.url && (
                            <a 
                              href={a.url} 
                              target="_blank" 
                              rel="noopener noreferrer" 
                              onClick={e => e.stopPropagation()} 
                              className="text-slate-400 hover:text-blue-300 transition"
                              title="Original Job Link"
                            >
                              <ExternalLink size={12} />
                            </a>
                          )}
                          <button 
                            onClick={(e) => { e.stopPropagation(); setEditing(a.id); setNotes(a.notes || ''); }} 
                            className="text-slate-400 hover:text-white transition cursor-pointer"
                            title="Edit Notes"
                          >
                            <StickyNote size={12} />
                          </button>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <button 
                            onClick={(e) => { e.stopPropagation(); del(a.id); }} 
                            className="opacity-40 group-hover:opacity-100 text-slate-500 hover:text-rose-400 transition cursor-pointer p-0.5"
                            title="Delete Application"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  ))}

                  {searchQuery && byStatus(col.key).length === 0 && (
                    <div className="py-8 text-center text-slate-500 text-xs italic border border-dashed border-white/[0.08] rounded-xl px-2">
                      No matching applications
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </main>

        {/* Add Modal */}
        <AnimatePresence>
          {adding && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-end md:items-center justify-center md:p-4"
              onClick={() => setAdding(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 12 }}
                className="glass-dropdown rounded-t-3xl md:rounded-3xl p-6 w-full md:max-w-md relative overflow-hidden"
                onClick={e => e.stopPropagation()}
              >
                <div className="glow-line-top" />
                <h3 className="font-extrabold text-lg text-white mb-4">Add Application Manually</h3>
                <div className="space-y-3">
                  {[['Job Title *','title'],['Company','company'],['Location','location'],['Job URL','url']].map(([label,key]) => (
                    <div key={key}>
                      <label className="text-xs font-bold text-slate-300 mb-1 block">{label}</label>
                      <input
                        value={form[key]}
                        onChange={e => setForm({ ...form, [key]: e.target.value })}
                        className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
                      />
                    </div>
                  ))}
                  <div>
                    <label className="text-xs font-bold text-slate-300 mb-1 block">Notes</label>
                    <textarea
                      value={form.notes}
                      onChange={e => setForm({ ...form, notes: e.target.value })}
                      rows={3}
                      className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm resize-none"
                    />
                  </div>
                  <div className="flex gap-2.5 pt-2">
                    <button onClick={() => setAdding(false)} className="flex-1 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] py-2.5 rounded-xl text-xs font-bold transition cursor-pointer">
                      Cancel
                    </button>
                    <button onClick={addApp} className="shimmer-btn flex-1 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 py-2.5 rounded-xl text-xs font-extrabold transition cursor-pointer">
                      Add Application
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Notes Modal */}
        <AnimatePresence>
          {editing && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-end md:items-center justify-center md:p-4"
              onClick={() => setEditing(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 12 }}
                className="glass-dropdown rounded-3xl p-6 w-full max-w-sm relative overflow-hidden"
                onClick={e => e.stopPropagation()}
              >
                <div className="glow-line-top" />
                <h3 className="font-extrabold text-base text-white mb-3">📝 Application Notes</h3>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  rows={5}
                  className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm resize-none mb-3"
                />
                <div className="flex gap-2">
                  <button onClick={() => setEditing(null)} className="flex-1 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] py-2.5 rounded-xl text-xs font-bold transition cursor-pointer">
                    Cancel
                  </button>
                  <button onClick={saveNotes} className="shimmer-btn flex-1 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 py-2.5 rounded-xl text-xs font-extrabold transition cursor-pointer">
                    Save Notes
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Single Follow-Up Modal */}
        <AnimatePresence>
          {followUpModal && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-end md:items-center justify-center md:p-4"
              onClick={() => !sendingFollowUp && setFollowUpModal(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 12 }}
                className="glass-dropdown rounded-t-3xl md:rounded-3xl p-6 w-full md:max-w-lg max-h-[90vh] overflow-y-auto relative"
                onClick={e => e.stopPropagation()}
              >
                <div className="glow-line-top" />
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="p-1.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
                        <Send size={15} />
                      </span>
                      <h3 className="font-extrabold text-base text-white">Send Follow-Up to Recruiter</h3>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      {followUpModal.title} · <strong className="text-slate-200">{followUpModal.company}</strong>
                    </p>
                  </div>
                  <button onClick={() => !sendingFollowUp && setFollowUpModal(null)} className="text-slate-400 hover:text-white transition">✕</button>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="text-xs font-bold text-slate-300 mb-1 block">To Recruiter(s)</label>
                    <div className="glass-input rounded-xl px-3 py-2 text-xs text-slate-300 font-mono flex flex-wrap gap-1.5">
                      {followUpForm.recipients?.length > 0 ? (
                        followUpForm.recipients.map(r => (
                          <span key={r.email} className="bg-blue-500/15 border border-blue-500/30 rounded-lg px-2 py-0.5 text-blue-300">
                            {r.name && r.name !== 'Hiring Team' ? `${r.name} <${r.email}>` : r.email}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-400 italic">Dispatches to verified recruiter inbox from prior email log</span>
                      )}
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-bold text-slate-300 mb-1 block">Subject Line</label>
                    <input
                      value={followUpForm.custom_subject}
                      onChange={e => setFollowUpForm({ ...followUpForm, custom_subject: e.target.value })}
                      className="w-full glass-input rounded-xl px-3.5 py-2 text-xs text-slate-200"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-slate-300 mb-1 block">Polite Follow-up Message</label>
                    <textarea
                      value={followUpForm.custom_body}
                      onChange={e => setFollowUpForm({ ...followUpForm, custom_body: e.target.value })}
                      rows={8}
                      className="w-full glass-input rounded-xl p-3 text-xs resize-none text-slate-200 leading-relaxed font-sans"
                    />
                  </div>

                  <div className="flex items-center gap-2 pt-1">
                    <input
                      type="checkbox"
                      id="attach_cv_single"
                      checked={followUpForm.attach_cv}
                      onChange={e => setFollowUpForm({ ...followUpForm, attach_cv: e.target.checked })}
                      className="rounded border-slate-700 text-amber-500 focus:ring-amber-500 h-4 w-4 bg-slate-900 cursor-pointer"
                    />
                    <label htmlFor="attach_cv_single" className="text-xs text-slate-300 cursor-pointer select-none font-medium">
                      📎 Re-attach tailored resume / CV (PDF)
                    </label>
                  </div>

                  <div className="flex gap-2.5 pt-3">
                    <button
                      onClick={() => setFollowUpModal(null)}
                      disabled={sendingFollowUp}
                      className="flex-1 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] disabled:opacity-50 py-2.5 rounded-xl text-xs font-bold transition cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSendFollowUp}
                      disabled={sendingFollowUp}
                      className="shimmer-btn flex-1 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 disabled:opacity-50 text-slate-950 font-extrabold py-2.5 rounded-xl text-xs shadow-lg transition flex items-center justify-center gap-1.5 cursor-pointer"
                    >
                      {sendingFollowUp ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                      <span>{sendingFollowUp ? 'Sending Follow-up...' : 'Send Follow-up Email'}</span>
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Batch Follow-Up Modal */}
        <AnimatePresence>
          {batchFollowUpOpen && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
              onClick={() => !sendingFollowUp && setBatchFollowUpOpen(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 12 }}
                className="glass-dropdown rounded-3xl p-6 w-full max-w-xl max-h-[85vh] flex flex-col relative overflow-hidden"
                onClick={e => e.stopPropagation()}
              >
                <div className="glow-line-top" />
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="font-extrabold text-lg text-white flex items-center gap-2">
                      <Clock className="text-amber-400" size={18} />
                      Recruiter Follow-Up Assistant
                    </h3>
                    <p className="text-xs text-slate-400 mt-1">
                      Select applications awaiting recruiter response to dispatch polite follow-ups.
                    </p>
                  </div>
                  <button onClick={() => !sendingFollowUp && setBatchFollowUpOpen(false)} className="text-slate-400 hover:text-white transition">✕</button>
                </div>

                <div className="flex items-center justify-between py-2 px-1 text-xs border-b border-white/[0.08]">
                  <span className="text-slate-400 font-semibold">
                    {selectedBatchIds.length} of {followUpCandidates.length} selected
                  </span>
                  <button
                    onClick={() => {
                      if (selectedBatchIds.length === followUpCandidates.length) setSelectedBatchIds([])
                      else setSelectedBatchIds(followUpCandidates.map(c => c.application_id))
                    }}
                    className="text-xs text-amber-400 hover:text-amber-300 transition cursor-pointer font-bold"
                  >
                    {selectedBatchIds.length === followUpCandidates.length ? 'Deselect All' : 'Select All'}
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto space-y-1.5 my-2.5 pr-1">
                  {followUpCandidates.map(cand => {
                    const isSelected = selectedBatchIds.includes(cand.application_id)
                    return (
                      <div
                        key={cand.application_id}
                        onClick={() => {
                          if (isSelected) setSelectedBatchIds(selectedBatchIds.filter(id => id !== cand.application_id))
                          else setSelectedBatchIds([...selectedBatchIds, cand.application_id])
                        }}
                        className={`p-3 rounded-xl flex items-center justify-between gap-3 cursor-pointer transition border ${
                          isSelected ? 'bg-amber-500/10 border-amber-500/35' : 'bg-white/[0.02] border-white/[0.05] hover:bg-white/[0.05]'
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="text-amber-400 shrink-0">
                            {isSelected ? <CheckSquare size={16} /> : <Square size={16} className="text-slate-500" />}
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-extrabold text-white truncate">{cand.title}</p>
                            <p className="text-[11px] font-semibold text-blue-300 truncate">{cand.company}</p>
                            <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-400">
                              <span>Waiting {cand.days_waiting} days</span>
                              <span>•</span>
                              <span>{cand.recipients?.length || 1} recipient(s)</span>
                              {cand.follow_up_count > 0 && (
                                <span className="text-amber-400">({cand.follow_up_count} prior follow-up)</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>

                <div className="pt-3 border-t border-white/[0.08] flex gap-2.5">
                  <button
                    onClick={() => setBatchFollowUpOpen(false)}
                    disabled={sendingFollowUp}
                    className="flex-1 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] disabled:opacity-50 py-2.5 rounded-xl text-xs font-bold transition cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSendBatchFollowUp}
                    disabled={sendingFollowUp || selectedBatchIds.length === 0}
                    className="shimmer-btn flex-1 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 disabled:opacity-50 text-slate-950 font-extrabold py-2.5 rounded-xl text-xs shadow-lg transition flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    {sendingFollowUp ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                    <span>{sendingFollowUp ? 'Sending Follow-ups...' : `Send Follow-ups (${selectedBatchIds.length})`}</span>
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Interactive Email Thread & Recruiter Communications Modal */}
        <AnimatePresence>
          {threadModal && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-3 md:p-6" 
              onClick={() => setThreadModal(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.96, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96, y: 12 }}
                className="glass-dropdown rounded-3xl w-full max-w-3xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden relative" 
                onClick={e => e.stopPropagation()}
              >
                <div className="glow-line-top" />
                {/* Modal Header */}
                <div className="p-5 border-b border-white/[0.07] bg-[#050811]/70 flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                        COLUMNS.find(c => c.key === (threadData?.application?.status || threadModal.status))?.color || 'border-slate-600'
                      } bg-white/[0.04] text-slate-200`}>
                        {COLUMNS.find(c => c.key === (threadData?.application?.status || threadModal.status))?.label || threadModal.status}
                      </span>
                      {(threadData?.application?.match_score || threadModal.match_score) > 0 && (
                        <ScoreBadge score={threadData?.application?.match_score || threadModal.match_score} />
                      )}
                      {threadData?.sent_count > 0 && (
                        <span className="text-[11px] text-blue-300 bg-blue-500/15 border border-blue-500/30 px-2.5 py-0.5 rounded-full font-bold">
                          {threadData.sent_count} email{threadData.sent_count > 1 ? 's' : ''} sent
                        </span>
                      )}
                      {threadData?.received_count > 0 && (
                        <span className="text-[11px] text-purple-300 bg-purple-500/15 border border-purple-500/30 px-2.5 py-0.5 rounded-full font-extrabold">
                          {threadData.received_count} reply received
                        </span>
                      )}
                    </div>
                    <h2 className="text-lg md:text-xl font-extrabold text-white truncate">
                      {threadData?.application?.title || threadModal.title}
                    </h2>
                    <div className="flex items-center gap-3 text-xs text-slate-400 mt-1 flex-wrap">
                      <span className="text-blue-300 font-bold flex items-center gap-1">
                        <Building2 size={13} className="text-blue-400" />
                        {threadData?.application?.company || threadModal.company}
                      </span>
                      {(threadData?.application?.location || threadModal.location) && (
                        <span className="flex items-center gap-1">
                          <MapPin size={13} className="text-slate-500" />
                          {threadData?.application?.location || threadModal.location}
                        </span>
                      )}
                    </div>
                  </div>

                  <button 
                    onClick={() => setThreadModal(null)} 
                    className="w-8 h-8 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-slate-400 hover:text-white flex items-center justify-center transition shrink-0 cursor-pointer"
                    title="Close"
                  >
                    ✕
                  </button>
                </div>

                {/* Quick Action Toolbar */}
                <div className="px-5 py-3 bg-[#070C1A] border-b border-white/[0.07] flex items-center justify-between gap-3 flex-wrap text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    {(threadData?.application?.has_tailored_cv || threadModal.tailored_cv_filename) && (
                      <button
                        onClick={() => handleDownloadCv(
                          threadData?.application?.id || threadModal.id, 
                          threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename
                        )}
                        className="flex items-center gap-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/35 px-3 py-1.5 rounded-xl font-mono text-[11px] font-bold transition cursor-pointer"
                        title="Download tailored resume PDF generated for this role"
                      >
                        <FileText size={12} className="text-emerald-400" />
                        <span className="truncate max-w-[200px]">{threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename || 'Tailored_CV.pdf'}</span>
                        <Download size={11} className="ml-0.5 opacity-70" />
                      </button>
                    )}

                    {(threadData?.application?.discovered_emails || []).map(em => (
                      <button
                        key={em}
                        onClick={() => copyToClipboard(em)}
                        className="flex items-center gap-1 bg-white/[0.04] hover:bg-white/[0.08] text-blue-300 border border-white/[0.08] px-2.5 py-1 rounded-lg text-[11px] transition cursor-pointer font-mono"
                        title="Click to copy email address"
                      >
                        <Mail size={11} className="text-blue-400" />
                        <span>{em}</span>
                        {copiedEmail === em ? <Check size={11} className="text-emerald-400 ml-0.5" /> : <Copy size={11} className="opacity-50 ml-0.5" />}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-2">
                    {(threadData?.application?.meet_url || getMeetLink(threadModal)) && (
                      <a
                        href={threadData?.application?.meet_url || getMeetLink(threadModal)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold px-3 py-1.5 rounded-xl text-xs shadow transition border border-emerald-400/40"
                        title="Open Google Meet video call"
                      >
                        <Video size={13} />
                        <span>📹 Join Google Meet</span>
                      </a>
                    )}

                    {(threadData?.application?.portal_url || getPortalLink(threadModal)) && (
                      <a
                        href={threadData?.application?.portal_url || getPortalLink(threadModal)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 bg-blue-500/15 hover:bg-blue-500/25 text-blue-300 border border-blue-500/30 px-2.5 py-1.5 rounded-xl font-bold transition"
                      >
                        <ExternalLink size={12} />
                        <span>Career Portal</span>
                      </a>
                    )}

                    <button
                      onClick={() => {
                        const target = threadData?.application || threadModal
                        setThreadModal(null)
                        openFollowUpModal(target)
                      }}
                      className="flex items-center gap-1.5 bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/35 px-2.5 py-1.5 rounded-xl font-bold text-xs transition cursor-pointer"
                      title="Compose and send a follow-up email"
                    >
                      <Send size={11} />
                      <span>Follow Up</span>
                    </button>
                  </div>
                </div>

                {/* Conversation Thread Body */}
                <div className="flex-1 overflow-y-auto p-5 space-y-4">
                  {loadingThread ? (
                    <div className="py-16 flex flex-col items-center justify-center text-slate-400 gap-3">
                      <Loader2 size={28} className="animate-spin text-blue-400" />
                      <p className="text-sm font-bold">Loading email thread &amp; correspondence...</p>
                    </div>
                  ) : threadData?.thread?.length > 0 ? (
                    <div className="space-y-4">
                      {threadData.thread.map((msg, idx) => (
                        <div 
                          key={idx} 
                          className={`rounded-2xl border p-4 transition ${
                            msg.direction === 'inbound'
                              ? 'bg-purple-950/30 border-purple-500/40 shadow-lg'
                              : 'glass-card'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3 mb-2.5 flex-wrap">
                            <div className="flex items-center gap-2.5">
                              {msg.direction === 'inbound' ? (
                                <span className="p-1.5 rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                  <Inbox size={15} />
                                </span>
                              ) : (
                                <span className="p-1.5 rounded-xl bg-blue-500/20 text-blue-300 border border-blue-500/30">
                                  <Send size={15} />
                                </span>
                              )}

                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="font-extrabold text-sm text-white">
                                    {msg.direction === 'inbound' ? 'Recruiter Response' : 'Outbound Application Email'}
                                  </span>
                                  {msg.direction === 'inbound' ? (
                                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-purple-500/20 text-purple-200 border-purple-500/40">
                                      {msg.status_outcome ? msg.status_outcome.toUpperCase() : 'REPLY'}
                                    </span>
                                  ) : (
                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 ${
                                      msg.status === 'sent'
                                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35'
                                        : 'bg-rose-500/15 text-rose-300 border-rose-500/35'
                                    }`}>
                                      {msg.status === 'sent' ? <CheckCircle size={10} /> : <XCircle size={10} />}
                                      {msg.status === 'sent' ? 'Delivered' : msg.status}
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-400 font-mono mt-0.5">
                                  {msg.direction === 'inbound' ? (
                                    <span>From: <strong className="text-slate-200">{msg.from_header}</strong></span>
                                  ) : (
                                    <span>To: <strong className="text-slate-200">{msg.to_name ? `${msg.to_name} <${msg.to_email}>` : msg.to_email}</strong></span>
                                  )}
                                </p>
                              </div>
                            </div>

                            <span className="text-xs text-slate-500 flex items-center gap-1 font-mono">
                              <Clock size={11} />
                              {msg.timestamp}
                            </span>
                          </div>

                          <div className="mb-2.5 pb-2 border-b border-white/[0.06] flex items-baseline gap-1.5">
                            <span className="text-xs text-slate-400 font-semibold">Subject:</span>
                            <span className="text-xs font-bold text-white">{msg.subject}</span>
                          </div>

                          <div className={`p-4 rounded-xl text-xs leading-relaxed select-text whitespace-pre-wrap ${
                            msg.direction === 'inbound'
                              ? 'bg-[#050811]/85 border border-purple-500/25 text-purple-100 font-sans italic'
                              : 'bg-[#050811]/70 border border-white/[0.06] text-slate-200 font-sans'
                          }`}>
                            {msg.body || '(No body content recorded)'}
                          </div>

                          {msg.direction === 'outbound' && (threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename) && (
                            <div className="mt-2.5 flex items-center gap-2 text-xs text-slate-400">
                              <Paperclip size={12} className="text-emerald-400" />
                              <span>Attached: <span className="font-mono text-emerald-300 font-semibold">{threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename}</span></span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-12 px-6 rounded-2xl bg-[#050811]/60 border border-white/[0.07] text-center">
                      <div className="max-w-md mx-auto space-y-3">
                        <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400 mx-auto">
                          <Mail size={24} />
                        </div>
                        <h4 className="font-extrabold text-white text-base">
                          {threadModal.status === 'saved' ? 'Application Queued in Pipeline' : 'No Emails Dispatched Yet'}
                        </h4>
                        <p className="text-xs text-slate-400 leading-relaxed">
                          {threadModal.status === 'saved'
                            ? 'This application is queued in your pipeline and will be dispatched automatically when your daily Gmail quota resets.'
                            : 'No automated emails have been logged for this application yet. You can dispatch a follow-up at any time.'}
                        </p>
                      </div>
                    </div>
                  )}

                  {(threadData?.application?.notes || threadModal.notes) && (
                    <div className="mt-4 p-4 rounded-2xl bg-[#050811]/60 border border-white/[0.07]">
                      <h4 className="text-xs font-extrabold text-slate-200 mb-2 flex items-center gap-1.5">
                        <StickyNote size={13} className="text-blue-400" />
                        <span>Application Notes &amp; Activity History</span>
                      </h4>
                      <div className="text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed bg-[#050811]/90 p-3 rounded-xl border border-white/[0.05] select-text max-h-36 overflow-y-auto">
                        {threadData?.application?.notes || threadModal.notes}
                      </div>
                    </div>
                  )}
                </div>

                {/* Modal Footer */}
                <div className="p-4 border-t border-white/[0.07] bg-[#050811]/80 flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs text-slate-400 mr-1 font-bold">Move Stage:</span>
                    {COLUMNS.filter(c => c.key !== (threadData?.application?.status || threadModal.status)).map(c => (
                      <button
                        key={c.key}
                        onClick={() => {
                          moveStatus(threadModal.id, c.key)
                          setThreadModal(prev => prev ? { ...prev, status: c.key } : null)
                          if (threadData?.application) {
                            setThreadData(prev => prev ? { ...prev, application: { ...prev.application, status: c.key } } : null)
                          }
                        }}
                        className="text-xs bg-white/[0.04] hover:bg-white/[0.1] text-slate-300 hover:text-white border border-white/[0.08] px-2.5 py-1 rounded-xl font-semibold transition cursor-pointer"
                      >
                        → {c.shortLabel}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const target = threadData?.application || threadModal
                        setThreadModal(null)
                        setPrepApp(target)
                      }}
                      className="bg-purple-600/20 hover:bg-purple-600 border border-purple-500/35 text-purple-200 hover:text-white text-xs font-bold px-3.5 py-2 rounded-xl flex items-center gap-1.5 transition cursor-pointer"
                    >
                      <Sparkles size={13} className="text-amber-400" />
                      <span>AI Interview Prep</span>
                    </button>
                    <button
                      onClick={() => setThreadModal(null)}
                      className="bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] text-white text-xs font-bold px-4 py-2 rounded-xl transition cursor-pointer"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <InterviewPrepModal
          isOpen={Boolean(prepApp)}
          onClose={() => setPrepApp(null)}
          application={prepApp}
        />
      </div>
    </PageWrapper>
  )
}
