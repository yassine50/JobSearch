
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { LayoutDashboard, Search, Users, Bookmark, LogOut, KanbanSquare, FileText, Mail, Settings } from 'lucide-react'

const links = [
  { to: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard'     },
  { to: '/seeker',      icon: Search,           label: 'Job Search'    },
  { to: '/recruiter',   icon: Users,            label: 'Recruiter'     },
  { to: '/tracker',     icon: KanbanSquare,     label: 'App Tracker'   },
  { to: '/coverletter', icon: FileText,          label: 'Cover Letter'  },
  { to: '/email',       icon: Mail,             label: 'Email History' },
  { to: '/settings',    icon: Settings,         label: 'Settings'      },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const handleLogout = () => { logout(); navigate('/') }

  return (
    <aside className="w-60 bg-slate-800 border-r border-slate-700 flex flex-col py-6 px-3 fixed h-full z-10 overflow-y-auto">
      <div className="flex items-center gap-2.5 px-3 mb-8">
        <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center text-lg font-bold">J</div>
        <span className="font-bold text-lg tracking-tight">Job Searcher</span>
      </div>
      <nav className="flex flex-col gap-1 flex-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
               ${isActive ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}>
            <Icon size={17} />
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
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-red-400 hover:text-red-300 hover:bg-slate-700 transition-colors w-full">
          <LogOut size={17} />Logout
        </button>
      </div>
    </aside>
  )
}
