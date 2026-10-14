import { createContext, useContext, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, AlertCircle, X } from 'lucide-react'

const ToastCtx = createContext(null)

const ICONS = {
  success: <CheckCircle size={18} className="text-emerald-400 shrink-0 drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]" />,
  error: <XCircle size={18} className="text-rose-400 shrink-0 drop-shadow-[0_0_8px_rgba(244,63,94,0.5)]" />,
  info: <AlertCircle size={18} className="text-blue-400 shrink-0 drop-shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
}

const ACCENTS = {
  success: 'border-emerald-500/30 shadow-[0_12px_32px_-8px_rgba(16,185,129,0.25)]',
  error: 'border-rose-500/30 shadow-[0_12px_32px_-8px_rgba(244,63,94,0.25)]',
  info: 'border-blue-500/30 shadow-[0_12px_32px_-8px_rgba(59,130,246,0.25)]'
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
    setToasts(prev => {
      const filtered = prev.filter(x => x.msg !== cleanMsg)
      return [...filtered.slice(-3), { id, msg: cleanMsg, type }]
    })
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
  }, [])

  const dismiss = (id) => setToasts(t => t.filter(x => x.id !== id))

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-2.5 pointer-events-none">
        <AnimatePresence>
          {toasts.map(t => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 24, scale: 0.94 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.94 }}
              transition={{ type: 'spring', damping: 22, stiffness: 340 }}
              className={`pointer-events-auto flex items-start gap-3 glass-dropdown rounded-2xl px-4 py-3.5 border min-w-[290px] max-w-sm ${ACCENTS[t.type] || ACCENTS.info}`}
            >
              {ICONS[t.type] || ICONS.info}
              <span className="text-xs font-medium text-slate-100 flex-1 break-words leading-relaxed">
                {String(t.msg || '')}
              </span>
              <button
                onClick={() => dismiss(t.id)}
                className="text-slate-500 hover:text-white transition shrink-0 cursor-pointer p-0.5 rounded-lg hover:bg-white/[0.06]"
              >
                <X size={14} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
