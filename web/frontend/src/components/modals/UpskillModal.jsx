import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, TrendingUp, BookOpen, CheckCircle2, ExternalLink, Loader2, Flame, Clock, Layers } from 'lucide-react'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

const PRIORITY_STYLE = {
  Critical: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  High: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  Medium: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  Low: 'bg-slate-700/40 text-slate-300 border-slate-600/40',
}

export default function UpskillModal({ isOpen, onClose, jobs = [] }) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [plan, setPlan] = useState(null)
  const [activeTab, setActiveTab] = useState('heatmap') // 'heatmap' | 'sequence'

  useEffect(() => {
    if (isOpen) {
      loadPlan()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  const loadPlan = async () => {
    setLoading(true)
    try {
      const payloadJobs = (jobs || []).slice(0, 50).map(j => ({
        title: j.title || '',
        company: j.company || '',
        description: j.description || '',
        score: j.score ?? null,
      }))
      const { data } = await client.post('/power/upskill-plan', { jobs: payloadJobs })
      setPlan(data)
    } catch {
      toast('Could not generate Upskill Plan', 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          onClick={e => e.stopPropagation()}
          className="glass-dropdown rounded-3xl w-full max-w-4xl max-h-[88vh] overflow-hidden flex flex-col border border-white/[0.1] shadow-2xl relative"
        >
          <div className="glow-line-top" />

          {/* Header */}
          <div className="p-6 border-b border-white/[0.08] flex items-center justify-between gap-4 bg-slate-950/60">
            <div className="space-y-1 min-w-0">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[10px] font-extrabold uppercase tracking-wider">
                <TrendingUp size={11} /> Aggregate Skill-Gap Heatmap &amp; Learning Roadmap
              </div>
              <h3 className="font-black text-lg sm:text-xl text-white tracking-tight">
                Market Demand vs. <span className="text-gradient-blue">Your Active CV</span>
              </h3>
              <p className="text-xs text-slate-400">
                Weighted by <code className="text-slate-300">(100 - fit_score) / 100</code> across your searched, saved, and tracked roles.
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 hover:text-white transition cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>

          {/* Tabs */}
          <div className="px-6 pt-3 pb-2 border-b border-white/[0.06] bg-slate-950/30 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab('heatmap')}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 transition cursor-pointer ${
                activeTab === 'heatmap'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/25'
                  : 'bg-white/[0.03] hover:bg-white/[0.07] text-slate-400 hover:text-white border border-white/[0.06]'
              }`}
            >
              <Flame size={13} />
              <span>Skill-Gap Heatmap ({plan?.gap_heatmap?.length || 0})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('sequence')}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 transition cursor-pointer ${
                activeTab === 'sequence'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/25'
                  : 'bg-white/[0.03] hover:bg-white/[0.07] text-slate-400 hover:text-white border border-white/[0.06]'
              }`}
            >
              <BookOpen size={13} />
              <span>Study Sequence &amp; CV Strengths</span>
            </button>
          </div>

          {/* Content */}
          <div className="p-6 overflow-y-auto flex-1 space-y-5">
            {loading || !plan ? (
              <div className="py-14 text-center space-y-3">
                <Loader2 size={28} className="animate-spin text-blue-400 mx-auto" />
                <p className="text-sm font-bold text-white">Computing Weighted Skill-Gap Heatmap...</p>
                <p className="text-xs text-slate-400">Diffing target job descriptions against your uploaded CV.</p>
              </div>
            ) : (
              <>
                {/* Summary KPIs */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="glass-card rounded-2xl p-3.5 border border-white/[0.07]">
                    <div className="text-xl font-black text-white">{plan.summary?.jobs_analyzed || 0}</div>
                    <div className="text-[11px] text-slate-400 font-semibold">Jobs Analyzed</div>
                  </div>
                  <div className="glass-card rounded-2xl p-3.5 border border-emerald-500/25">
                    <div className="text-xl font-black text-emerald-400">{plan.summary?.cv_skills_count || 0}</div>
                    <div className="text-[11px] text-slate-400 font-semibold">CV Skills Detected</div>
                  </div>
                  <div className="glass-card rounded-2xl p-3.5 border border-rose-500/25">
                    <div className="text-xl font-black text-rose-400">{plan.summary?.critical_gaps_count || 0}</div>
                    <div className="text-[11px] text-slate-400 font-semibold">Critical / High Gaps</div>
                  </div>
                  <div className="glass-card rounded-2xl p-3.5 border border-indigo-500/25">
                    <div className="text-xl font-black text-indigo-300">{plan.summary?.total_study_hours || 0}h</div>
                    <div className="text-[11px] text-slate-400 font-semibold">Focused Study Plan</div>
                  </div>
                </div>

                {activeTab === 'heatmap' ? (
                  plan.gap_heatmap?.length > 0 ? (
                    <div className="space-y-3">
                      {plan.gap_heatmap.map((item, idx) => (
                        <div key={item.skill} className="glass-card rounded-2xl p-4 border border-white/[0.07] space-y-2.5">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-black text-slate-400">#{idx + 1}</span>
                              <span className="text-sm font-black text-white uppercase tracking-wide">{item.skill}</span>
                              <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-md border ${PRIORITY_STYLE[item.priority] || PRIORITY_STYLE.Low}`}>
                                {item.priority}
                              </span>
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-white/[0.05] text-slate-300 border border-white/[0.07]">
                                {item.category}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                              <span className="text-slate-300 font-bold">{item.job_count} jobs ({item.job_pct}%)</span>
                              <span className="text-[11px] text-slate-500 flex items-center gap-1">
                                <Clock size={11} /> ~{item.estimated_hours}h
                              </span>
                            </div>
                          </div>

                          {/* Demand Progress Bar */}
                          <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 rounded-full"
                              style={{ width: `${Math.min(100, Math.max(8, item.job_pct))}%` }}
                            />
                          </div>

                          <p className="text-xs text-slate-200 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-white/[0.05]">
                            <strong className="text-blue-400 mr-1.5">Tailored Study Direction:</strong>
                            {item.tailored_direction}
                          </p>

                          <div className="flex items-center justify-between gap-2 flex-wrap pt-0.5 text-[11px]">
                            <div className="text-slate-400">
                              <span className="font-semibold text-emerald-300">CV Proof Milestone:</span> {item.milestone_project}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              {(item.resources || []).map((r, i) => (
                                <a
                                  key={i}
                                  href={r.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="px-2.5 py-1 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] text-blue-300 font-semibold flex items-center gap-1 transition"
                                >
                                  <span>{i === 0 ? 'Official Docs' : 'Roadmap'}</span>
                                  <ExternalLink size={10} />
                                </a>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-10 text-center text-slate-400 text-xs">
                      Run a job search or save jobs first to compute your personalized Skill-Gap Heatmap.
                    </div>
                  )
                ) : (
                  <div className="space-y-4">
                    {/* Study Sequence */}
                    <div className="glass-card rounded-2xl p-5 border border-white/[0.07] space-y-3">
                      <h4 className="text-xs font-extrabold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                        <Layers size={14} /> Recommended Study Order (Foundational → Advanced)
                      </h4>
                      <div className="space-y-2.5">
                        {(plan.study_order || []).map(st => (
                          <div key={st.step} className="p-3 rounded-xl bg-slate-950/60 border border-white/[0.05] flex items-start justify-between gap-3">
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[10px] font-black flex items-center justify-center">
                                  {st.step}
                                </span>
                                <span className="text-xs font-black text-white uppercase">{st.skill}</span>
                                <span className="text-[10px] text-slate-400 font-semibold">~{st.estimated_hours} hrs</span>
                              </div>
                              <p className="text-xs text-slate-300 pl-7">{st.goal}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Strongest Matched Skills */}
                    {plan.strongest_matched?.length > 0 && (
                      <div className="glass-card rounded-2xl p-5 border border-emerald-500/25 space-y-3">
                        <h4 className="text-xs font-extrabold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                          <CheckCircle2 size={14} /> Your Strongest Market-Aligned CV Skills
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {plan.strongest_matched.map(m => (
                            <span
                              key={m.skill}
                              className="px-3 py-1 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 text-xs font-bold"
                            >
                              ✓ {m.skill.toUpperCase()} ({m.job_count} jobs)
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
