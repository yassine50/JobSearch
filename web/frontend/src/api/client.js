import axios from 'axios'

const RAW_API_URL = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '')
// Ignore legacy onrender.com env var so Vercel's /api/* rewrite routes directly to the fast VPS (34.55.247.158)
const EFFECTIVE_API_URL = RAW_API_URL.includes('onrender.com') ? '' : RAW_API_URL
const baseURL = EFFECTIVE_API_URL
  ? (EFFECTIVE_API_URL.endsWith('/api') ? EFFECTIVE_API_URL : `${EFFECTIVE_API_URL}/api`)
  : '/api'

const client = axios.create({ baseURL })

client.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

client.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/'
    }
    return Promise.reject(err)
  }
)

export default client
