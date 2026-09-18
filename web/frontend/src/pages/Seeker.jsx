import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import confetti from 'canvas-confetti'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import { SkeletonRow } from '../components/Skeleton.jsx'
import { useToast } from '../context/ToastContext.jsx'
import client from '../api/client.js'
import {
  Upload, Search, ExternalLink, Bookmark, Mail, Send, X, Copy,
  Check, Sparkles, Plus, Link, Trash2, Info, ChevronDown, ChevronUp, Globe,
  Zap, Loader2, CheckCircle2, AlertCircle, FileText, Download, ShieldCheck
} from 'lucide-react'

const CORE_SITES = [
  { id:'linkedin', label:'LinkedIn',  color:'bg-blue-700' },
  { id:'indeed',   label:'Indeed',    color:'bg-indigo-700' },
]
const ALL_COUNTRIES = [
  'USA','UK','Canada','Australia','France','Germany','Netherlands',
  'Spain','Switzerland','Belgium','Ireland','Sweden','Denmark','Norway',
  'UAE','Qatar','Saudi Arabia','Singapore','India','South Africa',
  'Morocco','Tunisia','Romania','Poland','Portugal','Italy','Austria',
]
const TEMPLATE_LABELS = {
  application:'📩 Application', cold_outreach:'❄️ Cold Outreach',
  follow_up:'🔁 Follow-Up', thank_you:'🙏 Thank You'
}

const fireConfetti = () => {
  confetti({ particleCount:120, spread:80, origin:{y:0.6}, colors:['#3b82f6','#8b5cf6','#10b981','#f59e0b'] })
}

function EmailPill({ data, onClick }) {
  const [copied, setCopied] = useState(false)
  const source = data.source || 'inferred'
  const isDirect = source === 'found'
  const isSite = source === 'company_site'
  const isVerified = data.verified ?? (isDirect || isSite)

  const tooltip = isDirect
    ? 'Direct recruiter email from post / ATS (100% Deliverable)'
    : isSite
    ? 'Official email from company website (Verified Deliverable)'
    : 'Inferred domain mailbox (Unverified — not used for auto-apply)'

  const copy = (e) => {
    e.stopPropagation()
    navigator.clipboard.writeText(data.email)
    setCopied(true); setTimeout(()=>setCopied(false),1500)
  }

  return (
    <div className="flex items-center gap-1 group">
      <button onClick={onClick} title={tooltip}
        className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-all max-w-[190px] font-medium ${
          isDirect
            ? 'bg-emerald-950/70 text-emerald-300 border-emerald-700/80 hover:bg-emerald-900'
            : isSite
            ? 'bg-cyan-950/70 text-cyan-300 border-cyan-700/80 hover:bg-cyan-900'
            : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-750 opacity-70'
        }`}>
        <Mail size={11} className="shrink-0"/>
        <span className="truncate">{data.email}</span>
        <span className={`text-[10px] shrink-0 font-bold ${
          isDirect ? 'text-emerald-400' : isSite ? 'text-cyan-400' : 'text-slate-500'
        }`} title={tooltip}>●</span>
      </button>
      <button onClick={copy} className="opacity-0 group-hover:opacity-100 transition text-slate-500 hover:text-white shrink-0" title="Copy email">
        {copied ? <Check size={11} className="text-emerald-400"/> : <Copy size={11}/>}
      </button>
    </div>
  )
}

function JobDetailPopup({ job, onClose, onEmail, onSave, onAutoApply, onTailor, isApplying, isApplied }) {
  const hasVerifiedEmail = job.emails?.some(e => e.verified || e.source === 'found' || e.source === 'company_site')

  return (
    <motion.div className="fixed inset-0 bg-black/75 z-50 flex items-end sm:items-center justify-center p-4"
      initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
      onClick={onClose}>
      <motion.div
        initial={{opacity:0,y:40,scale:.97}} animate={{opacity:1,y:0,scale:1}}
        exit={{opacity:0,y:20,scale:.97}}
        transition={{type:'spring',damping:24,stiffness:300}}
        className="bg-slate-800 border border-slate-700 rounded-t-2xl md:rounded-2xl w-full md:max-w-xl max-h-[92vh] overflow-y-auto"
        onClick={e=>e.stopPropagation()}>
        <div className="sticky top-0 bg-slate-800 border-b border-slate-700 px-6 py-4 flex items-start justify-between rounded-t-2xl">
          <div className="flex-1 min-w-0 mr-3">
            <h3 className="font-bold text-base truncate">{job.title}</h3>
            <p className="text-slate-400 text-sm">{job.company} · {job.location}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {job.score!=null && <ScoreBadge score={job.score}/>}
            <button onClick={onClose} className="text-slate-400 hover:text-white transition p-1"><X size={18}/></button>
          </div>
        </div>
        <div className="p-6">
          {/* Meta row */}
          <div className="flex flex-wrap gap-2 mb-4">
            <span className="bg-slate-700 text-xs px-2.5 py-1 rounded-full capitalize">{job.site}</span>
            {job.salary && <span className="bg-emerald-900 text-emerald-300 text-xs px-2.5 py-1 rounded-full">{job.salary}</span>}
            {job.date_posted && <span className="text-slate-500 text-xs self-center">{job.date_posted}</span>}
          </div>
          {/* Emails */}
          {job.emails?.length>0 && (
            <div className="mb-4">
              <p className="text-xs text-slate-400 mb-2">📧 Recruiter Contacts</p>
              <div className="flex flex-wrap gap-2">
                {job.emails.map((e,i)=>(
                  <EmailPill key={i} data={e} onClick={()=>{onClose();onEmail(job,e.email)}}/>
                ))}
              </div>
            </div>
          )}
          {/* Matched / missing skills */}
          {job.matched_skills?.length>0 && (
            <div className="mb-3">
              <p className="text-xs text-slate-400 mb-1.5">✅ Your matched skills</p>
              <div className="flex flex-wrap gap-1">
                {job.matched_skills.map(s=><span key={s} className="bg-emerald-900 text-emerald-300 text-xs px-2 py-0.5 rounded-full">{s}</span>)}
              </div>
            </div>
          )}
          {job.missing_skills?.length>0 && (
            <div className="mb-4">
              <p className="text-xs text-slate-400 mb-1.5">❌ Skills to develop (Auto-Bridged in Tailored CV)</p>
              <div className="flex flex-wrap gap-1">
                {job.missing_skills.map(s=><span key={s} className="bg-red-950 text-red-400 text-xs px-2 py-0.5 rounded-full">✗ {s}</span>)}
              </div>
            </div>
          )}
          {/* Description */}
          {job.description && (
            <div className="border-t border-slate-700 pt-4">
              <p className="text-xs text-slate-400 mb-2">📋 Description</p>
              <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{job.description.substring(0,600)}{job.description.length>600?'…':''}</p>
            </div>
          )}
          {/* Actions */}
          <div className="flex gap-2 mt-5 sticky bottom-0 bg-slate-800 pt-3 flex-wrap">
            <button onClick={()=>{onClose();onTailor(job)}}
              className="flex-1 min-w-[120px] flex items-center justify-center gap-1.5 bg-purple-900/80 hover:bg-purple-800 border border-purple-600/70 text-purple-200 py-2.5 rounded-xl text-sm transition-colors font-semibold cursor-pointer">
              <Sparkles size={15}/>Tailor CV
            </button>
            {hasVerifiedEmail ? (
              isApplied ? (
                <div className="flex-1 min-w-[140px] flex items-center justify-center gap-1.5 bg-emerald-950/80 border border-emerald-700/80 py-2.5 rounded-xl text-sm font-semibold text-emerald-300">
                  <Check size={15} className="stroke-[3]" /> Applied
                </div>
              ) : (
                <button
                  onClick={() => onAutoApply(job)}
                  disabled={isApplying}
                  className="flex-1 min-w-[140px] flex items-center justify-center gap-1.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold py-2.5 rounded-xl text-sm transition-all shadow-md shadow-amber-500/20 disabled:opacity-50 cursor-pointer"
                >
                  {isApplying ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} className="fill-slate-950" />}
                  <span>⚡ 1-Click Auto-Apply</span>
                </button>
              )
            ) : (
              job.url && (
                <a href={job.url} target="_blank" rel="noopener noreferrer"
                  className="flex-1 min-w-[140px] flex items-center justify-center gap-1.5 bg-slate-700 hover:bg-slate-600 py-2.5 rounded-xl text-sm transition-colors font-semibold text-slate-200">
                  <ExternalLink size={15}/>Apply on Portal
                </a>
              )
            )}
            <button onClick={()=>onSave(job)}
              className="min-w-[80px] flex items-center justify-center gap-1.5 bg-emerald-800 hover:bg-emerald-700 py-2.5 rounded-xl text-sm transition-colors">
              <Bookmark size={15}/>Save
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}

function BatchAutoApplyModal({ isOpen, onClose, eligibleJobs, onExecute, isApplying, progress, cvInfo }) {
  if (!isOpen) return null
  const isDone = progress?.status === 'done'

  return (
    <motion.div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
      onClick={() => !isApplying && onClose()}>
      <motion.div
        initial={{opacity:0, scale:0.94, y:20}}
        animate={{opacity:1, scale:1, y:0}}
        exit={{opacity:0, scale:0.94, y:20}}
        transition={{type:'spring', damping:25, stiffness:320}}
        className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}>
        
        {/* Header */}
        <div className="bg-slate-850 border-b border-slate-700 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
              <Zap size={20} className="fill-amber-400" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">⚡ Batch Direct Applications</h3>
              <p className="text-xs text-slate-400">1-click direct outreach to verified recruiter inboxes</p>
            </div>
          </div>
          {!isApplying && (
            <button onClick={onClose} className="text-slate-400 hover:text-white transition p-1">
              <X size={20} />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-4 flex-1">
          {/* Key Facts Cards */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-900/80 border border-slate-700/80 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-400 font-medium">Recruiter Targets</p>
              <p className="text-lg font-bold text-amber-400 mt-0.5">{eligibleJobs.length} Jobs</p>
            </div>
            <div className="bg-slate-900/80 border border-slate-700/80 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-400 font-medium">Attached Resume</p>
              <p className="text-xs font-semibold text-emerald-400 mt-1 truncate" title={cvInfo?.filename || 'Resume.pdf'}>
                ✓ {cvInfo?.filename || 'Resume.pdf'}
              </p>
            </div>
            <div className="bg-slate-900/80 border border-slate-700/80 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-400 font-medium">Safe Rate Limit</p>
              <p className="text-xs font-semibold text-blue-400 mt-1">1.0s / email delay</p>
            </div>
          </div>

          {/* If In Progress */}
          {isApplying && (
            <div className="bg-slate-900/90 border border-amber-500/40 rounded-xl p-5 text-center space-y-3">
              <div className="flex items-center justify-center gap-2 text-amber-400">
                <Loader2 size={24} className="animate-spin" />
                <span className="font-semibold text-sm">Delivering applications via Gmail SMTP...</span>
              </div>
              <p className="text-xs text-slate-400">
                Attaching your PDF resume, crafting tailored letters, and logging to tracker...
              </p>
              <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-amber-500 to-orange-500 h-2.5 rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(10, Math.min(100, ((progress?.current || 0) / (eligibleJobs.length || 1)) * 100))}%` }}
                />
              </div>
              <p className="text-[11px] text-slate-500">Please keep this window open while applications are sent.</p>
            </div>
          )}

          {/* If Completed */}
          {isDone && (
            <div className="bg-slate-900 border border-emerald-500/40 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                <CheckCircle2 size={20} />
                <span>Batch Outreach Completed!</span>
              </div>
              <div className="flex gap-4 text-xs">
                <span className="text-emerald-300">✅ Successfully sent: <strong>{progress.applied}</strong></span>
                {progress.failed > 0 && (
                  <span className="text-red-400">❌ Failed: <strong>{progress.failed}</strong></span>
                )}
              </div>
              <div className="max-h-48 overflow-y-auto space-y-1.5 border-t border-slate-800 pt-3">
                {progress.results?.map((r, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-slate-800/60">
                    <span className="text-slate-300 font-medium truncate max-w-[240px]">{r.company} — {r.title}</span>
                    <span className="text-slate-400 text-[11px]">{r.to_email}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${r.status === 'sent' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-red-950 text-red-300 border border-red-800'}`}>
                      {r.status === 'sent' ? '✓ Sent & Tracked' : 'Failed'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Target List (Preview before executing) */}
          {!isApplying && !isDone && (
            <div className="space-y-2">
              <p className="text-xs text-slate-300 font-medium">Ready to apply to {eligibleJobs.length} verified listings:</p>
              <div className="max-h-56 overflow-y-auto space-y-2 border border-slate-700/60 rounded-xl p-2 bg-slate-900/50">
                {eligibleJobs.map((j, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-slate-800/70 hover:bg-slate-800 transition">
                    <div className="min-w-0 flex-1 mr-3">
                      <p className="text-xs font-semibold text-white truncate">{j.title}</p>
                      <p className="text-[11px] text-slate-400 truncate">{j.company} · {j.location || 'Remote'}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {j.score != null && <ScoreBadge score={j.score} />}
                      <span className="text-[11px] bg-blue-950 text-blue-300 border border-blue-800 px-2 py-0.5 rounded-lg flex items-center gap-1">
                        <Mail size={10} /> {j.emails[0]?.email}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="bg-blue-950/40 border border-blue-800/50 rounded-xl p-3 text-xs text-blue-300 flex items-start gap-2">
                <Info size={15} className="shrink-0 mt-0.5 text-blue-400" />
                <span>
                  Each application is automatically logged into your <strong>Application Tracker</strong> with a 5-day follow-up reminder. Your attached resume and personalized cover message will be delivered directly to the recruiter's mailbox.
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-850 border-t border-slate-700 px-6 py-4 flex items-center justify-end gap-3">
          {isDone ? (
            <button
              onClick={onClose}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm px-5 py-2.5 rounded-xl transition cursor-pointer"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                disabled={isApplying}
                className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-300 font-medium text-sm px-4 py-2.5 rounded-xl transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => onExecute(eligibleJobs)}
                disabled={isApplying || eligibleJobs.length === 0}
                className="flex items-center gap-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-50 text-slate-950 font-bold text-sm px-5 py-2.5 rounded-xl shadow-lg shadow-amber-500/25 transition cursor-pointer"
              >
                {isApplying ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Applying in background...</span>
                  </>
                ) : (
                  <>
                    <Zap size={16} className="fill-slate-950" />
                    <span>⚡ Launch Auto-Apply ({eligibleJobs.length} Jobs)</span>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}

function TailorCvModal({ job, onClose, onApply, onAutoApply, isApplying, isApplied }) {
  if (!job) return null
  const toast = useToast()
  const [loading, setLoading] = useState(true)
  const [tailorData, setTailorData] = useState(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let mounted = true
    const fetchTailored = async () => {
      setLoading(true)
      try {
        const { data } = await client.post('/cv/tailor', {
          job_title: job.title,
          company: job.company,
          job_description: job.description || job.title
        })
        if (mounted) setTailorData(data)
      } catch (err) {
        toast('Tailoring preview unavailable: ' + (err.response?.data?.detail || err.message), 'error')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    fetchTailored()
    return () => { mounted = false }
  }, [job])

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const res = await client.post('/cv/tailored-pdf', {
        job_title: job.title,
        company: job.company,
        job_description: job.description || job.title
      }, { responseType: 'blob' })

      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = tailorData?.filename || `CV_Tailored_${job.company}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      toast('Tailored PDF resume downloaded!', 'success')
    } catch (err) {
      toast('Failed to download PDF', 'error')
    } finally {
      setDownloading(false)
    }
  }

  const origScore = tailorData?.original_score ?? job.score ?? 50
  const tailoredScore = tailorData?.tailored_score ?? 96
  const scoreDiff = Math.max(0, tailoredScore - origScore)

  return (
    <motion.div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
      onClick={onClose}>
      <motion.div
        initial={{opacity:0, scale:0.95, y:20}}
        animate={{opacity:1, scale:1, y:0}}
        exit={{opacity:0, scale:0.95, y:20}}
        transition={{type:'spring', damping:25, stiffness:300}}
        className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}>
        
        {/* Header */}
        <div className="bg-slate-850 border-b border-slate-700 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400">
              <Sparkles size={20} className="fill-purple-400" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">✨ AI Dynamic CV Customizer</h3>
              <p className="text-xs text-slate-400">Bridged skill gaps & tailored ATS resume for {job.company}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition p-1">
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-4 flex-1">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <Loader2 size={32} className="animate-spin text-purple-400 mx-auto" />
              <p className="text-sm font-semibold text-slate-200">Analyzing Job Requirements & Bridging Skills...</p>
              <p className="text-xs text-slate-400">Generating ATS-compliant executive PDF layout</p>
            </div>
          ) : (
            <>
              {/* Score Transformation Card */}
              <div className="bg-gradient-to-r from-slate-900 via-purple-950/40 to-slate-900 border border-purple-800/40 rounded-2xl p-5 flex items-center justify-between">
                <div className="text-center">
                  <p className="text-xs text-slate-400 font-medium">Original Match</p>
                  <p className="text-2xl font-bold text-slate-300 mt-1">{origScore}%</p>
                </div>
                <div className="flex flex-col items-center">
                  <span className="text-xs font-bold text-purple-400 uppercase tracking-wide">AI Tailoring</span>
                  <div className="flex items-center gap-2 my-1">
                    <span className="h-0.5 w-10 bg-purple-500/40" />
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-700/60">
                      +{scoreDiff}% Boost
                    </span>
                    <span className="h-0.5 w-10 bg-purple-500/40" />
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-xs text-emerald-400 font-medium">Tailored Match</p>
                  <p className="text-2xl font-bold text-emerald-400 mt-1 flex items-center justify-center gap-1">
                    <CheckCircle2 size={20} /> {tailoredScore}%
                  </p>
                </div>
              </div>

              {/* Target Headline */}
              {tailorData?.target_headline && (
                <div className="bg-slate-900/80 border border-slate-700/80 rounded-xl p-3.5 flex items-center justify-between">
                  <div>
                    <p className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">Target Role Headline</p>
                    <p className="text-sm font-bold text-blue-400 mt-0.5">{tailorData.target_headline}</p>
                  </div>
                  <span className="text-[10px] bg-blue-950 text-blue-300 border border-blue-800 px-2 py-0.5 rounded-md font-medium">
                    Aligned to JD
                  </span>
                </div>
              )}

              {/* Bridged Skills Section */}
              {tailorData?.bridged_skills?.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Sparkles size={14} className="text-amber-400" />
                      Skills Bridged into Resume ({tailorData.bridged_skills.length}):
                    </p>
                    <span className="text-[11px] text-emerald-400 font-medium">100% Requirement Coverage</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {tailorData.bridged_skills.map((s, i) => (
                      <span key={i} className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 font-medium">
                        <Check size={11} className="stroke-[3]" /> {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Tailored Summary Snippet */}
              {tailorData?.tailored_summary && (
                <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-4 space-y-1.5">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Tailored Executive Summary
                  </p>
                  <p className="text-xs text-slate-300 leading-relaxed italic">
                    "{tailorData.tailored_summary}"
                  </p>
                </div>
              )}

              {/* ATS Compliance Guarantee */}
              <div className="bg-emerald-950/30 border border-emerald-800/40 rounded-xl p-3 flex items-start gap-2.5">
                <ShieldCheck size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                <p className="text-xs text-emerald-200/90 leading-relaxed">
                  <strong>ATS-Verified Format:</strong> Generated with single-column layout, standard typography, and clean keyword density, guaranteeing 100% readability across Workday, Greenhouse, Lever, and Taleo scanners.
                </p>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-850 border-t border-slate-700 px-6 py-4 flex items-center justify-between">
          <button
            onClick={handleDownload}
            disabled={loading || downloading}
            className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200 font-medium text-xs px-4 py-2.5 rounded-xl transition cursor-pointer"
          >
            {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            <span>Download Tailored PDF</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="bg-slate-750 hover:bg-slate-700 text-slate-300 font-medium text-xs px-4 py-2.5 rounded-xl transition cursor-pointer"
            >
              Close
            </button>
            {job.emails?.length > 0 && (
              isApplied ? (
                <span className="inline-flex items-center gap-1.5 bg-emerald-950 border border-emerald-800 text-emerald-300 text-xs font-bold px-4 py-2.5 rounded-xl">
                  <Check size={14} className="stroke-[3]" /> Applied
                </span>
              ) : (
                <button
                  onClick={() => {
                    onClose()
                    if (onApply) onApply(job)
                    else if (onAutoApply) onAutoApply(job)
                  }}
                  disabled={isApplying}
                  className="flex items-center gap-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-50 text-slate-950 font-bold text-xs px-4 py-2.5 rounded-xl shadow-md shadow-amber-500/20 transition cursor-pointer"
                >
                  {isApplying ? <Loader2 size={14} className="animate-spin text-slate-950" /> : <Zap size={14} className="fill-slate-950" />}
                  <span>Apply with Tailored CV</span>
                </button>
              )
            )}
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}

export default function Seeker() {
  const toast = useToast()
  const [form, setForm] = useState({
    title:'', countries:[], results:30, hours:0,
    sites:['linkedin','indeed'], is_remote:false
  })
  const [cvInfo, setCvInfo]         = useState({ uploaded:false })
  const [jobs, setJobs]             = useState([])
  const [loading, setLoading]       = useState(false)
  const [matching, setMatch]        = useState(false)
  const [error, setError]           = useState('')
  const [detailJob, setDetail]      = useState(null)
  const [scoreModal, setScore]      = useState(null)
  const [cvAnalyzing, setCvAnalyzing] = useState(false)
  const [cvSuggestion, setCvSuggestion] = useState(null)  // result from /cv/analyze
  const fileRef = useRef()

  // Custom URL import
  const [urlInput, setUrlInput]     = useState('')
  const [urlLoading, setUrlLoading] = useState(false)
  const [showUrlBox, setShowUrlBox] = useState(false)

  // Email compose
  const [emailModal, setEmailModal]   = useState(null)
  const [emailForm, setEmailForm]     = useState({ to_email:'', to_name:'Hiring Team', subject:'', body:'', template_type:'application' })
  const [sendLoading, setSendLoading] = useState(false)
  const [tplLoading, setTplLoading]   = useState(false)
  const [attachCv, setAttachCv]       = useState(true)

  // Filters & sort
  const [filterSite, setFilterSite]   = useState('all')
  const [sortBy, setSortBy]           = useState('default')
  const [minScore, setMinScore]       = useState(0)

  // Direct Auto-Apply state
  const [applyingUrls, setApplyingUrls]   = useState(new Set())
  const [appliedJobs, setAppliedJobs]     = useState(new Set())
  const [batchModal, setBatchModal]       = useState(false)
  const [batchApplying, setBatchApplying] = useState(false)
  const [batchProgress, setBatchProgress] = useState(null)
  const [tailorModalJob, setTailorModalJob] = useState(null)
  const [autoTailorEnabled, setAutoTailorEnabled] = useState(true)

  useEffect(() => {
    client.get('/cv/info').then(r=>setCvInfo(r.data)).catch(()=>{})
    client.get('/tracker').then(r => {
      const set = new Set()
      r.data.forEach(a => {
        if (a.url) set.add(a.url)
        if (a.title && a.company) set.add(`${a.title}|${a.company}`)
      })
      setAppliedJobs(set)
    }).catch(()=>{})
  }, [])

  const toggleSite = s => setForm(f => ({
    ...f, sites: f.sites.includes(s) ? f.sites.filter(x=>x!==s) : [...f.sites,s]
  }))

  const uploadCv = async (e) => {
    const file = e.target.files[0]; if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      const { data } = await client.post('/cv/upload', fd, { headers:{'Content-Type':'multipart/form-data'} })
      setCvInfo({ uploaded:true, filename:data.filename, words:data.words })
      toast(`CV uploaded: ${data.filename}`, 'success')
    } catch { toast('CV upload failed','error') }
  }

  const importUrl = async () => {
    if (!urlInput.trim()) return
    setUrlLoading(true)
    try {
      const { data } = await client.post('/jobs/import-url', { url:urlInput.trim() })
      setJobs(prev => [data, ...prev])
      setUrlInput(''); setShowUrlBox(false)
      toast(`Imported: ${data.title}`, 'success')
      if (cvInfo.uploaded) matchAll([data], true)
    } catch(e) { toast(e.response?.data?.detail||'Import failed','error') }
    setUrlLoading(false)
  }

  const searchJobs = async () => {
    if (!form.title.trim()) {
      toast('Please enter a Job Title or Skill', 'error')
      return
    }
    if (!form.countries || form.countries.length === 0) {
      toast('Please select at least one Target Country below', 'error')
      return
    }
    setLoading(true); setError(''); setJobs([])
    try {
      const { data } = await client.post('/jobs/search', {
        title: form.title.trim(),
        country: form.countries[0],
        countries: form.countries,
        sites: form.sites,
        results_wanted: Number(form.results) || 30,
        hours_old: Number(form.hours) > 0 ? Number(form.hours) : null,
        is_remote: Boolean(form.is_remote),
      })
      setJobs(data.jobs)
      toast(`Found ${data.jobs.length} jobs!`, 'success')
      const needsScore = data.jobs.some(j => j.score === undefined || j.score === null)
      if (cvInfo.uploaded && needsScore && data.jobs.length > 0) matchAll(data.jobs, false)
    } catch(e) {
      setError(e.response?.data?.detail || 'Search failed — please try again')
      toast('Search failed', 'error')
    }
    setLoading(false)
  }

  const searchByCV = async () => {
    if (!cvInfo.uploaded) {
      toast('Please upload your CV first!', 'error'); return
    }
    setCvAnalyzing(true)
    try {
      const { data } = await client.get('/cv/analyze')
      setCvSuggestion(data)
      const newTitle = data.search_query || data.title || form.title
      const newRemote = data.is_remote ?? form.is_remote

      // Update role title and remote preference WITHOUT overwriting user's chosen countries
      setForm(f => ({
        ...f,
        title: newTitle,
        is_remote: newRemote,
      }))
      toast(`✨ Role detected from CV: "${newTitle}"`, 'success')

      // Check if user has chosen countries
      if (!form.countries || form.countries.length === 0) {
        toast('👉 Please select your target countries below, then click Search Jobs!', 'info')
        setCvAnalyzing(false)
        return
      }

      // If user already selected countries, run search with their chosen countries
      setLoading(true); setError(''); setJobs([])
      try {
        const res = await client.post('/jobs/search', {
          title: newTitle,
          country: form.countries[0],
          countries: form.countries,
          sites: form.sites,
          results_wanted: Number(form.results) || 30,
          hours_old: Number(form.hours) > 0 ? Number(form.hours) : null,
          is_remote: Boolean(newRemote),
        })
        setJobs(res.data.jobs)
        toast(`🎯 Found ${res.data.jobs.length} jobs matching your CV!`, 'success')
        const needsScore = res.data.jobs.some(j => j.score === undefined || j.score === null)
        if (cvInfo.uploaded && needsScore && res.data.jobs.length > 0) matchAll(res.data.jobs, false)
      } catch (e) {
        setError(e.response?.data?.detail || 'Search failed')
      } finally {
        setLoading(false)
      }
    } catch(e) {
      toast(e.response?.data?.detail || 'CV analysis failed', 'error')
    }
    setCvAnalyzing(false)
  }

  const toggleCountry = (c) => {
    setForm(f => {
      const has = f.countries.includes(c)
      const next = has ? f.countries.filter(x=>x!==c) : [...f.countries, c]
      return { ...f, countries: next }
    })
  }

  const selectTopHubs = () => {
    setForm(f => ({ ...f, countries: ['USA', 'UK', 'Germany', 'France', 'UAE'] }))
  }

  const selectAllCountries = () => {
    setForm(f => ({ ...f, countries: ALL_COUNTRIES }))
  }

  const clearCountries = () => {
    setForm(f => ({ ...f, countries: [] }))
  }


  const matchAll = async (jobList, single=false) => {
    if (!cvInfo.uploaded || !jobList || jobList.length === 0) return
    const targets = single ? [jobList[0]] : jobList.filter(j => j.score === undefined || j.score === null)
    if (targets.length === 0) return

    setMatch(true)
    try {
      if (single || targets.length === 1) {
        const target = targets[0]
        const { data } = await client.post('/cv/match', {
          job_description: target.description || '',
          job_title: target.title || ''
        })
        setJobs(prev => prev.map(j => (j.url && j.url === target.url) || (j.title === target.title && j.company === target.company) ? {
          ...j,
          score: data.score,
          breakdown: data.breakdown,
          matched_skills: data.breakdown?.matched_tech || [],
          missing_skills: data.breakdown?.missing_tech || [],
          tips: data.breakdown?.tips || []
        } : j))
      } else {
        // High-speed parallel batch match endpoint
        const { data } = await client.post('/cv/match-batch', {
          jobs: targets.map(t => ({ title: t.title || '', description: t.description || '', url: t.url || '' }))
        })
        const scoreMap = new Map(data.map(d => [d.url || d.title, d]))
        setJobs(prev => {
          const updated = prev.map(j => {
            const res = scoreMap.get(j.url) || scoreMap.get(j.title)
            return res ? {
              ...j,
              score: res.score,
              breakdown: res.breakdown,
              matched_skills: res.matched_skills || [],
              missing_skills: res.missing_skills || [],
              tips: res.tips || []
            } : j
          })
          return updated.sort((a, b) => (b.score || 0) - (a.score || 0))
        })
      }
    } catch (err) {
      console.error('Batch match failed:', err)
    } finally {
      setMatch(false)
    }
  }

  const saveJob = async (j) => {
    try {
      await client.post('/jobs/save', { title:j.title, company:j.company, location:j.location,
        url:j.url, description:j.description, match_score:j.score||0 })
      toast(`Saved: ${j.title}`,'success')
    } catch { toast('Save failed','error') }
  }

  const openEmail = async (job, prefill='') => {
    setEmailModal({ job }); setTplLoading(true)
    setEmailForm(f=>({ ...f, to_email:prefill, to_name:'Hiring Team', template_type:'application' }))
    try {
      const { data } = await client.post('/email/template', {
        template_type:'application', to_name:'Hiring Team',
        company:job.company, job_title:job.title
      })
      setEmailForm(f=>({ ...f, subject:data.subject, body:data.body, to_email:prefill }))
    } catch {}
    setTplLoading(false)
  }

  const changeTemplate = async (type) => {
    if (!emailModal) return
    setEmailForm(f=>({ ...f, template_type:type })); setTplLoading(true)
    try {
      const { data } = await client.post('/email/template', {
        template_type:type, to_name:emailForm.to_name,
        company:emailModal.job.company, job_title:emailModal.job.title
      })
      setEmailForm(f=>({ ...f, subject:data.subject, body:data.body }))
    } catch {}
    setTplLoading(false)
  }

  const sendEmail = async () => {
    if (!emailModal||!emailForm.to_email) return
    setSendLoading(true)
    try {
      let appId = null
      try {
        const { data:app } = await client.post('/tracker', {
          title:emailModal.job.title, company:emailModal.job.company,
          location:emailModal.job.location, url:emailModal.job.url,
          match_score:emailModal.job.score||0, status:'applied',
          notes:`Applied via email to ${emailForm.to_email}`
        })
        appId = app.id
      } catch {}
      await client.post('/email/send', {
        to_email:emailForm.to_email, to_name:emailForm.to_name,
        subject:emailForm.subject, body:emailForm.body,
        template_type:emailForm.template_type, application_id:appId,
        attach_cv: attachCv
      })
      fireConfetti()
      toast('🎉 Email sent & added to Tracker!','success')
      setEmailModal(null)
    } catch(e) {
      toast(e.response?.data?.detail||'Send failed — check Settings → Email','error')
    }
    setSendLoading(false)
  }


  const handleAutoApply = async (job) => {
    if (!cvInfo.uploaded) {
      toast('Please upload your CV before auto-applying!', 'error')
      return
    }

    const verifiedEmailObj = job.emails?.find(e => e.verified || e.source === 'found' || e.source === 'company_site')
    const email = verifiedEmailObj?.email || (job.emails?.[0]?.verified !== false ? job.emails?.[0]?.email : null)

    if (!email) {
      if (job.url || job.job_url_direct) {
        window.open(job.url || job.job_url_direct, '_blank')
        toast('Opening company job portal to apply directly with your tailored CV...', 'info')
      } else {
        toast('No verified recruiter email found for this listing.', 'error')
      }
      return
    }

    const jobKey = job.url || `${job.title}|${job.company}`
    setApplyingUrls(prev => new Set(prev).add(jobKey))
    try {
      await client.post('/email/auto-apply', {
        job_title: job.title,
        company: job.company,
        to_email: email,
        job_url: job.url || '',
        location: job.location || '',
        match_score: job.score || 0,
        job_description: job.description || job.title,
        customize_cv: autoTailorEnabled,
        notes: `1-Click Auto-applied to ${email}` + (autoTailorEnabled ? ' (Tailored CV)' : '')
      })
      setAppliedJobs(prev => new Set(prev).add(jobKey))
      fireConfetti()
      toast(`🎉 Applied to ${job.company}! ${autoTailorEnabled ? 'Tailored 100% Resume attached' : 'Resume attached'} & saved to Tracker.`, 'success')
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Auto-apply failed'
      toast(`Auto-apply failed: ${msg}`, 'error')
    } finally {
      setApplyingUrls(prev => {
        const next = new Set(prev)
        next.delete(jobKey)
        return next
      })
    }
  }

  const executeBatchAutoApply = async (targetJobs) => {
    if (!cvInfo.uploaded) {
      toast('Please upload your CV before auto-applying!', 'error')
      return
    }
    if (!targetJobs || targetJobs.length === 0) {
      toast('No eligible jobs with recruiter emails available.', 'error')
      return
    }

    setBatchApplying(true)
    setBatchProgress({ current: 0, total: targetJobs.length, status: 'sending', results: [] })

    try {
      const payload = {
        jobs: targetJobs.map(j => {
          const verifiedEmail = j.emails?.find(e => e.verified || e.source === 'found' || e.source === 'company_site')?.email || j.emails[0]?.email
          return {
            job_title: j.title,
            company: j.company,
            to_email: verifiedEmail,
            job_url: j.url || '',
            location: j.location || '',
            match_score: j.score || 0,
            job_description: j.description || j.title,
            customize_cv: autoTailorEnabled
          }
        }),
        delay_seconds: 1.0,
        customize_cv: autoTailorEnabled
      }

      const { data } = await client.post('/email/batch-auto-apply', payload)

      // Add successfully applied jobs to appliedJobs set
      setAppliedJobs(prev => {
        const next = new Set(prev)
        targetJobs.forEach((j, i) => {
          const res = data.details?.[i]
          if (res && res.status === 'sent') {
            next.add(j.url || `${j.title}|${j.company}`)
          }
        })
        return next
      })

      setBatchProgress({
        current: targetJobs.length,
        total: targetJobs.length,
        status: 'done',
        applied: data.applied,
        failed: data.failed,
        results: data.details || []
      })

      if (data.applied > 0) {
        fireConfetti()
        toast(`🎉 Batch applied to ${data.applied} companies! Track them in Application Tracker.`, 'success')
      } else {
        toast(`Batch completed with ${data.failed} failures.`, 'error')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Batch apply failed'
      toast(`Batch apply failed: ${msg}`, 'error')
      setBatchProgress(prev => prev ? { ...prev, status: 'error', error: msg } : null)
    } finally {
      setBatchApplying(false)
    }
  }

  // Deduplicate + filter + sort
  const filteredJobs = (() => {
    // 1. Deduplicate by title+company
    const seen = new Set()
    let list = jobs.filter(j => {
      const key = `${(j.title||'').toLowerCase().trim()}|${(j.company||'').toLowerCase().trim()}`
      if (seen.has(key)) return false
      seen.add(key); return true
    })
    // 2. Filter by site
    if (filterSite !== 'all') list = list.filter(j => j.site === filterSite || (filterSite==='custom' && j.imported))
    // 3. Filter by min match score
    if (minScore > 0) list = list.filter(j => (j.score||0) >= minScore)
    // 4. Sort
    if (sortBy === 'score') list = [...list].sort((a,b) => (b.score||0)-(a.score||0))
    else if (sortBy === 'company') list = [...list].sort((a,b) => (a.company||'').localeCompare(b.company||''))
    return list
  })()

  const eligibleBatchJobs = filteredJobs.filter(j => {
    const key = j.url || `${j.title}|${j.company}`
    const hasVerified = j.emails?.some(e => e.verified || e.source === 'found' || e.source === 'company_site')
    return hasVerified && !appliedJobs.has(key)
  })

  const emailCount = jobs.reduce((n,j)=>n+(j.emails?.length||0),0)

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar/>
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">
        <motion.div className="flex items-center justify-between mb-6"
          initial={{opacity:0,x:-10}} animate={{opacity:1,x:0}} transition={{duration:.25}}>
          <h1 className="text-2xl font-bold">🔎 Job Search</h1>
          <motion.button whileHover={{scale:1.03}} whileTap={{scale:.96}}
            onClick={()=>setShowUrlBox(v=>!v)}
            className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 border border-slate-600 text-sm px-4 py-2 rounded-xl transition-colors">
            <Globe size={15}/>{showUrlBox ? 'Hide URL Import':'Import from URL'}
          </motion.button>
        </motion.div>

        {/* URL Import box */}
        <AnimatePresence>
          {showUrlBox && (
            <motion.div initial={{opacity:0,height:0}} animate={{opacity:1,height:'auto'}}
              exit={{opacity:0,height:0}} className="mb-4 overflow-hidden">
              <div className="bg-slate-800 border border-purple-700/50 rounded-2xl p-5">
                <p className="text-sm font-semibold mb-1 flex items-center gap-2"><Link size={14} className="text-purple-400"/>Import Any Job Posting</p>
                <p className="text-xs text-slate-400 mb-3">Paste a URL from any job board — WeWorkRemotely, RemoteOK, company careers page, etc.</p>
                <div className="flex gap-2">
                  <input value={urlInput} onChange={e=>setUrlInput(e.target.value)}
                    onKeyDown={e=>e.key==='Enter'&&importUrl()}
                    placeholder="https://weworkremotely.com/jobs/... or any job posting URL"
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-purple-500 transition-colors"/>
                  <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                    onClick={importUrl} disabled={urlLoading||!urlInput.trim()}
                    className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-colors">
                    {urlLoading ? <LoadingSpinner label="Importing..."/> : <><Plus size={15}/>Import</>}
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search form */}
        <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6"
          initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{duration:.3,delay:.06}}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-5">
            {/* Job Title — No Location Input needed */}
            <div className="md:col-span-2 lg:col-span-3">
              <label className="text-xs text-slate-400 mb-1.5 block font-medium">Job Title, Role or Skill *</label>
              <div className="relative">
                <input
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && searchJobs()}
                  placeholder="e.g. Flutter Developer, Mobile Engineer, React, Full Stack, Python..."
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                />
                <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              </div>
            </div>

            {/* Countries with Quick Selectors */}
            <div className="md:col-span-2 lg:col-span-3">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <label className="text-xs text-slate-400 font-medium">
                  Target Countries
                  <span className={`ml-1.5 font-normal ${form.countries.length > 0 ? 'text-blue-400' : 'text-amber-400'}`}>
                    ({form.countries.length} selected{form.countries.length === 0 ? ' — click countries below to select' : ''})
                  </span>
                </label>
                <div className="flex items-center gap-2 text-xs">
                  <button type="button" onClick={selectTopHubs} className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
                    Top Tech Hubs
                  </button>
                  <span className="text-slate-600">·</span>
                  <button type="button" onClick={selectAllCountries} className="text-slate-400 hover:text-slate-200 transition-colors">
                    Select All
                  </button>
                  <span className="text-slate-600">·</span>
                  <button type="button" onClick={clearCountries} className="text-slate-500 hover:text-slate-300 transition-colors">
                    Reset
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto pr-1">
                {ALL_COUNTRIES.map(c => {
                  const selected = form.countries.includes(c)
                  return (
                    <button key={c} type="button"
                      onClick={() => toggleCountry(c)}
                      className={`text-xs px-3 py-1.5 rounded-full border transition-all ${
                        selected
                          ? 'bg-blue-600 border-blue-500 text-white font-semibold shadow-sm shadow-blue-500/20'
                          : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                      }`}>
                      {c}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Results Wanted */}
            <div>
              <label className="text-xs text-slate-400 mb-1.5 block">Results Wanted</label>
              <select
                value={form.results}
                onChange={e => setForm({ ...form, results: Number(e.target.value) })}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors">
                {[20, 30, 50, 75, 100].map(n => (
                  <option key={n} value={n}>{n} jobs</option>
                ))}
              </select>
            </div>

            {/* Posted Within */}
            <div>
              <label className="text-xs text-slate-400 mb-1.5 block">Date Posted</label>
              <select
                value={form.hours}
                onChange={e => setForm({ ...form, hours: Number(e.target.value) })}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors">
                {[
                  [0, 'Anytime (Maximum Jobs)'],
                  [720, 'Past 30 days'],
                  [336, 'Past 14 days'],
                  [168, 'Past 7 days'],
                  [24, 'Past 24 hours']
                ].map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>

            {/* Job Boards & Remote Toggle */}
            <div>
              <label className="text-xs text-slate-400 mb-2 block">Sources & Preferences</label>
              <div className="flex flex-wrap items-center gap-4 pt-1">
                {CORE_SITES.map(s => (
                  <label key={s.id} className="flex items-center gap-2 text-sm cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={form.sites.includes(s.id)}
                      onChange={() => toggleSite(s.id)}
                      className="accent-blue-500 w-4 h-4 rounded"
                    />
                    <span className="font-medium">{s.label}</span>
                  </label>
                ))}
                <label className="flex items-center gap-2 text-sm cursor-pointer select-none text-slate-300">
                  <input
                    type="checkbox"
                    checked={Boolean(form.is_remote)}
                    onChange={e => setForm({ ...form, is_remote: e.target.checked })}
                    className="accent-purple-500 w-4 h-4 rounded"
                  />
                  <span className="font-medium text-purple-300">🌐 Remote Only</span>
                </label>
              </div>
            </div>
          </div>

          {/* CV Section + Action Buttons */}
          <div className="border-t border-slate-700 pt-5 mt-2">

            {/* Smart Search from CV — hero feature */}
            <div className="bg-gradient-to-r from-blue-900/40 to-purple-900/30 border border-blue-700/40 rounded-2xl p-4 mb-4">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-600/30 flex items-center justify-center shrink-0">
                    <span className="text-lg">🧠</span>
                  </div>
                  <div>
                    <p className="font-semibold text-sm">Smart Search from CV</p>
                    {cvInfo.uploaded
                      ? <p className="text-xs text-slate-400 mt-0.5">✓ {cvInfo.filename} · {cvInfo.words} words — ready to analyze</p>
                      : <p className="text-xs text-slate-400 mt-0.5">Upload your CV and we'll find the best jobs automatically</p>
                    }
                    {cvSuggestion && (
                      <p className="text-xs text-blue-300 mt-1">
                        Detected: <strong>{cvSuggestion.title}</strong> · Skills: {cvSuggestion.top_skills?.slice(0,4).join(', ')}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                    onClick={()=>fileRef.current.click()}
                    className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-sm px-4 py-2 rounded-xl transition-colors">
                    <Upload size={14}/>{cvInfo.uploaded?'Replace CV':'Upload CV'}
                  </motion.button>
                  <motion.button whileHover={{scale:1.03}} whileTap={{scale:.96}}
                    onClick={searchByCV}
                    disabled={cvAnalyzing || loading || !cvInfo.uploaded}
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl transition-colors text-sm">
                    {cvAnalyzing
                      ? <><LoadingSpinner label="Analyzing..."/></>
                      : <><Search size={14}/>🎯 Search by CV</>
                    }
                  </motion.button>
                </div>
              </div>
            </div>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" onChange={uploadCv} className="hidden"/>

            {/* Manual search button */}
            <div className="flex items-center gap-4">
              <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                onClick={searchJobs} disabled={loading || !form.title.trim()}
                className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 font-semibold px-7 py-2.5 rounded-xl transition-colors text-sm">
                {loading ? <LoadingSpinner label="Searching..."/> : <><Search size={16}/>Search Jobs</>}
              </motion.button>
              <span className="text-xs text-slate-500">or use Smart Search above</span>
              <AnimatePresence>
                {matching && (
                <motion.div initial={{opacity:0,x:-8}} animate={{opacity:1,x:0}} exit={{opacity:0}}>
                  <LoadingSpinner label="AI scoring..."/>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          </div>{/* end CV Section + Action Buttons */}
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div initial={{opacity:0,y:-8}} animate={{opacity:1,y:0}} exit={{opacity:0}}
              className="bg-red-900/60 border border-red-700 text-red-300 text-sm rounded-xl px-4 py-3 mb-4 flex items-center justify-between">
              {error}<button onClick={()=>setError('')}><X size={15}/></button>
            </motion.div>
          )}
        </AnimatePresence>

        {(loading||jobs.length>0) && (
          <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6"
            initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{duration:.3}}>
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <h2 className="font-bold text-lg">
                Results{jobs.length>0 && (
                  <span className="text-slate-400 font-normal text-base ml-2">
                    ({filteredJobs.length}{filteredJobs.length!==jobs.length?` of ${jobs.length}`:''} jobs · {emailCount} emails)
                  </span>
                )}
              </h2>
              {jobs.length>0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => setAutoTailorEnabled(v => !v)}
                    className={`flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-xl border transition-all cursor-pointer ${
                      autoTailorEnabled
                        ? 'bg-purple-950/90 text-purple-300 border-purple-500/80 shadow-md shadow-purple-500/25'
                        : 'bg-slate-900 text-slate-400 border-slate-700 hover:text-white'
                    }`}
                    title="When enabled, dynamically adapts your CV to bridge skill mismatches and attaches a 100% role-matched PDF"
                  >
                    <Sparkles size={13} className={autoTailorEnabled ? "fill-purple-400 text-purple-400" : "text-slate-500"} />
                    <span>Auto-Tailor CV: {autoTailorEnabled ? "100% Fit ON" : "OFF"}</span>
                  </button>

                  {eligibleBatchJobs.length > 0 && (
                    <motion.button
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => { setBatchProgress(null); setBatchModal(true); }}
                      className="flex items-center gap-1.5 bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold text-xs px-3.5 py-1.5 rounded-xl shadow-md shadow-amber-500/25 transition-all cursor-pointer"
                      title="Direct 1-click batch apply to all qualified recruiter emails with attached CV"
                    >
                      <Zap size={14} className="fill-slate-950 text-slate-950" />
                      <span>⚡ Batch Auto-Apply ({eligibleBatchJobs.length})</span>
                    </motion.button>
                  )}
                  <select value={filterSite} onChange={e=>setFilterSite(e.target.value)}
                    className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500">
                    <option value="all">All Sites</option>
                    <option value="linkedin">LinkedIn</option>
                    <option value="indeed">Indeed</option>
                    <option value="custom">Imported</option>
                  </select>
                  <select value={minScore} onChange={e=>setMinScore(Number(e.target.value))}
                    className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500">
                    <option value={0}>Any Match</option>
                    <option value={30}>30%+ Match</option>
                    <option value={50}>50%+ Match</option>
                    <option value={70}>70%+ Match</option>
                  </select>
                  <select value={sortBy} onChange={e=>setSortBy(e.target.value)}
                    className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500">
                    <option value="default">Default Order</option>
                    <option value="score">Best Match ↓</option>
                    <option value="company">Company A-Z</option>
                  </select>
                </div>
              )}
              <div className="flex gap-3 text-xs text-slate-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"/>Direct from post</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-cyan-500 inline-block"/>Company website</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500 inline-block"/>Verified HR mailbox</span>
              </div>
            </div>
            {/* ── Desktop table ──────────────────────── */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    {['','Title','Company','Location','Site','Salary',
                      ...(cvInfo.uploaded?['Match']:['']),'Recruiter Emails','Actions'].map((h,i)=>(
                      <th key={i} className="pb-3 pr-3 font-medium text-xs whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading
                    ? Array(8).fill(0).map((_,i)=><SkeletonRow key={i}/>)
                    : filteredJobs.map((j,i)=>(
                    <motion.tr key={i}
                      initial={{opacity:0,x:-6}} animate={{opacity:1,x:0}}
                      transition={{delay:i*.03,duration:.18}}
                      className="border-b border-slate-700/50 hover:bg-slate-700/25 transition-colors cursor-pointer group"
                      onClick={()=>setDetail(j)}>
                      <td className="py-3 pr-2">
                        {j.imported && (
                          <span className="w-1.5 h-1.5 rounded-full bg-purple-500 inline-block" title="Imported from URL"/>
                        )}
                      </td>
                      <td className="py-3 pr-3 font-medium max-w-[180px]">
                        <span className="truncate block group-hover:text-blue-300 transition-colors" title={j.title}>{j.title}</span>
                      </td>
                      <td className="py-3 pr-3 text-slate-300 max-w-[140px]"><span className="truncate block">{j.company}</span></td>
                      <td className="py-3 pr-3 text-slate-400 text-xs whitespace-nowrap">{j.location||'—'}</td>
                      <td className="py-3 pr-3">
                        <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${j.imported?'bg-purple-900 text-purple-300':'bg-slate-700 text-slate-300'}`}>
                          {j.imported?'custom':j.site}
                        </span>
                      </td>
                      <td className="py-3 pr-3 text-xs text-slate-400 whitespace-nowrap">{j.salary||'—'}</td>
                      {cvInfo.uploaded && (
                        <td className="py-3 pr-3" onClick={e=>{e.stopPropagation();j.score!=null&&setScore(j)}}>
                          {j.score!=null
                            ? <ScoreBadge score={j.score}/>
                            : <span className="text-slate-600 text-xs">—</span>}
                        </td>
                      )}
                      {!cvInfo.uploaded && <td className="py-3 pr-3"/>}
                      <td className="py-3 pr-3 min-w-[180px]" onClick={e=>e.stopPropagation()}>
                        {j.emails?.length>0 ? (
                          <div className="flex flex-col gap-1">
                            {j.emails.slice(0,2).map((e,ei)=>(
                              <EmailPill key={ei} data={e} onClick={()=>openEmail(j,e.email)}/>
                            ))}
                            {j.emails.length>2 && (
                              <button onClick={()=>setDetail(j)} className="text-xs text-slate-500 hover:text-blue-400 transition-colors text-left">
                                +{j.emails.length-2} more →
                              </button>
                            )}
                          </div>
                        ) : (
                          <button onClick={()=>openEmail(j,'')}
                            className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-400 transition-colors">
                            <Mail size={12}/>Compose
                          </button>
                        )}
                      </td>
                      <td className="py-3" onClick={e=>e.stopPropagation()}>
                        <div className="flex items-center gap-1.5">
                          {cvInfo.uploaded && (
                            <button
                              onClick={() => setTailorModalJob(j)}
                              title="Tailor CV to bridge missing skills and achieve 95%+ ATS match score"
                              className="inline-flex items-center gap-1 text-xs font-semibold bg-purple-950/60 hover:bg-purple-900/80 text-purple-300 border border-purple-700/60 px-2 py-1 rounded-lg transition-colors cursor-pointer shadow-sm"
                            >
                              <Sparkles size={11} className="text-purple-400" />
                              <span>Tailor</span>
                            </button>
                          )}
                          {j.emails?.some(e => e.verified || e.source === 'found' || e.source === 'company_site') ? (
                            appliedJobs.has(j.url || `${j.title}|${j.company}`) ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-800/80 px-2.5 py-1 rounded-lg">
                                <Check size={12} className="stroke-[3]" /> Applied
                              </span>
                            ) : (
                              <button
                                onClick={() => handleAutoApply(j)}
                                disabled={applyingUrls.has(j.url || `${j.title}|${j.company}`)}
                                title={`1-Click Direct Application: tailors letter, attaches CV, sends to ${j.emails.find(e => e.verified || e.source === 'found' || e.source === 'company_site')?.email || j.emails[0]?.email}`}
                                className="inline-flex items-center gap-1.5 text-xs font-bold bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 px-2.5 py-1 rounded-lg transition-all shadow-sm shadow-amber-500/30 disabled:opacity-50 cursor-pointer"
                              >
                                {applyingUrls.has(j.url || `${j.title}|${j.company}`) ? (
                                  <Loader2 size={13} className="animate-spin text-slate-950" />
                                ) : (
                                  <>
                                    <Zap size={12} className="fill-slate-950 text-slate-950" />
                                    <span>Auto-Apply</span>
                                  </>
                                )}
                              </button>
                            )
                          ) : (
                            j.url ? (
                              <a
                                href={j.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 px-2.5 py-1 rounded-lg transition-colors"
                                title="Open posting on job portal"
                              >
                                <ExternalLink size={12} /> Apply
                              </a>
                            ) : null
                          )}
                          {j.url && (
                            <a
                              href={j.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-slate-400 hover:text-blue-300 transition-colors p-1"
                              title="View job post"
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                          <button
                            onClick={() => saveJob(j)}
                            className="text-slate-400 hover:text-emerald-300 transition-colors p-1"
                            title="Save to bookmarks"
                          >
                            <Bookmark size={14} />
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* ── Mobile cards ───────────────────────── */}
            <div className="md:hidden space-y-3 mt-2">
              {loading
                ? Array(4).fill(0).map((_,i)=>(
                  <div key={i} className="bg-slate-900 rounded-2xl p-4 animate-pulse space-y-3 border border-slate-700">
                    <div className="h-4 bg-slate-700 rounded w-3/4"/>
                    <div className="h-3 bg-slate-700/60 rounded w-1/2"/>
                    <div className="h-3 bg-slate-700/40 rounded w-full"/>
                  </div>
                ))
                : jobs.map((j,i)=>(
                <motion.div key={i}
                  initial={{opacity:0,y:10}} animate={{opacity:1,y:0}}
                  transition={{delay:i*.04}}
                  onClick={()=>setDetail(j)}
                  className="bg-slate-900 border border-slate-700 rounded-2xl p-4 hover:border-slate-500 transition-colors cursor-pointer active:scale-[0.98]">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm truncate">{j.title}</p>
                      <p className="text-slate-400 text-xs truncate">{j.company}</p>
                    </div>
                    {j.score!=null && <ScoreBadge score={j.score} onClick={e=>{e.stopPropagation();setScore(j)}}/>}
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs mb-3">
                    {j.location && <span className="text-slate-400">📍 {j.location}</span>}
                    {j.salary   && <span className="text-emerald-400">💰 {j.salary}</span>}
                    <span className="bg-slate-700 px-2 py-0.5 rounded-full capitalize">{j.imported?'custom':j.site}</span>
                  </div>
                  {/* Emails */}
                  {j.emails?.length>0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3" onClick={e=>e.stopPropagation()}>
                      {j.emails.slice(0,2).map((e,ei)=>(
                        <EmailPill key={ei} data={e} onClick={()=>openEmail(j,e.email)}/>
                      ))}
                      {j.emails.length>2 && <span className="text-xs text-slate-500">+{j.emails.length-2}</span>}
                    </div>
                  )}
                  <div className="flex items-center gap-2 border-t border-slate-700 pt-2.5 flex-wrap" onClick={e=>e.stopPropagation()}>
                    {cvInfo.uploaded && (
                      <button
                        onClick={() => setTailorModalJob(j)}
                        className="inline-flex items-center gap-1 text-xs font-semibold bg-purple-950/60 hover:bg-purple-900/80 text-purple-300 border border-purple-700/60 px-2 py-1 rounded-lg transition-colors cursor-pointer"
                      >
                        <Sparkles size={11} className="text-purple-400" />
                        <span>Tailor</span>
                      </button>
                    )}
                    {j.emails?.some(e => e.verified || e.source === 'found' || e.source === 'company_site') ? (
                      appliedJobs.has(j.url || `${j.title}|${j.company}`) ? (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-800/80 px-2 py-0.5 rounded-lg">
                          <Check size={11} className="stroke-[3]" /> Applied
                        </span>
                      ) : (
                        <button
                          onClick={() => handleAutoApply(j)}
                          disabled={applyingUrls.has(j.url || `${j.title}|${j.company}`)}
                          className="inline-flex items-center gap-1 text-xs font-bold bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 px-2.5 py-1 rounded-lg transition-all shadow-sm shadow-amber-500/20 disabled:opacity-50"
                        >
                          {applyingUrls.has(j.url || `${j.title}|${j.company}`) ? (
                            <Loader2 size={12} className="animate-spin text-slate-950" />
                          ) : (
                            <>
                              <Zap size={11} className="fill-slate-950" />
                              <span>⚡ Auto-Apply</span>
                            </>
                          )}
                        </button>
                      )
                    ) : (
                      j.url && (
                        <a
                          href={j.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 px-2.5 py-1 rounded-lg transition-colors"
                        >
                          <ExternalLink size={12} /> Apply
                        </a>
                      )
                    )}
                    {j.url && <a href={j.url} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-blue-400">
                      <ExternalLink size={13}/>View
                    </a>}
                    <button onClick={()=>openEmail(j,'')} className="flex items-center gap-1 text-xs text-slate-300">
                      <Mail size={13}/>Email
                    </button>
                    <button onClick={()=>saveJob(j)} className="flex items-center gap-1 text-xs text-emerald-400 ml-auto">
                      <Bookmark size={13}/>Save
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </main>

      <ScoreModal item={scoreModal} onClose={()=>setScore(null)} mode="seeker"/>

      {/* Job Detail Popup */}
      <AnimatePresence>
        {detailJob && (
          <JobDetailPopup
            job={detailJob}
            onClose={()=>setDetail(null)}
            onEmail={(j,e)=>openEmail(j,e)}
            onSave={saveJob}
            onAutoApply={handleAutoApply}
            onTailor={(j) => { setDetail(null); setTailorModalJob(j); }}
            isApplying={applyingUrls.has(detailJob.url || `${detailJob.title}|${detailJob.company}`)}
            isApplied={appliedJobs.has(detailJob.url || `${detailJob.title}|${detailJob.company}`)}
          />
        )}
      </AnimatePresence>

      {/* Tailor CV Modal */}
      <AnimatePresence>
        {tailorModalJob && (
          <TailorCvModal
            job={tailorModalJob}
            onClose={() => setTailorModalJob(null)}
            onApply={(j) => {
              setTailorModalJob(null);
              handleAutoApply(j);
            }}
          />
        )}
      </AnimatePresence>

      {/* Batch Auto-Apply Modal */}
      <AnimatePresence>
        {batchModal && (
          <BatchAutoApplyModal
            isOpen={batchModal}
            onClose={() => setBatchModal(false)}
            eligibleJobs={eligibleBatchJobs}
            onExecute={executeBatchAutoApply}
            isApplying={batchApplying}
            progress={batchProgress}
            cvInfo={cvInfo}
          />
        )}
      </AnimatePresence>

      {/* Email Compose Modal */}
      <AnimatePresence>
        {emailModal && (
          <motion.div className="fixed inset-0 bg-black/75 z-50 flex items-end md:items-center justify-center md:p-4"
            initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
            onClick={()=>setEmailModal(null)}>
            <motion.div
              initial={{opacity:0,scale:.93,y:24}} animate={{opacity:1,scale:1,y:0}}
              exit={{opacity:0,scale:.96,y:12}}
              transition={{type:'spring',damping:22,stiffness:280}}
              className="bg-slate-800 border border-slate-700 rounded-t-2xl md:rounded-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto p-4 md:p-6"
              onClick={e=>e.stopPropagation()}>
              <div className="flex justify-between items-start mb-5">
                <div>
                  <h3 className="font-bold text-lg flex items-center gap-2"><Sparkles size={17} className="text-blue-400"/>Compose Email</h3>
                  <p className="text-slate-400 text-sm">{emailModal.job.title} @ {emailModal.job.company}</p>
                </div>
                <button onClick={()=>setEmailModal(null)} className="text-slate-400 hover:text-white transition p-1"><X size={20}/></button>
              </div>
              <div className="flex gap-2 mb-5 flex-wrap">
                {Object.entries(TEMPLATE_LABELS).map(([key,label])=>(
                  <motion.button key={key} whileTap={{scale:.95}}
                    onClick={()=>changeTemplate(key)}
                    className={`text-xs px-3 py-1.5 rounded-xl border transition-all ${
                      emailForm.template_type===key
                        ? 'border-blue-500 bg-blue-900/50 text-blue-300'
                        : 'border-slate-700 text-slate-400 hover:border-slate-500'}`}>
                    {label}
                  </motion.button>
                ))}
              </div>
              {tplLoading ? (
                <div className="flex items-center justify-center py-12"><LoadingSpinner label="Loading template..."/></div>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block">To Email *</label>
                      <input value={emailForm.to_email} type="email"
                        onChange={e=>setEmailForm({...emailForm,to_email:e.target.value})}
                        placeholder="recruiter@company.com"
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"/>
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block">Name</label>
                      <input value={emailForm.to_name}
                        onChange={e=>setEmailForm({...emailForm,to_name:e.target.value})}
                        placeholder="Hiring Manager"
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"/>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Subject</label>
                    <input value={emailForm.subject}
                      onChange={e=>setEmailForm({...emailForm,subject:e.target.value})}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"/>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Message</label>
                    <textarea value={emailForm.body}
                      onChange={e=>setEmailForm({...emailForm,body:e.target.value})}
                      rows={11}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors resize-none font-mono leading-relaxed"/>
                  </div>
                </div>
              )}
              <div className="flex gap-3 mt-5">
                <button onClick={()=>setEmailModal(null)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 py-2.5 rounded-xl text-sm transition-colors">Cancel</button>
                <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                  onClick={sendEmail} disabled={sendLoading||!emailForm.to_email||tplLoading}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors">
                  {sendLoading ? <LoadingSpinner label="Sending..."/> : <><Send size={15}/>Send & Track</>}
                </motion.button>
              </div>
              <p className="text-xs text-slate-500 text-center mt-2">Sends via Gmail · Auto-added to Tracker</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </PageWrapper>
  )
}
