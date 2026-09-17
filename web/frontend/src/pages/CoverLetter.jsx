import { useEffect, useState } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import client from '../api/client.js'
import { FileText, Copy, Mail, Check } from 'lucide-react'

const STYLES = [
  { key:'professional', label:'🏢 Professional', desc:'Formal & results-driven' },
  { key:'casual',       label:'😊 Casual',       desc:'Friendly & enthusiastic' },
  { key:'technical',    label:'⚙️ Technical',    desc:'Skill-focused & precise'  },
]

export default function CoverLetter() {
  const [form, setForm]       = useState({ job_title:'', company:'', job_description:'', style:'professional' })
  const [letter, setLetter]   = useState('')
  const [skills, setSkills]   = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [copied, setCopied]   = useState(false)
  const [cvUploaded, setCvUploaded] = useState(false)
  const [emailModal, setEmailModal] = useState(false)
  const [emailForm, setEmailForm]   = useState({ to_email:'', to_name:'' })
  const [sending, setSending] = useState(false)
  const [sendMsg, setSendMsg] = useState('')

  useEffect(() => {
    client.get('/cv/info').then(r => setCvUploaded(r.data.uploaded)).catch(()=>{})
  }, [])

  const generate = async () => {
    if (!form.job_title || !form.job_description) return
    setLoading(true); setError(''); setLetter('')
    try {
      const { data } = await client.post('/coverletter/generate', form)
      setLetter(data.letter); setSkills(data.skills_used || [])
    } catch(e) { setError(e.response?.data?.detail || 'Generation failed') }
    setLoading(false)
  }

  const copy = () => {
    navigator.clipboard.writeText(letter)
    setCopied(true); setTimeout(()=>setCopied(false), 2000)
  }

  const sendByEmail = async () => {
    if (!emailForm.to_email) return
    setSending(true); setSendMsg('')
    try {
      await client.post('/email/send', {
        to_email: emailForm.to_email, to_name: emailForm.to_name || 'Hiring Manager',
        subject: `Cover Letter — ${form.job_title} | Application`,
        body: letter, template_type: 'cover_letter'
      })
      setSendMsg('✅ Email sent successfully!')
      setTimeout(()=>{ setEmailModal(false); setSendMsg('') }, 2000)
    } catch(e) { setSendMsg('❌ ' + (e.response?.data?.detail || 'Send failed')) }
    setSending(false)
  }

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="ml-60 flex-1 p-8">
        <h1 className="text-2xl font-bold mb-6">📝 Cover Letter Generator</h1>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: form */}
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in">
            <h2 className="font-semibold mb-4 text-slate-300">Job Details</h2>

            {!cvUploaded && (
              <div className="bg-yellow-900/30 border border-yellow-700 text-yellow-300 text-sm rounded-lg px-4 py-3 mb-4">
                ⚠️ Upload your CV in Job Search for better personalization
              </div>
            )}

            <div className="space-y-4">
              {[['Job Title *','job_title','e.g. Senior Python Developer'],
                ['Company *','company','e.g. Google']].map(([label,key,ph])=>(
                <div key={key}>
                  <label className="text-xs text-slate-400 mb-1 block">{label}</label>
                  <input value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})} placeholder={ph}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"/>
                </div>
              ))}

              <div>
                <label className="text-xs text-slate-400 mb-1 block">Writing Style</label>
                <div className="grid grid-cols-3 gap-2">
                  {STYLES.map(s=>(
                    <button key={s.key} onClick={()=>setForm({...form,style:s.key})}
                      className={`p-3 rounded-xl border text-left transition ${form.style===s.key ? 'border-blue-500 bg-blue-900/30' : 'border-slate-700 hover:border-slate-500'}`}>
                      <div className="text-sm font-medium">{s.label}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{s.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-400 mb-1 block">Job Description *</label>
                <textarea value={form.job_description} onChange={e=>setForm({...form,job_description:e.target.value})}
                  rows={8} placeholder="Paste the full job description here..."
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition resize-none"/>
              </div>

              <button onClick={generate} disabled={loading || !form.job_title || !form.job_description}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-lg transition">
                {loading ? <LoadingSpinner label="Generating..." /> : <><FileText size={16}/> Generate Cover Letter</>}
              </button>
            </div>
          </div>

          {/* Right: output */}
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-300">Generated Letter</h2>
              {letter && (
                <div className="flex gap-2">
                  <button onClick={copy}
                    className="flex items-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-sm px-3 py-1.5 rounded-lg transition">
                    {copied ? <><Check size={14} className="text-emerald-400"/> Copied!</> : <><Copy size={14}/> Copy</>}
                  </button>
                  <button onClick={()=>setEmailModal(true)}
                    className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-sm px-3 py-1.5 rounded-lg transition">
                    <Mail size={14}/> Send Email
                  </button>
                </div>
              )}
            </div>

            {error && <div className="bg-red-900/60 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3 mb-4">{error}</div>}

            {skills.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-4">
                <span className="text-xs text-slate-400">Skills matched:</span>
                {skills.map(s=><span key={s} className="bg-emerald-900 text-emerald-300 text-xs px-2 py-0.5 rounded-full">{s}</span>)}
              </div>
            )}

            {letter ? (
              <textarea value={letter} onChange={e=>setLetter(e.target.value)} rows={22}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition resize-none font-mono leading-relaxed"/>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-slate-600">
                <FileText size={48} className="mb-3 opacity-30"/>
                <p>Fill the form and click Generate</p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Send email modal */}
      {emailModal && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={()=>setEmailModal(false)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-sm" onClick={e=>e.stopPropagation()}>
            <h3 className="font-bold text-lg mb-4">📧 Send Cover Letter</h3>
            <div className="space-y-3 mb-4">
              {[['Recruiter Email *','to_email','email','recruiter@company.com'],
                ['Recruiter Name','to_name','text','e.g. John Smith']].map(([l,k,t,ph])=>(
                <div key={k}>
                  <label className="text-xs text-slate-400 mb-1 block">{l}</label>
                  <input type={t} value={emailForm[k]} onChange={e=>setEmailForm({...emailForm,[k]:e.target.value})}
                    placeholder={ph} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"/>
                </div>
              ))}
            </div>
            {sendMsg && <p className="text-sm mb-3">{sendMsg}</p>}
            <div className="flex gap-2">
              <button onClick={()=>setEmailModal(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 py-2 rounded-lg text-sm transition">Cancel</button>
              <button onClick={sendByEmail} disabled={sending || !emailForm.to_email}
                className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 py-2 rounded-lg text-sm font-semibold transition">
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
