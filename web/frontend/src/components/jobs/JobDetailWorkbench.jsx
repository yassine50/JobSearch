import { useState, useEffect } from 'react'
import {
  Briefcase, Building2, MapPin, Mail, ExternalLink, Sparkles,
  Zap, MessageSquare, Bookmark, ShieldCheck, Check, Copy, CheckCheck,
  CheckCircle2, FileText, Target, Eye, AlertTriangle, Lightbulb, ArrowRight,
  Loader2, RotateCcw
} from 'lucide-react'
import client from '../../api/client.js'

export default function JobDetailWorkbench({
  job,
  isApplied = false,
  isSaved = false,
  applying = false,
  onAutoApply,
  onEasyApply,
  onTailor,
  onOpenInMail,
  onOpenReader,
  onSave,
  onMarkApplied,
  onUpdateJob
}) {
  const [copiedEmail, setCopiedEmail] = useState(null)
  const [fetchingDesc, setFetchingDesc] = useState(false)
  const [fetchError, setFetchError] = useState(false)

  // Auto-fetch description if missing from the initial feed card
  useEffect(() => {
    let isMounted = true
    setFetchError(false)

    const needsDesc = job && (!job.description || job.description.trim().length < 50)
    if (needsDesc) {
      setFetchingDesc(true)
      const cleanJobId = job.id ? String(job.id).replace('li-', '') : null
      client.post('/jobs/fetch-description', {
        url: job.url || job.job_url || job.job_url_direct || '',
        job_id: cleanJobId,
        title: job.title || ''
      })
      .then(res => {
        if (!isMounted) return
        setFetchingDesc(false)
        if (res.data && res.data.description) {
          const updated = {
            ...job,
            description: res.data.description,
            score: res.data.score != null ? res.data.score : job.score,
            matched_skills: res.data.matched_skills?.length ? res.data.matched_skills : job.matched_skills,
            missing_skills: res.data.missing_skills?.length ? res.data.missing_skills : job.missing_skills,
            tips: res.data.tips?.length ? res.data.tips : job.tips,
          }
          if (res.data.emails && res.data.emails.length > 0) {
            const currentEmails = Array.isArray(job.emails) ? job.emails : []
            const currentRaw = currentEmails.map(e => typeof e === 'object' ? e.email : e)
            const added = res.data.emails.filter(e => !currentRaw.includes(e)).map(e => ({ email: e, source: 'found' }))
            updated.emails = [...currentEmails, ...added]
          }
          if (onUpdateJob) onUpdateJob(updated)
        } else {
          setFetchError(true)
        }
      })
      .catch(() => {
        if (!isMounted) return
        setFetchingDesc(false)
        setFetchError(true)
      })
    } else {
      setFetchingDesc(false)
    }

    return () => { isMounted = false }
  }, [job?.id, job?.url])

  if (!job) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center text-slate-500 bg-slate-900/60 border border-slate-800 rounded-2xl">
        <Briefcase size={36} className="text-slate-600 mb-3" />
        <p className="text-sm font-semibold text-slate-400">Select a job from the feed</p>
        <p className="text-xs text-slate-500 mt-1">Review recruiter contact, tailored ATS match analysis, missing skills, and 1-click apply</p>
      </div>
    )
  }

  const emails = Array.isArray(job.emails) ? job.emails : []
  const hasEmails = emails.length > 0 || Boolean(job.to_email)
  const primaryEmail = hasEmails
    ? (typeof emails[0] === 'object' ? emails[0]?.email : emails[0]) || job.to_email
    : null

  const handleCopyEmail = (em) => {
    if (!em) return
    navigator.clipboard.writeText(em)
    setCopiedEmail(em)
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  const score = job.score != null ? job.score : (job.match_score != null ? job.match_score : 75)
  const matchedSkills = job.matched_skills || []
  const missingSkills = job.missing_skills || []
  const tips = job.tips || []

  const isLinkedIn = (job.site || '').toLowerCase().includes('linkedin')
  const jobUrl = job.url || job.job_url_direct || job.job_url || '#'
  const isEasyApply = Boolean(job && (job.easy_apply || job.is_direct_apply))

  return (
    <div className="sticky top-4 max-h-[calc(100vh-140px)] overflow-y-auto space-y-4 bg-slate-900 border border-slate-750 rounded-2xl p-6 shadow-xl">
      {/* Header & Role Info */}
      <div className="space-y-3 pb-4 border-b border-slate-800">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <h3 className="text-lg md:text-xl font-bold text-white tracking-tight leading-snug">
              {job.title}
            </h3>
            <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap pt-0.5">
              <span className="font-semibold text-blue-300 flex items-center gap-1">
                <Building2 size={12} className="text-blue-400" />
                {job.company || 'Company'}
              </span>
              <span className="text-slate-500">·</span>
              <span className="text-slate-400 flex items-center gap-1">
                <MapPin size={11} className="text-slate-400" />
                {job.location || 'Remote'}
              </span>
              <span className="text-slate-500">·</span>
              <span className={`px-2 py-0.5 rounded-md font-semibold text-[10px] uppercase border ${
                isLinkedIn
                  ? 'bg-blue-950/80 text-blue-300 border-blue-800/80'
                  : 'bg-indigo-950/80 text-indigo-300 border-indigo-800/80'
              }`}>
                {job.site || 'Job Board'}
              </span>
              {job.age_str && (
                <>
                  <span className="text-slate-500">·</span>
                  <span className={`px-2 py-0.5 rounded-md font-semibold text-[10px] border ${
                    job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)
                      ? 'bg-amber-950/80 text-amber-300 border-amber-800/80 flex items-center gap-1'
                      : 'bg-slate-850 text-slate-400 border-slate-700'
                  }`}>
                    {(job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)) && <span>⚡</span>}
                    {job.age_str}
                  </span>
                </>
              )}
              {!primaryEmail && isEasyApply && (
                <>
                  <span className="text-slate-500">·</span>
                  <span className="px-2 py-0.5 rounded-md font-semibold text-[10px] border bg-emerald-950/80 text-emerald-300 border-emerald-700/80 flex items-center gap-1">
                    <Zap size={10} className="fill-emerald-400" />
                    Candidature Simplifiée
                  </span>
                </>
              )}
              {job.salary && (
                <>
                  <span className="text-slate-500">·</span>
                  <span className="text-emerald-400 font-semibold">{job.salary}</span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <span className={`text-xs font-bold px-3 py-1 rounded-xl border flex items-center gap-1 ${
              score >= 75
                ? 'bg-emerald-950/90 border-emerald-700 text-emerald-300'
                : score >= 55
                ? 'bg-blue-950/90 border-blue-700 text-blue-300'
                : 'bg-amber-950/90 border-amber-700 text-amber-300'
            }`}>
              <Target size={12} /> {score}% CV Match
            </span>
          </div>
        </div>

        {/* Action Toolbar (Exact same as Photo) */}
        <div className="flex items-center gap-2 pt-2 flex-wrap">
          {isApplied ? (
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 bg-emerald-950/90 border border-emerald-800 px-4 py-2 rounded-xl shadow-xs">
              <CheckCheck size={14} className="stroke-[3]" /> Applied
            </div>
          ) : primaryEmail ? (
            <button
              type="button"
              onClick={() => onAutoApply && onAutoApply({
                ...job,
                author_name: 'Hiring Team',
                role_title: job.title,
                recruiter_emails: [{ email: primaryEmail, name: 'Hiring Team' }]
              }, primaryEmail)}
              disabled={applying}
              className="flex items-center gap-1.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs px-4 py-2.5 rounded-xl shadow-md shadow-amber-500/20 transition cursor-pointer disabled:opacity-50"
            >
              <Zap size={14} className="fill-slate-950" />
              <span>⚡ Auto-Apply (Tailored CV)</span>
            </button>
          ) : isEasyApply ? (
            <button
              type="button"
              onClick={() => onEasyApply && onEasyApply(job)}
              disabled={applying}
              className="flex items-center gap-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl shadow-md shadow-emerald-500/25 transition cursor-pointer disabled:opacity-50"
            >
              <Zap size={14} className="fill-white" />
              <span>⚡ Auto-Apply (Candidature Simplifiée)</span>
            </button>
          ) : (
            <a
              href={jobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-500/20 transition cursor-pointer"
            >
              <ExternalLink size={14} />
              <span>{isLinkedIn ? 'View on LinkedIn' : 'Apply on Portal'}</span>
            </a>
          )}

          {/* If email or easy apply exists, still offer direct external link */}
          {!isApplied && (primaryEmail || isEasyApply) && (
            <a
              href={jobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-500/20 transition cursor-pointer"
            >
              <ExternalLink size={13} />
              <span>{isLinkedIn ? 'View on LinkedIn' : 'Apply on Portal'}</span>
            </a>
          )}

          {/* Mark as Applied button (saves to Tracker pipeline & removes from search) */}
          {!isApplied && (
            <button
              type="button"
              onClick={() => onMarkApplied && onMarkApplied(job)}
              className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-emerald-900/60 hover:bg-emerald-800/80 border border-emerald-600/70 text-emerald-200 hover:text-white font-bold text-xs shadow-md shadow-emerald-950/30 transition cursor-pointer"
              title="Mark this job as applied and save it into Tracker"
            >
              <CheckCheck size={14} className="text-emerald-400 stroke-[2.5]" />
              <span>Mark as Applied</span>
            </button>
          )}

          {/* 1-Click Tailor CV */}
          <button
            type="button"
            onClick={() => onTailor && onTailor(job)}
            className="flex items-center gap-1.5 text-xs text-purple-200 hover:text-white bg-purple-950/60 hover:bg-purple-900/80 border border-purple-700/80 px-3.5 py-2.5 rounded-xl transition cursor-pointer font-medium"
          >
            <Sparkles size={13} className="text-amber-400" />
            <span>Tailor CV</span>
          </button>

          {/* Connection Pitch */}
          <button
            type="button"
            onClick={() => onOpenInMail && onOpenInMail({
              author_name: 'Hiring Team',
              company: job.company,
              role_title: job.title,
              full_text: job.description
            })}
            className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-slate-800 hover:bg-slate-750 border border-slate-700 px-3 py-2.5 rounded-xl transition cursor-pointer font-medium"
          >
            <MessageSquare size={13} className="text-blue-400" />
            <span>Connection Pitch</span>
          </button>

          {/* Reader Mode */}
          <button
            type="button"
            onClick={() => onOpenReader && onOpenReader({
              post_url: jobUrl,
              role_title: job.title,
              company: job.company,
              full_text: job.description
            })}
            className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-750 border border-slate-700 p-2.5 rounded-xl transition cursor-pointer"
            title="Read full description in reader mode"
          >
            <Eye size={14} />
          </button>

          {/* Bookmark */}
          <button
            type="button"
            onClick={() => !isApplied && onSave && onSave(job)}
            disabled={isSaved || isApplied}
            className="p-2.5 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-300 hover:text-white transition cursor-pointer disabled:opacity-50"
            title={isSaved ? 'Saved to pipeline' : 'Save to pipeline'}
          >
            <Bookmark size={14} className={isSaved ? 'fill-blue-400 text-blue-400' : ''} />
          </button>
        </div>
      </div>

      {/* Recruiter Email Banner */}
      {primaryEmail && (
        <div className="p-3.5 rounded-xl bg-purple-950/30 border border-purple-800/50 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
              <Mail size={12} className="text-purple-400" /> Mined Recruiter Direct Mailbox
            </span>
            <span className="text-[10px] text-emerald-400 font-semibold bg-emerald-950/80 border border-emerald-800/80 px-2 py-0.5 rounded-full flex items-center gap-1">
              <ShieldCheck size={10} /> MX Verified Deliverable
            </span>
          </div>
          <div className="flex items-center justify-between gap-3 p-2 rounded-lg bg-slate-950/80 border border-slate-800">
            <div className="flex items-center gap-2 truncate">
              <span className="text-xs font-mono font-bold text-white truncate">{primaryEmail}</span>
            </div>
            <button
              type="button"
              onClick={() => handleCopyEmail(primaryEmail)}
              className="text-xs text-purple-300 hover:text-white flex items-center gap-1 px-2 py-1 rounded hover:bg-purple-900/50 cursor-pointer transition shrink-0"
            >
              {copiedEmail === primaryEmail ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              <span>{copiedEmail === primaryEmail ? 'Copied' : 'Copy Email'}</span>
            </button>
          </div>
        </div>
      )}

      {/* ─── CV MATCH & IMPROVEMENT ANALYSIS CARD (Exact same as in Photo) ─── */}
      <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800 space-y-3.5">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
            <Target size={14} className="text-blue-400" /> ATS CV Match Analysis
          </h4>
          <span className="text-xs font-bold text-blue-400">{score}% Score</span>
        </div>

        {/* Score Progress Bar */}
        <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              score >= 75 ? 'bg-emerald-500' : score >= 55 ? 'bg-blue-500' : 'bg-amber-500'
            }`}
            style={{ width: `${Math.max(5, Math.min(100, score))}%` }}
          />
        </div>

        {/* Matched Skills (Present on your CV) */}
        {matchedSkills.length > 0 ? (
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
              <CheckCircle2 size={12} /> Matched Skills (Present on your CV):
            </span>
            <div className="flex flex-wrap gap-1.5">
              {matchedSkills.map((s, i) => (
                <span key={i} className="text-[11px] px-2.5 py-0.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 font-medium">
                  ✓ {s}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-slate-500 italic">
            Upload your CV to auto-analyze matched technical skills
          </div>
        )}

        {/* Missing Things on Your CV */}
        {missingSkills.length > 0 && (
          <div className="space-y-1.5 pt-1 border-t border-slate-800/80">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-amber-400 flex items-center gap-1">
                <AlertTriangle size={12} /> Missing Things on Your CV:
              </span>
              <span className="text-[10px] text-slate-400">{missingSkills.length} keyword(s) absent</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {missingSkills.map((s, i) => (
                <span key={i} className="text-[11px] px-2.5 py-0.5 rounded-lg bg-amber-950/50 border border-amber-800/60 text-amber-300 font-medium flex items-center gap-1">
                  <span>+</span> {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Actionable Tips to Improve */}
        {tips.length > 0 && (
          <div className="space-y-2 pt-1 border-t border-slate-800/80">
            <span className="text-[11px] font-semibold text-purple-300 flex items-center gap-1">
              <Lightbulb size={13} className="text-amber-300" /> How to Improve Your CV for This Post:
            </span>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {tips.map((tip, i) => (
                <li key={i} className="flex items-start gap-2 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/90 leading-relaxed">
                  <span className="text-amber-400 font-bold shrink-0">💡</span>
                  <span>{tip}</span>
                </li>
              ))}
            </ul>

            <button
              type="button"
              onClick={() => onTailor && onTailor(job)}
              className="w-full mt-2 py-2 px-3 rounded-lg bg-purple-900/40 hover:bg-purple-900/60 border border-purple-700/60 text-xs font-bold text-purple-200 hover:text-white transition flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
            >
              <Sparkles size={13} className="text-amber-300" />
              <span>Bridge Missing Skills with AI Resume Tailor</span>
              <ArrowRight size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Full Job Description Section */}
      <div className="space-y-2 pt-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <FileText size={12} /> Job Description & Requirements
          </h4>
          <a
            href={jobUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
          >
            <span>Original Listing</span>
            <ExternalLink size={11} />
          </a>
        </div>
        {fetchingDesc ? (
          <div className="p-6 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col items-center justify-center gap-2 py-8 text-center text-xs text-blue-400">
            <Loader2 size={18} className="animate-spin text-blue-400" />
            <span className="font-semibold text-slate-300">Fetching complete job description & ATS requirements from live board...</span>
            <span className="text-[11px] text-slate-500">Extracting responsibilities, tech stack, and recruiter contacts</span>
          </div>
        ) : job.description && job.description.trim() ? (
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-300 leading-relaxed whitespace-pre-line max-h-[420px] overflow-y-auto select-text">
            {job.description}
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-2">
            <p className="text-slate-400">
              Detailed requirements and full description are available directly on the original posting.
            </p>
            <a
              href={jobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 font-semibold transition"
            >
              <span>View Full Listing on {isLinkedIn ? 'LinkedIn' : 'Portal'}</span>
              <ExternalLink size={12} />
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
