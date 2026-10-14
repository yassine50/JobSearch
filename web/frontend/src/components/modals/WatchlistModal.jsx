import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Bell, Plus, Radar, Trash2, Sparkles, Globe, Loader2, Play, ArrowUpRight
} from 'lucide-react'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

const DEFAULT_LOCATIONS = ['Worldwide']

export default function WatchlistModal({
  isOpen,
  onClose,
  currentRole = 'Flutter Developer',
  currentLocations = DEFAULT_LOCATIONS,
  onLoadWatchlist
}) {
  const toast = useToast()
  const [watchlists, setWatchlists] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [runningId, setRunningId] = useState(null)

  const [role, setRole] = useState(currentRole || 'Flutter Developer')
  const [locationsText, setLocationsText] = useState((currentLocations || DEFAULT_LOCATIONS).join(', '))
  const [minScore, setMinScore] = useState(65)

  const loadWatchlists = async () => {
    setLoading(true)
    try {
      const { data } = await client.get('/power/watchlists')
      setWatchlists(data.watchlists || [])
    } catch {
      toast('Failed to load watchlists', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      setRole(currentRole || 'Flutter Developer')
      setLocationsText((currentLocations || DEFAULT_LOCATIONS).join(', '))
      loadWatchlists()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!role.trim()) return
    setCreating(true)
    const locs = locationsText.split(',').map(s => s.trim()).filter(Boolean)
    try {
      await client.post('/power/watchlists', {
        role: role.trim(),
        locations: locs.length ? locs : ['Worldwide'],
        min_match_score: Number(minScore) || 65,
        auto_pilot: true,
      })
      toast(`Saved "${role.trim()}" to Auto-Pilot Watchlists!`, 'success')
      await loadWatchlists()
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to save watchlist', 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleRunNow = async (wl) => {
    setRunningId(wl.id)
    try {
      const { data } = await client.post(`/power/watchlists/${wl.id}/run`)
      toast(`Found ${data.new_matches_count || 0} high-match posts for ${wl.role}!`, 'success')
      await loadWatchlists()
    } catch {
      toast('Watchlist scan failed', 'error')
    } finally {
      setRunningId(null)
    }
  }

  const handleDelete = async (id) => {
    try {
      await client.delete(`/power/watchlists/${id}`)
      setWatchlists(prev => prev.filter(w => w.id !== id))
      toast('Watchlist removed', 'info')
    } catch {
      toast('Failed to delete watchlist', 'error')
    }
  }

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          onClick={e => e.stopPropagation()}
          className="glass-dropdown rounded-3xl w-full max-w-2xl max-h-[88vh] overflow-hidden flex flex-col border border-white/[0.1] shadow-2xl relative"
        >
          <div className="glow-line-top" />

          {/* Header */}
          <div className="p-6 border-b border-white/[0.08] flex items-center justify-between gap-4 bg-slate-950/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                <Bell size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-black text-lg text-white tracking-tight">Auto-Pilot Saved Watchlists</h3>
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                    Live Radar
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Save target roles &amp; regions to monitor verified recruiter posts and launch instant 1-click scans.
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 hover:text-white transition cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 overflow-y-auto space-y-5 flex-1">
            {/* Create New Watchlist Form */}
            <form onSubmit={handleCreate} className="glass-card rounded-2xl p-4 border border-blue-500/25 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-blue-300 flex items-center gap-1.5">
                  <Sparkles size={13} className="text-amber-400" />
                  <span>Create New Auto-Pilot Watchlist</span>
                </span>
                <span className="text-[10px] text-slate-400">Min Match: <strong className="text-emerald-400">{minScore}%</strong></span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-12 gap-2.5">
                <input
                  type="text"
                  value={role}
                  onChange={e => setRole(e.target.value)}
                  placeholder="Role (e.g. Flutter Developer)"
                  className="sm:col-span-5 glass-input rounded-xl px-3.5 py-2 text-xs"
                />
                <input
                  type="text"
                  value={locationsText}
                  onChange={e => setLocationsText(e.target.value)}
                  placeholder="Locations (e.g. Worldwide, France)"
                  className="sm:col-span-4 glass-input rounded-xl px-3.5 py-2 text-xs"
                />
                <button
                  type="submit"
                  disabled={creating || !role.trim()}
                  className="sm:col-span-3 shimmer-btn px-3.5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-extrabold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={14} />}
                  <span>Save Radar</span>
                </button>
              </div>
            </form>

            {/* Watchlists List */}
            {loading ? (
              <div className="py-10 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
                <Loader2 size={16} className="animate-spin text-blue-400" />
                <span>Loading saved watchlists...</span>
              </div>
            ) : watchlists.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs space-y-2">
                <Radar size={28} className="mx-auto text-slate-600" />
                <p className="font-bold text-slate-300">No saved watchlists yet</p>
                <p>Save your current search above to monitor new high-match recruiter publications.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {watchlists.map(wl => (
                  <div
                    key={wl.id}
                    className="glass-card rounded-2xl p-4 border border-white/[0.08] hover:border-blue-500/35 transition-all space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-extrabold text-sm text-white">{wl.role}</span>
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-blue-500/15 text-blue-300 border border-blue-500/30">
                            <Globe size={10} /> {(wl.locations || ['Worldwide']).join(', ')}
                          </span>
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-extrabold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                            {wl.new_matches_count || 0} Verified Matches
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400">
                          Min ATS Score: {wl.min_match_score}% · {wl.last_run_at ? `Last scanned ${new Date(wl.last_run_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Ready to scan'}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleRunNow(wl)}
                          disabled={runningId === wl.id}
                          className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.09] border border-white/[0.08] text-xs font-bold text-slate-200 flex items-center gap-1.5 transition cursor-pointer"
                        >
                          {runningId === wl.id ? <Loader2 size={12} className="animate-spin text-blue-400" /> : <Play size={12} className="text-emerald-400" />}
                          <span>Scan Index</span>
                        </button>
                        {onLoadWatchlist && (
                          <button
                            type="button"
                            onClick={() => {
                              onLoadWatchlist(wl.role, wl.locations || ['Worldwide'])
                              onClose()
                            }}
                            className="px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center gap-1 transition cursor-pointer shadow-sm"
                          >
                            <span>Hunt Live</span>
                            <ArrowUpRight size={13} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleDelete(wl.id)}
                          className="p-1.5 rounded-xl bg-white/[0.03] hover:bg-rose-500/15 border border-white/[0.06] hover:border-rose-500/30 text-slate-400 hover:text-rose-400 transition cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
