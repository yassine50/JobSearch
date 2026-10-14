import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  X, RotateCcw, Check, SlidersHorizontal, ShieldCheck
} from 'lucide-react'
import {
  COMPANY_PRESETS,
  SECTOR_PRESETS,
  FUNCTION_PRESETS,
  TITLE_PRESETS,
  COMMITMENT_PRESETS,
  DEFAULT_FILTERS
} from '../../constants/searchConstants.js'

export default function JobFilterDrawer({
  isOpen,
  onClose,
  filters,
  onApplyFilters,
  onResetFilters
}) {
  const [localFilters, setLocalFilters] = useState(filters || DEFAULT_FILTERS)
  const [customCompany, setCustomCompany] = useState('')
  const [customSector, setCustomSector] = useState('')
  const [customFunction, setCustomFunction] = useState('')
  const [customTitle, setCustomTitle] = useState('')

  if (!isOpen) return null

  const toggleArrayItem = (key, item) => {
    setLocalFilters(prev => {
      const list = prev[key] || []
      const exists = list.includes(item)
      return {
        ...prev,
        [key]: exists ? list.filter(x => x !== item) : [...list, item]
      }
    })
  }

  const handleAddCustom = (key, value, setter) => {
    if (!value.trim()) return
    const val = value.trim()
    setLocalFilters(prev => {
      const list = prev[key] || []
      return {
        ...prev,
        [key]: list.includes(val) ? list : [...list, val]
      }
    })
    setter('')
  }

  const handleApply = () => {
    onApplyFilters(localFilters)
    onClose()
  }

  const handleReset = () => {
    setLocalFilters(DEFAULT_FILTERS)
    if (onResetFilters) onResetFilters()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 15 }}
        className="w-full max-w-3xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 flex items-center justify-center">
              <SlidersHorizontal size={16} />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">All Filters (Job Boards)</h3>
              <p className="text-xs text-slate-400">Precise multi-criteria search filters (LinkedIn style)</p>
            </div>
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
              onClick={onClose}
              className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition cursor-pointer"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Drawer Body */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1 text-xs">
          {/* 1. Sort by */}
          <div className="space-y-2.5">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Sort by</h4>
            <div className="flex items-center gap-2">
              {[
                { id: 'relevant', label: 'Most relevant' },
                { id: 'recent', label: 'Most recent' }
              ].map(opt => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setLocalFilters(prev => ({ ...prev, sortBy: opt.id }))}
                  className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer ${
                    localFilters.sortBy === opt.id
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
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Date Posted</h4>
            <div className="flex items-center gap-2 flex-wrap">
              {[
                { id: 'all', label: 'Any time' },
                { id: 'month', label: 'Past month' },
                { id: 'week', label: 'Past week' },
                { id: '24h', label: 'Past 24 hours' }
              ].map(opt => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setLocalFilters(prev => ({ ...prev, datePosted: opt.id }))}
                  className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer ${
                    localFilters.datePosted === opt.id
                      ? 'bg-blue-600 text-white border-blue-500 shadow-xs'
                      : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* 3. Experience Level */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Experience Level</h4>
            <div className="flex items-center gap-2 flex-wrap">
              {[
                { id: 'internship', label: 'Internship' },
                { id: 'entry', label: 'Entry level' },
                { id: 'associate', label: 'Associate' },
                { id: 'senior', label: 'Mid-Senior level' },
                { id: 'director', label: 'Director' },
                { id: 'executive', label: 'Executive' }
              ].map(opt => {
                const active = (localFilters.experience || []).includes(opt.id)
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => toggleArrayItem('experience', opt.id)}
                    className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer flex items-center gap-1.5 ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active && <Check size={12} />}
                    <span>{opt.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 4. Job Type */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Job Type</h4>
            <div className="flex items-center gap-2 flex-wrap">
              {[
                { id: 'fulltime', label: 'Full-time' },
                { id: 'contract', label: 'Contract / Freelance' },
                { id: 'internship', label: 'Internship' },
                { id: 'parttime', label: 'Part-time' }
              ].map(opt => {
                const active = (localFilters.jobTypes || []).includes(opt.id)
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => toggleArrayItem('jobTypes', opt.id)}
                    className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer flex items-center gap-1.5 ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active && <Check size={12} />}
                    <span>{opt.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 5. On-site / Remote */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">On-site / Remote</h4>
            <div className="flex items-center gap-2 flex-wrap">
              {[
                { id: 'remote', label: 'Remote' },
                { id: 'onsite', label: 'On-site' },
                { id: 'hybrid', label: 'Hybrid' }
              ].map(opt => {
                const active = (localFilters.workplaceType || []).includes(opt.id)
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => toggleArrayItem('workplaceType', opt.id)}
                    className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer flex items-center gap-1.5 ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active && <Check size={12} />}
                    <span>{opt.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 6. Special Features: Easy Apply, Verified Email, Under 10 applicants, In your network */}
          <div className="space-y-3 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Special Features</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <label className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer select-none hover:border-slate-700">
                <span className="font-medium text-slate-300">Easy Apply</span>
                <input
                  type="checkbox"
                  checked={Boolean(localFilters.easyApply)}
                  onChange={e => setLocalFilters(p => ({ ...p, easyApply: e.target.checked }))}
                  className="w-4 h-4 rounded accent-blue-600"
                />
              </label>

              <label className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer select-none hover:border-slate-700">
                <div className="flex items-center gap-1.5">
                  <ShieldCheck size={14} className="text-emerald-400" />
                  <span className="font-medium text-slate-300">Verified Recruiter Info (Direct Email)</span>
                </div>
                <input
                  type="checkbox"
                  checked={Boolean(localFilters.verifiedInfoOnly)}
                  onChange={e => setLocalFilters(p => ({ ...p, verifiedInfoOnly: e.target.checked }))}
                  className="w-4 h-4 rounded accent-emerald-500"
                />
              </label>

              <label className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer select-none hover:border-slate-700">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">🌐</span>
                  <span className="font-medium text-slate-300">International Candidates (LMIA / Job Bank)</span>
                </div>
                <input
                  type="checkbox"
                  checked={Boolean(localFilters.internationalOnly)}
                  onChange={e => setLocalFilters(p => ({ ...p, internationalOnly: e.target.checked }))}
                  className="w-4 h-4 rounded accent-amber-500"
                />
              </label>

              <label className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer select-none hover:border-slate-700">
                <span className="font-medium text-slate-300">Under 10 applicants</span>
                <input
                  type="checkbox"
                  checked={Boolean(localFilters.under10Applicants)}
                  onChange={e => setLocalFilters(p => ({ ...p, under10Applicants: e.target.checked }))}
                  className="w-4 h-4 rounded accent-blue-600"
                />
              </label>

              <label className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer select-none hover:border-slate-700">
                <span className="font-medium text-slate-300">In your network</span>
                <input
                  type="checkbox"
                  checked={Boolean(localFilters.inYourNetwork)}
                  onChange={e => setLocalFilters(p => ({ ...p, inYourNetwork: e.target.checked }))}
                  className="w-4 h-4 rounded accent-blue-600"
                />
              </label>
            </div>
          </div>

          {/* 7. Company */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <div className="flex items-center justify-between">
              <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Company</h4>
              <span className="text-[10px] text-slate-500">Select or add</span>
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              {COMPANY_PRESETS.map(c => {
                const active = (localFilters.companies || []).includes(c)
                return (
                  <button
                    key={c}
                    type="button"
                    onClick={() => toggleArrayItem('companies', c)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition cursor-pointer ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active ? `✓ ${c}` : c}
                  </button>
                )
              })}
            </div>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={customCompany}
                onChange={e => setCustomCompany(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddCustom('companies', customCompany, setCustomCompany))}
                placeholder="Add a company (e.g. Google, Spotify)..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={() => handleAddCustom('companies', customCompany, setCustomCompany)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-xl font-medium text-xs cursor-pointer"
              >
                Add
              </button>
            </div>
          </div>

          {/* 8. Industry / Sector */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Industry / Sector</h4>
            <div className="flex items-center gap-1.5 flex-wrap">
              {SECTOR_PRESETS.map(s => {
                const active = (localFilters.sectors || []).includes(s)
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleArrayItem('sectors', s)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition cursor-pointer ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active ? `✓ ${s}` : s}
                  </button>
                )
              })}
            </div>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={customSector}
                onChange={e => setCustomSector(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddCustom('sectors', customSector, setCustomSector))}
                placeholder="Add an industry..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={() => handleAddCustom('sectors', customSector, setCustomSector)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-xl font-medium text-xs cursor-pointer"
              >
                Add
              </button>
            </div>
          </div>

          {/* 9. Job Function */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Job Function</h4>
            <div className="flex items-center gap-1.5 flex-wrap">
              {FUNCTION_PRESETS.map(f => {
                const active = (localFilters.functions || []).includes(f)
                return (
                  <button
                    key={f}
                    type="button"
                    onClick={() => toggleArrayItem('functions', f)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition cursor-pointer ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active ? `✓ ${f}` : f}
                  </button>
                )
              })}
            </div>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={customFunction}
                onChange={e => setCustomFunction(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddCustom('functions', customFunction, setCustomFunction))}
                placeholder="Add a job function..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={() => handleAddCustom('functions', customFunction, setCustomFunction)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-xl font-medium text-xs cursor-pointer"
              >
                Add
              </button>
            </div>
          </div>

          {/* 10. Job Title */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Job Title</h4>
            <div className="flex items-center gap-1.5 flex-wrap">
              {TITLE_PRESETS.map(t => {
                const active = (localFilters.jobTitles || []).includes(t)
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleArrayItem('jobTitles', t)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition cursor-pointer ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active ? `✓ ${t}` : t}
                  </button>
                )
              })}
            </div>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={customTitle}
                onChange={e => setCustomTitle(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddCustom('jobTitles', customTitle, setCustomTitle))}
                placeholder="Add a custom job title..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={() => handleAddCustom('jobTitles', customTitle, setCustomTitle)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-xl font-medium text-xs cursor-pointer"
              >
                Add
              </button>
            </div>
          </div>

          {/* 11. Commitments */}
          <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
            <h4 className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">Commitments</h4>
            <div className="flex items-center gap-1.5 flex-wrap">
              {COMMITMENT_PRESETS.map(comm => {
                const active = (localFilters.commitments || []).includes(comm)
                return (
                  <button
                    key={comm}
                    type="button"
                    onClick={() => toggleArrayItem('commitments', comm)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition cursor-pointer ${
                      active
                        ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {active ? `✓ ${comm}` : comm}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Drawer Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
          <button
            type="button"
            onClick={handleReset}
            className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-semibold cursor-pointer transition"
          >
            Clear all filters
          </button>

          <button
            type="button"
            onClick={handleApply}
            className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-500/25 transition cursor-pointer"
          >
            Apply Filters & Search
          </button>
        </div>
      </motion.div>
    </div>
  )
}
