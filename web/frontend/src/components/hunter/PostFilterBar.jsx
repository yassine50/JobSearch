import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Columns, LayoutGrid, SlidersHorizontal, ShieldCheck, Clock,
  Zap, ChevronDown, Check, X, RotateCcw
} from 'lucide-react'

export const DEFAULT_POST_FILTERS = {
  sortBy: 'relevant', // 'relevant' | 'recent'
  datePosted: 'all',  // '24h', 'week', 'month', 'all'
  emailOnly: false
}

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

  // Count active filters (excluding defaults)
  const activeCount = [
    postFilters.sortBy !== 'relevant',
    postFilters.datePosted !== 'all',
    Boolean(postFilters.emailOnly)
  ].filter(Boolean).length

  const handleReset = () => {
    setPostFilters(DEFAULT_POST_FILTERS)
  }

  return (
    <div className="space-y-2 py-2 border-b border-slate-800">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {/* Left: Clean Filter Controls & Quick Chips */}
        <div className="flex items-center gap-2 flex-wrap text-xs">
          {/* Main "Post Filters" Button */}
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 hover:border-slate-600 text-slate-200 font-bold flex items-center gap-1.5 transition cursor-pointer shadow-xs"
          >
            <SlidersHorizontal size={13} className="text-blue-400" />
            <span>Post Filters</span>
            {activeCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold">
                {activeCount}
              </span>
            )}
          </button>

          {/* Quick Date Dropdown */}
          <select
            value={postFilters.datePosted}
            onChange={e => {
              const next = { ...postFilters, datePosted: e.target.value }
              setPostFilters(next)
              if (onApplyAndSearch) onApplyAndSearch(next)
            }}
            className="bg-slate-900 border border-slate-750 rounded-xl px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500 cursor-pointer"
          >
            <option value="all">Date: Any time</option>
            <option value="24h">Past 24 hours</option>
            <option value="week">Past week</option>
            <option value="month">Past month</option>
          </select>

          {/* Quick Email Filter Chip */}
          <button
            type="button"
            onClick={() => {
              setPostFilters(p => ({ ...p, emailOnly: !p.emailOnly }))
            }}
            className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer flex items-center gap-1.5 ${
              postFilters.emailOnly
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-600 shadow-xs'
                : 'bg-slate-900 text-slate-400 border-slate-750 hover:text-white'
            }`}
          >
            <ShieldCheck size={12} className={postFilters.emailOnly ? 'text-emerald-400' : 'text-slate-500'} />
            <span>With Recruiter Email ({emailCount})</span>
          </button>

          {activeCount > 0 && (
            <button
              type="button"
              onClick={handleReset}
              className="text-[11px] text-slate-500 hover:text-white flex items-center gap-1 transition cursor-pointer px-1"
              title="Clear all filters"
            >
              <RotateCcw size={10} />
              <span>Clear</span>
            </button>
          )}
        </div>

        {/* Right: Batch Apply, Sort & View Mode */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Bulk Auto-Apply Button */}
          {emailCount > 0 && onBatchApply && (
            <button
              type="button"
              onClick={onBatchApply}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-bold text-xs shadow-md shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer shrink-0 border border-blue-400/30"
              title="Dispatch tailored applications to all verified recruiters"
            >
              <Zap size={13} className="text-amber-300" />
              <span>Auto-Apply to All ({emailCount})</span>
            </button>
          )}

          {/* Sort Dropdown: Most relevant / Most recent */}
          <div className="flex items-center gap-1 text-xs">
            <span className="text-slate-500 text-[11px] hidden sm:inline">Sort:</span>
            <select
              value={postFilters.sortBy}
              onChange={e => {
                const next = { ...postFilters, sortBy: e.target.value }
                setPostFilters(next)
                if (onApplyAndSearch) onApplyAndSearch(next)
              }}
              className="bg-slate-900 border border-slate-750 rounded-xl px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              <option value="relevant">Most relevant</option>
              <option value="recent">Most recent</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center p-0.5 rounded-xl bg-slate-900 border border-slate-750">
            <button
              type="button"
              onClick={() => setViewMode('split')}
              className={`p-1.5 rounded-lg transition ${
                viewMode === 'split' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-400 hover:text-white'
              }`}
              title="Split Workbench View"
            >
              <Columns size={15} />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`p-1.5 rounded-lg transition ${
                viewMode === 'cards' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-400 hover:text-white'
              }`}
              title="Multi-column Cards Grid"
            >
              <LayoutGrid size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Streamlined LinkedIn Post Filters Modal */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 15 }}
            className="w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
              <div className="flex items-center gap-2.5">
                <SlidersHorizontal size={16} className="text-blue-400" />
                <h3 className="font-bold text-white text-base">LinkedIn Post Filters</h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleReset}
                  className="text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-slate-800 transition flex items-center gap-1 cursor-pointer"
                >
                  <RotateCcw size={12} />
                  <span>Reset</span>
                </button>
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6 overflow-y-auto flex-1 text-xs">
              {/* 1. Sort by */}
              <div className="space-y-2">
                <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Sort by</h4>
                <div className="flex items-center gap-2">
                  {[
                    { id: 'relevant', label: 'Most relevant' },
                    { id: 'recent', label: 'Most recent' }
                  ].map(opt => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setPostFilters(p => ({ ...p, sortBy: opt.id }))}
                      className={`px-3.5 py-2 rounded-xl font-medium border transition cursor-pointer ${
                        postFilters.sortBy === opt.id
                          ? 'bg-blue-600 text-white border-blue-500 shadow-xs'
                          : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* 2. Date Posted */}
              <div className="space-y-2 border-t border-slate-800/80 pt-4">
                <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Date Posted</h4>
                <div className="flex items-center gap-2 flex-wrap">
                  {[
                    { id: 'all', label: 'Any time' },
                    { id: '24h', label: 'Past 24 hours' },
                    { id: 'week', label: 'Past week' },
                    { id: 'month', label: 'Past month' }
                  ].map(opt => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setPostFilters(p => ({ ...p, datePosted: opt.id }))}
                      className={`px-3.5 py-2 rounded-xl font-medium border transition cursor-pointer ${
                        postFilters.datePosted === opt.id
                          ? 'bg-blue-600 text-white border-blue-500 shadow-xs'
                          : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* 3. With Verified Recruiter Email Toggle */}
              <div className="space-y-2 border-t border-slate-800/80 pt-4">
                <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Recruiter Contact</h4>
                <label className="flex items-center justify-between p-3.5 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer select-none hover:border-slate-700">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={16} className="text-emerald-400" />
                    <div>
                      <span className="font-semibold text-white block">Verified Corporate Recruiter Email</span>
                      <span className="text-[11px] text-slate-400">Only show posts with authoritative MX-verified recruiter email</span>
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
            <div className="p-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
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
                className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-500/25 transition cursor-pointer"
              >
                Apply Filters
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}
