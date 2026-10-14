import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Globe, Search, Check, X } from 'lucide-react'
import { ALL_COUNTRY_SUGGESTIONS, REGION_CATEGORIES } from '../../constants/searchConstants.js'

export default function LocationPickerModal({
  isOpen,
  onClose,
  selectedLocations = ['Worldwide'],
  onToggleLocation,
  onApplyRegionBundle
}) {
  const [searchTerm, setSearchTerm] = useState('')
  const [activeRegion, setActiveRegion] = useState('all')
  const [customInput, setCustomInput] = useState('')

  const filteredList = useMemo(() => {
    return ALL_COUNTRY_SUGGESTIONS.filter(item => {
      const matchSearch = item.label.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          item.value.toLowerCase().includes(searchTerm.toLowerCase())
      if (!matchSearch) return false
      if (activeRegion === 'all') return true
      if (activeRegion === 'popular') return Boolean(item.popular)
      return item.region === activeRegion
    })
  }, [searchTerm, activeRegion])

  if (!isOpen) return null

  const handleAddCustom = (e) => {
    e.preventDefault()
    const trimmed = customInput.trim()
    if (!trimmed) return
    onToggleLocation(trimmed)
    setCustomInput('')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className="w-full max-w-2xl bg-slate-900 border border-slate-750 rounded-2xl shadow-2xl flex flex-col max-h-[88vh] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
              <Globe size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Target Countries & Locations</h3>
              <p className="text-xs text-slate-400">Select regions to harvest recruiter posts across</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Search & Region Filter Bar */}
        <div className="p-4 border-b border-slate-800/80 bg-slate-950/40 space-y-3">
          <div className="relative">
            <input
              type="text"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search 45+ countries, states or regions..."
              className="w-full bg-slate-900 border border-slate-750 rounded-xl pl-9 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
            {REGION_CATEGORIES.map(r => (
              <button
                key={r.id}
                type="button"
                onClick={() => setActiveRegion(r.id)}
                className={`px-2.5 py-1 rounded-lg font-medium transition shrink-0 ${
                  activeRegion === r.id
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-750'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {/* Country Grid */}
        <div className="p-6 overflow-y-auto flex-1 grid grid-cols-2 sm:grid-cols-3 gap-2">
          {filteredList.map(item => {
            const isSelected = selectedLocations.some(l => l.toLowerCase() === item.value.toLowerCase())
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => onToggleLocation(item.value)}
                className={`p-2.5 rounded-xl border text-left transition flex items-center justify-between gap-2 text-xs font-medium cursor-pointer ${
                  isSelected
                    ? 'bg-blue-600/15 border-blue-500/80 text-blue-300 shadow-xs'
                    : 'bg-slate-800/60 border-slate-750 hover:bg-slate-800 text-slate-300 hover:border-slate-650'
                }`}
              >
                <span className="flex items-center gap-2 truncate">
                  <span className="text-base">{item.icon}</span>
                  <span className="truncate">{item.label}</span>
                </span>
                {isSelected && <Check size={14} className="text-blue-400 shrink-0 stroke-[3]" />}
              </button>
            )
          })}
        </div>

        {/* Custom City Adder & Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between gap-3 flex-wrap">
          <form onSubmit={handleAddCustom} className="flex items-center gap-2 flex-1 max-w-sm">
            <input
              type="text"
              value={customInput}
              onChange={e => setCustomInput(e.target.value)}
              placeholder="Add custom city (e.g. Austin, Casablanca)..."
              className="bg-slate-900 border border-slate-750 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 flex-1"
            />
            <button
              type="submit"
              disabled={!customInput.trim()}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-semibold transition disabled:opacity-40"
            >
              Add
            </button>
          </form>

          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-500/25 transition cursor-pointer"
          >
            Apply Selection ({selectedLocations.length})
          </button>
        </div>
      </motion.div>
    </div>
  )
}
