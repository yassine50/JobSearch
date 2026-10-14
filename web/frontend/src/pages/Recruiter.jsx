import { useState } from 'react'
import { motion } from 'framer-motion'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import client from '../api/client.js'
import { Users, ExternalLink, BarChart2, AlertTriangle, Sparkles } from 'lucide-react'

const STEPS = ['🔍 Building queries...', '📡 Searching LinkedIn...', '🤖 Ranking candidates...']

export default function Recruiter() {
  const [form, setForm] = useState({ job_title: '', location: '', job_description: '', required_skills: '', max_results: 30 })
  const [candidates, setCandidates] = useState([])
  const [skillsUsed, setSkillsUsed] = useState([])
  const [loading, setLoading] = useState(false)
  const [stepIdx, setStepIdx] = useState(0)
  const [error, setError]     = useState('')
  const [modal, setModal]     = useState(null)

  const search = async () => {
    if (!form.job_title.trim() || !form.job_description.trim()) return
    setLoading(true); setCandidates([]); setError(''); setStepIdx(0)
    const iv = setInterval(() => setStepIdx(i => (i + 1) % STEPS.length), 3000)
    try {
      const { data } = await client.post('/recruiter/search', { ...form, max_results: Number(form.max_results) })
      setCandidates(data.candidates)
      setSkillsUsed(data.skills_used || [])
    } catch (e) {
      setError(e.response?.data?.detail || 'Search failed. Is the backend running?')
    }
    clearInterval(iv); setLoading(false)
  }

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14 w-full">

          {/* Hero Header */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-panel rounded-3xl p-6 mb-6 relative overflow-hidden"
          >
            <div className="glow-line-top" />
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300 text-[11px] font-bold mb-1.5">
              <Sparkles size={11} className="text-amber-400" />
              <span>AI Talent Sourcing Engine</span>
            </div>
            <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white">
              Recruiter <span className="text-gradient-blue">Talent Radar</span>
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Source and rank active LinkedIn candidates against your job description with multi-factor AI scoring.
            </p>
          </motion.div>

          {/* Search Studio Form */}
          <div className="glass-panel rounded-3xl p-6 mb-6 fade-in relative overflow-hidden">
            <div className="glow-line-top" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="text-xs font-bold text-slate-300 mb-1.5 block">Job Title *</label>
                <input
                  value={form.job_title}
                  onChange={e => setForm({ ...form, job_title: e.target.value })}
                  placeholder="e.g. Senior Python Developer"
                  className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-300 mb-1.5 block">Location</label>
                <input
                  value={form.location}
                  onChange={e => setForm({ ...form, location: e.target.value })}
                  placeholder="e.g. London, Paris, Remote"
                  className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-300 mb-1.5 block">Max Candidates</label>
                <select
                  value={form.max_results}
                  onChange={e => setForm({ ...form, max_results: e.target.value })}
                  className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm cursor-pointer"
                >
                  {[10, 20, 30, 50].map(n => <option key={n} value={n}>{n} candidates</option>)}
                </select>
              </div>
            </div>
            <div className="mb-4">
              <label className="text-xs font-bold text-slate-300 mb-1.5 block">
                Required Skills <span className="text-slate-500 font-normal">(comma-separated, optional)</span>
              </label>
              <input
                value={form.required_skills}
                onChange={e => setForm({ ...form, required_skills: e.target.value })}
                placeholder="e.g. Python, FastAPI, AWS, Docker"
                className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm"
              />
            </div>
            <div className="mb-5">
              <label className="text-xs font-bold text-slate-300 mb-1.5 block">
                Job Description * <span className="text-slate-500 font-normal">(paste the full JD for best AI results)</span>
              </label>
              <textarea
                value={form.job_description}
                onChange={e => setForm({ ...form, job_description: e.target.value })}
                rows={6}
                placeholder="Paste the full job description here..."
                className="w-full glass-input rounded-xl px-3.5 py-2.5 text-sm resize-none"
              />
            </div>

            <div className="flex items-center gap-4 flex-wrap">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={search}
                disabled={loading || !form.job_title.trim() || !form.job_description.trim()}
                className="shimmer-btn flex items-center gap-2 bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 disabled:opacity-50 text-white font-extrabold px-7 py-2.5 rounded-xl transition text-xs shadow-lg shadow-purple-600/25 cursor-pointer"
              >
                {loading ? <LoadingSpinner label={STEPS[stepIdx]} /> : <><Users size={15} /> Search Candidates</>}
              </motion.button>
              {skillsUsed.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-slate-400">Skills detected:</span>
                  {skillsUsed.map(s => (
                    <span key={s} className="bg-purple-500/15 border border-purple-500/30 text-xs px-2.5 py-0.5 rounded-lg text-purple-300 font-semibold">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-rose-950/60 border border-rose-500/40 text-rose-300 text-xs font-semibold rounded-2xl px-4 py-3 mb-4">
              {error}
            </div>
          )}

          {/* Results */}
          {candidates.length > 0 && (
            <div className="fade-in">
              <h2 className="font-extrabold text-lg mb-4 text-white">
                Ranked Candidates <span className="text-slate-400 font-semibold text-sm">({candidates.length} found)</span>
              </h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
                {candidates.map((c, i) => (
                  <div key={i} className="glass-card card-hover rounded-2xl p-5 flex flex-col">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-2.5">
                      <div className="flex-1 min-w-0 mr-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-extrabold text-sm text-white">{c.name}</span>
                          {c.available && (
                            <span className="text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/35 px-2 py-0.5 rounded-full">
                              🟢 Open
                            </span>
                          )}
                          {c.seniority_gap && (
                            <span className="text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/35 px-2 py-0.5 rounded-full flex items-center gap-0.5">
                              <AlertTriangle size={10} /> Seniority
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-blue-300/90 font-medium mt-0.5 line-clamp-2">{c.headline}</p>
                      </div>
                      <ScoreBadge score={c.score} />
                    </div>

                    {/* Snippet */}
                    <p className="text-xs text-slate-400 mb-3 line-clamp-3 flex-1 leading-relaxed">{c.snippet}</p>

                    {/* Matched skills */}
                    {c.matched_skills?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1.5">
                        {c.matched_skills.slice(0, 4).map(s => (
                          <span key={s} className="bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[10px] font-semibold px-2 py-0.5 rounded-lg">
                            ✓ {s}
                          </span>
                        ))}
                        {c.matched_skills.length > 4 && (
                          <span className="text-[10px] text-slate-500 font-medium">+{c.matched_skills.length - 4}</span>
                        )}
                      </div>
                    )}

                    {/* Missing */}
                    {c.missing_skills?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-3">
                        {c.missing_skills.slice(0, 3).map(s => (
                          <span key={s} className="bg-rose-500/15 border border-rose-500/30 text-rose-300 text-[10px] font-semibold px-2 py-0.5 rounded-lg">
                            ✗ {s}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-2 mt-auto pt-3 border-t border-white/[0.06]">
                      <a
                        href={c.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 flex items-center justify-center gap-1.5 bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] text-xs font-bold py-2 rounded-xl transition"
                      >
                        <ExternalLink size={13} /> Profile
                      </a>
                      <button
                        onClick={() => setModal(c)}
                        className="flex-1 flex items-center justify-center gap-1.5 bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/35 text-purple-300 text-xs font-bold py-2 rounded-xl transition cursor-pointer"
                      >
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
