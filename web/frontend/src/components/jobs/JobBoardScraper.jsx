import { useState, useMemo, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, ExternalLink, Bookmark, Mail, Check, Sparkles,
  Building2, MapPin, Loader2, ShieldCheck, AlertCircle, Send,
  ChevronDown, ChevronUp, Zap, SlidersHorizontal, RotateCcw,
  Globe, Briefcase, Compass, Columns, LayoutGrid, CheckCheck, Target, TrendingUp
} from 'lucide-react'
import ScoreBadge from '../ScoreBadge.jsx'
import AutoApplyModal from '../modals/AutoApplyModal.jsx'
import BatchApplyModal from '../modals/BatchApplyModal.jsx'
import EasyApplyModal from '../modals/EasyApplyModal.jsx'
import BatchEasyApplyModal from '../modals/BatchEasyApplyModal.jsx'
import SmtpPromptModal from '../modals/SmtpPromptModal.jsx'
import InMailPitchModal from '../modals/InMailPitchModal.jsx'
import PostReaderModal from '../modals/PostReaderModal.jsx'
import UpskillModal from '../modals/UpskillModal.jsx'
import JobFilterDrawer from './JobFilterDrawer.jsx'
import LocationPickerModal from '../hunter/LocationPickerModal.jsx'
import JobDetailWorkbench from './JobDetailWorkbench.jsx'
import JobSignalBadges from './JobSignalBadges.jsx'
import { GuestBlurGate } from '../modals/AuthGateModal.jsx'
import client from '../../api/client.js'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import { DEFAULT_FILTERS, POPULAR_COUNTRIES, QUICK_ROLES } from '../../constants/searchConstants.js'
import { getCleanJobUrl } from '../../utils/jobUtils.js'

const CORE_SITES = [
  { id: 'linkedin', label: 'LinkedIn Jobs', color: 'bg-blue-600' },
  { id: 'indeed', label: 'Indeed', color: 'bg-indigo-600' },
  { id: 'job_bank', label: '🇨🇦 Job Bank Canada', color: 'bg-red-600' },
  { id: 'google', label: 'Google Jobs', color: 'bg-rose-600' },
  // Zero-auth open sources (ported from career-ops) — never blocked, always live data
  { id: 'remote_boards', label: '🌍 Remote Boards (7)', color: 'bg-teal-600',
    hint: 'Remotive, RemoteOK, Jobicy, Himalayas, We Work Remotely, Working Nomads, Arbeitnow' },
  { id: 'ats', label: '🏢 Company Careers (ATS)', color: 'bg-violet-600',
    hint: 'Greenhouse, Lever & Ashby career pages — direct from the employer, verified still open' },
  { id: 'hackernews', label: '🟧 HN Who\'s Hiring', color: 'bg-orange-600',
    hint: 'Latest Hacker News "Who is hiring?" thread' },
  { id: 'official_apis', label: 'Adzuna / Jooble / Careerjet', color: 'bg-emerald-600',
    hint: 'Free official job APIs (keys configured by the platform admin)' },
]

export default function JobBoardScraper({
  jobs = [],
  loading,
  streaming = false,
  searchMeta,
  onSearch,
  onSaveJob = () => {},
  onOpenDetail = () => {},
  onTailorJob = () => {},
  isJobApplied = () => false,
  isJobSaved = () => false,
  onJobApplied = () => {},
  onSwitchToPosts = () => {}
}) {
  const toast = useToast()
  const { isAuth } = useAuth()
  const [title, setTitle] = useState('')
  const [selectedCountries, setSelectedCountries] = useState(['Worldwide'])
  const [showLocationPicker, setShowLocationPicker] = useState(false)
  const [resultsCount, setResultsCount] = useState(30)
  const [isRemote, setIsRemote] = useState(false)
  const [cvAnalyzing, setCvAnalyzing] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const [localJobs, setLocalJobs] = useState(jobs || [])
  const [hasSerperKey, setHasSerperKey] = useState(false)
  const [upskillOpen, setUpskillOpen] = useState(false)

  // Every search automatically covers ALL sources — the user doesn't pick boards.
  // Google Jobs is only included when a Serper key is configured (otherwise it returns nothing).
  const selectedSites = useMemo(
    () => CORE_SITES.map(s => s.id).filter(id => id !== 'google' || hasSerperKey),
    [hasSerperKey]
  )
  const siteLabel = (id) => (CORE_SITES.find(s => s.id === id)?.label || id).replace(/^[^\w]+\s*/, '')

  // Auto-mark searched if jobs prop has items & sync local state
  useEffect(() => {
    setLocalJobs(jobs || [])
    if (jobs && jobs.length > 0) {
      setHasSearched(true)
    }
  }, [jobs])

  useEffect(() => {
    client.get('/jobs/scraper-config').then(r => {
      if (r.data?.has_serper) setHasSerperKey(true)
    }).catch(() => {})
  }, [])

  // After each search finishes, tell the user where we searched and what each source returned
  useEffect(() => {
    const st = searchMeta?.stats
    if (!st?.sites_searched?.length) return
    const parts = st.sites_searched.map(id => `${siteLabel(id)} (${st.per_site?.[id] || 0})`)
    toast(`🔎 Searched ${st.sites_searched.length} sources: ${parts.join(', ')}`, 'success')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchMeta])

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
      const cleanU = getCleanJobUrl(u)
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
      const jCleanUrl = getCleanJobUrl(jUrl)
      const jTc = `${(j.title || '').trim().toLowerCase()}|${(j.company || '').trim().toLowerCase()}`
      if (jUrl && (appliedUrls.has(jUrl) || (jCleanUrl && appliedUrls.has(jCleanUrl)))) return false
      if (jTc !== '|' && appliedTcs.has(jTc)) return false
      return true
    }))
  }

  // Explicit Mark as Applied action (external portal / manual application)
  const handleMarkApplied = async (job) => {
    if (!job) return
    if (!isAuth) {
      window.dispatchEvent(new CustomEvent('open-auth-gate', {
        detail: { reason: 'Create a Free Account to Track Your Applications' }
      }))
      return
    }
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
    if (filterSet.datePosted === '1h') return 1
    if (filterSet.datePosted === '3h') return 3
    if (filterSet.datePosted === '6h') return 6
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

      toast(`🎯 CV analyzed — searching all ${selectedSites.length} sources for "${targetQuery}"...`, 'success')
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
    const subDayMap = { '1h': 1.0, '3h': 3.0, '6h': 6.0, '24h': 24.0 }
    const isSubDayOr24h = datePostedFilter in subDayMap

    // If backend computed age_hours
    if (job.age_hours != null) {
      if (isSubDayOr24h) return job.age_hours <= subDayMap[datePostedFilter]
      if (datePostedFilter === 'week') return job.age_hours <= 168.0
      if (datePostedFilter === 'month') return job.age_hours <= 720.0
    }
    
    // If backend computed is_under_24h
    if (datePostedFilter === '24h' && job.is_under_24h) return true

    // Fallback check on date_posted or age_str
    const dateStr = String(job.date_posted || job.age_str || '').toLowerCase().trim()
    if (!dateStr) {
      // If sub-day or 24h filter is strictly requested and we have no proof it's fresh, exclude it
      if (isSubDayOr24h) return false
      return true
    }

    // Obvious older indicators
    if (dateStr.includes('week') || dateStr.includes('wk') || dateStr.includes('mo') || dateStr.includes('month') || dateStr.includes('year') || dateStr.includes('yr')) {
      return false
    }
    const matchDays = dateStr.match(/(\d+)\s*(?:d|day)/)
    if (matchDays) {
      const days = parseInt(matchDays[1], 10)
      if (datePostedFilter in { '1h': 1, '3h': 1, '6h': 1 }) return false
      if (datePostedFilter === '24h') return days <= 1
      if (datePostedFilter === 'week' && days > 7) return false
      if (datePostedFilter === 'month' && days > 30) return false
      return true
    }

    const matchHours = dateStr.match(/(\d+)\s*(?:h|hr|hour)/)
    if (matchHours) {
      const hours = parseInt(matchHours[1], 10)
      if (isSubDayOr24h) return hours <= subDayMap[datePostedFilter]
      return true
    }

    if (dateStr.includes('just now') || dateStr.includes('minute') || dateStr.includes('min') || dateStr.includes('m ago') || dateStr.includes('sec')) {
      return true
    }
    if (dateStr.includes('today') || dateStr.includes('yesterday')) {
      return !['1h', '3h', '6h'].includes(datePostedFilter)
    }

    // Try parsing ISO date
    const parsed = Date.parse(dateStr)
    if (!isNaN(parsed)) {
      const diffHours = (Date.now() - parsed) / (1000 * 3600)
      if (isSubDayOr24h) return diffHours <= (datePostedFilter === '24h' ? 36.0 : subDayMap[datePostedFilter] + 0.5)
      if (datePostedFilter === 'week') return diffHours <= 168.0
      if (datePostedFilter === 'month') return diffHours <= 720.0
    }

    return !isSubDayOr24h
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

      // International candidates only (Job Bank Canada LMIA / foreign worker eligible)
      if (filters.internationalOnly) {
        const isIntl = job.is_international_eligible ||
          job.site?.toLowerCase().includes('job_bank') ||
          job.site?.toLowerCase().includes('jobbank') ||
          desc.includes('international candidate') ||
          desc.includes('without a valid canadian work permit') ||
          desc.includes('who can apply')
        if (!isIntl) return false
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
      return (b.rank_score ?? b.score ?? 0) - (a.rank_score ?? a.score ?? 0)
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
      <form onSubmit={handleSubmit} className="p-4 sm:p-5 rounded-3xl glass-panel relative overflow-hidden space-y-3.5">
        <div className="glow-line-top" />
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 p-1.5 rounded-2xl bg-[#050811]/90 border border-white/[0.08] focus-within:border-blue-500/70 focus-within:ring-2 focus-within:ring-blue-500/15 transition-all shadow-inner">
          {/* Main Search Input */}
          <div className="relative flex-1 flex items-center min-h-[44px]">
            <Search size={18} className="absolute left-3.5 text-blue-400 pointer-events-none" />
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Search formal job board listings (e.g. Senior Flutter Developer, React)..."
              className="w-full bg-transparent pl-11 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none font-medium"
            />
          </div>

          {/* Location Selector Pill */}
          <button
            type="button"
            onClick={() => setShowLocationPicker(true)}
            className="flex items-center justify-between sm:justify-start gap-2 px-3.5 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] hover:border-blue-500/40 text-xs text-slate-200 font-semibold transition cursor-pointer shrink-0 max-w-full sm:max-w-[200px]"
            title="Click to select target country / region"
          >
            <div className="flex items-center gap-1.5 truncate">
              <Globe size={13} className="text-blue-400 shrink-0" />
              <span className="truncate">{locationLabel}</span>
            </div>
            <ChevronDown size={12} className="text-slate-500 shrink-0" />
          </button>

          {/* Primary Search Button */}
          <motion.button
            type="submit"
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            disabled={loading || !title.trim()}
            className="shimmer-btn px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 text-white text-xs font-extrabold shadow-lg shadow-blue-600/25 transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 shrink-0"
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
          </motion.button>
        </div>

        {/* LinkedIn-Standard Filter Bar (Boards + 14 Categories) */}
        <div className="flex items-center justify-between gap-3 pt-2.5 border-t border-white/[0.06] flex-wrap text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            {/* All Filters Button */}
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] hover:border-blue-500/40 text-slate-200 font-bold text-xs flex items-center gap-1.5 transition cursor-pointer shadow-xs"
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
              className="bg-[#050811]/90 border border-white/[0.08] rounded-xl px-2.5 py-1.5 text-xs text-slate-300 font-medium focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              <option value="all">Date: Any time</option>
              <option value="1h">⚡ Past 1 hour</option>
              <option value="3h">⚡ Past 3 hours</option>
              <option value="6h">⚡ Past 6 hours</option>
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
              className="bg-[#050811]/90 border border-white/[0.08] rounded-xl px-2.5 py-1.5 text-xs text-slate-300 font-medium focus:outline-none focus:border-blue-500 cursor-pointer"
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
              className={`px-3 py-1.5 rounded-xl font-semibold border transition cursor-pointer flex items-center gap-1 ${
                filters.workplaceType?.includes('remote')
                  ? 'bg-blue-500/20 text-blue-300 border-blue-500/50 shadow-sm shadow-blue-500/10'
                  : 'bg-[#050811]/90 text-slate-400 border-white/[0.08] hover:text-white'
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
              className={`px-3 py-1.5 rounded-xl font-semibold border transition cursor-pointer flex items-center gap-1.5 ${
                filters.verifiedInfoOnly
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/45 shadow-sm shadow-emerald-500/10'
                  : 'bg-[#050811]/90 text-slate-400 border-white/[0.08] hover:text-white'
              }`}
            >
              <ShieldCheck size={12} className={filters.verifiedInfoOnly ? 'text-emerald-400' : 'text-slate-500'} />
              <span>Verified Recruiter Email</span>
            </button>

            {/* Quick Filter: International Candidates (LMIA / Job Bank) */}
            <button
              type="button"
              onClick={() => {
                const nextVal = !filters.internationalOnly
                const next = { ...filters, internationalOnly: nextVal }
                setFilters(next)
                handleTriggerSearchWithFilters(next)
              }}
              className={`px-3 py-1.5 rounded-xl font-semibold border transition cursor-pointer flex items-center gap-1.5 ${
                filters.internationalOnly
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/45 shadow-sm shadow-amber-500/10'
                  : 'bg-[#050811]/90 text-slate-400 border-white/[0.08] hover:text-white'
              }`}
              title="Filter jobs open to international candidates (Job Bank Canada LMIA)"
            >
              <Globe size={12} className={filters.internationalOnly ? 'text-amber-400' : 'text-slate-500'} />
              <span>International (LMIA)</span>
            </button>

            {/* Upskill & Skill-Gap Heatmap Button (ported from ai-job-search /upskill) */}
            <button
              type="button"
              onClick={() => setUpskillOpen(true)}
              className="px-3 py-1.5 rounded-xl font-bold border bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 border-indigo-500/40 transition cursor-pointer flex items-center gap-1.5"
              title="Open Aggregate Skill-Gap Heatmap & Prioritized Learning Roadmap across these jobs"
            >
              <TrendingUp size={12} className="text-indigo-400" />
              <span>Upskill Heatmap</span>
            </button>

            {/* Reset active filters */}
            {activeFiltersCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  setFilters(DEFAULT_FILTERS)
                  handleTriggerSearchWithFilters(DEFAULT_FILTERS)
                }}
                className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1 transition cursor-pointer px-1.5 font-semibold"
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
              <span className="text-slate-500 text-[11px] font-medium">Sort by:</span>
              <select
                value={filters.sortBy}
                onChange={e => {
                  const next = { ...filters, sortBy: e.target.value }
                  setFilters(next)
                  handleTriggerSearchWithFilters(next)
                }}
                className="bg-[#050811]/90 border border-white/[0.08] rounded-xl px-2.5 py-1 text-xs text-slate-300 font-medium focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                <option value="relevant">Most relevant</option>
                <option value="recent">Most recent</option>
              </select>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center p-0.5 rounded-xl bg-[#050811]/90 border border-white/[0.08]">
              <button
                type="button"
                onClick={() => setViewMode('split')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${
                  viewMode === 'split' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
                }`}
                title="Split Workbench View"
              >
                <Columns size={13} />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('cards')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${
                  viewMode === 'cards' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
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
      {isAuth && jobsWithEmails.length > 0 && !loading && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 rounded-2xl glass-panel border border-blue-500/30 flex items-center justify-between gap-3 shadow-sm flex-wrap"
        >
          <div className="flex items-center gap-3 text-xs">
            <div className="w-9 h-9 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center justify-center shrink-0">
              <Zap size={16} />
            </div>
            <div>
              <span className="font-extrabold text-white">Discovered {jobsWithEmails.length} Job(s) with Verified Recruiter Emails!</span>
              <p className="text-[11px] text-slate-400">Dispatch tailored applications and customized resumes to all recruiters in 1 click.</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setBatchApplyOpen(true)}
            className="shimmer-btn px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-extrabold text-xs shadow-lg shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer shrink-0"
          >
            <Send size={13} />
            <span>Auto-Apply to All with Emails ({jobsWithEmails.length})</span>
          </button>
        </motion.div>
      )}

      {/* Bulk Action Banner when jobs have Candidature Simplifiée without emails */}
      {isAuth && easyApplyJobsWithoutEmail.length > 0 && !loading && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 rounded-2xl glass-panel border border-blue-500/30 flex items-center justify-between gap-3 shadow-sm flex-wrap"
        >
          <div className="flex items-center gap-3 text-xs">
            <div className="w-9 h-9 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center justify-center shrink-0">
              <Zap size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-white">Discovered {easyApplyJobsWithoutEmail.length} Job(s) with Candidature Simplifiée!</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/15 text-blue-300 border border-blue-500/30">
                  Easy Apply
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Auto-apply to all simplified listings in 1 click with AI-tailored resumes and instant Tracker sync.</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setBatchEasyApplyOpen(true)}
            className="shimmer-btn px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-extrabold text-xs shadow-lg shadow-blue-500/25 transition flex items-center gap-1.5 cursor-pointer shrink-0"
          >
            <Zap size={13} />
            <span>Auto-Apply to All Candidatures Simplifiées ({easyApplyJobsWithoutEmail.length})</span>
          </button>
        </motion.div>
      )}

      {/* Results List */}
      {loading ? (
        <div className="p-14 text-center text-slate-400 space-y-4 glass-panel rounded-3xl relative overflow-hidden">
          <div className="glow-line-top" />
          <div className="relative w-14 h-14 mx-auto">
            <div className="absolute inset-0 rounded-full border-2 border-blue-500/25 animate-ping" />
            <div className="w-14 h-14 rounded-full border-2 border-t-blue-500 border-r-purple-400 border-b-transparent border-l-transparent animate-spin flex items-center justify-center">
              <Search size={20} className="text-blue-400" />
            </div>
          </div>
          <div className="space-y-1.5">
            <p className="text-base font-extrabold text-white">
              Scraping Live Job Boards for <span className="text-gradient-blue">"{title || 'Jobs'}"</span>
            </p>
            <p className="text-xs text-slate-400">
              Searching all sources automatically: <span className="text-purple-300 font-bold">{selectedSites.map(siteLabel).join(', ')}</span> across <span className="text-emerald-300 font-bold">{selectedCountries.join(', ')}</span>...
            </p>
            <p className="text-[11px] text-slate-500 italic">
              Automating recruiter email extraction &amp; resume ATS alignment
            </p>
          </div>
        </div>
      ) : filteredJobs.length > 0 ? (
        <GuestBlurGate count={filteredJobs.length} itemLabel="Matching Jobs & Recruiter Emails">
        {viewMode === 'split' ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Left Master Feed (5 cols) */}
            <div className="lg:col-span-5 space-y-2.5 max-h-[calc(100vh-140px)] overflow-y-auto pr-1 select-none">
              <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400 px-1 pb-1 flex items-center justify-between">
                <span>Job Postings ({filteredJobs.length})</span>
                <span className="text-slate-500 font-normal">Ranked by fit &amp; quality</span>
              </div>

              {streaming && (
                <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center gap-2 text-[11px] font-bold text-blue-300">
                  <Loader2 size={13} className="animate-spin text-blue-400 shrink-0" />
                  <span>Streaming more jobs from LinkedIn, Indeed &amp; Google...</span>
                </div>
              )}

              {searchMeta?.stats && (
                <div className="p-3 rounded-2xl glass-card space-y-1.5 text-[10px]">
                  {searchMeta.stats.sites_searched?.length > 0 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      <span className="text-slate-500 font-bold mr-0.5">Searched in:</span>
                      {searchMeta.stats.sites_searched.map(id => {
                        const n = searchMeta.stats.per_site?.[id] || 0
                        return (
                          <span key={id} className={`px-1.5 py-0.5 rounded-md border font-semibold ${n > 0 ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300' : 'bg-white/[0.03] border-white/[0.06] text-slate-500'}`}>
                            {siteLabel(id)} · {n}
                          </span>
                        )
                      })}
                    </div>
                  )}
                  {searchMeta.queries?.length > 1 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      <span className="text-slate-500 font-bold mr-0.5">Searched as:</span>
                      {searchMeta.queries.map(q => (
                        <span key={q} className="px-1.5 py-0.5 rounded-md bg-blue-500/15 border border-blue-500/30 text-blue-300 font-semibold">{q}</span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center gap-2 flex-wrap text-slate-400">
                    <span>{searchMeta.stats.raw} scraped</span>
                    <span className="text-slate-600">→</span>
                    <span>{searchMeta.stats.after_dedup} unique</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-emerald-400 font-bold">{searchMeta.stats.after_relevance} relevant</span>
                    {searchMeta.stats.spam_removed > 0 && (
                      <span className="text-rose-400">· {searchMeta.stats.spam_removed} spam removed</span>
                    )}
                    {searchMeta.stats.timings?.total_s && (
                      <span className="text-slate-500">· {searchMeta.stats.timings.total_s}s</span>
                    )}
                  </div>
                </div>
              )}

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
                  <motion.div
                    key={jobId}
                    whileHover={{ y: -2 }}
                    onClick={() => setSelectedJobId(job.id || job.url)}
                    className={`p-4 rounded-2xl border transition-all cursor-pointer space-y-2 relative overflow-hidden ${
                      isSelected
                        ? 'bg-gradient-to-br from-blue-950/60 via-slate-900/95 to-indigo-950/50 border-blue-500/70 shadow-lg shadow-blue-500/15 ring-1 ring-blue-500/40'
                        : 'glass-card hover:border-slate-600/80'
                    } ${applied ? 'border-l-4 border-l-emerald-500' : ''}`}
                  >
                    {isSelected && (
                      <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-blue-400 to-purple-500" />
                    )}

                    {/* Role Title & Match Fit */}
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="font-extrabold text-sm text-white leading-snug line-clamp-2">
                        {job.title}
                      </h4>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-lg border bg-blue-500/15 border-blue-500/35 text-blue-300">
                          {score}% CV
                        </span>
                      </div>
                    </div>

                    {/* Company, Location, Site */}
                    <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
                      <span className="font-bold text-blue-300 flex items-center gap-1 truncate max-w-[130px]">
                        <Building2 size={11} className="text-blue-400 shrink-0" />
                        {job.company}
                      </span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-400 flex items-center gap-1 truncate max-w-[120px]">
                        <MapPin size={10} className="shrink-0" />
                        {job.location || 'Remote'}
                      </span>
                      <span className="text-slate-600">·</span>
                      <span className="px-1.5 py-0.2 rounded-md text-[10px] uppercase font-bold border bg-blue-500/10 text-blue-300 border-blue-500/25">
                        {(job.site || '').toLowerCase().includes('job_bank') || (job.site || '').toLowerCase().includes('jobbank') ? '🇨🇦 Job Bank' : job.site}
                      </span>
                      {job.is_international_eligible && (
                        <span className="px-1.5 py-0.2 rounded-md text-[10px] font-semibold border bg-white/[0.04] text-slate-300 border-white/[0.08] flex items-center gap-0.5">
                          <span>🌐</span> LMIA / Global
                        </span>
                      )}
                      {(job.also_on?.length || 0) > 1 && (
                        <span
                          className="px-1.5 py-0.2 rounded-md text-[10px] font-semibold border bg-white/[0.04] text-slate-300 border-white/[0.08]"
                          title={`Also listed on: ${job.also_on.join(', ')}`}
                        >
                          ✓ {job.also_on.length} boards
                        </span>
                      )}
                      <JobSignalBadges job={job} />
                      {job.age_str && (
                        <>
                          <span className="text-slate-600">·</span>
                          <span className="px-1.5 py-0.2 rounded-md text-[10px] font-semibold border bg-white/[0.04] text-slate-400 border-white/[0.08]">
                            {job.age_str}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Recruiter Email Badge with 1-Click Action */}
                    {primaryEmail && (
                      <div className="flex items-center justify-between gap-1.5 pt-0.5">
                        <div className="flex items-center gap-1 text-[10px] text-blue-300 bg-blue-500/10 border border-blue-500/25 px-2 py-0.5 rounded-lg w-fit">
                          <ShieldCheck size={11} className="text-blue-400 shrink-0" />
                          <span className="font-mono truncate max-w-[190px]">{primaryEmail}</span>
                        </div>
                        {!applied && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setAutoApplyJob({
                                ...job,
                                author_name: 'Hiring Team',
                                role_title: job.title,
                                recruiter_emails: [{ email: primaryEmail, name: 'Hiring Team' }]
                              })
                            }}
                            className="px-2.5 py-0.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold flex items-center gap-1 transition cursor-pointer shadow-xs shrink-0"
                            title="1-Click Auto Apply directly to recruiter"
                          >
                            <Send size={10} />
                            <span>Auto-Apply</span>
                          </button>
                        )}
                      </div>
                    )}

                    {/* Candidature Simplifiée Badge for jobs without email */}
                    {!primaryEmail && checkIsEasyApply(job) && (
                      <div className="flex items-center justify-between pt-0.5">
                        <div className="flex items-center gap-1 text-[10px] font-bold text-blue-300 bg-blue-500/10 border border-blue-500/25 px-2 py-0.5 rounded-lg w-fit">
                          <Zap size={10} className="text-blue-400 shrink-0" />
                          <span>Candidature Simplifiée</span>
                        </div>
                        {!applied && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setEasyApplyJob(job)
                            }}
                            className="px-2.5 py-0.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold flex items-center gap-1 transition cursor-pointer"
                            title="1-click Auto Apply via Candidature Simplifiée"
                          >
                            <Zap size={10} />
                            <span>Auto-Apply</span>
                          </button>
                        )}
                      </div>
                    )}

                    {/* Matched skills pill preview */}
                    {matchedSkills.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap text-[10px]">
                        {matchedSkills.slice(0, 3).map((s, sIdx) => (
                          <span key={sIdx} className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/25 px-1.5 py-0.2 rounded-md text-[10px] font-medium">
                            ✓ {s}
                          </span>
                        ))}
                        {matchedSkills.length > 3 && (
                          <span className="text-slate-500 text-[10px]">+{matchedSkills.length - 3}</span>
                        )}
                      </div>
                    )}
                  </motion.div>
                )
              })}
            </div>

            {/* Right Active Detail Workbench (7 cols) */}
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
            <div className="text-xs font-extrabold uppercase tracking-wider text-slate-400 px-1 flex items-center justify-between">
              <span>Formal Job Postings ({filteredJobs.length}{activeFiltersCount > 0 ? ` filtrés sur ${unappliedJobs.length}` : ''})</span>
              {jobsWithEmails.length > 0 && (
                <span className="text-emerald-400 font-semibold">
                  {jobsWithEmails.length} with direct recruiter email
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                    className="p-5 rounded-2xl glass-card card-hover flex flex-col justify-between space-y-3 relative"
                  >
                    <div className="space-y-2.5">
                      {/* Header: Title & ATS Score */}
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="font-extrabold text-sm text-white line-clamp-1">{job.title}</h4>
                        {job.score != null ? (
                          <ScoreBadge score={job.score} />
                        ) : null}
                      </div>

                      {/* Company, Location, Board */}
                      <div className="flex items-center gap-2 text-xs text-slate-300 flex-wrap">
                        <span className="font-bold text-blue-300 flex items-center gap-1">
                          <Building2 size={11} className="text-blue-400" />
                          {job.company}
                        </span>
                        <span className="text-slate-600">·</span>
                        <span className="text-slate-400 flex items-center gap-1">
                          <MapPin size={11} />
                          {job.location || 'Remote'}
                        </span>
                        <span className="text-slate-600">·</span>
                        <span className={`capitalize px-1.5 py-0.5 rounded-md text-[10px] font-bold border ${
                          (job.site || '').toLowerCase().includes('job_bank') || (job.site || '').toLowerCase().includes('jobbank')
                            ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                            : 'bg-white/[0.04] text-slate-300 border-white/[0.08]'
                        }`}>
                          {(job.site || '').toLowerCase().includes('job_bank') || (job.site || '').toLowerCase().includes('jobbank') ? '🇨🇦 Job Bank' : job.site}
                        </span>
                        {job.is_international_eligible && (
                          <span className="px-1.5 py-0.5 rounded-md text-[10px] font-bold border bg-amber-500/15 text-amber-300 border-amber-500/30 flex items-center gap-0.5">
                            <span>🌐</span> LMIA / Global
                          </span>
                        )}
                        <JobSignalBadges job={job} />
                        {job.age_str && (
                          <>
                            <span className="text-slate-600">·</span>
                            <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold border ${
                              job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)
                                ? 'bg-amber-500/15 text-amber-300 border-amber-500/30 flex items-center gap-0.5'
                                : 'bg-white/[0.04] text-slate-400 border-white/[0.08]'
                            }`}>
                              {(job.is_under_24h || (job.age_hours != null && job.age_hours <= 24)) && <span>⚡</span>}
                              {job.age_str}
                            </span>
                          </>
                        )}
                      </div>

                      {/* Recruiter Email Badge if discovered */}
                      {primaryEmail && (
                        <div className="flex items-center gap-1.5 text-[11px] text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-1 rounded-xl w-fit">
                          <ShieldCheck size={12} className="text-emerald-400 shrink-0" />
                          <span className="font-mono font-bold">{primaryEmail}</span>
                        </div>
                      )}

                      {/* Candidature Simplifiée Badge if discovered and no email */}
                      {!primaryEmail && checkIsEasyApply(job) && (
                        <div className="flex items-center gap-1.5 text-[11px] text-amber-300 bg-amber-500/15 border border-amber-500/30 px-2.5 py-1 rounded-xl w-fit font-semibold">
                          <Zap size={12} className="fill-amber-400 text-amber-400 shrink-0" />
                          <span>Candidature Simplifiée (Easy Apply)</span>
                        </div>
                      )}

                      {/* Matched & Missing Skills Pills */}
                      {(matchedSkills.length > 0 || missingSkills.length > 0) && (
                        <div className="space-y-1.5 pt-1">
                          {matchedSkills.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap text-[10px]">
                              <span className="text-slate-500 font-bold mr-0.5">Matched:</span>
                              {matchedSkills.slice(0, 4).map((s, sIdx) => (
                                <span key={sIdx} className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-1.5 py-0.5 rounded-md font-semibold">
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
                              <span className="text-amber-500/90 font-bold mr-0.5">Missing:</span>
                              {missingSkills.slice(0, 3).map((s, sIdx) => (
                                <span key={sIdx} className="bg-amber-500/15 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 rounded-md font-semibold flex items-center gap-0.5">
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
                            className="text-[11px] text-blue-400 hover:text-blue-300 flex items-center gap-1 font-bold transition cursor-pointer"
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
                                className="mt-1.5 p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/25 space-y-1 text-[11px] text-slate-300"
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
                    <div className="flex items-center justify-between pt-3 border-t border-white/[0.06] text-xs gap-2">
                      <a
                        href={job.url || job.job_url_direct}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 flex items-center gap-1 font-bold"
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
                            className="px-2.5 py-1 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-xs font-bold flex items-center gap-1 cursor-pointer transition shadow-xs"
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
                            className="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-xs font-bold flex items-center gap-1 cursor-pointer transition shadow-xs"
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
                            className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-bold flex items-center gap-1 cursor-pointer transition"
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
                          className="px-2.5 py-1 rounded-lg bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/35 text-purple-300 text-xs font-bold flex items-center gap-1 cursor-pointer transition"
                        >
                          <Sparkles size={11} />
                          <span>Tailor CV</span>
                        </button>

                        {/* Bookmark */}
                        <button
                          type="button"
                          onClick={() => onSaveJob(job)}
                          disabled={saved || applied}
                          className="p-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.08] text-slate-400 hover:text-white transition disabled:opacity-40 cursor-pointer"
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
        )}
        </GuestBlurGate>
      ) : unappliedJobs.length > 0 ? (
        <div className="p-10 text-center text-slate-400 space-y-2.5 glass-panel rounded-3xl relative overflow-hidden">
          <div className="glow-line-top" />
          <p className="text-sm font-extrabold text-white">No jobs match your selected filters</p>
          <p className="text-xs text-slate-400">Try broadening your date, experience, or industry filters.</p>
          <button
            type="button"
            onClick={() => {
              setFilters(DEFAULT_FILTERS)
              handleTriggerSearchWithFilters(DEFAULT_FILTERS)
            }}
            className="px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.1] text-white text-xs font-bold mt-2 cursor-pointer transition"
          >
            Reset filters
          </button>
        </div>
      ) : hasSearched ? (
        <div className="p-10 text-center space-y-5 glass-panel rounded-3xl relative overflow-hidden">
          <div className="glow-line-top" />
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center mx-auto shadow-inner">
            <AlertCircle size={26} />
          </div>
          <div className="max-w-md mx-auto space-y-1.5">
            <h3 className="text-base font-extrabold text-white">
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
              className="shimmer-btn px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-2 transition cursor-pointer shadow-lg shadow-blue-600/25"
            >
              <Globe size={14} />
              <span>Expand to Worldwide (Global)</span>
            </button>

            {onSwitchToPosts && (
              <button
                type="button"
                onClick={() => onSwitchToPosts(title)}
                className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-2 transition cursor-pointer shadow-lg shadow-purple-600/25"
              >
                <Sparkles size={14} className="text-amber-300" />
                <span>Search LinkedIn Recruiter Posts</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleSubmit}
              className="px-4 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-white border border-white/[0.08] text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
            >
              <RotateCcw size={13} />
              <span>Retry Search</span>
            </button>
          </div>

          {/* Broader Keyword Suggestions */}
          <div className="pt-4 border-t border-white/[0.06] max-w-lg mx-auto">
            <p className="text-[11px] font-extrabold text-slate-400 uppercase tracking-wider mb-2.5">
              Suggested Broader Search Terms:
            </p>
            <div className="flex items-center justify-center gap-2 flex-wrap">
              {['Mobile Developer', 'Software Engineer', 'Full Stack Developer', 'Frontend Developer'].map(alt => (
                <button
                  key={alt}
                  type="button"
                  onClick={() => handleQuickRoleSearch(alt)}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] hover:border-blue-500/40 text-slate-300 hover:text-white text-xs font-semibold transition cursor-pointer flex items-center gap-1"
                >
                  <Search size={11} className="text-blue-400" />
                  <span>{alt}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Initial Ready-to-Search Explorer Card */
        <div className="p-8 sm:p-10 rounded-3xl glass-panel relative overflow-hidden space-y-6">
          <div className="glow-line-top" />
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/25 text-blue-400 text-xs font-bold mb-2">
                <Briefcase size={12} />
                <span>Multi-Board AI Aggregator</span>
              </div>
              <h3 className="text-xl md:text-2xl font-black text-white tracking-tight">
                Search Formal Job Boards with <span className="text-gradient-blue">Recruiter Intelligence</span>
              </h3>
              <p className="text-xs text-slate-400 mt-1 max-w-xl leading-relaxed">
                Scrapes active postings directly from LinkedIn Jobs, Indeed, Job Bank Canada &amp; global remote boards. Automatically mines direct recruiter emails and calculates ATS CV alignment scores.
              </p>
            </div>
          </div>

          {/* Quick Start Presets */}
          <div className="p-4 rounded-2xl bg-[#050811]/70 border border-white/[0.07] space-y-2.5">
            <p className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <Sparkles size={13} className="text-amber-400" />
              <span>Quick Role Presets (Click to Search Instantly):</span>
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              {QUICK_ROLES.map(roleName => (
                <button
                  key={roleName}
                  type="button"
                  onClick={() => handleQuickRoleSearch(roleName)}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] hover:border-blue-500/50 hover:bg-blue-500/10 text-slate-300 hover:text-white text-xs font-semibold transition cursor-pointer flex items-center gap-1.5 group"
                >
                  <Search size={11} className="text-slate-500 group-hover:text-blue-400 transition" />
                  <span>{roleName}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 3 Pillars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
            <div className="p-4 rounded-2xl glass-card space-y-1.5">
              <div className="w-8 h-8 rounded-xl bg-blue-500/15 border border-blue-500/30 text-blue-400 flex items-center justify-center font-extrabold text-xs">
                01
              </div>
              <h4 className="text-xs font-extrabold text-white">Live Multi-Country Scraping</h4>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Queries Indeed, LinkedIn Jobs &amp; open APIs simultaneously across 9+ countries without outdated caches.
              </p>
            </div>

            <div className="p-4 rounded-2xl glass-card space-y-1.5">
              <div className="w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center font-extrabold text-xs">
                02
              </div>
              <h4 className="text-xs font-extrabold text-white">Direct Recruiter Email Mining</h4>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Extracts contact emails from job descriptions and company domains for direct email outreach.
              </p>
            </div>

            <div className="p-4 rounded-2xl glass-card space-y-1.5">
              <div className="w-8 h-8 rounded-xl bg-purple-500/15 border border-purple-500/30 text-purple-400 flex items-center justify-center font-extrabold text-xs">
                03
              </div>
              <h4 className="text-xs font-extrabold text-white">ATS CV Scoring &amp; 1-Click Apply</h4>
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

      {/* Aggregate Skill-Gap Heatmap & Learning Plan Modal */}
      <UpskillModal
        isOpen={upskillOpen}
        onClose={() => setUpskillOpen(false)}
        jobs={filteredJobs}
      />
    </div>
  )
}
