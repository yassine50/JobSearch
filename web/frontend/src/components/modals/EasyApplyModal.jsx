import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import confetti from 'canvas-confetti'
import client, { getCached } from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import {
  Zap, Building2, MapPin, Check, Loader2,
  X, ShieldCheck, Sparkles, Send, ExternalLink,
  CheckCheck, FileText, Download, Puzzle
} from 'lucide-react'

export default function EasyApplyModal({
  isOpen,
  onClose,
  job,
  onSuccess
}) {
  const toast = useToast()
  const { user } = useAuth()
  const [loading, setLoading] = useState(false)
  const [pitch, setPitch] = useState('')
  const [cvFilename, setCvFilename] = useState(() => getCached('/cv/info')?.filename || '')
  const [extInstalled, setExtInstalled] = useState(
    () => typeof document !== 'undefined' && document.documentElement.getAttribute('data-cvtomatch-extension') === 'installed'
  )
  const [showExtHelp, setShowExtHelp] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    const checkInstalled = () => {
      if (document.documentElement.getAttribute('data-cvtomatch-extension') === 'installed') {
        setExtInstalled(true)
      }
    }
    checkInstalled()
    const onMsg = (e) => {
      if (e.data?.type === 'CVTOMATCH_EXTENSION_PONG') setExtInstalled(true)
    }
    window.addEventListener('message', onMsg)
    window.postMessage({ type: 'CVTOMATCH_EXTENSION_PING' }, '*')
    return () => window.removeEventListener('message', onMsg)
  }, [isOpen])

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

  useEffect(() => {
    if (job) {
      const comp = job.company || 'the team'
      const title = job.title || 'Software Opportunity'
      setPitch(
`Hello Hiring Team at ${comp},

I am excited to submit my simplified application for the ${title} position.

My background aligns closely with the technical and operational requirements of this role. I have extensive experience building scalable solutions and delivering high-impact software.

I have attached my resume for your review and look forward to discussing how I can contribute to ${comp}.

Best regards,`
      )
    }
  }, [job])

  if (!isOpen || !job) return null

  const jobUrl = job.url || job.job_url_direct || job.job_url || ''
  const isLinkedIn = (job.site || '').toLowerCase().includes('linkedin')
  const score = job.score != null ? job.score : (job.match_score != null ? job.match_score : 75)

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const { data } = await client.post('/jobs/easy-apply', {
        title: job.title,
        company: job.company,
        location: job.location,
        url: jobUrl,
        job_url_direct: job.job_url_direct || jobUrl,
        description: job.description || '',
        site: job.site || 'LinkedIn',
        match_score: score,
        customize_cv: true,
        custom_pitch: pitch,
        notes: 'Applied via Candidature Simplifiée.'
      })

      if (pitch && navigator.clipboard) {
        try { await navigator.clipboard.writeText(pitch) } catch(e) {}
      }
      window.postMessage({
        type: 'CVTOMATCH_PREPARE_EASY_APPLY',
        job: {
          title: job.title,
          company: job.company,
          location: job.location,
          url: jobUrl,
          description: job.description || '',
          custom_pitch: pitch
        }
      }, '*')
      if (jobUrl) {
        window.open(jobUrl, '_blank')
      }

      confetti({ particleCount: 120, spread: 80, origin: { y: 0.6 } })
      toast(`✅ Pitch copied & logged in Tracker! Complete the Easy Apply popup on LinkedIn.`, 'success')

      if (onSuccess) {
        onSuccess({
          ...job,
          is_applied: true,
          status: 'applied'
        })
      }
      onClose()
    } catch (err) {
      toast(err?.response?.data?.detail || err.message || 'Application failed', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-lg bg-slate-900 border border-blue-500/35 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-800 bg-slate-950/70 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center justify-center shrink-0">
              <Zap size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white tracking-tight">
                  Candidature Simplifiée
                </h3>
                <span className="bg-blue-500/15 text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded text-[10px] font-bold uppercase">
                  Easy Apply
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Auto-apply with tailored resume directly to this posting.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Job Summary Banner */}
        <div className="p-5 border-b border-slate-800/80 bg-slate-950/40 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h4 className="font-bold text-sm text-white">
                {job.title}
              </h4>
              <div className="flex items-center gap-2 text-xs text-slate-300 mt-1">
                <span className="font-semibold text-blue-300 flex items-center gap-1">
                  <Building2 size={12} className="text-blue-400" />
                  {job.company}
                </span>
                <span className="text-slate-500">•</span>
                <span className="text-slate-400 flex items-center gap-1">
                  <MapPin size={11} />
                  {job.location || 'Remote'}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold border ${
                isLinkedIn
                  ? 'bg-blue-950/80 text-blue-300 border-blue-800'
                  : 'bg-indigo-950/80 text-indigo-300 border-indigo-800'
              }`}>
                {job.site || 'LinkedIn'}
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-blue-500/15 text-blue-300 border-blue-500/30">
                {score}% CV
              </span>
            </div>
          </div>
        </div>

        {/* Form Body */}
        <div className="p-5 space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
              <span>Application Note / Cover Pitch</span>
              <span className="text-[11px] text-slate-500 font-normal">Pre-filled & editable</span>
            </label>
            <textarea
              value={pitch}
              onChange={e => setPitch(e.target.value)}
              rows={5}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 focus:outline-none focus:border-blue-500 resize-none font-sans leading-relaxed"
            />
          </div>

          <div className="flex items-center gap-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800">
            <div className="p-2 rounded-lg bg-blue-500/15 text-blue-300 border border-blue-500/30 shrink-0">
              <FileText size={16} />
            </div>
            <div className="text-xs min-w-0">
              <span className="font-semibold text-white flex items-center gap-2 flex-wrap">
                <span>Authentic Verified Resume</span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-blue-500/15 border border-blue-500/30 text-blue-300 truncate max-w-[180px]">
                  {displayCvName}
                </span>
              </span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                A copy of your resume tailored to this job (missing skills added, off-topic content removed) is saved on the Tracker card. Download it there to upload on the job site. Your original CV is never changed.
              </p>
            </div>
          </div>

          {/* Chrome Extension 1-Click Autofill Banner */}
          <div className="p-3 rounded-xl bg-slate-850 border border-blue-500/30 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="p-2 rounded-lg bg-blue-500/15 text-blue-300 border border-blue-500/30 shrink-0">
                  <Puzzle size={15} />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <span>1-Click Chrome Autofill Extension</span>
                    {extInstalled && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-blue-500/15 border border-blue-500/30 text-blue-300">
                        Active
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {extInstalled
                      ? 'Extension synced! Click the floating "⚡ 1-Click Autofill" button once the job page opens.'
                      : 'Automatically fills forms, screening answers & attaches your tailored PDF on Workday, Greenhouse, Lever & LinkedIn.'}
                  </p>
                </div>
              </div>
              {!extInstalled && (
                <div className="flex items-center gap-1.5 shrink-0">
                  <a
                    href="/api/extension/download.zip"
                    download="CVtoMatch-Autofill-Extension.zip"
                    onClick={() => setShowExtHelp(true)}
                    className="px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-semibold flex items-center gap-1 transition"
                  >
                    <Download size={12} />
                    <span>Get Extension</span>
                  </a>
                </div>
              )}
            </div>
            {showExtHelp && !extInstalled && (
              <div className="text-[11px] text-slate-300 bg-slate-900 border border-slate-700/70 rounded-lg p-2.5 space-y-1">
                <p className="font-semibold text-white">Install in 20 seconds:</p>
                <ol className="list-decimal list-inside space-y-0.5 text-slate-400">
                  <li>Unzip <code className="text-blue-300">CVtoMatch-Autofill-Extension.zip</code></li>
                  <li>Open <code className="text-blue-300">chrome://extensions</code> in Chrome and enable <b>Developer mode</b> (top-right)</li>
                  <li>Click <b>Load unpacked</b> and select the unzipped folder — your session syncs automatically!</li>
                </ol>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between gap-3">
          {jobUrl ? (
            <a
              href={jobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium transition"
            >
              <span>Open on {job.site || 'Portal'}</span>
              <ExternalLink size={11} />
            </a>
          ) : <div />}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs shadow-md shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Submitting...</span>
                </>
              ) : (
                <>
                  <Zap size={14} className="fill-white" />
                  <span>Open on LinkedIn & Log in Tracker</span>
                </>
              )}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
