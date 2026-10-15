import axios from 'axios'

const RAW_API_URL = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '')
// Ignore legacy onrender.com env var so Vercel's /api/* rewrite routes directly to the fast VPS (34.55.247.158)
const EFFECTIVE_API_URL = RAW_API_URL.includes('onrender.com') ? '' : RAW_API_URL
const baseURL = EFFECTIVE_API_URL
  ? (EFFECTIVE_API_URL.endsWith('/api') ? EFFECTIVE_API_URL : `${EFFECTIVE_API_URL}/api`)
  : '/api'

const client = axios.create({ baseURL })

// ─────────────────────────────────────────────────────────────────────────────
// Ultra-Fast Stale-While-Revalidate (SWR) Memory + Session Cache
// ─────────────────────────────────────────────────────────────────────────────
const _memCache = new Map()
const _cacheTs = new Map()
const _inFlightGet = new Map()
const CACHE_PREFIX = 'js_swr_v1:'
const FRESH_TTL_MS = 4000

function _tokenTag() {
  const t = localStorage.getItem('token') || ''
  return t ? t.slice(-12) : 'anon'
}

export function normalizeCacheKey(url = '', params = null) {
  let clean = String(url || '').trim()
  if (clean.startsWith(baseURL)) clean = clean.slice(baseURL.length)
  if (clean.startsWith('/api/')) clean = clean.slice(4)
  if (!clean.startsWith('/')) clean = '/' + clean

  if (params && typeof params === 'object') {
    const entries = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .sort(([a], [b]) => a.localeCompare(b))
    if (entries.length > 0) {
      const qs = entries
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&')
      clean += (clean.includes('?') ? '&' : '?') + qs
    }
  }
  return `${_tokenTag()}:${clean}`
}

export function getCached(url, fallback = null, params = null) {
  const key = normalizeCacheKey(url, params)
  if (_memCache.has(key)) {
    return _memCache.get(key)
  }
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + key)
    if (raw) {
      const parsed = JSON.parse(raw)
      _memCache.set(key, parsed)
      return parsed
    }
  } catch {
    // Ignore storage parse errors
  }
  return fallback
}

function _setCached(url, params, data) {
  if (data === undefined || data instanceof Blob) return
  const key = normalizeCacheKey(url, params)
  _memCache.set(key, data)
  _cacheTs.set(key, Date.now())
  try {
    const serialized = JSON.stringify(data)
    if (serialized.length < 350000) {
      sessionStorage.setItem(CACHE_PREFIX + key, serialized)
    }
  } catch {
    // Ignore sessionStorage quota errors
  }
}

export function invalidateCache() {
  _cacheTs.clear()
}

export function clearAllCache() {
  _memCache.clear()
  _cacheTs.clear()
  _inFlightGet.clear()
  try {
    Object.keys(sessionStorage).forEach(k => {
      if (k.startsWith(CACHE_PREFIX)) sessionStorage.removeItem(k)
    })
  } catch {
    // Ignore
  }
}

client.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

client.interceptors.response.use(
  res => {
    const method = (res.config?.method || 'get').toLowerCase()
    if (method === 'get' && res.status === 200 && res.config?.responseType !== 'blob') {
      _setCached(res.config.url, res.config.params, res.data)
    } else if (method !== 'get') {
      // Any mutation marks cached GET timestamps stale so next GET revalidates from server
      _cacheTs.clear()
    }
    return res
  },
  err => {
    if (err.response?.status === 401) {
      clearAllCache()
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/'
    }
    return Promise.reject(err)
  }
)

// Wrap client.get with in-flight deduplication and short-window freshness reuse
const _rawGet = client.get.bind(client)
client.get = function cachedGet(url, config = {}) {
  if (config?.responseType === 'blob') {
    return _rawGet(url, config)
  }
  const key = normalizeCacheKey(url, config?.params)
  const now = Date.now()
  if (!config?.forceRefresh && _memCache.has(key) && (now - (_cacheTs.get(key) || 0) < FRESH_TTL_MS)) {
    return Promise.resolve({
      data: _memCache.get(key),
      status: 200,
      statusText: 'OK (cached)',
      headers: {},
      config,
    })
  }
  if (_inFlightGet.has(key)) {
    return _inFlightGet.get(key)
  }
  const reqPromise = _rawGet(url, config).finally(() => {
    _inFlightGet.delete(key)
  })
  _inFlightGet.set(key, reqPromise)
  return reqPromise
}

// ─────────────────────────────────────────────────────────────────────────────
// Proactive Workspace & Route Prefetching
// ─────────────────────────────────────────────────────────────────────────────
let _lastWorkspacePrefetch = 0

export function prefetchWorkspaceData() {
  if (!localStorage.getItem('token')) return
  const now = Date.now()
  if (now - _lastWorkspacePrefetch < 15000) return
  _lastWorkspacePrefetch = now

  const d = new Date()
  const y = d.getFullYear()
  const m = d.getMonth() + 1

  // Stage 1: Highest-priority core pages (Dashboard, Tracker, Seeker)
  Promise.allSettled([
    client.get('/tracker'),
    client.get('/tracker/stats/detailed'),
    client.get('/cv/info'),
    client.get('/jobs/saved'),
  ]).then(() => {
    // Stage 2: Secondary tabs (Follow-ups, Email History, Calendar, Settings)
    Promise.allSettled([
      client.get('/email/follow-up/candidates?days=3'),
      client.get('/email/history'),
      client.get(`/email/calendar-analytics?year=${y}&month=${m}`),
      client.get('/email/settings'),
      client.get('/email/google/status'),
    ])
  })
}

export function prefetchRouteData(routePath) {
  if (!localStorage.getItem('token')) return
  const d = new Date()
  const y = d.getFullYear()
  const m = d.getMonth() + 1

  switch (routePath) {
    case '/tracker':
      client.get('/tracker').catch(() => {})
      client.get('/email/follow-up/candidates?days=3').catch(() => {})
      break
    case '/dashboard':
      client.get('/tracker/stats/detailed').catch(() => {})
      client.get('/jobs/saved').catch(() => {})
      client.get('/cv/info').catch(() => {})
      break
    case '/seeker':
      client.get('/cv/info').catch(() => {})
      client.get('/tracker').catch(() => {})
      break
    case '/email':
      client.get('/email/history').catch(() => {})
      client.get(`/email/calendar-analytics?year=${y}&month=${m}`).catch(() => {})
      break
    case '/coverletter':
    case '/cover-letter':
      client.get('/cv/info').catch(() => {})
      break
    case '/settings':
      client.get('/email/settings').catch(() => {})
      client.get('/email/google/status').catch(() => {})
      client.get('/email/custom-templates').catch(() => {})
      client.get('/email/blacklist').catch(() => {})
      break
    default:
      break
  }
}

export default client
