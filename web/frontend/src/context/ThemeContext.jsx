import { createContext, useContext, useState, useEffect } from 'react'
import { Sun, Moon } from 'lucide-react'

const THEME_STORAGE_KEY = 'cvtomatch_theme_v2'

const ThemeContext = createContext({
  theme: 'light',
  setTheme: () => {},
  toggleTheme: () => {},
})

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY)
      if (saved === 'light' || saved === 'dark') return saved
    } catch {}
    return 'light'
  })

  useEffect(() => {
    const isLight = theme === 'light'
    document.documentElement.classList.toggle('light-mode', isLight)
    document.body.classList.toggle('light-mode', isLight)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {}
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}

export function ThemeToggle({ compact = false, className = '' }) {
  const { theme, toggleTheme } = useTheme()
  const isLight = theme === 'light'

  if (compact) {
    return (
      <button
        type="button"
        onClick={toggleTheme}
        title={isLight ? 'Switch to Night Mode' : 'Switch to Light Mode'}
        aria-label={isLight ? 'Switch to Night Mode' : 'Switch to Light Mode'}
        className={`p-2 rounded-xl border transition cursor-pointer flex items-center justify-center ${
          isLight
            ? 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-amber-600'
            : 'bg-white/[0.04] hover:bg-white/[0.1] border-white/[0.08] text-amber-300'
        } ${className}`}
      >
        {isLight ? <Moon size={15} className="text-indigo-600" /> : <Sun size={15} className="text-amber-300" />}
      </button>
    )
  }

  return (
    <div
      role="group"
      aria-label="Theme Mode Selector"
      className={`inline-flex items-center p-1 rounded-xl border transition select-none ${
        isLight
          ? 'bg-slate-200/90 border-slate-300/90'
          : 'bg-slate-950/90 border-white/[0.09]'
      } ${className}`}
    >
      <button
        type="button"
        onClick={() => !isLight && toggleTheme()}
        title="Light Mode"
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-extrabold transition cursor-pointer ${
          isLight
            ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-sm'
            : 'text-slate-400 hover:text-white'
        }`}
      >
        <Sun size={12} />
        <span>Light</span>
      </button>
      <button
        type="button"
        onClick={() => isLight && toggleTheme()}
        title="Night Mode (Dark)"
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-extrabold transition cursor-pointer ${
          !isLight
            ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-sm'
            : 'text-slate-600 hover:text-slate-900'
        }`}
      >
        <Moon size={12} />
        <span>Night</span>
      </button>
    </div>
  )
}
