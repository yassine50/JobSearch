import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Users, ShieldCheck, Globe, Mail, ExternalLink, Copy, Check, Loader2, Sparkles, Send
} from 'lucide-react'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

export default function CompanyContactsModal({ isOpen, onClose, job, onSelectEmailForApply }) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [copiedEmail, setCopiedEmail] = useState(null)

  useEffect(() => {
    if (isOpen && job) {
      discoverContacts()
    } else if (!isOpen) {
      setResult(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, job?.company, job?.title, job?.role_title])

  const discoverContacts = async () => {
    setLoading(true)
    try {
      const { data } = await client.post('/power/find-company-contacts', {
        company: job?.company || '',
        role_title: job?.title || job?.role_title || '',
        location: job?.location || '',
        job_url: job?.url || job?.job_url_direct || job?.post_url || '',
        description: job?.description || job?.full_text || '',
      })
      setResult(data)
    } catch (err) {
      toast(err.response?.data?.detail || 'Could not discover contacts for this company', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = (email) => {
    navigator.clipboard.writeText(email)
    setCopiedEmail(email)
    toast(`Copied ${email}`, 'success')
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  if (!isOpen || !job) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          onClick={e => e.stopPropagation()}
          className="glass-dropdown rounded-3xl w-full max-w-2xl max-h-[88vh] overflow-hidden flex flex-col border border-white/[0.1] shadow-2xl relative"
        >
          <div className="glow-line-top" />

          {/* Header */}
          <div className="p-6 border-b border-white/[0.08] flex items-center justify-between gap-4 bg-slate-950/50">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-purple-500/15 border border-purple-500/30 flex items-center justify-center text-purple-400 shrink-0">
                <Users size={18} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-black text-lg text-white tracking-tight truncate">
                    HR &amp; Decision-Maker Radar
                  </h3>
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/30">
                    DNS MX Intelligence
                  </span>
                </div>
                <p className="text-xs text-slate-400 truncate mt-0.5">
                  Target Company: <strong className="text-white">{job.company || 'Company'}</strong> · {job.title || job.role_title}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 hover:text-white transition cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 overflow-y-auto space-y-6 flex-1">
            {loading ? (
              <div className="py-12 text-center space-y-3">
                <Loader2 size={28} className="animate-spin text-purple-400 mx-auto" />
                <p className="text-sm font-bold text-white">Scanning Corporate Domain &amp; LinkedIn Recruiters...</p>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Resolving official domain for <span className="text-white font-semibold">{job.company}</span>, validating DNS MX servers, and locating Talent Acquisition &amp; Engineering leads.
                </p>
              </div>
            ) : !result ? (
              <div className="py-10 text-center text-xs text-slate-400">
                Could not resolve company domain or contacts. Ensure the job has a valid company name.
              </div>
            ) : (
              <>
                {/* Domain & MX Verification Banner */}
                <div className="glass-card rounded-2xl p-4 border border-white/[0.08] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0">
                      <Globe size={16} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-white flex items-center gap-2">
                        <span>Corporate Domain: {result.domain || 'Not detected'}</span>
                        {result.mx_verified && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                            <ShieldCheck size={11} /> MX Active
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {result.mx_verified
                          ? 'Mail Exchange (MX) records verified — domain actively accepts incoming recruiter & HR outreach.'
                          : 'Public LinkedIn recruiter profiles discovered below.'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Verified Corporate Email Channels */}
                {result.email_channels?.length > 0 && (
                  <div className="space-y-2.5">
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                      <Mail size={13} /> Verified Corporate Outreach Channels ({result.email_channels.length})
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {result.email_channels.map(ch => (
                        <div
                          key={ch.email}
                          className="glass-card rounded-2xl p-3.5 border border-emerald-500/25 flex items-center justify-between gap-2"
                        >
                          <div className="min-w-0">
                            <div className="text-xs font-mono font-bold text-emerald-300 truncate">{ch.email}</div>
                            <div className="text-[10px] text-slate-400 flex items-center gap-1.5 mt-0.5">
                              <span>{ch.type}</span>
                              <span>·</span>
                              <span className="text-emerald-400 font-semibold">{ch.confidence}% Match</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <button
                              type="button"
                              onClick={() => handleCopy(ch.email)}
                              className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.1] border border-white/[0.08] text-slate-300 hover:text-white transition cursor-pointer"
                              title="Copy email"
                            >
                              {copiedEmail === ch.email ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                            </button>
                            {onSelectEmailForApply && (
                              <button
                                type="button"
                                onClick={() => {
                                  onSelectEmailForApply(ch.email)
                                  onClose()
                                }}
                                className="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold flex items-center gap-1 transition cursor-pointer"
                                title="Auto-Apply to this email"
                              >
                                <Send size={11} />
                                <span>Apply</span>
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Discovered LinkedIn Recruiters & Engineering Leads */}
                <div className="space-y-2.5">
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-purple-300 flex items-center gap-1.5">
                    <Sparkles size={13} /> Discovered Recruiters &amp; Decision Makers ({result.decision_makers?.length || 0})
                  </h4>
                  {!result.decision_makers?.length ? (
                    <div className="glass-card rounded-2xl p-5 text-center text-xs text-slate-400">
                      No public LinkedIn profiles indexed for this exact company name yet. Use the corporate email channels above for direct outreach.
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {result.decision_makers.map((dm, i) => (
                        <div
                          key={dm.linkedin_url || i}
                          className="glass-card rounded-2xl p-4 border border-white/[0.07] hover:border-purple-500/35 transition flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                        >
                          <div className="space-y-1 min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-extrabold text-sm text-white">{dm.name}</span>
                              {dm.inferred_email && (
                                <span
                                  onClick={() => handleCopy(dm.inferred_email)}
                                  className="text-[11px] font-mono text-emerald-300 bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 rounded-md cursor-pointer hover:bg-emerald-500/20 transition flex items-center gap-1"
                                  title="Click to copy inferred corporate email"
                                >
                                  <Mail size={10} /> {dm.inferred_email}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-purple-300 font-medium truncate">{dm.headline}</p>
                            {dm.snippet && <p className="text-[11px] text-slate-400 line-clamp-2">{dm.snippet}</p>}
                          </div>

                          <div className="flex items-center gap-2 shrink-0">
                            {dm.inferred_email && onSelectEmailForApply && (
                              <button
                                type="button"
                                onClick={() => {
                                  onSelectEmailForApply(dm.inferred_email, dm.name)
                                  onClose()
                                }}
                                className="px-3 py-1.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border border-emerald-500/35 text-xs font-bold transition flex items-center gap-1.5 cursor-pointer"
                              >
                                <Send size={12} />
                                <span>Email {dm.name.split(' ')[0]}</span>
                              </button>
                            )}
                            <a
                              href={dm.linkedin_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 rounded-xl bg-blue-600/20 hover:bg-blue-600 text-blue-300 hover:text-white border border-blue-500/35 text-xs font-bold transition flex items-center gap-1.5"
                            >
                              <span>LinkedIn</span>
                              <ExternalLink size={12} />
                            </a>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
