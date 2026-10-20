/**
 * Compact career-ops + ai-job-search signals for a job card:
 *  - posting legitimacy tier (ghost / scam detection)
 *  - repost history & company mass-posting count
 *  - verified first-party ATS provenance (Greenhouse, Lever, Ashby, Workday, etc.)
 *  - work-authorization blockers / visa-sponsorship positives
 *  - language gate requirements (e.g. German / Dutch / French fluency)
 *  - recruiter easter-egg / attention check alert
 */
export default function JobSignalBadges({ job }) {
  if (!job) return null
  const tier = job.legitimacy?.tier
  const flags = job.legitimacy?.flags || []
  const reposts = job.repost_count || 0
  const blockers = job.work_auth?.blockers || []
  const positives = job.work_auth?.positives || []
  const atsProv = job.ats_provenance
  const langMissing = job.language_gate?.missing || []
  const langMatched = job.language_gate?.matched || []
  const hasAttentionCheck = Boolean(job.posting_guard?.has_attention_check)
  const attentionSnippet = job.posting_guard?.attention_checks?.[0]?.snippet || 'Recruiter attention check inside JD'
  const companyOpenings = job.company_openings_count || 1
  const dlInfo = job.deadline_info

  return (
    <>
      {dlInfo?.is_urgent && dlInfo?.label && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-amber-950/85 text-amber-200 border-amber-600/80"
          title={`Application deadline: ${dlInfo.deadline} (${dlInfo.days_remaining} days left)`}
        >
          ⏰ {dlInfo.label}
        </span>
      )}
      {!dlInfo?.is_urgent && dlInfo?.deadline && !dlInfo?.is_expired && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-slate-900/80 text-slate-300 border-slate-700/70"
          title={`Application deadline: ${dlInfo.deadline}`}
        >
          📅 {dlInfo.label}
        </span>
      )}
      {atsProv?.is_first_party && atsProv?.vendor && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-teal-950/70 text-teal-300 border-teal-700/70"
          title={`Verified first-party company ATS (${atsProv.vendor})`}
        >
          ✓ {atsProv.vendor}
        </span>
      )}
      {tier === 'Suspicious' && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-red-950/80 text-red-300 border-red-800/80"
          title={flags.join(' · ') || 'Multiple ghost / scam signals'}
        >
          ⚠ Suspicious
        </span>
      )}
      {tier === 'Proceed with Caution' && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-orange-950/70 text-orange-300 border-orange-800/70"
          title={flags.join(' · ')}
        >
          ⚠ Caution
        </span>
      )}
      {reposts > 0 && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-fuchsia-950/70 text-fuchsia-300 border-fuchsia-800/70"
          title={`Same role re-posted under ${reposts + 1} different URLs since ${job.sighting?.first_seen || 'earlier'} — possible ghost job`}
        >
          ↻ Reposted ×{reposts + 1}
        </span>
      )}
      {companyOpenings >= 3 && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-indigo-950/70 text-indigo-300 border-indigo-800/70"
          title={`${companyOpenings} active openings from ${job.company} in this search`}
        >
          🏢 {companyOpenings} roles
        </span>
      )}
      {blockers.length > 0 && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-red-950/60 text-red-300 border-red-800/60"
          title={blockers.join(' · ')}
        >
          🛂 {blockers[0]}
        </span>
      )}
      {blockers.length === 0 && positives.length > 0 && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-emerald-950/70 text-emerald-300 border-emerald-800/70"
          title={positives.join(' · ')}
        >
          ✈ {/sponsor/i.test(positives[0]) ? 'Visa sponsor' : /relocat/i.test(positives[0]) ? 'Relocation' : 'Global remote'}
        </span>
      )}
      {langMissing.length > 0 && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-amber-950/75 text-amber-300 border-amber-700/70"
          title={job.language_gate?.note || `Requires ${langMissing.join(', ')} fluency`}
        >
          🗣 {langMissing.join('/')} req
        </span>
      )}
      {langMissing.length === 0 && langMatched.length > 0 && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-emerald-950/70 text-emerald-300 border-emerald-800/70"
          title={job.language_gate?.note}
        >
          🗣 {langMatched.join('/')} ✓
        </span>
      )}
      {hasAttentionCheck && (
        <span
          className="px-1.5 py-0.2 rounded text-[10px] font-semibold border bg-purple-950/80 text-purple-200 border-purple-700/80"
          title={attentionSnippet}
        >
          🎯 Attention Check
        </span>
      )}
    </>
  )
}
