
import { X } from 'lucide-react'

function Bar({ label, value, color }) {
  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-slate-300">{label}</span>
        <span className="font-bold" style={{ color }}>{value ?? 0}%</span>
      </div>
      <div className="bg-slate-700 rounded-full h-2">
        <div className="h-2 rounded-full transition-all duration-700"
             style={{ width: `${value ?? 0}%`, background: color }} />
      </div>
    </div>
  )
}

export default function ScoreModal({ item, onClose, mode = 'seeker' }) {
  if (!item) return null
  const bd = item.breakdown || {}

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-6 fade-in"
           onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex justify-between items-start mb-5">
          <div>
            <h3 className="font-bold text-lg">{item.title || item.name}</h3>
            <p className="text-slate-400 text-sm">{item.company || item.headline}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-sm font-bold px-3 py-1 rounded-full border ${
              item.score >= 70 ? 'bg-emerald-900 text-emerald-300 border-emerald-700'
              : item.score >= 40 ? 'bg-yellow-900 text-yellow-300 border-yellow-700'
              : 'bg-red-900 text-red-300 border-red-700'}`}>
              {item.score}% Match
            </span>
            <button onClick={onClose} className="text-slate-400 hover:text-white transition">
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Score bars */}
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
            <Bar label="⚙️ Skill Recall"   value={bd.skill_score}    color="#3b82f6" />
            <Bar label="🏷️ Title/Seniority" value={bd.title_score}   color="#8b5cf6" />
            <Bar label="🔑 Keyword Density" value={bd.keyword_score} color="#10b981" />
            <Bar label="📍 Location"        value={bd.location_score} color="#f59e0b" />
          </>
        )}

        {/* Matched skills */}
        {item.matched_skills?.length > 0 && (
          <div className="mt-4 mb-3">
            <p className="text-xs text-slate-400 mb-2">✅ Matched Skills</p>
            <div className="flex flex-wrap gap-1.5">
              {item.matched_skills.map(s => (
                <span key={s} className="bg-emerald-900 text-emerald-300 text-xs px-2 py-0.5 rounded-full">{s}</span>
              ))}
            </div>
          </div>
        )}

        {/* Missing skills */}
        {item.missing_skills?.length > 0 && (
          <div className="mb-3">
            <p className="text-xs text-slate-400 mb-2">❌ Missing Skills</p>
            <div className="flex flex-wrap gap-1.5">
              {item.missing_skills.map(s => (
                <span key={s} className="bg-red-900 text-red-300 text-xs px-2 py-0.5 rounded-full">{s}</span>
              ))}
            </div>
          </div>
        )}

        {/* Tips */}
        {item.tips?.length > 0 && (
          <div className="border-t border-slate-700 pt-4 mt-2">
            <p className="text-xs text-slate-400 mb-2">💡 Tips to Improve</p>
            <ul className="space-y-1.5">
              {item.tips.map((t, i) => (
                <li key={i} className="text-sm text-slate-300 flex gap-2">
                  <span className="text-blue-400 mt-0.5">•</span><span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
