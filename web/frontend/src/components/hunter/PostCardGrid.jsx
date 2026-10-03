import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Building2, User, MapPin, Mail, ExternalLink, Sparkles,
  Zap, MessageSquare, Bookmark, ShieldCheck, Check, Copy,
  CheckCircle2, Target, Loader2, ChevronDown
} from 'lucide-react'

export default function PostCardGrid({
  posts = [],
  isPostApplied,
  isPostSaved,
  applyingPostId,
  onAutoApply,
  onTailor,
  onOpenInMail,
  onSave,
  loadingMore,
  hasMore,
  page,
  onLoadMore,
  cardsObserverTargetRef
}) {
  const [copiedEmail, setCopiedEmail] = useState(null)

  const copyEmail = (email) => {
    if (!email) return
    navigator.clipboard.writeText(email)
    setCopiedEmail(email)
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {posts.map((post, idx) => {
        const isApplied = isPostApplied(post)
        const isSaved = isPostSaved(post)
        const hasEmails = post.recruiter_emails && post.recruiter_emails.length > 0
        const firstEmail = hasEmails ? post.recruiter_emails[0].email : null

        return (
          <motion.div
            key={post.id || idx}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(idx * 0.03, 0.3) }}
            className={`rounded-2xl border bg-slate-900 flex flex-col justify-between p-5 transition-all space-y-3 relative card-hover ${
              isApplied
                ? 'border-emerald-600/60 bg-emerald-950/10'
                : 'border-slate-750 hover:border-slate-650'
            }`}
          >
            {/* Top Row: Role Title & Match Badges */}
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-bold text-base text-white leading-snug line-clamp-2">
                  {post.role_title || 'LinkedIn Recruiter Publication'}
                </h3>
                <div className="flex items-center gap-1 shrink-0">
                  {post.role_fit_score != null && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-md border bg-purple-950/80 border-purple-700 text-purple-300">
                      {post.role_fit_score}% Fit
                    </span>
                  )}
                  {post.score != null && post.score !== post.role_fit_score && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${
                      post.score >= 75
                        ? 'bg-emerald-950/80 border-emerald-700 text-emerald-300'
                        : 'bg-blue-950/80 border-blue-700 text-blue-300'
                    }`}>
                      {post.score}% CV
                    </span>
                  )}
                </div>
              </div>

              {/* Meta: Company, Author, Location */}
              <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
                <span className="font-semibold text-blue-300 flex items-center gap-1">
                  <Building2 size={12} className="text-blue-400" />
                  {post.company}
                </span>
                <span className="text-slate-500">·</span>
                <span className="text-slate-400">{post.author_name}</span>
                {post.location && (
                  <>
                    <span className="text-slate-500">·</span>
                    <span className="text-emerald-300 text-[10px] bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60 flex items-center gap-0.5">
                      <MapPin size={9} /> {post.location}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Post Snippet */}
            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 leading-relaxed font-sans line-clamp-3">
              {post.full_text || post.post_snippet}
            </div>

            {/* Skills & Missing Tags Summary */}
            {(post.matched_skills?.length > 0 || post.missing_skills?.length > 0) && (
              <div className="space-y-1.5 pt-0.5">
                {post.missing_skills && post.missing_skills.length > 0 ? (
                  <div className="flex items-center gap-1 flex-wrap text-[10px]">
                    <span className="text-amber-400 font-semibold">Missing from CV:</span>
                    {post.missing_skills.slice(0, 3).map((ms, i) => (
                      <span key={i} className="px-1.5 py-0.2 rounded bg-amber-950/60 border border-amber-800/60 text-amber-300">
                        +{ms}
                      </span>
                    ))}
                    {post.missing_skills.length > 3 && (
                      <span className="text-slate-500">+{post.missing_skills.length - 3} more</span>
                    )}
                  </div>
                ) : post.matched_skills && post.matched_skills.length > 0 ? (
                  <div className="flex items-center gap-1 flex-wrap text-[10px]">
                    <span className="text-emerald-400 font-semibold">Matched:</span>
                    {post.matched_skills.slice(0, 3).map((ms, i) => (
                      <span key={i} className="px-1.5 py-0.2 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-300">
                        ✓ {ms}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            )}

            {/* Recruiter Email & Action Footer */}
            <div className="space-y-3 pt-1 border-t border-slate-800/80">
              {hasEmails ? (
                <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-purple-950/30 border border-purple-800/40">
                  <div className="flex items-center gap-1.5 truncate">
                    <Mail size={12} className="text-purple-400 shrink-0" />
                    <span className="text-xs font-mono font-bold text-white truncate">{firstEmail}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => copyEmail(firstEmail)}
                    className="text-xs text-purple-300 hover:text-white flex items-center gap-1 font-medium px-2 py-0.5 rounded hover:bg-purple-900/50 cursor-pointer"
                  >
                    {copiedEmail === firstEmail ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                    <span>{copiedEmail === firstEmail ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
              ) : (
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <span>Direct LinkedIn Publication</span>
                </span>
              )}

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-wrap">
                {isApplied ? (
                  <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 bg-emerald-950/90 border border-emerald-800 px-3.5 py-2 rounded-xl shadow-xs">
                    <Check size={13} className="stroke-[3]" /> Applied
                  </div>
                ) : hasEmails ? (
                  <button
                    type="button"
                    onClick={() => onAutoApply(post, firstEmail)}
                    disabled={applyingPostId === post.id}
                    className="flex items-center gap-1.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs px-3.5 py-2 rounded-xl shadow-md shadow-amber-500/20 transition cursor-pointer disabled:opacity-50"
                  >
                    <Zap size={13} className="fill-slate-950" />
                    <span>Auto-Apply</span>
                  </button>
                ) : (
                  <a
                    href={post.post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-600/25 transition cursor-pointer"
                  >
                    <ExternalLink size={13} />
                    <span>View Post</span>
                  </a>
                )}

                <button
                  type="button"
                  onClick={() => onTailor(post)}
                  className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-750 border border-slate-700 px-2.5 py-2 rounded-xl transition cursor-pointer font-medium"
                >
                  <Sparkles size={12} className="text-amber-400" />
                  <span>Tailor</span>
                </button>

                <button
                  type="button"
                  onClick={() => onOpenInMail(post)}
                  className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-750 border border-slate-700 px-2.5 py-2 rounded-xl transition cursor-pointer font-medium"
                  title="Generate LinkedIn connection pitch"
                >
                  <MessageSquare size={12} className="text-blue-400" />
                  <span>Pitch</span>
                </button>

                <button
                  type="button"
                  onClick={() => !isApplied && onSave(post)}
                  disabled={isSaved || isApplied}
                  className="p-2 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-300 hover:text-white transition cursor-pointer disabled:opacity-50 ml-auto"
                  title={isSaved ? 'Saved to pipeline' : 'Save to pipeline'}
                >
                  <Bookmark size={13} className={isSaved ? 'fill-blue-400 text-blue-400' : ''} />
                </button>
              </div>
            </div>
          </motion.div>
        )
      })}

      {/* Infinite Scroll Sentinel & Load More for Cards View */}
      <div ref={cardsObserverTargetRef} className="col-span-full pt-6 pb-4 text-center">
        {loadingMore ? (
          <div className="inline-flex items-center justify-center gap-2 py-3 px-6 rounded-xl bg-slate-800/90 border border-slate-700 text-sm font-semibold text-blue-400 shadow-md">
            <Loader2 size={17} className="animate-spin text-blue-400" />
            <span>Loading more LinkedIn recruiter posts...</span>
          </div>
        ) : hasMore ? (
          <button
            type="button"
            onClick={onLoadMore}
            className="inline-flex items-center justify-center gap-2 py-3 px-6 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 hover:border-slate-600 text-sm font-semibold text-slate-200 hover:text-white transition cursor-pointer shadow-md hover:shadow-lg"
          >
            <ChevronDown size={16} className="text-blue-400" />
            <span>Load More Posts (Page {page + 1})</span>
          </button>
        ) : posts.length > 0 ? (
          <div className="inline-block py-2.5 px-5 rounded-xl bg-slate-850/60 border border-slate-800 text-xs text-slate-500 font-medium">
            ✓ All matching recruiter posts loaded ({posts.length} total)
          </div>
        ) : null}
      </div>
    </div>
  )
}
