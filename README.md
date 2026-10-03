# 🚀 Job Searcher - AI-Powered Job Hunting Platform

![Banner](banner.jpg) *(Add your banner image here)*

**Job Searcher** is a complete, full-stack platform built to revolutionize how you find, track, and apply to jobs. By combining automated job board scraping, AI-powered CV matching, and a built-in email outreach system, it turns the exhausting process of job hunting into a streamlined, highly organized workflow.

Built by **Yassine Youssef**.

---

## ✨ Key Features

### 🔎 Multi-Source Job Search & Importer
- **Aggregated Search:** Search simultaneously across major job boards (LinkedIn, Indeed) with a single click.
- **Universal URL Importer:** Found a job on an obscure site or company careers page? Paste the URL! The backend uses `curl_cffi` to bypass Cloudflare/anti-bot protections, scraping the job details instantly.

### 🧠 AI CV Matching & Analysis
- **Smart Scoring:** Upload your CV (PDF, DOCX, TXT) and the app automatically matches your skills against every job description.
- **Skill Gap Analysis:** Instantly see your ✅ *Matched Skills* and ❌ *Skills to Develop* for every single role.

### 📧 Automated Email Outreach
- **Smart Email Extraction:** Employs 3 layers of logic (regex, scraper data, and domain inference) to find hidden recruiter emails.
- **Built-in Email Client:** Connect your Gmail via App Password.
- **Templates:** Send highly personalized emails (Application, Cold Outreach, Follow-Up, Thank You) directly from the app.
- **Confetti & Tracking:** Sending an email fires a success animation and automatically logs the application to your Tracker!

### 📋 Kanban Application Tracker
- A built-in drag-and-drop-style Kanban board to manage your pipeline: *Applied → Interview → Offer → Rejected → Accepted*.
- Logs full email history inside each application card.

### 📝 Cover Letter Generator
- Auto-generates tailored cover letters using your CV and the specific job description.
- Choose your tone: *Professional*, *Casual*, or *Technical*.

### 🎨 Premium UI/UX
- Built with **React** & **TailwindCSS**.
- Fluid, professional page transitions, staggered list entrances, and animated modals powered by **Framer Motion**.
- Toast notification system for non-intrusive feedback.

---

## 🛠️ Tech Stack

**Frontend:**
- React 18 (Vite)
- TailwindCSS
- Framer Motion (Animations)
- React Router (Routing)
- Axios (API Client)

**Backend:**
- Python 3
- FastAPI (High-performance API)
- SQLAlchemy (SQLite Database)
- JobSpy (Scraping Engine)
- `curl_cffi` (Advanced TLS Fingerprint Spoofing for URL imports)
- JWT Authentication

---

## 💻 Getting Started (Local Development)

### 1. Backend Setup
Open a terminal and navigate to the root folder:
```bash
# Install dependencies
pip install fastapi uvicorn sqlalchemy passlib bcrypt python-jose PyPDF2 pandas beautifulsoup4 curl_cffi

# Start the FastAPI server (runs on port 8000)
uvicorn web.backend.main:app --reload
```

### 2. Frontend Setup
Open a second terminal window:
```bash
# Navigate to the frontend directory
cd web/frontend

# Install dependencies
npm install

# Start the Vite development server
npm run dev
```

Visit `http://localhost:5173` in your browser.

---

## 🌐 Deployment (Free Hosting)

This repository includes configuration files for easy deployment:

1. **Frontend (Vercel):** Connect this repo to Vercel. Set the Root Directory to `web/frontend` and add your `VITE_API_URL` environment variable. The provided `vercel.json` handles React Router fallbacks automatically.
2. **Backend (Render):** Connect this repo to Render. The included `render.yaml` Blueprint will automatically detect the FastAPI app and provision a free web service.

---

## 🔒 Privacy & Security
- **Local First:** All your data (Jobs, CV, Applications) is stored securely in your local SQLite database.
- **Direct SMTP:** Emails are sent directly via Gmail's SMTP servers. Passwords are never sent to third parties.

---

*Transform your job search from a chore into a highly optimized machine.*
