import { useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Building2, MapPin, ShieldCheck, CheckCheck, ArrowRight,
  ChevronDown, Clock, UserCheck, Flame
} from 'lucide-react'

export default function PostSplitFeed({
  posts = [],
  selectedPostId,
  onSelectPost,
  isPostApplied,
  loadingMore,
  hasMore,
  page,
  onLoadMore,
  observerTargetRef
}) {
  const containerRef = useRef(null)

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    if (scrollHeight - scrollTop - clientHeight < 400 && hasMore && !loadingMore) {
      if (onLoadMore) onLoadMore()
    }
  }

  useEffect(() => {
    if (!containerRef.current || !hasMore || loadingMore) return

    const el = observerTargetRef?.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loadingMore) {
          if (onLoadMore) onLoadMore()
        }
      },
      { root: containerRef.current, rootMargin: '300px', threshold: 0.05 }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loadingMore, onLoadMore, observerTargetRef])

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="space-y-2.5 max-h-[calc(100vh-140px)] overflow-y-auto pr-1.5 select-none"
    >
      <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400 px-1.5 pb-1 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          Live Recruiter Feed ({posts.length})
        </span>
        <span className="text-slate-500 font-medium text-[10px]">Select to inspect</span>
      </div>

      {posts.map((post, idx) => {
        const isSelected = selectedPostId === post.id
        const isApplied = isPostApplied(post)
        const isRecent = post.is_under_24h || (post.age_hours != null && post.age_hours <= 24)
        const hasEmail = post.recruiter_emails && post.recruiter_emails.length > 0
        const emailBadge = hasEmail ? (post.recruiter_emails[0]?.badge || 'MX Verified Email') : null
        const isHumanRecruiter = post.author_authority === 'human_recruiter'
        const authorInitial = (post.author_name || post.company || 'R').charAt(0).toUpperCase()

        return (
          <motion.div
            key={post.id || idx}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -2.5, scale: 1.005 }}
            whileTap={{ scale: 0.992 }}
            transition={{ delay: Math.min(idx * 0.03, 0.25), duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            onClick={() => onSelectPost(post.id)}
            className={`group p-4 rounded-2xl border transition-all cursor-pointer space-y-2.5 relative overflow-hidden ${
              isSelected
                ? 'bg-gradient-to-br from-slate-800/95 via-slate-900/95 to-blue-950/40 border-blue-500/80 shadow-lg shadow-blue-500/15 ring-1 ring-blue-500/50'
                : 'glass-panel hover:bg-slate-800/60 hover:border-white/[0.14]'
            } ${isApplied ? 'border-l-4 border-l-emerald-500' : ''}`}
          >
            {/* Active Left Glow Accent with Shared Layout Spring */}
            {isSelected && (
              <motion.div
                layoutId="active-post-left-accent"
                transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-blue-400 via-indigo-500 to-purple-500 z-0"
              />
            )}

            {/* Top Row: Role Title & Score Pills */}
            <div className="flex items-start justify-between gap-2.5">
              <h4 className={`font-extrabold text-sm leading-snug line-clamp-2 transition-colors ${
                isSelected ? 'text-white' : 'text-slate-100 group-hover:text-blue-200'
              }`}>
                {post.role_title || 'Recruiter Job Posting'}
              </h4>
              <div className="flex items-center gap-1 shrink-0">
                {post.role_fit_score != null && (
                  <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-lg border bg-purple-500/15 border-purple-500/30 text-purple-300">
                    {post.role_fit_score}% Fit
                  </span>
                )}
                {post.score != null && post.score !== post.role_fit_score && (
                  <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-lg border ${
                    post.score >= 75
                      ? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300'
                      : 'bg-blue-500/15 border-blue-500/35 text-blue-300'
                  }`}>
                    {post.score}% CV
                  </span>
                )}
              </div>
            </div>

            {/* Recruiter Avatar + Company + Location + Age */}
            <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
              <div className="flex items-center gap-1.5 min-w-0">
                <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-500 text-[10px] font-black text-white flex items-center justify-center shrink-0">
                  {authorInitial}
                </div>
                <span className="text-slate-200 font-semibold truncate max-w-[125px]">
                  {post.author_name}
                </span>
              </div>
              <span className="text-slate-600">·</span>
              <span className="font-bold text-blue-300 flex items-center gap-1 truncate max-w-[130px]">
                <Building2 size={11} className="text-blue-400 shrink-0" />
                {post.company}
              </span>
              {post.location && (
                <span className="text-emerald-300 text-[10px] font-semibold bg-emerald-950/60 px-1.5 py-0.5 rounded-md border border-emerald-800/60 flex items-center gap-0.5">
                  <MapPin size={9} /> {post.location}
                </span>
              )}
              {post.age_str && (
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md border flex items-center gap-0.5 ${
                  isRecent
                    ? 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                    : 'bg-white/[0.03] border-white/[0.07] text-slate-400'
                }`}>
                  {isRecent ? <Flame size={9} className="text-amber-400" /> : <Clock size={9} />}
                  {post.age_str}
                </span>
              )}
            </div>

            {/* Snippet preview */}
            <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
              {post.full_text || post.post_snippet}
            </p>

            {/* Bottom Intelligence Badges Row */}
            <div className="flex items-center justify-between text-[11px] pt-1">
              <div className="flex items-center gap-1.5 flex-wrap">
                {hasEmail && (
                  <span className="text-emerald-300 font-bold flex items-center gap-1 bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/25 text-[10px]">
                    <ShieldCheck size={10} className="text-emerald-400" />
                    {emailBadge}
                  </span>
                )}
                {isHumanRecruiter && (
                  <span className="text-indigo-300 font-semibold flex items-center gap-1 bg-indigo-500/10 px-1.5 py-0.5 rounded-md border border-indigo-500/25 text-[10px]">
                    <UserCheck size={10} className="text-indigo-400" />
                    Recruiter
                  </span>
                )}
                {post.required_years != null && (
                  <span className="text-slate-300 font-semibold bg-white/[0.04] px-1.5 py-0.5 rounded-md border border-white/[0.08] text-[10px]">
                    {post.required_years}+ yrs
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                {isApplied ? (
                  <span className="text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCheck size={11} /> Applied
                  </span>
                ) : (
                  <span className={`text-[11px] font-bold flex items-center gap-0.5 transition-transform group-hover:translate-x-0.5 ${
                    isSelected ? 'text-blue-300' : 'text-slate-400 group-hover:text-white'
                  }`}>
                    Inspect <ArrowRight size={10} />
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )
      })}

      {/* Infinite Scroll Sentinel & Load More Indicator */}
      <div ref={observerTargetRef} className="pt-3 pb-2 text-center">
        {loadingMore ? (
          <div className="flex flex-col items-center justify-center py-5 px-4 rounded-2xl glass-panel text-xs font-semibold text-slate-300 shadow-sm space-y-2.5">
            <div className="w-7 h-7 rounded-full border-[3px] border-slate-700 border-t-blue-500 border-r-indigo-400 animate-spin" />
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-white font-bold text-xs tracking-wide">Harvesting Next Recruiter Batch...</span>
              <span className="text-[11px] font-normal text-slate-400 animate-pulse">
                Scrolling feed & verifying corporate mailboxes...
              </span>
            </div>
          </div>
        ) : hasMore ? (
          <button
            type="button"
            onClick={onLoadMore}
            className="w-full py-2.5 px-4 rounded-2xl glass-panel hover:border-blue-500/40 text-xs font-bold text-slate-300 hover:text-white transition flex items-center justify-center gap-2 cursor-pointer"
          >
            <ChevronDown size={14} className="text-blue-400" />
            <span>Load More Posts (Page {page + 1})</span>
          </button>
        ) : posts.length > 0 ? (
          <div className="py-2.5 px-4 rounded-2xl bg-white/[0.02] border border-white/[0.05] text-[11px] text-slate-500 font-semibold">
            ✓ All matching recruiter posts loaded ({posts.length} total)
          </div>
        ) : null}
      </div>
    </div>
  )
}
