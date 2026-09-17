
import { createContext, useContext, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, AlertCircle, X } from 'lucide-react'

const ToastCtx = createContext(null)

const ICONS = {
  success: <CheckCircle size={18} className="text-emerald-400 shrink-0"/>,
  error:   <XCircle    size={18} className="text-red-400 shrink-0"/>,
  info:    <AlertCircle size={18} className="text-blue-400 shrink-0"/>,
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const toast = useCallback((msg, type='success', duration=3500) => {
    const id = Date.now()
    setToasts(t => [...t, { id, msg, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
  }, [])

  const dismiss = (id) => setToasts(t => t.filter(x => x.id !== id))

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence>
          {toasts.map(t => (
            <motion.div key={t.id}
              initial={{ opacity:0, y:24, scale:0.95 }}
              animate={{ opacity:1, y:0,  scale:1    }}
              exit={{    opacity:0, y:8,  scale:0.95  }}
              transition={{ type:'spring', damping:20, stiffness:300 }}
              className="pointer-events-auto flex items-start gap-3 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 shadow-2xl min-w-[280px] max-w-sm">
              {ICONS[t.type]}
              <span className="text-sm text-slate-200 flex-1">{t.msg}</span>
              <button onClick={()=>dismiss(t.id)} className="text-slate-500 hover:text-white transition shrink-0">
                <X size={15}/>
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
