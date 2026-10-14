import { useState, useMemo, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { RotateCcw, Search, Sparkles, Link2, Radar, ShieldCheck, Globe, Cpu } from 'lucide-react'
import client from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { DEFAULT_POST_FILTERS } from '../constants/searchConstants.js'
import {
  parseApiError,
  buildTrackerLookupSets,
  matchesTrackerSet
} from '../utils/jobUtils.js'

// Subcomponents
import PostSearchHeader from './hunter/PostSearchHeader.jsx'
import PostFilterBar from './hunter/PostFilterBar.jsx'
import PostSplitFeed from './hunter/PostSplitFeed.jsx'
import PostDetailWorkbench from './hunter/PostDetailWorkbench.jsx'
import PostCardGrid from './hunter/PostCardGrid.jsx'
import LocationPickerModal from './hunter/LocationPickerModal.jsx'

// Modals
import AutoApplyModal from './modals/AutoApplyModal.jsx'
import InMailPitchModal from './modals/InMailPitchModal.jsx'
import PostReaderModal from './modals/PostReaderModal.jsx'
import TailorCvModal from './modals/TailorCvModal.jsx'
import SmtpPromptModal from './modals/SmtpPromptModal.jsx'
import BatchApplyModal from './modals/BatchApplyModal.jsx'
import LinkedInConnectModal from './modals/LinkedInConnectModal.jsx'

export default function LinkedInPostHunter({
  initialRole = 'Flutter Developer',
  cvUploaded = false,
  onOpenEmailModal,
  onTailor
}) {
  const toast = useToast()

  // Search Query State
  const [role, setRole] = useState(initialRole || '')
  const [selectedLocations, setSelectedLocations] = useState(['Worldwide'])
  const [showLocationPicker, setShowLocationPicker] = useState(false)

  // Layout & Filter State
  const [viewMode, setViewMode] = useState('split') // 'split' | 'cards'
  const [postFilters, setPostFilters] = useState(DEFAULT_POST_FILTERS)
  const [selectedPostId, setSelectedPostId] = useState(null)

  // Search Lifecycle & Pagination
  const [loading, setLoading] = useState(false)
  const [cvAnalyzing, setCvAnalyzing] = useState(false)
  const [posts, setPosts] = useState([])
  const [searched, setSearched] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)

  // Tracker & Action Sync State
  const [appliedPostIds, setAppliedPostIds] = useState(new Set())
  const [savedPostIds, setSavedPostIds] = useState(new Set())
  const [trackerAppliedKeys, setTrackerAppliedKeys] = useState(new Set())
  const [trackerSavedKeys, setTrackerSavedKeys] = useState(new Set())
  const [applyingPostId, setApplyingPostId] = useState(null)

  // Active Modals
  const [autoApplyTarget, setAutoApplyTarget] = useState(null)
  const [inmailTarget, setInmailTarget] = useState(null)
  const [readerTarget, setReaderTarget] = useState(null)
  const [tailorTarget, setTailorTarget] = useState(null)
  const [showSmtpPrompt, setShowSmtpPrompt] = useState(false)
  const [batchApplyOpen, setBatchApplyOpen] = useState(false)
  const [showLinkedInConnect, setShowLinkedInConnect] = useState(false)
  const [isLinkedInConnected, setIsLinkedInConnected] = useState(false)

  // Infinite Scroll Refs
  const observerTargetRef = useRef(null)
  const cardsObserverTargetRef = useRef(null)

  // Sync LinkedIn Session Status
  useEffect(() => {
    const localCookie = (localStorage.getItem('linkedin_li_at') || '').trim()
    if (localCookie) {
      setIsLinkedInConnected(true)
    }
    client.get('/linkedin-posts/account-status').then(r => {
      if (r.data?.connected) {
        setIsLinkedInConnected(true)
      }
    }).catch(() => {})
  }, [])

  // Load Tracker Applications to match applied/saved status
  useEffect(() => {
    client.get('/tracker').then(r => {
      const { applied, saved } = buildTrackerLookupSets(r.data || [])
      setTrackerAppliedKeys(applied)
      setTrackerSavedKeys(saved)
    }).catch(() => {})
  }, [])

  // Listen for CommandPalette / Watchlist quick-hunt events
  useEffect(() => {
    const onQuickHunt = (ev) => {
      const detail = ev.detail
      const nextRole = typeof detail === 'string' ? detail : detail?.role
      const nextLocs = Array.isArray(detail?.locations) && detail.locations.length ? detail.locations : selectedLocations
      if (nextRole) {
        setRole(nextRole)
        if (Array.isArray(detail?.locations) && detail.locations.length) {
          setSelectedLocations(detail.locations)
        }
        handleSearch(null, false, postFilters, nextRole, nextLocs)
      }
    }
    window.addEventListener('quick-hunt-role', onQuickHunt)
    return () => window.removeEventListener('quick-hunt-role', onQuickHunt)
  }, [selectedLocations, postFilters])

  // Check if post is applied or saved
  const isPostApplied = (p) => {
    if (!p) return false
    if (appliedPostIds.has(p.id) || p.is_applied) return true
    return matchesTrackerSet(p, trackerAppliedKeys)
  }

  const isPostSaved = (p) => {
    if (!p) return false
    if (isPostApplied(p)) return false
    if (savedPostIds.has(p.id) || p.is_saved) return true
    return matchesTrackerSet(p, trackerSavedKeys)
  }

  // Primary Search
  const handleSearch = async (e, forceRefresh = false, activeFilters = postFilters, overrideRole = null, overrideLocations = null) => {
    if (e && e.preventDefault) e.preventDefault()
    const targetRole = (overrideRole !== null ? overrideRole : role).trim()
    const targetLocs = overrideLocations || selectedLocations
    if (!targetRole) {
      toast('Please enter a role or skill to search', 'error')
      return
    }

    setLoading(true)
    setPage(1)
    setHasMore(true)
    try {
      const activeLocs = targetLocs.filter(l => l && l.toLowerCase() !== 'worldwide')
      const eff = activeFilters || postFilters
      const liAt = (localStorage.getItem('linkedin_li_at') || '').trim()
      const { data } = await client.post('/linkedin-posts/search', {
        role: targetRole,
        location: activeLocs.join(', '),
        locations: activeLocs,
        limit: 40,
        page: 1,
        force_refresh: forceRefresh,
        sort_by: eff.sortBy === 'recent' ? 'newest' : 'score',
        email_only: Boolean(eff.emailOnly),
        time_range: eff.datePosted || 'all',
        li_at: liAt
      })

      const foundPosts = data.posts || []
      setPosts(foundPosts)
      setSearched(true)
      setPage(1)
      setHasMore(data.has_more ?? (foundPosts.length >= 10))
      if (foundPosts.length > 0) {
        setSelectedPostId(foundPosts[0].id)
      }

      // Sync applied/saved tags
      const newApplied = new Set()
      const newSaved = new Set()
      foundPosts.forEach(p => {
        if (p.is_applied) newApplied.add(p.id)
        if (p.is_saved) newSaved.add(p.id)
      })
      if (newApplied.size > 0) setAppliedPostIds(prev => new Set([...prev, ...newApplied]))
      if (newSaved.size > 0) setSavedPostIds(prev => new Set([...prev, ...newSaved]))

      const locSummary = activeLocs.length > 0 ? ` in ${activeLocs.join(', ')}` : ' globally'
      toast(`⚡ Discovered ${foundPosts.length} LinkedIn recruiter publications${locSummary}!`, 'success')
    } catch (err) {
      toast(parseApiError(err, 'Failed to hunt LinkedIn posts'), 'error')
    } finally {
      setLoading(false)
    }
  }

  // Pagination / Load More (Scroll Down to Load Next Page)
  const handleLoadMore = async () => {
    if (loading || loadingMore || loadingMoreRef.current || !hasMore || !role.trim()) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    const nextPage = page + 1
    try {
      const activeLocs = selectedLocations.filter(l => l && l.toLowerCase() !== 'worldwide')
      const liAt = (localStorage.getItem('linkedin_li_at') || '').trim()
      const { data } = await client.post('/linkedin-posts/search', {
        role: role.trim(),
        location: activeLocs.join(', '),
        locations: activeLocs,
        limit: 40,
        page: nextPage,
        force_refresh: false,
        sort_by: postFilters.sortBy === 'recent' ? 'newest' : 'score',
        email_only: Boolean(postFilters.emailOnly),
        time_range: postFilters.datePosted || 'all',
        li_at: liAt
      })

      const newPosts = data.posts || []
      if (newPosts.length === 0) {
        setHasMore(false)
      } else {
        setPosts(prev => {
          const existingKeys = new Set(prev.map(p => (p.post_url || p.id || '').toLowerCase()))
          const fresh = newPosts.filter(p => !existingKeys.has((p.post_url || p.id || '').toLowerCase()))
          if (fresh.length === 0) {
            setHasMore(false)
            return prev
          }
          return [...prev, ...fresh]
        })
        setPage(nextPage)
        setHasMore(data.has_more ?? (newPosts.length >= 5))
        toast(`⚡ Loaded ${newPosts.length} more posts (Page ${nextPage})`, 'success')

        // Sync applied / saved tags
        const newApplied = new Set()
        const newSaved = new Set()
        newPosts.forEach(p => {
          if (p.is_applied) newApplied.add(p.id)
          if (p.is_saved) newSaved.add(p.id)
        })
        if (newApplied.size > 0) setAppliedPostIds(prev => new Set([...prev, ...newApplied]))
        if (newSaved.size > 0) setSavedPostIds(prev => new Set([...prev, ...newSaved]))
      }
    } catch (err) {
      toast(parseApiError(err, 'Failed to load more posts'), 'error')
    } finally {
      setLoadingMore(false)
      loadingMoreRef.current = false
    }
  }

  // Infinite Scroll Trigger for Cards View
  useEffect(() => {
    if (!hasMore || loading || loadingMore || posts.length === 0 || viewMode !== 'cards') return

    const observer = new IntersectionObserver(
      entries => {
        if (entries[0]?.isIntersecting && !loadingMoreRef.current) {
          handleLoadMore()
        }
      },
      { root: null, rootMargin: '300px', threshold: 0.05 }
    )

    const target = cardsObserverTargetRef.current
    if (target) observer.observe(target)

    return () => {
      if (target) observer.unobserve(target)
    }
  }, [hasMore, loading, loadingMore, posts.length, page, role, selectedLocations, postFilters.sortBy, viewMode])

  // Save Post to Pipeline Tracker
  const handleSave = async (post) => {
    try {
      const emailList = (post.recruiter_emails || []).map(e => e.email)
      await client.post('/linkedin-posts/save', {
        post_url: post.post_url,
        role_title: post.role_title,
        company: post.company,
        author_name: post.author_name,
        recruiter_emails: emailList,
        snippet: post.full_text || post.post_snippet
      })
      setSavedPostIds(prev => new Set([...prev, post.id]))
      setTrackerSavedKeys(prev => {
        const next = new Set(prev)
        if (post.post_url) next.add(post.post_url.trim().toLowerCase())
        next.add(`${(post.role_title || '').trim().toLowerCase()}|${(post.company || '').trim().toLowerCase()}`)
        return next
      })
      toast(`Saved ${post.role_title} at ${post.company} to Pipeline!`, 'success')
    } catch (err) {
      toast(parseApiError(err, 'Failed to save post'), 'error')
    }
  }

  // Location Toggling
  const handleToggleLocation = (loc) => {
    if (!loc || loc.toLowerCase() === 'worldwide') {
      setSelectedLocations(['Worldwide'])
      return
    }
    setSelectedLocations(prev => {
      const withoutWw = prev.filter(l => l.toLowerCase() !== 'worldwide')
      if (withoutWw.some(l => l.toLowerCase() === loc.toLowerCase())) {
        const rem = withoutWw.filter(l => l.toLowerCase() !== loc.toLowerCase())
        return rem.length > 0 ? rem : ['Worldwide']
      }
      return [...withoutWw, loc]
    })
  }

  // Filtered Posts - Exclude already applied posts and apply active filters
  const filteredPosts = useMemo(() => {
    let result = posts.filter(p => {
      if (isPostApplied(p)) return false

      if (postFilters.emailOnly) {
        if (!p.has_email || !p.recruiter_emails || p.recruiter_emails.length === 0) {
          return false
        }
      }

      if (postFilters.datePosted === '24h') {
        const is24h = p.is_under_24h || (p.age_hours != null && p.age_hours <= 24)
        if (!is24h) return false
      } else if (postFilters.datePosted === 'week') {
        const isWeek = p.age_hours != null ? p.age_hours <= 168 : true
        if (!isWeek) return false
      } else if (postFilters.datePosted === 'month') {
        const isMonth = p.age_hours != null ? p.age_hours <= 720 : true
        if (!isMonth) return false
      }

      return true
    })

    if (postFilters.sortBy === 'recent') {
      result = [...result].sort((a, b) => {
        const aAge = a.age_hours != null ? a.age_hours : 9999
        const bAge = b.age_hours != null ? b.age_hours : 9999
        return aAge - bAge
      })
    } else {
      result = [...result].sort((a, b) => {
        const aScore = a.score || a.role_fit_score || 0
        const bScore = b.score || b.role_fit_score || 0
        if (bScore !== aScore) return bScore - aScore
        const aEmail = a.has_email && a.recruiter_emails?.length ? 1 : 0
        const bEmail = b.has_email && b.recruiter_emails?.length ? 1 : 0
        return bEmail - aEmail
      })
    }

    return result
  }, [posts, postFilters, appliedPostIds, trackerAppliedKeys])

  // Active Post for Split View
  const activePost = useMemo(() => {
    if (!filteredPosts.length) return null
    return filteredPosts.find(p => p.id === selectedPostId) || filteredPosts[0]
  }, [filteredPosts, selectedPostId])

  return (
    <div className="space-y-6">
      {/* 1. Sleek Command Search Header */}
      <PostSearchHeader
        role={role}
        setRole={setRole}
        selectedLocations={selectedLocations}
        onOpenLocationPicker={() => setShowLocationPicker(true)}
        onSearch={handleSearch}
        loading={loading}
        isLinkedInConnected={isLinkedInConnected}
        onOpenLinkedInConnect={() => setShowLinkedInConnect(true)}
      />

      {/* 2. Filter & View Controls */}
      <PostFilterBar
        postFilters={postFilters}
        setPostFilters={setPostFilters}
        viewMode={viewMode}
        setViewMode={setViewMode}
        posts={posts}
        onBatchApply={() => setBatchApplyOpen(true)}
        onApplyAndSearch={(newFilters) => {
          if (searched && role.trim()) {
            handleSearch(null, false, newFilters)
          }
        }}
      />

      {/* 2.5 Initial Ready-to-Hunt Launchpad (Before First Search) */}
      {!loading && !searched && posts.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel rounded-3xl p-8 sm:p-10 md:p-12 text-center relative overflow-hidden space-y-7"
        >
          <div className="glow-line-top" />

          <div className="relative w-20 h-20 mx-auto flex items-center justify-center">
            <div className="absolute inset-0 rounded-3xl bg-blue-500/15 blur-xl animate-pulse" />
            <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600/30 via-indigo-600/30 to-purple-600/30 border border-blue-400/30 flex items-center justify-center text-blue-400 shadow-lg shadow-blue-600/20">
              <Radar size={30} />
            </div>
          </div>

          <div className="space-y-2 max-w-xl mx-auto">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300 text-[11px] font-bold">
              <Sparkles size={11} className="text-amber-400" />
              <span>Ready to Harvest Live Hiring Publications</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
              Discover Direct Recruiter Posts with <span className="text-gradient-blue">Verified Emails</span>
            </h2>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Click <span className="text-white font-bold">Hunt Posts</span> above or launch directly below to scan live LinkedIn publications, decode exact Snowflake URN timestamps, and verify corporate MX records.
            </p>
          </div>

          {/* 3 Feature Pillars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl mx-auto text-left">
            {[
              {
                icon: Globe,
                title: 'Multilingual Dork Matrix',
                desc: 'Simultaneously queries English & French hiring phrases across your selected regions.'
              },
              {
                icon: Cpu,
                title: 'Snowflake URN Age Gate',
                desc: 'Extracts exact post creation timestamps directly from LinkedIn 64-bit activity IDs.'
              },
              {
                icon: ShieldCheck,
                title: 'DNS MX Email Verification',
                desc: 'Extracts HR & recruiter emails and validates live mail exchange servers automatically.'
              }
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="glass-card rounded-2xl p-4 border border-white/[0.06] space-y-1.5">
                <div className="flex items-center gap-2 text-blue-400 font-bold text-xs">
                  <div className="w-7 h-7 rounded-lg bg-blue-500/15 border border-blue-500/25 flex items-center justify-center shrink-0">
                    <Icon size={14} />
                  </div>
                  <span className="text-white">{title}</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed pl-0.5">{desc}</p>
              </div>
            ))}
          </div>

          <div className="pt-1 flex items-center justify-center gap-3 flex-wrap">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              type="button"
              onClick={e => handleSearch(e, false)}
              className="shimmer-btn px-7 py-3 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white text-xs sm:text-sm font-extrabold shadow-xl shadow-blue-600/25 flex items-center gap-2.5 cursor-pointer"
            >
              <Radar size={16} />
              <span>Hunt &ldquo;{role || 'Flutter Developer'}&rdquo; Posts Now</span>
            </motion.button>
          </div>
        </motion.div>
      )}

      {/* 3. Animated Live AI Harvesting Radar (Loading State) */}
      {loading && posts.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-3xl p-10 text-center relative overflow-hidden space-y-6"
        >
          <div className="glow-line-top" />

          {/* Concentric Sonar Radar Animation */}
          <div className="relative w-24 h-24 mx-auto flex items-center justify-center">
            <span className="absolute inset-0 rounded-full border border-blue-500/30 animate-ping" style={{ animationDuration: '2.4s' }} />
            <span className="absolute inset-3 rounded-full border border-indigo-500/40 animate-ping" style={{ animationDuration: '1.8s' }} />
            <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 flex items-center justify-center shadow-xl shadow-blue-600/30 border border-white/20">
              <Radar size={28} className="text-white animate-spin" style={{ animationDuration: '3s' }} />
            </div>
          </div>

          <div className="space-y-1.5 max-w-lg mx-auto">
            <h3 className="text-base font-extrabold text-white tracking-tight">
              AI Recruiter Radar Harvesting Live Publications...
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Executing multilingual dorks, decoding LinkedIn Snowflake URN timestamps, filtering aggregator bots, and verifying corporate DNS MX records.
            </p>
          </div>

          {/* Live Pipeline Stage Pills */}
          <div className="flex items-center justify-center gap-2 flex-wrap max-w-2xl mx-auto">
            {[
              { icon: Globe, label: 'Multilingual Query Matrix' },
              { icon: Cpu, label: 'Snowflake URN Age Check' },
              { icon: ShieldCheck, label: 'DNS MX Email Verification' },
              { icon: Sparkles, label: 'ATS CV Skill Scoring' },
            ].map(({ icon: Icon, label }, i) => (
              <motion.span
                key={label}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.12 }}
                className="px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-[11px] font-semibold text-slate-300 flex items-center gap-1.5"
              >
                <Icon size={12} className="text-blue-400 animate-pulse" />
                <span>{label}</span>
              </motion.span>
            ))}
          </div>
        </motion.div>
      )}

      {/* Empty State */}
      {!loading && searched && filteredPosts.length === 0 && (
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          className="p-8 md:p-12 text-center text-slate-400 space-y-4 glass-card rounded-3xl max-w-lg mx-auto"
        >
          <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto">
            <Search size={22} className="text-blue-400" />
          </div>
          <div className="space-y-1.5">
            <p className="text-base font-extrabold text-white">No matching recruiter posts found</p>
            {postFilters.datePosted === '24h' ? (
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                No posts found in the <span className="text-white font-semibold">last 24 hours</span> for this role.
                LinkedIn frequently throttles recent post indexing — try expanding to Past Week.
              </p>
            ) : (
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Try broadening your search term (e.g. <code className="text-blue-300">Software Engineer</code>, <code className="text-blue-300">Full Stack</code>) or switching target location to <span className="text-white font-semibold">Worldwide</span>.
              </p>
            )}
          </div>

          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            {postFilters.datePosted === '24h' && (
              <button
                type="button"
                onClick={() => {
                  const next = { ...postFilters, datePosted: 'week' }
                  setPostFilters(next)
                  handleSearch(null, false, next)
                }}
                className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-md shadow-emerald-500/20"
              >
                <RotateCcw size={13} />
                <span>Try Past Week Instead</span>
              </button>
            )}
            {!isLinkedInConnected && (
              <button
                type="button"
                onClick={() => setShowLinkedInConnect(true)}
                className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-md shadow-blue-500/20"
              >
                <Link2 size={13} />
                <span>Connect LinkedIn for Direct Live Feed</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setPostFilters(DEFAULT_POST_FILTERS)
                handleSearch(null, false, DEFAULT_POST_FILTERS)
              }}
              className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
            >
              <RotateCcw size={12} />
              <span>Reset Filters & Search Again</span>
            </button>
          </div>
        </motion.div>
      )}

      {/* 4. Results: Split Workbench vs Cards Grid */}
      {!loading && filteredPosts.length > 0 && (
        viewMode === 'split' ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Left Master Feed (5 cols) */}
            <div className="lg:col-span-5">
              <PostSplitFeed
                posts={filteredPosts}
                selectedPostId={activePost?.id}
                onSelectPost={id => setSelectedPostId(id)}
                isPostApplied={isPostApplied}
                loadingMore={loadingMore}
                hasMore={hasMore}
                page={page}
                onLoadMore={handleLoadMore}
                observerTargetRef={observerTargetRef}
              />
            </div>

            {/* Right Active Detail Workbench (7 cols) */}
            <div className="lg:col-span-7">
              <PostDetailWorkbench
                post={activePost}
                isApplied={isPostApplied(activePost)}
                isSaved={isPostSaved(activePost)}
                applying={applyingPostId === activePost?.id}
                onAutoApply={p => setAutoApplyTarget(p)}
                onTailor={p => (onTailor ? onTailor(p) : setTailorTarget(p))}
                onOpenInMail={p => setInmailTarget(p)}
                onOpenReader={p => setReaderTarget(p)}
                onSave={handleSave}
              />
            </div>
          </div>
        ) : (
          <PostCardGrid
            posts={filteredPosts}
            isPostApplied={isPostApplied}
            isPostSaved={isPostSaved}
            applyingPostId={applyingPostId}
            onAutoApply={p => setAutoApplyTarget(p)}
            onTailor={p => (onTailor ? onTailor(p) : setTailorTarget(p))}
            onOpenInMail={p => setInmailTarget(p)}
            onSave={handleSave}
            loadingMore={loadingMore}
            hasMore={hasMore}
            page={page}
            onLoadMore={handleLoadMore}
            cardsObserverTargetRef={cardsObserverTargetRef}
          />
        )
      )}

      {/* 5. Modals */}
      <LocationPickerModal
        isOpen={showLocationPicker}
        onClose={() => setShowLocationPicker(false)}
        selectedLocations={selectedLocations}
        onToggleLocation={handleToggleLocation}
      />

      <AutoApplyModal
        isOpen={Boolean(autoApplyTarget)}
        onClose={() => setAutoApplyTarget(null)}
        post={autoApplyTarget}
        onSuccess={p => {
          setAppliedPostIds(prev => new Set([...prev, p.id]))
          setTrackerAppliedKeys(prev => {
            const next = new Set(prev)
            if (p.post_url) next.add(p.post_url.trim().toLowerCase())
            next.add(`${(p.role_title || '').trim().toLowerCase()}|${(p.company || '').trim().toLowerCase()}`)
            return next
          })
        }}
        onOpenSmtpPrompt={() => setShowSmtpPrompt(true)}
      />

      <InMailPitchModal
        isOpen={Boolean(inmailTarget)}
        onClose={() => setInmailTarget(null)}
        post={inmailTarget}
      />

      <PostReaderModal
        isOpen={Boolean(readerTarget)}
        onClose={() => setReaderTarget(null)}
        post={readerTarget}
        onAutoApply={p => setAutoApplyTarget(p)}
      />

      <TailorCvModal
        isOpen={Boolean(tailorTarget)}
        onClose={() => setTailorTarget(null)}
        job={tailorTarget}
      />

      <SmtpPromptModal
        isOpen={showSmtpPrompt}
        onClose={() => setShowSmtpPrompt(false)}
      />

      <BatchApplyModal
        isOpen={batchApplyOpen}
        onClose={() => setBatchApplyOpen(false)}
        items={posts.filter(p => p.has_email && p.recruiter_emails && p.recruiter_emails.length > 0)}
        source="linkedin"
        onSuccess={(appliedList) => {
          const appliedIds = appliedList.map(i => i.id)
          setAppliedPostIds(prev => new Set([...prev, ...appliedIds]))
          setTrackerAppliedKeys(prev => {
            const next = new Set(prev)
            appliedList.forEach(item => {
              if (item.post_url) next.add(item.post_url.trim().toLowerCase())
              next.add(`${(item.title || '').trim().toLowerCase()}|${(item.company || '').trim().toLowerCase()}`)
            })
            return next
          })
        }}
        onOpenSmtpPrompt={() => setShowSmtpPrompt(true)}
      />

      <LinkedInConnectModal
        isOpen={showLinkedInConnect}
        onClose={() => setShowLinkedInConnect(false)}
        onConnected={(cookie) => {
          setIsLinkedInConnected(Boolean(cookie))
          if (cookie && role.trim()) {
            handleSearch(null, true)
          }
        }}
      />
    </div>
  )
}
