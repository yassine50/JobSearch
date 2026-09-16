import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import client from '../api/client.js'
import { Search, Users, Bookmark, FileText, Trash2, ExternalLink } from 'lucide-react'

function StatCard({ icon, value, label, sub, color = 'blue' }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 hover:-translate-y-0.5 transition-transform fade-in">
      <div className="text-3xl mb-3">{icon}</div>
      <div className={`text-2xl font-bold text-${color}-400`}>{value}</div>
      <div className="text-slate-300 text-sm font-medium mt-0.5">{label}</div>
      {sub && <div className="text-slate-500 text-xs mt-0.5 truncate">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate  = useNavigate()
  const [saved, setSaved]   = useState([])
  const [cvInfo, setCvInfo] = useState({ uploaded: false })

  useEffect(() => {
    client.get('/jobs/saved').then(r => setSaved(r.data)).catch(() => {})
    client.get('/cv/info').then(r => setCvInfo(r.data)).catch(() => {})
  }, [])

  const deleteSaved = async (id) => {
    await client.delete(`/jobs/saved/${id}`)
    setSaved(s => s.filter(j => j.id !== id))
  }

  return (
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="ml-60 flex-1 p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">Welcome back, {user?.name?.split(' ')[0]} 👋</h1>
            <p className="text-slate-400 text-sm mt-1">Here's your job search overview</p>
          </div>
          <span className="px-3 py-1 bg-blue-900 text-blue-300 text-xs font-semibold rounded-full uppercase tracking-wide">
            {user?.role || 'seeker'}
          </span>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard icon="💾" value={saved.length} label="Saved Jobs" color="blue" />
          <StatCard icon="📄" value={cvInfo.uploaded ? '✓' : '—'}
            label="CV Status" sub={cvInfo.uploaded ? cvInfo.filename : 'No CV uploaded'} color="emerald" />
          <StatCard icon="📝" value={cvInfo.words ?? '—'} label="CV Words" color="purple" />
          <StatCard icon="📅" value={user?.created_at?.substring(0,10) ?? '—'} label="Member Since" color="slate" />
        </div>

        {/* Quick actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          <button onClick={() => navigate('/seeker')}
            className="flex items-center gap-4 bg-gradient-to-r from-blue-700 to-blue-600 hover:from-blue-600 hover:to-blue-500 rounded-2xl p-6 transition text-left fade-in">
            <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center"><Search className="text-white" size={22} /></div>
            <div>
              <div className="font-bold text-lg">Search Jobs</div>
              <div className="text-blue-200 text-sm">Find your next opportunity with AI matching</div>
            </div>
          </button>
          <button onClick={() => navigate('/recruiter')}
            className="flex items-center gap-4 bg-gradient-to-r from-purple-700 to-purple-600 hover:from-purple-600 hover:to-purple-500 rounded-2xl p-6 transition text-left fade-in">
            <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center"><Users className="text-white" size={22} /></div>
            <div>
              <div className="font-bold text-lg">Find Candidates</div>
              <div className="text-purple-200 text-sm">Source and rank top candidates with AI</div>
            </div>
          </button>
        </div>

        {/* Saved jobs table */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in">
          <div className="flex items-center gap-2 mb-5">
            <Bookmark size={18} className="text-blue-400" />
            <h2 className="font-bold text-lg">Saved Jobs</h2>
          </div>

          {saved.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Bookmark size={40} className="mx-auto mb-3 opacity-30" />
              <p>No saved jobs yet.</p>
              <p className="text-sm mt-1">Search for jobs and save the ones you like!</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    <th className="pb-3 pr-4 font-medium">Title</th>
                    <th className="pb-3 pr-4 font-medium">Company</th>
                    <th className="pb-3 pr-4 font-medium">Location</th>
                    <th className="pb-3 pr-4 font-medium">Match</th>
                    <th className="pb-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {saved.map(j => (
                    <tr key={j.id} className="border-b border-slate-700/50 hover:bg-slate-700/20 transition">
                      <td className="py-3 pr-4 font-medium max-w-xs truncate">{j.title}</td>
                      <td className="py-3 pr-4 text-slate-300 max-w-xs truncate">{j.company}</td>
                      <td className="py-3 pr-4 text-slate-400 text-xs">{j.location}</td>
                      <td className="py-3 pr-4">
                        {j.match_score ? <ScoreBadge score={j.match_score} /> : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-3">
                          {j.url && (
                            <a href={j.url} target="_blank" rel="noopener noreferrer"
                              className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-xs transition">
                              <ExternalLink size={13} /> View
                            </a>
                          )}
                          <button onClick={() => deleteSaved(j.id)}
                            className="text-red-400 hover:text-red-300 transition">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
