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
