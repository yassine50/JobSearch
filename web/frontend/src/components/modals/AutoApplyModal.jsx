import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import confetti from 'canvas-confetti'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import {
  Zap, Mail, Building2, User, FileText, Check, Loader2,
  X, ShieldCheck, Sparkles, Send, ArrowRight
} from 'lucide-react'

export default function AutoApplyModal({
  isOpen,
  onClose,
  post,
  onSuccess,
  onOpenSmtpPrompt
}) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [selectedEmail, setSelectedEmail] = useState('')
  const [recruiterName, setRecruiterName] = useState('')
  const [customizeCv, setCustomizeCv] = useState(true)

  useEffect(() => {
    if (post) {
      const email = post.recruiter_emails?.[0]?.email || ''
      const name = post.author_name || 'Hiring Team'
      const comp = post.company || 'the team'
      const title = post.role_title || 'Software Opportunity'

      setSelectedEmail(email)
      setRecruiterName(name)
      setSubject(`Application for ${title} — ${comp}`)
      setBody(
`Dear ${name} at ${comp},

I came across your hiring publication on LinkedIn for the ${title} opportunity and wanted to reach out directly.

Having reviewed your technical requirements, my experience aligns closely with the skills your team is seeking. I build high-performance, maintainable software and would love to contribute to your upcoming projects.

I have attached my tailored resume for your review. Thank you for your time, and I look forward to speaking with you.

Best regards,`
      )
    }
  }, [post])

  if (!isOpen || !post) return null

  const handleSend = async () => {
    if (!selectedEmail) {
      toast('No recipient email available for this post', 'error')
      return
    }

    setLoading(true)
    try {
      const targetUrl = post.post_url || post.url || post.job_url || post.job_url_direct || ''
      const targetTitle = post.role_title || post.title || 'Software Opportunity'
      const targetCompany = post.company || 'Company'
      const targetLocation = post.location || ''

      const { data } = await client.post('/linkedin-posts/auto-apply', {
        post_url: targetUrl,
        role_title: targetTitle,
        company: targetCompany,
        location: targetLocation,
        recruiter_name: recruiterName,
        recruiter_email: selectedEmail,
        post_text: post.full_text || post.post_snippet || post.description || '',
        customize_cv: customizeCv,
        custom_subject: subject,
        custom_body: body
      })

      confetti({ particleCount: 120, spread: 80, origin: { y: 0.6 } })
      toast(data.message || `Application sent to ${selectedEmail}!`, 'success')
      if (onSuccess) onSuccess({
        ...post,
        url: targetUrl,
        post_url: targetUrl,
        title: targetTitle,
        role_title: targetTitle,
        company: targetCompany
      })
      onClose()
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string' && detail.toLowerCase().includes('smtp')) {
        onClose()
        if (onOpenSmtpPrompt) onOpenSmtpPrompt()
      } else {
        toast(detail || err.message || 'Failed to dispatch application', 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  const emailsList = post.recruiter_emails || []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className="w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-600 text-slate-950 font-bold shadow-md shadow-amber-500/20">
              <Zap size={18} className="fill-slate-950" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span>1-Click Auto-Apply</span>
                <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-950/80 border border-emerald-800/80 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <ShieldCheck size={10} /> Verified Recruiter
                </span>
              </h3>
              <p className="text-xs text-slate-400">Review outreach message and tailored CV attachment</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {/* Target Meta Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3.5 rounded-xl bg-slate-800/60 border border-slate-750">
            <div>
              <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1 mb-1">
                <Building2 size={12} className="text-blue-400" /> Target Role & Company
              </span>
              <p className="text-xs font-bold text-white truncate">{post.role_title || 'Role'}</p>
              <p className="text-xs text-blue-300 truncate">{post.company || 'Company'}</p>
            </div>

            <div>
              <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1 mb-1">
                <Mail size={12} className="text-purple-400" /> Recruiter Contact
              </span>
              {emailsList.length > 1 ? (
                <select
                  value={selectedEmail}
                  onChange={e => setSelectedEmail(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  {emailsList.map((e, idx) => (
                    <option key={idx} value={e.email}>
                      {e.email} {e.name ? `(${e.name})` : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-mono font-bold text-white bg-purple-950/80 border border-purple-800/80 px-2 py-0.5 rounded">
                    {selectedEmail || 'No email'}
                  </span>
                  <span className="text-[10px] text-emerald-400 bg-emerald-950/70 border border-emerald-800/60 px-1.5 py-0.2 rounded font-medium">
                    MX Valid
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Subject Line */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">Email Subject</label>
            <input
              type="text"
              value={subject}
              onChange={e => setSubject(e.target.value)}
              className="w-full px-3 py-2 text-xs text-white bg-slate-900 border border-slate-700 rounded-xl focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Message Body */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300">Personalized Message</label>
              <span className="text-[11px] text-slate-500 font-mono">{body.length} chars</span>
            </div>
            <textarea
              rows={6}
              value={body}
              onChange={e => setBody(e.target.value)}
              className="w-full p-3 text-xs leading-relaxed text-slate-200 bg-slate-900 border border-slate-700 rounded-xl focus:outline-none focus:border-blue-500 resize-none font-sans"
            />
          </div>

          {/* Tailored CV Toggle & Bridged Skills */}
          <div className="p-3.5 rounded-xl bg-slate-850 border border-slate-700/60 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-purple-600/20 text-purple-300 border border-purple-500/30">
                  <Sparkles size={15} />
                </div>
                <div>
                  <p className="text-xs font-semibold text-white flex items-center gap-2">
                    <span>Attach Tailored PDF Resume</span>
                    {post.score != null && (
                      <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-purple-950 border border-purple-700 text-purple-300">
                        {post.score}% Match
                      </span>
                    )}
                  </p>
                  <p className="text-[11px] text-slate-400">Dynamically optimizes your resume to bridge recruiter requirements</p>
                </div>
              </div>
              <input
                type="checkbox"
                checked={customizeCv}
                onChange={e => setCustomizeCv(e.target.checked)}
                className="w-4 h-4 rounded text-blue-600 bg-slate-900 border-slate-700 focus:ring-blue-500 cursor-pointer"
              />
            </div>

            {customizeCv && post.missing_skills && post.missing_skills.length > 0 && (
              <div className="p-2 rounded-lg bg-purple-950/40 border border-purple-800/40 text-[11px] text-purple-200 flex items-center gap-1.5 flex-wrap">
                <span className="text-amber-300 font-semibold">Bridging keywords in PDF:</span>
                {post.missing_skills.slice(0, 4).map((ms, i) => (
                  <span key={i} className="px-1.5 py-0.2 rounded bg-purple-900/60 text-purple-300 border border-purple-700/50">
                    +{ms}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSend}
            disabled={loading || !selectedEmail}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs shadow-lg shadow-amber-500/20 transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} className="fill-slate-950" />}
            <span>{loading ? 'Dispatching Application...' : 'Send Tailored Application'}</span>
          </button>
        </div>
      </motion.div>
    </div>
  )
}
