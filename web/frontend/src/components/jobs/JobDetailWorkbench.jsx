import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Briefcase, Building2, MapPin, Mail, ExternalLink, Sparkles,
  Zap, MessageSquare, Bookmark, ShieldCheck, Check, Copy, CheckCheck,
  CheckCircle2, FileText, Target, Eye, AlertTriangle, Lightbulb, ArrowRight,
  Loader2, Users
} from 'lucide-react'
import client from '../../api/client.js'
import ApplyVerdictPanel from './ApplyVerdictPanel.jsx'
import CompanyContactsModal from '../modals/CompanyContactsModal.jsx'

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
  const [contactsOpen, setContactsOpen] = useState(false)

  // Auto-fetch description and Job Bank recruiter emails if missing from the initial feed card
  useEffect(() => {
    let isMounted = true
    setFetchError(false)

    const isJobBank = job && (
      (job.site || '').toLowerCase().includes('job bank') ||
      (job.url || '').includes('jobbank.gc.ca') ||
      (job.listing_type || '').toLowerCase().includes('job bank')
    )
    const hasNoEmails = !job?.emails || (Array.isArray(job.emails) && job.emails.length === 0)
    const needsDesc = job && (!job.description || job.description.trim().length < 50 || (isJobBank && hasNoEmails))

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
        if (res.data && (res.data.description || (res.data.emails && res.data.emails.length > 0) || res.data.job_url_direct)) {
          const updated = {
            ...job,
            description: res.data.description || job.description,
            job_url_direct: res.data.job_url_direct || job.job_url_direct,
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
      <div className="flex flex-col items-center justify-center p-14 text-center text-slate-500 glass-panel rounded-3xl relative overflow-hidden">
        <div className="glow-line-top" />
        <div className="w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 mb-3 animate-float">
          <Briefcase size={26} />
        </div>
        <p className="text-sm font-bold text-slate-300">Select a job from the live feed</p>
        <p className="text-xs text-slate-500 mt-1 max-w-xs">
          Inspect direct recruiter emails, ATS resume alignment, skill gaps, and 1-click Auto-Apply
        </p>
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

  const directUrl = (job.job_url_direct || '').trim()
  const hasExternalDirect = Boolean(directUrl && directUrl.startsWith('http') && !directUrl.toLowerCase().includes('linkedin.com'))
  const rawPrimaryUrl = hasExternalDirect ? directUrl : (job.url || job.job_url_direct || job.job_url || '#')
  const liIdMatch = rawPrimaryUrl.match(/linkedin\.com\/jobs\/view\/(?:[^/?#]*-)?(\d{8,12})(?:[/?#]|$)/i)
  const jobUrl = liIdMatch ? `https://www.linkedin.com/jobs/view/${liIdMatch[1]}` : rawPrimaryUrl
  const isLinkedIn = !hasExternalDirect && ((job.site || '').toLowerCase().includes('linkedin') || jobUrl.toLowerCase().includes('linkedin.com'))
  const isEasyApply = Boolean(job && (job.easy_apply || job.is_direct_apply))

  return (
    <motion.div
      key={job.id || job.url}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="sticky top-4 max-h-[calc(100vh-140px)] overflow-y-auto space-y-4 glass-panel rounded-3xl p-6 relative"
    >
      <div className="glow-line-top" />

      {/* Header & Role Info */}
      <div className="space-y-3.5 pb-4 border-b border-white/[0.07]">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1.5">
            <h3 className="text-lg md:text-xl font-extrabold text-white tracking-tight leading-snug">
              {job.title}
            </h3>
            <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap pt-0.5">
              <span className="font-bold text-blue-300 flex items-center gap-1">
                <Building2 size={12} className="text-blue-400" />
                {job.company || 'Company'}
              </span>
              <span className="text-slate-600">·</span>
              <span className="text-slate-400 flex items-center gap-1">
                <MapPin size={11} className="text-slate-400" />
                {job.location || 'Remote'}
              </span>
              <span className="text-slate-600">·</span>
              <span className="px-2 py-0.5 rounded-lg font-bold text-[10px] uppercase border bg-blue-500/10 text-blue-300 border-blue-500/25">
                {job.site || 'Job Board'}
              </span>
              {job.age_str && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="px-2 py-0.5 rounded-lg font-semibold text-[10px] border bg-white/[0.04] text-slate-300 border-white/[0.08] flex items-center gap-1">
                    {job.age_str}
                  </span>
                </>
              )}
              {!primaryEmail && isEasyApply && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="px-2 py-0.5 rounded-lg font-bold text-[10px] border bg-blue-500/10 text-blue-300 border-blue-500/25 flex items-center gap-1">
                    <Zap size={10} />
                    Candidature Simplifiée
                  </span>
                </>
              )}
              {job.salary && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="text-blue-300 font-bold">{job.salary}</span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <span className="text-xs font-extrabold px-3 py-1.5 rounded-xl border flex items-center gap-1.5 shadow-sm bg-blue-500/15 border-blue-500/35 text-blue-300">
              <Target size={13} /> {score}% CV Match
            </span>
          </div>
        </div>

        {/* Unified Action Toolbar (Primary Blue CTA + Consistent Slate Secondary Buttons) */}
        <div className="flex items-center gap-2 pt-2 flex-wrap">
          {isApplied ? (
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-300 bg-emerald-500/15 border border-emerald-500/35 px-4 py-2.5 rounded-xl shadow-sm">
              <CheckCheck size={14} className="stroke-[3] text-emerald-400" /> Applied
            </div>
          ) : primaryEmail ? (
            <motion.button
              type="button"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => onAutoApply && onAutoApply({
                ...job,
                author_name: 'Hiring Team',
                role_title: job.title,
                recruiter_emails: [{ email: primaryEmail, name: 'Hiring Team' }]
              }, primaryEmail)}
              disabled={applying}
              className="shimmer-btn flex items-center gap-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-extrabold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-blue-600/25 transition cursor-pointer disabled:opacity-50"
            >
              <Zap size={14} />
              <span>Auto-Apply (Direct Email)</span>
            </motion.button>
          ) : isEasyApply ? (
            <motion.button
              type="button"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => onEasyApply && onEasyApply(job)}
              disabled={applying}
              className="shimmer-btn flex items-center gap-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-extrabold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-blue-600/25 transition cursor-pointer disabled:opacity-50"
            >
              <Zap size={14} />
              <span>Auto-Apply (Candidature Simplifiée)</span>
            </motion.button>
          ) : (
            <a
              href={jobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="shimmer-btn flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-blue-600/25 transition cursor-pointer"
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
              className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200 hover:text-white font-semibold text-xs transition cursor-pointer"
            >
              <ExternalLink size={13} className="text-blue-400" />
              <span>{isLinkedIn ? 'View on LinkedIn' : 'Apply on Portal'}</span>
            </a>
          )}

          {/* 1-Click Tailor CV */}
          <button
            type="button"
            onClick={() => onTailor && onTailor(job)}
            className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-3.5 py-2.5 rounded-xl transition cursor-pointer font-semibold"
          >
            <Sparkles size={13} className="text-blue-400" />
            <span>Tailor CV</span>
          </button>

          {/* Mark as Applied button */}
          {!isApplied && (
            <button
              type="button"
              onClick={() => onMarkApplied && onMarkApplied(job)}
              className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200 hover:text-white font-semibold text-xs transition cursor-pointer"
              title="Mark this job as applied and save it into Tracker"
            >
              <CheckCheck size={14} className="text-blue-400" />
              <span>Mark as Applied</span>
            </button>
          )}

          {/* Connection Pitch */}
          <button
            type="button"
            onClick={() => onOpenInMail && onOpenInMail({
              author_name: 'Hiring Team',
              company: job.company,
              role_title: job.title,
              full_text: job.description
            })}
            className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-3.5 py-2.5 rounded-xl transition cursor-pointer font-semibold"
          >
            <MessageSquare size={13} className="text-blue-400" />
            <span>Connection Pitch</span>
          </button>

          {/* Find HR & Corporate Emails */}
          <button
            type="button"
            onClick={() => setContactsOpen(true)}
            className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-3.5 py-2.5 rounded-xl transition cursor-pointer font-semibold"
            title="Discover company recruiters, HR contacts & MX-verified emails"
          >
            <Users size={13} className="text-blue-400" />
            <span>Find HR &amp; Emails</span>
          </button>

          {/* 1-Click LinkedIn Referral / Peer Search */}
          {job.company && !['confidential', 'unknown', 'n/a'].includes((job.company || '').toLowerCase()) && (
            <a
              href={
                job.referral_links?.peers_url ||
                `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`${job.company} ${(job.title || '').split('-')[0].trim()}`)}`
              }
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-3.5 py-2.5 rounded-xl transition cursor-pointer font-semibold"
              title={`Find ${job.company} engineers & hiring managers on LinkedIn for a warm referral`}
            >
              <ExternalLink size={12} className="text-blue-400" />
              <span>Find Referral</span>
            </a>
          )}

          {/* Reader Mode */}
          <button
            type="button"
            onClick={() => onOpenReader && onOpenReader({
              post_url: jobUrl,
              role_title: job.title,
              company: job.company,
              full_text: job.description
            })}
            className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] p-2.5 rounded-xl transition cursor-pointer"
            title="Read full description in reader mode"
          >
            <Eye size={14} />
          </button>

          {/* Bookmark */}
          <button
            type="button"
            onClick={() => !isApplied && onSave && onSave(job)}
            disabled={isSaved || isApplied}
            className="p-2.5 rounded-xl border border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.08] text-slate-300 hover:text-white transition cursor-pointer disabled:opacity-50"
            title={isSaved ? 'Saved to pipeline' : 'Save to pipeline'}
          >
            <Bookmark size={14} className={isSaved ? 'fill-blue-400 text-blue-400' : ''} />
          </button>
        </div>
      </div>

      {/* career-ops: "Should I apply?" evaluation */}
      <ApplyVerdictPanel job={job} />

      {/* Recruiter Email Banner */}
      {primaryEmail ? (
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-blue-500/25 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-extrabold text-blue-300 uppercase tracking-wider flex items-center gap-1.5">
              <Mail size={12} className="text-blue-400" />
              {(job.site || '').toLowerCase().includes('job bank') || (job.url || '').includes('jobbank.gc.ca')
                ? 'Job Bank Recruiter Email (Additional ways to apply)'
                : 'Mined Recruiter Direct Mailbox'}
            </span>
            <span className="text-[10px] text-emerald-300 font-bold bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <ShieldCheck size={10} className="text-emerald-400" /> MX Verified Deliverable
            </span>
          </div>
          <div className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-900/90 border border-white/[0.08]">
            <div className="flex items-center gap-2 truncate">
              <span className="text-xs font-mono font-bold text-white truncate">{primaryEmail}</span>
            </div>
            <button
              type="button"
              onClick={() => handleCopyEmail(primaryEmail)}
              className="text-xs text-blue-300 hover:text-white flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-500/15 hover:bg-blue-500/25 border border-blue-500/30 cursor-pointer transition shrink-0 font-semibold"
            >
              {copiedEmail === primaryEmail ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              <span>{copiedEmail === primaryEmail ? 'Copied!' : 'Copy Email'}</span>
            </button>
          </div>
        </div>
      ) : ((job.site || '').toLowerCase().includes('job bank') || (job.url || '').includes('jobbank.gc.ca')) && (
        <div className="p-3.5 rounded-2xl bg-white/[0.03] border border-white/[0.07] flex items-center justify-between text-xs text-slate-400">
          <span className="flex items-center gap-1.5 text-slate-300">
            <Mail size={13} className="text-blue-400" />
            {fetchingDesc ? 'Mining "Additional ways to apply" for recruiter email...' : 'No email in "Additional ways to apply" (Direct Apply / Postal Mail)'}
          </span>
          {!fetchingDesc && (
            <button
              type="button"
              onClick={() => {
                setFetchingDesc(true)
                client.post('/jobs/fetch-description', {
                  url: job.url || job.job_url || '',
                  job_id: job.id,
                  title: job.title || '',
                  site: job.site || ''
                }).then(res => {
                  setFetchingDesc(false)
                  if (res.data?.emails?.length && onUpdateJob) {
                    onUpdateJob({ ...job, emails: res.data.emails.map(e => ({ email: e, source: 'found' })) })
                  }
                }).catch(() => setFetchingDesc(false))
              }}
              className="text-[11px] font-bold text-blue-400 hover:text-blue-300 transition cursor-pointer"
            >
              Re-check
            </button>
          )}
        </div>
      )}

      {/* CV Match & Improvement Analysis Card */}
      <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.07] space-y-3.5">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-extrabold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
            <Target size={14} className="text-blue-400" /> ATS CV Match Analysis
          </h4>
          <span className="text-xs font-extrabold text-blue-400">{score}% Score</span>
        </div>

        {/* Score Progress Bar */}
        <div className="w-full bg-slate-900 border border-white/[0.06] rounded-full h-2 overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${Math.max(5, Math.min(100, score))}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="h-full rounded-full bg-gradient-to-r from-blue-600 to-indigo-500"
          />
        </div>

        {/* Matched Skills */}
        {matchedSkills.length > 0 ? (
          <div className="space-y-1.5">
            <span className="text-[11px] font-bold text-emerald-400 flex items-center gap-1">
              <CheckCircle2 size={12} /> Matched Skills (Present on your CV):
            </span>
            <div className="flex flex-wrap gap-1.5">
              {matchedSkills.map((s, i) => (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.88, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  transition={{ delay: i * 0.03, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                  className="text-[11px] px-2.5 py-0.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-semibold"
                >
                  ✓ {s}
                </motion.span>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-slate-500 italic">
            Upload your CV to auto-analyze matched technical skills
          </div>
        )}

        {/* Missing Skills */}
        {missingSkills.length > 0 && (
          <div className="space-y-1.5 pt-2 border-t border-white/[0.06]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-amber-400 flex items-center gap-1">
                <AlertTriangle size={12} /> Missing Keywords on Your CV:
              </span>
              <span className="text-[10px] text-slate-400 font-medium">{missingSkills.length} keyword(s) absent</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {missingSkills.map((s, i) => (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.88, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  transition={{ delay: 0.05 + i * 0.03, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                  className="text-[11px] px-2.5 py-0.5 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 font-semibold flex items-center gap-1"
                >
                  <span>+</span> {s}
                </motion.span>
              ))}
            </div>
          </div>
        )}

        {/* Actionable Tips */}
        {tips.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-white/[0.06]">
            <span className="text-[11px] font-bold text-purple-300 flex items-center gap-1">
              <Lightbulb size={13} className="text-amber-300" /> How to Improve Your CV for This Role:
            </span>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {tips.map((tip, i) => (
                <li key={i} className="flex items-start gap-2 bg-white/[0.02] p-2.5 rounded-xl border border-white/[0.06] leading-relaxed">
                  <span className="text-amber-400 font-bold shrink-0">💡</span>
                  <span>{tip}</span>
                </li>
              ))}
            </ul>

            <button
              type="button"
              onClick={() => onTailor && onTailor(job)}
              className="w-full mt-2 py-2.5 px-3 rounded-xl bg-gradient-to-r from-purple-600/30 to-indigo-600/30 hover:from-purple-600/45 hover:to-indigo-600/45 border border-purple-500/35 text-xs font-bold text-purple-200 hover:text-white transition flex items-center justify-center gap-1.5 cursor-pointer shadow-sm"
            >
              <Sparkles size={13} className="text-amber-300" />
              <span>Bridge Missing Skills with AI Resume Tailor</span>
              <ArrowRight size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Full Job Description Section */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <FileText size={12} className="text-blue-400" /> Job Description & Requirements
          </h4>
          <a
            href={jobUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-bold"
          >
            <span>Original Listing</span>
            <ExternalLink size={11} />
          </a>
        </div>
        {fetchingDesc ? (
          <div className="p-6 rounded-2xl bg-slate-950/60 border border-white/[0.06] flex flex-col items-center justify-center gap-2 py-8 text-center text-xs text-blue-400">
            <Loader2 size={18} className="animate-spin text-blue-400" />
            <span className="font-bold text-slate-300">Fetching complete job description & ATS requirements from live board...</span>
            <span className="text-[11px] text-slate-500">Extracting responsibilities, tech stack, and recruiter contacts</span>
          </div>
        ) : job.description && job.description.trim() ? (
          <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.06] text-xs text-slate-300 leading-relaxed whitespace-pre-line max-h-[420px] overflow-y-auto select-text">
            {job.description}
          </div>
        ) : (
          <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.06] text-xs text-slate-400 space-y-2">
            <p className="text-slate-400">
              Detailed requirements and full description are available directly on the original posting.
            </p>
            <a
              href={jobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 font-bold transition"
            >
              <span>View Full Listing on {isLinkedIn ? 'LinkedIn' : 'Portal'}</span>
              <ExternalLink size={12} />
            </a>
          </div>
        )}
      </div>

      <CompanyContactsModal
        isOpen={contactsOpen}
        onClose={() => setContactsOpen(false)}
        job={job}
        onSelectEmailForApply={(discoveredEmail, contactName) => {
          onAutoApply && onAutoApply({
            ...job,
            author_name: contactName || 'Hiring Team',
            role_title: job.title,
            recruiter_emails: [{ email: discoveredEmail, name: contactName || 'Hiring Team' }]
          }, discoveredEmail)
        }}
      />
    </motion.div>
  )
}
