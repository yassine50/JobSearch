import { useState } from 'react'
import { motion } from 'framer-motion'
import { useToast } from '../../context/ToastContext.jsx'
import {
  FileText, Copy, Check, ExternalLink, X, Building2, User,
  MapPin, ShieldCheck, Mail
} from 'lucide-react'

export default function PostReaderModal({ isOpen, onClose, post, onAutoApply }) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)

  if (!isOpen || !post) return null

  const text = post.full_text || post.post_snippet || 'No post content available.'
  const firstEmail = post.recruiter_emails?.[0]?.email

  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    toast('Post text copied to clipboard', 'info')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className="w-full max-w-2xl bg-slate-900 border border-slate-750 rounded-2xl shadow-2xl flex flex-col max-h-[88vh] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/70 flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-base font-bold text-white leading-snug">
              {post.role_title || 'LinkedIn Recruiter Publication'}
            </h3>
            <div className="flex items-center gap-2 text-xs text-slate-400 flex-wrap">
              <span className="text-white font-medium flex items-center gap-1">
                <User size={12} className="text-slate-500" />
                {post.author_name}
              </span>
              <span>·</span>
              <span className="text-blue-300 font-semibold flex items-center gap-1">
                <Building2 size={12} className="text-blue-400" />
                {post.company}
              </span>
              {post.location && (
                <>
                  <span>·</span>
                  <span className="text-emerald-300 flex items-center gap-0.5">
                    <MapPin size={11} /> {post.location}
                  </span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {/* Post Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 text-xs text-slate-200 leading-relaxed font-sans whitespace-pre-line selection:bg-blue-600 selection:text-white">
            {text}
          </div>

          {post.recruiter_emails && post.recruiter_emails.length > 0 && (
            <div className="p-3 rounded-xl bg-purple-950/30 border border-purple-800/40 flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <Mail size={14} className="text-purple-400" />
                <span className="text-xs font-mono font-bold text-white">
                  {post.recruiter_emails[0].email}
                </span>
                <span className="text-[10px] text-emerald-400 font-semibold bg-emerald-950/80 border border-emerald-800/70 px-1.5 py-0.5 rounded-full flex items-center gap-1">
                  <ShieldCheck size={10} /> MX Verified
                </span>
              </div>
              {onAutoApply && (
                <button
                  type="button"
                  onClick={() => {
                    onClose()
                    onAutoApply(post, firstEmail)
                  }}
                  className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition cursor-pointer"
                >
                  ⚡ Auto-Apply
                </button>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 transition cursor-pointer"
          >
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            <span>{copied ? 'Copied Post' : 'Copy Text'}</span>
          </button>

          <div className="flex items-center gap-3">
            <a
              href={post.post_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 font-medium"
            >
              <span>View on LinkedIn</span>
              <ExternalLink size={12} />
            </a>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-750 text-white text-xs font-semibold transition"
            >
              Close
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
