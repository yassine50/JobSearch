/**
 * Compact career-ops signals for a job card:
 *  - posting legitimacy tier (ghost / scam detection)
 *  - repost history
 *  - work-authorization blockers / visa-sponsorship positives
 */
export default function JobSignalBadges({ job }) {
  if (!job) return null
  const tier = job.legitimacy?.tier
  const flags = job.legitimacy?.flags || []
  const reposts = job.repost_count || 0
  const blockers = job.work_auth?.blockers || []
  const positives = job.work_auth?.positives || []

  return (
    <>
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
    </>
  )
}
