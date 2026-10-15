import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const SITE_URL = 'https://www.cvtomatch.com'

export const SEO_ROUTE_CONFIG = {
  '/': {
    title: 'CVtoMatch — AI Resume to Job Matcher, ATS Checker & LinkedIn Recruiter Radar',
    description:
      'Match your CV to any job description in seconds with CVtoMatch’s 6-factor AI ATS Resume Matcher. Discover hidden LinkedIn hiring posts with verified recruiter emails, generate tailored cover letters, and auto-track job applications.',
    canonical: `${SITE_URL}/`,
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
    heroBadge: 'Bypass crowded job boards — match your CV & reach hiring managers directly',
    heroTitleLine1: 'Match Your CV to Any Job.',
    heroTitleAccent: 'Powered by Live AI.',
    heroSub:
      'Score your resume across 6 ATS dimensions, mine live LinkedIn recruiter posts with DNS MX-verified corporate emails, tailor cover letters in one click, and auto-sync application replies.',
  },
  '/ats-resume-checker': {
    title: 'Free AI ATS Resume Checker & CV to Job Match Calculator | CVtoMatch',
    description:
      'Check how well your CV matches any job description with our 6-factor NLP ATS Resume Checker. Analyze technical skills, TF-IDF keyword density, title alignment, and missing skills instantly.',
    canonical: `${SITE_URL}/ats-resume-checker`,
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
    heroBadge: '6-Factor Deterministic NLP & TF-IDF Resume Scoring Engine',
    heroTitleLine1: 'Instant AI ATS Resume Checker',
    heroTitleAccent: '& CV-to-Job Match Score.',
    heroSub:
      'Upload your PDF or DOCX resume and compare it against any job posting across Technical Skills, TF-IDF Keywords, Title Fit, Seniority, Must-Haves, and Soft Skills.',
  },
  '/linkedin-recruiter-posts': {
    title: 'LinkedIn Recruiter Post Finder & Direct Hiring Manager Email Radar | CVtoMatch',
    description:
      'Uncover hidden job opportunities announced directly by hiring managers and technical recruiters on LinkedIn. Extract DNS MX-verified corporate emails and apply before roles hit crowded job boards.',
    canonical: `${SITE_URL}/linkedin-recruiter-posts`,
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
    heroBadge: '8-Layer LinkedIn Hiring Post & DNS MX Email Verification Radar',
    heroTitleLine1: 'Mine Live LinkedIn Hiring Posts',
    heroTitleAccent: '& Verified Recruiter Emails.',
    heroSub:
      'Skip 500+ applicant portals. Discover real-time LinkedIn posts from hiring managers announcing open roles with verified direct corporate mailboxes.',
  },
  '/ai-cover-letter-generator': {
    title: 'AI Cover Letter Generator & Direct Recruiter Cold Email Studio | CVtoMatch',
    description:
      'Generate personalized, ATS-optimized cover letters and cold outreach emails tailored to your CV and target job description. Dispatch directly via SMTP with your resume attached.',
    canonical: `${SITE_URL}/ai-cover-letter-generator`,
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
    heroBadge: 'Role-Specific AI Cover Letters + Direct SMTP Cold Outreach',
    heroTitleLine1: 'Tailored AI Cover Letters',
    heroTitleAccent: '& 1-Click Recruiter Outreach.',
    heroSub:
      'Turn your CV and any job description into a high-conversion cover letter or direct hiring manager pitch, and send it straight from your mailbox with your PDF resume attached.',
  },
  '/job-application-tracker': {
    title: 'AI Job Application Tracker with Automatic IMAP Inbox Sync | CVtoMatch',
    description:
      'Organize every job application in an interactive Kanban board that automatically syncs with your email inbox via IMAP to detect interviews, offers, and ATS updates from Greenhouse, Lever, and Workday.',
    canonical: `${SITE_URL}/job-application-tracker`,
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
    heroBadge: 'Zero-Manual-Entry Kanban Pipeline with Smart IMAP Inbox Sync',
    heroTitleLine1: 'Track Every Job Application',
    heroTitleAccent: 'Automatically via Inbox Sync.',
    heroSub:
      'Stop updating spreadsheets manually. CVtoMatch scans incoming recruiter and ATS emails (Greenhouse, Lever, Workday, Ashby) to move applications across Applied, Interview, and Offer stages.',
  },
  '/recruiter-talent-sourcing': {
    title: 'AI Recruiter X-Ray Search & LinkedIn Candidate Matcher | CVtoMatch',
    description:
      'Source and rank public LinkedIn candidates automatically from any job description using multi-query X-Ray search and parallel 6-factor resume compatibility scoring.',
    canonical: `${SITE_URL}/recruiter-talent-sourcing`,
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
    heroBadge: 'Automated LinkedIn X-Ray Sourcing & Batch Candidate Ranking',
    heroTitleLine1: 'Source & Rank Top Talent',
    heroTitleAccent: 'From Any Job Description.',
    heroSub:
      'Generate targeted LinkedIn X-Ray queries from your job description, discover public candidate profiles, and rank every profile by skill coverage and seniority alignment.',
  },
  '/dashboard': {
    title: 'Workspace Dashboard | CVtoMatch AI',
    description: 'Your AI career intelligence and application pipeline command center on CVtoMatch.',
    canonical: `${SITE_URL}/dashboard`,
    robots: 'noindex, nofollow',
  },
  '/seeker': {
    title: 'Live LinkedIn Post Hunter & Multi-Board Job Search | CVtoMatch AI',
    description: 'Search live LinkedIn hiring posts and multi-board jobs with instant 6-factor CV match scoring.',
    canonical: `${SITE_URL}/seeker`,
    robots: 'noindex, nofollow',
  },
  '/tracker': {
    title: 'Application Pipeline & IMAP Mailbox Sync | CVtoMatch AI',
    description: 'Manage your Kanban job application pipeline with automated IMAP email status detection.',
    canonical: `${SITE_URL}/tracker`,
    robots: 'noindex, nofollow',
  },
  '/coverletter': {
    title: 'AI Cover Letter & Resume Tailoring Studio | CVtoMatch AI',
    description: 'Generate tailored cover letters and customized resumes for target job descriptions.',
    canonical: `${SITE_URL}/coverletter`,
    robots: 'noindex, nofollow',
  },
  '/cover-letter': {
    title: 'AI Cover Letter & Resume Tailoring Studio | CVtoMatch AI',
    description: 'Generate tailored cover letters and customized resumes for target job descriptions.',
    canonical: `${SITE_URL}/coverletter`,
    robots: 'noindex, nofollow',
  },
  '/email': {
    title: 'Direct Recruiter Outreach & Email History | CVtoMatch AI',
    description: 'View sent recruiter outreach emails, scheduled campaigns, and follow-ups.',
    canonical: `${SITE_URL}/email`,
    robots: 'noindex, nofollow',
  },
  '/recruiter': {
    title: 'Recruiter Talent X-Ray Search | CVtoMatch AI',
    description: 'Source and rank LinkedIn candidates using AI X-Ray search and skill matching.',
    canonical: `${SITE_URL}/recruiter`,
    robots: 'noindex, nofollow',
  },
  '/settings': {
    title: 'Account, SMTP & IMAP Settings | CVtoMatch AI',
    description: 'Configure your SMTP outreach credentials, IMAP inbox sync, and workspace profile.',
    canonical: `${SITE_URL}/settings`,
    robots: 'noindex, nofollow',
  },
}

function setMetaTag(attrName, attrValue, content) {
  if (!content) return
  let el = document.querySelector(`meta[${attrName}="${attrValue}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attrName, attrValue)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

export default function SEOHead() {
  const { pathname } = useLocation()

  useEffect(() => {
    const cleanPath = pathname === '/' ? '/' : pathname.replace(/\/+$/, '')
    const cfg = SEO_ROUTE_CONFIG[cleanPath] || SEO_ROUTE_CONFIG['/']

    document.title = cfg.title
    setMetaTag('name', 'title', cfg.title)
    setMetaTag('name', 'description', cfg.description)
    setMetaTag('name', 'robots', cfg.robots)

    setMetaTag('property', 'og:title', cfg.title)
    setMetaTag('property', 'og:description', cfg.description)
    setMetaTag('property', 'og:url', cfg.canonical)

    setMetaTag('name', 'twitter:title', cfg.title)
    setMetaTag('name', 'twitter:description', cfg.description)
    setMetaTag('name', 'twitter:url', cfg.canonical)

    let canonicalEl = document.querySelector('link[rel="canonical"]')
    if (!canonicalEl) {
      canonicalEl = document.createElement('link')
      canonicalEl.setAttribute('rel', 'canonical')
      document.head.appendChild(canonicalEl)
    }
    canonicalEl.setAttribute('href', cfg.canonical)

    // Track SPA route view + dedicated page tag in Google Analytics 4 (G-Q9TZ5QCLB0) & Microsoft Clarity
    try {
      const ROUTE_TAG_MAP = {
        '/': 'view_landing_home',
        '/ats-resume-checker': 'view_landing_ats_checker',
        '/linkedin-recruiter-posts': 'view_landing_linkedin_radar',
        '/ai-cover-letter-generator': 'view_landing_cover_letter',
        '/job-application-tracker': 'view_landing_job_tracker',
        '/recruiter-talent-sourcing': 'view_landing_recruiter_xray',
        '/dashboard': 'view_app_dashboard',
        '/seeker': 'view_app_opportunity_hunter',
        '/tracker': 'view_app_kanban_tracker',
        '/coverletter': 'view_app_cover_letter_studio',
        '/cover-letter': 'view_app_cover_letter_studio',
        '/email': 'view_app_email_outreach',
        '/recruiter': 'view_app_recruiter_xray',
        '/settings': 'view_app_settings',
      }
      const routeEventName = ROUTE_TAG_MAP[cleanPath] || 'view_page'

      if (typeof window.gtag === 'function') {
        window.gtag('config', 'G-Q9TZ5QCLB0', {
          page_path: cleanPath,
          page_title: cfg.title,
          page_location: window.location.href,
        })
        window.gtag('event', routeEventName, {
          page_path: cleanPath,
          page_title: cfg.title,
        })
      }
      if (typeof window.clarity === 'function') {
        window.clarity('set', 'page', cleanPath)
        window.clarity('event', routeEventName)
      }
    } catch {
      // Ignore analytics errors if blocked by browser extension
    }
  }, [pathname])

  return null
}

