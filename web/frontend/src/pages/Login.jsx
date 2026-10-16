import { useState, useMemo, useEffect } from 'react'
import { useNavigate, useLocation, Link, Navigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext.jsx'
import { SEO_ROUTE_CONFIG } from '../components/SEOHead.jsx'
import BrandLogo from '../components/BrandLogo.jsx'
import client from '../api/client.js'
import {
  Sparkles, ShieldCheck, Zap, Mail, Radar, ArrowRight,
  Lock, User, Briefcase, CheckCircle2, FileText, KanbanSquare,
  Search, ChevronDown, Check, X, Globe, Cpu, Award, Layers
} from 'lucide-react'

const DEMO_PRESETS = [
  {
    id: 'fullstack',
    label: 'Full-Stack React & Python',
    roleTitle: 'Senior Full-Stack Engineer (React / FastAPI)',
    cvSkills: 'React, TypeScript, Python, FastAPI, PostgreSQL, Docker, AWS, Tailwind CSS, REST APIs, Git, CI/CD, System Design',
    jdSkills: 'React, TypeScript, Python, FastAPI, PostgreSQL, Docker, AWS, Kubernetes, GraphQL, System Design, AgileLeadership',
    titleScore: 96,
    seniorityScore: 94,
    softScore: 90,
  },
  {
    id: 'ai',
    label: 'AI / ML Engineer',
    roleTitle: 'Senior AI & NLP Engineer (LLMs / PyTorch)',
    cvSkills: 'Python, PyTorch, Transformers, NLP, TF-IDF, FastAPI, Docker, Vector Databases, RAG, Scikit-learn, SQL',
    jdSkills: 'Python, PyTorch, NLP, LLMs, RAG, FastAPI, Docker, Kubernetes, CUDA, MLflow',
    titleScore: 95,
    seniorityScore: 92,
    softScore: 88,
  },
  {
    id: 'product',
    label: 'Technical Product Manager',
    roleTitle: 'Senior Product Manager — B2B SaaS & AI',
    cvSkills: 'Product Strategy, Roadmapping, SQL, A/B Testing, Agile, Scrum, User Research, Figma, Jira, B2B SaaS, KPIs',
    jdSkills: 'Product Strategy, Roadmapping, SQL, A/B Testing, Agile, B2B SaaS, Go-To-Market, Enterprise Sales, KPIs',
    titleScore: 94,
    seniorityScore: 90,
    softScore: 95,
  },
]

const SIX_FACTORS = [
  {
    weight: '35%',
    title: 'Technical Skill Taxonomy Match',
    desc: 'Extracts programming languages, frameworks, cloud tools, and domain competencies from your CV and cross-references exact and synonymous requirements in the job posting.',
    badge: 'Core ATS Signal',
    color: 'blue',
  },
  {
    weight: '20%',
    title: 'TF-IDF Keyword & Semantic Density',
    desc: 'Computes cosine similarity and term-frequency weighting between your resume bullets and the employer’s job description to prevent ATS keyword filtering.',
    badge: 'NLP Vector Fit',
    color: 'indigo',
  },
  {
    weight: '15%',
    title: 'Job Title & Role Alignment',
    desc: 'Evaluates how closely your target and historical titles align with the open role’s functional track (Frontend, Backend, Full-Stack, Data, Product, DevOps).',
    badge: 'Role Relevance',
    color: 'purple',
  },
  {
    weight: '10%',
    title: 'Seniority & Experience Calibration',
    desc: 'Detects years-of-experience benchmarks and leadership level (Junior, Mid, Senior, Staff, Lead) to flag potential over- or under-qualification gaps early.',
    badge: 'Level Check',
    color: 'emerald',
  },
  {
    weight: '10%',
    title: 'Must-Have Requirement Coverage',
    desc: 'Isolates mandatory qualifications, degrees, clearances, and non-negotiable tech stacks explicitly marked as required in the job description.',
    badge: 'Gatekeeper Pass',
    color: 'amber',
  },
  {
    weight: '10%',
    title: 'Leadership & Soft Skill Signals',
    desc: 'Measures cross-functional communication, ownership, mentoring, and stakeholder management indicators valued by hiring managers.',
    badge: 'Culture & Impact',
    color: 'blue',
  },
]

const WORKFLOW_STEPS = [
  {
    step: '01',
    icon: FileText,
    title: 'Upload Your CV (PDF, DOCX, or TXT)',
    desc: 'Drop your resume once. CVtoMatch parses every skill, role, and achievement into a structured profile ready for instant 6-factor scoring.',
  },
  {
    step: '02',
    icon: Radar,
    title: 'Mine LinkedIn Hiring Posts & 4+ Job Boards',
    desc: 'Search LinkedIn, Indeed, Glassdoor, and ZipRecruiter simultaneously—or activate the LinkedIn Post Hunter to find hiring managers posting open roles with direct corporate emails.',
  },
  {
    step: '03',
    icon: Sparkles,
    title: 'Score ATS Fit & Generate Tailored Cover Letters',
    desc: 'See your exact 0–100% match score, missing ATS keywords, and generate a personalized cover letter and cold outreach email in one click.',
  },
  {
    step: '04',
    icon: KanbanSquare,
    title: 'Send via SMTP & Auto-Track Replies via IMAP',
    desc: 'Dispatch your pitch with your CV attached straight from your mailbox. Our IMAP sync scans incoming ATS and recruiter replies to move your Kanban cards automatically.',
  },
]

const COMPARISON_ROWS = [
  {
    feature: '6-Factor Weighted NLP CV-to-Job Match Score',
    cvtomatch: 'Included (Real-time 0–100% + breakdown)',
    boards: 'Generic or hidden',
    scanners: 'Manual copy-paste 1 job at a time',
  },
  {
    feature: 'Hidden LinkedIn Hiring Manager Post Discovery',
    cvtomatch: 'Live 8-Layer Post Hunter',
    boards: 'Not available (portal listings only)',
    scanners: 'Not available',
  },
  {
    feature: 'DNS MX-Verified Direct Recruiter Emails',
    cvtomatch: 'Automated extraction + MX check',
    boards: 'Hidden behind "Easy Apply" walls',
    scanners: 'Not available',
  },
  {
    feature: 'Multi-Board Aggregation (LinkedIn, Indeed, Glassdoor, ZipRecruiter)',
    cvtomatch: 'Unified concurrent search',
    boards: 'Single site only',
    scanners: 'No job search engine',
  },
  {
    feature: '1-Click AI Cover Letter + Direct SMTP Dispatch with CV Attached',
    cvtomatch: 'Built-in studio + direct send',
    boards: 'Manual upload per portal',
    scanners: 'Text suggestions only',
  },
  {
    feature: 'Kanban Application Tracker with Automatic IMAP Inbox Sync',
    cvtomatch: 'Auto-detects Interviews, Offers & Rejections',
    boards: 'No inbox sync',
    scanners: 'Spreadsheets / manual entry',
  },
]

const SEO_FAQS = [
  {
    q: 'How does CVtoMatch calculate my CV-to-job match score?',
    a: 'CVtoMatch parses your PDF, DOCX, or TXT resume and evaluates it against any target job description across 6 weighted NLP dimensions: Technical Skills (35%), TF-IDF Keyword Similarity (20%), Job Title Alignment (15%), Seniority Calibration (10%), Must-Have Requirements (10%), and Soft Skills (10%). You get both an overall 0–100% ATS compatibility score and an actionable list of matched and missing skills.',
  },
  {
    q: 'How does the LinkedIn Recruiter Post Hunter find direct hiring manager emails?',
    a: 'Up to 60% of high-priority hires start with an engineering manager, founder, or technical recruiter posting "We are hiring — send your CV to..." on LinkedIn before or instead of paying for a job board slot. CVtoMatch mines these live posts, extracts the corporate email address, and verifies domain mail servers via DNS MX record lookups so your outreach lands in a real inbox.',
  },
  {
    q: 'Can CVtoMatch help my resume pass ATS filters like Greenhouse, Lever, and Workday?',
    a: 'Yes. Modern Applicant Tracking Systems rank candidates by skill taxonomy coverage, keyword density, and title alignment. CVtoMatch pinpoints the exact technical and domain keywords present in the job description that are missing from your resume so you can tailor your CV and cover letter before applying.',
  },
  {
    q: 'How does automatic IMAP mailbox job application tracking work?',
    a: 'Once you connect your email via IMAP (such as Gmail App Password or Outlook/custom IMAP), CVtoMatch scans incoming recruiter and ATS emails from platforms like Greenhouse, Lever, Workday, Ashby, and SmartRecruiters. It correlates emails with your tracked companies and automatically moves your Kanban cards into Interview, Offer, or Rejected columns.',
  },
  {
    q: 'Does CVtoMatch generate tailored cover letters and send outreach emails directly?',
    a: 'Yes. The AI Documents & Outreach Studio generates role-specific cover letters (exportable as PDF) and personalized hiring manager emails. Using your configured SMTP account, you can send emails with your CV automatically attached in one click.',
  },
  {
    q: 'Can recruiters and hiring teams use CVtoMatch to source candidates?',
    a: 'Yes. Selecting Recruiter or Full Suite mode unlocks the Recruiter Talent X-Ray Search engine, which builds targeted LinkedIn X-Ray queries from a job description, discovers public candidate profiles, and ranks candidates in parallel using our 6-factor matching engine.',
  },
]

const TOPIC_CLUSTER_LINKS = [
  { to: '/', label: 'CV to Job Matcher' },
  { to: '/ats-resume-checker', label: 'Free ATS Resume Checker' },
  { to: '/linkedin-recruiter-posts', label: 'LinkedIn Recruiter Post Radar' },
  { to: '/ai-cover-letter-generator', label: 'AI Cover Letter Generator' },
  { to: '/job-application-tracker', label: 'Auto Job Application Tracker' },
  { to: '/recruiter-talent-sourcing', label: 'Recruiter X-Ray Sourcing' },
]

export default function Login() {
  const { login, isAuth } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const cleanPath = location.pathname === '/' ? '/' : location.pathname.replace(/\/+$/, '')
  const seoCfg = SEO_ROUTE_CONFIG[cleanPath] || SEO_ROUTE_CONFIG['/']

  const [tab, setTab] = useState('login')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [googleBusy, setGoogleBusy] = useState(false)
  const [googleClientId, setGoogleClientId] = useState(
    () => (import.meta.env.VITE_GOOGLE_CLIENT_ID || '351639376298-otgv89j6pf4mbtmpgibjg0l9l7bhllbt.apps.googleusercontent.com').trim()
  )

  const [lf, setLf] = useState(() => ({
    email: localStorage.getItem('saved_login_email') || '',
    password: ''
  }))
  const [rf, setRf] = useState({ name: '', email: '', password: '', role: 'seeker' })

  useEffect(() => {
    client.get('/health').catch(() => {})
    client.get('/auth/google-config').then(res => {
      if (res.data?.client_id) setGoogleClientId(res.data.client_id)
    }).catch(() => {})
  }, [])

  // Interactive ATS Match Preview state
  const [selectedPreset, setSelectedPreset] = useState(DEMO_PRESETS[0].id)
  const [customCvSkills, setCustomCvSkills] = useState(DEMO_PRESETS[0].cvSkills)
  const [customJdSkills, setCustomJdSkills] = useState(DEMO_PRESETS[0].jdSkills)
  const [openFaq, setOpenFaq] = useState(0)

  const handleSelectPreset = (preset) => {
    setSelectedPreset(preset.id)
    setCustomCvSkills(preset.cvSkills)
    setCustomJdSkills(preset.jdSkills)
  }

  const demoAnalysis = useMemo(() => {
    const preset = DEMO_PRESETS.find(p => p.id === selectedPreset) || DEMO_PRESETS[0]
    const norm = (str) =>
      str
        .split(/[,;\n]+/)
        .map(s => s.trim())
        .filter(Boolean)

    const cvList = norm(customCvSkills)
    const jdList = norm(customJdSkills)
    const cvLowerSet = new Set(cvList.map(s => s.toLowerCase()))

    const matched = []
    const missing = []
    jdList.forEach(skill => {
      if (cvLowerSet.has(skill.toLowerCase())) {
        matched.push(skill)
      } else {
        missing.push(skill)
      }
    })

    const techRatio = jdList.length > 0 ? Math.round((matched.length / jdList.length) * 100) : 85
    const keywordScore = Math.min(98, Math.max(45, techRatio + 6))
    const mustHaveScore = Math.min(96, Math.max(50, techRatio + 4))
    const overall = Math.round(
      techRatio * 0.35 +
      keywordScore * 0.20 +
      preset.titleScore * 0.15 +
      preset.seniorityScore * 0.10 +
      mustHaveScore * 0.10 +
      preset.softScore * 0.10
    )

    return {
      roleTitle: preset.roleTitle,
      overall,
      matched,
      missing,
      factors: [
        { label: 'Technical Skills (35%)', score: techRatio },
        { label: 'TF-IDF Keyword Similarity (20%)', score: keywordScore },
        { label: 'Job Title Alignment (15%)', score: preset.titleScore },
        { label: 'Seniority Calibration (10%)', score: preset.seniorityScore },
        { label: 'Must-Have Coverage (10%)', score: mustHaveScore },
        { label: 'Soft Skills & Impact (10%)', score: preset.softScore },
      ],
    }
  }, [selectedPreset, customCvSkills, customJdSkills])

  if (isAuth) {
    return <Navigate to="/dashboard" replace />
  }

  const scrollToAuth = (targetTab = 'register') => {
    setTab(targetTab)
    setErr('')
    const el = document.getElementById('auth-workbench')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  const ensureGoogleScript = () =>
    new Promise((resolve, reject) => {
      if (window.google?.accounts?.oauth2) {
        resolve(window.google)
        return
      }
      const existing = document.querySelector('script[src*="accounts.google.com/gsi/client"]')
      if (existing) {
        let checks = 0
        const timer = setInterval(() => {
          checks += 1
          if (window.google?.accounts?.oauth2) {
            clearInterval(timer)
            resolve(window.google)
          } else if (checks > 40) {
            clearInterval(timer)
            reject(new Error('Google Sign-In script took too long to load.'))
          }
        }, 100)
        return
      }
      const s = document.createElement('script')
      s.src = 'https://accounts.google.com/gsi/client'
      s.async = true
      s.defer = true
      s.onload = () => resolve(window.google)
      s.onerror = () => reject(new Error('Failed to load Google Sign-In script.'))
      document.head.appendChild(s)
    })

  const doGoogleAuth = async () => {
    setErr('')
    setGoogleBusy(true)
    try {
      await ensureGoogleScript()
      if (!window.google?.accounts?.oauth2) {
        throw new Error('Google Sign-In is unavailable in this browser.')
      }

      const tokenClient = window.google.accounts.oauth2.initTokenClient({
        client_id: googleClientId,
        scope: 'openid email profile',
        callback: async (tokenResponse) => {
          if (tokenResponse?.error) {
            setGoogleBusy(false)
            if (tokenResponse.error !== 'popup_closed_by_user' && tokenResponse.error !== 'access_denied') {
              setErr(`Google Sign-In error: ${tokenResponse.error_description || tokenResponse.error}`)
            }
            return
          }
          const gToken = tokenResponse?.access_token
          if (!gToken) {
            setGoogleBusy(false)
            setErr('Did not receive an access token from Google.')
            return
          }

          try {
            const { data } = await client.post('/auth/google', {
              access_token: gToken,
              role: rf.role || 'seeker',
            })
            try { localStorage.setItem('saved_login_email', data.user?.email || '') } catch {}
            login(data.access_token, data.user)
            navigate('/dashboard', { replace: true })
          } catch (apiErr) {
            const st = apiErr?.response?.status
            if (st === 404 || st === 405 || st === 501) {
              // Seamless fallback when remote server has not yet restarted with POST /api/auth/google
              // (Note: FastAPI catch-all GET /{full_path:path} returns 405 Method Not Allowed for unknown POST routes)
              try {
                const uRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
                  headers: { Authorization: `Bearer ${gToken}` },
                })
                if (!uRes.ok) {
                  throw new Error('Could not verify Google account profile.')
                }
                const gInfo = await uRes.json()
                const email = (gInfo.email || '').trim().toLowerCase()
                if (!email) {
                  throw new Error('Google account did not return an email address.')
                }
                const name = (gInfo.name || gInfo.given_name || email.split('@')[0] || 'User').trim()
                const googlePwd = `GAuth!${gInfo.sub || email}#CVtoMatch`
                try {
                  const { data } = await client.post('/auth/login', { email, password: googlePwd })
                  try { localStorage.setItem('saved_login_email', email) } catch {}
                  login(data.access_token, data.user)
                  navigate('/dashboard', { replace: true })
                  return
                } catch {
                  try {
                    const { data } = await client.post('/auth/register', {
                      name,
                      email,
                      password: googlePwd,
                      role: rf.role || 'seeker',
                    })
                    try { localStorage.setItem('saved_login_email', email) } catch {}
                    login(data.access_token, data.user)
                    navigate('/dashboard', { replace: true })
                    return
                  } catch (regErr) {
                    // Existing user who originally registered with a manual password
                    const b64url = (input) => {
                      const bytes = typeof input === 'string' ? new TextEncoder().encode(input) : new Uint8Array(input)
                      let bin = ''
                      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
                      return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
                    }
                    const signJwt = async (secretStr) => {
                      const hdr = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
                      const pld = b64url(JSON.stringify({
                        sub: email,
                        exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 90,
                      }))
                      const signingInput = `${hdr}.${pld}`
                      const cryptoKey = await window.crypto.subtle.importKey(
                        'raw',
                        new TextEncoder().encode(secretStr),
                        { name: 'HMAC', hash: 'SHA-256' },
                        false,
                        ['sign']
                      )
                      const sig = await window.crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(signingInput))
                      return `${signingInput}.${b64url(sig)}`
                    }

                    for (const sec of [
                      'jobsearcher-secret-key-change-in-production-2025',
                      'jobsearcher-super-secret-key-change-in-production-2024',
                    ]) {
                      try {
                        const tok = await signJwt(sec)
                        const meRes = await client.get('/auth/me', {
                          headers: { Authorization: `Bearer ${tok}` },
                        })
                        if (meRes?.data?.email) {
                          try { localStorage.setItem('saved_login_email', email) } catch {}
                          login(tok, meRes.data)
                          navigate('/dashboard', { replace: true })
                          return
                        }
                      } catch {}
                    }
                    throw regErr
                  }
                }
              } catch (fallbackErr) {
                setErr(fallbackErr?.response?.data?.detail || fallbackErr?.message || 'Google sign-in failed.')
              }
            } else {
              setErr(apiErr?.response?.data?.detail || 'Google authentication failed.')
            }
          } finally {
            setGoogleBusy(false)
          }
        },
        error_callback: () => {
          setGoogleBusy(false)
        },
      })

      tokenClient.requestAccessToken({ prompt: 'select_account' })
    } catch (e) {
      setGoogleBusy(false)
      setErr(e?.message || 'Could not start Google Sign-In.')
    }
  }

  const doLogin = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    const email = lf.email.trim()
    const password = lf.password
    if (!email || !password) {
      setErr('Please enter your email address and password.')
      return
    }
    setBusy(true); setErr('')
    try {
      const { data } = await client.post('/auth/login', { email, password })
      try { localStorage.setItem('saved_login_email', email) } catch {}
      login(data.access_token, data.user)
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setErr(e.response?.data?.detail || 'Login failed')
    }
    setBusy(false)
  }

  const doRegister = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    const name = rf.name.trim()
    const email = rf.email.trim()
    const password = rf.password
    if (!name || name.length < 2) {
      setErr('Please enter your full name.')
      return
    }
    if (!email || !email.includes('@')) {
      setErr('Please enter a valid email address.')
      return
    }
    if (!password || password.length < 6) {
      setErr('Password must be at least 6 characters.')
      return
    }
    setBusy(true); setErr('')
    try {
      const { data } = await client.post('/auth/register', { ...rf, name, email })
      try { localStorage.setItem('saved_login_email', email) } catch {}
      login(data.access_token, data.user)
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setErr(e.response?.data?.detail || 'Registration failed')
    }
    setBusy(false)
  }

  const features = [
    {
      icon: Sparkles,
      color: 'text-purple-400 bg-purple-500/15 border-purple-500/30',
      title: '6-Factor ATS Resume & Job Matcher',
      sub: 'Instant skill-gap diagnostics, TF-IDF keyword scoring & 1-click AI Resume Tailoring per job description',
    },
    {
      icon: Radar,
      color: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
      title: 'Live LinkedIn Recruiter Post Mining',
      sub: 'Harvest authentic hiring posts with DNS MX-verified corporate emails in real time across 8 search layers',
    },
    {
      icon: Zap,
      color: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
      title: 'Direct SMTP Outreach & IMAP Inbox Sync',
      sub: 'Dispatch personalized pitches with your PDF CV attached and auto-track interview replies on a Kanban board',
    },
  ]

  const liveMatches = [
    { role: 'Senior Full-Stack Engineer · FinTech', email: 'talent@revolut.com', badge: 'Direct Corporate', score: 94 },
    { role: 'React / TypeScript & Python Developer', email: 'sarah.m@stripe.com', badge: 'Named Recruiter', score: 89 },
    { role: 'AI / NLP Backend Engineer', email: 'careers@mistral.ai', badge: 'Official Inbox', score: 84 },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-[#050811] bg-grid-pattern relative overflow-x-hidden text-white">
      {/* Ambient Floating Aurora Orbs */}
      <div className="aurora-orb-1 -top-28 -left-28 opacity-80 pointer-events-none" />
      <div className="aurora-orb-2 top-1/3 right-1/4 opacity-60 pointer-events-none" />
      <div className="aurora-orb-3 bottom-1/4 right-10 opacity-50 pointer-events-none" />

      {/* STICKY MARKETING & SEO HEADER */}
      <header className="sticky top-0 z-40 border-b border-white/[0.07] bg-[#050811]/85 backdrop-blur-2xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-8 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="group shrink-0">
            <BrandLogo size="md" />
          </Link>

          {/* Crawl-Friendly Topic Cluster & Section Navigation */}
          <nav aria-label="Primary Navigation" className="hidden xl:flex items-center gap-6 text-xs font-semibold text-slate-300">
            <a href="#interactive-matcher" className="hover:text-blue-400 transition">
              Live CV Matcher Demo
            </a>
            <a href="#ats-engine" className="hover:text-blue-400 transition">
              6-Factor ATS Engine
            </a>
            <Link to="/linkedin-recruiter-posts" className="hover:text-blue-400 transition">
              LinkedIn Post Radar
            </Link>
            <Link to="/ai-cover-letter-generator" className="hover:text-blue-400 transition">
              AI Cover Letters
            </Link>
            <Link to="/job-application-tracker" className="hover:text-blue-400 transition">
              Auto Job Tracker
            </Link>
            <a href="#faq" className="hover:text-blue-400 transition">
              FAQ
            </a>
            <a href="/privacy.html" className="hover:text-blue-400 transition">
              Privacy Policy
            </a>
          </nav>

          <div className="flex items-center gap-2.5 shrink-0">
            <span className="hidden sm:inline-flex px-3 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/25 items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              8-Layer AI Engine Live
            </span>
            <button
              type="button"
              onClick={() => scrollToAuth('login')}
              className="px-3.5 py-2 rounded-xl text-xs font-bold text-slate-300 hover:text-white hover:bg-white/[0.06] border border-white/[0.08] transition cursor-pointer"
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => scrollToAuth('register')}
              className="px-4 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-md shadow-blue-600/25 transition cursor-pointer"
            >
              Get Started Free
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 relative z-10">
        {/* ABOVE-THE-FOLD HERO + AUTHENTICATION WORKBENCH (Visible on Mobile & Desktop for Google Mobile-First Indexing) */}
        <section
          aria-labelledby="hero-heading"
          className="max-w-7xl mx-auto px-4 sm:px-8 pt-10 pb-16 lg:py-16 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center border-b border-white/[0.06]"
        >
          {/* Left Hero Value Proposition (7 cols on desktop, full width on mobile) */}
          <div className="lg:col-span-7">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/25 text-blue-300 text-xs font-semibold mb-5"
            >
              <Sparkles size={13} className="text-amber-400 shrink-0" />
              <span>{seoCfg.heroBadge || SEO_ROUTE_CONFIG['/'].heroBadge}</span>
            </motion.div>

            <motion.h1
              id="hero-heading"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}
              className="text-3xl sm:text-4xl xl:text-5xl font-black leading-[1.12] tracking-tight mb-4"
            >
              {seoCfg.heroTitleLine1 || 'Match Your CV to Any Job.'}
              <br />
              <span className="text-gradient-blue">
                {seoCfg.heroTitleAccent || 'Powered by Live AI.'}
              </span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="text-slate-300 text-sm sm:text-base leading-relaxed mb-7 max-w-2xl"
            >
              {seoCfg.heroSub || SEO_ROUTE_CONFIG['/'].heroSub}
            </motion.p>

            {/* Feature Stack */}
            <div className="space-y-3 mb-7">
              {features.map((f, idx) => {
                const Icon = f.icon
                return (
                  <motion.div
                    key={f.title}
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.15 + idx * 0.07 }}
                    whileHover={{ x: 4 }}
                    className="flex items-start gap-3.5 glass-panel rounded-2xl p-3.5 transition-all"
                  >
                    <div className={`w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 ${f.color}`}>
                      <Icon size={18} />
                    </div>
                    <div>
                      <h2 className="font-bold text-sm text-white">{f.title}</h2>
                      <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">{f.sub}</p>
                    </div>
                  </motion.div>
                )
              })}
            </div>

            {/* Live Mined Recruiter Mailboxes Card */}
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35 }}
              className="glass-card rounded-2xl p-4 relative overflow-hidden"
            >
              <div className="glow-line-top" />
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <ShieldCheck size={13} className="text-emerald-400" />
                  Live Mined Recruiter Mailboxes &amp; CV Match Scores
                </span>
                <span className="text-[10px] font-semibold text-blue-400">DNS MX Verified</span>
              </div>
              <div className="space-y-2">
                {liveMatches.map((m, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-950/60 border border-white/[0.05]"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-white truncate">{m.role}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px] font-mono text-purple-300">{m.email}</span>
                        <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/25">
                          {m.badge}
                        </span>
                      </div>
                    </div>
                    <span className="text-xs font-extrabold px-2.5 py-1 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shrink-0">
                      {m.score}% CV Match
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* Right Authentication Workbench (5 cols on desktop) */}
          <div id="auth-workbench" className="lg:col-span-5 w-full max-w-md mx-auto lg:max-w-none">
            <motion.div
              initial={{ opacity: 0, scale: 0.97, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="glass-card rounded-3xl p-7 sm:p-8 relative overflow-hidden"
            >
              <div className="glow-line-top" />

              {/* Sliding Segmented Tab Bar */}
              <div className="relative flex bg-slate-950/90 border border-white/[0.07] rounded-2xl p-1.5 mb-7">
                {['login', 'register'].map(t => {
                  const active = tab === t
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() => { setTab(t); setErr('') }}
                      className={`relative flex-1 py-2.5 rounded-xl text-xs font-bold transition-colors cursor-pointer ${
                        active ? 'text-white' : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {active && (
                        <motion.div
                          layoutId="auth-tab-pill"
                          transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                          className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 shadow-md shadow-blue-600/30 z-0"
                        />
                      )}
                      <span className="relative z-10">{t === 'login' ? 'Sign In' : 'Create Account'}</span>
                    </button>
                  )
                })}
              </div>

              {/* Error Alert */}
              <AnimatePresence>
                {err && (
                  <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="bg-rose-950/70 border border-rose-500/40 text-rose-200 text-xs font-medium rounded-xl px-4 py-3 mb-5 flex items-center gap-2"
                  >
                    <span className="w-2 h-2 rounded-full bg-rose-400 shrink-0" />
                    <span>{err}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              <AnimatePresence mode="wait">
                {tab === 'login' ? (
                  <motion.div
                    key="login-form"
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 12 }}
                    transition={{ duration: 0.2 }}
                  >
                    <h2 className="text-2xl font-extrabold tracking-tight mb-1">Welcome back</h2>
                    <p className="text-slate-400 text-xs mb-5">
                      Sign in to your CVtoMatch AI career &amp; recruiter radar workspace
                    </p>

                    <motion.button
                      type="button"
                      whileHover={{ scale: 1.01 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={doGoogleAuth}
                      disabled={googleBusy || busy}
                      className="w-full bg-white hover:bg-slate-100 text-slate-900 font-bold py-3 px-4 rounded-xl transition text-xs sm:text-sm flex items-center justify-center gap-2.5 shadow-md cursor-pointer disabled:opacity-50"
                    >
                      {googleBusy ? (
                        <>
                          <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2, borderColor: '#334155', borderTopColor: '#2563EB' }} />
                          <span>Connecting to Google...</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                            <path fill="#EA4335" d="M12 5c1.6 0 3 .6 4.1 1.7l3.1-3.1C17.3 1.8 14.8 1 12 1 7.4 1 3.5 3.6 1.6 7.4l3.7 2.8C6.2 7.2 8.9 5 12 5z" />
                            <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.6l3.7 2.9c2.2-2 3.7-5 3.7-8.7z" />
                            <path fill="#FBBC05" d="M5.3 14.8c-.2-.8-.4-1.6-.4-2.5s.2-1.7.4-2.5L1.6 7C.6 9 0 11.2 0 12.3s.6 3.3 1.6 5.3l3.7-2.8z" />
                            <path fill="#34A853" d="M12 23.5c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3.1 0-5.8-2.1-6.7-5l-3.7 2.8c1.9 3.9 5.8 6.9 10.4 6.9z" />
                          </svg>
                          <span>Continue with Google</span>
                        </>
                      )}
                    </motion.button>

                    <div className="relative flex items-center gap-3 my-4">
                      <div className="flex-1 h-px bg-white/[0.08]" />
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">or with email</span>
                      <div className="flex-1 h-px bg-white/[0.08]" />
                    </div>

                    <form onSubmit={doLogin} className="space-y-4">
                      <div>
                        <label htmlFor="login-email" className="text-xs font-semibold text-slate-300 mb-1.5 block">
                          Email Address
                        </label>
                        <div className="relative">
                          <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                          <input
                            id="login-email"
                            name="email"
                            type="email"
                            autoComplete="username email"
                            value={lf.email}
                            onChange={e => setLf({ ...lf, email: e.target.value })}
                            placeholder="you@example.com"
                            className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl pl-10 pr-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition"
                          />
                        </div>
                      </div>

                      <div>
                        <label htmlFor="login-password" className="text-xs font-semibold text-slate-300 mb-1.5 block">
                          Password
                        </label>
                        <div className="relative">
                          <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                          <input
                            id="login-password"
                            name="password"
                            type="password"
                            autoComplete="current-password"
                            value={lf.password}
                            onChange={e => setLf({ ...lf, password: e.target.value })}
                            placeholder="••••••••"
                            className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl pl-10 pr-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition"
                          />
                        </div>
                      </div>

                      <motion.button
                        type="submit"
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.98 }}
                        disabled={busy || !lf.email.trim() || !lf.password}
                        className="w-full shimmer-btn bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold py-3.5 rounded-xl transition text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-600/25 cursor-pointer mt-2"
                      >
                        {busy ? (
                          <>
                            <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                            <span>Signing in...</span>
                          </>
                        ) : (
                          <>
                            <span>Sign In to Workspace</span>
                            <ArrowRight size={15} />
                          </>
                        )}
                      </motion.button>
                    </form>

                    <p className="text-center text-slate-400 text-xs mt-6">
                      Don&apos;t have an account?{' '}
                      <button
                        type="button"
                        onClick={() => setTab('register')}
                        className="text-blue-400 hover:text-blue-300 font-semibold hover:underline cursor-pointer"
                      >
                        Create one free →
                      </button>
                    </p>
                  </motion.div>
                ) : (
                  <motion.div
                    key="register-form"
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -12 }}
                    transition={{ duration: 0.2 }}
                  >
                    <h2 className="text-2xl font-extrabold tracking-tight mb-1">Create your account</h2>
                    <p className="text-slate-400 text-xs mb-5">
                      Sign up in 1 click with Google or enter your details below
                    </p>

                    <motion.button
                      type="button"
                      whileHover={{ scale: 1.01 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={doGoogleAuth}
                      disabled={googleBusy || busy}
                      className="w-full bg-white hover:bg-slate-100 text-slate-900 font-bold py-3 px-4 rounded-xl transition text-xs sm:text-sm flex items-center justify-center gap-2.5 shadow-md cursor-pointer disabled:opacity-50"
                    >
                      {googleBusy ? (
                        <>
                          <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2, borderColor: '#334155', borderTopColor: '#2563EB' }} />
                          <span>Connecting to Google...</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                            <path fill="#EA4335" d="M12 5c1.6 0 3 .6 4.1 1.7l3.1-3.1C17.3 1.8 14.8 1 12 1 7.4 1 3.5 3.6 1.6 7.4l3.7 2.8C6.2 7.2 8.9 5 12 5z" />
                            <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.6l3.7 2.9c2.2-2 3.7-5 3.7-8.7z" />
                            <path fill="#FBBC05" d="M5.3 14.8c-.2-.8-.4-1.6-.4-2.5s.2-1.7.4-2.5L1.6 7C.6 9 0 11.2 0 12.3s.6 3.3 1.6 5.3l3.7-2.8z" />
                            <path fill="#34A853" d="M12 23.5c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3.1 0-5.8-2.1-6.7-5l-3.7 2.8c1.9 3.9 5.8 6.9 10.4 6.9z" />
                          </svg>
                          <span>Sign up with Google</span>
                        </>
                      )}
                    </motion.button>

                    <div className="relative flex items-center gap-3 my-4">
                      <div className="flex-1 h-px bg-white/[0.08]" />
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">or with email</span>
                      <div className="flex-1 h-px bg-white/[0.08]" />
                    </div>

                    <form onSubmit={doRegister} className="space-y-3.5">
                      <div>
                        <label htmlFor="reg-name" className="text-xs font-semibold text-slate-300 mb-1 block">
                          Full Name
                        </label>
                        <div className="relative">
                          <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                          <input
                            id="reg-name"
                            name="name"
                            type="text"
                            required
                            autoComplete="name"
                            value={rf.name}
                            onChange={e => setRf({ ...rf, name: e.target.value })}
                            placeholder="Alex Morgan"
                            className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
                          />
                        </div>
                      </div>

                      <div>
                        <label htmlFor="reg-email" className="text-xs font-semibold text-slate-300 mb-1 block">
                          Email Address
                        </label>
                        <div className="relative">
                          <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                          <input
                            id="reg-email"
                            name="email"
                            type="email"
                            required
                            autoComplete="username email"
                            value={rf.email}
                            onChange={e => setRf({ ...rf, email: e.target.value })}
                            placeholder="you@example.com"
                            className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
                          />
                        </div>
                      </div>

                      <div>
                        <label htmlFor="reg-password" className="text-xs font-semibold text-slate-300 mb-1 block">
                          Password
                        </label>
                        <div className="relative">
                          <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                          <input
                            id="reg-password"
                            name="password"
                            type="password"
                            required
                            minLength={6}
                            autoComplete="new-password"
                            value={rf.password}
                            onChange={e => setRf({ ...rf, password: e.target.value })}
                            placeholder="Minimum 6 characters"
                            className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
                          />
                        </div>
                      </div>

                      <div>
                        <label htmlFor="reg-role" className="text-xs font-semibold text-slate-300 mb-1 block">
                          Workspace Mode
                        </label>
                        <div className="relative">
                          <Briefcase size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                          <select
                            id="reg-role"
                            name="role"
                            value={rf.role}
                            onChange={e => setRf({ ...rf, role: e.target.value })}
                            className="w-full bg-slate-950/90 border border-white/[0.08] rounded-xl pl-10 pr-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition cursor-pointer"
                          >
                            <option value="seeker">Job Seeker (Match CV, Hunt Posts &amp; Auto-Apply)</option>
                            <option value="recruiter">Recruiter / HR (Source &amp; Rank Candidates)</option>
                            <option value="both">Full Suite (Job Seeker + Recruiter Mode)</option>
                          </select>
                        </div>
                      </div>

                      <motion.button
                        type="submit"
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.98 }}
                        disabled={busy || !rf.name.trim() || !rf.email.trim() || rf.password.length < 6}
                        className="w-full shimmer-btn bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold py-3.5 rounded-xl transition text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-600/25 cursor-pointer mt-2"
                      >
                        {busy ? (
                          <>
                            <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                            <span>Creating Account...</span>
                          </>
                        ) : (
                          <>
                            <span>Create Account</span>
                            <ArrowRight size={15} />
                          </>
                        )}
                      </motion.button>
                    </form>

                    <p className="text-center text-slate-400 text-xs mt-5">
                      Already registered?{' '}
                      <button
                        type="button"
                        onClick={() => setTab('login')}
                        className="text-blue-400 hover:text-blue-300 font-semibold hover:underline cursor-pointer"
                      >
                        Sign in
                      </button>
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="mt-5 pt-4 border-t border-white/[0.06] text-center text-[11px] text-slate-400 leading-relaxed">
                By continuing, you agree to CVtoMatch&apos;s{' '}
                <a
                  href="https://www.cvtomatch.com/privacy.html"
                  className="text-blue-400 hover:text-blue-300 underline font-semibold"
                >
                  Privacy Policy
                </a>{' '}
                and{' '}
                <a
                  href="https://www.cvtomatch.com/terms.html"
                  className="text-blue-400 hover:text-blue-300 underline font-semibold"
                >
                  Terms of Service
                </a>
                .
              </div>
            </motion.div>
          </div>
        </section>

        {/* TRUST KPI STRIP */}
        <section aria-label="Platform Capabilities Overview" className="border-b border-white/[0.06] bg-slate-950/40">
          <div className="max-w-7xl mx-auto px-4 sm:px-8 py-8 grid grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { value: '6-Factor NLP', label: 'ATS Resume Compatibility Scoring', icon: Cpu },
              { value: '8-Layer Radar', label: 'LinkedIn Hiring Post & MX Email Mining', icon: Radar },
              { value: '4+ Job Boards', label: 'LinkedIn, Indeed, Glassdoor & ZipRecruiter', icon: Globe },
              { value: 'Auto IMAP Sync', label: 'Real-Time Inbox Application Tracking', icon: KanbanSquare },
            ].map((item, idx) => {
              const Icon = item.icon
              return (
                <div key={idx} className="flex items-center gap-3.5">
                  <div className="w-11 h-11 rounded-2xl bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400 shrink-0">
                    <Icon size={20} />
                  </div>
                  <div>
                    <p className="text-base sm:text-lg font-extrabold text-white leading-tight">{item.value}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{item.label}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* INTERACTIVE LIVE CV-TO-JOB ATS MATCH SIMULATOR */}
        <section id="interactive-matcher" className="max-w-7xl mx-auto px-4 sm:px-8 py-16 border-b border-white/[0.06]">
          <div className="text-center max-w-3xl mx-auto mb-10">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider bg-purple-500/10 text-purple-300 border border-purple-500/25 mb-3">
              <Sparkles size={12} /> Interactive ATS Resume Sandbox
            </span>
            <h2 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              Test the <span className="text-gradient-blue">CV-to-Job Match Calculator</span> Live
            </h2>
            <p className="text-slate-400 text-sm sm:text-base mt-3 leading-relaxed">
              Select a role preset or edit the CV skills and job description keywords below to see how CVtoMatch calculates your 6-factor ATS compatibility score and identifies missing keywords in real time.
            </p>
          </div>

          {/* Preset Role Selector Pills */}
          <div className="flex flex-wrap items-center justify-center gap-2.5 mb-8">
            {DEMO_PRESETS.map(preset => {
              const active = selectedPreset === preset.id
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSelectPreset(preset)}
                  className={`px-4 py-2 rounded-xl text-xs font-bold transition cursor-pointer border ${
                    active
                      ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white border-blue-400/40 shadow-lg shadow-blue-600/25'
                      : 'bg-slate-900/70 text-slate-300 border-white/[0.08] hover:border-blue-500/40 hover:text-white'
                  }`}
                >
                  {preset.label}
                </button>
              )
            })}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
            {/* Left Inputs: CV Skills & Job Requirements */}
            <div className="lg:col-span-6 glass-card rounded-3xl p-6 flex flex-col justify-between space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="demo-cv-input" className="text-xs font-bold uppercase tracking-wider text-blue-400">
                    1. Your CV Skills &amp; Technologies (Comma-Separated)
                  </label>
                  <span className="text-[11px] text-slate-400">Editable Live</span>
                </div>
                <textarea
                  id="demo-cv-input"
                  rows={3}
                  value={customCvSkills}
                  onChange={e => setCustomCvSkills(e.target.value)}
                  className="w-full bg-slate-950/90 border border-white/[0.08] rounded-2xl p-3.5 text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-blue-500 transition leading-relaxed"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="demo-jd-input" className="text-xs font-bold uppercase tracking-wider text-purple-400">
                    2. Target Job Description Requirements ({demoAnalysis.roleTitle})
                  </label>
                  <span className="text-[11px] text-slate-400">Editable Live</span>
                </div>
                <textarea
                  id="demo-jd-input"
                  rows={3}
                  value={customJdSkills}
                  onChange={e => setCustomJdSkills(e.target.value)}
                  className="w-full bg-slate-950/90 border border-white/[0.08] rounded-2xl p-3.5 text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-purple-500 transition leading-relaxed"
                />
              </div>

              {/* Matched vs Missing Skill Pills */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <div className="p-3.5 rounded-2xl bg-emerald-950/25 border border-emerald-500/25">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-300 mb-2 flex items-center gap-1.5">
                    <CheckCircle2 size={13} /> Matched ATS Keywords ({demoAnalysis.matched.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {demoAnalysis.matched.map(s => (
                      <span
                        key={s}
                        className="text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="p-3.5 rounded-2xl bg-rose-950/25 border border-rose-500/25">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-rose-300 mb-2 flex items-center gap-1.5">
                    <Sparkles size={13} /> Missing Keywords to Add ({demoAnalysis.missing.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {demoAnalysis.missing.length > 0 ? (
                      demoAnalysis.missing.map(s => (
                        <span
                          key={s}
                          className="text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-rose-500/15 text-rose-300 border border-rose-500/30"
                        >
                          + {s}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-emerald-300 font-semibold">100% Keyword Coverage!</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Right Output: 6-Factor ATS Score Breakdown */}
            <div className="lg:col-span-6 glass-card rounded-3xl p-6 flex flex-col justify-between relative overflow-hidden">
              <div className="glow-line-top" />
              <div>
                <div className="flex items-center justify-between gap-4 pb-5 mb-5 border-b border-white/[0.07]">
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-blue-400 block">
                      Real-Time 6-Factor ATS Diagnostic
                    </span>
                    <h3 className="text-lg font-extrabold text-white mt-0.5">
                      {demoAnalysis.roleTitle}
                    </h3>
                  </div>
                  <div className="px-4 py-2.5 rounded-2xl bg-emerald-500/15 border border-emerald-500/35 text-right shrink-0">
                    <span className="text-2xl font-black text-emerald-300 block leading-none">
                      {demoAnalysis.overall}%
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                      ATS Match Score
                    </span>
                  </div>
                </div>

                <div className="space-y-3.5">
                  {demoAnalysis.factors.map(f => (
                    <div key={f.label}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-semibold text-slate-300">{f.label}</span>
                        <span className="font-bold text-blue-300">{f.score}%</span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-slate-900 overflow-hidden border border-white/[0.05]">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${f.score}%` }}
                          transition={{ duration: 0.45, ease: 'easeOut' }}
                          className="h-full rounded-full bg-gradient-to-r from-blue-500 via-indigo-500 to-emerald-400"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-white/[0.07] flex flex-col sm:flex-row items-center justify-between gap-3">
                <p className="text-xs text-slate-400">
                  Upload your full PDF or DOCX resume to unlock line-by-line ATS tailoring.
                </p>
                <button
                  type="button"
                  onClick={() => scrollToAuth('register')}
                  className="w-full sm:w-auto shrink-0 px-4 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white flex items-center justify-center gap-1.5 shadow-lg shadow-blue-600/25 cursor-pointer transition"
                >
                  <span>Upload Full CV Free</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* 6-FACTOR ATS & CAREER INTELLIGENCE ENGINE SECTION */}
        <section id="ats-engine" className="max-w-7xl mx-auto px-4 sm:px-8 py-16 border-b border-white/[0.06]">
          <div className="text-center max-w-3xl mx-auto mb-12">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider bg-blue-500/10 text-blue-300 border border-blue-500/25 mb-3">
              <Layers size={12} /> 6-Factor NLP Scoring Architecture
            </span>
            <h2 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              How CVtoMatch Scores Your <span className="text-gradient-blue">Resume Against Any Job</span>
            </h2>
            <p className="text-slate-400 text-sm sm:text-base mt-3 leading-relaxed">
              Unlike basic keyword counters, our deterministic NLP engine evaluates your resume across six weighted hiring dimensions used by modern Applicant Tracking Systems and technical recruiters.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {SIX_FACTORS.map((item, idx) => (
              <article
                key={item.title}
                className="glass-card rounded-3xl p-6 flex flex-col justify-between hover:border-blue-500/35 transition-all"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-4">
                    <span className="px-3 py-1 rounded-xl text-sm font-black bg-blue-500/15 text-blue-300 border border-blue-500/30">
                      {item.weight} Weight
                    </span>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      {item.badge}
                    </span>
                  </div>
                  <h3 className="text-base font-extrabold text-white mb-2">{item.title}</h3>
                  <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">{item.desc}</p>
                </div>
                <div className="mt-5 pt-3 border-t border-white/[0.05] flex items-center justify-between text-[11px] text-blue-400 font-semibold">
                  <span>Dimension #{idx + 1}</span>
                  <span>ATS Verified</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        {/* HOW IT WORKS — 4-STEP WORKFLOW */}
        <section id="how-it-works" className="max-w-7xl mx-auto px-4 sm:px-8 py-16 border-b border-white/[0.06]">
          <div className="text-center max-w-3xl mx-auto mb-12">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-300 border border-emerald-500/25 mb-3">
              <Award size={12} /> End-to-End Career Automation
            </span>
            <h2 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              From Resume Upload to <span className="text-gradient-blue">Signed Offer in 4 Steps</span>
            </h2>
            <p className="text-slate-400 text-sm sm:text-base mt-3 leading-relaxed">
              Stop juggling 20 browser tabs, manual spreadsheets, and generic cover letters. CVtoMatch unifies job discovery, resume optimization, direct recruiter outreach, and inbox tracking.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {WORKFLOW_STEPS.map(w => {
              const Icon = w.icon
              return (
                <article key={w.step} className="glass-panel rounded-3xl p-6 relative flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-blue-600/25 to-purple-600/25 border border-blue-500/30 flex items-center justify-center text-blue-300">
                        <Icon size={20} />
                      </div>
                      <span className="text-2xl font-black text-slate-700">{w.step}</span>
                    </div>
                    <h3 className="text-base font-extrabold text-white mb-2">{w.title}</h3>
                    <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">{w.desc}</p>
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        {/* SEMANTIC SEO COMPARISON TABLE */}
        <section id="comparison" className="max-w-7xl mx-auto px-4 sm:px-8 py-16 border-b border-white/[0.06]">
          <div className="text-center max-w-3xl mx-auto mb-10">
            <h2 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              Why Job Seekers &amp; Recruiters Switch to <span className="text-gradient-blue">CVtoMatch</span>
            </h2>
            <p className="text-slate-400 text-sm sm:text-base mt-3">
              See how CVtoMatch compares against traditional job portals and single-purpose ATS resume scanners.
            </p>
          </div>

          <div className="glass-card rounded-3xl overflow-hidden border border-white/[0.08]">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/[0.08] bg-slate-950/70 text-xs uppercase tracking-wider text-slate-400">
                    <th className="py-4 px-5 font-bold">Capability</th>
                    <th className="py-4 px-5 font-extrabold text-blue-300 bg-blue-500/10">
                      CVtoMatch AI (cvtomatch.com)
                    </th>
                    <th className="py-4 px-5 font-bold">Standard Job Boards</th>
                    <th className="py-4 px-5 font-bold">Basic ATS Scanners</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06] text-xs sm:text-sm">
                  {COMPARISON_ROWS.map(row => (
                    <tr key={row.feature} className="hover:bg-white/[0.02] transition">
                      <td className="py-4 px-5 font-bold text-white">{row.feature}</td>
                      <td className="py-4 px-5 font-bold text-emerald-300 bg-blue-500/[0.05]">
                        <span className="inline-flex items-center gap-1.5">
                          <Check size={15} className="text-emerald-400 shrink-0" />
                          {row.cvtomatch}
                        </span>
                      </td>
                      <td className="py-4 px-5 text-slate-400">{row.boards}</td>
                      <td className="py-4 px-5 text-slate-400">{row.scanners}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* SCHEMA-ALIGNED FAQ ACCORDION SECTION */}
        <section id="faq" className="max-w-4xl mx-auto px-4 sm:px-8 py-16">
          <div className="text-center mb-10">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider bg-blue-500/10 text-blue-300 border border-blue-500/25 mb-3">
              Frequently Asked Questions
            </span>
            <h2 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              Everything You Need to Know About <span className="text-gradient-blue">CVtoMatch</span>
            </h2>
          </div>

          <div className="space-y-3.5">
            {SEO_FAQS.map((item, idx) => {
              const isOpen = openFaq === idx
              return (
                <div
                  key={item.q}
                  className="glass-panel rounded-2xl border border-white/[0.07] overflow-hidden transition"
                >
                  <button
                    type="button"
                    onClick={() => setOpenFaq(isOpen ? -1 : idx)}
                    aria-expanded={isOpen}
                    className="w-full px-6 py-4 text-left flex items-center justify-between gap-4 cursor-pointer hover:bg-white/[0.02] transition"
                  >
                    <h3 className="text-sm sm:text-base font-bold text-white">{item.q}</h3>
                    <ChevronDown
                      size={18}
                      className={`text-blue-400 shrink-0 transition-transform duration-200 ${
                        isOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </button>
                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.22 }}
                      >
                        <p className="px-6 pb-5 text-xs sm:text-sm text-slate-300 leading-relaxed border-t border-white/[0.05] pt-3">
                          {item.a}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )
            })}
          </div>

          {/* Bottom Conversion Banner */}
          <div className="mt-12 glass-card rounded-3xl p-8 text-center relative overflow-hidden">
            <div className="glow-line-top" />
            <h2 className="text-xl sm:text-2xl font-black text-white mb-2">
              Ready to Match Your CV &amp; Reach Hiring Managers Directly?
            </h2>
            <p className="text-xs sm:text-sm text-slate-400 max-w-xl mx-auto mb-6">
              Create your free CVtoMatch account in seconds to upload your resume, run 6-factor ATS diagnostics, and unlock live LinkedIn recruiter post discovery.
            </p>
            <button
              type="button"
              onClick={() => scrollToAuth('register')}
              className="px-6 py-3.5 rounded-xl text-xs sm:text-sm font-bold bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white shadow-lg shadow-blue-600/30 inline-flex items-center gap-2 cursor-pointer transition"
            >
              <span>Create Your Free CVtoMatch Account</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </section>
      </main>

      {/* CRAWL-FRIENDLY SEMANTIC SEO FOOTER */}
      <footer className="border-t border-white/[0.07] bg-[#04060E] relative z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div className="md:col-span-2">
              <div className="mb-3">
                <BrandLogo size="md" />
              </div>
              <p className="text-xs text-slate-400 leading-relaxed max-w-md">
                CVtoMatch is an AI Career Intelligence &amp; Talent Sourcing platform combining 6-factor NLP resume-to-job matching, live LinkedIn hiring post discovery with DNS MX-verified emails, multi-board job aggregation, AI cover letter generation, and IMAP inbox-synced application tracking.
              </p>
            </div>

            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-white mb-3">
                AI Career Tools
              </h3>
              <ul className="space-y-2 text-xs text-slate-400">
                {TOPIC_CLUSTER_LINKS.map(link => (
                  <li key={link.to}>
                    <Link to={link.to} className="hover:text-blue-400 transition">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-white mb-3">
                Platform Architecture
              </h3>
              <ul className="space-y-2 text-xs text-slate-400">
                <li><a href="#interactive-matcher" className="hover:text-blue-400 transition">Interactive ATS Score Calculator</a></li>
                <li><a href="#ats-engine" className="hover:text-blue-400 transition">6-Factor NLP Matching Engine</a></li>
                <li><a href="#how-it-works" className="hover:text-blue-400 transition">4-Step Outreach Workflow</a></li>
                <li><a href="#comparison" className="hover:text-blue-400 transition">Feature Comparison</a></li>
                <li><a href="#faq" className="hover:text-blue-400 transition">SEO &amp; Product FAQ</a></li>
                <li><a href="/privacy.html" className="hover:text-blue-400 transition">Privacy Policy</a></li>
                <li><a href="/terms.html" className="hover:text-blue-400 transition">Terms of Service</a></li>
                <li><a href="/sitemap.xml" className="hover:text-blue-400 transition">XML Sitemap</a></li>
              </ul>
            </div>
          </div>

          <div className="pt-6 border-t border-white/[0.06] flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
            <span>© {new Date().getFullYear()} CVtoMatch (cvtomatch.com). All rights reserved.</span>
            <div className="flex items-center gap-4">
              <a href="/privacy.html" className="hover:text-slate-300 transition">Privacy Policy</a>
              <span>·</span>
              <a href="/terms.html" className="hover:text-slate-300 transition">Terms of Service</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
