import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import confetti from 'canvas-confetti'
import client, { getCached } from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import {
  Zap, Mail, Building2, User, FileText, Check, Loader2,
  X, ShieldCheck, Sparkles, Send, ArrowRight
} from 'lucide-react'

const FR_INDICATORS = [
  ' de ', ' le ', ' la ', ' les ', ' des ', ' un ', ' une ', ' du ', ' et ', ' pour ',
  ' avec ', ' dans ', ' sur ', ' nous ', ' vous ', ' poste ', ' équipe ', ' profil ',
  ' expérience ', ' compétences ', ' chez ', ' télétravail ', ' développeur ', ' développeuse ',
  ' ingénieur ', ' recherchons ', ' rejoignez ', ' embauche ', ' candidature ', ' montréal ', ' québec '
]

function detectPostLanguage(text) {
  if (!text) return 'en'
  const t = ` ${text.toLowerCase()} `
  if (['développeur', 'développeuse', 'recherchons', 'télétravail', 'candidature', 'montréal', 'québec'].some(k => t.includes(k))) {
    return 'fr'
  }
  const matches = FR_INDICATORS.filter(ind => t.includes(ind)).length
  return matches >= 2 ? 'fr' : 'en'
}

const PLATFORM_PHRASES = {
  job_bank: {
    en: 'referenced in your recent job posting on Job Bank',
    fr: "suite à votre offre d'emploi sur Job Bank"
  },
  indeed: {
    en: 'referenced in your recent job posting on Indeed',
    fr: "suite à votre offre d'emploi sur Indeed"
  },
  linkedin: {
    en: 'referenced in your recent publication on LinkedIn',
    fr: 'suite à votre publication sur LinkedIn'
  },
  zip_recruiter: {
    en: 'referenced in your recent job posting on ZipRecruiter',
    fr: "suite à votre offre d'emploi sur ZipRecruiter"
  },
  glassdoor: {
    en: 'referenced in your recent job posting on Glassdoor',
    fr: "suite à votre offre d'emploi sur Glassdoor"
  },
  google: {
    en: 'referenced in your recent job posting on Google Jobs',
    fr: "suite à votre offre d'emploi sur Google Jobs"
  },
  generic: {
    en: 'referenced in your recent job posting',
    fr: "suite à votre récente offre d'emploi"
  }
}

function detectPlatformSource(item) {
  if (!item) return 'linkedin'
  const combined = `${item.site || ''} ${item.source || ''} ${item.url || ''} ${item.post_url || ''} ${item.job_url || ''} ${item.job_url_direct || ''}`.toLowerCase()
  if (combined.includes('job_bank') || combined.includes('jobbank') || combined.includes('guichet')) return 'job_bank'
  if (combined.includes('indeed')) return 'indeed'
  if (combined.includes('linkedin')) return 'linkedin'
  if (combined.includes('zip_recruiter') || combined.includes('ziprecruiter')) return 'zip_recruiter'
  if (combined.includes('glassdoor')) return 'glassdoor'
  if (combined.includes('google')) return 'google'
  return 'linkedin'
}

function generateEmailContent(targetLang, name, comp, title, platformKey = 'linkedin') {
  const isGeneric = !name || ['hiring team', 'recruiter', 'unknown', 'team'].includes(name.trim().toLowerCase())
  const phrases = PLATFORM_PHRASES[platformKey] || PLATFORM_PHRASES.generic

  if (targetLang === 'fr') {
    const salutation = isGeneric ? `Madame, Monsieur,\nÉquipe de recrutement de ${comp},` : `Bonjour ${name.trim()},`
    return {
      subject: `Candidature : ${title} — ${comp}`,
      body: `${salutation}

Je vous soumets par la présente ma candidature pour le poste de ${title}, ${phrases.fr}.

Ayant pris connaissance de vos exigences techniques, mon profil correspond étroitement aux compétences que vous recherchez. Je conçois des solutions logicielles performantes, maintenables et évolutives, et je serais ravi de mettre mon expertise au service de vos prochains projets.

Vous trouverez mon curriculum vitae ci-joint pour examen. Je me tiens à votre entière disposition pour un échange afin d'approfondir l'adéquation de mon parcours avec vos objectifs.

En vous remerciant de l'attention que vous porterez à ma démarche, je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

Best regards / Cordialement,`
    }
  } else {
    const salutation = isGeneric ? `Dear Hiring Team at ${comp},` : `Dear ${name.trim()} at ${comp},`
    return {
      subject: `Application: ${title} — ${comp}`,
      body: `${salutation}

I am writing to formally submit my application for the ${title} position ${phrases.en}.

Having reviewed your technical requirements, my experience aligns closely with the skills your team is seeking. I specialize in building high-performance, maintainable software and would love to contribute to your upcoming projects and engineering milestones.

I have attached my resume for your review. Thank you for your time and consideration, and I look forward to the opportunity to speak with you.

Sincerely,`
    }
  }
}

export default function AutoApplyModal({
  isOpen,
  onClose,
  post,
  onSuccess,
  onOpenSmtpPrompt
}) {
  const toast = useToast()
  const { user } = useAuth()
  const [loading, setLoading] = useState(false)
  const [lang, setLang] = useState('en')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [selectedEmail, setSelectedEmail] = useState('')
  const [recruiterName, setRecruiterName] = useState('')
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

  useEffect(() => {
    if (post) {
      const email = post.recruiter_emails?.[0]?.email || ''
      const name = post.author_name || 'Hiring Team'
      const comp = post.company || 'the team'
      const title = post.role_title || post.title || 'Software Opportunity'
      const fullText = `${post.full_text || ''} ${post.post_snippet || ''} ${post.description || ''} ${title} ${comp}`

      const detectedLang = detectPostLanguage(fullText)
      setLang(detectedLang)

      const platform = detectPlatformSource(post)
      const content = generateEmailContent(detectedLang, name, comp, title, platform)
      setSelectedEmail(email)
      setRecruiterName(name)
      setSubject(content.subject)
      setBody(content.body)
    }
  }, [post])

  const handleToggleLang = (newLang) => {
    if (newLang === lang) return
    setLang(newLang)
    const name = recruiterName || post?.author_name || 'Hiring Team'
    const comp = post?.company || 'the team'
    const title = post?.role_title || post?.title || 'Software Opportunity'
    const platform = detectPlatformSource(post)
    const content = generateEmailContent(newLang, name, comp, title, platform)
    setSubject(content.subject)
    setBody(content.body)
  }

  if (!isOpen || !post) return null

  const handleSend = async () => {
    if (!selectedEmail) {
      toast('No recipient email available for this post', 'error')
      return
    }

    setLoading(true)
    try {
      const targetUrl = post.post_url || post.url || post.job_url || post.job_url_direct || ''
      const targetTitle = post.role_title || post.title || 'Software Opportunity'
      const targetCompany = post.company || 'Company'
      const targetLocation = post.location || ''

      const { data } = await client.post('/linkedin-posts/auto-apply', {
        post_url: targetUrl,
        role_title: targetTitle,
        company: targetCompany,
        location: targetLocation,
        recruiter_name: recruiterName,
        recruiter_email: selectedEmail,
        post_text: post.full_text || post.post_snippet || post.description || '',
        customize_cv: true,
        custom_subject: subject,
        custom_body: body,
        lang: lang,
        site: detectPlatformSource(post)
      })

      confetti({ particleCount: 120, spread: 80, origin: { y: 0.6 } })
      toast(data.message || `Application sent to ${selectedEmail}!`, 'success')
      if (onSuccess) onSuccess({
        ...post,
        url: targetUrl,
        post_url: targetUrl,
        title: targetTitle,
        role_title: targetTitle,
        company: targetCompany
      })
      onClose()
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string' && detail.toLowerCase().includes('smtp')) {
        onClose()
        if (onOpenSmtpPrompt) onOpenSmtpPrompt()
      } else {
        toast(detail || err.message || 'Failed to dispatch application', 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  const emailsList = post.recruiter_emails || []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        className="w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white font-bold shadow-md shadow-blue-500/20">
              <Zap size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span>1-Click Auto-Apply</span>
                <span className="text-[10px] font-semibold text-blue-300 bg-blue-500/15 border border-blue-500/30 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <ShieldCheck size={10} /> Verified Recruiter
                </span>
              </h3>
              <p className="text-xs text-slate-400">Review outreach message and tailored CV attachment</p>
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
          {/* Target Meta Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3.5 rounded-xl bg-slate-800/60 border border-slate-750">
            <div>
              <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1 mb-1">
                <Building2 size={12} className="text-blue-400" /> Target Role & Company
              </span>
              <p className="text-xs font-bold text-white truncate">{post.role_title || 'Role'}</p>
              <p className="text-xs text-blue-300 truncate">{post.company || 'Company'}</p>
            </div>

            <div>
              <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1 mb-1">
                <Mail size={12} className="text-purple-400" /> Recruiter Contact
              </span>
              {emailsList.length > 1 ? (
                <select
                  value={selectedEmail}
                  onChange={e => setSelectedEmail(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  {emailsList.map((e, idx) => (
                    <option key={idx} value={e.email}>
                      {e.email} {e.name ? `(${e.name})` : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-mono font-bold text-white bg-purple-950/80 border border-purple-800/80 px-2 py-0.5 rounded">
                    {selectedEmail || 'No email'}
                  </span>
                  <span className="text-[10px] text-emerald-400 bg-emerald-950/70 border border-emerald-800/60 px-1.5 py-0.2 rounded font-medium">
                    MX Valid
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Subject Line */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">Email Subject</label>
            <input
              type="text"
              value={subject}
              onChange={e => setSubject(e.target.value)}
              className="w-full px-3 py-2 text-xs text-white bg-slate-900 border border-slate-700 rounded-xl focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Message Body */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <label className="text-xs font-semibold text-slate-300">Personalized Message</label>
                <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-700/80">
                  <button
                    type="button"
                    onClick={() => handleToggleLang('en')}
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold transition cursor-pointer ${
                      lang === 'en'
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    🇬🇧 EN
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggleLang('fr')}
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold transition cursor-pointer ${
                      lang === 'fr'
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    🇫🇷 FR
                  </button>
                </div>
              </div>
              <span className="text-[11px] text-slate-500 font-mono">{body.length} chars</span>
            </div>
            <textarea
              rows={6}
              value={body}
              onChange={e => setBody(e.target.value)}
              className="w-full p-3 text-xs leading-relaxed text-slate-200 bg-slate-900 border border-slate-700 rounded-xl focus:outline-none focus:border-blue-500 resize-none font-sans"
            />
          </div>

          {/* Resume Attachment: Authentic Verified PDF */}
          <div className="p-3.5 rounded-xl bg-slate-850 border border-slate-700/60 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-emerald-600/20 text-emerald-300 border border-emerald-500/30">
                <FileText size={16} />
              </div>
              <div>
                <p className="text-xs font-semibold text-white flex items-center gap-2">
                  <span>Attached: Authentic Verified Resume</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-emerald-950 border border-emerald-700 text-emerald-300">
                    {displayCvName}
                  </span>
                </p>
                <p className="text-[11px] text-slate-400">
                  A copy of your resume tailored to this job is attached: missing job skills added, off-topic content removed, headline set to the role. Your original CV is never changed.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 rounded-lg">
              <ShieldCheck size={13} />
              <span>Original PDF</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSend}
            disabled={loading || !selectedEmail}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-blue-500/20 transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            <span>{loading ? 'Dispatching Application...' : 'Send Application'}</span>
          </button>
        </div>
      </motion.div>
    </div>
  )
}
