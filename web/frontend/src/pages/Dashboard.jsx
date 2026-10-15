import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import client, { getCached } from '../api/client.js'
import {
  Search, Users, Bookmark, Trash2, ExternalLink, Bell,
  Mail, TrendingUp, Briefcase, Calendar, ArrowRight,
  Sparkles, Radar, CheckCircle2, Send, Activity
} from 'lucide-react'

const STATUS_COLORS = {
  applied:   { bg: 'bg-blue-500',    text: 'text-blue-400',    border: 'border-blue-500/30',    label: 'Applied'   },
  interview: { bg: 'bg-amber-400',   text: 'text-amber-300',   border: 'border-amber-500/30',   label: 'Interview' },
  offer:     { bg: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-500/30', label: 'Offer'     },
  rejected:  { bg: 'bg-rose-500',    text: 'text-rose-400',    border: 'border-rose-500/30',    label: 'Rejected'  },
  accepted:  { bg: 'bg-purple-500',  text: 'text-purple-400',  border: 'border-purple-500/30',  label: 'Accepted'  },
}

const CARD_THEMES = {
  blue: {
    iconBg: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    valueText: 'text-blue-400',
    glow: 'from-blue-600/15 to-transparent'
  },
  emerald: {
    iconBg: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    valueText: 'text-emerald-400',
    glow: 'from-emerald-600/15 to-transparent'
  },
  purple: {
    iconBg: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    valueText: 'text-purple-400',
    glow: 'from-purple-600/15 to-transparent'
  },
  amber: {
    iconBg: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    valueText: 'text-amber-400',
    glow: 'from-amber-600/15 to-transparent'
  },
}

function AnimatedNumber({ value }) {
  const isPercent = typeof value === 'string' && value.endsWith('%')
  const numericTarget = Number(isPercent ? value.replace('%', '') : value) || 0
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    let rafId
    const startTime = performance.now()
    const duration = 750

    const tick = (now) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 4)
      setDisplay(Math.round(eased * numericTarget))
      if (progress < 1) {
        rafId = requestAnimationFrame(tick)
      }
    }

    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [numericTarget])

  return <>{display}{isPercent ? '%' : ''}</>
}

function StatCard({ Icon, value, label, sub, color = 'blue', delay = 0, onClick }) {
  const theme = CARD_THEMES[color] || CARD_THEMES.blue
  return (
    <motion.div
      initial={{ opacity: 0, y: 18, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -5, scale: 1.01 }}
      whileTap={onClick ? { scale: 0.985 } : undefined}
      onClick={onClick}
      className={`glass-card rounded-2xl p-5 relative overflow-hidden group transition-all ${
        onClick ? 'cursor-pointer hover:border-blue-500/45' : ''
      }`}
    >
      {/* Subtle corner radial spotlight */}
      <div className={`absolute -top-12 -right-12 w-32 h-32 rounded-full bg-gradient-to-bl ${theme.glow} blur-2xl pointer-events-none group-hover:scale-150 transition-transform duration-700`} />

      <div className="flex items-start justify-between mb-3 relative z-10">
        <div className={`w-10 h-10 rounded-xl border flex items-center justify-center transition-transform duration-300 group-hover:scale-110 group-hover:rotate-3 ${theme.iconBg}`}>
          <Icon size={18} />
        </div>
        {onClick && (
          <ArrowRight size={14} className="text-slate-600 group-hover:text-slate-200 group-hover:translate-x-1 transition-all duration-300" />
        )}
      </div>

      <div className="relative z-10">
        <div className={`text-3xl font-black tracking-tight ${theme.valueText}`}>
          <AnimatedNumber value={value} />
        </div>
        <div className="text-slate-200 text-xs font-bold mt-1">{label}</div>
        {sub && <div className="text-slate-400 text-[11px] mt-0.5 truncate">{sub}</div>}
      </div>
    </motion.div>
  )
}

function PipelineBar({ pipeline, total }) {
  const stages = ['applied', 'interview', 'offer', 'accepted', 'rejected']
  if (!total) {
    return (
      <div className="text-slate-400 text-xs text-center py-8 space-y-2">
        <div className="w-10 h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto text-slate-500 animate-float">
          <Briefcase size={18} />
        </div>
        <p className="font-semibold text-slate-300">No tracked applications yet</p>
        <p className="text-slate-500">Auto-apply to a recruiter post to populate your live funnel</p>
      </div>
    )
  }
  return (
    <div className="space-y-3.5">
      {stages.map((s, idx) => {
        const count = pipeline[s] || 0
        const pct = total ? Math.round((count / total) * 100) : 0
        const c = STATUS_COLORS[s]
        return (
          <motion.div
            key={s}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15 + idx * 0.06, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-1"
          >
            <div className="flex items-center justify-between text-xs">
              <span className={`${c.text} font-bold flex items-center gap-1.5`}>
                <span className={`w-2 h-2 rounded-full ${c.bg} ${count > 0 ? 'animate-pulse' : ''}`} />
                {c.label}
              </span>
              <span className="text-slate-400 font-semibold">
                {count} <span className="text-slate-600 text-[10px]">({pct}%)</span>
              </span>
            </div>
            <div className="w-full bg-slate-900/90 border border-white/[0.05] rounded-full h-2.5 overflow-hidden p-0.5">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${ Math.max(count > 0 ? 6 : 0, pct) }%` }}
                transition={{ delay: 0.22 + idx * 0.08, duration: 0.85, ease: [0.16, 1, 0.3, 1] }}
                className={`h-full ${c.bg} rounded-full relative`}
              />
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [saved, setSaved] = useState(() => getCached('/jobs/saved', []))
  const [cvInfo, setCvInfo] = useState(() => getCached('/cv/info', { uploaded: false }))
  const [stats, setStats] = useState(() => getCached('/tracker/stats/detailed', null))
  const [loading, setLoading] = useState(() => !getCached('/tracker/stats/detailed', null))

  useEffect(() => {
    Promise.all([
      client.get('/jobs/saved').then(r => setSaved(r.data)).catch(() => {}),
      client.get('/cv/info').then(r => setCvInfo(r.data)).catch(() => {}),
      client.get('/tracker/stats/detailed').then(r => setStats(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [])

  const deleteSaved = async (id) => {
    await client.delete(`/jobs/saved/${id}`)
    setSaved(s => s.filter(j => j.id !== id))
    toast('Job removed', 'info')
  }

  const totalApps = stats?.total || 0
  const responseRate = stats?.response_rate || 0
  const emailsSent = stats?.emails_sent || 0
  const thisWeek = stats?.this_week || 0
  const followUps = stats?.follow_ups_due || []
  const recentEmails = stats?.recent_emails || []

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14 w-full">

          {/* Hero Welcome Header */}
          <motion.div
            className="glass-card rounded-3xl p-6 mb-6 relative overflow-hidden flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <div className="glow-line-top" />
            <div className="space-y-1 relative z-10">
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300 text-[11px] font-bold mb-1">
                <Sparkles size={11} className="text-amber-400" />
                <span>AI Command Center</span>
              </div>
              <h1 className="text-2xl md:text-3xl font-black tracking-tight">
                Welcome back, <span className="text-gradient-blue">{user?.name?.split(' ')[0] || 'Explorer'}</span> 👋
              </h1>
              <p className="text-slate-400 text-xs md:text-sm">
                {cvInfo.uploaded
                  ? `Resume active (${cvInfo.filename}) · Ready for 1-click AI tailoring & outreach`
                  : 'Upload your PDF resume in Post Hunter to unlock ATS match scoring & auto-apply'}
              </p>
            </div>

            <div className="flex items-center gap-2.5 relative z-10 shrink-0">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate('/seeker')}
                className="shimmer-btn px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white text-xs font-bold shadow-lg shadow-blue-600/25 flex items-center gap-2 cursor-pointer"
              >
                <Radar size={15} />
                <span>Launch Post Hunter</span>
              </motion.button>
              <span className="px-3 py-2 bg-white/[0.04] border border-white/[0.08] text-slate-300 text-[11px] font-bold rounded-xl uppercase tracking-wider">
                {user?.role || 'seeker'}
              </span>
            </div>
          </motion.div>

          {/* Follow-up Alerts */}
          <AnimatePresence>
            {followUps.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="bg-amber-950/40 border border-amber-500/30 rounded-2xl p-4 mb-6 flex items-center gap-3.5 backdrop-blur-xl"
              >
                <div className="w-9 h-9 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center shrink-0">
                  <Bell size={16} className="text-amber-400 animate-bounce" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-amber-200 font-bold text-xs sm:text-sm">
                    {followUps.length} Recruiter Follow-Up{followUps.length > 1 ? 's' : ''} Due Today
                  </p>
                  <p className="text-amber-300/70 text-xs truncate mt-0.5">
                    {followUps.map(f => `${f.company} (${f.status})`).join(' · ')}
                  </p>
                </div>
                <button
                  onClick={() => navigate('/tracker')}
                  className="px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 text-xs font-bold text-amber-200 flex items-center gap-1 shrink-0 cursor-pointer transition"
                >
                  <span>Review</span>
                  <ArrowRight size={12} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* KPI Bento Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6">
            <StatCard
              delay={0}
              Icon={Briefcase}
              value={totalApps}
              label="Total Applications"
              sub="Tracked in Kanban →"
              color="blue"
              onClick={() => navigate('/tracker')}
            />
            <StatCard
              delay={0.06}
              Icon={Activity}
              value={`${responseRate}%`}
              label="Response Rate"
              sub={`${stats?.interviews || 0} active interviews`}
              color="emerald"
            />
            <StatCard
              delay={0.12}
              Icon={Send}
              value={emailsSent}
              label="Recruiter Outreach"
              sub="Direct emails dispatched →"
              color="purple"
              onClick={() => navigate('/email')}
            />
            <StatCard
              delay={0.18}
              Icon={Calendar}
              value={thisWeek}
              label="Velocity This Week"
              sub="Activity log →"
              color="amber"
              onClick={() => navigate('/email')}
            />
          </div>

          {/* Pipeline + Recent Outreach */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            {/* Pipeline Chart */}
            <motion.div
              className="glass-card rounded-2xl p-6"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-blue-500/15 border border-blue-500/25 flex items-center justify-center text-blue-400">
                    <TrendingUp size={15} />
                  </div>
                  <div>
                    <h2 className="font-bold text-sm text-white">Application Funnel</h2>
                    <p className="text-[11px] text-slate-400">Real-time stage distribution</p>
                  </div>
                </div>
                <button
                  onClick={() => navigate('/tracker')}
                  className="text-xs font-semibold text-blue-400 hover:text-blue-300 flex items-center gap-1 cursor-pointer"
                >
                  <span>Open Board</span>
                  <ArrowRight size={12} />
                </button>
              </div>
              {loading ? (
                <div className="space-y-3.5">
                  {Array(4).fill(0).map((_, i) => (
                    <div key={i} className="space-y-1.5">
                      <div className="h-3 bg-slate-800 rounded w-24 animate-pulse" />
                      <div className="h-2.5 bg-slate-800 rounded-full w-full animate-pulse" />
                    </div>
                  ))}
                </div>
              ) : (
                <PipelineBar pipeline={stats?.pipeline || {}} total={totalApps} />
              )}
            </motion.div>

            {/* Recent Email Activity */}
            <motion.div
              className="glass-card rounded-2xl p-6"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.26 }}
            >
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/15 border border-purple-500/25 flex items-center justify-center text-purple-400">
                    <Mail size={15} />
                  </div>
                  <div>
                    <h2 className="font-bold text-sm text-white">Recent Recruiter Outreach</h2>
                    <p className="text-[11px] text-slate-400">Direct tailored applications</p>
                  </div>
                </div>
                <button
                  onClick={() => navigate('/email')}
                  className="text-xs font-semibold text-purple-400 hover:text-purple-300 flex items-center gap-1 cursor-pointer"
                >
                  <span>Full Log</span>
                  <ArrowRight size={12} />
                </button>
              </div>

              {recentEmails.length === 0 ? (
                <div className="text-slate-400 text-xs text-center py-8 space-y-2">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto text-slate-500">
                    <Mail size={18} />
                  </div>
                  <p className="font-semibold text-slate-300">No outreach dispatched yet</p>
                  <p className="text-slate-500">Use ⚡ Auto-Apply on any verified recruiter post</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {recentEmails.map((e, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: 8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.3 + i * 0.05 }}
                      className="flex items-center gap-3 p-2.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.05] transition-colors"
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${
                        e.status === 'sent' ? 'bg-emerald-400 shadow-sm shadow-emerald-400' : 'bg-rose-400'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-bold text-white truncate">{e.subject}</p>
                        <p className="text-[11px] text-slate-400 font-mono truncate">To: {e.to_email}</p>
                      </div>
                      <span className="text-[10px] font-medium text-slate-500 shrink-0">
                        {e.sent_at?.substring(0, 10)}
                      </span>
                    </motion.div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>

          {/* Quick Action Hero Banners */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            {[
              {
                label: 'Hunt Live Recruiter Posts',
                sub: 'Mine verified corporate emails & 1-click Auto-Apply',
                Icon: Radar,
                to: '/seeker',
                gradient: 'from-blue-600/25 via-indigo-600/15 to-slate-900/80 border-blue-500/30 hover:border-blue-400/60',
                iconColor: 'bg-blue-600 text-white shadow-blue-500/30',
                delay: 0.1
              },
              {
                label: 'Manage Application Pipeline',
                sub: 'Track interviews, offers, and automated follow-ups',
                Icon: Briefcase,
                to: '/tracker',
                gradient: 'from-emerald-600/20 via-teal-600/15 to-slate-900/80 border-emerald-500/30 hover:border-emerald-400/60',
                iconColor: 'bg-emerald-600 text-white shadow-emerald-500/30',
                delay: 0.16
              },
            ].map(({ label, sub, Icon, to, gradient, iconColor, delay }) => (
              <motion.button
                key={to}
                onClick={() => navigate(to)}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay, duration: 0.3 }}
                whileHover={{ y: -3, scale: 1.005 }}
                whileTap={{ scale: 0.99 }}
                className={`group flex items-center gap-4 bg-gradient-to-br ${gradient} border rounded-2xl p-5 transition-all text-left cursor-pointer backdrop-blur-xl`}
              >
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg shrink-0 ${iconColor}`}>
                  <Icon size={22} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-extrabold text-sm md:text-base text-white group-hover:text-blue-200 transition-colors">
                    {label}
                  </div>
                  <div className="text-slate-400 text-xs mt-0.5 truncate">{sub}</div>
                </div>
                <ArrowRight size={18} className="text-slate-400 group-hover:text-white group-hover:translate-x-1 transition-all shrink-0" />
              </motion.button>
            ))}
          </div>

          {/* Saved Jobs Table */}
          <motion.div
            className="glass-card rounded-2xl p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.3 }}
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-500/15 border border-blue-500/25 flex items-center justify-center text-blue-400">
                  <Bookmark size={15} />
                </div>
                <div>
                  <h2 className="font-bold text-sm text-white">Saved Opportunities</h2>
                  <p className="text-[11px] text-slate-400">Bookmarked posts & job board listings</p>
                </div>
              </div>
              <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/[0.08] text-slate-300">
                {saved.length} saved
              </span>
            </div>

            {saved.length === 0 ? (
              <div className="text-center py-10 text-slate-500 space-y-3">
                <Bookmark size={32} className="mx-auto opacity-30" />
                <p className="text-xs text-slate-400">No saved jobs yet.</p>
                <button
                  onClick={() => navigate('/seeker')}
                  className="px-4 py-2 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 text-blue-300 text-xs font-bold transition cursor-pointer"
                >
                  Explore Live Recruiter Posts →
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto -mx-2 px-2">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-400 text-left border-b border-white/[0.07]">
                      {['Role Title', 'Company', 'Location', 'AI Match', 'Saved Date', 'Actions'].map(h => (
                        <th key={h} className="pb-3 pr-4 font-bold text-[11px] uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {saved.map((j, i) => (
                      <motion.tr
                        key={j.id}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.04, duration: 0.2 }}
                        className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors"
                      >
                        <td className="py-3.5 pr-4 font-bold text-white max-w-xs">
                          <div className="truncate">{j.title}</div>
                        </td>
                        <td className="py-3.5 pr-4 text-blue-300 font-medium max-w-xs">
                          <div className="truncate">{j.company}</div>
                        </td>
                        <td className="py-3.5 pr-4 text-slate-400 text-xs">{j.location || 'Remote / Global'}</td>
                        <td className="py-3.5 pr-4">
                          {j.match_score ? <ScoreBadge score={j.match_score} /> : <span className="text-slate-600">—</span>}
                        </td>
                        <td className="py-3.5 pr-4 text-xs text-slate-500">{j.saved_at?.substring(0, 10)}</td>
                        <td className="py-3.5">
                          <div className="flex items-center gap-3">
                            {j.url && (
                              <a
                                href={j.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-xs font-semibold transition-colors"
                              >
                                <ExternalLink size={13} /> View
                              </a>
                            )}
                            <button
                              onClick={() => deleteSaved(j.id)}
                              className="text-slate-500 hover:text-rose-400 transition-colors cursor-pointer"
                              title="Remove saved job"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>
        </main>
      </div>
    </PageWrapper>
  )
}
