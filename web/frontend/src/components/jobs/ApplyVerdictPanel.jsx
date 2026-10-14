import { useState, useEffect } from 'react'
import {
  Scale, Loader2, ShieldCheck, ShieldAlert, AlertTriangle, CheckCircle2, XCircle,
  HelpCircle, Plane, DollarSign, Target, KeyRound, MessageSquare, Radio
} from 'lucide-react'
import client from '../../api/client.js'

/**
 * "Should I apply?" — career-ops A–G evaluation for one posting.
 * Calls POST /api/jobs/evaluate: CV match, work authorization, comp,
 * posting legitimacy (ghost / scam / repost) + live "still open?" check.
 */
const VERDICT_STYLE = {
  apply: { box: 'bg-emerald-950/50 border-emerald-700/70', text: 'text-emerald-300', Icon: CheckCircle2 },
  consider: { box: 'bg-amber-950/40 border-amber-700/70', text: 'text-amber-300', Icon: HelpCircle },
  skip: { box: 'bg-red-950/40 border-red-800/70', text: 'text-red-300', Icon: XCircle },
}
const TIER_STYLE = {
  'High Confidence': 'text-emerald-300 bg-emerald-950/70 border-emerald-800/70',
  'Proceed with Caution': 'text-orange-300 bg-orange-950/60 border-orange-800/70',
  Suspicious: 'text-red-300 bg-red-950/60 border-red-800/70',
}
const LIVE_STYLE = {
  active: 'text-emerald-300 bg-emerald-950/70 border-emerald-800/70',
  expired: 'text-red-300 bg-red-950/60 border-red-800/70',
  uncertain: 'text-slate-300 bg-slate-800 border-slate-700',
}

function ScoreBar({ label, score, Icon, note }) {
  const pct = Math.max(0, Math.min(100, ((score - 1) / 4) * 100))
  const color = score >= 4 ? 'bg-emerald-500' : score >= 3 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-slate-300 flex items-center gap-1.5 font-medium"><Icon size={12} className="text-slate-400" />{label}</span>
        <span className="font-bold text-slate-200">{score?.toFixed ? score.toFixed(1) : score}/5</span>
      </div>
      <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden"><div className={`h-full ${color}`} style={{ width: `${pct}%` }} /></div>
      {note && <p className="text-[10px] text-slate-500 leading-snug">{note}</p>}
    </div>
  )
}

export default function ApplyVerdictPanel({ job }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [showSignals, setShowSignals] = useState(false)

  useEffect(() => { setResult(null); setError(''); setShowSignals(false) }, [job?.url, job?.title])

  const run = async () => {
    setLoading(true); setError('')
    try {
      const { data } = await client.post('/jobs/evaluate', {
        title: job.title || '', company: job.company || '', location: job.location || '',
        url: job.url || job.job_url || '', job_url_direct: job.job_url_direct || '',
        description: job.description || '', salary: job.salary || '',
        date_posted: job.date_posted || '', age_hours: job.age_hours ?? null, site: job.site || '',
        check_liveness: true,
      })
      setResult(data)
    } catch (e) {
      setError(e?.response?.data?.detail || 'Evaluation failed')
    } finally {
      setLoading(false)
    }
  }

  if (!job) return null

  if (!result) {
    return (
      <div className="p-3.5 rounded-xl bg-slate-850/60 bg-slate-800/40 border border-slate-700/80 flex items-center justify-between gap-3">
        <div className="space-y-0.5">
          <p className="text-xs font-bold text-slate-100 flex items-center gap-1.5"><Scale size={13} className="text-sky-400" /> Should I apply?</p>
          <p className="text-[11px] text-slate-400">Checks it's still open, ghost/scam signals, visa blockers, pay and CV fit — then gives a verdict.</p>
          {error && <p className="text-[11px] text-red-400">{error}</p>}
        </div>
        <button type="button" onClick={run} disabled={loading}
          className="shrink-0 flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs transition cursor-pointer disabled:opacity-60">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Scale size={13} />}
          {loading ? 'Evaluating…' : 'Evaluate'}
        </button>
      </div>
    )
  }

  const v = VERDICT_STYLE[result.verdict] || VERDICT_STYLE.consider
  const d = result.dimensions || {}
  const legit = d.legitimacy || {}
  const auth = d.work_authorization || {}
  const comp = d.compensation || {}
  const cv = d.cv_match || {}
  const live = result.liveness
  const rs = result.role_summary || {}

  return (
    <div className={`p-4 rounded-xl border space-y-3.5 ${v.box}`}>
      {/* Verdict header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <v.Icon size={22} className={`${v.text} shrink-0 mt-0.5`} />
          <div>
            <p className={`text-sm font-extrabold ${v.text}`}>{result.verdict_label}</p>
            <p className="text-[11px] text-slate-400">
              {rs.archetype} · {rs.seniority} · {rs.work_mode}
              <span className="ml-1.5 text-slate-500">(evidence: {result.confidence})</span>
            </p>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className={`text-2xl font-black leading-none ${v.text}`}>{result.global_score?.toFixed(1)}</p>
          <p className="text-[10px] text-slate-500">/ 5</p>
        </div>
      </div>

      {/* Liveness + legitimacy chips */}
      <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-semibold">
        {live && (
          <span className={`px-2 py-0.5 rounded-md border flex items-center gap-1 ${LIVE_STYLE[live.result] || LIVE_STYLE.uncertain}`} title={live.reason}>
            <Radio size={10} />
            {live.result === 'active' ? 'Still open' : live.result === 'expired' ? 'Closed' : 'Open? unverified'}
          </span>
        )}
        {legit.tier && (
          <span className={`px-2 py-0.5 rounded-md border flex items-center gap-1 ${TIER_STYLE[legit.tier]}`}>
            {legit.tier === 'High Confidence' ? <ShieldCheck size={10} /> : <ShieldAlert size={10} />}
            {legit.tier}
          </span>
        )}
        {(auth.positives || []).slice(0, 1).map(p => (
          <span key={p} className="px-2 py-0.5 rounded-md border text-emerald-300 bg-emerald-950/70 border-emerald-800/70 flex items-center gap-1"><Plane size={10} />{p}</span>
        ))}
      </div>

      {/* Red flags */}
      {result.red_flags?.length > 0 && (
        <ul className="space-y-1">
          {result.red_flags.map(f => (
            <li key={f} className="text-[11px] text-red-300 flex items-start gap-1.5"><AlertTriangle size={11} className="mt-0.5 shrink-0" />{f}</li>
          ))}
        </ul>
      )}

      {/* Dimension scores */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2.5">
        <ScoreBar label="CV match" Icon={Target} score={cv.score}
          note={cv.match_pct != null ? `${cv.match_pct}% skills match${cv.seniority_note ? ' · ' + cv.seniority_note : ''}` : cv.note} />
        <ScoreBar label="Posting legitimacy" Icon={ShieldCheck} score={legit.score}
          note={`${(legit.signals || []).filter(s => s.impact >= 0.5).length} warning signal(s)`} />
        <ScoreBar label="Work authorization" Icon={Plane} score={auth.score}
          note={auth.blockers?.length ? auth.blockers.map(b => b.label).join(' · ') : auth.positives?.length ? 'Open to international candidates' : 'Not stated in the posting'} />
        <ScoreBar label="Compensation" Icon={DollarSign} score={comp.score} note={comp.note} />
      </div>

      {/* Gaps */}
      {cv.gaps?.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">Gaps & how to handle them</p>
          {cv.gaps.slice(0, 5).map(g => (
            <p key={g.skill} className="text-[11px] text-slate-400">
              <span className={`font-semibold ${g.importance === 'hard requirement' ? 'text-red-300' : 'text-amber-300'}`}>{g.skill}</span>
              <span className="text-slate-500"> ({g.importance})</span> — {g.mitigation}
            </p>
          ))}
        </div>
      )}

      {/* ATS keywords */}
      {result.customization?.keywords?.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1"><KeyRound size={11} /> JD keywords</p>
          <div className="flex flex-wrap gap-1">
            {result.customization.keywords.map(k => (
              <span key={k.keyword} title={`${k.mentions} mention(s) in the JD`}
                className={`px-1.5 py-0.5 rounded text-[10px] border ${k.in_cv ? 'text-emerald-300 bg-emerald-950/60 border-emerald-800/60' : 'text-slate-300 bg-slate-800 border-slate-700'}`}>
                {k.in_cv ? '✓ ' : ''}{k.keyword}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Interview focus */}
      {result.interview_focus?.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1"><MessageSquare size={11} /> Interview prep</p>
          {result.interview_focus.map(t => <p key={t} className="text-[11px] text-slate-400">• {t}</p>)}
        </div>
      )}

      {/* Legitimacy signal table */}
      <div>
        <button type="button" onClick={() => setShowSignals(s => !s)} className="text-[11px] text-sky-300 hover:text-sky-200 cursor-pointer">
          {showSignals ? 'Hide' : 'Show'} legitimacy signals ({legit.signals?.length || 0})
        </button>
        {showSignals && (
          <div className="mt-2 space-y-1">
            {(legit.signals || []).map((s, i) => (
              <div key={i} className="flex items-start justify-between gap-2 text-[11px]">
                <span className="text-slate-400"><span className="text-slate-200 font-semibold">{s.signal}:</span> {s.finding}</span>
                <span className={`shrink-0 font-mono ${s.impact > 0 ? 'text-red-300' : s.impact < 0 ? 'text-emerald-300' : 'text-slate-500'}`}>
                  {s.impact > 0 ? '+' : ''}{s.impact} · {s.reliability}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <button type="button" onClick={run} disabled={loading} className="text-[11px] text-slate-400 hover:text-white cursor-pointer flex items-center gap-1">
          {loading && <Loader2 size={11} className="animate-spin" />} Re-evaluate
        </button>
      </div>
    </div>
  )
}
