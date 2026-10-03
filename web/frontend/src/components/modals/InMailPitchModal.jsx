import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import { MessageSquare, Copy, Check, ExternalLink, X, Sparkles, Loader2 } from 'lucide-react'

export default function InMailPitchModal({ isOpen, onClose, post }) {
  const toast = useToast()
  const [note, setNote] = useState('')
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isOpen && post) {
      setLoading(true)
      client.post('/linkedin-posts/generate-inmail', {
        recruiter_name: post.author_name || 'Hiring Manager',
        company: post.company || 'Company',
        role_title: post.role_title || 'Software Opportunity',
        post_text: post.full_text || post.post_snippet || ''
      }).then(r => {
        setNote(r.data?.note || '')
      }).catch(() => {
        const name = (post.author_name || '').split(' ')[0] || 'there'
        setNote(`Hi ${name}, saw your post regarding the ${post.role_title || 'open role'} at ${post.company || 'your team'}. I have strong experience in this domain and would love to connect and share my resume!`)
      }).finally(() => setLoading(false))
    }
  }, [isOpen, post])

  if (!isOpen || !post) return null

  const handleCopy = () => {
    if (!note) return
    navigator.clipboard.writeText(note)
    setCopied(true)
    toast('Connection note copied to clipboard!', 'info')
    setTimeout(() => setCopied(false), 2000)
  }

  const charCount = note.length
  const isOverLimit = charCount > 300

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 15 }}
        className="w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
              <MessageSquare size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white leading-tight">LinkedIn Connection Note</h3>
              <p className="text-xs text-slate-400">Personalized ≤300 character pitch for direct outreach</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X size={18} />
          </button>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2 text-slate-400">
            <Loader2 size={24} className="animate-spin text-blue-400" />
            <span className="text-xs font-medium">Generating tailored connection note...</span>
          </div>
        ) : (
          <div className="space-y-2.5">
            <div className="relative">
              <textarea
                rows={5}
                value={note}
                onChange={e => setNote(e.target.value)}
                className={`w-full p-3.5 rounded-xl bg-slate-950 border text-xs leading-relaxed text-slate-100 focus:outline-none resize-none font-sans ${
                  isOverLimit ? 'border-red-500 focus:border-red-500' : 'border-slate-700 focus:border-blue-500'
                }`}
                placeholder="Type connection note..."
              />
              <div className="flex items-center justify-between px-1 pt-1 text-[11px]">
                <span className="text-slate-500">LinkedIn limits connection request notes to 300 characters.</span>
                <span className={`font-mono font-bold ${isOverLimit ? 'text-red-400' : 'text-slate-400'}`}>
                  {charCount}/300
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <a
                href={post.post_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
              >
                <span>Open Post on LinkedIn</span>
                <ExternalLink size={12} />
              </a>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-white transition"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer"
                >
                  {copied ? <Check size={14} className="text-emerald-300" /> : <Copy size={14} />}
                  <span>{copied ? 'Copied to Clipboard!' : 'Copy Note'}</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  )
}
