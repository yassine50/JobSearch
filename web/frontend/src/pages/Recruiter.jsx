import { useState } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import client from '../api/client.js'
import { Users, ExternalLink, BarChart2, AlertTriangle } from 'lucide-react'

const STEPS = ['🔍 Building queries...','📡 Searching LinkedIn...','🤖 Ranking candidates...']

export default function Recruiter() {
  const [form, setForm] = useState({ job_title:'', location:'', job_description:'', required_skills:'', max_results:30 })
  const [candidates, setCandidates] = useState([])
  const [skillsUsed, setSkillsUsed] = useState([])
  const [loading, setLoading] = useState(false)
  const [stepIdx, setStepIdx] = useState(0)
  const [error, setError]     = useState('')
  const [modal, setModal]     = useState(null)

  const search = async () => {
    if (!form.job_title.trim() || !form.job_description.trim()) return
    setLoading(true); setCandidates([]); setError(''); setStepIdx(0)
    const iv = setInterval(() => setStepIdx(i => (i+1) % STEPS.length), 3000)
    try {
      const { data } = await client.post('/recruiter/search', { ...form, max_results: Number(form.max_results) })
      setCandidates(data.candidates)
      setSkillsUsed(data.skills_used || [])
    } catch(e) { setError(e.response?.data?.detail || 'Search failed. Is the backend running?') }
    clearInterval(iv); setLoading(false)
  }

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="ml-60 flex-1 p-8">
        <h1 className="text-2xl font-bold mb-6">👔 Recruiter Mode</h1>

        {/* Form */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6 fade-in">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Job Title *</label>
              <input value={form.job_title} onChange={e=>setForm({...form,job_title:e.target.value})}
                placeholder="e.g. Senior Python Developer"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Location</label>
              <input value={form.location} onChange={e=>setForm({...form,location:e.target.value})}
                placeholder="e.g. London, Paris, Remote"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Max Candidates</label>
              <select value={form.max_results} onChange={e=>setForm({...form,max_results:e.target.value})}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition">
                {[10,20,30,50].map(n=><option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
          <div className="mb-4">
            <label className="text-xs text-slate-400 mb-1 block">Required Skills <span className="text-slate-500">(comma-separated, optional)</span></label>
            <input value={form.required_skills} onChange={e=>setForm({...form,required_skills:e.target.value})}
              placeholder="e.g. Python, FastAPI, AWS, Docker"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition" />
          </div>
          <div className="mb-5">
            <label className="text-xs text-slate-400 mb-1 block">Job Description * <span className="text-slate-500">(paste the full JD for best AI results)</span></label>
            <textarea value={form.job_description} onChange={e=>setForm({...form,job_description:e.target.value})}
              rows={6} placeholder="Paste the full job description here..."
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition resize-none" />
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <button onClick={search} disabled={loading || !form.job_title.trim() || !form.job_description.trim()}
              className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold px-7 py-2.5 rounded-lg transition text-sm">
              {loading ? <LoadingSpinner label={STEPS[stepIdx]} /> : <><Users size={16} /> Search Candidates</>}
            </button>
            {skillsUsed.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-slate-400">Skills detected:</span>
                {skillsUsed.map(s=>(
                  <span key={s} className="bg-slate-700 text-xs px-2 py-0.5 rounded text-slate-300">{s}</span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Error */}
        {error && <div className="bg-red-900/60 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3 mb-4">{error}</div>}

        {/* Results */}
        {candidates.length > 0 && (
          <div className="fade-in">
            <h2 className="font-bold text-lg mb-4">
              Candidates <span className="text-slate-400 font-normal text-base">({candidates.length} found)</span>
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {candidates.map((c,i) => (
                <div key={i} className="bg-slate-800 border border-slate-700 hover:border-slate-500 rounded-2xl p-5 transition fade-in flex flex-col">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0 mr-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold text-sm">{c.name}</span>
                        {c.available && <span className="text-xs bg-emerald-900 text-emerald-400 border border-emerald-700 px-1.5 py-0.5 rounded-full">🟢 Open</span>}
                        {c.seniority_gap && <span className="text-xs bg-yellow-900 text-yellow-400 border border-yellow-700 px-1.5 py-0.5 rounded-full flex items-center gap-0.5"><AlertTriangle size={10} />Seniority</span>}
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{c.headline}</p>
                    </div>
                    <ScoreBadge score={c.score} />
                  </div>

                  {/* Snippet */}
                  <p className="text-xs text-slate-500 mb-3 line-clamp-3 flex-1">{c.snippet}</p>

                  {/* Matched skills */}
                  {c.matched_skills?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      {c.matched_skills.slice(0,4).map(s=>(
                        <span key={s} className="bg-emerald-900 text-emerald-300 text-xs px-1.5 py-0.5 rounded-full">{s}</span>
                      ))}
                      {c.matched_skills.length > 4 && <span className="text-xs text-slate-500">+{c.matched_skills.length-4}</span>}
                    </div>
                  )}

                  {/* Missing */}
                  {c.missing_skills?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-3">
                      {c.missing_skills.slice(0,3).map(s=>(
                        <span key={s} className="bg-red-950 text-red-400 text-xs px-1.5 py-0.5 rounded-full">✗ {s}</span>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2 mt-auto pt-2">
                    <a href={c.url} target="_blank" rel="noopener noreferrer"
                      className="flex-1 flex items-center justify-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-xs py-2 rounded-lg transition">
                      <ExternalLink size={13} /> Profile
                    </a>
                    <button onClick={() => setModal(c)}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-purple-900 hover:bg-purple-800 text-purple-300 text-xs py-2 rounded-lg transition">
                      <BarChart2 size={13} /> Breakdown
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
      <ScoreModal item={modal} onClose={() => setModal(null)} mode="recruiter" />
    </div>
  </PageWrapper>
  )
}
