import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Briefcase, User, Building2, MapPin, Mail, ExternalLink, Sparkles,
  Zap, MessageSquare, Bookmark, ShieldCheck, Check, Copy, CheckCheck,
  CheckCircle2, FileText, Target, Eye,
  AlertTriangle, Lightbulb, ArrowRight, Clock, UserCheck, Link2, Users
} from 'lucide-react'
import CompanyContactsModal from '../modals/CompanyContactsModal.jsx'

export default function PostDetailWorkbench({
  post,
  isApplied,
  isSaved,
  applying,
  onAutoApply,
  onTailor,
  onOpenInMail,
  onOpenReader,
  onSave
}) {
  const [copiedEmail, setCopiedEmail] = useState(null)
  const [contactsOpen, setContactsOpen] = useState(false)

  if (!post) {
    return (
      <div className="flex flex-col items-center justify-center p-14 text-center text-slate-500 glass-card rounded-3xl">
        <div className="w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 mb-3">
          <Briefcase size={26} />
        </div>
        <p className="text-sm font-bold text-slate-300">Select a LinkedIn post from the feed</p>
        <p className="text-xs text-slate-500 mt-1 max-w-xs">
          Inspect verified recruiter mailboxes, ATS skill-gap diagnostics, and trigger 1-click Auto-Apply
        </p>
      </div>
    )
  }

  const emails = post.recruiter_emails || []
  const hasEmails = emails.length > 0
  const firstEmail = emails[0]?.email
  const emailBadge = emails[0]?.badge || 'MX Verified Deliverable'

  const handleCopyEmail = (em) => {
    navigator.clipboard.writeText(em)
    setCopiedEmail(em)
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  const score = Math.max(0, Math.min(100, Number(post.score ?? post.role_fit_score ?? 70)))
  const matchedSkills = post.matched_skills || []
  const missingSkills = post.missing_skills || []
  const tips = post.tips || []
  const authorInitial = (post.author_name || post.company || 'R').charAt(0).toUpperCase()

  // SVG Radial Gauge calculations
  const radius = 26
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (score / 100) * circumference
  const gaugeColor = score >= 75 ? '#34d399' : score >= 55 ? '#60a5fa' : '#fbbf24'

  return (
    <motion.div
      key={post.id}
      initial={{ opacity: 0, y: 14, scale: 0.99 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
      className="sticky top-4 max-h-[calc(100vh-140px)] overflow-y-auto space-y-4 glass-card rounded-3xl p-6 relative"
    >
      <div className="glow-line-top" />

      {/* Header & Role Info */}
      <div className="space-y-3.5 pb-4 border-b border-white/[0.07]">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {post.author_authority === 'human_recruiter' && (
                <span className="text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 flex items-center gap-1">
                  <UserCheck size={10} /> Human Recruiter
                </span>
              )}
              {post.age_str && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-slate-300 flex items-center gap-1">
                  <Clock size={10} className="text-blue-400" /> Posted {post.age_str}
                </span>
              )}
              {post.required_years != null && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/25 text-amber-300">
                  {post.required_years}+ yrs exp mentioned
                </span>
              )}
            </div>

            <h3 className="text-lg md:text-xl font-black text-white tracking-tight leading-snug">
              {post.role_title || 'Recruiter Job Posting'}
            </h3>

            <div className="flex items-center gap-2.5 text-xs text-slate-300 flex-wrap">
              <span className="font-bold text-white flex items-center gap-1.5">
                <span className="w-5 h-5 rounded-full bg-gradient-to-tr from-blue-600 to-purple-600 text-[10px] font-black text-white flex items-center justify-center">
                  {authorInitial}
                </span>
                {post.author_name}
              </span>
              <span className="text-slate-600">·</span>
              <span className="font-bold text-blue-300 flex items-center gap-1">
                <Building2 size={12} className="text-blue-400" />
                {post.company}
              </span>
              {post.location && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="text-emerald-300 font-bold bg-emerald-950/70 px-2 py-0.5 rounded-md border border-emerald-800/70 flex items-center gap-1">
                    <MapPin size={11} className="text-emerald-400" />
                    {post.location}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Animated Circular SVG Match Gauge */}
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.08, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col items-center shrink-0 bg-slate-950/70 border border-white/[0.07] rounded-2xl p-2.5"
          >
            <div className="relative w-14 h-14 flex items-center justify-center">
              <svg className="w-14 h-14 -rotate-90" viewBox="0 0 64 64">
                <circle
                  cx="32"
                  cy="32"
                  r={radius}
                  fill="none"
                  stroke="rgba(255,255,255,0.08)"
                  strokeWidth="5"
                />
                <motion.circle
                  cx="32"
                  cy="32"
                  r={radius}
                  fill="none"
                  stroke={gaugeColor}
                  strokeWidth="5"
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  initial={{ strokeDashoffset: circumference }}
                  animate={{ strokeDashoffset }}
                  transition={{ duration: 0.85, ease: 'easeOut' }}
                />
              </svg>
              <span className="absolute text-xs font-black text-white">{score}%</span>
            </div>
            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 mt-1">
              CV Match
            </span>
          </motion.div>
        </div>

        {/* Action Toolbar */}
        <div className="flex items-center gap-2 pt-1 flex-wrap">
          {isApplied ? (
            <div className="flex items-center gap-1.5 text-xs font-extrabold text-emerald-300 bg-emerald-950/90 border border-emerald-600/50 px-4 py-2.5 rounded-xl shadow-xs">
              <CheckCheck size={14} className="stroke-[3]" /> Applied
            </div>
          ) : hasEmails ? (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              type="button"
              onClick={() => onAutoApply(post, firstEmail)}
              disabled={applying}
              className="shimmer-btn flex items-center gap-1.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-amber-500/20 transition cursor-pointer disabled:opacity-50"
            >
              <Zap size={14} className="fill-slate-950" />
              <span>⚡ Auto-Apply (Tailored CV)</span>
            </motion.button>
          ) : (
            <a
              href={post.post_url}
              target="_blank"
              rel="noopener noreferrer"
              className="shimmer-btn flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-lg shadow-blue-500/20 transition cursor-pointer"
            >
              <ExternalLink size={14} />
              <span>View on LinkedIn</span>
            </a>
          )}

          {post.external_apply_url && (
            <a
              href={post.external_apply_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-emerald-200 hover:text-white bg-emerald-950/60 hover:bg-emerald-900/70 border border-emerald-700/70 px-3.5 py-2.5 rounded-xl transition cursor-pointer font-bold"
              title="Unrolled external application link from post"
            >
              <Link2 size={13} className="text-emerald-400" />
              <span>Direct Apply Link</span>
            </a>
          )}

          <motion.button
            whileHover={{ y: -1.5, scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            type="button"
            onClick={() => onTailor(post)}
            className="flex items-center gap-1.5 text-xs text-purple-200 hover:text-white bg-purple-950/60 hover:bg-purple-900/80 border border-purple-700/70 px-3.5 py-2.5 rounded-xl transition cursor-pointer font-bold"
          >
            <Sparkles size={13} className="text-amber-400" />
            <span>Tailor CV</span>
          </motion.button>

          <motion.button
            whileHover={{ y: -1.5, scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            type="button"
            onClick={() => onOpenInMail(post)}
            className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-3.5 py-2.5 rounded-xl transition cursor-pointer font-semibold"
          >
            <MessageSquare size={13} className="text-blue-400" />
            <span>Connection Pitch</span>
          </motion.button>

          <motion.button
            whileHover={{ y: -1.5, scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            type="button"
            onClick={() => setContactsOpen(true)}
            className="flex items-center gap-1.5 text-xs text-cyan-200 hover:text-white bg-cyan-950/50 hover:bg-cyan-900/60 border border-cyan-500/35 px-3.5 py-2.5 rounded-xl transition cursor-pointer font-bold"
            title="Discover company recruiters, HR contacts & MX-verified emails"
          >
            <Users size={13} className="text-cyan-400" />
            <span>Find HR &amp; Emails</span>
          </motion.button>

          <button
            type="button"
            onClick={() => onOpenReader(post)}
            className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] p-2.5 rounded-xl transition cursor-pointer"
            title="Read full post in distraction-free mode"
          >
            <Eye size={14} />
          </button>

          <button
            type="button"
            onClick={() => !isApplied && onSave(post)}
            disabled={isSaved || isApplied}
            className="p-2.5 rounded-xl border border-white/[0.08] hover:bg-white/[0.06] text-slate-300 hover:text-white transition cursor-pointer disabled:opacity-50"
            title={isSaved ? 'Saved to pipeline' : 'Save to pipeline'}
          >
            <Bookmark size={14} className={isSaved ? 'fill-blue-400 text-blue-400' : ''} />
          </button>
        </div>
      </div>

      {/* Recruiter Email Banner */}
      {hasEmails && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08, duration: 0.3 }}
          className="p-4 rounded-2xl bg-gradient-to-r from-purple-950/40 via-indigo-950/35 to-slate-950/60 border border-purple-500/30 space-y-2.5"
        >
          <div className="flex items-center justify-between flex-wrap gap-2">
            <span className="text-[11px] font-extrabold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
              <Mail size={12} className="text-purple-400" /> Mined Recruiter Direct Mailbox
            </span>
            <span className="text-[10px] text-emerald-300 font-bold bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <ShieldCheck size={11} className="text-emerald-400" /> {emailBadge}
            </span>
          </div>
          <div className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-950/90 border border-white/[0.07]">
            <div className="flex items-center gap-2 truncate">
              <span className="text-xs font-mono font-bold text-white truncate">{firstEmail}</span>
              {emails[0]?.name && <span className="text-xs text-slate-400 truncate">({emails[0].name})</span>}
            </div>
            <button
              type="button"
              onClick={() => handleCopyEmail(firstEmail)}
              className="text-xs font-semibold text-purple-300 hover:text-white flex items-center gap-1 px-2.5 py-1 rounded-lg bg-purple-500/15 hover:bg-purple-500/30 border border-purple-500/25 cursor-pointer transition shrink-0"
            >
              {copiedEmail === firstEmail ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              <span>{copiedEmail === firstEmail ? 'Copied!' : 'Copy Email'}</span>
            </button>
          </div>
        </motion.div>
      )}

      {/* ─── CV MATCH & IMPROVEMENT ANALYSIS CARD ─── */}
      <div className="p-4 rounded-2xl bg-slate-950/75 border border-white/[0.07] space-y-3.5">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-extrabold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
            <Target size={14} className="text-blue-400" /> ATS CV Match Diagnostics
          </h4>
          <span className="text-xs font-extrabold text-blue-400">{score}% Compatibility</span>
        </div>

        {/* Score Progress Bar */}
        <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden p-0.5 border border-white/[0.05]">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${Math.max(5, Math.min(100, score))}%` }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className={`h-full rounded-full ${
              score >= 75 ? 'bg-emerald-500' : score >= 55 ? 'bg-blue-500' : 'bg-amber-500'
            }`}
          />
        </div>

        {/* Matched Skills */}
        {matchedSkills.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[11px] font-bold text-emerald-400 flex items-center gap-1">
              <CheckCircle2 size={12} /> Matched Skills on Your CV:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {matchedSkills.map((s, i) => (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.88, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  transition={{ delay: i * 0.03, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                  className="text-[11px] px-2.5 py-0.5 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 font-semibold"
                >
                  ✓ {s}
                </motion.span>
              ))}
            </div>
          </div>
        )}

        {/* Missing Skills */}
        {missingSkills.length > 0 && (
          <div className="space-y-1.5 pt-2 border-t border-white/[0.06]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-amber-400 flex items-center gap-1">
                <AlertTriangle size={12} /> Keywords Missing from Your CV:
              </span>
              <span className="text-[10px] font-semibold text-slate-400">{missingSkills.length} gap(s) detected</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {missingSkills.map((s, i) => (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.88, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  transition={{ delay: 0.05 + i * 0.03, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                  className="text-[11px] px-2.5 py-0.5 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-300 font-semibold flex items-center gap-1"
                >
                  <span>+</span> {s}
                </motion.span>
              ))}
            </div>
          </div>
        )}

        {/* Actionable Tips to Improve */}
        {tips.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-white/[0.06]">
            <span className="text-[11px] font-bold text-purple-300 flex items-center gap-1">
              <Lightbulb size={13} className="text-amber-300" /> AI Recommendations for This Post:
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
              onClick={() => onTailor(post)}
              className="w-full mt-2 py-2.5 px-3 rounded-xl bg-gradient-to-r from-purple-600/30 to-indigo-600/30 hover:from-purple-600/45 hover:to-indigo-600/45 border border-purple-500/40 text-xs font-extrabold text-purple-200 hover:text-white transition flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
            >
              <Sparkles size={13} className="text-amber-300" />
              <span>Bridge Missing Skills with AI Resume Tailor</span>
              <ArrowRight size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Post Text Preview */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <FileText size={12} /> Full Recruiter Publication
          </h4>
          <a
            href={post.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-bold"
          >
            <span>Open on LinkedIn</span>
            <ExternalLink size={11} />
          </a>
        </div>
        <div className="p-4 rounded-2xl bg-slate-950/90 border border-white/[0.07] text-xs text-slate-200 leading-relaxed font-sans whitespace-pre-line max-h-72 overflow-y-auto selection:bg-blue-600 selection:text-white">
          {post.full_text || post.post_snippet}
        </div>
      </div>

      <CompanyContactsModal
        isOpen={contactsOpen}
        onClose={() => setContactsOpen(false)}
        job={post}
        onSelectEmailForApply={(discoveredEmail, contactName) => {
          onAutoApply({
            ...post,
            has_email: true,
            recruiter_emails: [
              { email: discoveredEmail, name: contactName || post.author_name || 'Hiring Team' },
              ...(post.recruiter_emails || []),
            ],
          }, discoveredEmail)
        }}
      />
    </motion.div>
  )
}
