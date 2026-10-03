import { createContext, useContext, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, AlertCircle, X } from 'lucide-react'

const ToastCtx = createContext(null)

const ICONS = {
  success: <CheckCircle size={18} className="text-emerald-400 shrink-0" />,
  error: <XCircle size={18} className="text-red-400 shrink-0" />,
  info: <AlertCircle size={18} className="text-blue-400 shrink-0" />
}

function sanitizeToastMessage(msg) {
  if (msg == null) return ''
  if (typeof msg === 'string') return msg
  if (typeof msg === 'number' || typeof msg === 'boolean') return String(msg)
  if (Array.isArray(msg)) {
    return msg.map(item => {
      if (typeof item === 'object' && item !== null) {
        if (item.msg) {
          const locStr = Array.isArray(item.loc) ? item.loc.filter(l => l !== 'body').join('.') : ''
          return locStr ? `${locStr}: ${item.msg}` : item.msg
        }
        return item.message || item.detail || JSON.stringify(item)
      }
      return String(item)
    }).join('; ')
  }
  if (typeof msg === 'object') {
    if (msg.detail) return sanitizeToastMessage(msg.detail)
    if (msg.message) return String(msg.message)
    if (msg.msg) return String(msg.msg)
    try {
      return JSON.stringify(msg)
    } catch {
      return 'An unexpected error occurred'
    }
  }
  return String(msg)
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const toast = useCallback((msg, type = 'success', duration = 3500) => {
    const id = Date.now() + Math.random()
    const cleanMsg = sanitizeToastMessage(msg)
    setToasts(t => [...t, { id, msg: cleanMsg, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
  }, [])

  const dismiss = (id) => setToasts(t => t.filter(x => x.id !== id))

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence>
          {toasts.map(t => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 24, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.95 }}
              transition={{ type: 'spring', damping: 20, stiffness: 300 }}
              className="pointer-events-auto flex items-start gap-3 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 shadow-2xl min-w-[280px] max-w-sm"
            >
              {ICONS[t.type] || ICONS.info}
              <span className="text-sm text-slate-200 flex-1 break-words leading-snug">
                {String(t.msg || '')}
              </span>
              <button
                onClick={() => dismiss(t.id)}
                className="text-slate-500 hover:text-white transition shrink-0 cursor-pointer"
              >
                <X size={15} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
