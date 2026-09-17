import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import {
  LayoutDashboard, Search, Users, KanbanSquare,
  FileText, Mail, Settings, LogOut, Menu, X
} from 'lucide-react'

const links = [
  { to:'/dashboard',   icon: LayoutDashboard, label:'Dashboard'     },
  { to:'/seeker',      icon: Search,           label:'Job Search'    },
  { to:'/recruiter',   icon: Users,            label:'Recruiter'     },
  { to:'/tracker',     icon: KanbanSquare,     label:'App Tracker'   },
  { to:'/coverletter', icon: FileText,          label:'Cover Letter'  },
  { to:'/email',       icon: Mail,             label:'Email History' },
  { to:'/settings',    icon: Settings,         label:'Settings'      },
]

function NavContent({ onClose }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const handleLogout = () => { logout(); navigate('/') }

  return (
    <div className="flex flex-col h-full py-6 px-3">
      <div className="flex items-center justify-between px-3 mb-8">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center text-lg font-bold shrink-0">J</div>
          <span className="font-bold text-lg tracking-tight">Job Searcher</span>
        </div>
        {onClose && (
          <button onClick={onClose} className="md:hidden text-slate-400 hover:text-white transition p-1">
            <X size={20}/>
          </button>
        )}
      </div>

      <nav className="flex flex-col gap-1 flex-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors
               ${isActive ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}>
            <Icon size={17}/>
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-slate-700 pt-4 mt-4">
        <div className="px-3 mb-3">
          <p className="text-sm font-semibold truncate">{user?.name || 'User'}</p>
          <p className="text-xs text-slate-400 truncate">{user?.email || ''}</p>
        </div>
        <button onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-red-400 hover:text-red-300 hover:bg-slate-700 transition-colors w-full">
          <LogOut size={17}/>Logout
        </button>
      </div>
    </div>
  )
}

export default function Sidebar() {
  const [open, setOpen] = useState(false)

  return (
    <>
      {/* ── Desktop: fixed left sidebar ─────────────────────────── */}
      <aside className="hidden md:flex flex-col w-60 bg-slate-800 border-r border-slate-700 fixed h-full z-20 overflow-y-auto">
        <NavContent/>
      </aside>

      {/* ── Mobile: top bar with hamburger ──────────────────────── */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-30 bg-slate-800 border-b border-slate-700 px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-sm font-bold">J</div>
          <span className="font-bold">Job Searcher</span>
        </div>
        <button onClick={()=>setOpen(true)}
          className="text-slate-300 hover:text-white transition p-1.5 rounded-lg hover:bg-slate-700">
          <Menu size={22}/>
        </button>
      </header>

      {/* ── Mobile: slide-in drawer ──────────────────────────────── */}
      <AnimatePresence>
        {open && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
              className="md:hidden fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
              onClick={()=>setOpen(false)}/>
            {/* Drawer */}
            <motion.aside
              initial={{x:'-100%'}} animate={{x:0}} exit={{x:'-100%'}}
              transition={{type:'spring',damping:24,stiffness:280}}
              className="md:hidden fixed top-0 left-0 bottom-0 w-72 bg-slate-800 border-r border-slate-700 z-50 overflow-y-auto">
              <NavContent onClose={()=>setOpen(false)}/>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
