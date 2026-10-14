import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Columns, LayoutGrid, SlidersHorizontal, ShieldCheck,
  Zap, X, RotateCcw, Clock, ArrowUpDown
} from 'lucide-react'
import { DEFAULT_POST_FILTERS } from '../../constants/searchConstants.js'

export default function PostFilterBar({
  postFilters = DEFAULT_POST_FILTERS,
  setPostFilters,
  viewMode,
  setViewMode,
  posts = [],
  onBatchApply,
  onApplyAndSearch
}) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  const emailCount = posts.filter(p => p.has_email && p.recruiter_emails && p.recruiter_emails.length > 0).length

  const activeCount = [
    postFilters.sortBy !== 'relevant',
    postFilters.datePosted !== 'all',
    Boolean(postFilters.emailOnly)
  ].filter(Boolean).length

  const handleReset = () => {
    setPostFilters(DEFAULT_POST_FILTERS)
  }

  return (
    <div className="glass-card rounded-2xl px-4 py-3.5">
      <div className="flex items-center justify-between gap-3.5 flex-wrap">
        {/* Left: Clean Filter Controls & Quick Chips */}
        <div className="flex items-center gap-2.5 flex-wrap text-xs">
          {/* Main "Post Filters" Button */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="px-3.5 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-white/[0.08] hover:border-blue-500/40 text-slate-200 font-bold flex items-center gap-1.5 transition cursor-pointer shadow-xs"
          >
            <SlidersHorizontal size={13} className="text-blue-400" />
            <span>Filters</span>
            {activeCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-extrabold">
                {activeCount}
              </span>
            )}
          </motion.button>

          {/* Quick Date Dropdown */}
          <div className="relative flex items-center">
            <Clock size={12} className="absolute left-3 text-slate-400 pointer-events-none" />
            <select
              value={postFilters.datePosted}
              onChange={e => {
                const next = { ...postFilters, datePosted: e.target.value }
                setPostFilters(next)
                if (onApplyAndSearch) onApplyAndSearch(next)
              }}
              className="bg-slate-900/90 border border-white/[0.08] hover:border-white/[0.15] rounded-xl pl-8 pr-3 py-2 text-xs font-semibold text-slate-200 focus:outline-none focus:border-blue-500 cursor-pointer transition"
            >
              <option value="all">Time: Any time</option>
              <option value="24h">🔥 Past 24 hours</option>
              <option value="week">Past week</option>
              <option value="month">Past month</option>
            </select>
          </div>

          {/* Quick Email Filter Chip */}
          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type="button"
            onClick={() => {
              setPostFilters(p => ({ ...p, emailOnly: !p.emailOnly }))
            }}
            className={`px-3.5 py-2 rounded-xl font-bold border transition cursor-pointer flex items-center gap-1.5 ${
              postFilters.emailOnly
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50 shadow-sm shadow-emerald-500/10'
                : 'bg-slate-900/90 text-slate-400 border-white/[0.08] hover:text-white hover:border-white/[0.15]'
            }`}
          >
            <ShieldCheck size={13} className={postFilters.emailOnly ? 'text-emerald-400' : 'text-slate-500'} />
            <span>Verified Email ({emailCount})</span>
          </motion.button>

          {activeCount > 0 && (
            <button
              type="button"
              onClick={handleReset}
              className="text-[11px] font-semibold text-slate-400 hover:text-rose-300 flex items-center gap-1 transition cursor-pointer px-2 py-1 rounded-lg hover:bg-rose-500/10"
              title="Clear all filters"
            >
              <RotateCcw size={11} />
              <span>Reset</span>
            </button>
          )}
        </div>

        {/* Right: Batch Apply, Sort & View Mode */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Bulk Auto-Apply Button */}
          {emailCount > 0 && onBatchApply && (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              type="button"
              onClick={onBatchApply}
              className="shimmer-btn px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-extrabold text-xs shadow-lg shadow-blue-600/25 transition flex items-center gap-1.5 cursor-pointer shrink-0 border border-blue-400/30"
              title="Dispatch tailored applications to all verified recruiters"
            >
              <Zap size={13} className="text-amber-300 fill-amber-300" />
              <span>Auto-Apply to All ({emailCount})</span>
            </motion.button>
          )}

          {/* Sort Dropdown: Most relevant / Most recent */}
          <div className="relative flex items-center text-xs">
            <ArrowUpDown size={12} className="absolute left-3 text-slate-400 pointer-events-none" />
            <select
              value={postFilters.sortBy}
              onChange={e => {
                const next = { ...postFilters, sortBy: e.target.value }
                setPostFilters(next)
                if (onApplyAndSearch) onApplyAndSearch(next)
              }}
              className="bg-slate-900/90 border border-white/[0.08] hover:border-white/[0.15] rounded-xl pl-8 pr-3 py-2 text-xs font-semibold text-slate-200 focus:outline-none focus:border-blue-500 cursor-pointer transition"
            >
              <option value="relevant">Sort: AI Match & Email</option>
              <option value="recent">Sort: Most Recent</option>
            </select>
          </div>

          {/* Animated Segmented View Mode Toggle */}
          <div className="relative flex items-center p-1 rounded-xl bg-slate-900/90 border border-white/[0.08]">
            {[
              { id: 'split', Icon: Columns, label: 'Split' },
              { id: 'cards', Icon: LayoutGrid, label: 'Grid' },
            ].map(mode => {
              const active = viewMode === mode.id
              const Icon = mode.Icon
              return (
                <button
                  key={mode.id}
                  type="button"
                  onClick={() => setViewMode(mode.id)}
                  className={`relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                    active ? 'text-white' : 'text-slate-400 hover:text-white'
                  }`}
                  title={mode.id === 'split' ? 'Split Workbench View' : 'Multi-column Cards Grid'}
                >
                  {active && (
                    <motion.div
                      layoutId="hunter-view-toggle"
                      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                      className="absolute inset-0 rounded-lg bg-blue-600 shadow-xs z-0"
                    />
                  )}
                  <Icon size={14} className="relative z-10" />
                  <span className="relative z-10 hidden sm:inline text-[11px]">{mode.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Streamlined LinkedIn Post Filters Modal */}
      <AnimatePresence>
        {drawerOpen && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
            onClick={() => setDrawerOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 15 }}
              className="w-full max-w-lg glass-card rounded-3xl overflow-hidden flex flex-col max-h-[90vh] relative"
              onClick={e => e.stopPropagation()}
            >
              <div className="glow-line-top" />
              {/* Header */}
              <div className="p-5 border-b border-white/[0.07] flex items-center justify-between bg-slate-950/60">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400">
                    <SlidersHorizontal size={15} />
                  </div>
                  <h3 className="font-extrabold text-white text-base">LinkedIn Post Filters</h3>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleReset}
                    className="text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-white/5 transition flex items-center gap-1 cursor-pointer"
                  >
                    <RotateCcw size={12} />
                    <span>Reset</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setDrawerOpen(false)}
                    className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-white/5 transition cursor-pointer"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* Body */}
              <div className="p-6 space-y-6 overflow-y-auto flex-1 text-xs">
                {/* 1. Sort by */}
                <div className="space-y-2.5">
                  <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">Sort Ranking</h4>
                  <div className="flex items-center gap-2">
                    {[
                      { id: 'relevant', label: 'Most Relevant (AI + Email Tier)' },
                      { id: 'recent', label: 'Most Recent First' }
                    ].map(opt => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setPostFilters(p => ({ ...p, sortBy: opt.id }))}
                        className={`px-3.5 py-2.5 rounded-xl font-bold border transition cursor-pointer ${
                          postFilters.sortBy === opt.id
                            ? 'bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-600/20'
                            : 'bg-slate-950/80 text-slate-400 border-white/[0.08] hover:text-white'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 2. Date Posted */}
                <div className="space-y-2.5 border-t border-white/[0.06] pt-5">
                  <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">Publication Recency</h4>
                  <div className="flex items-center gap-2 flex-wrap">
                    {[
                      { id: 'all', label: 'Any time' },
                      { id: '24h', label: '🔥 Past 24 hours' },
                      { id: 'week', label: 'Past week' },
                      { id: 'month', label: 'Past month' }
                    ].map(opt => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setPostFilters(p => ({ ...p, datePosted: opt.id }))}
                        className={`px-3.5 py-2.5 rounded-xl font-bold border transition cursor-pointer ${
                          postFilters.datePosted === opt.id
                            ? 'bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-600/20'
                            : 'bg-slate-950/80 text-slate-400 border-white/[0.08] hover:text-white'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 3. With Verified Recruiter Email Toggle */}
                <div className="space-y-2.5 border-t border-white/[0.06] pt-5">
                  <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">Recruiter Contact</h4>
                  <label className="flex items-center justify-between p-4 rounded-2xl bg-slate-950/80 border border-white/[0.08] cursor-pointer select-none hover:border-emerald-500/40 transition">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
                        <ShieldCheck size={18} />
                      </div>
                      <div>
                        <span className="font-bold text-white block">Verified Recruiter Email Only</span>
                        <span className="text-[11px] text-slate-400">Only show posts with an MX-verified deliverable mailbox</span>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={Boolean(postFilters.emailOnly)}
                      onChange={e => setPostFilters(p => ({ ...p, emailOnly: e.target.checked }))}
                      className="w-4 h-4 rounded accent-emerald-500 cursor-pointer"
                    />
                  </label>
                </div>
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-white/[0.07] bg-slate-950/80 flex items-center justify-between">
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-2 text-slate-400 hover:text-white text-xs font-semibold cursor-pointer transition"
                >
                  Clear all filters
                </button>

                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="shimmer-btn px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-lg shadow-blue-500/25 transition cursor-pointer"
                >
                  Apply Filters
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
