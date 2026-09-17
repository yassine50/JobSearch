import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import client from '../api/client.js'

export default function Login() {
  const { login } = useAuth()
  const navigate   = useNavigate()
  const [tab, setTab]   = useState('login')
  const [err, setErr]   = useState('')
  const [busy, setBusy] = useState(false)

  const [lf, setLf] = useState({ email:'', password:'' })
  const [rf, setRf] = useState({ name:'', email:'', password:'', role:'seeker' })

  const doLogin = async () => {
    setBusy(true); setErr('')
    try {
      const { data } = await client.post('/auth/login', lf)
      login(data.access_token, data.user)
      navigate('/dashboard')
    } catch(e) { setErr(e.response?.data?.detail || 'Login failed') }
    setBusy(false)
  }

  const doRegister = async () => {
    setBusy(true); setErr('')
    try {
      const { data } = await client.post('/auth/register', rf)
      login(data.access_token, data.user)
      navigate('/dashboard')
    } catch(e) { setErr(e.response?.data?.detail || 'Registration failed') }
    setBusy(false)
  }

  return (
    <div className="min-h-screen px-4  flex">
      {/* LEFT HERO */}
      <div className="hidden lg:flex flex-col justify-center w-1/2 bg-gradient-to-br from-slate-900 via-slate-800 to-blue-950 px-16 py-12 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-600 opacity-10 rounded-full -translate-x-1/2 -translate-y-1/2 pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-80 h-80 bg-purple-600 opacity-10 rounded-full translate-x-1/3 translate-y-1/3 pointer-events-none" />
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center text-2xl font-bold">J</div>
            <span className="text-2xl font-bold">Job Searcher</span>
          </div>
          <h1 className="text-4xl font-extrabold leading-tight mb-4">
            Smarter Hiring.<br /><span className="text-blue-400">Powered by AI.</span>
          </h1>
          <p className="text-slate-400 text-lg mb-10">One platform for job seekers and recruiters. Find the right match — instantly.</p>

          {[
            { icon:'🤖', title:'AI-Powered Matching', sub:'6-factor scoring engine' },
            { icon:'👔', title:'Recruiter Mode',      sub:'Source & rank candidates' },
            { icon:'📧', title:'Email Automation',    sub:'Personalized outreach' },
          ].map(f => (
            <div key={f.title} className="flex items-center gap-3 bg-slate-800/60 border border-slate-700/50 rounded-xl px-4 py-3 mb-3">
              <span className="text-2xl">{f.icon}</span>
              <div>
                <p className="font-semibold text-sm">{f.title}</p>
                <p className="text-slate-400 text-xs">{f.sub}</p>
              </div>
            </div>
          ))}

          <div className="mt-8 bg-slate-800/70 border border-slate-700 rounded-2xl p-5">
            <p className="text-xs text-slate-400 mb-3">Top Candidates — AI Ranked</p>
            {[['Sarah J. — Full Stack Dev','88%','emerald'],['Michael C. — Frontend Dev','82%','emerald'],['Emily R. — Backend Dev','76%','yellow']].map(([name,score,c])=>(
              <div key={name} className="flex justify-between items-center py-1.5">
                <span className="text-sm">{name}</span>
                <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full bg-${c}-900 text-${c}-300 border border-${c}-700`}>{score}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT AUTH */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-slate-900">
        <div className="w-full w-full max-w-md">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center font-bold">J</div>
            <span className="text-xl font-bold">Job Searcher</span>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 shadow-2xl">
            {/* Tabs */}
            <div className="flex bg-slate-900 rounded-xl p-1 mb-6">
              {['login','register'].map(t => (
                <button key={t} onClick={() => { setTab(t); setErr('') }}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors
                    ${tab===t ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}`}>
                  {t === 'login' ? 'Sign In' : 'Create Account'}
                </button>
              ))}
            </div>

            {err && <div className="bg-red-900/60 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3 mb-4">{err}</div>}

            {tab === 'login' ? (
              <div className="fade-in">
                <h2 className="text-xl font-bold mb-1">Welcome back</h2>
                <p className="text-slate-400 text-sm mb-6">Sign in to your account</p>
                <div className="space-y-4">
                  {[['Email','email','email',lf.email,v=>setLf({...lf,email:v})],
                    ['Password','password','password',lf.password,v=>setLf({...lf,password:v})]].map(([label,id,type,val,set])=>(
                    <div key={id}>
                      <label className="text-sm text-slate-300 mb-1 block">{label}</label>
                      <input type={type} value={val} onChange={e=>set(e.target.value)}
                        onKeyDown={e=>e.key==='Enter'&&doLogin()}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition" />
                    </div>
                  ))}
                  <button onClick={doLogin} disabled={busy}
                    className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-lg transition text-sm flex items-center justify-center gap-2">
                    {busy ? <><span className="spinner" style={{width:16,height:16,borderWidth:2}} />Signing in...</> : 'Sign In →'}
                  </button>
                </div>
                <p className="text-center text-slate-400 text-sm mt-5">
                  No account? <button onClick={()=>setTab('register')} className="text-blue-400 hover:underline">Create one free</button>
                </p>
              </div>
            ) : (
              <div className="fade-in">
                <h2 className="text-xl font-bold mb-1">Get started free</h2>
                <p className="text-slate-400 text-sm mb-6">Create your account</p>
                <div className="space-y-4">
                  {[['Full Name','name','text',rf.name,v=>setRf({...rf,name:v})],
                    ['Email','email','email',rf.email,v=>setRf({...rf,email:v})],
                    ['Password','password','password',rf.password,v=>setRf({...rf,password:v})]].map(([label,id,type,val,set])=>(
                    <div key={id}>
                      <label className="text-sm text-slate-300 mb-1 block">{label}</label>
                      <input type={type} value={val} onChange={e=>set(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition" />
                    </div>
                  ))}
                  <div>
                    <label className="text-sm text-slate-300 mb-1 block">I am a</label>
                    <select value={rf.role} onChange={e=>setRf({...rf,role:e.target.value})}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition">
                      <option value="seeker">Job Seeker</option>
                      <option value="recruiter">Recruiter / HR</option>
                      <option value="both">Both</option>
                    </select>
                  </div>
                  <button onClick={doRegister} disabled={busy}
                    className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-lg transition text-sm flex items-center justify-center gap-2">
                    {busy ? <><span className="spinner" style={{width:16,height:16,borderWidth:2}} />Creating...</> : 'Create Account →'}
                  </button>
                </div>
                <p className="text-center text-slate-400 text-sm mt-5">
                  Already have an account? <button onClick={()=>setTab('login')} className="text-blue-400 hover:underline">Sign in</button>
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
