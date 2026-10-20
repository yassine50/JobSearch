import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Sparkles, Cpu, Award, HelpCircle, DollarSign, Copy, Check, RotateCw, Loader2, CheckCircle2, ClipboardList
} from 'lucide-react'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

export default function InterviewPrepModal({ isOpen, onClose, application }) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [kit, setKit] = useState(null)
  const [activeTab, setActiveTab] = useState('technical') // 'brief' | 'technical' | 'star' | 'questions'
  const [copiedText, setCopiedText] = useState(null)

  useEffect(() => {
    if (isOpen && application) {
      loadPrepKit(false)
    } else if (!isOpen) {
      setKit(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, application?.id, application?.title, application?.company])

  const loadPrepKit = async (force = false) => {
    setLoading(true)
    try {
      const { data } = await client.post('/power/interview-prep', {
        application_id: application?.id || null,
        title: application?.title || '',
        company: application?.company || '',
        location: application?.location || '',
        description: application?.notes || application?.description || '',
        force_regenerate: force,
      })
      setKit(data)
      if (force) toast('Regenerated fresh AI Interview Prep Kit!', 'success')
    } catch {
      toast('Failed to generate Interview Prep Kit', 'error')
    } finally {
      setLoading(false)
    }
  }

  const copyBlock = (text, label = 'Copied to clipboard!') => {
    navigator.clipboard.writeText(text)
    setCopiedText(text)
    toast(label, 'success')
    setTimeout(() => setCopiedText(null), 2000)
  }

  if (!isOpen || !application) return null

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
          className="glass-dropdown rounded-3xl w-full max-w-3xl max-h-[88vh] overflow-hidden flex flex-col border border-white/[0.1] shadow-2xl relative"
        >
          <div className="glow-line-top" />

          {/* Header */}
          <div className="p-6 border-b border-white/[0.08] flex items-center justify-between gap-4 bg-slate-950/60">
            <div className="space-y-1 min-w-0">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-purple-500/15 border border-purple-500/30 text-purple-300 text-[10px] font-extrabold uppercase tracking-wider">
                <Sparkles size={11} className="text-amber-400" /> AI Interview Prep &amp; Strategy Studio
              </div>
              <h3 className="font-black text-lg sm:text-xl text-white tracking-tight truncate">
                {application.title} <span className="text-slate-400 font-semibold">at</span> <span className="text-gradient-blue">{application.company}</span>
              </h3>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => loadPrepKit(true)}
                disabled={loading}
                className="px-3 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs font-bold text-slate-300 hover:text-white flex items-center gap-1.5 transition cursor-pointer"
                title="Regenerate Interview Kit"
              >
                <RotateCw size={13} className={loading ? 'animate-spin text-blue-400' : ''} />
                <span className="hidden sm:inline">Regenerate</span>
              </button>
              <button
                onClick={onClose}
                className="p-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 hover:text-white transition cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="px-6 pt-3 pb-2 border-b border-white/[0.06] bg-slate-950/30 flex items-center gap-2 overflow-x-auto">
            {[
              { id: 'technical', label: 'Technical Q&A (5)', icon: Cpu },
              { id: 'star',      label: 'STAR Stories (3)',  icon: Award },
              { id: 'portal',    label: 'Portal Form Answers', icon: ClipboardList },
              { id: 'brief',     label: 'Company & Pitch',   icon: Sparkles },
              { id: 'questions', label: 'Reverse Qs & Salary', icon: DollarSign },
            ].map(tab => {
              const Icon = tab.icon
              const active = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition cursor-pointer shrink-0 ${
                    active
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-600/25'
                      : 'bg-white/[0.03] hover:bg-white/[0.07] text-slate-400 hover:text-white border border-white/[0.06]'
                  }`}
                >
                  <Icon size={13} />
                  <span>{tab.label}</span>
                </button>
              )
            })}
          </div>

          {/* Body */}
          <div className="p-6 overflow-y-auto flex-1 space-y-4">
            {loading || !kit ? (
              <div className="py-14 text-center space-y-3">
                <Loader2 size={28} className="animate-spin text-blue-400 mx-auto" />
                <p className="text-sm font-bold text-white">Building Your Tailored Interview Prep Kit...</p>
                <p className="text-xs text-slate-400">Mapping your active CV skills against {application.company}&apos;s role requirements.</p>
              </div>
            ) : (
              <>
                {/* Tab 1: Technical Q&A */}
                {activeTab === 'technical' && (
                  <div className="space-y-3.5">
                    {kit.matched_skills?.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap pb-1">
                        <span className="text-[11px] font-bold text-emerald-400 mr-1">Core Stack Focus:</span>
                        {kit.matched_skills.map(s => (
                          <span key={s} className="text-[10px] font-bold px-2.5 py-0.5 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-300">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                    {(kit.technical_questions || []).map((q, idx) => (
                      <div key={idx} className="glass-card rounded-2xl p-4 border border-white/[0.07] space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/30">
                            Q{idx + 1} · {q.category}
                          </span>
                        </div>
                        <p className="text-sm font-extrabold text-white leading-snug">{q.question}</p>
                        <div className="p-3 rounded-xl bg-emerald-950/25 border border-emerald-500/20 text-xs text-slate-300 leading-relaxed">
                          <strong className="text-emerald-400 block mb-0.5 text-[11px] uppercase tracking-wider">Winning Answer Strategy:</strong>
                          {q.strategy}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Tab 2: Behavioral STAR Stories */}
                {activeTab === 'star' && (
                  <div className="space-y-4">
                    {(kit.behavioral_star || []).map((st, idx) => (
                      <div key={idx} className="glass-card rounded-2xl p-5 border border-white/[0.07] space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="font-extrabold text-sm text-white flex items-center gap-2">
                            <Award size={15} className="text-amber-400" />
                            <span>STAR Story #{idx + 1}: {st.title}</span>
                          </h4>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                            <span className="text-[10px] font-extrabold uppercase text-blue-400 block mb-1">Situation</span>
                            <p className="text-slate-300 leading-relaxed">{st.situation}</p>
                          </div>
                          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                            <span className="text-[10px] font-extrabold uppercase text-purple-400 block mb-1">Task</span>
                            <p className="text-slate-300 leading-relaxed">{st.task}</p>
                          </div>
                          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                            <span className="text-[10px] font-extrabold uppercase text-indigo-400 block mb-1">Action</span>
                            <p className="text-slate-300 leading-relaxed">{st.action}</p>
                          </div>
                          <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/20">
                            <span className="text-[10px] font-extrabold uppercase text-emerald-400 block mb-1">Result</span>
                            <p className="text-emerald-100 leading-relaxed">{st.result}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Tab 2b: Portal Application Form Answers (08-application-forms.md) */}
                {activeTab === 'portal' && (
                  <div className="space-y-4">
                    {kit.portal_form_fields?.self_intro && (
                      <div className="glass-card rounded-2xl p-4 border border-white/[0.07] space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <h4 className="text-xs font-extrabold text-white">1. Self-Introduction (&ldquo;Tell us about yourself&rdquo;)</h4>
                            <p className="text-[11px] text-slate-400">
                              Standard ~150-word portal box ({kit.portal_form_fields.self_intro.full_words} words · {kit.portal_form_fields.self_intro.full_chars} chars)
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => copyBlock(kit.portal_form_fields.self_intro.full, 'Copied 130w Self-Introduction!')}
                            className="px-3 py-1 rounded-lg bg-blue-600/20 hover:bg-blue-600/35 border border-blue-500/30 text-xs font-bold text-blue-300 cursor-pointer"
                          >
                            Copy 130w
                          </button>
                        </div>
                        <p className="text-xs text-slate-200 whitespace-pre-line leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-white/[0.05]">
                          {kit.portal_form_fields.self_intro.full}
                        </p>
                        <div className="flex items-center justify-between pt-1">
                          <span className="text-[11px] text-slate-400">
                            Compact 500-char box variant ({kit.portal_form_fields.self_intro.short_words} words · {kit.portal_form_fields.self_intro.short_chars} chars)
                          </span>
                          <button
                            type="button"
                            onClick={() => copyBlock(kit.portal_form_fields.self_intro.short, 'Copied compact Self-Intro!')}
                            className="px-2.5 py-1 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-[11px] font-bold text-slate-300 cursor-pointer"
                          >
                            Copy Short
                          </button>
                        </div>
                      </div>
                    )}

                    {kit.portal_form_fields?.stand_out_pitches?.length > 0 && (
                      <div className="glass-card rounded-2xl p-4 border border-white/[0.07] space-y-2.5">
                        <h4 className="text-xs font-extrabold text-white">
                          2. 140-Character Stand-Out Pitch (&ldquo;What makes you stand out in one sentence?&rdquo;)
                        </h4>
                        {kit.portal_form_fields.stand_out_pitches.map((p, idx) => (
                          <div key={idx} className="p-3 rounded-xl bg-slate-950/60 border border-white/[0.05] flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-[10px] font-extrabold uppercase tracking-wider text-amber-300 bg-amber-500/15 px-2 py-0.5 rounded">
                                  {p.angle}
                                </span>
                                <span className="text-[10px] font-bold text-emerald-400">{p.chars}/140 chars</span>
                              </div>
                              <p className="text-xs text-slate-100">{p.text}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => copyBlock(p.text, 'Copied 140-char pitch!')}
                              className="px-2.5 py-1 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-[11px] font-bold text-slate-200 shrink-0 cursor-pointer"
                            >
                              Copy
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {kit.portal_form_fields?.why_company && (
                      <div className="glass-card rounded-2xl p-4 border border-white/[0.07] space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <h4 className="text-xs font-extrabold text-white">3. &ldquo;Why do you want to work at {application.company}?&rdquo;</h4>
                            <p className="text-[11px] text-slate-400">
                              Forward-looking task-solving framing ({kit.portal_form_fields.why_company.words} words)
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => copyBlock(kit.portal_form_fields.why_company.text, 'Copied Why Company answer!')}
                            className="px-3 py-1 rounded-lg bg-blue-600/20 hover:bg-blue-600/35 border border-blue-500/30 text-xs font-bold text-blue-300 cursor-pointer"
                          >
                            Copy
                          </button>
                        </div>
                        <p className="text-xs text-slate-200 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-white/[0.05]">
                          {kit.portal_form_fields.why_company.text}
                        </p>
                      </div>
                    )}

                    {kit.portal_form_fields?.structured_project && (
                      <div className="glass-card rounded-2xl p-4 border border-white/[0.07] space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <h4 className="text-xs font-extrabold text-white">4. Structured Project Entry (Portal Form Box)</h4>
                            <p className="text-[11px] text-slate-400">
                              {kit.portal_form_fields.structured_project.name} · {kit.portal_form_fields.structured_project.role}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => copyBlock(kit.portal_form_fields.structured_project.description_100w, 'Copied project description!')}
                            className="px-3 py-1 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/35 border border-emerald-500/30 text-xs font-bold text-emerald-300 cursor-pointer"
                          >
                            Copy 100w
                          </button>
                        </div>
                        <p className="text-xs text-slate-200 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-white/[0.05]">
                          {kit.portal_form_fields.structured_project.description_100w}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Tab 3: Company Brief & 30-Second Elevator Pitch */}
                {activeTab === 'brief' && (
                  <div className="space-y-4">
                    <div className="glass-card rounded-2xl p-5 border border-white/[0.07] space-y-3">
                      <h4 className="text-xs font-extrabold uppercase tracking-wider text-blue-400">Role &amp; Hiring Team Brief</h4>
                      <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">{kit.company_brief?.summary}</p>
                      <div className="space-y-2 pt-2">
                        {(kit.company_brief?.key_focus_areas || []).map((area, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs text-slate-300">
                            <CheckCircle2 size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                            <span>{area}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="glass-card rounded-2xl p-5 border border-blue-500/30 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-extrabold uppercase tracking-wider text-amber-300">
                          Tailored 30-Second &ldquo;Tell Me About Yourself&rdquo; Pitch
                        </h4>
                        <button
                          type="button"
                          onClick={() => copyBlock(kit.company_brief?.elevator_pitch || '', 'Copied elevator pitch!')}
                          className="px-2.5 py-1 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-xs font-bold text-slate-200 flex items-center gap-1.5 transition cursor-pointer"
                        >
                          {copiedText === kit.company_brief?.elevator_pitch ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                          <span>Copy Pitch</span>
                        </button>
                      </div>
                      <p className="text-xs sm:text-sm text-white italic bg-slate-950/60 p-4 rounded-xl border border-white/[0.06] leading-relaxed">
                        &ldquo;{kit.company_brief?.elevator_pitch}&rdquo;
                      </p>
                    </div>
                  </div>
                )}

                {/* Tab 4: Reverse Questions & Salary Negotiation */}
                {activeTab === 'questions' && (
                  <div className="space-y-4">
                    <div className="glass-card rounded-2xl p-5 border border-white/[0.07] space-y-3">
                      <h4 className="text-xs font-extrabold uppercase tracking-wider text-purple-300 flex items-center gap-1.5">
                        <HelpCircle size={14} /> High-Signal Questions to Ask the Interviewer
                      </h4>
                      <div className="space-y-2">
                        {(kit.questions_to_ask || []).map((q, i) => (
                          <div
                            key={i}
                            onClick={() => copyBlock(q, 'Copied question!')}
                            className="p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.06] text-xs text-slate-200 flex items-center justify-between gap-3 cursor-pointer transition"
                          >
                            <span>{i + 1}. &ldquo;{q}&rdquo;</span>
                            <Copy size={12} className="text-slate-500 shrink-0" />
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="glass-card rounded-2xl p-5 border border-emerald-500/30 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-extrabold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                          <DollarSign size={14} /> Salary &amp; Offer Negotiation Script
                        </h4>
                        <button
                          type="button"
                          onClick={() => copyBlock(kit.salary_strategy?.script || '', 'Copied negotiation script!')}
                          className="px-2.5 py-1 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-xs font-bold text-slate-200 flex items-center gap-1.5 transition cursor-pointer"
                        >
                          <Copy size={12} />
                          <span>Copy Script</span>
                        </button>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">{kit.salary_strategy?.anchor_advice}</p>
                      <div className="p-3.5 rounded-xl bg-emerald-950/30 border border-emerald-500/25 text-xs text-emerald-200 italic leading-relaxed">
                        {kit.salary_strategy?.script}
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
