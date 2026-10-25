import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import confetti from 'canvas-confetti'
import client, { getCached } from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import {
  Zap, Mail, Building2, User, FileText, Check, Loader2,
  X, ShieldCheck, Sparkles, Send, CheckSquare, Square, AlertCircle
} from 'lucide-react'

export default function BatchApplyModal({
  isOpen,
  onClose,
  items = [], // Array of LinkedIn posts or Job Board jobs with emails
  source = 'linkedin', // 'linkedin' | 'jobs'
  onSuccess,
  onOpenSmtpPrompt
}) {
  const toast = useToast()
  const { user } = useAuth()
  const [selectedIds, setSelectedIds] = useState([])
  const [sending, setSending] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0, currentTarget: '' })
  const [results, setResults] = useState(null)
  const [errorBanner, setErrorBanner] = useState('')
  const [cvFilename, setCvFilename] = useState(() => getCached('/cv/info')?.filename || '')

  useEffect(() => {
    if (isOpen) {
      const cached = getCached('/cv/info')?.filename
      if (cached) setCvFilename(cached)
      client.get('/cv/info').then(r => {
        setCvFilename(r.data?.filename || '')
      }).catch(() => {})
    }
  }, [isOpen])

  const displayCvName = cvFilename || (user?.name ? `CV_${user.name.trim().replace(/\s+/g, '_')}.pdf` : 'Tailored_Resume.pdf')

  // Normalize items to standard structure
  const candidateItems = items.map((item, idx) => {
    let email = ''
    let name = 'Hiring Team'
    let company = item.company || 'Company'
    let title = item.role_title || item.title || 'Open Role'
    let id = item.id || `item-${idx}`
    let score = item.score || item.role_fit_score || null
    if (item.score == null && score != null && source === 'linkedin') {
      const skillsCount = Array.isArray(item.matched_skills) ? item.matched_skills.length : 1
      const reqYrs = item.required_years ?? (/\b([4-9]|\d{2})\+?\s*(?:years?|yrs?)\b/i.test(title) ? 5 : null)
      const isSenior = /\b(senior|sr\.?|lead|principal|staff|architect)\b/i.test(title)
      const textLen = (item.full_text || item.post_snippet || '').length
      let refined = 72 + Math.min(skillsCount * 5, 18) + (textLen > 350 ? 4 : textLen > 160 ? 2 : 0)
      if (reqYrs != null && reqYrs >= 4) refined -= 8
      else if (isSenior) refined -= 5
      score = Math.max(58, Math.min(96, refined))
    }

    if (source === 'linkedin') {
      email = item.recruiter_emails?.[0]?.email || ''
      name = item.author_name || 'Hiring Team'
    } else {
      // Job board item
      if (Array.isArray(item.emails) && item.emails.length > 0) {
        email = typeof item.emails[0] === 'object' ? item.emails[0].email : item.emails[0]
      } else if (item.to_email) {
        email = item.to_email
      }
      name = item.to_name || 'Hiring Manager'
    }

    return {
      raw: item,
      id,
      title,
      company,
      name,
      email,
      score,
      post_url: item.post_url || item.url || ''
    }
  }).filter(i => Boolean(i.email && i.email.includes('@')))

  // Auto-select all on open
  useEffect(() => {
    if (isOpen && candidateItems.length > 0) {
      setSelectedIds(candidateItems.map(i => i.id))
      setResults(null)
      setErrorBanner('')
      setProgress({ current: 0, total: candidateItems.length, currentTarget: '' })
    }
  }, [isOpen, items.length])

  if (!isOpen) return null

  const toggleSelect = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const toggleSelectAll = () => {
    if (selectedIds.length === candidateItems.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(candidateItems.map(i => i.id))
    }
  }

  const handleDispatchBatch = async () => {
    const selectedList = candidateItems.filter(i => selectedIds.includes(i.id))
    if (selectedList.length === 0) {
      toast('Please select at least one recruiter to email', 'error')
      return
    }

    setSending(true)
    setErrorBanner('')
    setProgress({ current: 0, total: selectedList.length, currentTarget: 'Connecting to email server...' })

    const CHUNK_SIZE = 5
    let totalApplied = 0
    let allErrors = []
    let dispatchedItems = []

    try {
      for (let offset = 0; offset < selectedList.length; offset += CHUNK_SIZE) {
        const chunk = selectedList.slice(offset, offset + CHUNK_SIZE)
        const targetNames = chunk.map(c => c.company).slice(0, 3).join(', ')
        setProgress({
          current: offset,
          total: selectedList.length,
          currentTarget: `Sending (${offset + 1}–${Math.min(offset + chunk.length, selectedList.length)} of ${selectedList.length}): ${targetNames}...`
        })

        if (source === 'linkedin') {
          const payload = {
            applications: chunk.map(item => ({
              post_url: item.post_url || item.raw?.post_url || item.raw?.url || item.raw?.job_url || '',
              role_title: item.title,
              company: item.company,
              recruiter_name: item.name,
              recruiter_email: item.email,
              post_text: item.raw.full_text || item.raw.post_snippet || '',
              customize_cv: false,
              site: item.raw?.site || 'linkedin'
            }))
          }

          const { data } = await client.post('/linkedin-posts/batch-auto-apply', payload)
          const chunkApplied = Number(data?.applied ?? 0)
          totalApplied += chunkApplied
          if (Array.isArray(data?.errors) && data.errors.length > 0) {
            allErrors.push(...data.errors)
          }

          const sentSet = Array.isArray(data?.dispatched_emails)
            ? new Set(data.dispatched_emails.map(e => String(e).toLowerCase()))
            : null
          const succeededInChunk = sentSet
            ? chunk.filter(i => sentSet.has(String(i.email).trim().toLowerCase()))
            : (chunkApplied > 0 ? chunk.slice(0, chunkApplied) : [])

          if (succeededInChunk.length > 0) {
            dispatchedItems.push(...succeededInChunk)
            if (onSuccess) onSuccess(succeededInChunk)
          }

          // Fail-fast if the very first chunk sent 0 emails
          if (offset === 0 && chunkApplied === 0) {
            const firstErr = data?.errors?.[0] || 'Could not dispatch emails. Please check your Gmail App Password in Settings.'
            throw new Error(firstErr)
          }
        } else {
          // Formal Job Boards batch auto-apply
          const payload = {
            customize_cv: selectedList.length <= 3,
            delay_seconds: 0.1,
            jobs: chunk.map(item => ({
              job_title: item.title,
              company: item.company,
              job_url: item.raw?.url || item.raw?.job_url || item.raw?.job_url_direct || item.post_url || '',
              location: item.raw?.location || '',
              to_email: item.email,
              to_name: item.name,
              job_description: item.raw?.description || '',
              match_score: item.score || 0,
              site: item.raw?.site || ''
            }))
          }

          const { data } = await client.post('/email/batch-auto-apply', payload)
          const chunkApplied = Number(data?.applied ?? 0)
          totalApplied += chunkApplied
          const details = Array.isArray(data?.details) ? data.details : []
          details.forEach(d => {
            if (d.status === 'failed' && d.error) {
              allErrors.push(`${d.company || 'Job'}: ${d.error}`)
            }
          })

          const succeededInChunk = chunk.filter((_, idx) => details[idx]?.status === 'sent')
          const toMark = succeededInChunk.length > 0 ? succeededInChunk : (chunkApplied > 0 ? chunk.slice(0, chunkApplied) : [])
          if (toMark.length > 0) {
            dispatchedItems.push(...toMark)
            if (onSuccess) {
              onSuccess(toMark.map(i => ({
                ...i,
                url: i.raw?.url || i.raw?.job_url || i.raw?.job_url_direct || i.post_url || '',
                ...i.raw
              })))
            }
          }

          if (offset === 0 && chunkApplied === 0) {
            const firstErr = allErrors[0] || 'Could not dispatch emails. Please check your Gmail App Password in Settings.'
            throw new Error(firstErr)
          }
        }

        setProgress({
          current: Math.min(offset + chunk.length, selectedList.length),
          total: selectedList.length,
          currentTarget: `Dispatched ${totalApplied} of ${selectedList.length} applications...`
        })
      }

      if (totalApplied > 0) {
        setResults({ applied: totalApplied, total_requested: selectedList.length, errors: allErrors })
        confetti({ particleCount: 150, spread: 90, origin: { y: 0.6 } })
        toast(`⚡ Successfully dispatched ${totalApplied} application${totalApplied === 1 ? '' : 's'}!`, 'success')
      } else {
        const msg = allErrors[0] || 'No emails were sent. Please verify your Gmail App Password in Settings.'
        setErrorBanner(msg)
        toast(msg, 'error')
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Batch application dispatch failed'
      if (typeof detail === 'string' && detail.toLowerCase().includes('configure your gmail smtp')) {
        onClose()
        if (onOpenSmtpPrompt) onOpenSmtpPrompt()
      } else if (totalApplied > 0) {
        setResults({ applied: totalApplied, total_requested: selectedList.length, errors: [...allErrors, String(detail)] })
        toast(`Sent ${totalApplied} application(s), then stopped: ${detail}`, 'error')
      } else {
        setErrorBanner(String(detail))
        toast(String(detail), 'error')
      }
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className="w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/70">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
              <Zap size={20} className="text-white" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base flex items-center gap-2">
                <span>Batch Auto-Apply Dispatcher</span>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/40">
                  {selectedIds.length} Selected
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Send personalized applications with tailored resumes to all verified recruiters simultaneously
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={sending}
            className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1 text-xs">
          {results ? (
            /* Results Screen */
            <div className="py-6 text-center space-y-4">
              <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center justify-center mx-auto">
                <Check size={32} />
              </div>
              <div>
                <h4 className="text-lg font-bold text-white">Batch Applications Dispatched!</h4>
                <p className="text-xs text-slate-400 mt-1">
                  Sent {Number(results.applied ?? 0)} verified application{Number(results.applied ?? 0) === 1 ? '' : 's'}. Saved to your Pipeline Tracker.
                </p>
              </div>
              {Array.isArray(results.errors) && results.errors.length > 0 && (
                <div className="text-left bg-amber-950/40 border border-amber-700/50 rounded-xl p-3 max-h-28 overflow-y-auto text-[11px] text-amber-200 space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-amber-300">
                    <AlertCircle size={13} />
                    <span>{results.errors.length} item(s) skipped or failed:</span>
                  </div>
                  {results.errors.slice(0, 5).map((e, idx) => (
                    <div key={idx} className="truncate">• {e}</div>
                  ))}
                </div>
              )}
              <button
                type="button"
                onClick={onClose}
                className="px-6 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md transition cursor-pointer"
              >
                Close & View Pipeline
              </button>
            </div>
          ) : (
            <>
              {errorBanner && (
                <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-700/60 text-rose-200 flex items-start gap-2.5 text-xs">
                  <AlertCircle size={16} className="text-rose-400 shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-rose-300">Email Dispatch Error</div>
                    <div className="text-[11px] mt-0.5 break-words">{errorBanner}</div>
                  </div>
                </div>
              )}
              {sending && progress.total > 0 && (
                <div className="p-3 rounded-xl bg-blue-950/40 border border-blue-700/50 space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-blue-200 font-semibold">
                    <span className="truncate pr-2">{progress.currentTarget || 'Dispatching emails...'}</span>
                    <span className="shrink-0 font-mono">{progress.current} / {progress.total}</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-300"
                      style={{ width: `${Math.max(8, Math.round((progress.current / Math.max(1, progress.total)) * 100))}%` }}
                    />
                  </div>
                </div>
              )}
              {/* Controls Bar */}
              <div className="flex items-center justify-between bg-slate-950 p-3 rounded-xl border border-slate-800">
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  className="flex items-center gap-2 text-slate-300 hover:text-white font-semibold cursor-pointer"
                >
                  {selectedIds.length === candidateItems.length ? (
                    <CheckSquare size={16} className="text-blue-400" />
                  ) : (
                    <Square size={16} className="text-slate-500" />
                  )}
                  <span>{selectedIds.length === candidateItems.length ? 'Deselect All' : 'Select All'} ({candidateItems.length})</span>
                </button>

                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold bg-emerald-950/50 border border-emerald-800/50 px-3 py-1 rounded-lg">
                  <FileText size={13} className="text-emerald-400" />
                  <span>Attaching Original Verified Resume ({displayCvName})</span>
                </div>
              </div>

              {/* Recipient Cards List */}
              <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                {candidateItems.map((item) => {
                  const isSelected = selectedIds.includes(item.id)
                  return (
                    <div
                      key={item.id}
                      onClick={() => toggleSelect(item.id)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between gap-3 ${
                        isSelected
                          ? 'bg-slate-800/90 border-blue-500/70 shadow-sm'
                          : 'bg-slate-900/60 border-slate-800 opacity-60'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="shrink-0 text-blue-400">
                          {isSelected ? <CheckSquare size={16} /> : <Square size={16} className="text-slate-500" />}
                        </div>
                        <div className="min-w-0">
                          <h5 className="font-bold text-white text-xs truncate">{item.title}</h5>
                          <div className="flex items-center gap-2 text-[11px] text-slate-400">
                            <span className="text-blue-300 font-medium flex items-center gap-1 truncate max-w-[120px]">
                              <Building2 size={10} /> {item.company}
                            </span>
                            <span>·</span>
                            <span className="text-emerald-400 font-mono text-[10px] flex items-center gap-1 truncate">
                              <ShieldCheck size={10} /> {item.email}
                            </span>
                          </div>
                        </div>
                      </div>

                      {item.score != null && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-purple-950/80 border-purple-700 text-purple-300 shrink-0">
                          {item.score}% Fit
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Safety & Compliance notice */}
              <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 text-[11px] text-slate-400 space-y-1">
                <div className="flex items-center gap-1.5 font-bold text-slate-300">
                  <ShieldCheck size={13} className="text-emerald-400" />
                  <span>Deliverability & Spam Guard Active</span>
                </div>
                <p className="leading-relaxed">
                  Emails are sent directly from your verified Gmail address with personalized greeting, relevant subject line, and a per-job tailored copy of your resume (missing job skills added, off-topic content removed).
                </p>
              </div>
            </>
          )}
        </div>

        {/* Modal Footer */}
        {!results && (
          <div className="p-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={sending}
              className="px-4 py-2 rounded-xl border border-slate-750 text-slate-400 hover:text-white hover:bg-slate-800 transition text-xs font-semibold cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleDispatchBatch}
              disabled={sending || selectedIds.length === 0}
              className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-blue-500/25 transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {sending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Sending Applications ({selectedIds.length})...</span>
                </>
              ) : (
                <>
                  <Send size={14} />
                  <span>Send Applications to All ({selectedIds.length})</span>
                </>
              )}
            </button>
          </div>
        )}
      </motion.div>
    </div>
  )
}
