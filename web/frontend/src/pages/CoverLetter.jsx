import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import client, { getCached } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { parseApiError } from '../utils/jobUtils.js'
import { FileText, Copy, Mail, Check, Download, Sparkles, ClipboardList } from 'lucide-react'

const STYLES = [
  { key: 'professional', label: '🏢 Professional', desc: 'Formal & results-driven' },
  { key: 'casual',       label: '😊 Conversational', desc: 'Warm & enthusiastic' },
  { key: 'technical',    label: '⚙️ Technical',    desc: 'Architecture & skill-focused' },
]

export default function CoverLetter() {
  const toast = useToast()
  const [form, setForm] = useState({ job_title: '', company: '', job_description: '', style: 'professional' })
  const [letter, setLetter] = useState('')
  const [headline, setHeadline] = useState('')
  const [portalFields, setPortalFields] = useState(null)
  const [activeTab, setActiveTab] = useState('letter')
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [copiedKey, setCopiedKey] = useState('')
  const [cvUploaded, setCvUploaded] = useState(() => Boolean(getCached('/cv/info', null)?.uploaded))
  const [emailModal, setEmailModal] = useState(false)
  const [emailForm, setEmailForm] = useState({ to_email: '', to_name: '' })
  const [sending, setSending] = useState(false)
  const [sendMsg, setSendMsg] = useState('')

  useEffect(() => {
    client.get('/cv/info').then(r => setCvUploaded(Boolean(r.data?.uploaded))).catch(() => {})
  }, [])

  const generate = async () => {
    if (!form.job_title || !form.job_description) return
    setLoading(true); setError(''); setLetter('')
    try {
      const { data } = await client.post('/coverletter/generate', form)
      setLetter(data.letter)
      setHeadline(data.headline || '')
      setPortalFields(data.portal_form_fields || null)
      setSkills(data.skills_used || [])
      toast('Cover letter & portal form answers generated!', 'success')
    } catch (e) {
      setError(parseApiError(e, 'Generation failed'))
    } finally {
      setLoading(false)
    }
  }

  const copyField = (text, key, label = 'Text') => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    toast(`${label} copied!`, 'success')
    setTimeout(() => setCopiedKey(''), 1800)
  }

  const copyToClipboard = () => {
    if (!letter) return
    navigator.clipboard.writeText(letter)
    setCopied(true)
    toast('Cover letter copied to clipboard!', 'success')
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadTxt = () => {
    if (!letter) return
    const blob = new Blob([letter], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `cover_letter_${(form.company || 'draft').replace(/\s+/g, '_')}.txt`
    a.click()
    URL.revokeObjectURL(a.href)
    toast('Cover letter downloaded!', 'success')
  }

  const sendByEmail = async () => {
    if (!emailForm.to_email) return
    setSending(true); setSendMsg('')
    try {
      await client.post('/email/send', {
        to_email: emailForm.to_email,
        to_name: emailForm.to_name || 'Hiring Manager',
        subject: `Cover Letter — ${form.job_title} | Application`,
        body: letter,
        template_type: 'cover_letter'
      })
      setSendMsg('✅ Email sent successfully!')
      setTimeout(() => { setEmailModal(false); setSendMsg('') }, 2000)
    } catch (e) {
      setSendMsg('❌ ' + parseApiError(e, 'Send failed'))
    } finally {
      setSending(false)
    }
  }

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white">
        <Sidebar />
        <main className="md:ml-64 flex-1 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14 w-full">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <FileText size={20} />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight">AI Cover Letter Studio</h1>
              <p className="text-xs text-slate-400">Generate role-specific cover letters aligned with your uploaded resume</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Left: Configuration Form */}
            <div className="glass-card rounded-3xl p-6 relative overflow-hidden">
              <div className="glow-line-top" />
              <h2 className="font-extrabold text-sm uppercase tracking-wider text-slate-300 mb-4">
                Target Role & Tone
              </h2>

              {!cvUploaded && (
                <div className="bg-amber-950/40 border border-amber-500/30 text-amber-200 text-xs rounded-xl px-4 py-3 mb-4">
                  ⚠️ Upload your PDF resume in Post Hunter for personalized skill extraction.
                </div>
              )}

              <div className="space-y-4">
                {[
                  ['Job Title *', 'job_title', 'e.g. Senior Flutter Engineer'],
                  ['Company', 'company', 'e.g. Stripe']
                ].map(([label, key, ph]) => (
                  <div key={key}>
                    <label className="text-xs font-semibold text-slate-300 mb-1.5 block">{label}</label>
                    <input
                      value={form[key]}
                      onChange={e => setForm({ ...form, [key]: e.target.value })}
                      placeholder={ph}
                      className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
                    />
                  </div>
                ))}

                <div>
                  <label className="text-xs font-semibold text-slate-300 mb-1.5 block">Writing Tone</label>
                  <div className="grid grid-cols-3 gap-2">
                    {STYLES.map(s => (
                      <button
                        key={s.key}
                        type="button"
                        onClick={() => setForm({ ...form, style: s.key })}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          form.style === s.key
                            ? 'border-blue-500 bg-blue-600/20 text-white'
                            : 'border-white/[0.08] bg-slate-950/60 text-slate-300 hover:border-white/[0.18]'
                        }`}
                      >
                        <div className="text-xs font-bold">{s.label}</div>
                        <div className="text-[11px] text-slate-400 mt-0.5">{s.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-300 mb-1.5 block">Job Description *</label>
                  <textarea
                    value={form.job_description}
                    onChange={e => setForm({ ...form, job_description: e.target.value })}
                    rows={8}
                    placeholder="Paste the job description or recruiter post content here..."
                    className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition resize-none"
                  />
                </div>

                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={generate}
                  disabled={loading || !form.job_title || !form.job_description}
                  className="w-full shimmer-btn flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 text-white font-bold py-3 rounded-xl text-sm shadow-lg shadow-blue-600/25 transition cursor-pointer"
                >
                  {loading ? (
                    <LoadingSpinner label="Crafting cover letter..." />
                  ) : (
                    <>
                      <Sparkles size={16} className="text-amber-300" />
                      <span>Generate Tailored Cover Letter</span>
                    </>
                  )}
                </motion.button>
              </div>
            </div>

            {/* Right: Generated Document Output */}
            <div className="glass-card rounded-3xl p-6 relative overflow-hidden flex flex-col">
              <div className="glow-line-top" />
              <div className="flex items-center justify-between gap-2 flex-wrap mb-4">
                <div className="flex items-center gap-1.5 bg-slate-950/80 border border-white/[0.08] p-1 rounded-xl">
                  <button
                    type="button"
                    onClick={() => setActiveTab('letter')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                      activeTab === 'letter'
                        ? 'bg-blue-600 text-white shadow'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <FileText size={13} />
                    <span>Cover Letter</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab('portal')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                      activeTab === 'portal'
                        ? 'bg-indigo-600 text-white shadow'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <ClipboardList size={13} />
                    <span>Portal Form Answers</span>
                  </button>
                </div>
                {letter && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-slate-900/90 border border-white/[0.07] text-slate-300">
                      {letter.trim().split(/\s+/).filter(Boolean).length} words · 1-Page Standard
                    </span>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={copyToClipboard}
                      className="flex items-center gap-1.5 bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] px-3 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer"
                    >
                      {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                      <span>{copied ? 'Copied!' : 'Copy'}</span>
                    </motion.button>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={downloadTxt}
                      className="flex items-center gap-1.5 bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] px-3 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer"
                    >
                      <Download size={13} />
                      <span>Download .txt</span>
                    </motion.button>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => setEmailModal(true)}
                      className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-xl text-xs font-bold transition cursor-pointer"
                    >
                      <Mail size={13} />
                      <span>Send via Email</span>
                    </motion.button>
                  </div>
                )}
              </div>

              {error && (
                <div className="bg-rose-950/60 border border-rose-500/40 text-rose-200 text-xs rounded-xl px-4 py-3 mb-4">
                  {error}
                </div>
              )}

              {headline && (
                <div className="flex items-center justify-between gap-2 bg-indigo-950/40 border border-indigo-500/30 rounded-xl px-3.5 py-2 mb-3">
                  <div className="text-xs text-indigo-200 truncate">
                    <span className="font-bold text-indigo-400 mr-1.5">Application Headline:</span>
                    {headline}
                  </div>
                  <button
                    type="button"
                    onClick={() => copyField(headline, 'headline', 'Headline')}
                    className="text-[11px] font-bold text-indigo-300 hover:text-white bg-indigo-500/20 px-2.5 py-1 rounded-lg shrink-0 cursor-pointer"
                  >
                    {copiedKey === 'headline' ? '✓ Copied' : 'Copy'}
                  </button>
                </div>
              )}

              {skills.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mb-4">
                  <span className="text-[11px] font-bold text-slate-400">Grounded JD Skills:</span>
                  {skills.map(s => (
                    <span
                      key={s}
                      className="bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[11px] font-semibold px-2.5 py-0.5 rounded-lg"
                    >
                      ✓ {s}
                    </span>
                  ))}
                </div>
              )}

              {letter ? (
                activeTab === 'letter' ? (
                  <textarea
                    value={letter}
                    onChange={e => setLetter(e.target.value)}
                    rows={20}
                    className="w-full flex-1 bg-slate-950/90 border border-white/[0.08] rounded-2xl px-4 py-3 text-xs md:text-sm text-slate-100 focus:outline-none focus:border-blue-500 transition resize-none font-sans leading-relaxed"
                  />
                ) : (
                  <div className="space-y-4 overflow-y-auto max-h-[540px] pr-1">
                    {/* 1. Self-Introduction (130w + 70w) */}
                    {portalFields?.self_intro && (
                      <div className="bg-slate-950/80 border border-white/[0.08] rounded-2xl p-4 space-y-3">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <div className="text-xs font-extrabold text-white">1. Self-Introduction ("Tell us about yourself")</div>
                            <div className="text-[11px] text-slate-400">
                              Standard ~150w portal box ({portalFields.self_intro.full_words} words · {portalFields.self_intro.full_chars} chars)
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => copyField(portalFields.self_intro.full, 'intro_full', 'Self-Introduction')}
                            className="text-xs font-bold bg-blue-600/20 hover:bg-blue-600/35 border border-blue-500/30 text-blue-300 px-3 py-1 rounded-lg cursor-pointer"
                          >
                            {copiedKey === 'intro_full' ? '✓ Copied' : 'Copy 130w'}
                          </button>
                        </div>
                        <p className="text-xs text-slate-200 whitespace-pre-line leading-relaxed bg-slate-900/70 rounded-xl p-3 border border-white/[0.05]">
                          {portalFields.self_intro.full}
                        </p>
                        <div className="flex items-center justify-between gap-2 pt-1">
                          <span className="text-[11px] font-semibold text-slate-400">
                            Compact 500-char box variant ({portalFields.self_intro.short_words} words · {portalFields.self_intro.short_chars} chars)
                          </span>
                          <button
                            type="button"
                            onClick={() => copyField(portalFields.self_intro.short, 'intro_short', 'Short Self-Intro')}
                            className="text-[11px] font-bold bg-white/[0.06] hover:bg-white/[0.12] text-slate-300 px-2.5 py-1 rounded-lg cursor-pointer"
                          >
                            {copiedKey === 'intro_short' ? '✓ Copied' : 'Copy Short'}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* 2. 140-Char Stand-Out Pitches */}
                    {portalFields?.stand_out_pitches?.length > 0 && (
                      <div className="bg-slate-950/80 border border-white/[0.08] rounded-2xl p-4 space-y-2.5">
                        <div className="text-xs font-extrabold text-white">
                          2. 140-Character Stand-Out Pitch ("Why you in one sentence?")
                        </div>
                        {portalFields.stand_out_pitches.map((p, idx) => (
                          <div key={idx} className="bg-slate-900/70 border border-white/[0.05] rounded-xl p-3 flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-amber-300 bg-amber-500/15 px-2 py-0.5 rounded">
                                  {p.angle}
                                </span>
                                <span className="text-[10px] text-emerald-400 font-semibold">{p.chars}/140 chars</span>
                              </div>
                              <p className="text-xs text-slate-100 leading-snug">{p.text}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => copyField(p.text, `pitch_${idx}`, '140-char pitch')}
                              className="text-[11px] font-bold bg-white/[0.06] hover:bg-white/[0.12] text-slate-200 px-2.5 py-1 rounded-lg shrink-0 cursor-pointer"
                            >
                              {copiedKey === `pitch_${idx}` ? '✓' : 'Copy'}
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 3. Why This Company & Role */}
                    {portalFields?.why_company && (
                      <div className="bg-slate-950/80 border border-white/[0.08] rounded-2xl p-4 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <div className="text-xs font-extrabold text-white">3. "Why do you want to work at {form.company || 'this company'}?"</div>
                            <div className="text-[11px] text-slate-400">
                              Task-solving forward-looking framing ({portalFields.why_company.words} words · {portalFields.why_company.chars} chars)
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => copyField(portalFields.why_company.text, 'why_comp', 'Why Company answer')}
                            className="text-xs font-bold bg-blue-600/20 hover:bg-blue-600/35 border border-blue-500/30 text-blue-300 px-3 py-1 rounded-lg cursor-pointer"
                          >
                            {copiedKey === 'why_comp' ? '✓ Copied' : 'Copy'}
                          </button>
                        </div>
                        <p className="text-xs text-slate-200 leading-relaxed bg-slate-900/70 rounded-xl p-3 border border-white/[0.05]">
                          {portalFields.why_company.text}
                        </p>
                      </div>
                    )}

                    {/* 4. Structured Project Entry */}
                    {portalFields?.structured_project && (
                      <div className="bg-slate-950/80 border border-white/[0.08] rounded-2xl p-4 space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <div className="text-xs font-extrabold text-white">4. Structured Project / Experience Entry</div>
                            <div className="text-[11px] text-slate-400">
                              Grounded in your CV: {portalFields.structured_project.name} ({portalFields.structured_project.role})
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => copyField(portalFields.structured_project.description_100w, 'proj_100', 'Project description')}
                            className="text-xs font-bold bg-emerald-600/20 hover:bg-emerald-600/35 border border-emerald-500/30 text-emerald-300 px-3 py-1 rounded-lg cursor-pointer"
                          >
                            {copiedKey === 'proj_100' ? '✓ Copied' : 'Copy 100w'}
                          </button>
                        </div>
                        <p className="text-xs text-slate-200 leading-relaxed bg-slate-900/70 rounded-xl p-3 border border-white/[0.05]">
                          {portalFields.structured_project.description_100w}
                        </p>
                      </div>
                    )}
                  </div>
                )
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center min-h-[320px] text-slate-500">
                  <FileText size={44} className="mb-3 opacity-25" />
                  <p className="text-xs font-semibold text-slate-400">Enter role details and click Generate</p>
                </div>
              )}
            </div>
          </div>
        </main>

        {/* Send Email Modal */}
        {emailModal && (
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setEmailModal(false)}
          >
            <div
              className="glass-card rounded-3xl p-6 w-full max-w-sm relative overflow-hidden"
              onClick={e => e.stopPropagation()}
            >
              <div className="glow-line-top" />
              <h3 className="font-extrabold text-base mb-4">📧 Dispatch Cover Letter</h3>
              <div className="space-y-3 mb-4">
                {[
                  ['Recruiter Email *', 'to_email', 'email', 'recruiter@company.com'],
                  ['Recruiter Name', 'to_name', 'text', 'e.g. Sarah Jenkins']
                ].map(([l, k, t, ph]) => (
                  <div key={k}>
                    <label className="text-xs font-semibold text-slate-300 mb-1 block">{l}</label>
                    <input
                      type={t}
                      value={emailForm[k]}
                      onChange={e => setEmailForm({ ...emailForm, [k]: e.target.value })}
                      placeholder={ph}
                      className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition"
                    />
                  </div>
                ))}
              </div>
              {sendMsg && <p className="text-xs font-semibold mb-3">{sendMsg}</p>}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setEmailModal(false)}
                  className="flex-1 bg-white/[0.06] hover:bg-white/[0.1] py-2.5 rounded-xl text-xs font-semibold transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={sendByEmail}
                  disabled={sending || !emailForm.to_email}
                  className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 py-2.5 rounded-xl text-xs font-bold transition cursor-pointer"
                >
                  {sending ? 'Sending...' : 'Send →'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  )
}
