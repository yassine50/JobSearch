import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import client from '../api/client.js'
import { Search, Users, Bookmark, Trash2, ExternalLink } from 'lucide-react'

function StatCard({ icon, value, label, sub, color='blue', delay=0 }) {
  return (
    <motion.div initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{delay,duration:.3}}
      className="bg-slate-800 border border-slate-700 rounded-2xl p-6 hover:-translate-y-0.5 transition-transform">
      <div className="text-3xl mb-3">{icon}</div>
      <div className={`text-2xl font-bold text-${color}-400`}>{value}</div>
      <div className="text-slate-300 text-sm font-medium mt-0.5">{label}</div>
      {sub && <div className="text-slate-500 text-xs mt-0.5 truncate">{sub}</div>}
    </motion.div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [saved, setSaved]   = useState([])
  const [cvInfo, setCvInfo] = useState({ uploaded:false })

  useEffect(() => {
    client.get('/jobs/saved').then(r=>setSaved(r.data)).catch(()=>{})
    client.get('/cv/info').then(r=>setCvInfo(r.data)).catch(()=>{})
  }, [])

  const deleteSaved = async (id) => {
    await client.delete(`/jobs/saved/${id}`)
    setSaved(s => s.filter(j=>j.id!==id))
    toast('Job removed','info')
  }

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-slate-900">
        <Sidebar/>
        <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">
          <motion.div className="flex items-center justify-between mb-8"
            initial={{opacity:0,x:-12}} animate={{opacity:1,x:0}} transition={{duration:.28}}>
            <div>
              <h1 className="text-2xl font-bold">Welcome back, {user?.name?.split(' ')[0]} 👋</h1>
              <p className="text-slate-400 text-sm mt-1">Here's your job search overview</p>
            </div>
            <span className="px-3 py-1 bg-blue-900 text-blue-300 text-xs font-semibold rounded-full uppercase tracking-wide">
              {user?.role||'seeker'}
            </span>
          </motion.div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard delay={0}    icon="💾" value={saved.length}             label="Saved Jobs"   color="blue"   />
            <StatCard delay={0.07} icon="📄" value={cvInfo.uploaded?'✓':'—'} label="CV Status"    color="emerald" sub={cvInfo.uploaded?cvInfo.filename:'No CV uploaded'}/>
            <StatCard delay={0.14} icon="📝" value={cvInfo.words??'—'}       label="CV Words"     color="purple"  />
            <StatCard delay={0.21} icon="📅" value={user?.created_at?.substring(0,10)??'—'} label="Member Since" color="slate"/>
          </div>

          {/* Quick actions */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
            {[
              { label:'Search Jobs', sub:'Find your next opportunity with AI', Icon:Search, to:'/seeker', gradient:'from-blue-700 to-blue-600 hover:from-blue-600 hover:to-blue-500', delay:0.1 },
              { label:'Find Candidates', sub:'Source & rank top candidates', Icon:Users, to:'/recruiter', gradient:'from-purple-700 to-purple-600 hover:from-purple-600 hover:to-purple-500', delay:0.18 },
            ].map(({ label, sub, Icon, to, gradient, delay }) => (
              <motion.button key={to} onClick={()=>navigate(to)}
                initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{delay,duration:.3}}
                whileHover={{scale:1.02}} whileTap={{scale:.97}}
                className={`flex items-center gap-4 bg-gradient-to-r ${gradient} rounded-2xl p-6 transition-all text-left`}>
                <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center">
                  <Icon className="text-white" size={22}/>
                </div>
                <div>
                  <div className="font-bold text-lg">{label}</div>
                  <div className="text-white/70 text-sm">{sub}</div>
                </div>
              </motion.button>
            ))}
          </div>

          {/* Saved jobs */}
          <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6"
            initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{delay:.25,duration:.3}}>
            <div className="flex items-center gap-2 mb-5">
              <Bookmark size={18} className="text-blue-400"/>
              <h2 className="font-bold text-lg">Saved Jobs</h2>
              <span className="ml-auto text-sm text-slate-400">{saved.length} jobs</span>
            </div>

            {saved.length===0 ? (
              <div className="text-center py-12 text-slate-500">
                <Bookmark size={40} className="mx-auto mb-3 opacity-30"/>
                <p>No saved jobs yet.</p>
                <p className="text-sm mt-1">Search for jobs and save the ones you like!</p>
              </div>
            ) : (
              <div className="overflow-x-auto -mx-2 px-2">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-400 text-left border-b border-slate-700">
                      {['Title','Company','Location','Match','Saved','Actions'].map(h=>(
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
