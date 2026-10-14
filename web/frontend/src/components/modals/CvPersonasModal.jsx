import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Layers, Upload, CheckCircle2, Trash2, Sparkles, FileText, Loader2, Check
} from 'lucide-react'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

export default function CvPersonasModal({ isOpen, onClose, onPersonaChanged }) {
  const toast = useToast()
  const [personas, setPersonas] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [personaLabel, setPersonaLabel] = useState('')

  const loadPersonas = async () => {
    setLoading(true)
    try {
      const { data } = await client.get('/cv/personas')
      setPersonas(data.personas || [])
    } catch {
      toast('Failed to load CV personas', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) loadPersonas()
  }, [isOpen])

  const handleUploadNewPersona = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('persona_name', personaLabel.trim())
    try {
      const { data } = await client.post('/cv/personas', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      toast(`Added & activated persona: ${data.persona_name}`, 'success')
      setPersonaLabel('')
      await loadPersonas()
      if (onPersonaChanged) onPersonaChanged()
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to upload CV persona', 'error')
    } finally {
      setUploading(false)
    }
  }

  const handleActivate = async (id) => {
    try {
      const { data } = await client.post(`/cv/personas/${id}/activate`)
      toast(data.message || 'Switched active CV persona', 'success')
      await loadPersonas()
      if (onPersonaChanged) onPersonaChanged()
    } catch {
      toast('Failed to switch active persona', 'error')
    }
  }

  const handleDelete = async (id) => {
    try {
      await client.delete(`/cv/personas/${id}`)
      toast('Removed CV persona', 'info')
      await loadPersonas()
      if (onPersonaChanged) onPersonaChanged()
    } catch {
      toast('Failed to delete CV persona', 'error')
    }
  }

  if (!isOpen) return null

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
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
                <Layers size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-black text-lg text-white tracking-tight">Multi-CV Personas Vault</h3>
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    {personas.length} Stored
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Store specialized resumes for different role tracks (e.g. Mobile, Full-Stack, AI) and switch in 1 click.
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
          <div className="p-6 overflow-y-auto space-y-5 flex-1">
            {/* Upload New Persona Card */}
            <div className="glass-card rounded-2xl p-4 border border-blue-500/25 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-blue-300">
                <Sparkles size={13} className="text-amber-400" />
                <span>Add a New Role Persona Resume</span>
              </div>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
                <input
                  type="text"
                  value={personaLabel}
                  onChange={e => setPersonaLabel(e.target.value)}
                  placeholder="Persona label (e.g. Flutter Mobile CV, React Full-Stack CV)..."
                  className="flex-1 glass-input rounded-xl px-3.5 py-2.5 text-xs"
                />
                <label className="shimmer-btn px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-extrabold flex items-center justify-center gap-2 cursor-pointer shrink-0 shadow-lg shadow-blue-600/20">
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  <span>{uploading ? 'Uploading...' : 'Upload PDF / DOCX'}</span>
                  <input
                    type="file"
                    accept=".pdf,.docx,.txt"
                    onChange={handleUploadNewPersona}
                    disabled={uploading}
                    className="hidden"
                  />
                </label>
              </div>
            </div>

            {/* Personas List */}
            {loading ? (
              <div className="py-10 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
                <Loader2 size={16} className="animate-spin text-blue-400" />
                <span>Loading your CV Personas Vault...</span>
              </div>
            ) : personas.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs space-y-2">
                <FileText size={28} className="mx-auto text-slate-600" />
                <p className="font-bold text-slate-300">No resumes uploaded yet</p>
                <p>Upload your first resume above to unlock AI ATS scoring and 1-click auto-apply.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {personas.map(p => (
                  <div
                    key={p.id}
                    className={`glass-card rounded-2xl p-4 border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                      p.is_active
                        ? 'border-emerald-500/45 bg-emerald-950/15 shadow-[0_0_25px_-5px_rgba(16,185,129,0.2)]'
                        : 'border-white/[0.07] hover:border-white/[0.15]'
                    }`}
                  >
                    <div className="space-y-1.5 min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-extrabold text-sm text-white truncate">{p.persona_name}</span>
                        {p.is_active && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/35">
                            <CheckCircle2 size={11} /> Active Persona
                          </span>
                        )}
                        <span className="text-[11px] text-slate-400 font-mono truncate">({p.filename})</span>
                      </div>

                      <div className="flex items-center gap-2 text-[11px] text-slate-400 flex-wrap">
                        <span>Detected Track: <strong className="text-slate-200">{p.detected_role}</strong></span>
                        <span>·</span>
                        <span>{p.words} words</span>
                      </div>

                      {p.top_skills?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {p.top_skills.map(s => (
                            <span key={s} className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.07] text-blue-300">
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {!p.is_active && (
                        <button
                          type="button"
                          onClick={() => handleActivate(p.id)}
                          className="px-3.5 py-2 rounded-xl bg-blue-600/20 hover:bg-blue-600 text-blue-300 hover:text-white border border-blue-500/35 text-xs font-bold transition flex items-center gap-1.5 cursor-pointer"
                        >
                          <Check size={13} />
                          <span>Set Active</span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDelete(p.id)}
                        className="p-2 rounded-xl bg-white/[0.03] hover:bg-rose-500/15 border border-white/[0.06] hover:border-rose-500/30 text-slate-400 hover:text-rose-400 transition cursor-pointer"
                        title="Delete this CV persona"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
