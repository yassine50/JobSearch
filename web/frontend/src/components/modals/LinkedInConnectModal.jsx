import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Link2, ShieldCheck, CheckCircle2, AlertCircle, Eye, EyeOff, Loader2, X, ExternalLink, Trash2, Sparkles } from 'lucide-react'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

export default function LinkedInConnectModal({ isOpen, onClose, onConnected }) {
  const toast = useToast()
  const [cookieInput, setCookieInput] = useState('')
  const [showCookie, setShowCookie] = useState(false)
  const [loading, setLoading] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [connected, setConnected] = useState(false)
  const [maskedCookie, setMaskedCookie] = useState('')

  // Load account status on open
  useEffect(() => {
    if (isOpen) {
      checkStatus()
    }
  }, [isOpen])

  const checkStatus = async () => {
    setStatusLoading(true)
    try {
      const localCookie = localStorage.getItem('linkedin_li_at') || ''
      const { data } = await client.get('/linkedin-posts/account-status')
      const isConn = Boolean(data.connected || localCookie)
      setConnected(isConn)
      if (data.masked_cookie) {
        setMaskedCookie(data.masked_cookie)
      } else if (localCookie) {
        setMaskedCookie(localCookie.slice(0, 4) + '...' + localCookie.slice(-4))
      }
    } catch {
      const localCookie = localStorage.getItem('linkedin_li_at') || ''
      setConnected(Boolean(localCookie))
      if (localCookie) {
        setMaskedCookie(localCookie.slice(0, 4) + '...' + localCookie.slice(-4))
      }
    } finally {
      setStatusLoading(false)
    }
  }

  const handleConnect = async (e) => {
    e.preventDefault()
    const cleanCookie = cookieInput.trim()
    if (!cleanCookie) {
      toast('Please enter your LinkedIn li_at cookie value', 'error')
      return
    }

    setLoading(true)
    try {
      // Save locally in browser
      localStorage.setItem('linkedin_li_at', cleanCookie)

      // Save on backend user record
      await client.post('/linkedin-posts/connect-account', { li_at: cleanCookie })

      setConnected(true)
      setMaskedCookie(cleanCookie.slice(0, 4) + '...' + cleanCookie.slice(-4))
      setCookieInput('')
      toast('⚡ LinkedIn live feed connected successfully! Live recruiter post search is active.', 'success')
      if (onConnected) onConnected(cleanCookie)
      onClose()
    } catch (err) {
      // Even if backend endpoint had a network hiccup, localStorage is saved
      setConnected(true)
      toast('Session saved locally. Live recruiter searches will now use this cookie.', 'success')
      if (onConnected) onConnected(cleanCookie)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  const handleDisconnect = async () => {
    setLoading(true)
    try {
      localStorage.removeItem('linkedin_li_at')
      await client.post('/linkedin-posts/disconnect-account').catch(() => {})
      setConnected(false)
      setMaskedCookie('')
      toast('LinkedIn session disconnected.', 'info')
      if (onConnected) onConnected('')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 15 }}
        className="w-full max-w-lg p-6 border rounded-2xl bg-slate-900 border-slate-750 shadow-2xl space-y-5"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-500/15 border border-blue-500/30 text-blue-400">
              <Link2 size={22} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white leading-tight flex items-center gap-2">
                <span>Connect LinkedIn Session</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  Live Feed API
                </span>
              </h3>
              <p className="text-xs text-slate-400">Search recruiter posts directly with infinite scroll & date filters</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Current Connection Status Badge */}
        <div className={`p-3.5 rounded-xl border flex items-center justify-between gap-3 text-xs ${
          connected 
            ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' 
            : 'bg-slate-800/60 border-slate-700/60 text-slate-300'
        }`}>
          <div className="flex items-center gap-2.5">
            {connected ? (
              <CheckCircle2 size={18} className="text-blue-400 shrink-0" />
            ) : (
              <AlertCircle size={18} className="text-blue-400 shrink-0" />
            )}
            <div>
              <div className="font-semibold text-white">
                {connected ? 'Active LinkedIn Session Connected' : 'Not Connected (Fallback Mode)'}
              </div>
              <div className="text-[11px] text-slate-400">
                {connected ? `Cookie active: ${maskedCookie}` : 'Connect your session to search live LinkedIn posts directly'}
              </div>
            </div>
          </div>

          {connected && (
            <button
              type="button"
              onClick={handleDisconnect}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.12] text-slate-200 hover:text-white text-[11px] font-bold transition cursor-pointer flex items-center gap-1 shrink-0"
              title="Disconnect LinkedIn session"
            >
              <Trash2 size={12} className="text-blue-400" />
              <span>Disconnect</span>
            </button>
          )}
        </div>

        {/* Step by Step Guide */}
        <div className="p-4 rounded-xl bg-slate-800/60 border border-slate-700/60 text-xs text-slate-300 space-y-2.5 leading-relaxed">
          <p className="font-semibold text-white flex items-center gap-1.5">
            <Sparkles size={14} className="text-blue-400" />
            How to get your <code className="text-blue-300 bg-blue-500/10 border border-blue-500/25 px-1.5 py-0.5 rounded font-mono">li_at</code> cookie in 30 seconds:
          </p>
          <ol className="list-decimal list-inside space-y-1.5 text-slate-300 pl-1 text-[11.5px]">
            <li>Open <a href="https://www.linkedin.com" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline font-medium inline-flex items-center gap-0.5">LinkedIn.com <ExternalLink size={10} /></a> in Chrome / Safari / Edge and ensure you are logged in.</li>
            <li>Press <kbd className="bg-blue-500/10 border border-blue-500/25 px-1.5 py-0.5 rounded text-[10px] font-bold text-blue-300 font-mono">F12</kbd> (or right click page &rarr; <span className="text-slate-100 font-semibold">Inspect</span>).</li>
            <li>Click the <span className="text-slate-100 font-semibold">Application</span> tab (or Storage) &rarr; Expand <span className="text-slate-100 font-semibold">Cookies</span> &rarr; Click <code className="text-blue-300 font-mono">https://www.linkedin.com</code>.</li>
            <li>Find the cookie named <strong className="text-blue-300 font-bold bg-blue-500/10 border border-blue-500/25 px-1.5 py-0.5 rounded font-mono text-[10.5px]">li_at</strong>, double click its value, copy it, and paste below.</li>
          </ol>
          <p className="text-[11px] text-slate-400 pt-1.5 border-t border-slate-700/40 flex items-center gap-1">
            <ShieldCheck size={12} className="text-blue-400 shrink-0" />
            <span>Used only for read-only querying of LinkedIn's live public Content Search feed.</span>
          </p>
        </div>

        {/* Form Input */}
        <form onSubmit={handleConnect} className="space-y-3.5">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              LinkedIn Session Cookie (<code className="text-blue-300">li_at</code>)
            </label>
            <div className="relative">
              <input
                type={showCookie ? 'text' : 'password'}
                value={cookieInput}
                onChange={e => setCookieInput(e.target.value)}
                placeholder={connected ? 'Paste new cookie to update session...' : 'AQEDARx...'}
                className="w-full bg-slate-950 border border-slate-700 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none pr-10 font-mono"
              />
              <button
                type="button"
                onClick={() => setShowCookie(!showCookie)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                title={showCookie ? 'Hide value' : 'Show value'}
              >
                {showCookie ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2.5 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !cookieInput.trim()}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold shadow-md shadow-blue-500/20 transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Connecting...</span>
                </>
              ) : (
                <>
                  <Link2 size={14} />
                  <span>{connected ? 'Update Session' : 'Save & Connect Live Feed'}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}
