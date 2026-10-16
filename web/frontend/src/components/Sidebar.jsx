import { useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { prefetchRouteData, clearAllCache } from '../api/client.js'
import BrandLogo from './BrandLogo.jsx'
import {
  LayoutDashboard, Users, KanbanSquare,
  FileText, Mail, Settings, LogOut, Menu, X, Sparkles, Radar, ChevronRight, Search
} from 'lucide-react'

function NavContent({ onClose }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const handleLogout = () => { clearAllCache(); logout(); navigate('/') }

  const links = [
    { to: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard',         sub: 'Overview & KPIs' },
    { to: '/seeker',      icon: Radar,           label: 'Post Hunter',       sub: 'Live AI Radar & Jobs', badge: 'Live' },
    { to: '/tracker',     icon: KanbanSquare,    label: 'Applications',      sub: 'Kanban Pipeline' },
    { to: '/coverletter', icon: FileText,        label: 'AI Documents',      sub: 'Tailor & Letters' },
    { to: '/email',       icon: Mail,            label: 'Outreach History',  sub: 'Sent & Scheduled' },
    ...(user?.role === 'recruiter' || user?.role === 'both'
      ? [{ to: '/recruiter', icon: Users, label: 'Recruiter Mode', sub: 'Source Talent' }]
      : []),
    { to: '/settings',    icon: Settings,        label: 'Settings',          sub: 'SMTP & Preferences' },
  ]

  const userInitial = (user?.name || user?.email || 'U').charAt(0).toUpperCase()

  return (
    <div className="flex flex-col h-full py-6 px-4 bg-[#070B18]/95 backdrop-blur-2xl border-r border-white/[0.07] relative overflow-hidden select-none">
      {/* Subtle top ambient light */}
      <div className="absolute -top-24 -left-24 w-56 h-56 rounded-full bg-blue-600/15 blur-3xl pointer-events-none" />
      <div className="absolute bottom-10 -right-24 w-48 h-48 rounded-full bg-purple-600/10 blur-3xl pointer-events-none" />

      {/* Brand Header */}
      <div className="flex items-center justify-between px-2 mb-5 relative z-10">
        <div
          onClick={() => navigate('/dashboard')}
          className="cursor-pointer group"
        >
          <BrandLogo size="md" />
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="md:hidden text-slate-400 hover:text-white transition p-1.5 rounded-lg hover:bg-white/5"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Global Cmd+K Spotlight Search Trigger */}
      <button
        type="button"
        onClick={() => {
          if (onClose) onClose()
          window.dispatchEvent(new CustomEvent('open-command-palette'))
        }}
        className="relative z-10 mx-1 mb-5 px-3 py-2.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-blue-500/40 flex items-center justify-between text-xs text-slate-400 hover:text-white transition cursor-pointer group"
      >
        <span className="flex items-center gap-2 font-medium">
          <Search size={13} className="text-blue-400 group-hover:scale-110 transition-transform" />
          <span>Quick Command...</span>
        </span>
        <kbd className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-900/90 border border-white/[0.1] text-slate-300">
          ⌘K
        </kbd>
      </button>

      {/* Section Label */}
      <div className="px-3 mb-2.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
        Workspace
      </div>

      {/* Nav Links with Shared Layout Sliding Pill */}
      <nav className="flex flex-col gap-1.5 flex-1 relative z-10">
        {links.map(({ to, icon: Icon, label, badge }) => {
          const isActive = location.pathname === to || (to !== '/dashboard' && location.pathname.startsWith(to))
          return (
            <div key={to}>
              <NavLink
                to={to}
                onClick={onClose}
                onMouseEnter={() => prefetchRouteData(to)}
                onFocus={() => prefetchRouteData(to)}
                className="relative group block rounded-xl focus:outline-none"
              >
                {isActive && (
                  <motion.div
                    layoutId="sidebar-active-pill"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                    className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-600/90 via-indigo-600/85 to-blue-600/80 shadow-lg shadow-blue-600/25 border border-blue-400/30 z-0"
                  />
                )}
                <div
                  className={`relative z-10 flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-xl text-xs transition-colors ${
                    isActive
                      ? 'text-white font-bold'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04] font-medium'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`p-1.5 rounded-lg transition-all duration-200 shrink-0 ${
                      isActive
                        ? 'bg-white/15 text-white scale-105'
                        : 'text-slate-400 group-hover:text-blue-400 group-hover:scale-110 bg-transparent'
                    }`}>
                      <Icon size={15} />
                    </div>
                    <span className="truncate tracking-tight">{label}</span>
                  </div>

                  {badge ? (
                    <span className={`text-[9px] font-extrabold uppercase px-2 py-0.5 rounded-full flex items-center gap-1 border shrink-0 ${
                      isActive
                        ? 'bg-white/20 text-white border-white/30'
                        : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    }`}>
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      {badge}
                    </span>
                  ) : isActive ? (
                    <motion.span
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="shrink-0"
                    >
                      <ChevronRight size={13} className="text-white/70" />
                    </motion.span>
                  ) : null}
                </div>
              </NavLink>
            </div>
          )
        })}
      </nav>

      {/* User Profile Footer */}
      <div className="relative z-10 border-t border-white/[0.06] pt-4 px-0.5 space-y-2">
        <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05]">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-purple-600 flex items-center justify-center font-extrabold text-xs text-white shrink-0 shadow-sm">
            {userInitial}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-bold text-white truncate">{user?.name || 'User'}</p>
            <p className="text-[10px] text-slate-400 truncate mt-0.5">{user?.email || ''}</p>
          </div>
        </div>
        <motion.button
          whileHover={{ x: 2 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleLogout}
          className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-xs font-semibold text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 border border-transparent hover:border-rose-500/20 transition-all w-full cursor-pointer"
        >
          <LogOut size={14} />
          <span>Sign Out</span>
        </motion.button>
      </div>
    </div>
  )
}

export default function Sidebar() {
  const [open, setOpen] = useState(false)

  return (
    <>
      {/* Desktop Fixed Left Sidebar (w-64 = 256px) */}
      <aside className="hidden md:flex flex-col w-64 fixed top-0 left-0 bottom-0 h-full z-20 overflow-y-auto">
        <NavContent />
      </aside>

      {/* Mobile Top Bar */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-30 bg-[#070B18]/90 backdrop-blur-xl border-b border-white/[0.07] px-4 h-14 flex items-center justify-between">
        <BrandLogo size="sm" />
        <button
          onClick={() => setOpen(true)}
          className="text-slate-300 hover:text-white transition p-2 rounded-xl bg-white/5 hover:bg-white/10"
        >
          <Menu size={18} />
        </button>
      </header>

      {/* Mobile Slide-in Drawer */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="md:hidden fixed inset-0 bg-black/75 z-40 backdrop-blur-sm"
              onClick={() => setOpen(false)}
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 26, stiffness: 300 }}
              className="md:hidden fixed top-0 left-0 bottom-0 w-72 z-50 overflow-y-auto"
            >
              <NavContent onClose={() => setOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
