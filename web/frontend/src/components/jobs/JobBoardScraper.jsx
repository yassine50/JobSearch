import { useState, useMemo, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, ExternalLink, Bookmark, Mail, Check, Sparkles,
  Building2, MapPin, Loader2, ShieldCheck, AlertCircle, Send,
  ChevronDown, ChevronUp, Zap, SlidersHorizontal, RotateCcw,
  Globe, Briefcase, Compass, Columns, LayoutGrid, CheckCheck, Target
} from 'lucide-react'
import ScoreBadge from '../ScoreBadge.jsx'
import AutoApplyModal from '../modals/AutoApplyModal.jsx'
import BatchApplyModal from '../modals/BatchApplyModal.jsx'
import EasyApplyModal from '../modals/EasyApplyModal.jsx'
import BatchEasyApplyModal from '../modals/BatchEasyApplyModal.jsx'
import SmtpPromptModal from '../modals/SmtpPromptModal.jsx'
import InMailPitchModal from '../modals/InMailPitchModal.jsx'
import PostReaderModal from '../modals/PostReaderModal.jsx'
import JobFilterDrawer, { DEFAULT_FILTERS } from './JobFilterDrawer.jsx'
import LocationPickerModal from '../hunter/LocationPickerModal.jsx'
import JobDetailWorkbench from './JobDetailWorkbench.jsx'
import client from '../../api/client.js'
import { useToast } from '../../context/ToastContext.jsx'

const CORE_SITES = [
  { id: 'linkedin', label: 'LinkedIn Jobs', color: 'bg-blue-600' },
  { id: 'indeed', label: 'Indeed', color: 'bg-indigo-600' },
  { id: 'zip_recruiter', label: 'ZipRecruiter', color: 'bg-emerald-600' },
  { id: 'google', label: 'Google Jobs', color: 'bg-rose-600' },
]

const POPULAR_COUNTRIES = [
  { code: 'Worldwide', label: 'Worldwide', flag: '🌐' },
  { code: 'USA', label: 'USA', flag: '🇺🇸' },
  { code: 'UAE', label: 'UAE', flag: '🇦🇪' },
  { code: 'UK', label: 'UK', flag: '🇬🇧' },
  { code: 'Canada', label: 'Canada', flag: '🇨🇦' },
  { code: 'Germany', label: 'Germany', flag: '🇩🇪' },
  { code: 'France', label: 'France', flag: '🇫🇷' },
  { code: 'Netherlands', label: 'Netherlands', flag: '🇳🇱' },
  { code: 'Morocco', label: 'Morocco', flag: '🇲🇦' },
  { code: 'Singapore', label: 'Singapore', flag: '🇸🇬' },
]

const QUICK_ROLES = [
  'Flutter Developer',
  'Mobile App Developer',
  'Full Stack Developer',
  'React / Next.js',
  'Python / AI Engineer',
  'Backend Engineer',
  'DevOps / Cloud'
]

export default function JobBoardScraper({
  jobs = [],
  loading,
  onSearch,
  onSaveJob,
  onOpenDetail,
  onTailorJob,
  isJobApplied,
  isJobSaved,
  onJobApplied,
  onSwitchToPosts
}) {
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [selectedCountries, setSelectedCountries] = useState(['Worldwide'])
  const [showLocationPicker, setShowLocationPicker] = useState(false)
  const [selectedSites, setSelectedSites] = useState(['linkedin', 'indeed', 'zip_recruiter', 'google'])
  const [resultsCount, setResultsCount] = useState(30)
  const [isRemote, setIsRemote] = useState(false)
  const [cvAnalyzing, setCvAnalyzing] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const [localJobs, setLocalJobs] = useState(jobs || [])

  // Auto-mark searched if jobs prop has items & sync local state
  useEffect(() => {
    setLocalJobs(jobs || [])
    if (jobs && jobs.length > 0) {
      setHasSearched(true)
    }
  }, [jobs])

  const handleUpdateJob = (updatedJob) => {
    if (!updatedJob) return
    setLocalJobs(prev => prev.map(j => {
      const match = (updatedJob.id && j.id === updatedJob.id) || (updatedJob.url && j.url === updatedJob.url)
      return match ? { ...j, ...updatedJob } : j
    }))
  }

  // Handle immediate local removal and synchronization when job(s) applied
  const handleAppliedLocally = (jobOrList) => {
    const list = Array.isArray(jobOrList) ? jobOrList : [jobOrList]
    if (list.length === 0) return

    const appliedUrls = new Set()
    const appliedTcs = new Set()

    list.forEach(item => {
      const raw = item.raw || item
      const u = (raw.url || raw.job_url || raw.job_url_direct || raw.post_url || '').trim().toLowerCase()
      const cleanU = u ? u.split('?')[0].replace(/\/+$/, '') : ''
      const tc = `${(raw.title || raw.role_title || '').trim().toLowerCase()}|${(raw.company || '').trim().toLowerCase()}`
      if (u) appliedUrls.add(u)
      if (cleanU) appliedUrls.add(cleanU)
      if (tc !== '|') appliedTcs.add(tc)

      if (onJobApplied) {
        onJobApplied(raw)
      }
    })

    setLocalJobs(prev => prev.filter(j => {
      const jUrl = (j.url || j.job_url || j.job_url_direct || '').trim().toLowerCase()
      const jCleanUrl = jUrl ? jUrl.split('?')[0].replace(/\/+$/, '') : ''
      const jTc = `${(j.title || '').trim().toLowerCase()}|${(j.company || '').trim().toLowerCase()}`
      if (jUrl && (appliedUrls.has(jUrl) || appliedUrls.has(jCleanUrl))) return false
      if (jTc !== '|' && appliedTcs.has(jTc)) return false
      return true
    }))
  }

  // Explicit Mark as Applied action (external portal / manual application)
  const handleMarkApplied = async (job) => {
    if (!job) return
    try {
      await client.post('/jobs/mark-applied', {
        title: job.title,
        company: job.company,
        location: job.location,
        url: job.url || job.job_url_direct || job.job_url || '',
        match_score: job.score || 0,
        notes: 'Applied on external portal.'
      })
      handleAppliedLocally(job)
      toast(`✅ Marked ${job.title} at ${job.company} as Applied & moved to Tracker!`, 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to mark as applied', 'error')
    }
  }

  // Filters State & Drawer
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Expanded tips accordion per job
  const [expandedTipsJobId, setExpandedTipsJobId] = useState(null)

  // Active Modals & View Mode
  const [viewMode, setViewMode] = useState('split') // 'split' | 'cards'
  const [selectedJobId, setSelectedJobId] = useState(null)
  const [inmailTarget, setInmailTarget] = useState(null)
  const [readerTarget, setReaderTarget] = useState(null)
  const [autoApplyJob, setAutoApplyJob] = useState(null)
  const [batchApplyOpen, setBatchApplyOpen] = useState(false)
  const [easyApplyJob, setEasyApplyJob] = useState(null)
  const [batchEasyApplyOpen, setBatchEasyApplyOpen] = useState(false)
  const [showSmtpPrompt, setShowSmtpPrompt] = useState(false)

  const getHoursOld = (filterSet = filters) => {
    if (!filterSet?.datePosted || filterSet.datePosted === 'all') return null
    if (filterSet.datePosted === '24h') return 24
    if (filterSet.datePosted === 'week') return 168
    if (filterSet.datePosted === 'month') return 720
    return null
  }

  const handleSubmit = (e) => {
    if (e) e.preventDefault()
    if (!title.trim()) {
      toast('Please enter a role or skill to search', 'error')
      return
    }
    setHasSearched(true)
    onSearch({
      title: title.trim(),
      countries: selectedCountries,
      sites: selectedSites,
      results_wanted: resultsCount,
      is_remote: isRemote,
      hours_old: getHoursOld(filters),
      filters: filters
    })
  }

  // Quick Preset Role Click
  const handleQuickRoleSearch = (roleName, countriesToUse = selectedCountries) => {
    setTitle(roleName)
    setHasSearched(true)
    onSearch({
      title: roleName,
      countries: countriesToUse,
      sites: selectedSites,
      results_wanted: resultsCount,
      is_remote: isRemote,
      hours_old: getHoursOld(filters),
      filters: filters
    })
  }

  // 1-Click Search with My CV for Job Boards
  const handleSearchByCv = async () => {
    setCvAnalyzing(true)
    try {
      const { data } = await client.get('/cv/analyze')
      const targetQuery = data.search_query || data.title || data.primary_title || 'Software Developer'
      setTitle(targetQuery)

      let newCountries = selectedCountries
      if (data.suggested_countries && data.suggested_countries.length > 0) {
        const match = POPULAR_COUNTRIES.filter(c =>
          data.suggested_countries.some(sc =>
            sc.toLowerCase().includes(c.code.toLowerCase()) ||
            sc.toLowerCase().includes(c.label.toLowerCase())
          )
        ).map(c => c.code)
        if (match.length > 0) {
          newCountries = match
          setSelectedCountries(newCountries)
        }
      }

      toast(`🎯 Analyzed your CV: Searching formal job boards for "${targetQuery}"...`, 'success')
      setHasSearched(true)

      onSearch({
        title: targetQuery,
        countries: newCountries,
        sites: selectedSites,
        results_wanted: resultsCount,
        is_remote: isRemote,
        hours_old: getHoursOld(filters),
        filters: filters
      })
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Please upload your CV first to search by CV!'
      toast(msg, 'error')
    } finally {
      setCvAnalyzing(false)
    }
  }

  // Helper to re-run the search when filters are applied or toggled
  const handleTriggerSearchWithFilters = (newFilters = filters) => {
    const searchRole = title.trim() || 'Software Engineer'
    if (!title.trim()) {
      setTitle(searchRole)
    }
    const isJobRemote = (newFilters.workplaceType || []).includes('remote') || isRemote
    onSearch({
      title: searchRole,
      countries: selectedCountries,
      sites: selectedSites,
      results_wanted: resultsCount,
      is_remote: isJobRemote,
      hours_old: getHoursOld(newFilters),
      filters: newFilters
    })
  }

  const handleToggleLocation = (loc) => {
    if (!loc || loc.toLowerCase() === 'worldwide') {
      setSelectedCountries(['Worldwide'])
      return
    }
    setSelectedCountries(prev => {
      const withoutWw = prev.filter(l => l.toLowerCase() !== 'worldwide')
      if (withoutWw.some(l => l.toLowerCase() === loc.toLowerCase())) {
        const rem = withoutWw.filter(l => l.toLowerCase() !== loc.toLowerCase())
        return rem.length > 0 ? rem : ['Worldwide']
      }
      return [...withoutWw, loc]
    })
  }

  const isWorldwide = selectedCountries.length === 1 && selectedCountries[0].toLowerCase() === 'worldwide'
  const locationLabel = isWorldwide ? 'Worldwide' : selectedCountries.join(', ')

  const toggleSite = (s) => {
    setSelectedSites(prev =>
      prev.includes(s) ? (prev.length > 1 ? prev.filter(x => x !== s) : prev) : [...prev, s]
    )
  }

  // Filter out already applied jobs so the candidate never sees them again
  const unappliedJobs = useMemo(() => {
    return (localJobs || []).filter(j => !isJobApplied(j))
  }, [localJobs, isJobApplied])

  // Count active filters for badge
  const activeFiltersCount = useMemo(() => {
    let cnt = 0
    if (filters.sortBy !== 'relevant') cnt++
    if (filters.datePosted !== 'all') cnt++
    if (filters.experience?.length > 0) cnt += filters.experience.length
    if (filters.companies?.length > 0) cnt += filters.companies.length
    if (filters.jobTypes?.length > 0) cnt += filters.jobTypes.length
    if (filters.workplaceType?.length > 0) cnt += filters.workplaceType.length
    if (filters.easyApply) cnt++
    if (filters.verifiedInfoOnly) cnt++
    if (filters.sectors?.length > 0) cnt += filters.sectors.length
    if (filters.functions?.length > 0) cnt += filters.functions.length
    if (filters.jobTitles?.length > 0) cnt += filters.jobTitles.length
    if (filters.under10Applicants) cnt++
    if (filters.inYourNetwork) cnt++
    if (filters.commitments?.length > 0) cnt += filters.commitments.length
    return cnt
  }, [filters])

  const checkJobAgeMatch = (job, datePostedFilter) => {
    if (!datePostedFilter || datePostedFilter === 'all') return true
    
    // If backend computed age_hours
    if (job.age_hours != null) {
      if (datePostedFilter === '24h') return job.age_hours <= 24.0
      if (datePostedFilter === 'week') return job.age_hours <= 168.0
      if (datePostedFilter === 'month') return job.age_hours <= 720.0
    }
    
    // If backend computed is_under_24h
    if (datePostedFilter === '24h' && job.is_under_24h) return true

    // Fallback check on date_posted or age_str
    const dateStr = String(job.date_posted || job.age_str || '').toLowerCase().trim()
    if (!dateStr) {
      // If 24h filter is strictly requested and we have no proof it's fresh, exclude it
      if (datePostedFilter === '24h') return false
      return true
    }

    // Obvious older indicators
    if (dateStr.includes('week') || dateStr.includes('wk') || dateStr.includes('mo') || dateStr.includes('month') || dateStr.includes('year') || dateStr.includes('yr')) {
      return false
    }
    const matchDays = dateStr.match(/(\d+)\s*(?:d|day)/)
    if (matchDays) {
      const days = parseInt(matchDays[1], 10)
      if (datePostedFilter === '24h') return false
      if (datePostedFilter === 'week' && days > 7) return false
      if (datePostedFilter === 'month' && days > 30) return false
      return true
    }

    const matchHours = dateStr.match(/(\d+)\s*(?:h|hr|hour)/)
    if (matchHours) {
      const hours = parseInt(matchHours[1], 10)
      if (datePostedFilter === '24h') return hours <= 24
      return true
    }

    if (dateStr.includes('just now') || dateStr.includes('today') || dateStr.includes('minute') || dateStr.includes('min') || dateStr.includes('m ago') || dateStr.includes('sec')) {
      return true
    }

    // Try parsing ISO date
    const parsed = Date.parse(dateStr)
    if (!isNaN(parsed)) {
      const diffHours = (Date.now() - parsed) / (1000 * 3600)
      if (datePostedFilter === '24h') return diffHours <= 24.0
      if (datePostedFilter === 'week') return diffHours <= 168.0
      if (datePostedFilter === 'month') return diffHours <= 720.0
    }

    return datePostedFilter !== '24h'
  }

  // Multi-criteria client-side filtering matching the 14 LinkedIn categories
  const filteredJobs = useMemo(() => {
    return unappliedJobs.filter(job => {
      const desc = (job.description || '').toLowerCase()
      const t = (job.title || '').toLowerCase()
      const comp = (job.company || '').toLowerCase()
      const loc = (job.location || '').toLowerCase()

      // Date posted
      if (!checkJobAgeMatch(job, filters.datePosted)) {
        return false
      }

      // Experience
      if (filters.experience?.length > 0) {
        const matchesExp = filters.experience.some(exp => {
          if (exp === 'internship') return t.includes('intern') || desc.includes('stage') || desc.includes('alternan')
          if (exp === 'entry') return t.includes('junior') || desc.includes('entry level') || desc.includes('premier emploi')
          if (exp === 'associate') return t.includes('mid') || desc.includes('associate') || desc.includes('confirmé')
          if (exp === 'senior') return t.includes('senior') || t.includes('lead') || desc.includes('cadre')
          if (exp === 'director') return t.includes('director') || t.includes('directeur') || t.includes('head')
          if (exp === 'executive') return t.includes('vp') || t.includes('c-level') || t.includes('chief')
          return false
        })
        if (!matchesExp) return false
      }

      // Workplace type (remote, onsite, hybrid)
      if (filters.workplaceType?.length > 0) {
        const isJobRemote = job.is_remote || loc.includes('remote') || desc.includes('à distance') || desc.includes('remote')
        const isJobHybrid = loc.includes('hybrid') || desc.includes('hybride') || desc.includes('hybrid')
        const isJobOnsite = !isJobRemote && !isJobHybrid

        const matchesWorkplace = filters.workplaceType.some(wt => {
          if (wt === 'remote') return isJobRemote
          if (wt === 'hybrid') return isJobHybrid
          if (wt === 'onsite') return isJobOnsite
          return false
        })
        if (!matchesWorkplace) return false
      }

      // Job Types
      if (filters.jobTypes?.length > 0) {
        const matchesType = filters.jobTypes.some(jt => {
          if (jt === 'fulltime') return desc.includes('full-time') || desc.includes('temps plein') || desc.includes('cdi')
          if (jt === 'contract') return desc.includes('contract') || desc.includes('cdd') || desc.includes('freelance')
          if (jt === 'internship') return desc.includes('intern') || desc.includes('stage') || desc.includes('alternance')
          if (jt === 'parttime') return desc.includes('part-time') || desc.includes('temps partiel')
          return false
        })
        if (!matchesType) return false
      }

      // Companies
      if (filters.companies?.length > 0) {
        const matchesComp = filters.companies.some(c => comp.includes(c.toLowerCase()))
        if (!matchesComp) return false
      }

      // Verified info only (has deliverable recruiter email)
      if (filters.verifiedInfoOnly) {
        const hasEmail = (Array.isArray(job.emails) && job.emails.length > 0) || (job.to_email && job.to_email.includes('@'))
        if (!hasEmail) return false
      }

      // Easy Apply
      if (filters.easyApply) {
        const hasEasy = job.easy_apply || (Array.isArray(job.emails) && job.emails.length > 0)
        if (!hasEasy) return false
      }

      // Sectors
      if (filters.sectors?.length > 0) {
        const matchesSector = filters.sectors.some(sec => {
          const sNorm = sec.toLowerCase()
          return desc.includes(sNorm) || t.includes(sNorm)
        })
        if (!matchesSector) return false
      }

      // Functions
      if (filters.functions?.length > 0) {
        const matchesFn = filters.functions.some(fn => {
          const fNorm = fn.toLowerCase()
          return desc.includes(fNorm) || t.includes(fNorm)
        })
        if (!matchesFn) return false
      }

      // Job Titles
      if (filters.jobTitles?.length > 0) {
        const matchesTitle = filters.jobTitles.some(jt => {
          const tNorm = jt.toLowerCase()
          return t.includes(tNorm)
        })
        if (!matchesTitle) return false
      }

      // Commitments
      if (filters.commitments?.length > 0) {
        const matchesComm = filters.commitments.some(comm => {
          const cNorm = comm.toLowerCase()
          return desc.includes(cNorm)
        })
        if (!matchesComm) return false
      }

      return true
    }).sort((a, b) => {
      if (filters.sortBy === 'recent') {
        return (a.age_hours ?? 999) - (b.age_hours ?? 999)
      }
      return (b.score ?? 0) - (a.score ?? 0)
    })
  }, [unappliedJobs, filters])

  // Find all unapplied jobs that have deliverable recruiter emails
  const jobsWithEmails = useMemo(() => {
    return filteredJobs.filter(j => {
      if (Array.isArray(j.emails) && j.emails.length > 0) return true
      if (j.to_email && j.to_email.includes('@')) return true
      return false
    })
  }, [filteredJobs])

  // Helper: check if a job supports Candidature Simplifiée (Easy Apply)
  const checkIsEasyApply = (job) => {
    if (!job) return false
    return Boolean(job.easy_apply || job.is_direct_apply)
  }

  // Find all unapplied jobs WITHOUT email that support Candidature Simplifiée (Easy Apply)
  const easyApplyJobsWithoutEmail = useMemo(() => {
    return filteredJobs.filter(j => {
      const hasEmail = (Array.isArray(j.emails) && j.emails.length > 0) || (j.to_email && j.to_email.includes('@'))
      if (hasEmail) return false
      return checkIsEasyApply(j)
    })
  }, [filteredJobs])

  // Active selected job for Split Workbench View
  const activeJob = useMemo(() => {
    if (!filteredJobs || filteredJobs.length === 0) return null
    if (selectedJobId) {
      const found = filteredJobs.find(j => (j.id || j.url) === selectedJobId)
      if (found) return found
    }
    return filteredJobs[0]
  }, [filteredJobs, selectedJobId])

  return (
    <div className="space-y-6">
      {/* Search Bar Panel */}
      <form onSubmit={handleSubmit} className="p-4 sm:p-5 rounded-2xl bg-slate-900 border border-slate-750 shadow-xl space-y-3">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 p-1.5 rounded-2xl bg-slate-950 border border-slate-800 focus-within:border-blue-500/80 transition-all shadow-inner">
          {/* Main Search Input */}
          <div className="relative flex-1 flex items-center min-h-[44px]">
            <Search size={18} className="absolute left-3.5 text-slate-500 pointer-events-none" />
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Search formal job board listings (e.g. Senior Flutter Developer, React)..."
              className="w-full bg-transparent pl-11 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none"
            />
          </div>

          {/* Location Selector Pill (Identical to Photo 1) */}
          <button
            type="button"
            onClick={() => setShowLocationPicker(true)}
            className="flex items-center justify-between sm:justify-start gap-2 px-3.5 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-800 border border-slate-700 hover:border-slate-600 text-xs text-slate-200 font-medium transition cursor-pointer shrink-0 max-w-full sm:max-w-[200px]"
            title="Click to select target country / region"
          >
            <div className="flex items-center gap-1.5 truncate">
              <Globe size={13} className="text-blue-400 shrink-0" />
              <span className="truncate">{locationLabel}</span>
            </div>
            <ChevronDown size={12} className="text-slate-500 shrink-0" />
          </button>

          {/* Status Badge (Identical to Photo 1) */}
          <div
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-semibold bg-emerald-950/60 border-emerald-500/50 text-emerald-300 shadow-xs shrink-0 select-none"
            title="Live scraping active across LinkedIn Jobs & Indeed"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            <span className="truncate">Live LinkedIn</span>
          </div>

          {/* 1-Click Search with My CV */}
          <button
            type="button"
            onClick={handleSearchByCv}
            disabled={cvAnalyzing || loading}
            className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-bold text-xs shadow-md shadow-purple-500/25 transition flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 shrink-0 border border-purple-400/30"
            title="Parse your CV and search formal listings"
          >
            {cvAnalyzing ? <Loader2 size={13} className="animate-spin text-white" /> : <Sparkles size={13} className="text-amber-300" />}
            <span className="truncate">{cvAnalyzing ? 'Analyzing CV...' : 'Search with My CV'}</span>
          </button>

          {/* Standard Search Button */}
          <button
            type="submit"
            disabled={loading || !title.trim()}
            className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-500/20 transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 shrink-0"
          >
            {loading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                <span>Scraping...</span>
              </>
            ) : (
              <>
                <Search size={14} />
                <span>Search Boards</span>
              </>
            )}
          </button>
        </div>

        {/* LinkedIn-Standard Filter Bar (Boards + 14 Categories) */}
        <div className="flex items-center justify-between gap-3 pt-2.5 border-t border-slate-800/80 flex-wrap text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Boards Selector */}
            <div className="flex items-center gap-1.5 mr-2">
              <span className="text-slate-400 font-medium">Boards:</span>
              {CORE_SITES.map(s => {
                const active = selectedSites.includes(s.id)
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => toggleSite(s.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer border ${
                      active
                        ? 'bg-blue-600/20 text-blue-300 border-blue-500/60'
                        : 'bg-slate-800 text-slate-400 border-slate-750 hover:text-white'
                    }`}
                  >
                    {s.label}
                  </button>
                )
              })}
            </div>
            {/* All Filters Button */}
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 hover:border-slate-600 text-slate-200 font-bold text-xs flex items-center gap-1.5 transition cursor-pointer shadow-xs"
            >
              <SlidersHorizontal size={13} className="text-blue-400" />
              <span>All Filters</span>
              {activeFiltersCount > 0 && (
                <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold">
                  {activeFiltersCount}
                </span>
              )}
            </button>

            {/* Quick Filter: Date Posted */}
            <select
              value={filters.datePosted}
              onChange={e => {
                const next = { ...filters, datePosted: e.target.value }
                setFilters(next)
                handleTriggerSearchWithFilters(next)
              }}
              className="bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              <option value="all">Date: Any time</option>
              <option value="24h">Past 24 hours</option>
              <option value="week">Past week</option>
              <option value="month">Past month</option>
            </select>

            {/* Target Results Count */}
            <select
              value={resultsCount}
              onChange={e => {
                const val = Number(e.target.value)
                setResultsCount(val)
              }}
              className="bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500 cursor-pointer"
              title="Target number of jobs to retrieve"
            >
              <option value={30}>30 jobs</option>
              <option value={60}>60 jobs</option>
              <option value={100}>100 jobs</option>
            </select>

            {/* Quick Filter: Remote */}
            <button
              type="button"
              onClick={() => {
                const list = filters.workplaceType || []
                const next = {
                  ...filters,
                  workplaceType: list.includes('remote') ? list.filter(x => x !== 'remote') : [...list, 'remote']
                }
                setFilters(next)
                handleTriggerSearchWithFilters(next)
              }}
              className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer flex items-center gap-1 ${
                filters.workplaceType?.includes('remote')
                  ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
              }`}
            >
              <MapPin size={11} />
              <span>Remote</span>
            </button>

            {/* Quick Filter: Verified Recruiter Email */}
            <button
              type="button"
              onClick={() => {
                const next = { ...filters, verifiedInfoOnly: !filters.verifiedInfoOnly }
                setFilters(next)
                handleTriggerSearchWithFilters(next)
              }}
              className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer flex items-center gap-1.5 ${
                filters.verifiedInfoOnly
                  ? 'bg-emerald-950/80 text-emerald-300 border-emerald-600'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
              }`}
            >
              <ShieldCheck size={12} className={filters.verifiedInfoOnly ? 'text-emerald-400' : 'text-slate-500'} />
              <span>Verified Recruiter Email</span>
            </button>

            {/* Quick Filter: Easy Apply */}
            <button
              type="button"
              onClick={() => {
                const next = { ...filters, easyApply: !filters.easyApply }
                setFilters(next)
                handleTriggerSearchWithFilters(next)
              }}
              className={`px-3 py-1.5 rounded-xl font-medium border transition cursor-pointer ${
                filters.easyApply
                  ? 'bg-blue-600/25 text-blue-300 border-blue-500/80'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
              }`}
            >
              <span>Easy Apply</span>
            </button>

            {/* Reset active filters */}
            {activeFiltersCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  setFilters(DEFAULT_FILTERS)
                  handleTriggerSearchWithFilters(DEFAULT_FILTERS)
                }}
                className="text-[11px] text-slate-500 hover:text-white flex items-center gap-1 transition cursor-pointer px-1.5"
                title="Clear all filters"
              >
                <RotateCcw size={10} />
                <span>Clear Filters</span>
              </button>
            )}
          </div>

          {/* Quick Sort: Relevant vs Recent & View Mode Toggle */}
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 text-[11px]">Sort by:</span>
              <select
                value={filters.sortBy}
                onChange={e => {
                  const next = { ...filters, sortBy: e.target.value }
                  setFilters(next)
                  handleTriggerSearchWithFilters(next)
                }}
                className="bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-1 text-xs text-slate-300 focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                <option value="relevant">Most relevant</option>
                <option value="recent">Most recent</option>
              </select>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center p-0.5 rounded-xl bg-slate-950 border border-slate-800">
              <button
                type="button"
                onClick={() => setViewMode('split')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${
                  viewMode === 'split' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-400 hover:text-white'
                }`}
                title="Split Workbench View"
              >
                <Columns size={13} />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('cards')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${
                  viewMode === 'cards' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-400 hover:text-white'
                }`}
                title="Multi-column Cards Grid"
              >
                <LayoutGrid size={13} />
              </button>
            </div>
          </div>
        </div>
      </form>

      {/* Bulk Action Banner when jobs have emails */}
      {jobsWithEmails.length > 0 && !loading && (
        <div className="p-3.5 rounded-xl bg-gradient-to-r from-blue-950/60 via-slate-900 to-purple-950/60 border border-blue-500/40 flex items-center justify-between gap-3 shadow-md flex-wrap">
          <div className="flex items-center gap-2.5 text-xs">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 text-blue-400 border border-blue-500/30 flex items-center justify-center shrink-0">
              <Zap size={16} />
            </div>
            <div>
              <span className="font-bold text-white">Discovered {jobsWithEmails.length} Job(s) with Verified Recruiter Emails!</span>
              <p className="text-[11px] text-slate-400">Dispatch tailored applications and customized resumes to all recruiters in 1 click.</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setBatchApplyOpen(true)}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs shadow-md shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer shrink-0"
          >
            <Send size={13} />
            <span>Auto-Apply to All with Emails ({jobsWithEmails.length})</span>
          </button>
        </div>
      )}

      {/* Bulk Action Banner when jobs have Candidature Simplifiée without emails */}
      {easyApplyJobsWithoutEmail.length > 0 && !loading && (
        <div className="p-3.5 rounded-xl bg-gradient-to-r from-amber-950/60 via-slate-900 to-indigo-950/60 border border-amber-500/40 flex items-center justify-between gap-3 shadow-md flex-wrap">
          <div className="flex items-center gap-2.5 text-xs">
            <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center shrink-0">
              <Zap size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-white">Discovered {easyApplyJobsWithoutEmail.length} Job(s) with Candidature Simplifiée!</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  Easy Apply
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Auto-apply to all simplified listings in 1 click with AI-tailored resumes and instant Tracker sync.</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setBatchEasyApplyOpen(true)}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs shadow-md shadow-amber-500/25 transition flex items-center gap-1.5 cursor-pointer shrink-0"
          >
            <Zap size={13} className="fill-slate-950 text-slate-950" />
            <span>Auto-Apply to All Candidatures Simplifiées ({easyApplyJobsWithoutEmail.length})</span>
          </button>
        </div>
      )}

      {/* Results List */}
      {loading ? (
        <div className="p-12 text-center text-slate-400 space-y-4 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-xl">
          <div className="relative w-12 h-12 mx-auto">
            <div className="absolute inset-0 rounded-full border-2 border-blue-500/20 animate-ping" />
            <div className="w-12 h-12 rounded-full border-2 border-t-blue-500 border-r-blue-400 border-b-transparent border-l-transparent animate-spin flex items-center justify-center">
              <Search size={18} className="text-blue-400" />
            </div>
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-bold text-white">
              Scraping Live Job Boards for <span className="text-blue-400">"{title || 'Jobs'}"</span>
            </p>
            <p className="text-xs text-slate-400">
              Querying <span className="text-purple-300 font-semibold">{selectedSites.map(s => s === 'linkedin' ? 'LinkedIn Jobs' : 'Indeed').join(' & ')}</span> across <span className="text-emerald-300 font-semibold">{selectedCountries.join(', ')}</span>...
            </p>
            <p className="text-[11px] text-slate-500 italic">
              Automating recruiter email extraction & resume ATS alignment
            </p>
          </div>
        </div>
      ) : filteredJobs.length > 0 ? (
        viewMode === 'split' ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Left Master Feed (5 cols) */}
            <div className="lg:col-span-5 space-y-2.5 max-h-[calc(100vh-140px)] overflow-y-auto pr-1 select-none">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 px-1 pb-1 flex items-center justify-between">
                <span>Job Postings ({filteredJobs.length})</span>
                <span className="text-slate-500 font-normal">Click to preview</span>
              </div>

              {filteredJobs.map((job, idx) => {
                const jobId = job.id || job.url || idx
                const isSelected = (activeJob?.id || activeJob?.url) === (job.id || job.url)
                const applied = isJobApplied(job)
                const matchedSkills = job.matched_skills || []
                const hasEmails = Array.isArray(job.emails) && job.emails.length > 0
                const primaryEmail = hasEmails
                  ? (typeof job.emails[0] === 'object' ? job.emails[0].email : job.emails[0])
                  : job.to_email
                const score = job.score != null ? job.score : (job.match_score != null ? job.match_score : 75)
                const isLinkedIn = (job.site || '').toLowerCase().includes('linkedin')

                return (
                  <div
                    key={jobId}
                    onClick={() => setSelectedJobId(job.id || job.url)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 relative ${
                      isSelected
                        ? 'bg-slate-800 border-blue-500 shadow-md shadow-blue-500/15 ring-1 ring-blue-500'
                        : 'bg-slate-850 hover:bg-slate-800 border-slate-750 hover:border-slate-700'
                    } ${applied ? 'border-l-4 border-l-emerald-500' : ''}`}
                  >
                    {/* Role Title & Match Fit */}
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="font-bold text-sm text-white leading-snug line-clamp-2">
                        {job.title}
                      </h4>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                          score >= 75
                            ? 'bg-emerald-950/80 border-emerald-700 text-emerald-300'
                            : score >= 55
                            ? 'bg-blue-950/80 border-blue-700 text-blue-300'
                            : 'bg-amber-950/80 border-amber-700 text-amber-300'
                        }`}>
                          {score}% CV
                        </span>
                      </div>
                    </div>

                    {/* Company, Location, Site */}
                    <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
                      <span className="font-semibold text-blue-300 flex items-center gap-1 truncate max-w-[130px]">
                        <Building2 size={11} className="text-blue-400 shrink-0" />
                        {job.company}
                      </span>
                      <span className="text-slate-500">·</span>
                      <span className="text-slate-400 flex items-center gap-1 truncate max-w-[120px]">
                        <MapPin size={10} className="shrink-0" />
                        {job.location || 'Remote'}
                      </span>
                      <span className="text-slate-500">·</span>
                      <span className={`px-1.5 py-0.2 rounded text-[10px] uppercase font-semibold border ${
                        isLinkedIn
                          ? 'bg-blue-950/80 text-blue-300 border-blue-800/80'
                          : 'bg-indigo-950/80 text-indigo-300 border-indigo-800/80'
                      }`}>
                        {job.site}
                      </span>
                      {job.age_str && (
                        <>
                          <span className="text-slate-500">·</span>
                          <span className={`px-1.5 py-0.2 rounded text-[10px] font-semibold border ${
                            job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)
                              ? 'bg-amber-950/80 text-amber-300 border-amber-800/80 flex items-center gap-0.5'
                              : 'bg-slate-800 text-slate-400 border-slate-700'
                          }`}>
                            {(job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)) && <span>⚡</span>}
                            {job.age_str}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Recruiter Email Badge */}
                    {primaryEmail && (
                      <div className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-950/70 border border-emerald-800/70 px-2 py-0.5 rounded-md w-fit">
                        <ShieldCheck size={11} className="text-emerald-400 shrink-0" />
                        <span className="font-mono truncate max-w-[200px]">{primaryEmail}</span>
                      </div>
                    )}

                    {/* Candidature Simplifiée Badge for jobs without email */}
                    {!primaryEmail && checkIsEasyApply(job) && (
                      <div className="flex items-center justify-between pt-0.5">
                        <div className="flex items-center gap-1 text-[10px] font-semibold text-amber-400 bg-amber-950/70 border border-amber-800/70 px-2 py-0.5 rounded-md w-fit">
                          <Zap size={10} className="fill-amber-400 text-amber-400 shrink-0" />
                          <span>Candidature Simplifiée</span>
                        </div>
                        {!applied && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setEasyApplyJob(job)
                            }}
                            className="px-2 py-0.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/50 text-amber-300 hover:text-amber-200 text-[10px] font-bold flex items-center gap-1 transition cursor-pointer"
                            title="1-click Auto Apply via Candidature Simplifiée"
                          >
                            <Zap size={10} className="fill-amber-300" />
                            <span>Auto-Apply</span>
                          </button>
                        )}
                      </div>
                    )}

                    {/* Matched skills pill preview */}
                    {matchedSkills.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap text-[10px]">
                        {matchedSkills.slice(0, 3).map((s, sIdx) => (
                          <span key={sIdx} className="bg-emerald-950/60 text-emerald-300 border border-emerald-800/50 px-1.5 py-0.2 rounded text-[10px]">
                            ✓ {s}
                          </span>
                        ))}
                        {matchedSkills.length > 3 && (
                          <span className="text-slate-500 text-[10px]">+{matchedSkills.length - 3}</span>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Right Active Detail Workbench (7 cols) - Exact same design as in photo! */}
            <div className="lg:col-span-7">
              <JobDetailWorkbench
                job={activeJob}
                isApplied={isJobApplied(activeJob)}
                isSaved={isJobSaved(activeJob)}
                onAutoApply={(j, em) => setAutoApplyJob({
                  ...j,
                  author_name: 'Hiring Team',
                  role_title: j.title,
                  recruiter_emails: [{ email: em, name: 'Hiring Team' }]
                })}
                onEasyApply={j => setEasyApplyJob(j)}
                onTailor={j => onTailorJob(j)}
                onOpenInMail={j => setInmailTarget(j)}
                onOpenReader={j => setReaderTarget(j)}
                onSave={j => onSaveJob(j)}
                onMarkApplied={handleMarkApplied}
                onUpdateJob={handleUpdateJob}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 px-1 flex items-center justify-between">
              <span>Formal Job Postings ({filteredJobs.length}{activeFiltersCount > 0 ? ` filtrés sur ${unappliedJobs.length}` : ''})</span>
              {jobsWithEmails.length > 0 && (
                <span className="text-emerald-400 font-normal">
                  {jobsWithEmails.length} with direct recruiter email
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {filteredJobs.map((job, idx) => {
                const applied = isJobApplied(job)
                const saved = isJobSaved(job)
                const matchedSkills = job.matched_skills || []
                const missingSkills = job.missing_skills || []
                const tips = job.tips || []
                const hasEmails = Array.isArray(job.emails) && job.emails.length > 0
                const primaryEmail = hasEmails
                  ? (typeof job.emails[0] === 'object' ? job.emails[0].email : job.emails[0])
                  : null
                const isTipsExpanded = expandedTipsJobId === (job.id || idx)

                return (
                  <div
                    key={job.id || idx}
                    className="p-4 rounded-xl bg-slate-900 border border-slate-750 hover:border-slate-650 transition flex flex-col justify-between space-y-3 relative shadow-xs"
                  >
                    <div className="space-y-2">
                      {/* Header: Title & ATS Score */}
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="font-bold text-sm text-white line-clamp-1">{job.title}</h4>
                        {job.score != null ? (
                          <ScoreBadge score={job.score} />
                        ) : null}
                      </div>

                      {/* Company, Location, Board */}
                      <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
                        <span className="font-semibold text-blue-300 flex items-center gap-1">
                          <Building2 size={11} className="text-blue-400" />
                          {job.company}
                        </span>
                        <span className="text-slate-500">·</span>
                        <span className="text-slate-400 flex items-center gap-1">
                          <MapPin size={11} />
                          {job.location || 'Remote'}
                        </span>
                        <span className="text-slate-500">·</span>
                        <span className="text-slate-400 capitalize bg-slate-800 px-1.5 py-0.5 rounded text-[10px]">{job.site}</span>
                        {job.age_str && (
                          <>
                            <span className="text-slate-500">·</span>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                              job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)
                                ? 'bg-amber-950/80 text-amber-300 border-amber-800/80 flex items-center gap-0.5'
                                : 'bg-slate-800 text-slate-400 border-slate-700'
                            }`}>
                              {(job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)) && <span>⚡</span>}
                              {job.age_str}
                            </span>
                          </>
                        )}
                      </div>

                      {/* Recruiter Email Badge if discovered */}
                      {primaryEmail && (
                        <div className="flex items-center gap-1.5 text-[11px] text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.8 rounded-lg w-fit">
                          <ShieldCheck size={12} className="text-emerald-400 shrink-0" />
                          <span className="font-mono">{primaryEmail}</span>
                        </div>
                      )}

                      {/* Candidature Simplifiée Badge if discovered and no email */}
                      {!primaryEmail && checkIsEasyApply(job) && (
                        <div className="flex items-center gap-1.5 text-[11px] text-amber-400 bg-amber-950/60 border border-amber-800/60 px-2 py-0.8 rounded-lg w-fit">
                          <Zap size={12} className="fill-amber-400 text-amber-400 shrink-0" />
                          <span>Candidature Simplifiée (Easy Apply)</span>
                        </div>
                      )}

                      {/* Matched & Missing Skills Pills */}
                      {(matchedSkills.length > 0 || missingSkills.length > 0) && (
                        <div className="space-y-1.5 pt-1">
                          {matchedSkills.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap text-[10px]">
                              <span className="text-slate-500 font-semibold mr-0.5">Matched:</span>
                              {matchedSkills.slice(0, 4).map((s, sIdx) => (
                                <span key={sIdx} className="bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 px-1.5 py-0.5 rounded font-medium">
                                  ✓ {s}
                                </span>
                              ))}
                              {matchedSkills.length > 4 && (
                                <span className="text-slate-500 font-medium">+{matchedSkills.length - 4}</span>
                              )}
                            </div>
                          )}

                          {missingSkills.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap text-[10px]">
                              <span className="text-amber-500/90 font-semibold mr-0.5">Missing:</span>
                              {missingSkills.slice(0, 3).map((s, sIdx) => (
                                <span key={sIdx} className="bg-amber-950/70 text-amber-300 border border-amber-800/60 px-1.5 py-0.5 rounded font-medium flex items-center gap-0.5">
                                  <AlertCircle size={9} /> {s}
                                </span>
                              ))}
                              {missingSkills.length > 3 && (
                                <span className="text-amber-500 font-medium">+{missingSkills.length - 3}</span>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Snippet */}
                      <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                        {job.description}
                      </p>

                      {/* Expandable Tips */}
                      {tips.length > 0 && (
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={() => setExpandedTipsJobId(isTipsExpanded ? null : (job.id || idx))}
                            className="text-[11px] text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium transition cursor-pointer"
                          >
                            <span>{isTipsExpanded ? 'Hide Improvement Tips' : `Tips to Pass ATS (${tips.length})`}</span>
                            {isTipsExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                          </button>

                          <AnimatePresence>
                            {isTipsExpanded && (
                              <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className="mt-1.5 p-2 rounded-lg bg-blue-950/40 border border-blue-900/60 space-y-1 text-[11px] text-slate-300"
                              >
                                {tips.map((tip, tIdx) => (
                                  <div key={tIdx} className="flex items-start gap-1.5 leading-relaxed">
                                    <span className="text-blue-400 shrink-0">•</span>
                                    <span>{tip}</span>
                                  </div>
                                ))}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      )}
                    </div>

                    {/* Actions Row */}
                    <div className="flex items-center justify-between pt-2.5 border-t border-slate-800 text-xs gap-2">
                      <a
                        href={job.url || job.job_url_direct}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
                      >
                        <span>Apply on Portal</span>
                        <ExternalLink size={11} />
                      </a>

                      <div className="flex items-center gap-1.5">
                        {/* 1-Click Auto Apply if email exists */}
                        {primaryEmail && !applied && (
                          <button
                            type="button"
                            onClick={() => setAutoApplyJob({
                              ...job,
                              author_name: 'Hiring Team',
                              role_title: job.title,
                              recruiter_emails: [{ email: primaryEmail, name: 'Hiring Team' }]
                            })}
                            className="px-2.5 py-1 rounded-lg bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 text-xs font-bold flex items-center gap-1 cursor-pointer transition shadow-xs"
                            title="Direct 1-click email application to recruiter"
                          >
                            <Send size={11} />
                            <span>Auto Apply</span>
                          </button>
                        )}

                        {/* 1-Click Auto Apply if Candidature Simplifiée without email */}
                        {!primaryEmail && checkIsEasyApply(job) && !applied && (
                          <button
                            type="button"
                            onClick={() => setEasyApplyJob(job)}
                            className="px-2.5 py-1 rounded-lg bg-amber-950/80 hover:bg-amber-900 border border-amber-600/70 text-amber-300 text-xs font-bold flex items-center gap-1 cursor-pointer transition shadow-xs"
                            title="Auto-Apply via Candidature Simplifiée"
                          >
                            <Zap size={11} className="fill-amber-300" />
                            <span>Auto Apply</span>
                          </button>
                        )}

                        {/* Mark Applied for manual/external applications */}
                        {!applied && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleMarkApplied(job)
                            }}
                            className="px-2.5 py-1 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/80 border border-emerald-800/60 text-emerald-300 text-xs font-semibold flex items-center gap-1 cursor-pointer transition"
                            title="Mark as applied and move to Tracker"
                          >
                            <CheckCheck size={11} />
                            <span>Applied</span>
                          </button>
                        )}

                        {/* Tailor CV */}
                        <button
                          type="button"
                          onClick={() => onTailorJob(job)}
                          className="px-2.5 py-1 rounded-lg bg-purple-950/60 hover:bg-purple-900 border border-purple-800 text-purple-300 text-xs font-semibold flex items-center gap-1 cursor-pointer transition"
                        >
                          <Sparkles size={11} />
                          <span>Tailor CV</span>
                        </button>

                        {/* Bookmark */}
                        <button
                          type="button"
                          onClick={() => onSaveJob(job)}
                          disabled={saved || applied}
                          className="p-1.5 rounded-lg border border-slate-755 hover:bg-slate-800 text-slate-400 hover:text-white transition disabled:opacity-40 cursor-pointer"
                          title={saved ? 'Saved' : 'Save job'}
                        >
                          <Bookmark size={13} className={saved ? 'fill-blue-400 text-blue-400' : ''} />
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      ) : unappliedJobs.length > 0 ? (
        <div className="p-8 text-center text-slate-400 space-y-2 bg-slate-900/40 border border-slate-800 rounded-2xl">
          <p className="text-sm font-bold text-white">No jobs match your selected filters</p>
          <p className="text-xs text-slate-400">Try broadening your date, experience, or industry filters.</p>
          <button
            type="button"
            onClick={() => {
              setFilters(DEFAULT_FILTERS)
              handleTriggerSearchWithFilters(DEFAULT_FILTERS)
            }}
            className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold mt-2 cursor-pointer transition"
          >
            Reset filters
          </button>
        </div>
      ) : hasSearched ? (
        <div className="p-10 text-center space-y-5 bg-slate-900/50 border border-slate-800 rounded-2xl">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center mx-auto shadow-inner">
            <AlertCircle size={26} />
          </div>
          <div className="max-w-md mx-auto space-y-1.5">
            <h3 className="text-base font-bold text-white">
              No formal job board postings found for "{title}" in {selectedCountries.join(', ')}
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Job boards often use specific role naming conventions or strict geographic restrictions. Try expanding your search location or search authentic recruiter posts in the live feed.
            </p>
          </div>

          <div className="flex items-center justify-center gap-3 flex-wrap pt-2">
            <button
              type="button"
              onClick={() => {
                const expanded = ['Worldwide']
                setSelectedCountries(expanded)
                handleQuickRoleSearch(title, expanded)
              }}
              className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center gap-2 transition cursor-pointer shadow-md shadow-blue-600/25"
            >
              <Globe size={14} />
              <span>Expand to Worldwide (Global)</span>
            </button>

            {onSwitchToPosts && (
              <button
                type="button"
                onClick={() => onSwitchToPosts(title)}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-2 transition cursor-pointer shadow-md shadow-purple-600/25"
              >
                <Sparkles size={14} className="text-amber-300" />
                <span>Search LinkedIn Recruiter Posts</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleSubmit}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white border border-slate-700 text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer"
            >
              <RotateCcw size={13} />
              <span>Retry Search</span>
            </button>
          </div>

          {/* Broader Keyword Suggestions */}
          <div className="pt-4 border-t border-slate-800/80 max-w-lg mx-auto">
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2.5">
              Suggested Broader Search Terms:
            </p>
            <div className="flex items-center justify-center gap-2 flex-wrap">
              {['Mobile Developer', 'Software Engineer', 'Full Stack Developer', 'Frontend Developer'].map(alt => (
                <button
                  key={alt}
                  type="button"
                  onClick={() => handleQuickRoleSearch(alt)}
                  className="px-3 py-1 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-750 text-slate-300 hover:text-white text-xs transition cursor-pointer flex items-center gap-1"
                >
                  <Search size={11} className="text-slate-500" />
                  <span>{alt}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Initial Ready-to-Search Explorer Card */
        <div className="p-8 sm:p-10 rounded-2xl bg-gradient-to-b from-slate-900/80 to-slate-950 border border-slate-800/80 shadow-xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-bold mb-2">
                <Briefcase size={12} />
                <span>Dual-Board Aggregator</span>
              </div>
              <h3 className="text-xl font-black text-white tracking-tight">
                Search Formal Job Boards with Recruiter Intelligence
              </h3>
              <p className="text-xs text-slate-400 mt-1 max-w-xl">
                Scrapes active postings directly from LinkedIn Jobs & Indeed. Automatically mines direct recruiter emails and calculates ATS CV alignment scores.
              </p>
            </div>
          </div>

          {/* Quick Start Presets */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2.5">
            <p className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <Sparkles size={13} className="text-amber-400" />
              <span>Quick Role Presets (Click to Search Instantly):</span>
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              {QUICK_ROLES.map(roleName => (
                <button
                  key={roleName}
                  type="button"
                  onClick={() => handleQuickRoleSearch(roleName)}
                  className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-750 hover:border-blue-500/60 hover:bg-slate-850 text-slate-300 hover:text-white text-xs font-medium transition cursor-pointer flex items-center gap-1.5 group"
                >
                  <Search size={11} className="text-slate-500 group-hover:text-blue-400 transition" />
                  <span>{roleName}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 3 Pillars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-1.5">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center font-bold text-xs">
                01
              </div>
              <h4 className="text-xs font-bold text-white">Live Multi-Country Scraping</h4>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Queries Indeed & LinkedIn Jobs simultaneously across 9+ countries without outdated caches.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-1.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold text-xs">
                02
              </div>
              <h4 className="text-xs font-bold text-white">Direct Recruiter Email Mining</h4>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Extracts contact emails from job descriptions and company domains for direct email outreach.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-1.5">
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center font-bold text-xs">
                03
              </div>
              <h4 className="text-xs font-bold text-white">ATS CV Scoring & 1-Click Apply</h4>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Analyzes matched vs missing skills and generates customized cover letters with 1-click batch sending.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Location Picker Modal */}
      <LocationPickerModal
        isOpen={showLocationPicker}
        onClose={() => setShowLocationPicker(false)}
        selectedLocations={selectedCountries}
        onToggleLocation={handleToggleLocation}
      />

      {/* 14-Category LinkedIn Filter Drawer */}
      <JobFilterDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        filters={filters}
        onApplyFilters={f => {
          setFilters(f)
          handleTriggerSearchWithFilters(f)
        }}
        onResetFilters={() => {
          setFilters(DEFAULT_FILTERS)
          handleTriggerSearchWithFilters(DEFAULT_FILTERS)
        }}
      />

      {/* Auto-Apply Modal for Single Job */}
      <AutoApplyModal
        isOpen={Boolean(autoApplyJob)}
        onClose={() => setAutoApplyJob(null)}
        post={autoApplyJob}
        onSuccess={(applied) => handleAppliedLocally(applied || autoApplyJob)}
        onOpenSmtpPrompt={() => setShowSmtpPrompt(true)}
      />

      {/* Candidature Simplifiée Modal (Single Job) */}
      <EasyApplyModal
        isOpen={Boolean(easyApplyJob)}
        onClose={() => setEasyApplyJob(null)}
        job={easyApplyJob}
        onSuccess={(applied) => handleAppliedLocally(applied || easyApplyJob)}
      />

      {/* Batch Auto-Apply Modal for All Jobs with Emails */}
      <BatchApplyModal
        isOpen={batchApplyOpen}
        onClose={() => setBatchApplyOpen(false)}
        items={jobsWithEmails}
        source="jobs"
        onSuccess={(appliedList) => handleAppliedLocally(appliedList)}
        onOpenSmtpPrompt={() => setShowSmtpPrompt(true)}
      />

      {/* Batch Candidature Simplifiée Modal (All Jobs without Email) */}
      <BatchEasyApplyModal
        isOpen={batchEasyApplyOpen}
        onClose={() => setBatchEasyApplyOpen(false)}
        items={easyApplyJobsWithoutEmail}
        jobs={easyApplyJobsWithoutEmail}
        onSuccess={(appliedList) => handleAppliedLocally(appliedList)}
      />

      {/* LinkedIn InMail / Pitch Modal */}
      <InMailPitchModal
        isOpen={Boolean(inmailTarget)}
        onClose={() => setInmailTarget(null)}
        post={inmailTarget}
      />

      {/* Full Description Reader Modal */}
      <PostReaderModal
        isOpen={Boolean(readerTarget)}
        onClose={() => setReaderTarget(null)}
        post={readerTarget}
        onAutoApply={p => setAutoApplyJob(p)}
      />

      {/* SMTP Prompt Modal */}
      <SmtpPromptModal
        isOpen={showSmtpPrompt}
        onClose={() => setShowSmtpPrompt(false)}
      />
    </div>
  )
}
