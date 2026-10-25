import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Radar, KanbanSquare, LayoutDashboard, FileText,
  Mail, Settings, Users, Sparkles, ArrowRight, Layers, Bell, Command, X, Sun
} from 'lucide-react'
import { useTheme } from '../context/ThemeContext.jsx'

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const inputRef = useRef(null)

  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(prev => !prev)
      } else if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    const onCustomOpen = () => setOpen(true)

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('open-command-palette', onCustomOpen)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('open-command-palette', onCustomOpen)
    }
  }, [open])

  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 40)
    }
  }, [open])

  // Quick hunts: persist the role so Seeker can pick it up even if it's still lazy-loading,
  // then Seeker switches to the LinkedIn Posts tab and triggers the hunt itself.
  const quickHunt = (role) => {
    if (!role) return
    try { sessionStorage.setItem('pending_quick_hunt', role) } catch {}
    navigate('/seeker')
    setTimeout(() => window.dispatchEvent(new Event('seeker-quick-hunt')), 60)
  }

  const actions = useMemo(() => [
    {
      id: 'nav-seeker',
      category: 'Workspace Navigation',
      label: 'Go to AI Opportunity Hunter (Posts & Jobs)',
      sub: 'Harvest live LinkedIn recruiter posts & global job boards',
      icon: Radar,
      color: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
      run: () => navigate('/seeker'),
    },
    {
      id: 'nav-tracker',
      category: 'Workspace Navigation',
      label: 'Go to CRM Application Pipeline (Kanban)',
      sub: 'Manage 7-stage pipeline, Gmail sync & AI Interview Prep',
      icon: KanbanSquare,
      color: 'text-indigo-400 bg-indigo-500/15 border-indigo-500/30',
      run: () => navigate('/tracker'),
    },
    {
      id: 'nav-dashboard',
      category: 'Workspace Navigation',
      label: 'Go to AI Command Dashboard',
      sub: 'View application funnel KPIs, response rates & saved jobs',
      icon: LayoutDashboard,
      color: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30',
      run: () => navigate('/dashboard'),
    },
    {
      id: 'nav-coverletter',
      category: 'Workspace Navigation',
      label: 'Go to AI Cover Letter & Document Studio',
      sub: 'Generate tailored cover letters aligned with your CV',
      icon: FileText,
      color: 'text-purple-400 bg-purple-500/15 border-purple-500/30',
      run: () => navigate('/coverletter'),
    },
    {
      id: 'nav-email',
      category: 'Workspace Navigation',
      label: 'Go to Outreach History & Calendar Heatmap',
      sub: 'Inspect daily sent volume, bounces & follow-ups',
      icon: Mail,
      color: 'text-cyan-400 bg-cyan-500/15 border-cyan-500/30',
      run: () => navigate('/email'),
    },
    {
      id: 'nav-recruiter',
      category: 'Workspace Navigation',
      label: 'Go to Recruiter Talent Radar',
      sub: 'Source and rank LinkedIn candidates with AI skill recall',
      icon: Users,
      color: 'text-pink-400 bg-pink-500/15 border-pink-500/30',
      run: () => navigate('/recruiter'),
    },
    {
      id: 'nav-settings',
      category: 'Workspace Navigation',
      label: 'Go to Workspace Settings & 1-Click Gmail',
      sub: 'Configure Gmail OAuth, custom templates & bounce blacklist',
      icon: Settings,
      color: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
      run: () => navigate('/settings'),
    },
    {
      id: 'power-theme',
      category: 'Power Tools',
      label: `Switch to ${theme === 'light' ? 'Night Mode (Dark)' : 'Light Mode'}`,
      sub: 'Toggle workspace appearance between Light Mode and Night Mode',
      icon: Sun,
      color: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
      run: () => toggleTheme(),
    },
    {
      id: 'power-personas',
      category: 'Power Tools',
      label: 'Open Multi-CV Personas Vault',
      sub: 'Upload & switch between specialized resumes (Mobile, Full-Stack, AI)',
      icon: Layers,
      color: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30',
      run: () => {
        navigate('/seeker')
        setTimeout(() => window.dispatchEvent(new CustomEvent('open-cv-personas')), 120)
      },
    },
    {
      id: 'power-watchlists',
      category: 'Power Tools',
      label: 'Open Auto-Pilot Saved Watchlists',
      sub: 'Monitor recurring role & country searches automatically',
      icon: Bell,
      color: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
      run: () => {
        navigate('/seeker')
        setTimeout(() => window.dispatchEvent(new CustomEvent('open-watchlists')), 120)
      },
    },
    {
      id: 'hunt-flutter',
      category: 'Quick Live Hunts',
      label: 'Hunt "Flutter Developer" Recruiter Posts',
      sub: 'Launch 8-layer LinkedIn post harvest for Flutter Developer',
      icon: Sparkles,
      color: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
      run: () => {
        quickHunt('Flutter Developer')
      },
    },
    {
      id: 'hunt-react',
      category: 'Quick Live Hunts',
      label: 'Hunt "React / Next.js" Recruiter Posts',
      sub: 'Launch 8-layer LinkedIn post harvest for React / Next.js',
      icon: Sparkles,
      color: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
      run: () => {
        quickHunt('React / Next.js')
      },
    },
    {
      id: 'hunt-python',
      category: 'Quick Live Hunts',
      label: 'Hunt "Python AI Engineer" Recruiter Posts',
      sub: 'Launch 8-layer LinkedIn post harvest for Python AI Engineer',
      icon: Sparkles,
      color: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
      run: () => {
        quickHunt('Python AI Engineer')
      },
    },
  ], [navigate, theme, toggleTheme])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return actions
    return actions.filter(a =>
      a.label.toLowerCase().includes(q) ||
      a.sub.toLowerCase().includes(q) ||
      a.category.toLowerCase().includes(q)
    )
  }, [actions, query])

  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(i => (filtered.length ? (i + 1) % filtered.length : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(i => (filtered.length ? (i - 1 + filtered.length) % filtered.length : 0))
    } else if (e.key === 'Enter' && filtered[selectedIndex]) {
      e.preventDefault()
      filtered[selectedIndex].run()
      setOpen(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/80 backdrop-blur-md z-[9998] flex items-start justify-center pt-[12vh] p-4"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -12 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            onClick={e => e.stopPropagation()}
            className="glass-dropdown rounded-3xl w-full max-w-xl overflow-hidden border border-white/[0.12] shadow-2xl relative"
          >
            <div className="glow-line-top" />

            {/* Search Input Header */}
            <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.08] bg-slate-950/60">
              <div className="w-8 h-8 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0">
                <Search size={15} />
              </div>
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a command, page, or role to hunt (e.g. Kanban, CV Vault, Flutter)..."
                className="flex-1 bg-transparent text-sm font-medium text-white placeholder-slate-500 focus:outline-none"
              />
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-[10px] font-mono font-bold text-slate-400 bg-white/[0.05] border border-white/[0.08] px-2 py-0.5 rounded-md">
                  ESC
                </span>
                <button
                  onClick={() => setOpen(false)}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/[0.06] transition cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Command List */}
            <div className="max-h-[60vh] overflow-y-auto p-2.5 space-y-1">
              {filtered.length === 0 ? (
                <div className="py-10 text-center space-y-2">
                  <p className="text-xs font-bold text-slate-300">No matching commands found</p>
                  <button
                    type="button"
                    onClick={() => {
                      quickHunt(query.trim())
                      setOpen(false)
                    }}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition cursor-pointer"
                  >
                    <Radar size={13} />
                    <span>Hunt &ldquo;{query.trim()}&rdquo; in Opportunity Hunter</span>
                  </button>
                </div>
              ) : (
                filtered.map((item, idx) => {
                  const Icon = item.icon
                  const isSelected = idx === selectedIndex
                  return (
                    <div
                      key={item.id}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      onClick={() => {
                        item.run()
                        setOpen(false)
                      }}
                      className={`flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-2xl cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-blue-600/20 border border-blue-500/40 shadow-sm'
                          : 'border border-transparent hover:bg-white/[0.03]'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${item.color}`}>
                          <Icon size={16} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-white truncate">{item.label}</span>
                            <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-400">
                              {item.category}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 truncate mt-0.5">{item.sub}</p>
                        </div>
                      </div>
                      <ArrowRight size={14} className={`shrink-0 transition-transform ${isSelected ? 'text-blue-400 translate-x-0.5' : 'text-slate-600'}`} />
                    </div>
                  )
                })
              )}
            </div>

            {/* Footer Hints */}
            <div className="px-5 py-2.5 border-t border-white/[0.06] bg-slate-950/70 flex items-center justify-between text-[10px] text-slate-400">
              <div className="flex items-center gap-3">
                <span><strong className="text-slate-200">↑↓</strong> Navigate</span>
                <span><strong className="text-slate-200">↵</strong> Execute</span>
                <span><strong className="text-slate-200">⌘K</strong> Toggle Anywhere</span>
              </div>
              <span className="flex items-center gap-1 text-blue-400 font-semibold">
                <Command size={11} /> AI Spotlight
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
