import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import client from '../api/client.js'
import { 
  ChevronLeft, ChevronRight, Calendar, Mail, CheckCircle, AlertTriangle, 
  Clock, Search, Copy, Check, Eye, X
} from 'lucide-react'

export default function EmailCalendarView() {
  const [currentDate, setCurrentDate] = useState(new Date())
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedDateStr, setSelectedDateStr] = useState(null)
  const [daySearch, setDaySearch] = useState('')
  const [viewingEmail, setViewingEmail] = useState(null)
  const [copiedEmail, setCopiedEmail] = useState(null)

  const year = currentDate.getFullYear()
  const month = currentDate.getMonth() + 1

  const fetchAnalytics = async (y, m) => {
    setLoading(true)
    try {
      const { data } = await client.get(`/email/calendar-analytics?year=${y}&month=${m}`)
      setAnalytics(data)
      
      const activeDays = Object.keys(data.days || {})
      if (activeDays.length > 0) {
        if (data.days[data.today_str]) {
          setSelectedDateStr(data.today_str)
        } else {
          const sorted = [...activeDays].sort().reverse()
          setSelectedDateStr(sorted[0])
        }
      } else {
        setSelectedDateStr(data.today_str)
      }
    } catch (err) {
      console.error('Failed to load calendar analytics:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAnalytics(year, month)
  }, [year, month])

  const prevMonth = () => setCurrentDate(new Date(year, month - 2, 1))
  const nextMonth = () => setCurrentDate(new Date(year, month, 1))

  const goToToday = () => {
    const today = new Date()
    setCurrentDate(today)
    fetchAnalytics(today.getFullYear(), today.getMonth() + 1)
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    setCopiedEmail(text)
    setTimeout(() => setCopiedEmail(null), 1500)
  }

  const firstDayIndex = new Date(year, month - 1, 1).getDay()
  const daysInMonth = new Date(year, month, 0).getDate()
  const prevMonthDays = new Date(year, month - 1, 0).getDate()

  const calendarCells = []

  for (let i = firstDayIndex - 1; i >= 0; i--) {
    calendarCells.push({
      dayNum: prevMonthDays - i,
      isCurrentMonth: false,
      dateStr: null
    })
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const mm = String(month).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    const dateStr = `${year}-${mm}-${dd}`
    calendarCells.push({
      dayNum: d,
      isCurrentMonth: true,
      dateStr,
      data: analytics?.days?.[dateStr] || null
    })
  }

  const remaining = 35 - calendarCells.length > 0 ? 35 - calendarCells.length : (42 - calendarCells.length)
  for (let i = 1; i <= remaining; i++) {
    calendarCells.push({
      dayNum: i,
      isCurrentMonth: false,
      dateStr: null
    })
  }

  const selectedDayData = selectedDateStr ? (analytics?.days?.[selectedDateStr] || null) : null
  const selectedEmails = (selectedDayData?.emails || []).filter(e => {
    if (!daySearch.trim()) return true
    const q = daySearch.toLowerCase()
    return (
      (e.to_email || '').toLowerCase().includes(q) ||
      (e.to_name || '').toLowerCase().includes(q) ||
      (e.company || '').toLowerCase().includes(q) ||
      (e.subject || '').toLowerCase().includes(q)
    )
  })

  const monthStats = analytics?.month_stats || { total_sent: 0, total_bounced: 0, total_follow_ups: 0, deliverability_rate: 100, active_days: 0 }
  const quotaUsed = analytics?.today_sent || 0
  const quotaLimit = analytics?.daily_limit || 100
  const quotaPct = Math.min(100, Math.round((quotaUsed / quotaLimit) * 100))

  return (
    <div className="space-y-6">
      {/* Top Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card rounded-2xl p-5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-extrabold text-slate-400 uppercase tracking-wider">Month Dispatched</span>
            <div className="w-9 h-9 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Mail size={16} />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-black text-white">{monthStats.total_sent + monthStats.total_bounced}</span>
            <span className="text-xs font-medium text-slate-400">outreach emails</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
            <span>{monthStats.total_sent} delivered · {monthStats.total_bounced} bounced</span>
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-extrabold text-slate-400 uppercase tracking-wider">Deliverability Rate</span>
            <div className="w-9 h-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <CheckCircle size={16} />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-black text-emerald-400">{monthStats.deliverability_rate}%</span>
            <span className="text-xs font-medium text-slate-400">clean inboxes</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400 font-medium">
            Filtered with DNS MX &amp; global bounce blacklist
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-extrabold text-slate-400 uppercase tracking-wider">Today's Gmail Quota</span>
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${quotaPct >= 90 ? 'bg-rose-500/15 border-rose-500/30 text-rose-400' : 'bg-amber-500/15 border-amber-500/30 text-amber-400'}`}>
              <Clock size={16} />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-black text-white">{quotaUsed}</span>
            <span className="text-xs font-medium text-slate-400">/ {quotaLimit} limit</span>
          </div>
          <div className="mt-2.5 w-full bg-[#050811] border border-white/[0.06] rounded-full h-2 overflow-hidden p-0.5">
            <motion.div 
              initial={{ width: 0 }}
              animate={{ width: `${quotaPct}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className={`h-full rounded-full ${quotaPct >= 90 ? 'bg-rose-500' : quotaPct >= 60 ? 'bg-amber-500' : 'bg-blue-500'}`}
            />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-extrabold text-slate-400 uppercase tracking-wider">Active Sending Days</span>
            <div className="w-9 h-9 rounded-xl bg-purple-500/15 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Calendar size={16} />
            </div>
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-black text-purple-300">{monthStats.active_days || 0}</span>
            <span className="text-xs font-medium text-slate-400">days this month</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400 font-medium">
            Consistent outreach boosts response rates
          </div>
        </div>
      </div>

      {/* Main Calendar & Day Detail Container */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Interactive Month Calendar (7 Cols) */}
        <div className="lg:col-span-7 glass-panel rounded-3xl p-5 md:p-6 flex flex-col relative overflow-hidden">
          <div className="glow-line-top" />
          {/* Calendar Header Navigation */}
          <div className="flex items-center justify-between mb-5 pb-3 border-b border-white/[0.07]">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-extrabold text-white flex items-center gap-2">
                <Calendar size={18} className="text-blue-400" />
                {analytics?.month_name || `${new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' }).format(currentDate)}`}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={goToToday}
                className="px-3 py-1.5 text-xs font-bold rounded-xl border border-white/[0.08] bg-white/[0.04] text-slate-300 hover:text-white hover:bg-white/[0.08] transition cursor-pointer"
              >
                Today
              </button>
              <div className="flex items-center border border-white/[0.08] rounded-xl overflow-hidden bg-[#050811]/80">
                <button
                  onClick={prevMonth}
                  className="p-1.5 hover:bg-white/[0.08] text-slate-400 hover:text-white transition cursor-pointer"
                  title="Previous Month"
                >
                  <ChevronLeft size={16} />
                </button>
                <div className="w-px h-4 bg-white/[0.08]" />
                <button
                  onClick={nextMonth}
                  className="p-1.5 hover:bg-white/[0.08] text-slate-400 hover:text-white transition cursor-pointer"
                  title="Next Month"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </div>

          {/* Weekday labels */}
          <div className="grid grid-cols-7 gap-1 text-center mb-2">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
              <div key={d} className="text-[11px] font-extrabold text-slate-500 uppercase tracking-wider py-1">
                {d}
              </div>
            ))}
          </div>

          {/* Calendar Day Cells */}
          <div className="grid grid-cols-7 gap-1.5 flex-1">
            {calendarCells.map((cell, idx) => {
              if (!cell.isCurrentMonth) {
                return (
                  <div
                    key={`empty-${idx}`}
                    className="min-h-[78px] rounded-xl p-2 bg-[#050811]/30 border border-transparent text-slate-700 text-xs flex flex-col justify-between select-none opacity-40"
                  >
                    <span>{cell.dayNum}</span>
                  </div>
                )
              }

              const isSelected = cell.dateStr === selectedDateStr
              const isToday = cell.dateStr === analytics?.today_str
              const dayData = cell.data
              const totalCount = dayData?.total || 0
              const sentCount = dayData?.sent_count || 0
              const bouncedCount = dayData?.bounced_count || 0

              let cellBg = 'bg-[#050811]/60 hover:bg-white/[0.04] border-white/[0.06]'
              if (totalCount > 0) {
                if (totalCount >= 50) cellBg = 'bg-blue-950/60 border-blue-500/45 shadow-sm shadow-blue-900/20'
                else if (totalCount >= 15) cellBg = 'bg-indigo-950/50 border-indigo-500/40'
                else cellBg = 'bg-slate-900/90 border-blue-500/30'
              }

              if (isSelected) {
                cellBg = 'bg-blue-600/20 border-blue-400 ring-2 ring-blue-500/30 shadow-lg'
              }

              return (
                <motion.button
                  key={cell.dateStr}
                  whileTap={{ scale: 0.96 }}
                  onClick={() => setSelectedDateStr(cell.dateStr)}
                  className={`min-h-[78px] rounded-xl p-1.5 border text-left transition-all flex flex-col justify-between relative cursor-pointer group ${cellBg}`}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className={`text-xs font-extrabold rounded-md px-1.5 py-0.2 ${
                      isToday
                        ? 'bg-blue-600 text-white shadow-sm'
                        : isSelected
                        ? 'text-blue-300 font-black'
                        : 'text-slate-300 group-hover:text-white'
                    }`}>
                      {cell.dayNum}
                    </span>
                    {totalCount > 0 && (
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                    )}
                  </div>

                  {totalCount > 0 ? (
                    <div className="mt-1 space-y-0.5 w-full">
                      <div className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 truncate">
                        🟢 {sentCount} sent
                      </div>
                      {bouncedCount > 0 && (
                        <div className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/15 border border-rose-500/30 text-rose-300 truncate">
                          🔴 {bouncedCount} dead
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-[10px] text-slate-600 italic px-1">
                      —
                    </div>
                  )}
                </motion.button>
              )
            })}
          </div>

          {/* Calendar Legend */}
          <div className="mt-4 pt-3 border-t border-white/[0.07] flex items-center justify-between text-xs text-slate-400 flex-wrap gap-2">
            <div className="flex items-center gap-3 font-medium">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded bg-emerald-500 inline-block" /> Delivered to Recruiter
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded bg-rose-500 inline-block" /> Bounced / Purged
              </span>
            </div>
            <span className="text-slate-500 text-[11px]">Click any date to inspect details</span>
          </div>
        </div>

        {/* Right Column: Selected Day Drilldown & Email Logs (5 Cols) */}
        <div className="lg:col-span-5 glass-panel rounded-3xl p-5 md:p-6 flex flex-col relative overflow-hidden">
          <div className="glow-line-top" />
          {/* Header */}
          <div className="pb-3 border-b border-white/[0.07] mb-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[11px] font-extrabold text-blue-400 uppercase tracking-wider">Day Analytics</span>
                <h3 className="text-base font-extrabold text-white mt-0.5">
                  {selectedDateStr ? new Date(`${selectedDateStr}T00:00:00`).toLocaleDateString('en-US', {
                    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
                  }) : 'Select a date'}
                </h3>
              </div>
              {selectedDayData && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs px-2.5 py-1 rounded-xl bg-white/[0.05] border border-white/[0.08] text-slate-200 font-bold">
                    {selectedDayData.total} {selectedDayData.total === 1 ? 'Email' : 'Emails'}
                  </span>
                </div>
              )}
            </div>

            {/* Daily KPI chips */}
            {selectedDayData && (
              <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                <div className="bg-[#050811]/70 border border-white/[0.06] rounded-xl p-2">
                  <div className="text-sm font-black text-emerald-400">{selectedDayData.sent_count}</div>
                  <div className="text-[10px] font-semibold text-slate-400">Delivered</div>
                </div>
                <div className="bg-[#050811]/70 border border-white/[0.06] rounded-xl p-2">
                  <div className="text-sm font-black text-rose-400">{selectedDayData.bounced_count}</div>
                  <div className="text-[10px] font-semibold text-slate-400">Bounced</div>
                </div>
                <div className="bg-[#050811]/70 border border-white/[0.06] rounded-xl p-2">
                  <div className="text-sm font-black text-purple-400">{selectedDayData.follow_up_count}</div>
                  <div className="text-[10px] font-semibold text-slate-400">Follow-Ups</div>
                </div>
              </div>
            )}
          </div>

          {/* Search box for day */}
          {selectedDayData && selectedDayData.total > 0 && (
            <div className="mb-3 relative">
              <Search size={14} className="absolute left-3 top-2.5 text-blue-400" />
              <input
                type="text"
                value={daySearch}
                onChange={e => setDaySearch(e.target.value)}
                placeholder="Filter by company, recruiter, or role..."
                className="w-full glass-input rounded-xl pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500"
              />
            </div>
          )}

          {/* Email List */}
          <div className="flex-1 overflow-y-auto space-y-2.5 max-h-[460px] pr-1">
            {!selectedDayData || selectedDayData.total === 0 ? (
              <div className="text-center py-16 text-slate-500">
                <Mail size={36} className="mx-auto mb-2 opacity-40 text-slate-400" />
                <p className="text-sm font-bold text-slate-300">No outreach emails dispatched on this date</p>
                <p className="text-xs text-slate-500 mt-1">Select another day with a green marker on the calendar.</p>
              </div>
            ) : selectedEmails.length === 0 ? (
              <div className="text-center py-10 text-slate-500">
                <p className="text-xs">No emails match "{daySearch}"</p>
              </div>
            ) : (
              selectedEmails.map(item => (
                <div
                  key={item.id}
                  className="glass-card hover:border-blue-500/40 rounded-xl p-3 transition-colors text-xs space-y-1.5 group"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 font-extrabold text-white truncate">
                        <span>{item.company}</span>
                        {item.job_title && (
                          <span className="text-slate-400 font-medium truncate">· {item.job_title}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 text-slate-400 text-[11px] mt-0.5">
                        <span className="truncate">{item.to_name || 'Recruiter'}</span>
                        <span className="font-mono text-blue-300/90">&lt;{item.to_email}&gt;</span>
                        <button
                          onClick={() => copyToClipboard(item.to_email)}
                          className="opacity-0 group-hover:opacity-100 transition text-slate-400 hover:text-white cursor-pointer"
                          title="Copy email"
                        >
                          {copiedEmail === item.to_email ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                        </button>
                      </div>
                    </div>
                    
                    <div className="shrink-0 flex flex-col items-end gap-1">
                      {item.status === 'sent' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-bold text-[10px]">
                          <CheckCircle size={10} /> Sent
                        </span>
                      ) : item.status === 'bounced' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-300 font-bold text-[10px]">
                          <AlertTriangle size={10} /> Bounced
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-lg bg-white/[0.05] text-slate-400 text-[10px] font-bold">
                          {item.status}
                        </span>
                      )}
                      <span className="text-[10px] text-slate-500 font-mono">{item.time_str}</span>
                    </div>
                  </div>

                  <div className="pt-1.5 border-t border-white/[0.05] flex items-center justify-between text-[11px] text-slate-400">
                    <span className="truncate max-w-[200px] text-slate-400 italic">
                      "{item.subject}"
                    </span>
                    <button
                      onClick={() => setViewingEmail(item)}
                      className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-bold cursor-pointer shrink-0"
                    >
                      <Eye size={12} /> View Message
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Email Body Preview Modal */}
      <AnimatePresence>
        {viewingEmail && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
            onClick={() => setViewingEmail(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              onClick={e => e.stopPropagation()}
              className="glass-dropdown rounded-3xl max-w-xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden relative"
            >
              <div className="glow-line-top" />
              <div className="p-5 border-b border-white/[0.07] flex items-start justify-between bg-[#050811]/70">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider bg-blue-500/15 border border-blue-500/30 text-blue-300">
                      {viewingEmail.template_type?.replace('_', ' ')}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      Sent at {viewingEmail.time_str}
                    </span>
                  </div>
                  <h3 className="font-extrabold text-base text-white mt-1.5">{viewingEmail.subject}</h3>
                  <p className="text-xs text-slate-400 mt-0.5 font-mono">
                    To: <strong className="text-slate-200">{viewingEmail.to_name}</strong> &lt;{viewingEmail.to_email}&gt;
                  </p>
                </div>
                <button
                  onClick={() => setViewingEmail(null)}
                  className="p-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="p-5 overflow-y-auto flex-1">
                <div className="bg-[#050811]/90 border border-white/[0.07] rounded-2xl p-4 text-xs leading-relaxed text-slate-200 font-mono whitespace-pre-wrap selection:bg-blue-600 selection:text-white">
                  {viewingEmail.body}
                </div>
              </div>

              <div className="p-4 border-t border-white/[0.07] flex items-center justify-between bg-[#050811]/80">
                <button
                  onClick={() => copyToClipboard(viewingEmail.body)}
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-300 hover:text-white px-3.5 py-2 rounded-xl border border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.08] transition cursor-pointer"
                >
                  {copiedEmail === viewingEmail.body ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  <span>{copiedEmail === viewingEmail.body ? 'Copied Content' : 'Copy Content'}</span>
                </button>
                <button
                  onClick={() => setViewingEmail(null)}
                  className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-extrabold rounded-xl transition cursor-pointer"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
