import { useState } from 'react'
import {
  Briefcase, User, Building2, MapPin, Mail, ExternalLink, Sparkles,
  Zap, MessageSquare, Bookmark, ShieldCheck, Check, Copy, CheckCheck,
  CheckCircle2, AlertCircle, FileText, Target, Eye, TrendingUp,
  AlertTriangle, Lightbulb, ArrowRight
} from 'lucide-react'

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

  if (!post) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center text-slate-500 bg-slate-900/60 border border-slate-800 rounded-2xl">
        <Briefcase size={36} className="text-slate-600 mb-3" />
        <p className="text-sm font-semibold text-slate-400">Select a LinkedIn post from the feed</p>
        <p className="text-xs text-slate-500 mt-1">Review recruiter contact, tailored match analysis, missing skills, and 1-click apply</p>
      </div>
    )
  }

  const emails = post.recruiter_emails || []
  const hasEmails = emails.length > 0
  const firstEmail = emails[0]?.email

  const handleCopyEmail = (em) => {
    navigator.clipboard.writeText(em)
    setCopiedEmail(em)
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  const score = post.score ?? post.role_fit_score ?? 70
  const matchedSkills = post.matched_skills || []
  const missingSkills = post.missing_skills || []
  const tips = post.tips || []

  return (
    <div className="sticky top-4 max-h-[calc(100vh-140px)] overflow-y-auto space-y-4 bg-slate-900 border border-slate-750 rounded-2xl p-6 shadow-xl">
      {/* Header & Role Info */}
      <div className="space-y-3 pb-4 border-b border-slate-800">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <h3 className="text-lg md:text-xl font-bold text-white tracking-tight leading-snug">
              {post.role_title || 'Recruiter Job Posting'}
            </h3>
            <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap pt-0.5">
              <span className="font-bold text-white flex items-center gap-1">
                <User size={12} className="text-slate-400" />
                {post.author_name}
              </span>
              <span className="text-slate-500">·</span>
              <span className="font-semibold text-blue-300 flex items-center gap-1">
                <Building2 size={12} className="text-blue-400" />
                {post.company}
              </span>
              {post.location && (
                <>
                  <span className="text-slate-500">·</span>
                  <span className="text-emerald-300 font-semibold bg-emerald-950/70 px-2 py-0.5 rounded-md border border-emerald-800/70 flex items-center gap-1">
                    <MapPin size={11} className="text-emerald-400" />
                    {post.location}
                  </span>
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

        {/* Action Toolbar */}
        <div className="flex items-center gap-2 pt-2 flex-wrap">
          {isApplied ? (
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 bg-emerald-950/90 border border-emerald-800 px-4 py-2 rounded-xl shadow-xs">
              <CheckCheck size={14} className="stroke-[3]" /> Applied
            </div>
          ) : hasEmails ? (
            <button
              type="button"
              onClick={() => onAutoApply(post, firstEmail)}
              disabled={applying}
              className="flex items-center gap-1.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs px-4 py-2.5 rounded-xl shadow-md shadow-amber-500/20 transition cursor-pointer disabled:opacity-50"
            >
              <Zap size={14} className="fill-slate-950" />
              <span>⚡ Auto-Apply (Tailored CV)</span>
            </button>
          ) : (
            <a
              href={post.post_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-500/20 transition cursor-pointer"
            >
              <ExternalLink size={14} />
              <span>View on LinkedIn</span>
            </a>
          )}

          <button
            type="button"
            onClick={() => onTailor(post)}
            className="flex items-center gap-1.5 text-xs text-purple-200 hover:text-white bg-purple-950/60 hover:bg-purple-900/80 border border-purple-700/80 px-3.5 py-2.5 rounded-xl transition cursor-pointer font-medium"
          >
            <Sparkles size={13} className="text-amber-400" />
            <span>Tailor CV</span>
          </button>

          <button
            type="button"
            onClick={() => onOpenInMail(post)}
            className="flex items-center gap-1.5 text-xs text-slate-200 hover:text-white bg-slate-800 hover:bg-slate-750 border border-slate-700 px-3 py-2.5 rounded-xl transition cursor-pointer font-medium"
          >
            <MessageSquare size={13} className="text-blue-400" />
            <span>Connection Pitch</span>
          </button>

          <button
            type="button"
            onClick={() => onOpenReader(post)}
            className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-750 border border-slate-700 p-2.5 rounded-xl transition cursor-pointer"
            title="Read full post in reader mode"
          >
            <Eye size={14} />
          </button>

          <button
            type="button"
            onClick={() => !isApplied && onSave(post)}
            disabled={isSaved || isApplied}
            className="p-2.5 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-300 hover:text-white transition cursor-pointer disabled:opacity-50"
            title={isSaved ? 'Saved to pipeline' : 'Save to pipeline'}
          >
            <Bookmark size={14} className={isSaved ? 'fill-blue-400 text-blue-400' : ''} />
          </button>
        </div>
      </div>

      {/* Recruiter Email Banner */}
      {hasEmails && (
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
              <span className="text-xs font-mono font-bold text-white truncate">{firstEmail}</span>
              {emails[0]?.name && <span className="text-xs text-slate-400 truncate">({emails[0].name})</span>}
            </div>
            <button
              type="button"
              onClick={() => handleCopyEmail(firstEmail)}
              className="text-xs text-purple-300 hover:text-white flex items-center gap-1 px-2 py-1 rounded hover:bg-purple-900/50 cursor-pointer transition shrink-0"
            >
              {copiedEmail === firstEmail ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              <span>{copiedEmail === firstEmail ? 'Copied' : 'Copy Email'}</span>
            </button>
          </div>
        </div>
      )}

      {/* ─── CV MATCH & IMPROVEMENT ANALYSIS CARD ─── */}
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
        {matchedSkills.length > 0 && (
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
        )}

        {/* Missing Things on your CV */}
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
              onClick={() => onTailor(post)}
              className="w-full mt-2 py-2 px-3 rounded-lg bg-purple-900/40 hover:bg-purple-900/60 border border-purple-700/60 text-xs font-bold text-purple-200 hover:text-white transition flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
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
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <FileText size={12} /> Post Publication Content
          </h4>
          <a
            href={post.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
          >
            <span>Original LinkedIn Post</span>
            <ExternalLink size={11} />
          </a>
        </div>
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 leading-relaxed font-sans whitespace-pre-line max-h-72 overflow-y-auto selection:bg-blue-600 selection:text-white">
          {post.full_text || post.post_snippet}
        </div>
      </div>
    </div>
  )
}
