import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Sidebar from '../components/Sidebar.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import LinkedInPostHunter from '../components/LinkedInPostHunter.jsx'
import JobBoardScraper from '../components/jobs/JobBoardScraper.jsx'
import TailorCvModal from '../components/modals/TailorCvModal.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import client from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import {
  Search, Upload, FileText, CheckCircle2, AlertCircle,
  Briefcase, Globe, Sparkles, MessageSquare, Layers, Users
} from 'lucide-react'

// Helper to normalize job URLs without destroying Indeed job IDs (?jk=)
const getCleanJobUrl = (url) => {
  if (!url) return ''
  const u = String(url).trim().toLowerCase()
  if (u.includes('indeed.com') || u.includes('viewjob')) {
    const match = u.match(/[?&]jk=([a-zA-Z0-9]+)/)
    if (match) return `indeed:${match[1]}`
    return u.split('&')[0].replace(/\/+$/, '')
  }
  return u.split('?')[0].replace(/\/+$/, '')
}

export default function Seeker() {
  const toast = useToast()
  const [activeTab, setActiveTab] = useState('linkedin_posts') // 'linkedin_posts' | 'job_boards'
  const [cvInfo, setCvInfo] = useState({ uploaded: false })
  const [cvUploading, setCvUploading] = useState(false)

  // Job boards scraper state
  const [boardJobs, setBoardJobs] = useState([])
  const [boardLoading, setBoardLoading] = useState(false)
  const [boardMeta, setBoardMeta] = useState(null)
  const [tailorJob, setTailorJob] = useState(null)
  const [scoreModalJob, setScoreModalJob] = useState(null)
  const [appliedJobs, setAppliedJobs] = useState(new Set())
  const [savedJobs, setSavedJobs] = useState(new Set())

  // Load CV Status & Tracker sync
  useEffect(() => {
    client.get('/cv/info').then(r => setCvInfo(r.data)).catch(() => {})
    client.get('/tracker').then(r => {
      const applied = new Set()
      const saved = new Set()
      ;(r.data || []).forEach(a => {
        const rawUrl = (a.url || '').trim().toLowerCase()
        const key1 = getCleanJobUrl(rawUrl)
        const key2 = `${(a.title || '').trim().toLowerCase()}|${(a.company || '').trim().toLowerCase()}`
        if (['applied', 'interviewing', 'offer'].includes(a.status?.toLowerCase())) {
          if (rawUrl) applied.add(rawUrl)
          if (key1) applied.add(key1)
          if (key2 !== '|') applied.add(key2)
        } else if (a.status?.toLowerCase() === 'saved') {
          if (rawUrl) saved.add(rawUrl)
          if (key1) saved.add(key1)
          if (key2 !== '|') saved.add(key2)
        }
      })
      setAppliedJobs(applied)
      setSavedJobs(saved)
    }).catch(() => {})
  }, [])

  // Handle CV Upload
  const handleCvUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCvUploading(true)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const { data } = await client.post('/cv/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setCvInfo({ uploaded: true, filename: data.filename, words: data.words })
      toast(`CV uploaded: ${data.filename}`, 'success')
    } catch (err) {
      toast('Failed to upload CV', 'error')
    } finally {
      setCvUploading(false)
    }
  }

  // Handle Board Search
  const handleBoardSearch = async (params) => {
    setBoardLoading(true)
    try {
      const hoursOld = params.hours_old !== undefined ? params.hours_old : (
        params.filters?.datePosted === '24h' ? 24 :
        params.filters?.datePosted === 'week' ? 168 :
        params.filters?.datePosted === 'month' ? 720 : null
      )

      const { data } = await client.post('/jobs/search', {
        title: params.title.trim(),
        country: params.countries[0] || 'Worldwide',
        countries: params.countries,
        sites: params.sites,
        results_wanted: Number(params.results_wanted) || 30,
        hours_old: hoursOld,
        is_remote: params.is_remote,
        easy_apply: Boolean(params.filters?.easyApply || params.easy_apply),
        international_only: Boolean(params.filters?.internationalOnly || params.international_only)
      })
      setBoardJobs(data.jobs || [])
      setBoardMeta({ queries: data.queries_used || [], stats: data.stats || null })
      const st = data.stats || {}
      const merged = st.raw && st.after_dedup ? ` · ${st.raw - st.after_dedup} duplicates merged` : ''
      toast(`Found ${data.jobs?.length || 0} relevant jobs${merged}`, 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Job board search failed', 'error')
    } finally {
      setBoardLoading(false)
    }
  }

  // Check if board job is applied / saved
  const isJobApplied = (j) => {
    if (!j) return false
    if (j.is_applied) return true
    const rawUrl = (j.url || j.job_url || j.job_url_direct || j.post_url || '').trim().toLowerCase()
    const cleanUrl = getCleanJobUrl(rawUrl)
    const key2 = `${(j.title || j.role_title || '').trim().toLowerCase()}|${(j.company || '').trim().toLowerCase()}`
    return (rawUrl && appliedJobs.has(rawUrl)) || (cleanUrl && appliedJobs.has(cleanUrl)) || (key2 !== '|' && appliedJobs.has(key2))
  }

  const handleJobApplied = (job) => {
    if (!job) return
    const rawUrl = (job.url || job.job_url || job.job_url_direct || job.post_url || '').trim().toLowerCase()
    const cleanUrl = getCleanJobUrl(rawUrl)
    const key2 = `${(job.title || job.role_title || '').trim().toLowerCase()}|${(job.company || '').trim().toLowerCase()}`
    
    setAppliedJobs(prev => {
      const next = new Set(prev)
      if (rawUrl) next.add(rawUrl)
      if (cleanUrl) next.add(cleanUrl)
      if (key2 !== '|') next.add(key2)
      return next
    })

    setBoardJobs(prev => prev.filter(j => {
      const jRawUrl = (j.url || j.job_url || j.job_url_direct || '').trim().toLowerCase()
      const jCleanUrl = getCleanJobUrl(jRawUrl)
      const jTc = `${(j.title || '').trim().toLowerCase()}|${(j.company || '').trim().toLowerCase()}`
      if (rawUrl && jRawUrl && (jRawUrl === rawUrl || (cleanUrl && jCleanUrl === cleanUrl))) return false
      if (key2 !== '|' && jTc === key2) return false
      return true
    }))
  }

  const isJobSaved = (j) => {
    if (!j) return false
    const key1 = (j.url || '').trim().toLowerCase()
    const key2 = `${(j.title || '').trim().toLowerCase()}|${(j.company || '').trim().toLowerCase()}`
    return savedJobs.has(key1) || savedJobs.has(key2)
  }

  const handleSaveBoardJob = async (job) => {
    try {
      await client.post('/jobs/save', {
        title: job.title,
        company: job.company,
        location: job.location,
        url: job.url || job.job_url_direct || '',
        description: job.description,
        match_score: job.score || 0
      })
      const key1 = (job.url || job.job_url_direct || '').trim().toLowerCase()
      const key2 = `${(job.title || '').trim().toLowerCase()}|${(job.company || '').trim().toLowerCase()}`
      setSavedJobs(prev => new Set([...prev, key1, key2]))
      toast(`Saved ${job.title} to pipeline!`, 'success')
    } catch (err) {
      toast('Failed to save job', 'error')
    }
  }

  // Active Mode Body
  const [hunterRole, setHunterRole] = useState('Flutter Developer')

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-slate-950 text-white selection:bg-blue-600 selection:text-white">
        <Sidebar />

        <main className="md:ml-60 flex-1 pt-14 md:pt-0 p-4 md:p-8 space-y-6">
          {/* Header Navigation & CV Status Banner */}
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div>
              <h1 className="text-2xl font-black text-white tracking-tight flex items-center gap-2">
                <span>Job Hunter</span>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  AI-Powered
                </span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Mine authentic recruiter posts with direct emails & formal job board listings
              </p>
            </div>

            {/* CV Upload Badge */}
            <div className="flex items-center gap-2.5">
              <label className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-750 hover:border-slate-650 transition cursor-pointer text-xs font-medium text-slate-300 hover:text-white shadow-xs">
                <Upload size={14} className={cvUploading ? 'animate-bounce text-blue-400' : 'text-slate-400'} />
                {cvInfo.uploaded ? (
                  <span className="flex items-center gap-1.5 text-emerald-300">
                    <CheckCircle2 size={13} className="text-emerald-400" />
                    <span className="truncate max-w-[140px] font-semibold">{cvInfo.filename}</span>
                  </span>
                ) : (
                  <span>Upload Resume (PDF)</span>
                )}
                <input
                  type="file"
                  accept=".pdf"
                  onChange={handleCvUpload}
                  disabled={cvUploading}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex items-center gap-2 p-1.5 bg-slate-900/80 border border-slate-800 rounded-xl w-fit">
            <button
              type="button"
              onClick={() => setActiveTab('linkedin_posts')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
                activeTab === 'linkedin_posts'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Users size={14} />
              <span>LinkedIn Recruiter Posts (Live Feed)</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('job_boards')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
                activeTab === 'job_boards'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Briefcase size={14} />
              <span>Job Boards (Indeed / LinkedIn Jobs)</span>
            </button>
          </div>

          {/* Active Mode Body (kept mounted so tab switching never triggers unwanted searches or loses results) */}
          <div className={activeTab === 'linkedin_posts' ? 'block' : 'hidden'}>
            <LinkedInPostHunter
              initialRole={hunterRole}
              cvUploaded={cvInfo.uploaded}
              onTailor={j => setTailorJob(j)}
            />
          </div>
          <div className={activeTab === 'job_boards' ? 'block' : 'hidden'}>
            <JobBoardScraper
              jobs={boardJobs}
              loading={boardLoading}
              searchMeta={boardMeta}
              onSearch={handleBoardSearch}
              onSaveJob={handleSaveBoardJob}
              onTailorJob={j => setTailorJob(j)}
              isJobApplied={isJobApplied}
              isJobSaved={isJobSaved}
              onJobApplied={handleJobApplied}
              onSwitchToPosts={(targetRole) => {
                if (targetRole) setHunterRole(targetRole)
                setActiveTab('linkedin_posts')
              }}
            />
          </div>
        </main>

        {/* Global Modals */}
        <TailorCvModal
          isOpen={Boolean(tailorJob)}
          onClose={() => setTailorJob(null)}
          job={tailorJob}
        />

        {scoreModalJob && (
          <ScoreModal
            job={scoreModalJob}
            onClose={() => setScoreModalJob(null)}
          />
        )}
      </div>
    </PageWrapper>
  )
}
