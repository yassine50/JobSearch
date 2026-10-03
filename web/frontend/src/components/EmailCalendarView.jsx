import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import client from '../api/client.js'
import { 
  ChevronLeft, ChevronRight, Calendar, Mail, CheckCircle, AlertTriangle, 
  Clock, ArrowUpRight, Search, Copy, Check, Eye, X, ShieldAlert, Sparkles 
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
  const month = currentDate.getMonth() + 1 // 1-indexed for backend

  const fetchAnalytics = async (y, m) => {
    setLoading(true)
    try {
      const { data } = await client.get(`/email/calendar-analytics?year=${y}&month=${m}`)
      setAnalytics(data)
      
      // Auto-select today if in current month, or the latest active date in this month
      const activeDays = Object.keys(data.days || {})
      if (activeDays.length > 0) {
        if (data.days[data.today_str]) {
          setSelectedDateStr(data.today_str)
        } else {
          // Select the most recent day with emails
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

  const prevMonth = () => {
    setCurrentDate(new Date(year, month - 2, 1))
  }

  const nextMonth = () => {
    setCurrentDate(new Date(year, month, 1))
  }

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

  // Generate calendar grid days
  const firstDayIndex = new Date(year, month - 1, 1).getDay() // 0 = Sun
  const daysInMonth = new Date(year, month, 0).getDate()
  const prevMonthDays = new Date(year, month - 1, 0).getDate()

  const calendarCells = []

  // Trailing days from previous month
  for (let i = firstDayIndex - 1; i >= 0; i--) {
    const dayNum = prevMonthDays - i
    calendarCells.push({
      dayNum,
      isCurrentMonth: false,
      dateStr: null
    })
  }

  // Days of current month
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

  // Leading days for next month to round out the 7-column grid
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

  const monthStats = analytics?.month_stats || { total_sent: 0, total_bounced: 0, total_follow_ups: 0, deliverability_rate: 100 }
  const quotaUsed = analytics?.today_sent || 0
  const quotaLimit = analytics?.daily_limit || 100
  const quotaPct = Math.min(100, Math.round((quotaUsed / quotaLimit) * 100))

  return (
    <div className="space-y-6">
      {/* Top Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-800/90 border border-slate-700/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Month Dispatched</span>
            <div className="w-8 h-8 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <Mail size={16} />
            </div>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{monthStats.total_sent + monthStats.total_bounced}</span>
            <span className="text-xs text-slate-400">outreach emails</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span>
            <span>{monthStats.total_sent} delivered · {monthStats.total_bounced} bounced</span>
          </div>
        </div>

        <div className="bg-slate-800/90 border border-slate-700/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Deliverability Rate</span>
            <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <CheckCircle size={16} />
            </div>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald-400">{monthStats.deliverability_rate}%</span>
            <span className="text-xs text-slate-400">clean inboxes</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            Filtered with DNS MX & community blacklist
          </div>
        </div>

        <div className="bg-slate-800/90 border border-slate-700/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Today's Gmail Quota</span>
            <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${quotaPct >= 90 ? 'bg-red-500/10 border border-red-500/20 text-red-400' : 'bg-amber-500/10 border border-amber-500/20 text-amber-400'}`}>
              <Clock size={16} />
            </div>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{quotaUsed}</span>
            <span className="text-xs text-slate-400">/ {quotaLimit} limit</span>
          </div>
          <div className="mt-2 w-full bg-slate-700/60 rounded-full h-1.5 overflow-hidden">
            <div 
              className={`h-full rounded-full transition-all duration-500 ${quotaPct >= 90 ? 'bg-red-500' : quotaPct >= 60 ? 'bg-amber-500' : 'bg-blue-500'}`}
              style={{ width: `${quotaPct}%` }}
            />
          </div>
        </div>

        <div className="bg-slate-800/90 border border-slate-700/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Active Sending Days</span>
            <div className="w-8 h-8 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
              <Calendar size={16} />
            </div>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-purple-300">{monthStats.active_days}</span>
            <span className="text-xs text-slate-400">days this month</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            Consistent outreach boosts response rates
          </div>
        </div>
      </div>

      {/* Main Calendar & Day Detail Container */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Interactive Month Calendar (7 Cols) */}
        <div className="lg:col-span-7 bg-slate-800 border border-slate-700 rounded-2xl p-5 shadow-sm flex flex-col">
          {/* Calendar Header Navigation */}
          <div className="flex items-center justify-between mb-5 pb-3 border-b border-slate-700/60">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Calendar size={18} className="text-blue-400" />
                {analytics?.month_name || `${new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' }).format(currentDate)}`}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={goToToday}
                className="px-2.5 py-1 text-xs font-medium rounded-lg border border-slate-700 bg-slate-750 text-slate-300 hover:text-white hover:border-slate-600 transition"
              >
                Today
              </button>
              <div className="flex items-center border border-slate-700 rounded-lg overflow-hidden bg-slate-900/60">
                <button
                  onClick={prevMonth}
                  className="p-1.5 hover:bg-slate-700 text-slate-400 hover:text-white transition"
                  title="Previous Month"
                >
                  <ChevronLeft size={16} />
                </button>
                <div className="w-px h-4 bg-slate-700" />
                <button
                  onClick={nextMonth}
                  className="p-1.5 hover:bg-slate-700 text-slate-400 hover:text-white transition"
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
              <div key={d} className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider py-1">
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
                    className="min-h-[76px] rounded-xl p-1.5 bg-slate-900/20 border border-transparent text-slate-600 text-xs flex flex-col justify-between select-none opacity-40"
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

              // Heatmap intensity background
              let cellBg = 'bg-slate-900/40 hover:bg-slate-750/70 border-slate-700/60'
              if (totalCount > 0) {
                if (totalCount >= 50) cellBg = 'bg-blue-950/70 border-blue-600/60 shadow-sm shadow-blue-900/20'
                else if (totalCount >= 15) cellBg = 'bg-indigo-950/60 border-indigo-600/50'
                else cellBg = 'bg-slate-800/90 border-blue-700/40'
              }

              if (isSelected) {
                cellBg = 'bg-blue-900/40 border-blue-400 ring-2 ring-blue-500/30 shadow-md'
              }

              return (
                <motion.button
                  key={cell.dateStr}
                  whileTap={{ scale: 0.96 }}
                  onClick={() => setSelectedDateStr(cell.dateStr)}
                  className={`min-h-[78px] rounded-xl p-1.5 border text-left transition-all flex flex-col justify-between relative cursor-pointer group ${cellBg}`}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className={`text-xs font-semibold rounded-md px-1.5 py-0.2 ${
                      isToday
                        ? 'bg-blue-600 text-white shadow-sm'
                        : isSelected
                        ? 'text-blue-300 font-bold'
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
                      <div className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/80 text-emerald-300 truncate">
                        🟢 {sentCount} sent
                      </div>
                      {bouncedCount > 0 && (
                        <div className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-red-950/80 border border-red-800/80 text-red-300 truncate">
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
          <div className="mt-4 pt-3 border-t border-slate-700/60 flex items-center justify-between text-xs text-slate-400 flex-wrap gap-2">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded bg-emerald-500 inline-block"></span> Delivered to Recruiter
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded bg-red-500 inline-block"></span> Bounced / Purged
              </span>
            </div>
            <span className="text-slate-500 text-[11px]">Click any date to inspect details</span>
          </div>
        </div>

        {/* Right Column: Selected Day Drilldown & Email Logs (5 Cols) */}
        <div className="lg:col-span-5 bg-slate-800 border border-slate-700 rounded-2xl p-5 shadow-sm flex flex-col">
          {/* Header */}
          <div className="pb-3 border-b border-slate-700/60 mb-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider">Day Analytics</span>
                <h3 className="text-base font-bold text-white mt-0.5">
                  {selectedDateStr ? new Date(`${selectedDateStr}T00:00:00`).toLocaleDateString('en-US', {
                    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
                  }) : 'Select a date'}
                </h3>
              </div>
              {selectedDayData && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs px-2.5 py-1 rounded-lg bg-slate-750 border border-slate-700 text-slate-300 font-semibold">
                    {selectedDayData.total} {selectedDayData.total === 1 ? 'Email' : 'Emails'}
                  </span>
                </div>
              )}
            </div>

            {/* Daily KPI chips */}
            {selectedDayData && (
              <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-2">
                  <div className="text-sm font-bold text-emerald-400">{selectedDayData.sent_count}</div>
                  <div className="text-[10px] text-slate-400">Delivered</div>
                </div>
                <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-2">
                  <div className="text-sm font-bold text-red-400">{selectedDayData.bounced_count}</div>
                  <div className="text-[10px] text-slate-400">Bounced</div>
                </div>
                <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-2">
                  <div className="text-sm font-bold text-purple-400">{selectedDayData.follow_up_count}</div>
                  <div className="text-[10px] text-slate-400">Follow-Ups</div>
                </div>
              </div>
            )}
          </div>

          {/* Search box for day */}
          {selectedDayData && selectedDayData.total > 0 && (
            <div className="mb-3 relative">
              <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                value={daySearch}
                onChange={e => setDaySearch(e.target.value)}
                placeholder="Filter by company, recruiter, or role..."
                className="w-full bg-slate-900/80 border border-slate-700 rounded-xl pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          )}

          {/* Email List */}
          <div className="flex-1 overflow-y-auto space-y-2.5 max-h-[460px] pr-1">
            {!selectedDayData || selectedDayData.total === 0 ? (
              <div className="text-center py-16 text-slate-500">
                <Mail size={36} className="mx-auto mb-2 opacity-40 text-slate-400" />
                <p className="text-sm">No outreach emails dispatched on this date.</p>
                <p className="text-xs text-slate-600 mt-1">Select another day with a green marker above.</p>
              </div>
            ) : selectedEmails.length === 0 ? (
              <div className="text-center py-10 text-slate-500">
                <p className="text-xs">No emails match "{daySearch}"</p>
              </div>
            ) : (
              selectedEmails.map(item => (
                <div
                  key={item.id}
                  className="bg-slate-900/80 border border-slate-700/70 hover:border-slate-600 rounded-xl p-3 transition-colors text-xs space-y-1.5 group"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 font-semibold text-white truncate">
                        <span>{item.company}</span>
                        {item.job_title && (
                          <span className="text-slate-400 font-normal truncate">· {item.job_title}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 text-slate-400 text-[11px] mt-0.5">
                        <span className="truncate">{item.to_name || 'Recruiter'}</span>
                        <span>&lt;{item.to_email}&gt;</span>
                        <button
                          onClick={() => copyToClipboard(item.to_email)}
                          className="opacity-0 group-hover:opacity-100 transition text-slate-400 hover:text-white"
                          title="Copy email"
                        >
                          {copiedEmail === item.to_email ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                        </button>
                      </div>
                    </div>
                    
                    <div className="shrink-0 flex flex-col items-end gap-1">
                      {item.status === 'sent' ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/80 text-emerald-300 font-medium text-[10px]">
                          <CheckCircle size={10} /> Sent
                        </span>
                      ) : item.status === 'bounced' ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-950/80 border border-red-800/80 text-red-300 font-medium text-[10px]">
                          <AlertTriangle size={10} /> Bounced
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">
                          {item.status}
                        </span>
                      )}
                      <span className="text-[10px] text-slate-500 font-mono">{item.time_str}</span>
                    </div>
                  </div>

                  <div className="pt-1 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
                    <span className="truncate max-w-[200px] text-slate-400 italic">
                      "{item.subject}"
                    </span>
                    <button
                      onClick={() => setViewingEmail(item)}
                      className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-semibold cursor-pointer shrink-0"
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
              className="bg-slate-800 border border-slate-700 rounded-2xl max-w-xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden"
            >
              <div className="p-5 border-b border-slate-700 flex items-start justify-between bg-slate-850">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider bg-blue-900/60 border border-blue-700/60 text-blue-300">
                      {viewingEmail.template_type?.replace('_', ' ')}
                    </span>
                    <span className="text-xs text-slate-400">
                      Sent at {viewingEmail.time_str}
                    </span>
                  </div>
                  <h3 className="font-bold text-base text-white mt-1.5">{viewingEmail.subject}</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    To: <strong className="text-slate-200">{viewingEmail.to_name}</strong> &lt;{viewingEmail.to_email}&gt;
                  </p>
                </div>
                <button
                  onClick={() => setViewingEmail(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white transition"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="p-5 overflow-y-auto flex-1 bg-slate-900/50">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs leading-relaxed text-slate-300 font-mono whitespace-pre-wrap selection:bg-blue-600 selection:text-white">
                  {viewingEmail.body}
                </div>
              </div>

              <div className="p-4 border-t border-slate-700 flex items-center justify-between bg-slate-850">
                <button
                  onClick={() => copyToClipboard(viewingEmail.body)}
                  className="inline-flex items-center gap-1.5 text-xs text-slate-300 hover:text-white px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-750 transition"
                >
                  {copiedEmail === viewingEmail.body ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  <span>{copiedEmail === viewingEmail.body ? 'Copied Content' : 'Copy Content'}</span>
                </button>
                <button
                  onClick={() => setViewingEmail(null)}
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition"
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
