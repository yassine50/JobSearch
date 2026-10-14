import { motion } from 'framer-motion'
import { Mail, AlertCircle, ArrowRight, X, ExternalLink, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export default function SmtpPromptModal({ isOpen, onClose }) {
  const navigate = useNavigate()

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 15 }}
        className="w-full max-w-md p-6 border rounded-2xl bg-slate-900 border-slate-700/80 shadow-2xl space-y-5"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-400">
              <Mail size={22} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white leading-tight">Connect Your Email</h3>
              <p className="text-xs text-slate-400">Required for 1-Click Auto-Apply</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/80 border border-slate-700/70 text-xs text-slate-300 space-y-3 leading-relaxed">
          <p className="font-semibold text-white flex items-center gap-1.5">
            <ShieldCheck size={15} className="text-emerald-400" />
            Send directly from your own Gmail account:
          </p>
          <ol className="list-decimal list-inside space-y-1.5 text-slate-400 pl-1">
            <li>Open your <span className="text-slate-200 font-medium">Google Account</span> Security settings.</li>
            <li>Ensure 2-Step Verification is active, then create an <span className="text-slate-200 font-medium">App Password</span>.</li>
            <li>Paste your email and 16-character app password in <span className="text-blue-400 font-medium">Settings → Email</span>.</li>
          </ol>
          <p className="text-[11px] text-slate-500 pt-1 border-t border-slate-700/60">
            Takes less than 1 minute. Emails arrive in recruiters' primary inbox with your tailored PDF resume attached.
          </p>
        </div>

        <div className="flex items-center justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
          >
            Maybe Later
          </button>
          <button
            type="button"
            onClick={() => {
              onClose()
              navigate('/settings')
            }}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer"
          >
            <span>Open Email Settings</span>
            <ArrowRight size={13} />
          </button>
        </div>
      </motion.div>
    </div>
  )
}
