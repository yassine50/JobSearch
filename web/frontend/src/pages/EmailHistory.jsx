import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import EmailCalendarView from '../components/EmailCalendarView.jsx'
import client from '../api/client.js'
import { Mail, CheckCircle, XCircle, Eye, AlertTriangle, Calendar, List, Sparkles, X } from 'lucide-react'

const TEMPLATE_LABELS = {
  application: 'Job Application',
  auto_apply: 'Direct Application',
  cold_outreach: 'Cold Outreach',
  follow_up: 'Follow-Up',
  thank_you: 'Thank You',
  cover_letter: 'Cover Letter',
  custom: 'Custom'
}

export default function EmailHistory() {
  const [logs, setLogs]         = useState([])
  const [filter, setFilter]     = useState('all')
  const [viewing, setViewing]   = useState(null)
  const [viewMode, setViewMode] = useState('calendar') // 'calendar' | 'table'

  useEffect(() => {
    client.get('/email/history').then(r => setLogs(r.data)).catch(() => {})
  }, [])

  const filteredLogs = logs.filter(l => {
    if (filter === 'all') return true
    if (filter === 'sent') return l.status === 'sent'
    if (filter === 'bounced') return l.status === 'bounced'
    if (filter === 'follow_up') return l.template_type === 'follow_up'
    return true
  })

  const countSent = logs.filter(l => l.status === 'sent').length
  const countBounced = logs.filter(l => l.status === 'bounced').length
  const countFollowUps = logs.filter(l => l.template_type === 'follow_up').length

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14 w-full">

          {/* Hero Command Header */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-panel rounded-3xl p-5 md:p-6 mb-6 relative overflow-hidden flex flex-col sm:flex-row sm:items-center justify-between gap-4"
          >
            <div className="glow-line-top" />
            <div className="space-y-1 relative z-10">
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300 text-[11px] font-bold">
                <Sparkles size={11} className="text-amber-400" />
                <span>Direct Outreach Intelligence</span>
              </div>
              <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white">
                Outreach History &amp; <span className="text-gradient-blue">Calendar Analytics</span>
              </h1>
              <p className="text-xs text-slate-400">
                Daily delivery heatmap, sent email audit log, and automated recruiter bounce protection.
              </p>
            </div>

            {/* Primary View Toggle: Calendar vs Table */}
            <div className="flex items-center gap-2 relative z-10 shrink-0">
              <div className="flex bg-[#050811]/90 border border-white/[0.08] rounded-2xl p-1 text-xs font-bold shadow-inner">
                <button
                  onClick={() => setViewMode('calendar')}
                  className={`relative flex items-center gap-1.5 px-3.5 py-2 rounded-xl transition cursor-pointer ${
                    viewMode === 'calendar'
                      ? 'text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {viewMode === 'calendar' && (
                    <motion.div
                      layoutId="email-view-pill"
                      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                      className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 shadow-md shadow-blue-600/25"
                    />
                  )}
                  <Calendar size={13} className="relative z-10" />
                  <span className="relative z-10">Daily Calendar</span>
                </button>
                <button
                  onClick={() => setViewMode('table')}
                  className={`relative flex items-center gap-1.5 px-3.5 py-2 rounded-xl transition cursor-pointer ${
                    viewMode === 'table'
                      ? 'text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {viewMode === 'table' && (
                    <motion.div
                      layoutId="email-view-pill"
                      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                      className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 shadow-md shadow-blue-600/25"
                    />
                  )}
                  <List size={13} className="relative z-10" />
                  <span className="relative z-10">Audit Table ({logs.length})</span>
                </button>
              </div>
            </div>
          </motion.div>

          {viewMode === 'calendar' ? (
            <EmailCalendarView />
          ) : (
            <div className="space-y-4">
              {/* Filter tabs for Table view */}
              <div className="flex items-center justify-between gap-3 flex-wrap glass-panel rounded-2xl p-3">
                <div className="flex bg-[#050811]/90 border border-white/[0.08] rounded-xl p-1 text-xs font-bold flex-wrap">
                  {[
                    { id: 'all', label: `All (${logs.length})` },
                    { id: 'sent', label: `Delivered (${countSent})` },
                    { id: 'bounced', label: `Bounced (${countBounced})` },
                    { id: 'follow_up', label: `Follow-Ups (${countFollowUps})` },
                  ].map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setFilter(tab.id)}
                      className={`px-3.5 py-1.5 rounded-lg transition cursor-pointer ${
                        filter === tab.id
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                <span className="text-xs text-slate-400 font-semibold px-2">
                  Showing <strong className="text-white">{filteredLogs.length}</strong> of {logs.length} logged email(s)
                </span>
              </div>

              {filteredLogs.length === 0 ? (
                <div className="glass-panel rounded-3xl p-16 text-center relative overflow-hidden">
                  <div className="glow-line-top" />
                  <div className="w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto mb-3 text-blue-400">
                    <Mail size={26} />
                  </div>
                  <p className="text-sm font-extrabold text-white">No emails matching filter</p>
                  <p className="text-slate-400 text-xs mt-1">Emails you dispatch and their real-time delivery status will appear here.</p>
                </div>
              ) : (
                <div className="glass-panel rounded-3xl p-6 fade-in relative overflow-hidden">
                  <div className="glow-line-top" />
                  <div className="overflow-x-auto -mx-2 px-2">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-slate-400 text-left border-b border-white/[0.08]">
                          {['Status', 'To Recruiter', 'Subject', 'Template Type', 'Sent At', 'Action'].map(h => (
                            <th key={h} className="pb-3.5 pr-4 font-extrabold text-[11px] uppercase tracking-wider">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredLogs.map(l => (
                          <tr key={l.id} className="border-b border-white/[0.04] hover:bg-white/[0.03] transition">
                            <td className="py-3.5 pr-4 whitespace-nowrap">
                              {l.status === 'sent' ? (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs font-bold">
                                  <CheckCircle size={12} className="text-emerald-400" />
                                  Delivered
                                </span>
                              ) : l.status === 'bounced' ? (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs font-bold" title="Message bloqué ou Adresse introuvable">
                                  <AlertTriangle size={12} className="text-rose-400" />
                                  Bounced
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs font-bold">
                                  <XCircle size={12} className="text-amber-400" />
                                  {l.status}
                                </span>
                              )}
                            </td>
                            <td className="py-3.5 pr-4">
                              <div className="font-bold text-white text-xs">{l.to_name}</div>
                              <div className="text-[11px] text-blue-300/90 font-mono">{l.to_email}</div>
                            </td>
                            <td className="py-3.5 pr-4 max-w-xs">
                              <div className="truncate text-slate-200 text-xs font-medium" title={l.subject}>{l.subject}</div>
                            </td>
                            <td className="py-3.5 pr-4">
                              <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-lg border ${
                                l.template_type === 'follow_up'
                                  ? 'bg-blue-500/15 text-blue-300 border-blue-500/30'
                                  : l.template_type === 'auto_apply'
                                  ? 'bg-purple-500/15 text-purple-300 border-purple-500/30'
                                  : 'bg-white/[0.04] text-slate-300 border-white/[0.08]'
                              }`}>
                                {TEMPLATE_LABELS[l.template_type] || l.template_type}
                              </span>
                            </td>
                            <td className="py-3.5 pr-4 text-slate-400 text-xs font-mono whitespace-nowrap">
                              {new Date(l.sent_at).toLocaleString()}
                            </td>
                            <td className="py-3.5">
                              <button
                                onClick={() => setViewing(l)}
                                className="text-slate-400 hover:text-white transition cursor-pointer p-1.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.06]"
                                title="View Full Email Content"
                              >
                                <Eye size={14} />
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
        </main>

        {/* View email modal */}
        <AnimatePresence>
          {viewing && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
              onClick={() => setViewing(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 12 }}
                className="glass-dropdown rounded-3xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto relative"
                onClick={e => e.stopPropagation()}
              >
                <div className="glow-line-top" />
                <div className="flex justify-between items-start gap-3 mb-4">
                  <div>
                    <h3 className="font-extrabold text-base text-white">{viewing.subject}</h3>
                    <p className="text-slate-400 text-xs font-mono mt-0.5">To: {viewing.to_name} &lt;{viewing.to_email}&gt;</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-xs px-2.5 py-1 rounded-full font-bold border ${
                      viewing.status === 'sent'
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35'
                        : viewing.status === 'bounced'
                        ? 'bg-rose-500/15 text-rose-300 border-rose-500/35'
                        : 'bg-amber-500/15 text-amber-300 border-amber-500/35'
                    }`}>
                      {viewing.status === 'bounced' ? 'Bounced / Bloqué' : viewing.status}
                    </span>
                    <button onClick={() => setViewing(null)} className="text-slate-400 hover:text-white p-1">
                      <X size={16} />
                    </button>
                  </div>
                </div>
                <pre className="text-xs text-slate-200 whitespace-pre-wrap font-sans bg-[#050811]/90 rounded-2xl p-4 leading-relaxed border border-white/[0.08]">
                  {viewing.body}
                </pre>
                <button
                  onClick={() => setViewing(null)}
                  className="mt-4 w-full bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] rounded-xl py-2.5 text-xs font-bold transition cursor-pointer"
                >
                  Close Preview
                </button>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageWrapper>
  )
}
