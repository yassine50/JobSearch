import { useEffect, useRef, useState } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import client from '../api/client.js'
import { Upload, Search, ExternalLink, Bookmark, ChevronDown } from 'lucide-react'

const SITES   = ['linkedin','indeed','glassdoor','zip_recruiter']
const COUNTRIES = ['USA','UK','Canada','Australia','France','Germany','Netherlands','Spain','Switzerland','UAE','India','Morocco']

export default function Seeker() {
  const [form, setForm] = useState({
    title:'', location:'', country:'USA', results:20, hours:168, sites:['linkedin','indeed']
  })
  const [cvInfo, setCvInfo]   = useState({ uploaded:false })
  const [jobs, setJobs]       = useState([])
  const [loading, setLoading] = useState(false)
  const [matching, setMatch]  = useState(false)
  const [error, setError]     = useState('')
  const [modal, setModal]     = useState(null)
  const [cvMsg, setCvMsg]     = useState('')
  const fileRef = useRef()

  useEffect(() => {
    client.get('/cv/info').then(r => setCvInfo(r.data)).catch(() => {})
  }, [])

  const toggleSite = (s) => setForm(f => ({
    ...f, sites: f.sites.includes(s) ? f.sites.filter(x=>x!==s) : [...f.sites,s]
  }))

  const uploadCv = async (e) => {
    const file = e.target.files[0]; if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      const { data } = await client.post('/cv/upload', fd, { headers:{'Content-Type':'multipart/form-data'} })
      setCvInfo({ uploaded:true, filename:data.filename, words:data.words })
      setCvMsg(`✅ ${data.filename} uploaded (${data.words} words)`)
      setTimeout(()=>setCvMsg(''), 4000)
    } catch(e) { setCvMsg('❌ Upload failed: '+e.response?.data?.detail) }
  }

  const searchJobs = async () => {
    if (!form.title.trim()) return
    setLoading(true); setError(''); setJobs([])
    try {
      const { data } = await client.post('/jobs/search', {
        title: form.title, location: form.location, country: form.country,
        sites: form.sites, results_wanted: Number(form.results), hours_old: Number(form.hours)
      })
      setJobs(data.jobs)
      if (cvInfo.uploaded && data.jobs.length > 0) matchAll(data.jobs)
    } catch(e) { setError(e.response?.data?.detail || 'Search failed. Is the backend running?') }
    setLoading(false)
  }

  const matchAll = async (jobList) => {
    setMatch(true)
    const updated = [...jobList]
    for (let i = 0; i < updated.length; i++) {
      if (!updated[i].description) continue
      try {
        const { data } = await client.post('/cv/match', {
          job_description: updated[i].description, job_title: updated[i].title
        })
        updated[i] = { ...updated[i], score: data.score, breakdown: data.breakdown,
          matched_skills: data.breakdown?.matched_tech || [],
          missing_skills: data.breakdown?.missing_tech || [],
          tips: data.breakdown?.tips || [] }
      } catch {}
    }
    updated.sort((a,b) => (b.score||0)-(a.score||0))
    setJobs([...updated])
    setMatch(false)
  }

  const saveJob = async (j) => {
    try {
      await client.post('/jobs/save', { title:j.title, company:j.company, location:j.location, url:j.url, description:j.description, match_score:j.score||0 })
      alert('✅ Job saved to dashboard!')
    } catch(e) { alert('Save failed: '+e.response?.data?.detail) }
  }

  return (
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="ml-60 flex-1 p-8">
        <h1 className="text-2xl font-bold mb-6">🔎 Job Search</h1>

        {/* Search form */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6 fade-in">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
            {[
              ['Job Title *','text','title','e.g. Python Developer'],
              ['Location','text','location','e.g. New York, Remote'],
            ].map(([label,type,key,ph])=>(
              <div key={key}>
                <label className="text-xs text-slate-400 mb-1 block">{label}</label>
                <input type={type} placeholder={ph} value={form[key]}
                  onChange={e=>setForm({...form,[key]:e.target.value})}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition" />
              </div>
            ))}
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Country</label>
              <select value={form.country} onChange={e=>setForm({...form,country:e.target.value})}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition">
                {COUNTRIES.map(c=><option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Results</label>
              <select value={form.results} onChange={e=>setForm({...form,results:e.target.value})}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition">
                {[10,20,30,50].map(n=><option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Posted Within</label>
              <select value={form.hours} onChange={e=>setForm({...form,hours:e.target.value})}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition">
                {[[24,'24 hours'],[72,'3 days'],[168,'7 days'],[720,'30 days']].map(([v,l])=><option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-2 block">Job Boards</label>
              <div className="flex flex-wrap gap-3">
                {SITES.map(s=>(
                  <label key={s} className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
                    <input type="checkbox" checked={form.sites.includes(s)} onChange={()=>toggleSite(s)}
                      className="accent-blue-500 w-4 h-4" />
                    <span className="capitalize">{s.replace('_',' ')}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* CV upload */}
          <div className="border-t border-slate-700 pt-4 mb-4 flex items-center gap-4 flex-wrap">
            <div>
              <p className="text-xs text-slate-400">Your CV (for AI Match %)</p>
              <p className="text-sm mt-0.5">{cvInfo.uploaded ? `✓ ${cvInfo.filename} (${cvInfo.words} words)` : 'No CV uploaded'}</p>
            </div>
            <button onClick={()=>fileRef.current.click()}
              className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-sm px-4 py-2 rounded-lg transition">
              <Upload size={15} />
              {cvInfo.uploaded ? 'Replace CV' : 'Upload CV'}
            </button>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" onChange={uploadCv} className="hidden" />
            {cvMsg && <span className="text-sm text-emerald-400">{cvMsg}</span>}
          </div>

          <div className="flex items-center gap-4">
            <button onClick={searchJobs} disabled={loading || !form.title.trim()}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-7 py-2.5 rounded-lg transition text-sm">
              {loading ? <LoadingSpinner label="Searching..." /> : <><Search size={16} /> Search Jobs</>}
            </button>
            {matching && <LoadingSpinner label="AI scoring..." />}
          </div>
        </div>

        {/* Error */}
        {error && <div className="bg-red-900/60 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3 mb-4">{error}</div>}

        {/* Results */}
        {jobs.length > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 fade-in">
            <h2 className="font-bold text-lg mb-4">
              Results <span className="text-slate-400 font-normal text-base">({jobs.length} jobs)</span>
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    {['Title','Company','Location','Site','Salary',...(cvInfo.uploaded?['Match %']:[]),'Actions'].map(h=>(
                      <th key={h} className="pb-3 pr-4 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j,i) => (
                    <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/20 transition">
                      <td className="py-3 pr-4 font-medium max-w-xs"><div className="truncate" title={j.title}>{j.title}</div></td>
                      <td className="py-3 pr-4 text-slate-300 max-w-xs"><div className="truncate" title={j.company}>{j.company}</div></td>
                      <td className="py-3 pr-4 text-slate-400 text-xs">{j.location}</td>
                      <td className="py-3 pr-4"><span className="bg-slate-700 text-xs px-2 py-0.5 rounded capitalize">{j.site}</span></td>
                      <td className="py-3 pr-4 text-xs text-slate-400">{j.salary || '—'}</td>
                      {cvInfo.uploaded && (
                        <td className="py-3 pr-4">
                          {j.score != null
                            ? <ScoreBadge score={j.score} onClick={() => setModal(j)} />
                            : <span className="text-slate-600 text-xs">—</span>}
                        </td>
                      )}
                      <td className="py-3">
                        <div className="flex items-center gap-3">
                          {j.url && <a href={j.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-xs transition"><ExternalLink size={12} />View</a>}
                          <button onClick={() => saveJob(j)} className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 text-xs transition"><Bookmark size={12} />Save</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
      <ScoreModal item={modal} onClose={() => setModal(null)} mode="seeker" />
    </div>
  )
}
