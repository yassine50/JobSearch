import { motion } from 'framer-motion'
import {
  Search, Globe, RotateCw, Loader2, ChevronDown, Link2, Sparkles, Radar
} from 'lucide-react'
import { QUICK_ROLES } from '../../constants/searchConstants.js'

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
    <div className="glass-panel rounded-3xl p-5 sm:p-6 relative overflow-hidden">
      <div className="glow-line-top" />

      <form onSubmit={e => onSearch(e, false)} className="space-y-4">
        {/* Raycast-style Glassmorphic Command Bar */}
        <div className="relative flex flex-col lg:flex-row items-stretch lg:items-center gap-3 p-2.5 rounded-2xl bg-[#050811]/90 border border-white/[0.1] focus-within:border-blue-500/70 focus-within:shadow-[0_0_35px_-5px_rgba(59,130,246,0.3)] transition-all">

          {/* Main Query Input */}
          <div className="relative flex-1 flex items-center min-h-[46px]">
            <div className="absolute left-3.5 w-8 h-8 rounded-xl bg-blue-500/15 border border-blue-500/25 flex items-center justify-center pointer-events-none">
              <Search size={15} className="text-blue-400" />
            </div>
            <input
              type="text"
              value={role}
              onChange={e => setRole(e.target.value)}
              placeholder="Search role, tech stack, or hashtag (e.g. Flutter Developer, #hiring react)..."
              className="w-full bg-transparent pr-4 py-2.5 text-sm font-medium text-white placeholder-slate-500 focus:outline-none"
              style={{ paddingLeft: '3.4rem' }}
            />
          </div>

          <div className="flex items-center gap-2.5 flex-wrap sm:flex-nowrap">
            {/* Location Selector Pill */}
            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              type="button"
              onClick={onOpenLocationPicker}
              className="flex items-center justify-between sm:justify-start gap-2.5 px-4 py-2.5 rounded-xl bg-slate-900/90 hover:bg-slate-800/90 border border-white/[0.08] hover:border-blue-500/40 text-xs text-slate-200 font-semibold transition cursor-pointer shrink-0 max-w-full sm:max-w-[220px]"
              title="Click to select target countries or regions"
            >
              <div className="flex items-center gap-2 truncate">
                <Globe size={14} className="text-blue-400 shrink-0" />
                <span className="truncate">{locationLabel}</span>
              </div>
              <ChevronDown size={13} className="text-slate-500 shrink-0" />
            </motion.button>

            {/* LinkedIn Live Connect Indicator / Button */}
            {onOpenLinkedInConnect && (
              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                type="button"
                onClick={onOpenLinkedInConnect}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-xs font-bold transition cursor-pointer shrink-0 ${
                  isLinkedInConnected
                    ? 'bg-blue-500/10 hover:bg-blue-500/20 border-blue-500/35 text-blue-300 shadow-xs'
                    : 'bg-white/[0.04] hover:bg-white/[0.08] border-white/[0.08] text-slate-200 shadow-xs'
                }`}
                title={
                  isLinkedInConnected
                    ? 'LinkedIn Live Feed Connected. Click to manage session.'
                    : 'Connect your LinkedIn session (li_at) to search live recruiter posts directly with infinite scroll.'
                }
              >
                {isLinkedInConnected ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse shrink-0" />
                    <span className="truncate">Live LinkedIn</span>
                  </>
                ) : (
                  <>
                    <Link2 size={13} className="text-blue-400 shrink-0" />
                    <span className="truncate">Connect LinkedIn</span>
                  </>
                )}
              </motion.button>
            )}

            {/* Submit Search Button */}
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              type="submit"
              disabled={loading}
              className="shimmer-btn px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-extrabold shadow-lg shadow-blue-600/25 transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 shrink-0"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Harvesting...</span>
                </>
              ) : (
                <>
                  <Radar size={14} />
                  <span>Hunt Posts</span>
                </>
              )}
            </motion.button>
          </div>
        </div>

        {/* Quick-Pick Role Chips & Force Crawl Bar */}
        <div className="flex items-center justify-between px-1.5 pt-0.5 text-[11px] text-slate-400 flex-wrap gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-blue-400 font-bold flex items-center gap-1.5 mr-1">
              <Sparkles size={12} className="text-amber-400" /> Quick Roles:
            </span>
            {QUICK_ROLES.map(qRole => {
              const active = role.trim().toLowerCase() === qRole.toLowerCase()
              return (
                <button
                  key={qRole}
                  type="button"
                  onClick={() => setRole(qRole)}
                  className={`px-3 py-1.5 rounded-xl text-[11px] font-semibold border transition cursor-pointer ${
                    active
                      ? 'bg-blue-600/20 border-blue-500/50 text-blue-300 shadow-sm shadow-blue-500/10'
                      : 'bg-white/[0.03] hover:bg-white/[0.07] border-white/[0.07] text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {qRole}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={e => onSearch(e, true)}
              disabled={loading || !role.trim()}
              className="text-slate-400 hover:text-blue-300 flex items-center gap-1.5 font-semibold transition cursor-pointer disabled:opacity-40 px-2.5 py-1.5 rounded-xl hover:bg-white/[0.04] border border-transparent hover:border-white/[0.06]"
              title="Bypass 30-minute search cache and trigger a fresh live crawl"
            >
              <RotateCw size={12} className={loading ? 'animate-spin' : ''} />
              <span>Force Fresh Crawl</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
