import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import client from '../api/client.js'
import { Search, Users, Bookmark, Trash2, ExternalLink, Bell,
         Mail, TrendingUp, Briefcase, Calendar, ArrowRight } from 'lucide-react'

const STATUS_COLORS = {
  applied:   { bg:'bg-blue-500',   text:'text-blue-400',   label:'Applied'   },
  interview: { bg:'bg-yellow-500', text:'text-yellow-400', label:'Interview'  },
  offer:     { bg:'bg-emerald-500',text:'text-emerald-400',label:'Offer'     },
  rejected:  { bg:'bg-red-500',    text:'text-red-400',    label:'Rejected'   },
  accepted:  { bg:'bg-purple-500', text:'text-purple-400', label:'Accepted'   },
}

function StatCard({ icon, value, label, sub, color='blue', delay=0, onClick }) {
  return (
    <motion.div
      initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{delay,duration:.3}}
      onClick={onClick}
      className={`bg-slate-800 border border-slate-700 rounded-2xl p-5 hover:-translate-y-0.5 transition-transform ${onClick?'cursor-pointer hover:border-slate-500':''}`}>
      <div className="text-2xl mb-2">{icon}</div>
      <div className={`text-2xl font-bold text-${color}-400`}>{value}</div>
      <div className="text-slate-300 text-sm font-medium mt-0.5">{label}</div>
      {sub && <div className="text-slate-500 text-xs mt-0.5 truncate">{sub}</div>}
    </motion.div>
  )
}

function PipelineBar({ pipeline, total }) {
  const stages = ['applied','interview','offer','accepted','rejected']
  if (!total) return (
    <div className="text-slate-500 text-sm text-center py-4">No applications yet</div>
  )
  return (
    <div className="space-y-3">
      {stages.map(s => {
        const count = pipeline[s] || 0
        const pct = total ? Math.round(count/total*100) : 0
        const c = STATUS_COLORS[s]
        return (
          <div key={s} className="flex items-center gap-3">
            <span className={`text-xs w-20 shrink-0 ${c.text} font-medium`}>{c.label}</span>
            <div className="flex-1 bg-slate-700 rounded-full h-2 overflow-hidden">
              <motion.div
                initial={{width:0}} animate={{width:`${pct}%`}}
                transition={{delay:.3,duration:.6,ease:'easeOut'}}
                className={`h-full ${c.bg} rounded-full`}/>
            </div>
            <span className="text-xs text-slate-400 w-8 text-right">{count}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [saved, setSaved]     = useState([])
  const [cvInfo, setCvInfo]   = useState({ uploaded:false })
  const [stats, setStats]     = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      client.get('/jobs/saved').then(r => setSaved(r.data)).catch(()=>{}),
      client.get('/cv/info').then(r => setCvInfo(r.data)).catch(()=>{}),
      client.get('/tracker/stats/detailed').then(r => setStats(r.data)).catch(()=>{}),
    ]).finally(() => setLoading(false))
  }, [])

  const deleteSaved = async (id) => {
    await client.delete(`/jobs/saved/${id}`)
    setSaved(s => s.filter(j=>j.id!==id))
    toast('Job removed','info')
  }

  const totalApps    = stats?.total || 0
  const responseRate = stats?.response_rate || 0
  const emailsSent   = stats?.emails_sent || 0
  const thisWeek     = stats?.this_week || 0
  const followUps    = stats?.follow_ups_due || []
  const recentEmails = stats?.recent_emails || []

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar/>
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">

        {/* Header */}
        <motion.div className="flex items-center justify-between mb-7"
          initial={{opacity:0,x:-12}} animate={{opacity:1,x:0}} transition={{duration:.28}}>
          <div>
            <h1 className="text-2xl font-bold">Welcome back, {user?.name?.split(' ')[0]} 👋</h1>
            <p className="text-slate-400 text-sm mt-1">Here's your job search overview</p>
          </div>
          <span className="px-3 py-1 bg-blue-900 text-blue-300 text-xs font-semibold rounded-full uppercase tracking-wide">
            {user?.role||'seeker'}
          </span>
        </motion.div>

        {/* Follow-up Alerts */}
        <AnimatePresence>
          {followUps.length > 0 && (
            <motion.div
              initial={{opacity:0,y:-10}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-10}}
              className="bg-amber-900/30 border border-amber-600/40 rounded-2xl p-4 mb-6 flex items-start gap-3">
              <Bell size={18} className="text-amber-400 mt-0.5 shrink-0"/>
              <div>
                <p className="text-amber-300 font-semibold text-sm">
                  {followUps.length} follow-up{followUps.length>1?'s':''} due!
                </p>
                <p className="text-amber-400/70 text-xs mt-0.5">
                  {followUps.map(f=>`${f.company} (${f.status})`).join(', ')}
                </p>
              </div>
              <button onClick={()=>navigate('/tracker')}
                className="ml-auto text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1 shrink-0">
                View<ArrowRight size={12}/>
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard delay={0}    icon="📋" value={totalApps}        label="Applications"   color="blue"    onClick={()=>navigate('/tracker')}/>
          <StatCard delay={0.07} icon="📈" value={`${responseRate}%`} label="Response Rate" color="emerald" sub={`${stats?.interviews||0} interviews`}/>
          <StatCard delay={0.14} icon="✉️"  value={emailsSent}       label="Emails Sent"    color="purple"  onClick={()=>navigate('/email')}/>
          <StatCard delay={0.21} icon="🗓️"  value={thisWeek}        label="This Week"       color="slate"   sub="new applications"/>
        </div>

        {/* Pipeline + Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">

          {/* Pipeline chart */}
          <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6"
            initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{delay:.2}}>
            <div className="flex items-center gap-2 mb-5">
              <TrendingUp size={17} className="text-blue-400"/>
              <h2 className="font-bold">Application Pipeline</h2>
              <button onClick={()=>navigate('/tracker')}
                className="ml-auto text-xs text-slate-400 hover:text-white flex items-center gap-1">
                View all<ArrowRight size={11}/>
              </button>
            </div>
            {loading
              ? <div className="space-y-3">{Array(4).fill(0).map((_,i)=>(
                  <div key={i} className="flex items-center gap-3">
                    <div className="h-3 bg-slate-700 rounded w-20 animate-pulse"/>
                    <div className="flex-1 h-2 bg-slate-700 rounded animate-pulse"/>
                  </div>
                ))}</div>
              : <PipelineBar pipeline={stats?.pipeline||{}} total={totalApps}/>
            }
          </motion.div>

          {/* Recent email activity */}
          <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6"
            initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{delay:.27}}>
            <div className="flex items-center gap-2 mb-5">
              <Mail size={17} className="text-purple-400"/>
              <h2 className="font-bold">Recent Emails</h2>
              <button onClick={()=>navigate('/email')}
                className="ml-auto text-xs text-slate-400 hover:text-white flex items-center gap-1">
                History<ArrowRight size={11}/>
              </button>
            </div>
            {recentEmails.length === 0
              ? <div className="text-slate-500 text-sm text-center py-6">No emails sent yet</div>
              : <div className="space-y-2.5">
                  {recentEmails.map((e,i) => (
                    <motion.div key={i}
                      initial={{opacity:0,x:8}} animate={{opacity:1,x:0}}
                      transition={{delay:.3+i*.05}}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-700/40 transition-colors">
                      <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${e.status==='sent'?'bg-emerald-500':'bg-red-500'}`}/>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate font-medium">{e.subject}</p>
                        <p className="text-xs text-slate-400 truncate">To: {e.to_email}</p>
                      </div>
                      <span className="text-xs text-slate-500 shrink-0">{e.sent_at?.substring(0,10)}</span>
                    </motion.div>
                  ))}
                </div>
            }
          </motion.div>
        </div>

        {/* Quick actions */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
          {[
            { label:'Search Jobs', sub:'Find your next role with AI matching', Icon:Search,   to:'/seeker',    gradient:'from-blue-700 to-blue-600 hover:from-blue-600 hover:to-blue-500',   delay:0.1  },
            { label:'App Tracker', sub:'Manage your pipeline & follow-ups',    Icon:Briefcase, to:'/tracker',   gradient:'from-emerald-700 to-emerald-600 hover:from-emerald-600 hover:to-emerald-500', delay:0.16 },
          ].map(({ label, sub, Icon, to, gradient, delay }) => (
            <motion.button key={to} onClick={()=>navigate(to)}
              initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{delay,duration:.3}}
              whileHover={{scale:1.02}} whileTap={{scale:.97}}
              className={`flex items-center gap-4 bg-gradient-to-r ${gradient} rounded-2xl p-5 transition-all text-left`}>
              <div className="w-11 h-11 bg-white/10 rounded-xl flex items-center justify-center">
                <Icon className="text-white" size={20}/>
              </div>
              <div>
                <div className="font-bold">{label}</div>
                <div className="text-white/70 text-sm">{sub}</div>
              </div>
              <ArrowRight size={16} className="ml-auto text-white/50"/>
            </motion.button>
          ))}
        </div>

        {/* Saved jobs table */}
        <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6"
          initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{delay:.3,duration:.3}}>
          <div className="flex items-center gap-2 mb-5">
            <Bookmark size={17} className="text-blue-400"/>
            <h2 className="font-bold">Saved Jobs</h2>
            <span className="ml-auto text-sm text-slate-400">{saved.length} jobs</span>
          </div>

          {saved.length===0 ? (
            <div className="text-center py-10 text-slate-500">
              <Bookmark size={36} className="mx-auto mb-3 opacity-30"/>
              <p>No saved jobs yet.</p>
              <button onClick={()=>navigate('/seeker')}
                className="mt-3 text-blue-400 hover:text-blue-300 text-sm">
                Search Jobs →
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto -mx-2 px-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    {['Title','Company','Location','Match','Saved',''].map(h=>(
                      <th key={h} className="pb-3 pr-4 font-medium text-xs">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {saved.map((j,i)=>(
                    <motion.tr key={j.id}
                      initial={{opacity:0,x:-8}} animate={{opacity:1,x:0}}
                      transition={{delay:i*.04,duration:.2}}
                      className="border-b border-slate-700/50 hover:bg-slate-700/20 transition-colors">
                      <td className="py-3 pr-4 font-medium max-w-xs"><div className="truncate">{j.title}</div></td>
                      <td className="py-3 pr-4 text-slate-300 max-w-xs"><div className="truncate">{j.company}</div></td>
                      <td className="py-3 pr-4 text-slate-400 text-xs">{j.location}</td>
                      <td className="py-3 pr-4">
                        {j.match_score ? <ScoreBadge score={j.match_score}/> : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="py-3 pr-4 text-xs text-slate-500">{j.saved_at?.substring(0,10)}</td>
                      <td className="py-3">
                        <div className="flex items-center gap-3">
                          {j.url && (
                            <a href={j.url} target="_blank" rel="noopener noreferrer"
                              className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-xs transition-colors">
                              <ExternalLink size={13}/>View
                            </a>
                          )}
                          <button onClick={()=>deleteSaved(j.id)} className="text-red-400 hover:text-red-300 transition-colors">
                            <Trash2 size={14}/>
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
