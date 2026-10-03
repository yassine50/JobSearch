import { useState, useMemo, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import confetti from 'canvas-confetti'
import { Zap, RotateCcw, Search, Sparkles, Link2 } from 'lucide-react'
import client from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'

// Subcomponents
import PostSearchHeader from './hunter/PostSearchHeader.jsx'
import PostFilterBar, { DEFAULT_POST_FILTERS } from './hunter/PostFilterBar.jsx'
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

function parseApiError(err, defaultMsg) {
  const detail = err?.response?.data?.detail
  if (!detail) return err?.message || defaultMsg
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => (typeof d === 'object' ? (d.msg || JSON.stringify(d)) : String(d))).join('; ')
  }
  return String(detail)
}

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
      const applied = new Set()
      const saved = new Set()
      ;(r.data || []).forEach(a => {
        const u = (a.url || '').trim().toLowerCase()
        const tc = `${(a.title || '').trim().toLowerCase()}|${(a.company || '').trim().toLowerCase()}`
        if (['applied', 'interviewing', 'offer'].includes(a.status?.toLowerCase())) {
          if (u) applied.add(u)
          if (tc !== '|') applied.add(tc)
        } else if (a.status?.toLowerCase() === 'saved') {
          if (u) saved.add(u)
          if (tc !== '|') saved.add(tc)
        }
      })
      setTrackerAppliedKeys(applied)
      setTrackerSavedKeys(saved)
    }).catch(() => {})
  }, [])

  // Manual search only: search starts only when user explicitly clicks "Search Posts"

  // Check if post is applied or saved
  const isPostApplied = (p) => {
    if (!p) return false
    if (appliedPostIds.has(p.id) || p.is_applied) return true
    const u = (p.post_url || '').trim().toLowerCase()
    const tc = `${(p.role_title || '').trim().toLowerCase()}|${(p.company || '').trim().toLowerCase()}`
    return trackerAppliedKeys.has(u) || trackerAppliedKeys.has(tc)
  }

  const isPostSaved = (p) => {
    if (!p) return false
    if (isPostApplied(p)) return false
    if (savedPostIds.has(p.id) || p.is_saved) return true
    const u = (p.post_url || '').trim().toLowerCase()
    const tc = `${(p.role_title || '').trim().toLowerCase()}|${(p.company || '').trim().toLowerCase()}`
    return trackerSavedKeys.has(u) || trackerSavedKeys.has(tc)
  }

  // Primary Search
  const handleSearch = async (e, forceRefresh = false, activeFilters = postFilters) => {
    if (e) e.preventDefault()
    if (!role.trim()) {
      toast('Please enter a role or skill to search', 'error')
      return
    }

    setLoading(true)
    setPage(1)
    setHasMore(true)
    try {
      const activeLocs = selectedLocations.filter(l => l && l.toLowerCase() !== 'worldwide')
      const eff = activeFilters || postFilters
      const liAt = (localStorage.getItem('linkedin_li_at') || '').trim()
      const { data } = await client.post('/linkedin-posts/search', {
        role: role.trim(),
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
      // 1. Exclude already applied posts so candidate never sees them again
      if (isPostApplied(p)) return false

      // 2. Email verification filter
      if (postFilters.emailOnly) {
        if (!p.has_email || !p.recruiter_emails || p.recruiter_emails.length === 0) {
          return false
        }
      }

      // 3. Date Posted filter
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

    // Sort by postFilters.sortBy
    if (postFilters.sortBy === 'recent') {
      result = [...result].sort((a, b) => {
        const aAge = a.age_hours != null ? a.age_hours : 9999
        const bAge = b.age_hours != null ? b.age_hours : 9999
        return aAge - bAge
      })
    } else {
      // 'relevant' (default)
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
    <div className="space-y-4">
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
          // When date filter or sortBy changes after a search, re-run with new filters
          if (searched && role.trim()) {
            handleSearch(null, false, newFilters)
          }
        }}
      />

      {/* 3. Empty & Loading States */}
      {loading && posts.length === 0 && (
        <div className="p-12 text-center text-slate-400 space-y-3.5 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-xl">
          {/* Authentic LinkedIn C-shaped loading spinner from media_1789952339246.png */}
          <div className="inline-block w-9 h-9 border-[3.5px] border-slate-700 border-t-blue-500 border-r-blue-400 rounded-full animate-spin" />
          <div className="space-y-1">
            <p className="text-sm font-bold text-white tracking-wide">Waiting for LinkedIn posts to load...</p>
            <p className="text-xs text-slate-400">
              Scrolling down feed, waiting for page loads to complete, and mining verified recruiter mailboxes...
            </p>
          </div>
        </div>
      )}

      {!loading && searched && filteredPosts.length === 0 && (
        <div className="p-8 md:p-12 text-center text-slate-400 space-y-4 bg-slate-900/60 border border-slate-800/80 rounded-2xl max-w-lg mx-auto shadow-xl">
          <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto text-xl">
            <Search size={22} className="text-blue-400" />
          </div>
          <div className="space-y-1.5">
            <p className="text-base font-bold text-white">No matching recruiter posts found</p>
            {postFilters.datePosted === '24h' ? (
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                No posts found in the <span className="text-white font-medium">last 24 hours</span> for this role.
                LinkedIn frequently throttles recent post indexing — try a wider window.
              </p>
            ) : (
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Try broadening your search term (e.g. <code className="text-blue-300">Software Engineer</code>, <code className="text-blue-300">Full Stack</code>) or switching target location to <span className="text-white font-medium">Worldwide</span>.
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
                handleApplyAndSearch(DEFAULT_POST_FILTERS)
              }}
              className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 text-slate-300 text-xs font-medium flex items-center justify-center gap-1.5 transition cursor-pointer"
            >
              <RotateCcw size={12} />
              <span>Reset Filters & Search Again</span>
            </button>
          </div>
        </div>
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
