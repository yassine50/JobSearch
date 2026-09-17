import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import client from '../api/client.js'
import { Settings as SettingsIcon, Mail, User, Lock, Trash2, Plus, Eye, EyeOff, Save, Send } from 'lucide-react'

function Section({ title, icon: Icon, children }) {
  return (
    <motion.div
      initial={{opacity:0,y:16}} animate={{opacity:1,y:0}}
      className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-5">
      <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-700">
        <Icon size={17} className="text-blue-400"/>
        <h2 className="font-bold text-lg">{title}</h2>
      </div>
      {children}
    </motion.div>
  )
}

export default function Settings() {
  const { user, updateUser } = useAuth()
  const toast = useToast()

  // SMTP
  const [smtp, setSmtp]          = useState({ smtp_host:'smtp.gmail.com', smtp_port:587, smtp_user:'', smtp_password:'', sender_name:'' })
  const [showPass, setShowPass]  = useState(false)
  const [smtpSaving, setSmtpSaving] = useState(false)
  const [testing, setTesting]    = useState(false)

  // Profile
  const [profile, setProfile]    = useState({ name: user?.name || '', password:'', confirm:'' })
  const [profSaving, setProfSaving] = useState(false)

  // Custom templates
  const [templates, setTemplates] = useState([])
  const [newTpl, setNewTpl]       = useState({ name:'', subject:'', body:'' })
  const [addingTpl, setAddingTpl] = useState(false)
  const [tplSaving, setTplSaving] = useState(false)

  useEffect(() => {
    client.get('/email/settings').then(r => {
      if (r.data.configured) setSmtp(s => ({ ...s, ...r.data }))
    }).catch(()=>{})
    client.get('/email/custom-templates').then(r => setTemplates(r.data)).catch(()=>{})
  }, [])

  const saveSmtp = async () => {
    if (!smtp.smtp_user || !smtp.smtp_password) return toast('Fill all email fields','error')
    setSmtpSaving(true)
    try {
      await client.post('/email/settings', smtp)
      toast('Email settings saved!','success')
    } catch(e) { toast(e.response?.data?.detail||'Save failed','error') }
    setSmtpSaving(false)
  }

  const testEmail = async () => {
    setTesting(true)
    try {
      await client.post('/email/test')
      toast('Test email sent to your inbox! ✅','success')
    } catch(e) { toast(e.response?.data?.detail||'Test failed','error') }
    setTesting(false)
  }

  const saveProfile = async () => {
    if (!profile.name.trim()) return toast('Name cannot be empty','error')
    if (profile.password && profile.password !== profile.confirm)
      return toast('Passwords do not match','error')
    setProfSaving(true)
    try {
      const payload = { name: profile.name.trim() }
      if (profile.password) payload.password = profile.password
      const { data } = await client.patch('/auth/profile', payload)
      if (updateUser) updateUser({ name: data.name })
      toast('Profile updated!','success')
      setProfile(p => ({ ...p, password:'', confirm:'' }))
    } catch(e) { toast(e.response?.data?.detail||'Update failed','error') }
    setProfSaving(false)
  }

  const saveTemplate = async () => {
    if (!newTpl.name.trim() || !newTpl.body.trim()) return toast('Name and body required','error')
    setTplSaving(true)
    try {
      const { data } = await client.post('/email/custom-templates', newTpl)
      setTemplates(t => [data, ...t])
      setNewTpl({ name:'', subject:'', body:'' })
      setAddingTpl(false)
      toast('Template saved!','success')
    } catch(e) { toast('Failed to save template','error') }
    setTplSaving(false)
  }

  const deleteTemplate = async (id) => {
    try {
      await client.delete(`/email/custom-templates/${id}`)
      setTemplates(t => t.filter(x => x.id !== id))
      toast('Template deleted','info')
    } catch { toast('Delete failed','error') }
  }

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar/>
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8 max-w-3xl">
        <motion.div className="flex items-center gap-3 mb-7"
          initial={{opacity:0,x:-12}} animate={{opacity:1,x:0}} transition={{duration:.28}}>
          <SettingsIcon size={22} className="text-blue-400"/>
          <h1 className="text-2xl font-bold">Settings</h1>
        </motion.div>

        {/* Profile */}
        <Section title="Profile" icon={User}>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Display Name</label>
              <input value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name:e.target.value }))}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Email (read only)</label>
              <input value={user?.email||''} disabled
                className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-3.5 py-2.5 text-sm text-slate-500 cursor-not-allowed"/>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-slate-400 mb-1 block">New Password</label>
                <input type="password" value={profile.password}
                  onChange={e => setProfile(p => ({ ...p, password:e.target.value }))}
                  placeholder="Leave blank to keep current"
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-slate-600"/>
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">Confirm Password</label>
                <input type="password" value={profile.confirm}
                  onChange={e => setProfile(p => ({ ...p, confirm:e.target.value }))}
                  placeholder="Repeat new password"
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-slate-600"/>
              </div>
            </div>
            <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
              onClick={saveProfile} disabled={profSaving}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
              <Save size={15}/>{profSaving ? 'Saving…' : 'Save Profile'}
            </motion.button>
          </div>
        </Section>

        {/* Gmail SMTP */}
        <Section title="Email / Gmail Setup" icon={Mail}>
          <div className="space-y-4">
            <div className="bg-blue-900/20 border border-blue-700/30 rounded-xl p-3 text-xs text-blue-300">
              💡 Use a Gmail <strong>App Password</strong> (not your regular password).
              Go to <a href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer" className="underline">Google Account → Security → App Passwords</a>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-slate-400 mb-1 block">Sender Name</label>
                <input value={smtp.sender_name}
                  onChange={e => setSmtp(s => ({ ...s, sender_name:e.target.value }))}
                  placeholder="Your Full Name"
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-slate-600"/>
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">Gmail Address</label>
                <input value={smtp.smtp_user} type="email"
                  onChange={e => setSmtp(s => ({ ...s, smtp_user:e.target.value }))}
                  placeholder="you@gmail.com"
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-slate-600"/>
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">App Password</label>
              <div className="relative">
                <input value={smtp.smtp_password} type={showPass?'text':'password'}
                  onChange={e => setSmtp(s => ({ ...s, smtp_password:e.target.value }))}
                  placeholder="xxxx xxxx xxxx xxxx"
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-slate-600 pr-10"/>
                <button type="button" onClick={() => setShowPass(v=>!v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition">
                  {showPass ? <EyeOff size={16}/> : <Eye size={16}/>}
                </button>
              </div>
            </div>
            <div className="flex gap-3">
              <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                onClick={saveSmtp} disabled={smtpSaving}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
                <Save size={15}/>{smtpSaving ? 'Saving…' : 'Save Settings'}
              </motion.button>
              <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                onClick={testEmail} disabled={testing}
                className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 font-medium px-5 py-2.5 rounded-xl text-sm transition-colors">
                <Send size={15}/>{testing ? 'Sending…' : 'Send Test Email'}
              </motion.button>
            </div>
          </div>
        </Section>

        {/* Custom Email Templates */}
        <Section title="Custom Email Templates" icon={Mail}>
          <div className="space-y-3 mb-4">
            {templates.length === 0 && !addingTpl && (
              <p className="text-slate-500 text-sm text-center py-4">
                No custom templates yet. Create one below!
              </p>
            )}
            <AnimatePresence>
              {templates.map(t => (
                <motion.div key={t.id}
                  initial={{opacity:0,y:-8}} animate={{opacity:1,y:0}} exit={{opacity:0,height:0}}
                  className="flex items-center gap-3 p-3.5 bg-slate-900 border border-slate-700 rounded-xl">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{t.name}</p>
                    <p className="text-xs text-slate-400 truncate">{t.subject}</p>
                  </div>
                  <button onClick={() => deleteTemplate(t.id)}
                    className="text-red-400 hover:text-red-300 transition p-1">
                    <Trash2 size={15}/>
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          <AnimatePresence>
            {addingTpl && (
              <motion.div
                initial={{opacity:0,y:-8}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-8}}
                className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3 mb-4">
                <input value={newTpl.name}
                  onChange={e => setNewTpl(t => ({ ...t, name:e.target.value }))}
                  placeholder="Template name (e.g. 'Startup Outreach')"
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                <input value={newTpl.subject}
                  onChange={e => setNewTpl(t => ({ ...t, subject:e.target.value }))}
                  placeholder="Subject line"
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                <textarea value={newTpl.body}
                  onChange={e => setNewTpl(t => ({ ...t, body:e.target.value }))}
                  rows={6} placeholder="Email body..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none font-mono"/>
                <div className="flex gap-2">
                  <motion.button whileTap={{scale:.96}} onClick={saveTemplate} disabled={tplSaving}
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-4 py-2 rounded-xl text-sm transition-colors">
                    <Save size={14}/>{tplSaving?'Saving…':'Save Template'}
                  </motion.button>
                  <button onClick={() => setAddingTpl(false)}
                    className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-xl text-sm transition-colors">
                    Cancel
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {!addingTpl && (
            <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
              onClick={() => setAddingTpl(true)}
              className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors">
              <Plus size={15}/> New Template
            </motion.button>
          )}
        </Section>

      </main>
    </div>
    </PageWrapper>
  )
}
