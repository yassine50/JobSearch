import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import Sidebar from '../components/Sidebar.jsx'
import PageWrapper from '../components/PageWrapper.jsx'
import LinkedInPostHunter from '../components/LinkedInPostHunter.jsx'
import JobBoardScraper from '../components/jobs/JobBoardScraper.jsx'
import TailorCvModal from '../components/modals/TailorCvModal.jsx'
import CvPersonasModal from '../components/modals/CvPersonasModal.jsx'
import WatchlistModal from '../components/modals/WatchlistModal.jsx'
import ScoreModal from '../components/ScoreModal.jsx'
import client, { getCached } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import {
  Upload, CheckCircle2, Briefcase, Sparkles, Users, Radar, Layers, Bell
} from 'lucide-react'
import {
  getCleanJobUrl,
  buildTrackerLookupSets
} from '../utils/jobUtils.js'

export default function Seeker() {
  const toast = useToast()
  const [activeTab, setActiveTab] = useState('job_boards') // 'job_boards' | 'linkedin_posts'
  const [cvInfo, setCvInfo] = useState(() => getCached('/cv/info', { uploaded: false, personas_count: 0 }))
  const [cvUploading, setCvUploading] = useState(false)

  // Power Modals State
  const [personasModalOpen, setPersonasModalOpen] = useState(false)
  const [watchlistModalOpen, setWatchlistModalOpen] = useState(false)

  // Job boards scraper state
  const [boardJobs, setBoardJobs] = useState([])
  const [boardLoading, setBoardLoading] = useState(false)
  const [boardMeta, setBoardMeta] = useState(null)
  const [tailorJob, setTailorJob] = useState(null)
  const [scoreModalJob, setScoreModalJob] = useState(null)
  const [appliedJobs, setAppliedJobs] = useState(() => buildTrackerLookupSets(getCached('/tracker', [])).applied)
  const [savedJobs, setSavedJobs] = useState(() => buildTrackerLookupSets(getCached('/tracker', [])).saved)

  const loadCvInfo = () => {
    client.get('/cv/info').then(r => setCvInfo(r.data)).catch(() => {})
  }

  // Load CV Status & Tracker sync
  useEffect(() => {
    loadCvInfo()
    client.get('/tracker').then(r => {
      const { applied, saved } = buildTrackerLookupSets(r.data || [])
      setAppliedJobs(applied)
      setSavedJobs(saved)
    }).catch(() => {})
  }, [])

  // Listen for CommandPalette power events
  useEffect(() => {
    const onOpenPersonas = () => setPersonasModalOpen(true)
    const onOpenWatchlists = () => setWatchlistModalOpen(true)
    window.addEventListener('open-cv-personas', onOpenPersonas)
    window.addEventListener('open-watchlists', onOpenWatchlists)
    return () => {
      window.removeEventListener('open-cv-personas', onOpenPersonas)
      window.removeEventListener('open-watchlists', onOpenWatchlists)
    }
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
      toast(`CV uploaded: ${data.filename}`, 'success')
      loadCvInfo()
    } catch {
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
    } catch {
      toast('Failed to save job', 'error')
    }
  }

  const [hunterRole, setHunterRole] = useState('Flutter Developer')

  return (
    <PageWrapper>
      <div className="flex min-h-screen bg-[#050811] text-white selection:bg-blue-600 selection:text-white">
        <Sidebar />

        <main className="flex-1 md:ml-64 min-w-0 px-5 sm:px-8 lg:px-10 pt-20 md:pt-8 lg:pt-10 pb-14">
          <div className="max-w-[1480px] mx-auto w-full space-y-6">

            {/* Hero Header Card */}
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-panel rounded-3xl p-5 sm:p-6 md:p-7 relative overflow-hidden flex flex-col xl:flex-row items-start xl:items-center justify-between gap-5"
            >
              <div className="glow-line-top" />

              <div className="space-y-1.5 relative z-10">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600/25 to-purple-600/25 border border-blue-500/30 flex items-center justify-center text-blue-400 shadow-sm shrink-0">
                    <Radar size={20} />
                  </div>
                  <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
                    AI Opportunity <span className="text-gradient-blue">Hunter</span>
                  </h1>
                  <span className="text-[11px] font-bold px-3 py-1 rounded-full bg-gradient-to-r from-blue-500/15 to-purple-500/15 text-blue-300 border border-blue-500/30 flex items-center gap-1.5">
                    <Sparkles size={11} className="text-amber-400" />
                    8-Layer Precision Engine
                  </span>
                </div>
                <p className="text-xs sm:text-sm text-slate-400 pl-0.5">
                  Harvest live LinkedIn recruiter posts with MX-verified corporate emails or scrape global job boards
                </p>
              </div>

              {/* Interactive Resume Status, Watchlists & Mode Switcher Row */}
              <div className="flex items-center gap-2.5 flex-wrap relative z-10 w-full xl:w-auto justify-between xl:justify-end">
                {/* Mode Switcher Tabs with Sliding Pill */}
                <div className="relative flex items-center p-1.5 bg-[#050811]/90 border border-white/[0.08] rounded-2xl backdrop-blur-xl shadow-inner">
                  {[
                    { id: 'job_boards',     label: 'Formal Job Boards',        badge: null,   Icon: Briefcase },
                    { id: 'linkedin_posts', label: 'LinkedIn Recruiter Posts', badge: 'Live', Icon: Users },
                  ].map(tab => {
                    const active = activeTab === tab.id
                    const Icon = tab.Icon
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setActiveTab(tab.id)}
                        className={`relative flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-colors cursor-pointer ${
                          active ? 'text-white' : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {active && (
                          <motion.div
                            layoutId="seeker-mode-pill"
                            transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                            className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 shadow-md shadow-blue-600/25 z-0"
                          />
                        )}
                        <Icon size={14} className="relative z-10" />
                        <span className="relative z-10">{tab.label}</span>
                        {tab.badge && (
                          <span className={`relative z-10 text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded-full ${
                            active ? 'bg-white/20 text-white' : 'bg-emerald-500/15 text-emerald-300'
                          }`}>
                            {tab.badge}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>

                {/* Auto-Pilot Watchlists Trigger */}
                <motion.button
                  whileHover={{ y: -2, scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  type="button"
                  onClick={() => setWatchlistModalOpen(true)}
                  className="flex items-center gap-2 px-3.5 py-2.5 rounded-2xl bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-200 text-xs font-bold transition cursor-pointer shadow-sm"
                  title="Manage Auto-Pilot Saved Watchlists"
                >
                  <Bell size={14} className="text-amber-400" />
                  <span>Watchlists</span>
                </motion.button>

                {/* Multi-CV Personas Vault Trigger */}
                <motion.button
                  whileHover={{ y: -2, scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  type="button"
                  onClick={() => setPersonasModalOpen(true)}
                  className={`flex items-center gap-2 px-3.5 py-2.5 rounded-2xl border transition cursor-pointer text-xs font-bold shadow-sm ${
                    cvInfo.uploaded
                      ? 'bg-emerald-950/40 border-emerald-500/35 hover:border-emerald-400/60 text-emerald-200'
                      : 'bg-slate-900/90 border-white/[0.1] hover:border-blue-500/50 text-slate-200 hover:text-white'
                  }`}
                  title="Open Multi-CV Personas Vault to switch or upload specialized resumes"
                >
                  <Layers size={14} className="text-emerald-400" />
                  {cvInfo.uploaded ? (
                    <span className="flex items-center gap-1.5">
                      <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                      <span className="truncate max-w-[140px]">{cvInfo.persona_name || cvInfo.filename}</span>
                      {cvInfo.personas_count > 1 && (
                        <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/25 text-emerald-200 text-[10px] font-extrabold">
                          {cvInfo.personas_count}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span>CV Personas Vault</span>
                  )}
                </motion.button>
              </div>
            </motion.div>

            {/* Active Mode Body (kept mounted so tab switching never triggers unwanted searches or loses results) */}
            <motion.div
              animate={{ opacity: activeTab === 'linkedin_posts' ? 1 : 0, y: activeTab === 'linkedin_posts' ? 0 : 6 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className={activeTab === 'linkedin_posts' ? 'block' : 'hidden'}
            >
              <LinkedInPostHunter
                initialRole={hunterRole}
                cvUploaded={cvInfo.uploaded}
                onTailor={j => setTailorJob(j)}
              />
            </motion.div>
            <motion.div
              animate={{ opacity: activeTab === 'job_boards' ? 1 : 0, y: activeTab === 'job_boards' ? 0 : 6 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className={activeTab === 'job_boards' ? 'block' : 'hidden'}
            >
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
            </motion.div>
          </div>
        </main>

        {/* Global Modals */}
        <TailorCvModal
          isOpen={Boolean(tailorJob)}
          onClose={() => setTailorJob(null)}
          job={tailorJob}
        />

        <CvPersonasModal
          isOpen={personasModalOpen}
          onClose={() => setPersonasModalOpen(false)}
          onPersonaChanged={loadCvInfo}
        />

        <WatchlistModal
          isOpen={watchlistModalOpen}
          onClose={() => setWatchlistModalOpen(false)}
          currentRole={hunterRole}
          onLoadWatchlist={(role, locations) => {
            setActiveTab('linkedin_posts')
            setHunterRole(role)
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent('quick-hunt-role', { detail: { role, locations } }))
            }, 60)
          }}
        />

        {scoreModalJob && (
          <ScoreModal
            item={scoreModalJob}
            onClose={() => setScoreModalJob(null)}
          />
        )}
      </div>
    </PageWrapper>
  )
}
