# CVtoMatch — AI Resume to Job Matcher, ATS Checker & LinkedIn Recruiter Radar

[![Live Website](https://img.shields.io/badge/Live_Website-cvtomatch.com-2563EB?style=for-the-badge&logo=vercel&logoColor=white)](https://www.cvtomatch.com)
[![Frontend](https://img.shields.io/badge/Frontend-React_18_%2B_Vite_%2B_Tailwind-4F46E5?style=for-the-badge&logo=react&logoColor=white)](https://react.dev)
[![Backend](https://img.shields.io/badge/Backend-FastAPI_%2B_SQLAlchemy-10B981?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/Author-Yassine_Youssef-9333EA?style=for-the-badge)](https://www.cvtomatch.com)

> **Live Platform:** [**https://www.cvtomatch.com**](https://www.cvtomatch.com)  
> **Built by:** **Yassine Youssef**

**CVtoMatch** (`cvtomatch.com`) is a full-stack **AI Career Intelligence & Talent Sourcing Platform** that unites **6-factor NLP resume-to-job matching**, **live LinkedIn hiring-post discovery with DNS MX-verified corporate emails**, **multi-board job aggregation**, **1-click AI cover letter & cold email dispatch**, and **automated IMAP inbox application tracking** in a unified command center.

---

## Core Architecture & Features

### 1. 6-Factor NLP & ATS Resume Matcher (`cv_matcher.py`)
Parses **PDF, DOCX, and TXT** resumes and evaluates compatibility against any target job description across six deterministic, weighted hiring dimensions:
- **Technical Skill Taxonomy Match (35%):** Cross-references programming languages, frameworks, cloud platforms, and domain competencies.
- **TF-IDF Keyword & Semantic Density (20%):** Computes cosine similarity and term-frequency weighting between your CV and the job posting.
- **Job Title & Functional Track Alignment (15%):** Evaluates role track relevance (Frontend, Backend, Full-Stack, AI/Data, DevOps, Product).
- **Seniority & Experience Calibration (10%):** Detects years-of-experience benchmarks and leadership levels (Junior, Mid, Senior, Staff, Lead).
- **Must-Have Requirement Coverage (10%):** Flags mandatory qualifications and non-negotiable tech stacks.
- **Leadership & Soft Skill Signals (10%):** Measures ownership, mentoring, and cross-functional impact indicators.

### 2. 8-Layer LinkedIn Hiring Post Hunter & Multi-Board Job Radar
- **LinkedIn Recruiter Post Hunter (`linkedin_post_hunter.py`):** Discovers "hidden market" opportunities where hiring managers, founders, and technical recruiters announce open roles directly on LinkedIn (`"We're hiring — send your CV to..."`), extracts corporate email addresses, and validates deliverability via **DNS MX record lookup**.
- **Concurrent Job Board Scraper (`jobspy`):** Aggregates live job postings simultaneously across **LinkedIn, Indeed, Glassdoor, and ZipRecruiter** with deep email extraction and time-window filtering.
- **Universal Job URL Importer:** Imports and parses external job postings using `curl_cffi` TLS fingerprint spoofing.

### 3. Kanban Application Tracker with Smart IMAP Inbox Sync
- **Interactive Pipeline (`/tracker`):** Manage applications across **Applied**, **Interview**, **Offer**, and **Rejected** stages with match scores, notes, and email logs.
- **Automated IMAP Mailbox Sync (`routers/tracker.py`):** Connects to your inbox via IMAP, scans incoming recruiter and ATS emails (**Greenhouse, Lever, Workday, Ashby, SmartRecruiters, BambooHR**), correlates sender domains and subject threads with your tracked companies, and automatically moves cards into **Interview**, **Offer**, or **Rejected** stages.

### 4. AI Cover Letter & Direct SMTP Outreach Studio
- **Role-Specific Cover Letters (`/coverletter`):** Generates tailored cover letters and customized resumes aligned with the target job description, with tone selection (*Professional*, *Casual*, *Technical*) and PDF export.
- **1-Click SMTP Cold Outreach (`/email`):** Sends personalized hiring manager pitches directly from your configured SMTP mailbox with your uploaded CV automatically attached, while logging the application to your Kanban tracker.

### 5. Recruiter Talent X-Ray Search
- **Automated Candidate Sourcing (`/recruiter`):** Generates multi-query LinkedIn X-Ray searches from a job description, discovers public candidate profiles, and ranks candidates in parallel using `batch_candidate_match` with skill-gap and seniority diagnostics.

### 6. Senior Technical SEO & Growth Architecture
- **JSON-LD Structured Data (`@graph`):** Rich Schema.org markup for `Organization`, `WebSite`, `SoftwareApplication`, and `FAQPage` in `web/frontend/index.html`.
- **Dynamic Topic-Cluster Landing Routes (`SEOHead.jsx`):** Dedicated, indexable landing URLs (`/`, `/ats-resume-checker`, `/linkedin-recruiter-posts`, `/ai-cover-letter-generator`, `/job-application-tracker`, `/recruiter-talent-sourcing`) backed by `public/sitemap.xml` and `public/robots.txt`.
- **Interactive ATS Match Sandbox:** Live in-browser 6-factor CV vs. Job Description simulator on the landing page.

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 18, Vite 5, Tailwind CSS, Framer Motion (spring physics & shared-layout animations), React Router v6, Lucide Icons, Axios |
| **Backend** | Python 3, FastAPI, SQLAlchemy ORM, SQLite, JWT Authentication (`python-jose`, `passlib[bcrypt]`) |
| **Scraping & Discovery** | Custom `JobSpy` multi-board engine (`requests`, `tls-client`, `curl_cffi`, `BeautifulSoup4`), DuckDuckGo X-Ray (`ddgs`), DNS MX Lookup (`dnspython`) |
| **NLP & Document Parsing** | Custom 6-factor TF-IDF & skill-taxonomy engine (`cv_matcher.py`), `PyPDF2`, `python-docx` |
| **Email & Inbox Automation** | Python `imaplib` (RFC-compliant ATS & recruiter email classifier), `smtplib` + `email.mime` |

---

## Project Structure

```text
JobSpy-main/
├── cv_matcher.py                  # 6-Factor NLP Resume-to-Job Matching & Batch Candidate Scoring Engine
├── jobspy/                        # Core multi-board job scraping library (LinkedIn, Indeed, Glassdoor, ZipRecruiter)
├── web/
│   ├── backend/
│   │   ├── main.py                # FastAPI application entrypoint & router registration
│   │   ├── database.py            # SQLAlchemy engine, session management & schema migrations
│   │   ├── models.py              # Database models (User, SavedJob, CvUpload, Application, EmailLog)
│   │   ├── auth.py                # JWT token creation, password hashing & route guards
│   │   ├── linkedin_post_hunter.py# 8-Layer LinkedIn recruiter post scraper & DNS MX email verifier
│   │   └── routers/               # Modular API routers (auth, jobs, linkedin_posts, cv, tracker, email, cover_letter, recruiter)
│   └── frontend/
│       ├── index.html             # SEO-optimized HTML shell with Open Graph & JSON-LD Schema.org @graph
│       ├── vercel.json            # Vercel SPA rewrites, security headers & sitemap/robots caching
│       ├── public/                # Static SEO assets (robots.txt, sitemap.xml, site.webmanifest, favicon.svg, og-banner.svg)
│       └── src/
│           ├── components/        # SEOHead, Sidebar, CommandPalette, ScoreDrawer, JobBoardScraper, LinkedInPostHunter, Modals
│           └── pages/             # Login (SEO Landing + Auth), Dashboard, Seeker, Tracker, CoverLetter, EmailHistory, Recruiter, Settings
└── README.md
```

---

## Local Development Setup

### 1. Start the FastAPI Backend
From the project root directory:

```bash
# Install backend dependencies
pip install -r web/backend/requirements.txt
pip install PyPDF2 python-docx pandas beautifulsoup4 curl_cffi ddgs dnspython

# Launch the FastAPI server on http://127.0.0.1:8000
python3 -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Start the React + Vite Frontend
Open a second terminal window:

```bash
cd web/frontend

# Install frontend packages
npm install

# Start Vite dev server on http://localhost:5173
npm run dev
```

---

## Production Deployment (`cvtomatch.com`)

1. **Frontend (Vercel — `https://www.cvtomatch.com`):**
   - Connect the repository to **Vercel** and set **Root Directory** to `web/frontend`.
   - `web/frontend/vercel.json` automatically configures SPA routing, security headers, `robots.txt`, and `sitemap.xml`.
   - Link custom domains `cvtomatch.com` (`A` record $\rightarrow$ `216.198.79.1`) and `www.cvtomatch.com` (`CNAME` $\rightarrow$ Vercel DNS).
2. **Backend (Render / Railway / Fly.io):**
   - Deploy `web/backend/main.py` with Uvicorn (`uvicorn web.backend.main:app --host 0.0.0.0 --port $PORT`) and set `VITE_API_URL` in your Vercel environment variables.

---

## Security & Privacy
- **Authenticated Workspaces:** Strict server-side and client-side authentication with bcrypt password hashing and signed JWTs.
- **Direct User-Controlled Mailboxes:** Outbound emails are dispatched directly through your configured SMTP server, and inbox status syncing connects directly via IMAP using your app password.
