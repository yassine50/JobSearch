import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import {
  LayoutDashboard, Search, Users, KanbanSquare,
  FileText, Mail, Settings, LogOut, Menu, X, Sparkles
} from 'lucide-react'

function NavContent({ onClose }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const handleLogout = () => { logout(); navigate('/') }

  const links = [
    { to: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/seeker',      icon: Search,          label: 'Post Hunter & Jobs', badge: 'Live' },
    { to: '/tracker',     icon: KanbanSquare,    label: 'Applications' },
    { to: '/coverletter', icon: FileText,        label: 'AI Documents' },
    { to: '/email',       icon: Mail,            label: 'Outreach History' },
    ...(user?.role === 'recruiter' || user?.role === 'both' ? [{ to: '/recruiter', icon: Users, label: 'Recruiter Mode' }] : []),
    { to: '/settings',    icon: Settings,        label: 'Settings' },
  ]

  const userInitial = (user?.name || user?.email || 'U').charAt(0).toUpperCase()

  return (
    <div className="flex flex-col h-full py-6 px-3 bg-slate-900 border-r border-slate-800">
      {/* Brand Header */}
      <div className="flex items-center justify-between px-3 mb-7">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-base font-black text-white shadow-md shadow-blue-500/20">
            J
          </div>
          <div>
            <span className="font-bold text-base tracking-tight text-white block leading-tight">Job Searcher</span>
            <span className="text-[10px] font-semibold text-blue-400">AI Recruiter Hunter</span>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="md:hidden text-slate-400 hover:text-white transition p-1">
            <X size={20} />
          </button>
        )}
      </div>

      {/* Nav Links */}
      <nav className="flex flex-col gap-1 flex-1">
        {links.map(({ to, icon: Icon, label, badge }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20 font-bold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/80'
              }`
            }
          >
            <div className="flex items-center gap-3 truncate">
              <Icon size={16} />
              <span className="truncate">{label}</span>
            </div>
            {badge && (
              <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded-full bg-blue-400/20 text-blue-300 border border-blue-400/30">
                {badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User Profile Footer */}
      <div className="border-t border-slate-800/80 pt-4 mt-4 px-1">
        <div className="flex items-center gap-3 px-2 mb-3">
          <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-bold text-xs text-blue-300 shrink-0">
            {userInitial}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-bold text-white truncate">{user?.name || 'User'}</p>
            <p className="text-[11px] text-slate-400 truncate">{user?.email || ''}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-red-400 hover:text-red-300 hover:bg-red-950/30 transition-colors w-full cursor-pointer"
        >
          <LogOut size={15} />
          <span>Sign Out</span>
        </button>
      </div>
    </div>
  )
}

export default function Sidebar() {
  const [open, setOpen] = useState(false)

  return (
    <>
      {/* Desktop Fixed Left Sidebar */}
      <aside className="hidden md:flex flex-col w-60 fixed h-full z-20 overflow-y-auto">
        <NavContent />
      </aside>

      {/* Mobile Top Bar */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-30 bg-slate-900 border-b border-slate-800 px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-xs font-bold text-white">J</div>
          <span className="font-bold text-sm text-white">Job Searcher</span>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="text-slate-300 hover:text-white transition p-1.5 rounded-lg hover:bg-slate-800"
        >
          <Menu size={20} />
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
              className="md:hidden fixed inset-0 bg-black/70 z-40 backdrop-blur-xs"
              onClick={() => setOpen(false)}
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
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
