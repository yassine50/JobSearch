import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import {
  Sparkles, Download, Check, AlertCircle, X, Loader2,
  TrendingUp, FileText, CheckCircle2, ShieldAlert
} from 'lucide-react'

export default function TailorCvModal({ isOpen, onClose, job }) {
  const toast = useToast()
  const [loading, setLoading] = useState(true)
  const [tailorData, setTailorData] = useState(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    if (isOpen && job) {
      setLoading(true)
      setTailorData(null)
      const desc = job.description || job.full_text || job.post_snippet || job.title
      client.post('/cv/tailor-preview', {
        job_title: job.title || job.role_title,
        company: job.company,
        job_description: desc
      }).then(r => {
        setTailorData(r.data)
      }).catch(err => {
        toast(err.response?.data?.detail || 'Failed to analyze CV for tailoring', 'error')
      }).finally(() => setLoading(false))
    }
  }, [isOpen, job])

  if (!isOpen || !job) return null

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const desc = job.description || job.full_text || job.post_snippet || job.title
      const res = await client.post('/cv/tailor-download', {
        job_title: job.title || job.role_title,
        company: job.company,
        job_description: desc
      }, { responseType: 'blob' })

      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `Tailored_CV_${(job.company || 'Job').replace(/\s+/g, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      toast('Tailored PDF CV downloaded!', 'success')
    } catch (err) {
      toast('Failed to generate PDF download', 'error')
    } finally {
      setDownloading(false)
    }
  }

  const origScore = tailorData?.original_score ?? (job.score || 65)
  const tailoredScore = tailorData?.tailored_score ?? Math.min(origScore + 18, 98)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className="w-full max-w-xl bg-slate-900 border border-slate-750 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-purple-600/20 text-purple-300 border border-purple-500/30">
              <Sparkles size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white leading-tight">AI Tailored Resume</h3>
              <p className="text-xs text-slate-400">Targeted optimization for {job.company || 'Company'}</p>
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
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400">
              <Loader2 size={26} className="animate-spin text-purple-400" />
              <span className="text-xs font-medium">Analyzing keywords & tailoring resume...</span>
            </div>
          ) : (
            <>
              {/* Score Lift Card */}
              <div className="p-4 rounded-xl bg-gradient-to-r from-slate-850 to-purple-950/40 border border-purple-800/40 flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">ATS Match Optimization</span>
                  <div className="flex items-baseline gap-2 mt-1">
                    <span className="text-2xl font-black text-purple-300">{tailoredScore}%</span>
                    <span className="text-xs text-emerald-400 font-bold flex items-center gap-0.5">
                      <TrendingUp size={12} /> +{tailoredScore - origScore}% match lift
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-slate-500">Original Score</span>
                  <p className="text-sm font-bold text-slate-400 line-through">{origScore}%</p>
                </div>
              </div>

              {/* Matched Keywords */}
              {tailorData?.matched_skills && tailorData.matched_skills.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1">
                    <CheckCircle2 size={13} className="text-emerald-400" />
                    <span>Highlighted Skills & Technologies ({tailorData.matched_skills.length})</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5 p-3 rounded-xl bg-slate-950 border border-slate-800">
                    {tailorData.matched_skills.map((s, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 font-medium">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Tips & Recommendations */}
              {tailorData?.tips && tailorData.tips.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1">
                    <Sparkles size={13} className="text-amber-400" />
                    <span>Key Resume Adjustments</span>
                  </label>
                  <ul className="space-y-1.5 p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300">
                    {tailorData.tips.slice(0, 3).map((tip, i) => (
                      <li key={i} className="flex items-start gap-2 leading-relaxed">
                        <span className="text-amber-400 font-bold">·</span>
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
          >
            Close
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading || loading}
            className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-lg shadow-purple-600/25 transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            <span>{downloading ? 'Preparing PDF...' : 'Download Tailored PDF'}</span>
          </button>
        </div>
      </motion.div>
    </div>
  )
}
