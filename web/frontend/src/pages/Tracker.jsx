import { useEffect, useState, useMemo } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import client from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { 
  Plus, Trash2, ExternalLink, StickyNote, Mail, CheckCircle, XCircle, ChevronDown, 
  Calendar, Download, ShieldAlert, RefreshCw, Loader2, Sparkles, Inbox, Clock, 
  Send, CheckSquare, Square, FileText, MessageSquare, Building2, MapPin, 
  Check, Copy, Paperclip, AlertCircle, Search, X, Filter, Video
} from 'lucide-react'

const COLUMNS = [
  { key:'saved',     label:'💾 Saved / Queue', color:'border-slate-600'  },
  { key:'applied',   label:'📤 Sent / Applied',color:'border-blue-700'   },
  { key:'review',    label:'👀 Under Review',  color:'border-amber-700'  },
  { key:'interview', label:'📞 Interview',     color:'border-purple-700' },
  { key:'offer',     label:'🤝 Offer',         color:'border-emerald-700'},
  { key:'rejected',  label:'❌ Rejected',      color:'border-red-700'    },
  { key:'accepted',  label:'🏆 Accepted',      color:'border-yellow-700' },
]

function EmailBadge({ email }) {

  const exportCsv = () => {
    const token = localStorage.getItem('token')
    const a = document.createElement('a')
    a.href = `${import.meta.env.VITE_API_URL || ''}/api/tracker/export?token=${token}`
    // Use fetch with auth header instead
    fetch('/api/tracker/export', { headers: { Authorization: `Bearer ${token}` }})
      .then(r => r.blob())
      .then(blob => {
        a.href = URL.createObjectURL(blob)
        a.download = 'applications.csv'
        a.click()
      })
  }

  return (
    <div className="flex items-center gap-1 text-xs text-slate-400 mt-1">
      {email.status==='sent'
        ? <CheckCircle size={10} className="text-emerald-400 shrink-0"/>
        : <XCircle size={10} className="text-red-400 shrink-0"/>}
      <span className="truncate" title={email.subject}>{email.subject}</span>
    </div>
  )
}

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

  // 1. Check emails (from email logs or notes)
  const hasEmailMatch = appEmails.some(em => em.includes(q))
  if (hasEmailMatch) return true

  // 2. Also check recipient name and email subject in logs
  if (Array.isArray(app.emails)) {
    const logMatch = app.emails.some(e => 
      (e.to_name && e.to_name.toLowerCase().includes(q)) ||
      (e.subject && e.subject.toLowerCase().includes(q))
    )
    if (logMatch) return true
  }

  // If in email-only mode, stop here
  if (emailOnly) return false

  // 3. Fallback to company, role title, location, notes
  if (app.company && app.company.toLowerCase().includes(q)) return true
  if (app.title && app.title.toLowerCase().includes(q)) return true
  if (app.location && app.location.toLowerCase().includes(q)) return true
  if (app.notes && app.notes.toLowerCase().includes(q)) return true

  return false
}

export default function Tracker() {
  const [apps, setApps]       = useState([])
  const [editing, setEditing] = useState(null)
  const [notes, setNotes]     = useState('')
  const [adding, setAdding]   = useState(false)
  const [form, setForm]       = useState({ title:'', company:'', location:'', url:'', notes:'' })
  const [expanded, setExpanded] = useState({})
  const [syncingMailbox, setSyncingMailbox] = useState(false)
  const [searchQuery, setSearchQuery]       = useState('')
  const [emailOnly, setEmailOnly]           = useState(false)

  // Interactive Conversation Thread Modal State
  const [threadModal, setThreadModal]     = useState(null)
  const [threadData, setThreadData]       = useState(null)
  const [loadingThread, setLoadingThread] = useState(false)
  const [copiedEmail, setCopiedEmail]     = useState(null)

  // Recruiter Follow-up State
  const [followUpCandidates, setFollowUpCandidates] = useState([])
  const [followUpModal, setFollowUpModal]           = useState(null)
  const [followUpForm, setFollowUpForm]             = useState({ custom_subject: '', custom_body: '', attach_cv: true, recipients: [] })
  const [sendingFollowUp, setSendingFollowUp]       = useState(false)
  const [batchFollowUpOpen, setBatchFollowUpOpen]   = useState(false)
  const [selectedBatchIds, setSelectedBatchIds]     = useState([])

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
  useEffect(()=>{ load() },[])

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
      const token = localStorage.getItem('token')
      const response = await fetch(`/api/tracker/${appId}/cv?token=${token}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!response.ok) throw new Error('Failed to download CV')
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
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
      const parts = []
      if (summary.replies_updated > 0) parts.push(`${summary.replies_updated} replies updated`)
      if (summary.follow_ups_sent > 0) parts.push(`${summary.follow_ups_sent} follow-ups sent`)
      if (summary.auto_rejected > 0) parts.push(`${summary.auto_rejected} auto-rejected (3d no reply)`)
      if (summary.saved_sent > 0) parts.push(`${summary.saved_sent} queued jobs dispatched`)
      if (summary.dead_purged > 0) parts.push(`${summary.dead_purged} dead bounces purged`)

      let msg = '✨ Mailbox Synced!'
      if (parts.length > 0) {
        msg += ` (${parts.join(', ')})`
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
    setApps(a => a.map(x => x.id===id ? {...x, status} : x))
  }

  const saveNotes = async () => {
    await client.patch(`/tracker/${editing}`, { notes })
    setApps(a => a.map(x => x.id===editing ? {...x, notes} : x))
    setEditing(null)
  }

  const del = async (id) => {
    await client.delete(`/tracker/${id}`)
    setApps(a => a.filter(x=>x.id!==id))
  }

  const filteredApps = useMemo(() => {
    return apps.filter(a => matchesAppSearch(a, searchQuery, emailOnly))
  }, [apps, searchQuery, emailOnly])

  const byStatus = key => filteredApps.filter(a=>a.status===key)
  const totalEmails = apps.reduce((sum,a)=>sum+(a.emails?.length||0),0)
  const totalFiltered = filteredApps.length

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar/>
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold">📋 Applications</h1>
            <div className="flex items-center gap-2 text-slate-400 text-xs mt-1">
              <span>{apps.length} applications</span>
              <span>·</span>
              <a 
                href="/email" 
                className="text-blue-400 hover:text-blue-300 transition flex items-center gap-1 font-medium"
                title="View full audit log of all sent emails"
              >
                <span>{totalEmails} emails sent</span>
                <ExternalLink size={11} />
              </a>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={handleSyncMailbox}
              disabled={syncingMailbox}
              title="1-Click Mailbox Sync: Purges dead/bounced emails from Sent box and syncs incoming recruiter replies"
              className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2 rounded-xl shadow-md shadow-blue-500/10 transition cursor-pointer"
            >
              {syncingMailbox ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              <span>{syncingMailbox ? 'Syncing Mailbox...' : '⚡ Sync Mailbox'}</span>
            </button>
            <button onClick={()=>setAdding(true)}
              className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold px-3.5 py-2 rounded-xl transition cursor-pointer">
              <Plus size={15}/> Add Manually
            </button>
          </div>
        </div>

        {/* Follow-up Assistant Alert Bar */}
        {followUpCandidates.length > 0 && (
          <div className="mb-5 bg-gradient-to-r from-amber-950/70 via-slate-800 to-amber-950/70 border border-amber-500/40 rounded-2xl p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg shadow-amber-950/20">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0">
                <Clock size={16} />
              </div>
              <div>
                <p className="text-sm font-bold text-amber-200">
                  ⚡ Follow-Up Assistant: {followUpCandidates.length} application{followUpCandidates.length > 1 ? 's' : ''} awaiting recruiter response (&gt;3 days)
                </p>
                <p className="text-xs text-amber-300/80">
                  Following up increases recruiter response rates. Review candidates and dispatch follow-ups in 1 click.
                </p>
              </div>
            </div>
            <button
              onClick={() => setBatchFollowUpOpen(true)}
              className="flex items-center gap-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs px-3.5 py-2 rounded-xl transition shadow cursor-pointer shrink-0"
            >
              <Send size={13} />
              <span>Review & Follow Up ({followUpCandidates.length})</span>
            </button>
          </div>
        )}

        {/* Stats */}
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
          {COLUMNS.map(c=>(
            <div key={c.key} className={`bg-slate-800 border ${c.color} rounded-xl px-4 py-3 text-center min-w-[90px]`}>
              <div className="text-xl font-bold">{byStatus(c.key).length}</div>
              <div className="text-xs text-slate-400">{c.label.split(' ').slice(1).join(' ')}</div>
            </div>
          ))}
          <div className="bg-slate-800 border border-blue-600 rounded-xl px-4 py-3 text-center min-w-[90px]">
            <div className="text-xl font-bold text-blue-400">{totalEmails}</div>
            <div className="text-xs text-slate-400">Emails Sent</div>
          </div>
        </div>

        {/* Search & Filter Bar: Email / Keyword filter */}
        <div className="mb-5 bg-slate-800/90 border border-slate-700/80 rounded-2xl p-2.5 sm:p-3 shadow-lg shadow-black/20 space-y-2">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            {/* Search Input */}
            <div className="relative flex-1 flex items-center">
              <Search size={16} className="absolute left-3.5 text-slate-400 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search by recruiter email (e.g. tiffany@adp.com, @google.com), company, or role..."
                className="w-full bg-slate-900 border border-slate-700 focus:border-blue-500 rounded-xl pl-10 pr-9 py-2 text-xs text-white placeholder-slate-500 focus:outline-none transition shadow-inner"
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
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer shrink-0 ${
                emailOnly
                  ? 'bg-blue-600 border-blue-500 text-white shadow-md shadow-blue-500/20'
                  : 'bg-slate-900 hover:bg-slate-800 border-slate-700 text-slate-300'
              }`}
              title="Filter exclusively by recruiter email addresses"
            >
              <Mail size={13} className={emailOnly ? 'text-white' : 'text-blue-400'} />
              <span>Email Only</span>
            </button>

            {/* Live Filter Indicator */}
            {searchQuery && (
              <div className="flex items-center gap-2 text-xs text-slate-400 pl-1 shrink-0">
                <span className="bg-slate-900 px-2.5 py-1.5 rounded-lg border border-slate-700 text-[11px] font-medium text-slate-300">
                  <strong className="text-blue-400">{totalFiltered}</strong> of {apps.length}
                </span>
                <button
                  type="button"
                  onClick={() => { setSearchQuery(''); setEmailOnly(false); }}
                  className="text-xs text-slate-400 hover:text-white underline cursor-pointer"
                >
                  Reset
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Global Empty Search State if no results */}
        {searchQuery && totalFiltered === 0 && (
          <div className="mb-6 p-8 text-center bg-slate-800/60 border border-slate-700/60 rounded-2xl max-w-md mx-auto shadow-xl space-y-3">
            <div className="w-11 h-11 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto">
              <Mail size={20} />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-bold text-white">No applications match "{searchQuery}"</p>
              <p className="text-xs text-slate-400">
                {emailOnly ? 'No sent emails or recruiter contacts match this email query.' : 'Try checking the spelling or unchecking "Email Only".'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => { setSearchQuery(''); setEmailOnly(false); }}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-xl text-xs font-semibold transition cursor-pointer shadow"
            >
              Clear Search Query
            </button>
          </div>
        )}

        {/* Kanban */}
        <div className="flex gap-4 overflow-x-auto pb-4 md:grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-7 md:overflow-visible">
          {COLUMNS.map(col=>(
            <div key={col.key} className={`bg-slate-800 border ${col.color} rounded-2xl p-4 min-h-[300px] min-w-[260px] md:min-w-0 shrink-0 md:shrink`}>
              <h3 className="font-semibold text-sm mb-3 flex items-center justify-between">
                <span>{col.label}</span>
                <span className="text-slate-500 text-xs font-normal">
                  {searchQuery ? `${byStatus(col.key).length}/${apps.filter(a=>a.status===col.key).length}` : `(${byStatus(col.key).length})`}
                </span>
              </h3>
              <div className="space-y-3">
                {byStatus(col.key).map(a=>(
                  <div 
                    key={a.id} 
                    onClick={() => openThreadModal(a)}
                    className="bg-slate-900 border border-slate-700 hover:border-blue-500/60 rounded-xl p-3 transition cursor-pointer group shadow-sm hover:shadow-md hover:shadow-blue-500/5 relative"
                  >
                    {/* Header */}
                    <div className="flex items-start justify-between mb-1">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate group-hover:text-blue-200 transition">{a.title}</p>
                        <p className="text-xs text-slate-400 truncate">{a.company}</p>
                      </div>
                      {a.match_score>0 && <ScoreBadge score={a.match_score}/>}
                    </div>

                    {/* Primary Recruiter Email Pill */}
                    {(() => {
                      const primaryEmail = getPrimaryEmail(a);
                      if (!primaryEmail) return null;
                      const allEmails = getAppEmails(a);
                      const extraCount = allEmails.length > 1 ? allEmails.length - 1 : 0;
                      const qLower = searchQuery.trim().toLowerCase();
                      const isEmailMatched = qLower && (primaryEmail.toLowerCase().includes(qLower) || allEmails.some(em => em.includes(qLower)));
                      return (
                        <div 
                          onClick={(e) => { e.stopPropagation(); copyToClipboard(primaryEmail); }}
                          className={`mt-1.5 flex items-center justify-between gap-1.5 text-[11px] px-2 py-1 rounded-lg font-mono truncate transition cursor-pointer border ${
                            isEmailMatched
                              ? 'bg-blue-950/90 border-blue-500/80 text-blue-200 shadow-sm ring-1 ring-blue-500/50'
                              : 'bg-slate-950/60 hover:bg-slate-800/90 border-slate-700/70 text-slate-300 hover:text-white'
                          }`}
                          title={`Recruiter Email: ${primaryEmail} (Click to copy)`}
                        >
                          <div className="flex items-center gap-1.5 truncate">
                            <Mail size={11} className={isEmailMatched ? 'text-blue-300 shrink-0' : 'text-blue-400 shrink-0'} />
                            <span className="truncate">{primaryEmail}</span>
                            {extraCount > 0 && (
                              <span className="text-[9px] bg-slate-800 text-slate-400 px-1 py-0.2 rounded font-sans shrink-0" title={`${allEmails.length} total contacts`}>
                                +{extraCount}
                              </span>
                            )}
                          </div>
                          {copiedEmail === primaryEmail ? (
                            <span className="text-[10px] text-emerald-400 font-sans font-semibold shrink-0">Copied!</span>
                          ) : (
                            <Copy size={11} className="shrink-0 text-slate-500 hover:text-slate-200 transition" />
                          )}
                        </div>
                      );
                    })()}

                    {/* Tailored CV badge */}
                    {a.tailored_cv_filename && (
                      <div 
                        onClick={(e) => { e.stopPropagation(); handleDownloadCv(a.id, a.tailored_cv_filename); }}
                        className="mt-1 flex items-center justify-between gap-1 text-[10px] text-emerald-400 bg-emerald-950/40 hover:bg-emerald-900/40 border border-emerald-800/40 px-2 py-0.5 rounded font-mono truncate transition cursor-pointer" 
                        title={`Click to download ${a.tailored_cv_filename}`}
                      >
                        <div className="flex items-center gap-1 truncate">
                          <FileText size={10} className="shrink-0 text-emerald-400" />
                          <span className="truncate">{a.tailored_cv_filename}</span>
                        </div>
                        <Download size={10} className="shrink-0 opacity-60 group-hover:opacity-100" />
                      </div>
                    )}

                    {/* Notes preview & Recruiter Response highlight */}
                    {a.notes && (
                      <div className="mt-1">
                        {a.notes.includes('📥 Recruiter Reply') ? (
                          <div className="bg-purple-950/70 border border-purple-800/80 rounded-lg p-2 my-1 text-[11px] text-purple-200 shadow-sm">
                            <div className="flex items-center gap-1 text-purple-300 font-bold mb-0.5">
                              <Sparkles size={11} className="text-purple-400 shrink-0" />
                              <span>Recruiter Response:</span>
                            </div>
                            <p className="line-clamp-2 italic text-slate-300">
                              {a.notes.split('📥 Recruiter Reply:').slice(-1)[0].replace(/^[^"]*"|"[^"]*$/g, '').trim()}
                            </p>
                          </div>
                        ) : (
                          <p className="text-xs text-slate-500 italic line-clamp-2">{a.notes}</p>
                        )}
                      </div>
                    )}

                    {/* Official Portal / Position Quick Link */}
                    {(() => {
                      const portalLink = getPortalLink(a);
                      if (portalLink && (a.status === 'review' || a.notes?.includes('Portal / Position Link:'))) {
                        return (
                          <a
                            href={portalLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            className="mt-2 flex items-center justify-center gap-1.5 w-full bg-blue-600/20 hover:bg-blue-600/35 text-blue-300 border border-blue-500/30 rounded-lg py-1 px-2 text-xs font-medium transition"
                            title="Open official career site / position link to complete application"
                          >
                            <ExternalLink size={12} className="shrink-0 text-blue-400" />
                            <span>Apply on Official Site</span>
                          </a>
                        );
                      }
                      return null;
                    })()}

                    {/* Google Meet / Video Interview Call Quick Link */}
                    {(() => {
                      const meetLink = getMeetLink(a);
                      if (meetLink || a.status === 'interview') {
                        const targetUrl = meetLink || (a.notes?.match(/meet\.google\.com\/[^\s<>"'\)]+/i) ? `https://${a.notes.match(/meet\.google\.com\/[^\s<>"'\)]+/i)[0]}` : null);
                        if (targetUrl) {
                          return (
                            <a
                              href={targetUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              className="mt-2 flex items-center justify-center gap-2 w-full bg-gradient-to-r from-emerald-600/30 to-teal-600/30 hover:from-emerald-600/50 hover:to-teal-600/50 text-emerald-300 hover:text-white border border-emerald-500/40 rounded-lg py-1.5 px-2.5 text-xs font-bold transition shadow-sm hover:shadow-emerald-500/20"
                              title="Join Google Meet Video Interview"
                            >
                              <Video size={13} className="shrink-0 text-emerald-400" />
                              <span>📹 Join Google Meet</span>
                            </a>
                          );
                        }
                      }
                      return null;
                    })()}

                    {/* Quick Thread / Conversation indicator */}
                    <div className="mt-2 pt-1.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-blue-400 group-hover:text-blue-300 font-medium transition">
                      <span className="flex items-center gap-1">
                        <MessageSquare size={11} />
                        <span>View Emails & Activity</span>
                      </span>
                      <span className="text-slate-500 text-[10px] font-normal">
                        {a.emails?.length || 0} sent {a.notes?.includes('📥 Recruiter Reply') ? '· 1 reply' : ''}
                      </span>
                    </div>

                    {/* Follow-up trigger button for Applied cards */}
                    {col.key === 'applied' && !a.notes?.includes('📥 Recruiter Reply') && (
                      <div className="mt-1.5 pt-1.5 border-t border-slate-800/60 flex items-center justify-between gap-1">
                        {(() => {
                          const daysWaiting = Math.floor((new Date() - new Date(a.applied_at || Date.now())) / (1000 * 60 * 60 * 24));
                          const isWaitingLong = daysWaiting >= 3;
                          return (
                            <>
                              <span className={`text-[10px] flex items-center gap-1 font-medium ${isWaitingLong ? 'text-amber-400' : 'text-slate-400'}`}>
                                <Clock size={11} />
                                {daysWaiting === 0 ? 'Applied today' : `${daysWaiting}d waiting`}
                              </span>
                              <button
                                onClick={(e) => { e.stopPropagation(); openFollowUpModal(a); }}
                                className={`flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded transition cursor-pointer ${
                                  isWaitingLong
                                    ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 shadow-sm'
                                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700'
                                }`}
                                title="Send a polite follow-up email to the recruiter"
                              >
                                <Send size={10} />
                                <span>Follow Up</span>
                              </button>
                            </>
                          );
                        })()}
                      </div>
                    )}

                    {/* Queued badge for Saved / Quota cards */}
                    {col.key === 'saved' && (
                      <div className="mt-1.5 pt-1.5 border-t border-slate-800/60 flex items-center justify-between">
                        <span className="text-[10px] flex items-center gap-1 font-semibold text-amber-400">
                          <Clock size={11} />
                          Queued (Quota Resets Daily)
                        </span>
                      </div>
                    )}

                    {/* Action buttons & minimal footer */}
                    <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-slate-800/60 text-xs">
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
                            <ExternalLink size={12}/>
                          </a>
                        )}
                        <button 
                          onClick={(e)=>{ e.stopPropagation(); setEditing(a.id); setNotes(a.notes||''); }} 
                          className="text-slate-400 hover:text-white transition cursor-pointer"
                          title="Edit Notes"
                        >
                          <StickyNote size={12}/>
                        </button>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button 
                          onClick={(e)=>{ e.stopPropagation(); del(a.id); }} 
                          className="opacity-40 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition cursor-pointer p-0.5"
                          title="Delete Application"
                        >
                          <Trash2 size={12}/>
                        </button>
                      </div>
                    </div>
                  </div>
                ))}

                {/* Subtle indicator when searching and column has 0 matches */}
                {searchQuery && byStatus(col.key).length === 0 && (
                  <div className="py-8 text-center text-slate-500 text-xs italic border border-dashed border-slate-700/60 rounded-xl px-2">
                    No matching applications in this stage
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Add Modal */}
      {adding && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-end md:items-center justify-center md:p-4" onClick={()=>setAdding(false)}>
          <div className="bg-slate-800 border border-slate-700 rounded-t-2xl md:rounded-2xl p-5 w-full md:max-w-md" onClick={e=>e.stopPropagation()}>
            <h3 className="font-bold text-lg mb-4">Add Application</h3>
            <div className="space-y-3">
              {[['Job Title *','title'],['Company','company'],['Location','location'],['Job URL','url']].map(([label,key])=>(
                <div key={key}>
                  <label className="text-xs text-slate-400 mb-1 block">{label}</label>
                  <input value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"/>
                </div>
              ))}
              <div>
                <label className="text-xs text-slate-400 mb-1 block">Notes</label>
                <textarea value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})} rows={3}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition resize-none"/>
              </div>
              <div className="flex gap-2 pt-2">
                <button onClick={()=>setAdding(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 py-2 rounded-lg text-sm transition">Cancel</button>
                <button onClick={addApp} className="flex-1 bg-blue-600 hover:bg-blue-500 py-2 rounded-lg text-sm font-semibold transition">Add</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Notes Modal */}
      {editing && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-end md:items-center justify-center md:p-4" onClick={()=>setEditing(null)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-sm" onClick={e=>e.stopPropagation()}>
            <h3 className="font-bold mb-3">📝 Notes</h3>
            <textarea value={notes} onChange={e=>setNotes(e.target.value)} rows={5}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition resize-none mb-3"/>
            <div className="flex gap-2">
              <button onClick={()=>setEditing(null)} className="flex-1 bg-slate-700 hover:bg-slate-600 py-2 rounded-lg text-sm transition">Cancel</button>
              <button onClick={saveNotes} className="flex-1 bg-blue-600 hover:bg-blue-500 py-2 rounded-lg text-sm font-semibold transition">Save</button>
            </div>
          </div>
        </div>
      )}

      {/* Single Follow-Up Modal */}
      {followUpModal && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-end md:items-center justify-center md:p-4" onClick={() => !sendingFollowUp && setFollowUpModal(null)}>
          <div className="bg-slate-800 border border-slate-700 rounded-t-2xl md:rounded-2xl p-5 md:p-6 w-full md:max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
                    <Send size={15} />
                  </span>
                  <h3 className="font-bold text-base text-slate-100">Send Follow-Up to Recruiter</h3>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {followUpModal.title} · <strong className="text-slate-300">{followUpModal.company}</strong>
                </p>
              </div>
              <button onClick={() => !sendingFollowUp && setFollowUpModal(null)} className="text-slate-400 hover:text-white transition">✕</button>
            </div>

            <div className="space-y-3.5">
              {/* Recipients indicator */}
              <div>
                <label className="text-xs text-slate-400 mb-1 block font-medium">To Recruiter(s)</label>
                <div className="bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-slate-300 font-mono flex flex-wrap gap-1.5">
                  {followUpForm.recipients?.length > 0 ? (
                    followUpForm.recipients.map(r => (
                      <span key={r.email} className="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-blue-300">
                        {r.name && r.name !== 'Hiring Team' ? `${r.name} <${r.email}>` : r.email}
                      </span>
                    ))
                  ) : (
                    <span className="text-slate-400 italic">Dispatches to verified recruiter inbox from prior email log</span>
                  )}
                </div>
              </div>

              {/* Subject */}
              <div>
                <label className="text-xs text-slate-400 mb-1 block font-medium">Subject Line</label>
                <input
                  value={followUpForm.custom_subject}
                  onChange={e => setFollowUpForm({ ...followUpForm, custom_subject: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2 text-xs focus:outline-none focus:border-amber-500 transition text-slate-200"
                />
              </div>

              {/* Message Body */}
              <div>
                <label className="text-xs text-slate-400 mb-1 block font-medium">Polite Follow-up Message</label>
                <textarea
                  value={followUpForm.custom_body}
                  onChange={e => setFollowUpForm({ ...followUpForm, custom_body: e.target.value })}
                  rows={8}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-xs focus:outline-none focus:border-amber-500 transition resize-none text-slate-200 leading-relaxed font-sans"
                />
              </div>

              {/* Attach CV option */}
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="attach_cv_single"
                  checked={followUpForm.attach_cv}
                  onChange={e => setFollowUpForm({ ...followUpForm, attach_cv: e.target.checked })}
                  className="rounded border-slate-700 text-amber-500 focus:ring-amber-500 h-4 w-4 bg-slate-900 cursor-pointer"
                />
                <label htmlFor="attach_cv_single" className="text-xs text-slate-300 cursor-pointer select-none">
                  📎 Re-attach tailored resume / CV (PDF)
                </label>
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-3">
                <button
                  onClick={() => setFollowUpModal(null)}
                  disabled={sendingFollowUp}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 py-2.5 rounded-xl text-xs font-semibold transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSendFollowUp}
                  disabled={sendingFollowUp}
                  className="flex-1 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-50 text-slate-950 font-bold py-2.5 rounded-xl text-xs shadow-md transition flex items-center justify-center gap-1.5 cursor-pointer"
                >
                  {sendingFollowUp ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                  <span>{sendingFollowUp ? 'Sending Follow-up...' : 'Send Follow-up Email'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Batch Follow-Up Modal */}
      {batchFollowUpOpen && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => !sendingFollowUp && setBatchFollowUpOpen(false)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2">
                  <Clock className="text-amber-400" size={18} />
                  Recruiter Follow-Up Assistant
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Select applications awaiting recruiter response to dispatch polite follow-ups.
                </p>
              </div>
              <button onClick={() => !sendingFollowUp && setBatchFollowUpOpen(false)} className="text-slate-400 hover:text-white transition">✕</button>
            </div>

            {/* List of candidates */}
            <div className="flex items-center justify-between py-2 px-1 text-xs border-b border-slate-700/80">
              <span className="text-slate-400 font-medium">
                {selectedBatchIds.length} of {followUpCandidates.length} selected
              </span>
              <button
                onClick={() => {
                  if (selectedBatchIds.length === followUpCandidates.length) setSelectedBatchIds([])
                  else setSelectedBatchIds(followUpCandidates.map(c => c.application_id))
                }}
                className="text-xs text-amber-400 hover:text-amber-300 transition cursor-pointer font-medium"
              >
                {selectedBatchIds.length === followUpCandidates.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto divide-y divide-slate-800 my-2 pr-1">
              {followUpCandidates.map(cand => {
                const isSelected = selectedBatchIds.includes(cand.application_id)
                return (
                  <div
                    key={cand.application_id}
                    onClick={() => {
                      if (isSelected) setSelectedBatchIds(selectedBatchIds.filter(id => id !== cand.application_id))
                      else setSelectedBatchIds([...selectedBatchIds, cand.application_id])
                    }}
                    className={`p-3 rounded-xl flex items-center justify-between gap-3 cursor-pointer transition ${
                      isSelected ? 'bg-slate-900/90 border border-amber-500/30' : 'hover:bg-slate-700/20'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="text-amber-400 shrink-0">
                        {isSelected ? <CheckSquare size={16} /> : <Square size={16} className="text-slate-500" />}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-slate-200 truncate">{cand.title}</p>
                        <p className="text-[11px] text-slate-400 truncate">{cand.company}</p>
                        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-500">
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

            {/* Actions */}
            <div className="pt-3 border-t border-slate-700 flex gap-2">
              <button
                onClick={() => setBatchFollowUpOpen(false)}
                disabled={sendingFollowUp}
                className="flex-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 py-2.5 rounded-xl text-xs font-semibold transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleSendBatchFollowUp}
                disabled={sendingFollowUp || selectedBatchIds.length === 0}
                className="flex-1 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-50 text-slate-950 font-bold py-2.5 rounded-xl text-xs shadow-md transition flex items-center justify-center gap-1.5 cursor-pointer"
              >
                {sendingFollowUp ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                <span>{sendingFollowUp ? 'Sending Follow-ups...' : `Send Follow-ups (${selectedBatchIds.length})`}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Email Thread & Recruiter Communications Modal */}
      {threadModal && (
        <div 
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-3 md:p-6" 
          onClick={() => setThreadModal(null)}
        >
          <div 
            className="bg-slate-900 border border-slate-700/90 rounded-2xl w-full max-w-3xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden" 
            onClick={e => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-800 bg-slate-950/70 flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1.5">
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                    COLUMNS.find(c => c.key === (threadData?.application?.status || threadModal.status))?.color || 'border-slate-600'
                  } bg-slate-800 text-slate-200`}>
                    {COLUMNS.find(c => c.key === (threadData?.application?.status || threadModal.status))?.label || threadModal.status}
                  </span>
                  {(threadData?.application?.match_score || threadModal.match_score) > 0 && (
                    <ScoreBadge score={threadData?.application?.match_score || threadModal.match_score} />
                  )}
                  {threadData?.sent_count > 0 && (
                    <span className="text-[11px] text-blue-300 bg-blue-950/60 border border-blue-700/60 px-2 py-0.5 rounded-full font-medium">
                      {threadData.sent_count} email{threadData.sent_count > 1 ? 's' : ''} sent
                    </span>
                  )}
                  {threadData?.received_count > 0 && (
                    <span className="text-[11px] text-purple-300 bg-purple-950/60 border border-purple-700/60 px-2 py-0.5 rounded-full font-bold">
                      {threadData.received_count} reply received
                    </span>
                  )}
                </div>
                <h2 className="text-lg md:text-xl font-bold text-white truncate">
                  {threadData?.application?.title || threadModal.title}
                </h2>
                <div className="flex items-center gap-3 text-xs text-slate-400 mt-1 flex-wrap">
                  <span className="text-slate-200 font-semibold flex items-center gap-1">
                    <Building2 size={13} className="text-slate-400" />
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
                className="w-8 h-8 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition shrink-0 cursor-pointer"
                title="Close"
              >
                ✕
              </button>
            </div>

            {/* Quick Action Toolbar */}
            <div className="px-5 py-3 bg-slate-900 border-b border-slate-800 flex items-center justify-between gap-3 flex-wrap text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                {/* Tailored CV Download */}
                {(threadData?.application?.has_tailored_cv || threadModal.tailored_cv_filename) && (
                  <button
                    onClick={() => handleDownloadCv(
                      threadData?.application?.id || threadModal.id, 
                      threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename
                    )}
                    className="flex items-center gap-1.5 bg-emerald-950/70 hover:bg-emerald-900/80 text-emerald-300 border border-emerald-700/70 px-3 py-1.5 rounded-xl font-mono text-[11px] transition cursor-pointer shadow-sm"
                    title="Download tailored resume PDF generated for this role"
                  >
                    <FileText size={12} className="text-emerald-400" />
                    <span className="truncate max-w-[200px]">{threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename || 'Tailored_CV.pdf'}</span>
                    <Download size={11} className="ml-0.5 opacity-70" />
                  </button>
                )}

                {/* Recruiter Email pills with Copy */}
                {(threadData?.application?.discovered_emails || []).map(em => (
                  <button
                    key={em}
                    onClick={() => copyToClipboard(em)}
                    className="flex items-center gap-1 bg-slate-800 hover:bg-slate-700 text-blue-300 border border-slate-700 px-2.5 py-1 rounded-lg text-[11px] transition cursor-pointer font-mono"
                    title="Click to copy email address"
                  >
                    <Mail size={11} className="text-blue-400" />
                    <span>{em}</span>
                    {copiedEmail === em ? <Check size={11} className="text-emerald-400 ml-0.5" /> : <Copy size={11} className="opacity-50 ml-0.5" />}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                {/* Google Meet Call Link */}
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

                {/* Official Career Portal Link */}
                {(threadData?.application?.portal_url || getPortalLink(threadModal)) && (
                  <a
                    href={threadData?.application?.portal_url || getPortalLink(threadModal)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 bg-blue-600/20 hover:bg-blue-600/35 text-blue-300 border border-blue-500/30 px-2.5 py-1 rounded-lg font-medium transition"
                  >
                    <ExternalLink size={12} />
                    <span>Career Portal</span>
                  </a>
                )}

                {/* Follow-up Action */}
                <button
                  onClick={() => {
                    const target = threadData?.application || threadModal;
                    setThreadModal(null);
                    openFollowUpModal(target);
                  }}
                  className="flex items-center gap-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 px-2.5 py-1 rounded-lg font-semibold text-xs transition cursor-pointer"
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
                  <p className="text-sm font-medium">Loading email thread & correspondence...</p>
                </div>
              ) : threadData?.thread?.length > 0 ? (
                <div className="space-y-4">
                  {threadData.thread.map((msg, idx) => (
                    <div 
                      key={idx} 
                      className={`rounded-2xl border p-4 transition ${
                        msg.direction === 'inbound'
                          ? 'bg-purple-950/25 border-purple-800/70 shadow-lg shadow-purple-950/20'
                          : 'bg-slate-900/90 border-slate-700/80 shadow-md'
                      }`}
                    >
                      {/* Message Top Bar */}
                      <div className="flex items-start justify-between gap-3 mb-2.5 flex-wrap">
                        <div className="flex items-center gap-2.5">
                          {msg.direction === 'inbound' ? (
                            <span className="p-1.5 rounded-lg bg-purple-600/20 text-purple-400 border border-purple-500/30">
                              <Inbox size={15} />
                            </span>
                          ) : (
                            <span className="p-1.5 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30">
                              <Send size={15} />
                            </span>
                          )}

                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-sm text-slate-100">
                                {msg.direction === 'inbound' ? 'Recruiter Response' : 'Outbound Application Email'}
                              </span>
                              {msg.direction === 'inbound' ? (
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                  msg.status_outcome === 'interview'
                                    ? 'bg-purple-900/60 text-purple-300 border-purple-500'
                                    : msg.status_outcome === 'review'
                                    ? 'bg-amber-900/60 text-amber-300 border-amber-500'
                                    : msg.status_outcome === 'rejected'
                                    ? 'bg-red-900/60 text-red-300 border-red-500'
                                    : 'bg-blue-900/60 text-blue-300 border-blue-500'
                                }`}>
                                  {msg.status_outcome ? msg.status_outcome.toUpperCase() : 'REPLY'}
                                </span>
                              ) : (
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border flex items-center gap-1 ${
                                  msg.status === 'sent'
                                    ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                                    : 'bg-red-950/60 text-red-300 border-red-700/50'
                                }`}>
                                  {msg.status === 'sent' ? <CheckCircle size={10} /> : <XCircle size={10} />}
                                  {msg.status === 'sent' ? 'Delivered' : msg.status}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 font-mono mt-0.5">
                              {msg.direction === 'inbound' ? (
                                <span>From: <strong className="text-slate-300">{msg.from_header}</strong></span>
                              ) : (
                                <span>To: <strong className="text-slate-300">{msg.to_name ? `${msg.to_name} <${msg.to_email}>` : msg.to_email}</strong></span>
                              )}
                            </p>
                          </div>
                        </div>

                        <span className="text-xs text-slate-500 flex items-center gap-1 font-mono">
                          <Clock size={11} />
                          {msg.timestamp}
                        </span>
                      </div>

                      {/* Subject */}
                      <div className="mb-2.5 pb-2 border-b border-slate-800 flex items-baseline gap-1.5">
                        <span className="text-xs text-slate-400 font-medium">Subject:</span>
                        <span className="text-xs font-semibold text-slate-200">{msg.subject}</span>
                      </div>

                      {/* Body Content */}
                      <div className={`p-4 rounded-xl text-xs leading-relaxed select-text whitespace-pre-wrap ${
                        msg.direction === 'inbound'
                          ? 'bg-slate-950/80 border border-purple-900/40 text-purple-100 font-sans italic'
                          : 'bg-slate-950/60 border border-slate-800/80 text-slate-200 font-sans'
                      }`}>
                        {msg.body || '(No body content recorded)'}
                      </div>

                      {/* Tailored CV Attachment badge */}
                      {msg.direction === 'outbound' && (threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename) && (
                        <div className="mt-2.5 flex items-center gap-2 text-xs text-slate-400">
                          <Paperclip size={12} className="text-emerald-400" />
                          <span>Attached: <span className="font-mono text-emerald-300">{threadData?.application?.tailored_cv_filename || threadModal.tailored_cv_filename}</span></span>
                        </div>
                      )}

                      {/* Inbound Direct Portal / Action Link */}
                      {msg.direction === 'inbound' && msg.portal_link && (
                        <div className="mt-3">
                          <a
                            href={msg.portal_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs px-4 py-2 rounded-xl shadow-lg transition"
                          >
                            <ExternalLink size={13} />
                            <span>Complete Application on Official Career Site</span>
                          </a>
                        </div>
                      )}

                      {/* Inbound Direct Google Meet Call Action */}
                      {msg.direction === 'inbound' && (msg.meet_link || msg.body?.includes('meet.google.com')) && (
                        <div className="mt-3">
                          <a
                            href={msg.meet_link || (msg.body.match(/https?:\/\/meet\.google\.com\/[^\s<>"'\)]+/i)?.[0])}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-emerald-950/40 transition border border-emerald-400/40"
                          >
                            <Video size={14} />
                            <span>📹 Join Google Meet Video Interview</span>
                          </a>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-12 px-6 rounded-2xl bg-slate-950/40 border border-slate-800 text-center">
                  {threadModal.status === 'saved' ? (
                    <div className="max-w-md mx-auto space-y-3">
                      <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mx-auto">
                        <Clock size={24} />
                      </div>
                      <h4 className="font-bold text-slate-200 text-base">Application Saved in Queue</h4>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        This job application was saved to protect your Gmail 100/day SMTP quota. It is queued in your pipeline and will be dispatched once your daily quota resets.
                      </p>
                      {threadModal.notes && (
                        <div className="mt-3 p-3 bg-slate-900 border border-slate-800 rounded-xl text-left text-xs text-slate-400">
                          <span className="font-semibold text-slate-300 block mb-1">Queue Notes:</span>
                          <span className="italic">{threadModal.notes}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="max-w-md mx-auto space-y-3">
                      <div className="w-12 h-12 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 mx-auto">
                        <Mail size={24} />
                      </div>
                      <h4 className="font-bold text-slate-200 text-base">No Emails Dispatched Yet</h4>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        No automated emails have been logged for this application yet. You can dispatch a direct email or follow-up at any time.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Application Notes / Audit Log section */}
              {(threadData?.application?.notes || threadModal.notes) && (
                <div className="mt-4 p-4 rounded-xl bg-slate-950/40 border border-slate-800/80">
                  <h4 className="text-xs font-bold text-slate-300 mb-2 flex items-center gap-1.5">
                    <StickyNote size={13} className="text-slate-400" />
                    <span>Application Notes & Activity History</span>
                  </h4>
                  <div className="text-xs text-slate-400 whitespace-pre-wrap font-mono leading-relaxed bg-slate-900/60 p-3 rounded-lg border border-slate-800/60 select-text max-h-36 overflow-y-auto">
                    {threadData?.application?.notes || threadModal.notes}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs text-slate-400 mr-1 font-medium">Status:</span>
                {COLUMNS.filter(c => c.key !== (threadData?.application?.status || threadModal.status)).map(c => (
                  <button
                    key={c.key}
                    onClick={() => {
                      moveStatus(threadModal.id, c.key);
                      setThreadModal(prev => prev ? { ...prev, status: c.key } : null);
                      if (threadData?.application) {
                        setThreadData(prev => prev ? { ...prev, application: { ...prev.application, status: c.key } } : null);
                      }
                    }}
                    className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 px-2 py-1 rounded-lg transition cursor-pointer"
                  >
                    →{c.label.split(' ').slice(1).join(' ')}
                  </button>
                ))}
              </div>

              <button
                onClick={() => setThreadModal(null)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold px-4 py-2 rounded-xl transition cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  </PageWrapper>
  )
}
