import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import confetti from 'canvas-confetti'
import client, { getCached } from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import {
  Zap, Building2, MapPin, Check, Loader2,
  X, ShieldCheck, Sparkles, CheckSquare, Square, CheckCheck,
  ExternalLink, ArrowRight, FileText
} from 'lucide-react'

export default function BatchEasyApplyModal({
  isOpen,
  onClose,
  items = [],
  jobs = [],
  onSuccess
}) {
  const toast = useToast()
  const { user } = useAuth()
  const [selectedIds, setSelectedIds] = useState([])
  const [applying, setApplying] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0, currentTarget: '' })
  const [completed, setCompleted] = useState(false)
  const [appliedResults, setAppliedResults] = useState([])
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

  const rawList = items && items.length > 0 ? items : (jobs || [])

  // Normalize items
  const candidateItems = rawList.map((job, idx) => ({
    raw: job,
    id: job.id || job.url || `job-${idx}`,
    title: job.title || 'Open Position',
    company: job.company || 'Hiring Company',
    location: job.location || 'Remote',
    site: job.site || 'LinkedIn',
    score: job.score != null ? job.score : (job.match_score != null ? job.match_score : 75),
    url: job.url || job.job_url_direct || job.job_url || '',
    description: job.description || ''
  }))

  // Auto-select all items on open
  useEffect(() => {
    if (isOpen && candidateItems.length > 0) {
      setSelectedIds(candidateItems.map(i => i.id))
      setCompleted(false)
      setAppliedResults([])
      setProgress({ current: 0, total: candidateItems.length, currentTarget: '' })
    }
  }, [isOpen, rawList.length])

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

  const handleLaunchBatch = async () => {
    const selectedList = candidateItems.filter(i => selectedIds.includes(i.id))
    if (selectedList.length === 0) {
      toast('Please select at least one job to apply to', 'error')
      return
    }

    setApplying(true)
    setProgress({ current: 0, total: selectedList.length, currentTarget: 'Initializing auto-apply pipeline...' })

    try {
      const payload = {
        jobs: selectedList.map(item => ({
          title: item.title,
          company: item.company,
          location: item.location,
          url: item.url,
          job_url_direct: item.raw?.job_url_direct || item.url,
          description: item.description,
          site: item.site,
          match_score: item.score,
          customize_cv: true,
          notes: 'Auto-applied via Candidature Simplifiée batch engine.'
        })),
        customize_cv: true
      }

      // Step-by-step progress simulation for realistic feedback
      for (let i = 0; i < selectedList.length; i++) {
        const item = selectedList[i]
        setProgress({
          current: i + 1,
          total: selectedList.length,
          currentTarget: `Submitting Candidature Simplifiée for ${item.title} at ${item.company}...`
        })
        if (selectedList.length <= 15) {
          await new Promise(r => setTimeout(r, 180))
        }
      }

      const { data } = await client.post('/jobs/batch-easy-apply', payload)

      confetti({ particleCount: 150, spread: 80, origin: { y: 0.5 } })
      toast(data.message || `Successfully auto-applied to ${selectedList.length} jobs!`, 'success')

      setCompleted(true)
      setAppliedResults(selectedList)

      if (onSuccess) {
        onSuccess(selectedList.map(s => s.raw))
      }
    } catch (err) {
      toast(err?.response?.data?.detail || err.message || 'Batch apply failed', 'error')
    } finally {
      setApplying(false)
    }
  }

  const selectedCount = selectedIds.length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-2xl bg-slate-900 border border-blue-500/35 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
      >
        {/* Top Header */}
        <div className="p-5 border-b border-slate-800 bg-slate-950/70 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center justify-center shrink-0 shadow-xs">
              <Zap size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white tracking-tight">
                  Candidature Simplifiée — Batch Auto-Apply
                </h3>
                <span className="bg-blue-500/15 text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded text-[10px] font-bold uppercase">
                  Easy Apply
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Auto-apply in 1 click to all {candidateItems.length} job postings without email that support simplified apply.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            disabled={applying}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {!completed ? (
            <>
              {/* Batch Controls Bar */}
              <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl flex items-center justify-between gap-3 text-xs flex-wrap">
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  disabled={applying}
                  className="flex items-center gap-2 text-slate-300 hover:text-white font-medium cursor-pointer transition"
                >
                  {selectedIds.length === candidateItems.length ? (
                    <CheckSquare size={16} className="text-emerald-400" />
                  ) : (
                    <Square size={16} className="text-slate-500" />
                  )}
                  <span>Select All ({selectedIds.length}/{candidateItems.length})</span>
                </button>

                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold bg-emerald-950/50 border border-emerald-800/50 px-3 py-1 rounded-lg">
                  <FileText size={13} className="text-emerald-400" />
                  <span>Attaching Original Verified Resume ({displayCvName})</span>
                </div>
              </div>

              {/* Progress Bar when applying */}
              {applying && (
                <div className="p-3.5 bg-emerald-950/30 border border-emerald-800/50 rounded-xl space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-emerald-300 flex items-center gap-1.5">
                      <Loader2 size={13} className="animate-spin text-emerald-400" />
                      Auto-Applying in progress...
                    </span>
                    <span className="font-mono text-slate-400">
                      {progress.current} / {progress.total}
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 transition-all duration-300"
                      style={{ width: `${(progress.current / Math.max(progress.total, 1)) * 100}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-slate-400 truncate italic">
                    {progress.currentTarget}
                  </p>
                </div>
              )}

              {/* Job List Cards */}
              <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
                {candidateItems.map((item) => {
                  const isChecked = selectedIds.includes(item.id)
                  const isLinkedIn = (item.site || '').toLowerCase().includes('linkedin')

                  return (
                    <div
                      key={item.id}
                      onClick={() => !applying && toggleSelect(item.id)}
                      className={`p-3 rounded-xl border transition cursor-pointer flex items-center justify-between gap-3 ${
                        isChecked
                          ? 'bg-slate-800/80 border-emerald-500/60 shadow-xs'
                          : 'bg-slate-950/50 border-slate-800 hover:border-slate-700 opacity-60'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="shrink-0 text-emerald-400">
                          {isChecked ? <CheckSquare size={16} /> : <Square size={16} className="text-slate-600" />}
                        </div>
                        <div className="min-w-0 space-y-0.5">
                          <h4 className="text-xs font-bold text-white truncate">
                            {item.title}
                          </h4>
                          <div className="flex items-center gap-2 text-[11px] text-slate-400">
                            <span className="text-blue-300 font-medium truncate max-w-[140px] flex items-center gap-1">
                              <Building2 size={10} />
                              {item.company}
                            </span>
                            <span>•</span>
                            <span className="truncate max-w-[120px] flex items-center gap-1">
                              <MapPin size={10} />
                              {item.location}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold border ${
                          isLinkedIn
                            ? 'bg-blue-950/80 text-blue-300 border-blue-800'
                            : 'bg-indigo-950/80 text-indigo-300 border-indigo-800'
                        }`}>
                          {item.site}
                        </span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-emerald-950/80 text-emerald-300 border-emerald-700">
                          {item.score}% CV
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Information Callout */}
              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80 text-[11px] text-slate-400 space-y-1">
                <div className="flex items-center gap-1.5 text-slate-300 font-semibold">
                  <CheckCheck size={13} className="text-emerald-400" />
                  <span>What happens next?</span>
                </div>
                <p>
                  Each selected position is processed with a per-job tailored copy of your resume (missing job skills added, off-topic content removed), recorded in your Application Tracker with status <span className="text-emerald-300 font-semibold">"Applied"</span>, and automatically filtered out of your future search feeds.
                </p>
              </div>
            </>
          ) : (
            /* Completed Success Screen */
            <div className="py-8 text-center space-y-4">
              <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center justify-center mx-auto shadow-lg shadow-emerald-500/20">
                <CheckCheck size={32} className="stroke-[2.5]" />
              </div>
              <div className="space-y-1">
                <h4 className="text-lg font-bold text-white">
                  Batch Application Successful!
                </h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Applied to <span className="text-emerald-300 font-bold">{appliedResults.length} positions</span> via Candidature Simplifiée. All applications are now tracked in your pipeline.
                </p>
              </div>

              <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-xl text-left max-h-[200px] overflow-y-auto space-y-1.5">
                {appliedResults.map((app, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs py-1 border-b border-slate-850 last:border-0">
                    <span className="font-semibold text-white truncate max-w-[280px]">
                      {app.title}
                    </span>
                    <span className="text-slate-400 truncate max-w-[150px]">
                      {app.company}
                    </span>
                    <span className="text-emerald-400 font-semibold text-[11px] flex items-center gap-1">
                      <Check size={11} /> Applied
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between gap-3">
          {!completed ? (
            <>
              <button
                type="button"
                onClick={onClose}
                disabled={applying}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleLaunchBatch}
                disabled={applying || selectedCount === 0}
                className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs shadow-lg shadow-emerald-500/25 transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {applying ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Applying ({progress.current}/{progress.total})...</span>
                  </>
                ) : (
                  <>
                    <Zap size={14} className="fill-white" />
                    <span>Auto-Apply to {selectedCount} Jobs in 1 Click</span>
                  </>
                )}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-md transition cursor-pointer"
            >
              Done & View Feed
            </button>
          )}
        </div>
      </motion.div>
    </div>
  )
}
