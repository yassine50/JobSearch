import { motion, AnimatePresence } from 'framer-motion'
import { X, Sparkles, CheckCircle2, AlertTriangle, Lightbulb } from 'lucide-react'
import ScoreBadge from './ScoreBadge'

function Bar({ label, value, color }) {
  const safeVal = Math.max(0, Math.min(100, value ?? 0))
  return (
    <div className="mb-3.5">
      <div className="flex justify-between items-center text-xs mb-1.5">
        <span className="text-slate-300 font-semibold">{label}</span>
        <span className="font-extrabold px-2 py-0.5 rounded-md bg-white/[0.03] border border-white/[0.06]" style={{ color }}>
          {safeVal}%
        </span>
      </div>
      <div className="bg-slate-900/90 border border-white/[0.05] rounded-full h-2 overflow-hidden p-0.5">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${safeVal}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          className="h-full rounded-full"
          style={{ background: color, boxShadow: `0 0 10px ${color}66` }}
        />
      </div>
    </div>
  )
}

export default function ScoreModal({ item, onClose, mode = 'seeker' }) {
  if (!item) return null
  const bd = item.breakdown || {}

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
          transition={{ type: 'spring', stiffness: 360, damping: 28 }}
          className="glass-dropdown glow-line-top rounded-3xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-6 shadow-2xl border border-white/[0.1]"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex justify-between items-start gap-4 mb-6 pb-4 border-b border-white/[0.06]">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300 text-[10px] font-bold uppercase tracking-widest mb-2">
                <Sparkles size={11} /> AI Match Breakdown
              </div>
              <h3 className="font-extrabold text-lg text-white tracking-tight truncate">{item.title || item.name}</h3>
              <p className="text-slate-400 text-xs mt-0.5 truncate">{item.company || item.headline}</p>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <ScoreBadge score={item.score ?? 0} />
              <button
                onClick={onClose}
                className="p-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 hover:text-white transition cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Score bars */}
          <div className="glass-card rounded-2xl p-4 border border-white/[0.06] mb-5">
            {mode === 'seeker' ? (
              <>
                <Bar label="⚙️ Tech Skills"    value={bd.tech_score}      color="#3b82f6" />
                <Bar label="📖 Semantic Match" value={bd.semantic_score}  color="#8b5cf6" />
                <Bar label="🏷️ Role / Title"   value={bd.title_score}     color="#10b981" />
                <Bar label="🤝 Soft Skills"    value={bd.soft_score}      color="#f59e0b" />
                <Bar label="🏢 Domain Fit"     value={bd.domain_score}    color="#06b6d4" />
                <Bar label="🎓 Education"      value={bd.edu_score}       color="#ec4899" />
              </>
            ) : (
              <>
                <Bar label="⚙️ Skill Recall"    value={bd.skill_score}    color="#3b82f6" />
                <Bar label="🏷️ Title/Seniority" value={bd.title_score}    color="#8b5cf6" />
                <Bar label="🔑 Keyword Density" value={bd.keyword_score}  color="#10b981" />
                <Bar label="📍 Location Fit"    value={bd.location_score} color="#f59e0b" />
              </>
            )}
          </div>

          {/* Matched skills */}
          {item.matched_skills?.length > 0 && (
            <div className="mb-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
                <CheckCircle2 size={13} /> Matched Skills ({item.matched_skills.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {item.matched_skills.map(s => (
                  <span key={s} className="bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-xs font-medium px-2.5 py-1 rounded-lg">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Missing skills */}
          {item.missing_skills?.length > 0 && (
            <div className="mb-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-rose-400 mb-2 flex items-center gap-1.5">
                <AlertTriangle size={13} /> Missing Skills ({item.missing_skills.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {item.missing_skills.map(s => (
                  <span key={s} className="bg-rose-500/10 border border-rose-500/25 text-rose-300 text-xs font-medium px-2.5 py-1 rounded-lg">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Tips */}
          {item.tips?.length > 0 && (
            <div className="border-t border-white/[0.06] pt-4 mt-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-amber-300 mb-2.5 flex items-center gap-1.5">
                <Lightbulb size={13} /> Actionable Tips
              </p>
              <ul className="space-y-2">
                {item.tips.map((t, i) => (
                  <li key={i} className="text-xs text-slate-300 flex gap-2.5 bg-white/[0.02] border border-white/[0.05] rounded-xl p-2.5 leading-relaxed">
                    <span className="text-blue-400 font-bold">•</span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
