import re

with open("jobspy/__init__.py", "r") as f:
    content = f.read()

# 1. Update scrape_jobs signature
content = content.replace(
    "enforce_annual_salary: bool = False,\n    verbose: int = 0,",
    "enforce_annual_salary: bool = False,\n    verbose: int = 0,\n    fetch_emails: bool = False,"
)

# 2. Update scrape_jobs_with_status call inside scrape_jobs
content = content.replace(
    "enforce_annual_salary=enforce_annual_salary,\n        verbose=verbose,",
    "enforce_annual_salary=enforce_annual_salary,\n        verbose=verbose,\n        fetch_emails=fetch_emails,"
)

# 3. Add helper function for fetching emails right before scrape_jobs_with_status
helper_func = """
def fetch_company_emails(url: str) -> set:
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return set()
    skip_domains = ['linkedin.com', 'indeed.com', 'glassdoor.com', 'ziprecruiter.com', 'naukri.com', 'bayt.com', 'bdjobs.com', 'google.com']
    if any(d in url.lower() for d in skip_domains):
        return set()
    try:
        import requests
        from bs4 import BeautifulSoup
        import urllib3
        from jobspy.util import extract_emails_from_text
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        if res.ok:
            text = BeautifulSoup(res.text, "html.parser").get_text(" ")
            found = extract_emails_from_text(text)
            if found:
                valid = set()
                for e in found:
                    if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css')):
                        valid.add(e.lower())
                return valid
    except Exception:
        pass
    return set()

"""

if "def fetch_company_emails" not in content:
    content = content.replace("def scrape_jobs_with_status(", helper_func + "def scrape_jobs_with_status(")


# 4. Inject the background scanning logic before jobs_dfs loop
scan_logic = """
    if fetch_emails:
        all_jobs = []
        for site, job_response in site_to_jobs_dict.items():
            all_jobs.extend(job_response.jobs)
            
        def scan_job(job):
            url_to_check = job.company_url_direct or job.company_url
            if url_to_check:
                web_emails = fetch_company_emails(url_to_check)
                if web_emails:
                    existing = set(job.emails) if job.emails else set()
                    existing.update(web_emails)
                    job.emails = list(existing)
                    
        with ThreadPoolExecutor(max_workers=10) as email_executor:
            list(email_executor.map(scan_job, all_jobs))

    jobs_dfs: list[pd.DataFrame] = []
"""

content = content.replace("    jobs_dfs: list[pd.DataFrame] = []\n", scan_logic)

with open("jobspy/__init__.py", "w") as f:
    f.write(content)

print("jobspy/__init__.py updated successfully.")
