import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import confetti from 'canvas-confetti'
import Sidebar from '../components/Sidebar.jsx'
import ScoreBadge from '../components/ScoreBadge.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import { SkeletonRow } from '../components/Skeleton.jsx'
import { useToast } from '../context/ToastContext.jsx'
import client from '../api/client.js'
import {
  Upload, Search, ExternalLink, Bookmark, Mail, Send, X, Copy,
  Check, Sparkles, Plus, Link, Trash2, Info, ChevronDown, ChevronUp, Globe
} from 'lucide-react'

const CORE_SITES = [
  { id:'linkedin', label:'LinkedIn',  color:'bg-blue-700' },
  { id:'indeed',   label:'Indeed',    color:'bg-indigo-700' },
]
const ALL_COUNTRIES = [
  'USA','UK','Canada','Australia','France','Germany','Netherlands',
  'Spain','Switzerland','Belgium','Ireland','Sweden','Denmark','Norway',
  'UAE','Qatar','Saudi Arabia','Singapore','India','South Africa',
  'Morocco','Tunisia','Romania','Poland','Portugal','Italy','Austria',
]
const TEMPLATE_LABELS = {
  application:'📩 Application', cold_outreach:'❄️ Cold Outreach',
  follow_up:'🔁 Follow-Up', thank_you:'🙏 Thank You'
}

const fireConfetti = () => {
  confetti({ particleCount:120, spread:80, origin:{y:0.6}, colors:['#3b82f6','#8b5cf6','#10b981','#f59e0b'] })
}

function EmailPill({ data, onClick }) {
  const [copied, setCopied] = useState(false)
  const isInferred = data.source==='inferred'
  const copy = (e) => {
    e.stopPropagation()
    navigator.clipboard.writeText(data.email)
    setCopied(true); setTimeout(()=>setCopied(false),1500)
  }
  return (
    <div className="flex items-center gap-1 group">
      <button onClick={onClick} title={isInferred?'Suggested email (may not exist)':'Found directly in post'}
        className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-all max-w-[160px]
          ${isInferred
            ? 'bg-slate-800 text-slate-400 border-slate-600 hover:border-blue-500 hover:text-blue-300'
            : 'bg-blue-950 text-blue-300 border-blue-700 hover:bg-blue-900'}`}>
        <Mail size={10}/>
        <span className="truncate">{data.email}</span>
        {!isInferred && <span className="text-emerald-400 text-[9px] shrink-0">●</span>}
      </button>
      <button onClick={copy} className="opacity-0 group-hover:opacity-100 transition text-slate-500 hover:text-white shrink-0">
        {copied ? <Check size={11} className="text-emerald-400"/> : <Copy size={11}/>}
      </button>
    </div>
  )
}

function JobDetailPopup({ job, onClose, onEmail, onSave }) {
  return (
    <motion.div className="fixed inset-0 bg-black/75 z-50 flex items-end sm:items-center justify-center p-4"
      initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
      onClick={onClose}>
      <motion.div
        initial={{opacity:0,y:40,scale:.97}} animate={{opacity:1,y:0,scale:1}}
        exit={{opacity:0,y:20,scale:.97}}
        transition={{type:'spring',damping:24,stiffness:300}}
        className="bg-slate-800 border border-slate-700 rounded-t-2xl md:rounded-2xl w-full md:max-w-xl max-h-[92vh] overflow-y-auto"
        onClick={e=>e.stopPropagation()}>
        <div className="sticky top-0 bg-slate-800 border-b border-slate-700 px-6 py-4 flex items-start justify-between rounded-t-2xl">
          <div className="flex-1 min-w-0 mr-3">
            <h3 className="font-bold text-base truncate">{job.title}</h3>
            <p className="text-slate-400 text-sm">{job.company} · {job.location}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {job.score!=null && <ScoreBadge score={job.score}/>}
            <button onClick={onClose} className="text-slate-400 hover:text-white transition p-1"><X size={18}/></button>
          </div>
        </div>
        <div className="p-6">
          {/* Meta row */}
          <div className="flex flex-wrap gap-2 mb-4">
            <span className="bg-slate-700 text-xs px-2.5 py-1 rounded-full capitalize">{job.site}</span>
            {job.salary && <span className="bg-emerald-900 text-emerald-300 text-xs px-2.5 py-1 rounded-full">{job.salary}</span>}
            {job.date_posted && <span className="text-slate-500 text-xs self-center">{job.date_posted}</span>}
          </div>
          {/* Emails */}
          {job.emails?.length>0 && (
            <div className="mb-4">
              <p className="text-xs text-slate-400 mb-2">📧 Recruiter Emails</p>
              <div className="flex flex-wrap gap-2">
                {job.emails.map((e,i)=>(
                  <EmailPill key={i} data={e} onClick={()=>{onClose();onEmail(job,e.email)}}/>
                ))}
              </div>
            </div>
          )}
          {/* Matched / missing skills */}
          {job.matched_skills?.length>0 && (
            <div className="mb-3">
              <p className="text-xs text-slate-400 mb-1.5">✅ Your matched skills</p>
              <div className="flex flex-wrap gap-1">
                {job.matched_skills.map(s=><span key={s} className="bg-emerald-900 text-emerald-300 text-xs px-2 py-0.5 rounded-full">{s}</span>)}
              </div>
            </div>
          )}
          {job.missing_skills?.length>0 && (
            <div className="mb-4">
              <p className="text-xs text-slate-400 mb-1.5">❌ Skills to develop</p>
              <div className="flex flex-wrap gap-1">
                {job.missing_skills.map(s=><span key={s} className="bg-red-950 text-red-400 text-xs px-2 py-0.5 rounded-full">✗ {s}</span>)}
              </div>
            </div>
          )}
          {/* Description */}
          {job.description && (
            <div className="border-t border-slate-700 pt-4">
              <p className="text-xs text-slate-400 mb-2">📋 Description</p>
              <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{job.description.substring(0,600)}{job.description.length>600?'…':''}</p>
            </div>
          )}
          {/* Actions */}
          <div className="flex gap-2 mt-5 sticky bottom-0 bg-slate-800 pt-3">
            {job.url && <a href={job.url} target="_blank" rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-2 bg-slate-700 hover:bg-slate-600 py-2.5 rounded-xl text-sm transition-colors">
              <ExternalLink size={15}/>View Job
            </a>}
            <button onClick={()=>{onClose();onEmail(job,'')}}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-700 hover:bg-blue-600 py-2.5 rounded-xl text-sm transition-colors">
              <Mail size={15}/>Email
            </button>
            <button onClick={()=>onSave(job)}
              className="flex-1 flex items-center justify-center gap-2 bg-emerald-800 hover:bg-emerald-700 py-2.5 rounded-xl text-sm transition-colors">
              <Bookmark size={15}/>Save
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}

export default function Seeker() {
  const toast = useToast()
  const [form, setForm] = useState({
    title:'', countries:[], results:30, hours:0,
    sites:['linkedin','indeed'], is_remote:false
  })
  const [cvInfo, setCvInfo]         = useState({ uploaded:false })
  const [jobs, setJobs]             = useState([])
  const [loading, setLoading]       = useState(false)
  const [matching, setMatch]        = useState(false)
  const [error, setError]           = useState('')
  const [detailJob, setDetail]      = useState(null)
  const [scoreModal, setScore]      = useState(null)
  const [cvAnalyzing, setCvAnalyzing] = useState(false)
  const [cvSuggestion, setCvSuggestion] = useState(null)  // result from /cv/analyze
  const fileRef = useRef()

  // Custom URL import
  const [urlInput, setUrlInput]     = useState('')
  const [urlLoading, setUrlLoading] = useState(false)
  const [showUrlBox, setShowUrlBox] = useState(false)

  // Email compose
  const [emailModal, setEmailModal]   = useState(null)
  const [emailForm, setEmailForm]     = useState({ to_email:'', to_name:'Hiring Team', subject:'', body:'', template_type:'application' })
  const [sendLoading, setSendLoading] = useState(false)
  const [tplLoading, setTplLoading]   = useState(false)
  const [attachCv, setAttachCv]       = useState(true)

  // Filters & sort
  const [filterSite, setFilterSite]   = useState('all')
  const [sortBy, setSortBy]           = useState('default')
  const [minScore, setMinScore]       = useState(0)

  useEffect(() => {
    client.get('/cv/info').then(r=>setCvInfo(r.data)).catch(()=>{})
  }, [])

  const toggleSite = s => setForm(f => ({
    ...f, sites: f.sites.includes(s) ? f.sites.filter(x=>x!==s) : [...f.sites,s]
  }))

  const uploadCv = async (e) => {
    const file = e.target.files[0]; if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      const { data } = await client.post('/cv/upload', fd, { headers:{'Content-Type':'multipart/form-data'} })
      setCvInfo({ uploaded:true, filename:data.filename, words:data.words })
      toast(`CV uploaded: ${data.filename}`, 'success')
    } catch { toast('CV upload failed','error') }
  }

  const importUrl = async () => {
    if (!urlInput.trim()) return
    setUrlLoading(true)
    try {
      const { data } = await client.post('/jobs/import-url', { url:urlInput.trim() })
      setJobs(prev => [data, ...prev])
      setUrlInput(''); setShowUrlBox(false)
      toast(`Imported: ${data.title}`, 'success')
      if (cvInfo.uploaded) matchAll([data], true)
    } catch(e) { toast(e.response?.data?.detail||'Import failed','error') }
    setUrlLoading(false)
  }

  const searchJobs = async () => {
    if (!form.title.trim()) {
      toast('Please enter a Job Title or Skill', 'error')
      return
    }
    if (!form.countries || form.countries.length === 0) {
      toast('Please select at least one Target Country below', 'error')
      return
    }
    setLoading(true); setError(''); setJobs([])
    try {
      const { data } = await client.post('/jobs/search', {
        title: form.title.trim(),
        country: form.countries[0],
        countries: form.countries,
        sites: form.sites,
        results_wanted: Number(form.results) || 30,
        hours_old: Number(form.hours) > 0 ? Number(form.hours) : null,
        is_remote: Boolean(form.is_remote),
      })
      setJobs(data.jobs)
      toast(`Found ${data.jobs.length} jobs!`, 'success')
      if (cvInfo.uploaded && data.jobs.length > 0) matchAll(data.jobs, false)
    } catch(e) {
      setError(e.response?.data?.detail || 'Search failed — please try again')
      toast('Search failed', 'error')
    }
    setLoading(false)
  }

  const searchByCV = async () => {
    if (!cvInfo.uploaded) {
      toast('Please upload your CV first!', 'error'); return
    }
    setCvAnalyzing(true)
    try {
      const { data } = await client.get('/cv/analyze')
      setCvSuggestion(data)
      const newTitle = data.search_query || data.title || form.title
      const newRemote = data.is_remote ?? form.is_remote

      // Update role title and remote preference WITHOUT overwriting user's chosen countries
      setForm(f => ({
        ...f,
        title: newTitle,
        is_remote: newRemote,
      }))
      toast(`✨ Role detected from CV: "${newTitle}"`, 'success')

      // Check if user has chosen countries
      if (!form.countries || form.countries.length === 0) {
        toast('👉 Please select your target countries below, then click Search Jobs!', 'info')
        setCvAnalyzing(false)
        return
      }

      // If user already selected countries, run search with their chosen countries
      setLoading(true); setError(''); setJobs([])
      try {
        const res = await client.post('/jobs/search', {
          title: newTitle,
          country: form.countries[0],
          countries: form.countries,
          sites: form.sites,
          results_wanted: Number(form.results) || 30,
          hours_old: Number(form.hours) > 0 ? Number(form.hours) : null,
          is_remote: Boolean(newRemote),
        })
        setJobs(res.data.jobs)
        toast(`🎯 Found ${res.data.jobs.length} jobs matching your CV in your selected countries!`, 'success')
        if (res.data.jobs.length > 0) matchAll(res.data.jobs, false)
      } catch (e) {
        setError(e.response?.data?.detail || 'Search failed')
      } finally {
        setLoading(false)
      }
    } catch(e) {
      toast(e.response?.data?.detail || 'CV analysis failed', 'error')
    }
    setCvAnalyzing(false)
  }

  const toggleCountry = (c) => {
    setForm(f => {
      const has = f.countries.includes(c)
      const next = has ? f.countries.filter(x=>x!==c) : [...f.countries, c]
      return { ...f, countries: next }
    })
  }

  const selectTopHubs = () => {
    setForm(f => ({ ...f, countries: ['USA', 'UK', 'Germany', 'France', 'UAE'] }))
  }

  const selectAllCountries = () => {
    setForm(f => ({ ...f, countries: ALL_COUNTRIES }))
  }

  const clearCountries = () => {
    setForm(f => ({ ...f, countries: [] }))
  }


  const matchAll = async (jobList, single=false) => {
    setMatch(true)
    const updated = single ? [...jobs] : [...jobList]
    const targets = single ? [jobList[0]] : jobList
    for (let i=0; i<targets.length; i++) {
      if (!targets[i].description) continue
      try {
        const { data } = await client.post('/cv/match', {
          job_description:targets[i].description, job_title:targets[i].title
        })
        const idx = updated.findIndex(j=>j.url===targets[i].url)
        if (idx>-1) updated[idx] = { ...updated[idx], score:data.score,
          breakdown:data.breakdown, matched_skills:data.breakdown?.matched_tech||[],
          missing_skills:data.breakdown?.missing_tech||[], tips:data.breakdown?.tips||[] }
        setJobs([...updated])
      } catch {}
    }
    if (!single) updated.sort((a,b)=>(b.score||0)-(a.score||0))
    setJobs([...updated]); setMatch(false)
  }

  const saveJob = async (j) => {
    try {
      await client.post('/jobs/save', { title:j.title, company:j.company, location:j.location,
        url:j.url, description:j.description, match_score:j.score||0 })
      toast(`Saved: ${j.title}`,'success')
    } catch { toast('Save failed','error') }
  }

  const openEmail = async (job, prefill='') => {
    setEmailModal({ job }); setTplLoading(true)
    setEmailForm(f=>({ ...f, to_email:prefill, to_name:'Hiring Team', template_type:'application' }))
    try {
      const { data } = await client.post('/email/template', {
        template_type:'application', to_name:'Hiring Team',
        company:job.company, job_title:job.title
      })
      setEmailForm(f=>({ ...f, subject:data.subject, body:data.body, to_email:prefill }))
    } catch {}
    setTplLoading(false)
  }

  const changeTemplate = async (type) => {
    if (!emailModal) return
    setEmailForm(f=>({ ...f, template_type:type })); setTplLoading(true)
    try {
      const { data } = await client.post('/email/template', {
        template_type:type, to_name:emailForm.to_name,
        company:emailModal.job.company, job_title:emailModal.job.title
      })
      setEmailForm(f=>({ ...f, subject:data.subject, body:data.body }))
    } catch {}
    setTplLoading(false)
  }

  const sendEmail = async () => {
    if (!emailModal||!emailForm.to_email) return
    setSendLoading(true)
    try {
      let appId = null
      try {
        const { data:app } = await client.post('/tracker', {
          title:emailModal.job.title, company:emailModal.job.company,
          location:emailModal.job.location, url:emailModal.job.url,
          match_score:emailModal.job.score||0, status:'applied',
          notes:`Applied via email to ${emailForm.to_email}`
        })
        appId = app.id
      } catch {}
      await client.post('/email/send', {
        to_email:emailForm.to_email, to_name:emailForm.to_name,
        subject:emailForm.subject, body:emailForm.body,
        template_type:emailForm.template_type, application_id:appId,
        attach_cv: attachCv
      })
      fireConfetti()
      toast('🎉 Email sent & added to Tracker!','success')
      setEmailModal(null)
    } catch(e) {
      toast(e.response?.data?.detail||'Send failed — check Settings → Email','error')
    }
    setSendLoading(false)
  }


  // Deduplicate + filter + sort
  const filteredJobs = (() => {
    // 1. Deduplicate by title+company
    const seen = new Set()
    let list = jobs.filter(j => {
      const key = `${(j.title||'').toLowerCase().trim()}|${(j.company||'').toLowerCase().trim()}`
      if (seen.has(key)) return false
      seen.add(key); return true
    })
    // 2. Filter by site
    if (filterSite !== 'all') list = list.filter(j => j.site === filterSite || (filterSite==='custom' && j.imported))
    // 3. Filter by min match score
    if (minScore > 0) list = list.filter(j => (j.score||0) >= minScore)
    // 4. Sort
    if (sortBy === 'score') list = [...list].sort((a,b) => (b.score||0)-(a.score||0))
    else if (sortBy === 'company') list = [...list].sort((a,b) => (a.company||'').localeCompare(b.company||''))
    return list
  })()

  const emailCount = jobs.reduce((n,j)=>n+(j.emails?.length||0),0)

  return (
    <PageWrapper>
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar/>
      <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8">
        <motion.div className="flex items-center justify-between mb-6"
          initial={{opacity:0,x:-10}} animate={{opacity:1,x:0}} transition={{duration:.25}}>
          <h1 className="text-2xl font-bold">🔎 Job Search</h1>
          <motion.button whileHover={{scale:1.03}} whileTap={{scale:.96}}
            onClick={()=>setShowUrlBox(v=>!v)}
            className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 border border-slate-600 text-sm px-4 py-2 rounded-xl transition-colors">
            <Globe size={15}/>{showUrlBox ? 'Hide URL Import':'Import from URL'}
          </motion.button>
        </motion.div>

        {/* URL Import box */}
        <AnimatePresence>
          {showUrlBox && (
            <motion.div initial={{opacity:0,height:0}} animate={{opacity:1,height:'auto'}}
              exit={{opacity:0,height:0}} className="mb-4 overflow-hidden">
              <div className="bg-slate-800 border border-purple-700/50 rounded-2xl p-5">
                <p className="text-sm font-semibold mb-1 flex items-center gap-2"><Link size={14} className="text-purple-400"/>Import Any Job Posting</p>
                <p className="text-xs text-slate-400 mb-3">Paste a URL from any job board — WeWorkRemotely, RemoteOK, company careers page, etc.</p>
                <div className="flex gap-2">
                  <input value={urlInput} onChange={e=>setUrlInput(e.target.value)}
                    onKeyDown={e=>e.key==='Enter'&&importUrl()}
                    placeholder="https://weworkremotely.com/jobs/... or any job posting URL"
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-purple-500 transition-colors"/>
                  <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                    onClick={importUrl} disabled={urlLoading||!urlInput.trim()}
                    className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-colors">
                    {urlLoading ? <LoadingSpinner label="Importing..."/> : <><Plus size={15}/>Import</>}
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search form */}
        <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6"
          initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{duration:.3,delay:.06}}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-5">
            {/* Job Title — No Location Input needed */}
            <div className="md:col-span-2 lg:col-span-3">
              <label className="text-xs text-slate-400 mb-1.5 block font-medium">Job Title, Role or Skill *</label>
              <div className="relative">
                <input
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && searchJobs()}
                  placeholder="e.g. Flutter Developer, Mobile Engineer, React, Full Stack, Python..."
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                />
                <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              </div>
            </div>

            {/* Countries with Quick Selectors */}
            <div className="md:col-span-2 lg:col-span-3">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <label className="text-xs text-slate-400 font-medium">
                  Target Countries
                  <span className={`ml-1.5 font-normal ${form.countries.length > 0 ? 'text-blue-400' : 'text-amber-400'}`}>
                    ({form.countries.length} selected{form.countries.length === 0 ? ' — click countries below to select' : ''})
                  </span>
                </label>
                <div className="flex items-center gap-2 text-xs">
                  <button type="button" onClick={selectTopHubs} className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
                    Top Tech Hubs
                  </button>
                  <span className="text-slate-600">·</span>
                  <button type="button" onClick={selectAllCountries} className="text-slate-400 hover:text-slate-200 transition-colors">
                    Select All
                  </button>
                  <span className="text-slate-600">·</span>
                  <button type="button" onClick={clearCountries} className="text-slate-500 hover:text-slate-300 transition-colors">
                    Reset
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto pr-1">
                {ALL_COUNTRIES.map(c => {
                  const selected = form.countries.includes(c)
                  return (
                    <button key={c} type="button"
                      onClick={() => toggleCountry(c)}
                      className={`text-xs px-3 py-1.5 rounded-full border transition-all ${
                        selected
                          ? 'bg-blue-600 border-blue-500 text-white font-semibold shadow-sm shadow-blue-500/20'
                          : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                      }`}>
                      {c}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Results Wanted */}
            <div>
              <label className="text-xs text-slate-400 mb-1.5 block">Results Wanted</label>
              <select
                value={form.results}
                onChange={e => setForm({ ...form, results: Number(e.target.value) })}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors">
                {[20, 30, 50, 75, 100].map(n => (
                  <option key={n} value={n}>{n} jobs</option>
                ))}
              </select>
            </div>

            {/* Posted Within */}
            <div>
              <label className="text-xs text-slate-400 mb-1.5 block">Date Posted</label>
              <select
                value={form.hours}
                onChange={e => setForm({ ...form, hours: Number(e.target.value) })}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors">
                {[
                  [0, 'Anytime (Maximum Jobs)'],
                  [720, 'Past 30 days'],
                  [336, 'Past 14 days'],
                  [168, 'Past 7 days'],
                  [24, 'Past 24 hours']
                ].map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>

            {/* Job Boards & Remote Toggle */}
            <div>
              <label className="text-xs text-slate-400 mb-2 block">Sources & Preferences</label>
              <div className="flex flex-wrap items-center gap-4 pt-1">
                {CORE_SITES.map(s => (
                  <label key={s.id} className="flex items-center gap-2 text-sm cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={form.sites.includes(s.id)}
                      onChange={() => toggleSite(s.id)}
                      className="accent-blue-500 w-4 h-4 rounded"
                    />
                    <span className="font-medium">{s.label}</span>
                  </label>
                ))}
                <label className="flex items-center gap-2 text-sm cursor-pointer select-none text-slate-300">
                  <input
                    type="checkbox"
                    checked={Boolean(form.is_remote)}
                    onChange={e => setForm({ ...form, is_remote: e.target.checked })}
                    className="accent-purple-500 w-4 h-4 rounded"
                  />
                  <span className="font-medium text-purple-300">🌐 Remote Only</span>
                </label>
              </div>
            </div>
          </div>

          {/* CV Section + Action Buttons */}
          <div className="border-t border-slate-700 pt-5 mt-2">

            {/* Smart Search from CV — hero feature */}
            <div className="bg-gradient-to-r from-blue-900/40 to-purple-900/30 border border-blue-700/40 rounded-2xl p-4 mb-4">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-600/30 flex items-center justify-center shrink-0">
                    <span className="text-lg">🧠</span>
                  </div>
                  <div>
                    <p className="font-semibold text-sm">Smart Search from CV</p>
                    {cvInfo.uploaded
                      ? <p className="text-xs text-slate-400 mt-0.5">✓ {cvInfo.filename} · {cvInfo.words} words — ready to analyze</p>
                      : <p className="text-xs text-slate-400 mt-0.5">Upload your CV and we'll find the best jobs automatically</p>
                    }
                    {cvSuggestion && (
                      <p className="text-xs text-blue-300 mt-1">
                        Detected: <strong>{cvSuggestion.title}</strong> · Skills: {cvSuggestion.top_skills?.slice(0,4).join(', ')}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                    onClick={()=>fileRef.current.click()}
                    className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-sm px-4 py-2 rounded-xl transition-colors">
                    <Upload size={14}/>{cvInfo.uploaded?'Replace CV':'Upload CV'}
                  </motion.button>
                  <motion.button whileHover={{scale:1.03}} whileTap={{scale:.96}}
                    onClick={searchByCV}
                    disabled={cvAnalyzing || loading || !cvInfo.uploaded}
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl transition-colors text-sm">
                    {cvAnalyzing
                      ? <><LoadingSpinner label="Analyzing..."/></>
                      : <><Search size={14}/>🎯 Search by CV</>
                    }
                  </motion.button>
                </div>
              </div>
            </div>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" onChange={uploadCv} className="hidden"/>

            {/* Manual search button */}
            <div className="flex items-center gap-4">
              <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                onClick={searchJobs} disabled={loading || !form.title.trim()}
                className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 font-semibold px-7 py-2.5 rounded-xl transition-colors text-sm">
                {loading ? <LoadingSpinner label="Searching..."/> : <><Search size={16}/>Search Jobs</>}
              </motion.button>
              <span className="text-xs text-slate-500">or use Smart Search above</span>
              <AnimatePresence>
                {matching && (
                <motion.div initial={{opacity:0,x:-8}} animate={{opacity:1,x:0}} exit={{opacity:0}}>
                  <LoadingSpinner label="AI scoring..."/>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          </div>{/* end CV Section + Action Buttons */}
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div initial={{opacity:0,y:-8}} animate={{opacity:1,y:0}} exit={{opacity:0}}
              className="bg-red-900/60 border border-red-700 text-red-300 text-sm rounded-xl px-4 py-3 mb-4 flex items-center justify-between">
              {error}<button onClick={()=>setError('')}><X size={15}/></button>
            </motion.div>
          )}
        </AnimatePresence>

        {(loading||jobs.length>0) && (
          <motion.div className="bg-slate-800 border border-slate-700 rounded-2xl p-6"
            initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{duration:.3}}>
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <h2 className="font-bold text-lg">
                Results{jobs.length>0 && (
                  <span className="text-slate-400 font-normal text-base ml-2">
                    ({filteredJobs.length}{filteredJobs.length!==jobs.length?` of ${jobs.length}`:''} jobs · {emailCount} emails)
                  </span>
                )}
              </h2>
              {jobs.length>0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <select value={filterSite} onChange={e=>setFilterSite(e.target.value)}
                    className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500">
                    <option value="all">All Sites</option>
                    <option value="linkedin">LinkedIn</option>
                    <option value="indeed">Indeed</option>
                    <option value="custom">Imported</option>
                  </select>
                  <select value={minScore} onChange={e=>setMinScore(Number(e.target.value))}
                    className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500">
                    <option value={0}>Any Match</option>
                    <option value={30}>30%+ Match</option>
                    <option value={50}>50%+ Match</option>
                    <option value={70}>70%+ Match</option>
                  </select>
                  <select value={sortBy} onChange={e=>setSortBy(e.target.value)}
                    className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500">
                    <option value="default">Default Order</option>
                    <option value="score">Best Match ↓</option>
                    <option value="company">Company A-Z</option>
                  </select>
                </div>
              )}
              <div className="flex gap-3 text-xs text-slate-500">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-600 inline-block"/>Found in post</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-600 inline-block"/>Suggested</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-600 inline-block"/>Imported</span>
              </div>
            </div>
            {/* ── Desktop table ──────────────────────── */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-700">
                    {['','Title','Company','Location','Site','Salary',
                      ...(cvInfo.uploaded?['Match']:['']),'Recruiter Emails','Actions'].map((h,i)=>(
                      <th key={i} className="pb-3 pr-3 font-medium text-xs whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading
                    ? Array(8).fill(0).map((_,i)=><SkeletonRow key={i}/>)
                    : filteredJobs.map((j,i)=>(
                    <motion.tr key={i}
                      initial={{opacity:0,x:-6}} animate={{opacity:1,x:0}}
                      transition={{delay:i*.03,duration:.18}}
                      className="border-b border-slate-700/50 hover:bg-slate-700/25 transition-colors cursor-pointer group"
                      onClick={()=>setDetail(j)}>
                      <td className="py-3 pr-2">
                        {j.imported && (
                          <span className="w-1.5 h-1.5 rounded-full bg-purple-500 inline-block" title="Imported from URL"/>
                        )}
                      </td>
                      <td className="py-3 pr-3 font-medium max-w-[180px]">
                        <span className="truncate block group-hover:text-blue-300 transition-colors" title={j.title}>{j.title}</span>
                      </td>
                      <td className="py-3 pr-3 text-slate-300 max-w-[140px]"><span className="truncate block">{j.company}</span></td>
                      <td className="py-3 pr-3 text-slate-400 text-xs whitespace-nowrap">{j.location||'—'}</td>
                      <td className="py-3 pr-3">
                        <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${j.imported?'bg-purple-900 text-purple-300':'bg-slate-700 text-slate-300'}`}>
                          {j.imported?'custom':j.site}
                        </span>
                      </td>
                      <td className="py-3 pr-3 text-xs text-slate-400 whitespace-nowrap">{j.salary||'—'}</td>
                      {cvInfo.uploaded && (
                        <td className="py-3 pr-3" onClick={e=>{e.stopPropagation();j.score!=null&&setScore(j)}}>
                          {j.score!=null
                            ? <ScoreBadge score={j.score}/>
                            : <span className="text-slate-600 text-xs">—</span>}
                        </td>
                      )}
                      {!cvInfo.uploaded && <td className="py-3 pr-3"/>}
                      <td className="py-3 pr-3 min-w-[180px]" onClick={e=>e.stopPropagation()}>
                        {j.emails?.length>0 ? (
                          <div className="flex flex-col gap-1">
                            {j.emails.slice(0,2).map((e,ei)=>(
                              <EmailPill key={ei} data={e} onClick={()=>openEmail(j,e.email)}/>
                            ))}
                            {j.emails.length>2 && (
                              <button onClick={()=>setDetail(j)} className="text-xs text-slate-500 hover:text-blue-400 transition-colors text-left">
                                +{j.emails.length-2} more →
                              </button>
                            )}
                          </div>
                        ) : (
                          <button onClick={()=>openEmail(j,'')}
                            className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-400 transition-colors">
                            <Mail size={12}/>Compose
                          </button>
                        )}
                      </td>
                      <td className="py-3" onClick={e=>e.stopPropagation()}>
                        <div className="flex items-center gap-2">
                          {j.url && <a href={j.url} target="_blank" rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-300 transition-colors">
                            <ExternalLink size={14}/>
                          </a>}
                          <button onClick={()=>saveJob(j)} className="text-emerald-400 hover:text-emerald-300 transition-colors">
                            <Bookmark size={14}/>
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* ── Mobile cards ───────────────────────── */}
            <div className="md:hidden space-y-3 mt-2">
              {loading
                ? Array(4).fill(0).map((_,i)=>(
                  <div key={i} className="bg-slate-900 rounded-2xl p-4 animate-pulse space-y-3 border border-slate-700">
                    <div className="h-4 bg-slate-700 rounded w-3/4"/>
                    <div className="h-3 bg-slate-700/60 rounded w-1/2"/>
                    <div className="h-3 bg-slate-700/40 rounded w-full"/>
                  </div>
                ))
                : jobs.map((j,i)=>(
                <motion.div key={i}
                  initial={{opacity:0,y:10}} animate={{opacity:1,y:0}}
                  transition={{delay:i*.04}}
                  onClick={()=>setDetail(j)}
                  className="bg-slate-900 border border-slate-700 rounded-2xl p-4 hover:border-slate-500 transition-colors cursor-pointer active:scale-[0.98]">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm truncate">{j.title}</p>
                      <p className="text-slate-400 text-xs truncate">{j.company}</p>
                    </div>
                    {j.score!=null && <ScoreBadge score={j.score} onClick={e=>{e.stopPropagation();setScore(j)}}/>}
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs mb-3">
                    {j.location && <span className="text-slate-400">📍 {j.location}</span>}
                    {j.salary   && <span className="text-emerald-400">💰 {j.salary}</span>}
                    <span className="bg-slate-700 px-2 py-0.5 rounded-full capitalize">{j.imported?'custom':j.site}</span>
                  </div>
                  {/* Emails */}
                  {j.emails?.length>0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3" onClick={e=>e.stopPropagation()}>
                      {j.emails.slice(0,2).map((e,ei)=>(
                        <EmailPill key={ei} data={e} onClick={()=>openEmail(j,e.email)}/>
                      ))}
                      {j.emails.length>2 && <span className="text-xs text-slate-500">+{j.emails.length-2}</span>}
                    </div>
                  )}
                  <div className="flex items-center gap-3 border-t border-slate-700 pt-2.5" onClick={e=>e.stopPropagation()}>
                    {j.url && <a href={j.url} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-blue-400">
                      <ExternalLink size={13}/>View
                    </a>}
                    <button onClick={()=>openEmail(j,'')} className="flex items-center gap-1 text-xs text-slate-300">
                      <Mail size={13}/>Email
                    </button>
                    <button onClick={()=>saveJob(j)} className="flex items-center gap-1 text-xs text-emerald-400 ml-auto">
                      <Bookmark size={13}/>Save
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </main>

      <ScoreModal item={scoreModal} onClose={()=>setScore(null)} mode="seeker"/>

      {/* Job Detail Popup */}
      <AnimatePresence>
        {detailJob && (
          <JobDetailPopup job={detailJob} onClose={()=>setDetail(null)}
            onEmail={(j,e)=>openEmail(j,e)} onSave={saveJob}/>
        )}
      </AnimatePresence>

      {/* Email Compose Modal */}
      <AnimatePresence>
        {emailModal && (
          <motion.div className="fixed inset-0 bg-black/75 z-50 flex items-end md:items-center justify-center md:p-4"
            initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
            onClick={()=>setEmailModal(null)}>
            <motion.div
              initial={{opacity:0,scale:.93,y:24}} animate={{opacity:1,scale:1,y:0}}
              exit={{opacity:0,scale:.96,y:12}}
              transition={{type:'spring',damping:22,stiffness:280}}
              className="bg-slate-800 border border-slate-700 rounded-t-2xl md:rounded-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto p-4 md:p-6"
              onClick={e=>e.stopPropagation()}>
              <div className="flex justify-between items-start mb-5">
                <div>
                  <h3 className="font-bold text-lg flex items-center gap-2"><Sparkles size={17} className="text-blue-400"/>Compose Email</h3>
                  <p className="text-slate-400 text-sm">{emailModal.job.title} @ {emailModal.job.company}</p>
                </div>
                <button onClick={()=>setEmailModal(null)} className="text-slate-400 hover:text-white transition p-1"><X size={20}/></button>
              </div>
              <div className="flex gap-2 mb-5 flex-wrap">
                {Object.entries(TEMPLATE_LABELS).map(([key,label])=>(
                  <motion.button key={key} whileTap={{scale:.95}}
                    onClick={()=>changeTemplate(key)}
                    className={`text-xs px-3 py-1.5 rounded-xl border transition-all ${
                      emailForm.template_type===key
                        ? 'border-blue-500 bg-blue-900/50 text-blue-300'
                        : 'border-slate-700 text-slate-400 hover:border-slate-500'}`}>
                    {label}
                  </motion.button>
                ))}
              </div>
              {tplLoading ? (
                <div className="flex items-center justify-center py-12"><LoadingSpinner label="Loading template..."/></div>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block">To Email *</label>
                      <input value={emailForm.to_email} type="email"
                        onChange={e=>setEmailForm({...emailForm,to_email:e.target.value})}
                        placeholder="recruiter@company.com"
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"/>
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block">Name</label>
                      <input value={emailForm.to_name}
                        onChange={e=>setEmailForm({...emailForm,to_name:e.target.value})}
                        placeholder="Hiring Manager"
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"/>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Subject</label>
                    <input value={emailForm.subject}
                      onChange={e=>setEmailForm({...emailForm,subject:e.target.value})}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"/>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Message</label>
                    <textarea value={emailForm.body}
                      onChange={e=>setEmailForm({...emailForm,body:e.target.value})}
                      rows={11}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors resize-none font-mono leading-relaxed"/>
                  </div>
                </div>
              )}
              <div className="flex gap-3 mt-5">
                <button onClick={()=>setEmailModal(null)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 py-2.5 rounded-xl text-sm transition-colors">Cancel</button>
                <motion.button whileHover={{scale:1.02}} whileTap={{scale:.97}}
                  onClick={sendEmail} disabled={sendLoading||!emailForm.to_email||tplLoading}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors">
                  {sendLoading ? <LoadingSpinner label="Sending..."/> : <><Send size={15}/>Send & Track</>}
                </motion.button>
              </div>
              <p className="text-xs text-slate-500 text-center mt-2">Sends via Gmail · Auto-added to Tracker</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </PageWrapper>
  )
}
