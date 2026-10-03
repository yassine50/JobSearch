import { Search, Globe, RotateCw, Loader2, ChevronDown, Link2, CheckCircle2 } from 'lucide-react'

export default function PostSearchHeader({
  role,
  setRole,
  selectedLocations,
  onOpenLocationPicker,
  onSearch,
  loading,
  isLinkedInConnected = false,
  onOpenLinkedInConnect
}) {
  const isWorldwide = selectedLocations.length === 1 && selectedLocations[0].toLowerCase() === 'worldwide'
  const locationLabel = isWorldwide ? 'Worldwide' : selectedLocations.join(', ')

  return (
    <div className="space-y-2.5">
      <form onSubmit={e => onSearch(e, false)} className="space-y-2">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 p-1.5 rounded-2xl bg-slate-900 border border-slate-750 shadow-lg shadow-black/20 focus-within:border-blue-500/80 transition-all">
          {/* Main Query Input */}
          <div className="relative flex-1 flex items-center min-h-[44px]">
            <Search size={18} className="absolute left-3.5 text-slate-500 pointer-events-none" />
            <input
              type="text"
              value={role}
              onChange={e => setRole(e.target.value)}
              placeholder="Search by role or hashtag (e.g. #hiring flutter, react in Germany)..."
              className="w-full bg-transparent pl-11 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none"
            />
          </div>

          {/* Location Selector Pill */}
          <button
            type="button"
            onClick={onOpenLocationPicker}
            className="flex items-center justify-between sm:justify-start gap-2 px-3.5 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-800 border border-slate-700 hover:border-slate-600 text-xs text-slate-250 font-medium transition cursor-pointer shrink-0 max-w-full sm:max-w-[200px]"
            title="Click to change target countries/regions"
          >
            <div className="flex items-center gap-1.5 truncate">
              <Globe size={13} className="text-blue-400 shrink-0" />
              <span className="truncate">{locationLabel}</span>
            </div>
            <ChevronDown size={12} className="text-slate-500 shrink-0" />
          </button>

          {/* LinkedIn Live Connect Indicator / Button */}
          <button
            type="button"
            onClick={onOpenLinkedInConnect}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-semibold transition cursor-pointer shrink-0 ${
              isLinkedInConnected
                ? 'bg-emerald-950/60 hover:bg-emerald-900/60 border-emerald-500/50 text-emerald-300 shadow-xs'
                : 'bg-blue-950/40 hover:bg-blue-900/50 border-blue-500/40 text-blue-300 shadow-xs'
            }`}
            title={
              isLinkedInConnected
                ? 'LinkedIn Live Feed Connected. Click to manage session.'
                : 'Connect your LinkedIn session (li_at) to search live recruiter posts directly with infinite scroll.'
            }
          >
            {isLinkedInConnected ? (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                <span className="truncate">Live LinkedIn</span>
              </>
            ) : (
              <>
                <Link2 size={13} className="text-blue-400 shrink-0" />
                <span className="truncate">Connect LinkedIn</span>
              </>
            )}
          </button>

          {/* Submit Search Button */}
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-500/20 transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 shrink-0"
          >
            {loading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                <span>Harvesting...</span>
              </>
            ) : (
              <>
                <Search size={14} />
                <span>Search Posts</span>
              </>
            )}
          </button>
        </div>

        {/* Quick Tips & Status */}
        <div className="flex items-center justify-between px-1 text-[11px] text-slate-400 flex-wrap gap-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-blue-400 font-medium">💡 Quick Tip:</span>
            <span>Search with hashtags like <code className="text-blue-300">#hiring flutter</code>, phrases like <code className="text-blue-300">"we are hiring" react</code>, or specify cities/regions.</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={e => onSearch(e, true)}
              disabled={loading || !role.trim()}
              className="text-slate-400 hover:text-blue-300 flex items-center gap-1 transition cursor-pointer disabled:opacity-40"
              title="Force fresh re-crawl bypassing cached results"
            >
              <RotateCw size={11} className={loading ? 'animate-spin' : ''} />
              <span>Force Fresh Crawl</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
