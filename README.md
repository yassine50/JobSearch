<<<<<<< HEAD
<div align="center">

<img src="https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey?style=for-the-badge" />
<img src="https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge" />

# 🔍 Job Searcher
### *Smarter Hiring. Powered by AI.*

An all-in-one, AI-powered desktop application for **job seekers** and **recruiters** — combining intelligent job search, resume analysis, candidate sourcing, and automated outreach into a single, fully local tool.

> **Better Candidates. Bigger Opportunities.**

</div>

---

## ✨ Features at a Glance

| Feature | Description |
|---|---|
| 🤖 **AI-Powered Matching** | Scores CVs and candidates against job descriptions with a 6-factor engine |
| 👔 **Recruiter Mode** | Source candidates using advanced X-Ray search |
| 👤 **Job Seeker Mode** | Search multiple job boards simultaneously and find your best matches |
| 📧 **Email Automation** | Send personalized outreach emails with templates directly from the app |
| 📊 **Score Breakdown** | Visual breakdown of every match with actionable improvement tips |
| 📄 **CV Parsing** | Upload PDF, DOCX, or TXT resumes — text is extracted automatically |
| 📥 **CSV Export** | Export all search results to a CSV file for further analysis |

---

## 🚀 Getting Started

### Prerequisites

Make sure you have **Python 3.9+** installed. Then install the required libraries:

```bash
pip install pandas scikit-learn ddgs PyPDF2 python-docx jobspy
```

### Run the App

```bash
git clone https://github.com/your-username/job-searcher.git
cd job-searcher
python3 gui.py
```

No account, no API key, no cloud required. 100% local and private.

---

## 🧠 How It Works

### For Job Seekers — `👤 Job Seeker Mode`

1. **Configure your search** — Enter a job title, location, country, and select job boards
2. **Upload your CV** — The app parses your PDF or Word resume automatically
3. **Run the search** — Results appear in a ranked table with an AI match score for each job
4. **Click any match score** — A popup shows your strengths, gaps, and personalised tips

### For Recruiters — `👔 Recruiter Mode`

1. **Describe the role** — Enter a job title, location, and paste the full job description
2. **Add required skills** — Optionally specify must-have skills to sharpen the search
3. **Click Search Candidates** — The app runs multiple smart search queries in the background
4. **AI ranks all results** — Candidates are scored, sorted by fit, and colour-coded 🟢🟡🔴
5. **Click any score** — See a full breakdown and exactly which skills each candidate matches

---

## 🤖 The Matching Engine

A custom-built, dual-mode AI matching engine powers the app:

### Mode 1 — Full CV Matching (Job Seeker Tab)

| Factor | Weight | Description |
|---|---|---|
| ⚙️ Tech Skills | 40% | 400+ skill database, required skills ×2, frequency & section weighted |
| 📖 BM25 + TF-IDF | 30% | Ensemble of two retrieval models for semantic similarity |
| 🏷️ Role / Seniority | 15% | Title alignment + Junior / Senior level detection |
| 🤝 Soft Skills | 8% | Leadership, communication, agile mindset, etc. |
| 🏢 Domain Fit | 4% | Fintech, Healthtech, E-commerce, AI/ML industry detection |
| 🎓 Education | 3% | Bachelor, Master, PhD requirement comparison |

### Mode 2 — Snippet-Optimised Matching (Recruiter Tab)

Built specifically for short ~100-word LinkedIn profile snippets.

| Factor | Weight | Description |
|---|---|---|
| ⚙️ Skill Recall | 50% | % of JD skills found in headline + snippet (required ×2) |
| 🏷️ Title / Seniority | 25% | Headline vs job title + seniority gap detection |
| 🔑 Keyword Density | 15% | Jaccard recall of JD keywords in snippet |
| 📍 Location Match | 10% | Candidate city/country vs required location |
| 🟢 Open to Work | +5 pts | Bonus for candidates actively looking |

---

## 💡 Score Breakdown Popup

Click any **🎯 Match %** badge to open a detailed popup:

- Visual **score bars** for every factor
- **Matched skills** highlighted in green
- **Missing skills** in red — required skills starred ★
- **Warnings** for seniority, experience, and education gaps
- **Personalised tips** telling you exactly what to improve

---

## 📧 Email Automation

- Built-in email templates for job applications and recruiter outreach
- Auto-fills candidate name, job title, and company from search results
- Track emails sent and monitor response rates

---

## 🛠️ Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.9+ |
| GUI | Tkinter (custom themed) |
| AI / NLP | Custom BM25 + TF-IDF ensemble, Jaccard similarity |
| Candidate Search | DuckDuckGo X-Ray Search (DDGS) |
| Job Search | JobSpy (LinkedIn, Indeed, and more) |
| CV Parsing | PyPDF2, python-docx |
| Data | pandas |
| Performance | ThreadPoolExecutor (8 parallel threads) |
| ML | scikit-learn (TF-IDF, Cosine Similarity) |

---

## 📁 Project Structure

```
job-searcher/
├── gui.py          # Main UI — all tabs, panels, interactions
├── cv_matcher.py   # AI matching engine (CV + snippet modes)
├── run.py          # Entry point
├── jobspy/         # Job board search backend
└── README.md
```

---

## 🗺️ Roadmap

- [ ] 🌍 Multi-language support (French, Arabic)
- [ ] 🔔 Background job alerts and notifications
- [ ] 📊 Analytics dashboard (applications, response rates, pipeline)
- [ ] 🌐 Web version (FastAPI + React)
- [ ] 🔗 ATS export (Greenhouse, Lever, Workday)

---

## 👤 About the Developer

Built by **Yassine Youssef** — a software engineer passionate about building tools that solve real problems.

**What building this project taught me:**
- Advanced NLP & search algorithms (BM25, TF-IDF, Jaccard similarity)
- Multithreaded desktop app development — keeping UIs responsive under heavy computation
- Smart query engineering — multi-variant searches to maximise result recall
- Dual-user product design — serving job seekers and recruiters from one shared AI backend

---

## 📄 License

MIT License — free to use, modify, and share.

---

<div align="center">

**⭐ If this helped you, please give it a star on GitHub!**

Made with ❤️ and Python by Yassine Youssef

</div>
=======
💻 Developer Journey: Tech Stack & What You Learned
You can use this section in a blog post, on your GitHub README, or as a follow-up comment on your LinkedIn post to show off your technical skills.

🛠️ Technologies Used:

Language: Python
User Interface: Tkinter (Custom styled for a modern desktop experience)
Search & Scraping: DuckDuckGo Search (DDGS) for LinkedIn X-Ray searching
Matching Engine (AI/NLP): Custom implementation of BM25 & TF-IDF ensemble, Jaccard similarity, and Regex-based entity extraction.
File Parsing: PyPDF2 and python-docx for extracting text from resumes.
Performance: concurrent.futures.ThreadPoolExecutor for multithreaded processing.
🧠 What I Learned Building This Project:

Advanced Text Analysis & Search Algorithms: I learned how to move beyond basic keyword matching. I built a 6-factor matching engine that understands context (BM25 & TF-IDF), extracts required vs. preferred skills, and detects seniority levels.
Building Responsive Desktop GUIs: I mastered Python's Tkinter by creating a complex, multi-tabbed interface with custom themes, interactive Treeviews (tables), and scrollable pop-up windows that update dynamically without freezing the app.
Multithreading & Performance Optimization: Because analyzing dozens of candidate profiles or jobs takes time, I learned how to use Python's ThreadPoolExecutor to run the AI matching engine in the background. This keeps the user interface smooth and responsive while data processes in parallel.
Web Scraping & X-Ray Searching: I learned how to build smart, automated search queries (like combining job titles with specific skills) to bypass traditional job board limits and accurately scrape LinkedIn profiles using DuckDuckGo.
Handling Rate Limits & Edge Cases: I implemented backoff delays (time.sleep) and fallback query variations to ensure the app doesn't crash when search engines try to block automated traffic.
Dual-User Architecture: I learned how to design software that serves two distinct audiences (Job Seekers and Recruiters), sharing the same underlying backend engine while providing completely different user experiences.
>>>>>>> 923b7b7603da3875e1dc98eb5a2c910ab19ab9d1
