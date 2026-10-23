import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import CvReviewEditor from './CvReviewEditor.jsx'
import {
  Sparkles, Download, X, Loader2,
  TrendingUp, FileText, CheckCircle2, Layers, ShieldCheck, Wrench, AlertTriangle,
  ClipboardCheck, ArrowLeft, ShieldAlert, Eye, BarChart2, Edit3
} from 'lucide-react'

const QUALITY_STYLES = {
  high: 'bg-blue-500/10 border-blue-500/30 text-blue-300',
  medium: 'bg-slate-900/80 border-blue-500/30 text-slate-300',
  low: 'bg-slate-900/80 border-blue-500/30 text-slate-300',
}

export default function TailorCvModal({ isOpen, onClose, job }) {
  const toast = useToast()
  const [loading, setLoading] = useState(true)
  const [tailorData, setTailorData] = useState(null)
  const [downloading, setDownloading] = useState(false)
  const [view, setView] = useState('results')        // 'results' | 'preview' | 'review'
  const [parsed, setParsed] = useState(null)         // { cv, quality }
  const [parsedLoading, setParsedLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pdfUrl, setPdfUrl] = useState(null)

  const jobPayload = useCallback(() => ({
    job_title: job?.title || job?.role_title || 'Software Engineer',
    company: job?.company || 'Company',
    job_description: job?.description || job?.full_text || job?.post_snippet || job?.title || ''
  }), [job])

  // Convert base64 PDF from /api/cv/tailor into an instant object URL for live preview & 0ms download
  useEffect(() => {
    if (!tailorData?.pdf_base64) {
      setPdfUrl(null)
      return
    }
    try {
      const bin = atob(tailorData.pdf_base64)
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      const blob = new Blob([bytes], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      setPdfUrl(url)
      return () => window.URL.revokeObjectURL(url)
    } catch {
      setPdfUrl(null)
    }
  }, [tailorData?.pdf_base64])

  const runTailor = useCallback(() => {
    setLoading(true)
    setTailorData(null)
    return client.post('/cv/tailor', jobPayload()).then(r => {
      setTailorData(r.data)
    }).catch(err => {
      toast(err.response?.data?.detail || 'Failed to analyze CV for tailoring', 'error')
    }).finally(() => setLoading(false))
  }, [jobPayload, toast])

  useEffect(() => {
    if (isOpen && job) {
      setView('results')
      setParsed(null)
      runTailor()
    }
  }, [isOpen, job])

  if (!isOpen || !job) return null

  const openReview = async () => {
    setView('review')
    if (parsed) return
    setParsedLoading(true)
    try {
      const r = await client.get('/cv/parsed')
      setParsed(r.data)
    } catch (err) {
      toast(err.response?.data?.detail || 'Could not load extracted CV', 'error')
      setView('results')
    } finally {
      setParsedLoading(false)
    }
  }

  const saveReview = async (cv) => {
    setSaving(true)
    try {
      const r = await client.put('/cv/parsed', { cv })
      setParsed(r.data)
      toast('Reviewed CV saved — re-tailoring with your corrections', 'success')
      setView('results')
      await runTailor()
    } catch (err) {
      toast(err.response?.data?.detail || 'Could not save your corrections', 'error')
    } finally {
      setSaving(false)
    }
  }

  const resetReview = async () => {
    setSaving(true)
    try {
      const r = await client.delete('/cv/parsed')
      setParsed(r.data)
      toast('Back to automatic extraction', 'success')
      setView('results')
      await runTailor()
    } catch {
      toast('Could not reset', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleDownload = async () => {
    const downloadName = tailorData?.filename || `Tailored_CV_${(job.company || 'Job').replace(/\s+/g, '_')}.pdf`
    if (pdfUrl) {
      const a = document.createElement('a')
      a.href = pdfUrl
      a.download = downloadName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      toast('Tailored PDF CV downloaded!', 'success')
      return
    }
    setDownloading(true)
    try {
      const res = await client.post('/cv/tailored-pdf', jobPayload(), { responseType: 'blob' })

      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = downloadName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      toast('Tailored PDF CV downloaded!', 'success')
    } catch {
      toast('Failed to generate PDF download', 'error')
    } finally {
      setDownloading(false)
    }
  }

  const origScore = tailorData?.original_score ?? (job.score || 65)
  const tailoredScore = tailorData?.tailored_score ?? Math.min(origScore + 18, 98)
  const lift = Math.max(0, tailoredScore - origScore)
  const profile = tailorData?.cv_profile || {}
  const diagnosis = tailorData?.diagnosis || {}
  const beforeQuality = diagnosis.before_scores?.overall ?? profile.quality_scores_before?.overall
  const afterQuality = diagnosis.after_scores?.overall ?? profile.quality_scores_after?.overall
  const issues = diagnosis.issues || profile.issues || []
  const enhancements = diagnosis.enhancements || profile.enhancements || []
  const totalRoles = (profile.roles_count || 0) + (profile.internships_count || 0)

  const skillsList = tailorData?.matched_skills?.length
    ? tailorData.matched_skills
    : (tailorData?.bridged_skills || [])

  const quality = tailorData?.extraction_quality || {}
  const qLevel = quality.level || 'high'
  const needsReview = !quality.reviewed && (qLevel === 'low' || qLevel === 'medium')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className={`w-full ${view === 'preview' ? 'max-w-4xl' : 'max-w-2xl'} glass-dropdown border border-white/[0.12] rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh] relative transition-all duration-200`}
        onClick={e => e.stopPropagation()}
      >
        <div className="glow-line-top" />

        {/* Header */}
        <div className="px-6 py-4 border-b border-white/[0.08] bg-slate-950/70 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 shrink-0">
              <Sparkles size={18} />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-white leading-tight">
                AI Executive CV Tailoring &amp; Live A4 Preview
              </h3>
              <p className="text-xs text-slate-400">
                Tailored for <strong className="text-slate-200">{job.title || job.role_title || 'Target Role'}</strong> at <strong className="text-blue-300">{job.company || 'Target Company'}</strong>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end sm:self-auto">
            {!loading && tailorData && (
              <div className="flex items-center bg-slate-900/90 border border-white/[0.08] rounded-xl p-1 text-[11px] font-bold">
                <button
                  type="button"
                  onClick={() => setView('results')}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition cursor-pointer ${
                    view === 'results' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <BarChart2 size={12} />
                  <span>Diagnosis ({tailoredScore}%)</span>
                </button>
                {pdfUrl && (
                  <button
                    type="button"
                    onClick={() => setView('preview')}
                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition cursor-pointer ${
                      view === 'preview' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <Eye size={12} />
                    <span>Live PDF Preview</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={openReview}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition cursor-pointer ${
                    view === 'review' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Edit3 size={12} />
                  <span>{quality.reviewed ? 'Edit CV' : 'Review & Fix'}</span>
                </button>
              </div>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition cursor-pointer"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {view === 'preview' && pdfUrl ? (
            <div className="space-y-3 h-full flex flex-col">
              <div className="flex items-center justify-between gap-2 bg-slate-950/80 border border-white/[0.08] rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-2 text-xs text-slate-300">
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                  <span>
                    <strong className="text-white">{tailorData?.filename || 'Tailored_CV.pdf'}</strong> · Single-Column A4 ATS Format · <strong className="text-emerald-300">{tailoredScore}% ATS Match</strong>
                  </span>
                </div>
                <button
                  type="button"
                  onClick={openReview}
                  className="text-[11px] font-bold text-blue-300 hover:text-white bg-blue-500/15 border border-blue-500/30 px-2.5 py-1 rounded-lg cursor-pointer transition"
                >
                  Need a tweak? Edit Extracted CV →
                </button>
              </div>
              <div className="w-full h-[64vh] rounded-2xl overflow-hidden border border-white/[0.12] bg-slate-950 shadow-inner">
                <iframe
                  src={`${pdfUrl}#toolbar=0&navpanes=0&view=FitH`}
                  title="Tailored A4 Resume PDF Preview"
                  className="w-full h-full border-0"
                />
              </div>
            </div>
          ) : view === 'review' ? (
            parsedLoading || !parsed ? (
              <div className="flex flex-col items-center justify-center py-14 gap-3 text-slate-400">
                <Loader2 size={28} className="animate-spin text-emerald-400" />
                <span className="text-xs font-semibold text-white">Loading what was extracted from your CV...</span>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold text-white">Review extracted CV</p>
                    <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
                      This is exactly what was read from <b className="text-slate-300">{parsed.filename || 'your CV'}</b>.
                      Fix anything missing or wrong — your corrections are saved and used for every future tailored CV.
                    </p>
                  </div>
                  <button type="button" onClick={() => setView('results')}
                    className="shrink-0 text-[11px] font-semibold text-slate-400 hover:text-white flex items-center gap-1 cursor-pointer">
                    <ArrowLeft size={12} /> Back
                  </button>
                </div>
                {(parsed.quality?.warnings || []).length > 0 && !parsed.quality?.reviewed && (
                  <ul className={`p-3 rounded-xl border text-[11px] space-y-1 ${QUALITY_STYLES[parsed.quality.level] || QUALITY_STYLES.medium}`}>
                    {parsed.quality.warnings.map((w, i) => <li key={i}>• {w}</li>)}
                  </ul>
                )}
                <CvReviewEditor
                  key={JSON.stringify(parsed.cv?.name) + (parsed.quality?.reviewed ? '-r' : '-a')}
                  initialCv={parsed.cv}
                  reviewed={!!parsed.quality?.reviewed}
                  saving={saving}
                  onSave={saveReview}
                  onReset={resetReview}
                />
              </>
            )
          ) : loading ? (
            <div className="flex flex-col items-center justify-center py-14 gap-3 text-slate-400">
              <Loader2 size={28} className="animate-spin text-purple-400" />
              <span className="text-xs font-semibold text-white">
                Step 1: Diagnosing CV layout, career stage &amp; writing quality...
              </span>
              <span className="text-[11px] text-slate-500">
                Step 2: Enhancing bullets, fixing typos &amp; rendering single-column A4 ATS PDF
              </span>
            </div>
          ) : (
            <>
              {/* Extraction confidence: can we trust what was read from the file? */}
              {tailorData && (
                <div className={`p-3.5 rounded-xl border flex items-start justify-between gap-3 ${QUALITY_STYLES[qLevel] || QUALITY_STYLES.high}`}>
                  <div className="flex items-start gap-2.5 min-w-0">
                    {quality.reviewed || qLevel === 'high'
                      ? <ClipboardCheck size={16} className="shrink-0 mt-0.5" />
                      : <ShieldAlert size={16} className="shrink-0 mt-0.5" />}
                    <div className="min-w-0">
                      <p className="text-xs font-bold">
                        {quality.reviewed
                          ? 'Using your reviewed CV'
                          : qLevel === 'high'
                            ? `Extraction confidence: high (${quality.score ?? 100}/100)`
                            : qLevel === 'medium'
                              ? `Extraction confidence: medium (${quality.score}/100) — please review`
                              : `Extraction confidence: low (${quality.score}/100) — review before sending`}
                      </p>
                      {!quality.reviewed && (quality.warnings || []).length > 0 && (
                        <ul className="text-[11px] mt-1 space-y-0.5 opacity-90">
                          {quality.warnings.slice(0, 3).map((w, i) => <li key={i}>• {w}</li>)}
                        </ul>
                      )}
                      {!quality.reviewed && qLevel === 'low' && (
                        <p className="text-[10px] mt-1 opacity-80">
                          Until you review it, automatic applications will attach your original CV instead of a tailored one.
                        </p>
                      )}
                    </div>
                  </div>
                  <button type="button" onClick={openReview}
                    className={`shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-bold cursor-pointer transition ${needsReview
                      ? 'bg-white text-slate-900 hover:bg-slate-200'
                      : 'bg-slate-900/70 text-slate-200 border border-slate-700 hover:bg-slate-800'}`}>
                    {quality.reviewed ? 'Edit' : 'Review & fix'}
                  </button>
                </div>
              )}

              {/* Step 1: Pre-Tailoring CV Type & Quality Diagnosis */}
              {profile.cv_type && (
                <div className="p-4 rounded-xl bg-slate-950/90 border border-blue-500/30 space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-blue-400 flex items-center gap-1.5">
                      <Layers size={13} />
                      1. Pre-Tailoring CV Diagnosis
                    </span>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {beforeQuality != null && afterQuality != null && (
                        <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                          CV Quality: {beforeQuality}/100 → {afterQuality}/100
                        </span>
                      )}
                      <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/30">
                        {profile.seniority || 'Professional'}
                        {profile.years_experience ? ` · ${profile.years_experience} Yrs` : ''}
                        {profile.language ? ` · ${profile.language.toUpperCase()}` : ''}
                      </span>
                    </div>
                  </div>

                  <div>
                    <p className="text-sm font-extrabold text-white">{profile.cv_type}</p>
                    {profile.domain_focus && (
                      <p className="text-xs text-slate-400 mt-0.5">{profile.domain_focus}</p>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2 pt-0.5">
                    <span className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
                      <b>{totalRoles}</b> Experience Entr{totalRoles === 1 ? 'y' : 'ies'}
                    </span>
                    <span className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
                      <b>{profile.projects_count || 0}</b> Projects
                    </span>
                    <span className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
                      <b>{profile.skills_count || 0}</b> Verified Skills
                    </span>
                    <span className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
                      <b>{profile.metrics_count || 0}</b> Quantified Metrics
                    </span>
                    {profile.layout === 'two-column' && (
                      <span className="text-[11px] px-2.5 py-1 rounded-lg bg-blue-500/10 border border-blue-500/25 text-blue-300">
                        2-Column Sidebar → Single-Column ATS
                      </span>
                    )}
                  </div>

                  {/* Pre-Tailoring Issues & Auto-Fixes */}
                  {issues.length > 0 && (
                    <div className="pt-2 border-t border-slate-800/80 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                        <AlertTriangle size={11} className="text-blue-400" />
                        Diagnostic Findings ({issues.filter(i => i.auto_fixed).length} Auto-Fixed)
                      </span>
                      <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                        {issues.slice(0, 6).map((iss, idx) => (
                          <div
                            key={idx}
                            className="text-[11px] p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex items-start justify-between gap-2"
                          >
                            <div className="text-slate-300 leading-snug">
                              <span className="font-semibold text-white">[{iss.area}]</span> {iss.message}{' '}
                              <span className="text-slate-400">{iss.fix}</span>
                            </div>
                            {iss.auto_fixed ? (
                              <span className="shrink-0 text-[10px] font-bold px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/30">
                                Auto-Fixed
                              </span>
                            ) : (
                              <span className="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded bg-white/[0.04] text-slate-300 border border-white/[0.08]">
                                Tip
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Step 2: Mechanical Enhancements Applied Before Tailoring */}
              {enhancements.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Wrench size={13} className="text-blue-400" />
                    <span>2. Pre-Tailoring CV Enhancements Applied ({enhancements.length})</span>
                  </label>
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5 max-h-36 overflow-y-auto">
                    {enhancements.slice(0, 8).map((ch, idx) => (
                      <div key={idx} className="text-[11px] text-slate-300 leading-snug flex items-start gap-2">
                        <span className="text-blue-400 font-bold shrink-0">✓</span>
                        <div className="min-w-0">
                          <span className="text-slate-500 line-through mr-1.5">{ch.before}</span>
                          {ch.after && <span className="text-blue-300 font-medium">→ {ch.after}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 3: ATS Match Optimization Card */}
              <div className="p-4 rounded-xl bg-slate-950/60 border border-blue-500/30 flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    3. Target Job ATS Match Score
                  </span>
                  <div className="flex items-baseline gap-2.5 mt-1">
                    <span className="text-2xl font-black text-blue-400">{tailoredScore}%</span>
                    {lift > 0 && (
                      <span className="text-xs text-blue-300 font-bold flex items-center gap-0.5">
                        <TrendingUp size={12} /> +{lift}% match lift
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className="text-[11px] text-slate-400">Original Score</span>
                    <p className="text-sm font-bold text-slate-400 line-through">{origScore}%</p>
                  </div>
                  {pdfUrl && (
                    <button
                      type="button"
                      onClick={() => setView('preview')}
                      className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 transition cursor-pointer shadow-sm"
                    >
                      <Eye size={13} />
                      <span>Preview A4 PDF</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Score breakdown — computed on the rendered PDF text, i.e. what the employer's ATS reads */}
              {tailorData?.score_breakdown && Object.keys(tailorData.score_breakdown).length > 0 && (() => {
                const b = tailorData.score_breakdown
                const parts = [
                  ['Tech skills', b.tech_score], ['JD wording', b.semantic_score], ['Role title', b.title_score],
                  ['Soft skills', b.soft_score],
                ].filter(([, v]) => v != null)
                return (
                  <div className="space-y-1.5 -mt-1">
                    <div className="grid grid-cols-4 gap-1.5">
                      {parts.map(([label, v]) => (
                        <div key={label} className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                          <div className="flex items-center justify-between text-[10px] text-slate-400">
                            <span>{label}</span><span className="font-bold text-slate-200">{v}</span>
                          </div>
                          <div className="h-1 mt-1 rounded bg-slate-800 overflow-hidden">
                            <div className={`h-full ${v >= 90 ? 'bg-emerald-500' : v >= 70 ? 'bg-amber-400' : 'bg-red-400'}`}
                              style={{ width: `${Math.min(100, v)}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                    {b.exp_penalty > 0 && (
                      <p className="text-[10px] text-amber-300">
                        −{b.exp_penalty} pts: the job asks for more years of experience than your CV shows (this cannot be tailored away honestly).
                      </p>
                    )}
                    {(b.missing_tech || []).length > 0 && (
                      <p className="text-[10px] text-slate-400">Still missing: {b.missing_tech.join(', ')}</p>
                    )}
                  </div>
                )
              })()}

              {/* Step 4: Tailored Headline & Executive Summary Preview */}
              {tailorData?.tailored_summary && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <FileText size={13} className="text-purple-400" />
                    <span>4. Tailored Headline &amp; Executive Summary</span>
                  </label>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                    {tailorData.target_headline && (
                      <p className="text-xs font-bold text-blue-300">
                        {tailorData.target_headline}
                      </p>
                    )}
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {tailorData.tailored_summary}
                    </p>
                  </div>
                </div>
              )}

              {/* Step 5: Highlighted & Bridged Skills */}
              {skillsList.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <CheckCircle2 size={13} className="text-emerald-400" />
                    <span>5. Prioritized &amp; Bridged Technical Keywords ({skillsList.length})</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5 p-3 rounded-xl bg-slate-950 border border-slate-800">
                    {skillsList.map((s, i) => (
                      <span
                        key={i}
                        className="text-xs px-2.5 py-0.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 6: Professional Editing Audit Log */}
              {tailorData?.tips && tailorData.tips.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <ShieldCheck size={13} className="text-amber-400" />
                    <span>6. Executive Pipeline Summary</span>
                  </label>
                  <ul className="space-y-1.5 p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300">
                    {tailorData.tips.map((tip, i) => (
                      <li key={i} className="flex items-start gap-2 leading-relaxed">
                        <span className="text-amber-400 font-bold">✓</span>
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
        <div className="px-6 py-3.5 border-t border-white/[0.08] bg-slate-950/70 flex items-center justify-between gap-2 flex-wrap">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition cursor-pointer"
          >
            Close
          </button>
          <div className="flex items-center gap-2">
            {pdfUrl && view !== 'preview' && view !== 'review' && (
              <button
                type="button"
                onClick={() => setView('preview')}
                className="px-4 py-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.1] text-slate-200 font-bold text-xs transition flex items-center gap-1.5 cursor-pointer"
              >
                <Eye size={14} className="text-blue-400" />
                <span>Live PDF Preview</span>
              </button>
            )}
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading || loading || view === 'review'}
              className={`px-5 py-2.5 rounded-xl text-white font-bold text-xs shadow-lg transition flex items-center gap-2 cursor-pointer disabled:opacity-50 ${needsReview && qLevel === 'low'
                ? 'bg-slate-700 hover:bg-slate-600 shadow-black/20'
                : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-blue-600/25'}`}
            >
              {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              <span>{downloading ? 'Preparing Executive PDF...' : (needsReview && qLevel === 'low' ? 'Download anyway' : 'Download Tailored PDF')}</span>
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
