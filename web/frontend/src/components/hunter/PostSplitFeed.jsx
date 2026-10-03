import { useRef, useEffect } from 'react'
import { Building2, MapPin, ShieldCheck, CheckCheck, ArrowRight, Loader2, ChevronDown } from 'lucide-react'

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

  // Active scroll listener on the feed container for infinite scroll
  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    if (scrollHeight - scrollTop - clientHeight < 400 && hasMore && !loadingMore) {
      if (onLoadMore) onLoadMore()
    }
  }

  // IntersectionObserver inside the container for seamless infinite scroll
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
      className="space-y-2.5 max-h-[calc(100vh-140px)] overflow-y-auto pr-1 select-none"
    >
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 px-1 pb-1 flex items-center justify-between">
        <span>Posts Feed ({posts.length})</span>
        <span className="text-slate-500 font-normal">Click to preview</span>
      </div>

      {posts.map((post, idx) => {
        const isSelected = selectedPostId === post.id
        const isApplied = isPostApplied(post)
        const isRecent = post.is_under_24h || (post.age_hours != null && post.age_hours <= 24)
        const hasEmail = post.recruiter_emails && post.recruiter_emails.length > 0

        return (
          <div
            key={post.id || idx}
            onClick={() => onSelectPost(post.id)}
            className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 relative ${
              isSelected
                ? 'bg-slate-800 border-blue-500 shadow-md shadow-blue-500/15 ring-1 ring-blue-500'
                : 'bg-slate-850 hover:bg-slate-800 border-slate-750 hover:border-slate-700'
            } ${isApplied ? 'border-l-4 border-l-emerald-500' : ''}`}
          >
            {/* Role Title & Match Fit */}
            <div className="flex items-start justify-between gap-2">
              <h4 className="font-bold text-sm text-white leading-snug line-clamp-2">
                {post.role_title || 'Recruiter Job Posting'}
              </h4>
              <div className="flex items-center gap-1 shrink-0">
                {post.role_fit_score != null && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border bg-purple-950/80 border-purple-700 text-purple-300">
                    {post.role_fit_score}% Fit
                  </span>
                )}
                {post.score != null && post.score !== post.role_fit_score && (
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                    post.score >= 75
                      ? 'bg-emerald-950/80 border-emerald-700 text-emerald-300'
                      : 'bg-blue-950/80 border-blue-700 text-blue-300'
                  }`}>
                    {post.score}% CV
                  </span>
                )}
              </div>
            </div>

            {/* Company, Recruiter, Location */}
            <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
              <span className="font-semibold text-blue-300 flex items-center gap-1 truncate max-w-[140px]">
                <Building2 size={11} className="text-blue-400 shrink-0" />
                {post.company}
              </span>
              <span className="text-slate-500">·</span>
              <span className="text-slate-400 truncate max-w-[120px]">{post.author_name}</span>
              {post.location && (
                <>
                  <span className="text-slate-500">·</span>
                  <span className="text-emerald-300 text-[10px] bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60 flex items-center gap-0.5">
                    <MapPin size={9} /> {post.location}
                  </span>
                </>
              )}
            </div>

            {/* Snippet preview */}
            <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
              {post.full_text || post.post_snippet}
            </p>

            {/* Badges row */}
            <div className="flex items-center justify-between text-[11px] pt-1">
              <div className="flex items-center gap-1.5">
                {hasEmail && (
                  <span className="text-emerald-400 font-semibold flex items-center gap-1 bg-emerald-950/70 px-1.5 py-0.5 rounded border border-emerald-800/60 text-[10px]">
                    <ShieldCheck size={10} /> MX Verified Email
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                {isApplied ? (
                  <span className="text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCheck size={11} /> Applied
                  </span>
                ) : (
                  <span className={`text-[11px] font-medium flex items-center gap-0.5 ${
                    isSelected ? 'text-blue-300 font-bold' : 'text-slate-400 hover:text-white'
                  }`}>
                    Details <ArrowRight size={10} />
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}

      {/* Infinite Scroll Sentinel & Load More Indicator */}
      <div ref={observerTargetRef} className="pt-3 pb-2 text-center">
        {loadingMore ? (
          <div className="flex flex-col items-center justify-center py-5 px-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-semibold text-slate-300 shadow-sm space-y-2.5">
            {/* Authentic LinkedIn C-shaped loading spinner from media_1789952339246.png */}
            <div className="w-7 h-7 rounded-full border-[3px] border-slate-700 border-t-blue-500 border-r-blue-400 animate-spin" />
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-white font-bold text-xs tracking-wide">LinkedIn Page Loading...</span>
              <span className="text-[11px] font-normal text-slate-400 animate-pulse">
                Scrolling down to load next batch & scraping posts...
              </span>
            </div>
          </div>
        ) : hasMore ? (
          <button
            type="button"
            onClick={onLoadMore}
            className="w-full py-2.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 hover:border-slate-600 text-xs font-semibold text-slate-300 hover:text-white transition flex items-center justify-center gap-2 cursor-pointer shadow-sm"
          >
            <ChevronDown size={14} className="text-blue-400" />
            <span>Load More Posts (Page {page + 1})</span>
          </button>
        ) : posts.length > 0 ? (
          <div className="py-2.5 px-4 rounded-xl bg-slate-850/60 border border-slate-800 text-[11px] text-slate-500 font-medium">
            ✓ All matching recruiter posts loaded ({posts.length} total)
          </div>
        ) : null}
      </div>
    </div>
  )
}
