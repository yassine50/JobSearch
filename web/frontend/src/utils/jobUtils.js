/**
 * Shared Job & Post Utilities
 * Centralizes URL normalization, Tracker state matching, and FastAPI error parsing.
 */

/**
 * Normalizes job/post URLs without stripping Indeed's `?jk=` job key identifier.
 */
export function getCleanJobUrl(url) {
  if (!url) return ''
  const u = String(url).trim().toLowerCase()
  if (u.includes('indeed.com') || u.includes('viewjob')) {
    const match = u.match(/[?&]jk=([a-zA-Z0-9]+)/)
    if (match) return `indeed:${match[1]}`
    return u.split('&')[0].replace(/\/+$/, '')
  }
  return u.split('?')[0].replace(/\/+$/, '')
}

/**
 * Extracts normalized identity keys ({ rawUrl, cleanUrl, titleCompanyKey })
 * from either a formal Job Board item, a LinkedIn Post item, or a Tracker item.
 */
export function getJobIdentityKeys(item) {
  if (!item) return { rawUrl: '', cleanUrl: '', titleCompanyKey: '' }
  const target = item.raw || item
  const rawUrl = String(
    target.url || target.job_url || target.job_url_direct || target.post_url || ''
  ).trim().toLowerCase()
  const cleanUrl = getCleanJobUrl(rawUrl)
  const title = String(target.title || target.role_title || '').trim().toLowerCase()
  const company = String(target.company || '').trim().toLowerCase()
  const titleCompanyKey = title || company ? `${title}|${company}` : ''
  return { rawUrl, cleanUrl, titleCompanyKey }
}

/**
 * Builds `appliedSet` and `savedSet` lookup sets from GET /tracker array.
 */
export function buildTrackerLookupSets(trackerApps = []) {
  const applied = new Set()
  const saved = new Set()

  ;(trackerApps || []).forEach(app => {
    const { rawUrl, cleanUrl, titleCompanyKey } = getJobIdentityKeys(app)
    const status = String(app?.status || '').toLowerCase()
    if (['applied', 'interviewing', 'interview', 'offer', 'accepted', 'review'].includes(status)) {
      if (rawUrl) applied.add(rawUrl)
      if (cleanUrl) applied.add(cleanUrl)
      if (titleCompanyKey && titleCompanyKey !== '|') applied.add(titleCompanyKey)
    } else if (status === 'saved') {
      if (rawUrl) saved.add(rawUrl)
      if (cleanUrl) saved.add(cleanUrl)
      if (titleCompanyKey && titleCompanyKey !== '|') saved.add(titleCompanyKey)
    }
  })

  return { applied, saved }
}

/**
 * Checks if a job or post matches any key in a tracker Set.
 */
export function matchesTrackerSet(item, lookupSet) {
  if (!item || !lookupSet || lookupSet.size === 0) return false
  const { rawUrl, cleanUrl, titleCompanyKey } = getJobIdentityKeys(item)
  return (
    (rawUrl && lookupSet.has(rawUrl)) ||
    (cleanUrl && lookupSet.has(cleanUrl)) ||
    (titleCompanyKey && titleCompanyKey !== '|' && lookupSet.has(titleCompanyKey))
  )
}

/**
 * Standardizes FastAPI / Axios error extraction into a clean human-readable string.
 */
export function parseApiError(err, defaultMsg = 'Request failed') {
  const detail = err?.response?.data?.detail
  if (!detail) return err?.message || defaultMsg
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(d => (typeof d === 'object' ? (d.msg || JSON.stringify(d)) : String(d)))
      .join('; ')
  }
  return String(detail)
}
