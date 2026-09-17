import { useEffect, useState } from 'react'
import PageWrapper from '../components/PageWrapper.jsx'
import Sidebar from '../components/Sidebar.jsx'
import client from '../api/client.js'
import { Settings as Cog, Mail, Shield, HelpCircle, CheckCircle } from 'lucide-react'

export default function Settings() {
  const [emailForm, setEmailForm] = useState({ smtp_host:'smtp.gmail.com', smtp_port:587, smtp_user:'', smtp_password:'', sender_name:'' })
  const [emailConfigured, setConfigured] = useState(false)
  const [emailMsg, setEmailMsg] = useState('')
  const [testMsg, setTestMsg]   = useState('')
  const [testing, setTesting]   = useState(false)

  useEffect(() => {
    client.get('/email/settings').then(r => {
      if (r.data.configured) {
        setConfigured(true)
        setEmailForm(f => ({...f, smtp_host: r.data.smtp_host || f.smtp_host,
          smtp_port: r.data.smtp_port || f.smtp_port,
          smtp_user: r.data.smtp_user || '', sender_name: r.data.sender_name || ''}))
      }
    }).catch(()=>{})
  }, [])

  const saveEmail = async () => {
    try {
      await client.post('/email/settings', emailForm)
      setEmailMsg('✅ Email settings saved!')
      setConfigured(true)
      setTimeout(()=>setEmailMsg(''), 3000)
    } catch(e) { setEmailMsg('❌ ' + (e.response?.data?.detail || 'Save failed')) }
  }

  const sendTest = async () => {
    setTesting(true); setTestMsg('')
    try {
      await client.post('/email/send', {
        to_email: emailForm.smtp_user, to_name: 'Me',
        subject: 'Job Searcher — Test Email ✅',
        body: 'This is a test email from your Job Searcher app. Email is configured correctly!',
        template_type: 'custom'
      })
      setTestMsg('✅ Test email sent to your inbox!')
    } catch(e) { setTestMsg('❌ ' + (e.response?.data?.detail || 'Test failed')) }
    setTesting(false)
  }

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="ml-60 flex-1 p-8 max-w-3xl">
        <h1 className="text-2xl font-bold mb-8">⚙️ Settings</h1>

        {/* Email Configuration */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6 fade-in">
          <div className="flex items-center gap-2 mb-1">
            <Mail size={18} className="text-blue-400"/>
            <h2 className="font-bold text-lg">Email Configuration</h2>
            {emailConfigured && <span className="ml-auto flex items-center gap-1 text-xs text-emerald-400"><CheckCircle size={14}/> Configured</span>}
          </div>
          <p className="text-slate-400 text-sm mb-5">Connect your Gmail to send job applications and outreach emails directly from the app.</p>

          {/* Gmail instructions */}
          <div className="bg-blue-900/20 border border-blue-800 rounded-xl p-4 mb-5">
            <div className="flex items-center gap-2 mb-2"><HelpCircle size={15} className="text-blue-400"/><span className="text-sm font-semibold text-blue-300">How to get a Gmail App Password</span></div>
            <ol className="text-xs text-slate-300 space-y-1 list-decimal ml-4">
              <li>Go to <span className="text-blue-400">myaccount.google.com/security</span></li>
              <li>Enable <strong>2-Step Verification</strong></li>
              <li>Search for <strong>"App passwords"</strong> at the top</li>
              <li>Create a new app password → Select <strong>Mail</strong> and <strong>Mac/Windows</strong></li>
              <li>Copy the 16-character code and paste it below as your password</li>
            </ol>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            {[['Your Full Name','sender_name','text','e.g. Yassine Youssef'],
              ['Gmail Address','smtp_user','email','your@gmail.com'],
              ['SMTP Host','smtp_host','text','smtp.gmail.com'],
              ['SMTP Port','smtp_port','number','587']].map(([label,key,type,ph])=>(
              <div key={key}>
                <label className="text-xs text-slate-400 mb-1 block">{label}</label>
                <input type={type} value={emailForm[key]} onChange={e=>setEmailForm({...emailForm,[key]:e.target.value})}
                  placeholder={ph} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"/>
              </div>
            ))}
            <div className="col-span-2">
              <label className="text-xs text-slate-400 mb-1 block">App Password <span className="text-slate-500">(16-character Gmail App Password)</span></label>
              <input type="password" value={emailForm.smtp_password} onChange={e=>setEmailForm({...emailForm,smtp_password:e.target.value})}
                placeholder="xxxx xxxx xxxx xxxx"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"/>
            </div>
          </div>

          {emailMsg && <p className="text-sm mb-3">{emailMsg}</p>}
          {testMsg  && <p className="text-sm mb-3">{testMsg}</p>}

          <div className="flex gap-3">
            <button onClick={saveEmail}
              className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-6 py-2.5 rounded-lg transition text-sm">
              Save Settings
            </button>
            {emailConfigured && (
              <button onClick={sendTest} disabled={testing}
                className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 px-6 py-2.5 rounded-lg transition text-sm">
                {testing ? 'Sending...' : '🧪 Send Test Email'}
              </button>
            )}
          </div>
        </div>

        {/* Security note */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in">
          <div className="flex items-center gap-2 mb-2"><Shield size={18} className="text-emerald-400"/><h2 className="font-bold">Privacy & Security</h2></div>
          <ul className="text-sm text-slate-400 space-y-2">
            <li>🔒 Your email password is stored locally in the database on your machine only</li>
            <li>🚫 No data is sent to any third-party servers</li>
            <li>📧 Emails are sent directly from your Gmail account via SMTP</li>
            <li>🗄️ All your data (jobs, CV, applications) stays on your computer</li>
          </ul>
        </div>
      </main>
    </div>
  </PageWrapper>
  )
}
