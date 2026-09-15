from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

import pandas as pd

from jobspy.bayt import BaytScraper
from jobspy.bdjobs import BDJobs
from jobspy.glassdoor import Glassdoor
from jobspy.google import Google
from jobspy.indeed import Indeed
from jobspy.linkedin import LinkedIn
from jobspy.naukri import Naukri
from jobspy.model import JobType, Location, JobResponse, Country
from jobspy.model import SalarySource, ScraperInput, Site
from jobspy.util import (
    set_logger_level,
    extract_salary,
    create_logger,
    get_enum_from_value,
    map_str_to_site,
    convert_to_annual,
    desired_order,
)
from jobspy.ziprecruiter import ZipRecruiter


# Update the SCRAPER_MAPPING dictionary in the scrape_jobs function

def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    fetch_emails: bool = False,
    user_agent: str = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Scrapes job data from job boards concurrently
    :return: Pandas DataFrame containing job data
    """
    df, _ = scrape_jobs_with_status(
        site_name=site_name,
        search_term=search_term,
        google_search_term=google_search_term,
        location=location,
        distance=distance,
        is_remote=is_remote,
        job_type=job_type,
        easy_apply=easy_apply,
        results_wanted=results_wanted,
        country_indeed=country_indeed,
        proxies=proxies,
        ca_cert=ca_cert,
        description_format=description_format,
        linkedin_fetch_description=linkedin_fetch_description,
        linkedin_company_ids=linkedin_company_ids,
        offset=offset,
        hours_old=hours_old,
        enforce_annual_salary=enforce_annual_salary,
        verbose=verbose,
        fetch_emails=fetch_emails,
        user_agent=user_agent,
        **kwargs,
    )
    return df



def _extract_root_domain(url: str) -> str | None:
    """Extract the root domain URL from a full URL (e.g., https://careers.example.com/job/123 → https://example.com)."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.hostname:
            return None
        # Get the root domain (last 2 parts, or 3 for co.uk etc.)
        parts = parsed.hostname.split('.')
        if len(parts) >= 2:
            # Handle cases like co.uk, com.au
            if len(parts) >= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'ac', 'gov'):
                root = '.'.join(parts[-3:])
            else:
                root = '.'.join(parts[-2:])
            return f"https://{root}"
    except Exception:
        pass
    return None


def fetch_company_emails(url: str, follow_links: bool = True) -> set:
    """
    Fetch emails from a URL. Optionally follows 'contact', 'about', and similar
    sub-page links to find additional emails.
    """
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return set()
    skip_domains = ['linkedin.com', 'indeed.com', 'glassdoor.com', 'ziprecruiter.com',
                    'naukri.com', 'bayt.com', 'bdjobs.com', 'google.com']
    if any(d in url.lower() for d in skip_domains):
        return set()
    try:
        import requests
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, urlparse
        import urllib3
        from jobspy.util import extract_emails_from_text
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        all_emails = set()

        # Fetch the main page
        res = requests.get(url, headers=headers, timeout=8, verify=False, allow_redirects=True)
        if not res.ok:
            return set()

        soup = BeautifulSoup(res.text, "html.parser")
        page_text = soup.get_text(" ")
        found = extract_emails_from_text(page_text)
        if found:
            all_emails.update(found)

        # Also check mailto: links
        for mailto_link in soup.find_all("a", href=True):
            href = mailto_link["href"]
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if "@" in email and not any(email.endswith(ext) for ext in ('.png', '.jpg', '.gif')):
                    all_emails.add(email)

        # Follow sub-page links for contact/about pages
        if follow_links:
            contact_keywords = ['contact', 'about', 'about-us', 'contact-us', 'impressum', 'team', 'support']
            sub_urls = set()
            base_domain = urlparse(res.url).netloc  # Use final URL after redirects

            for link_tag in soup.find_all("a", href=True):
                href = link_tag["href"].lower().strip()
                full_url = urljoin(res.url, link_tag["href"])
                parsed_link = urlparse(full_url)

                # Only follow links on the same domain
                if parsed_link.netloc != base_domain:
                    continue

                path_lower = parsed_link.path.lower().rstrip("/")
                link_text = link_tag.get_text(strip=True).lower()

                if any(kw in path_lower or kw in link_text for kw in contact_keywords):
                    sub_urls.add(full_url)

                if len(sub_urls) >= 3:  # Limit to avoid slow scans
                    break

            for sub_url in sub_urls:
                try:
                    sub_res = requests.get(sub_url, headers=headers, timeout=6, verify=False, allow_redirects=True)
                    if sub_res.ok:
                        sub_soup = BeautifulSoup(sub_res.text, "html.parser")
                        sub_text = sub_soup.get_text(" ")
                        sub_found = extract_emails_from_text(sub_text)
                        if sub_found:
                            all_emails.update(sub_found)
                        # Check mailto: links on sub-pages too
                        for mailto_link in sub_soup.find_all("a", href=True):
                            href = mailto_link["href"]
                            if href.startswith("mailto:"):
                                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                                if "@" in email:
                                    all_emails.add(email)
                except Exception:
                    continue

        return all_emails
    except Exception:
        pass
    return set()


def _scrape_linkedin_company_page(company_url: str) -> tuple[str | None, set]:
    """
    Visits a LinkedIn company page to extract:
    - The real external company website
    - Any email addresses found on the page
    Returns (website_url, set_of_emails)
    """
    import re
    import json
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, parse_qs, unquote
    from jobspy.util import extract_emails_from_text

    found_website = None
    found_emails = set()

    # Use plain requests with follow redirects (TLS client breaks on LinkedIn redirects)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    # Only use the base company URL — /about/ requires login and redirects to login page
    base_url = company_url.rstrip('/')

    try:
        res = requests.get(base_url, headers=headers, timeout=10, allow_redirects=True)
        # If LinkedIn redirected us to login, abort
        if not res.ok or "linkedin.com/uas/login" in res.url or "authwall" in res.url:
            return None, set()

        soup = BeautifulSoup(res.text, "html.parser")

        # --- Strategy 1: Find <dt>Website</dt> then the link in the next <dd> ---
        # This is LinkedIn's standard structure for company details
        for dt in soup.find_all('dt'):
            if dt.get_text(strip=True).lower() == 'website':
                dd = dt.find_next_sibling('dd')
                if dd:
                    a_tag = dd.find('a', href=True)
                    if a_tag:
                        href = a_tag['href']
                        # LinkedIn wraps external links in a redirect URL
                        if 'linkedin.com/redir' in href:
                            parsed = urlparse(href)
                            qs = parse_qs(parsed.query)
                            if 'url' in qs:
                                found_website = unquote(qs['url'][0])
                        elif href.startswith('http') and 'linkedin.com' not in href:
                            found_website = href
                break

        # --- Strategy 2: Find link with data-tracking-control-name="about_website" ---
        if not found_website:
            for a in soup.find_all('a', href=True):
                tracking = a.get('data-tracking-control-name', '')
                if 'about_website' in tracking:
                    href = a['href']
                    if 'linkedin.com/redir' in href:
                        parsed = urlparse(href)
                        qs = parse_qs(parsed.query)
                        if 'url' in qs:
                            found_website = unquote(qs['url'][0])
                    elif href.startswith('http') and 'linkedin.com' not in href:
                        found_website = href
                    if found_website:
                        break

        # --- Strategy 3: JSON-LD structured data ---
        if not found_website:
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        url_val = item.get('url') or item.get('sameAs')
                        if url_val and isinstance(url_val, str) and 'linkedin.com' not in url_val:
                            found_website = url_val
                            break
                    if found_website:
                        break
                except Exception:
                    pass

        # --- Collect any emails from the page ---
        page_text = soup.get_text(' ')
        page_emails = extract_emails_from_text(page_text)
        if page_emails:
            found_emails.update(page_emails)

        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('mailto:'):
                email = href.replace('mailto:', '').split('?')[0].strip().lower()
                if '@' in email:
                    found_emails.add(email)

    except Exception:
        pass

    return found_website, found_emails




def scrape_jobs_with_status(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    fetch_emails: bool = False,
    user_agent: str = None,
    **kwargs,
) -> Tuple[pd.DataFrame, dict]:
    """
    Scrapes job data from job boards concurrently.
    Returns a tuple of (DataFrame, status_dict) where status_dict maps
    site names to {"status": "success"/"error", "message": str, "count": int}
    """
    SCRAPER_MAPPING = {
        Site.LINKEDIN: LinkedIn,
        Site.INDEED: Indeed,
        Site.ZIP_RECRUITER: ZipRecruiter,
        Site.GLASSDOOR: Glassdoor,
        Site.GOOGLE: Google,
        Site.BAYT: BaytScraper,
        Site.NAUKRI: Naukri,
        Site.BDJOBS: BDJobs,
    }
    set_logger_level(verbose)
    job_type = get_enum_from_value(job_type) if job_type else None

    def get_site_type():
        site_types = list(Site)
        if isinstance(site_name, str):
            site_types = [map_str_to_site(site_name)]
        elif isinstance(site_name, Site):
            site_types = [site_name]
        elif isinstance(site_name, list):
            site_types = [
                map_str_to_site(site) if isinstance(site, str) else site
                for site in site_name
            ]
        return site_types

    country_enum = Country.from_string(country_indeed)

    scraper_input = ScraperInput(
        site_type=get_site_type(),
        country=country_enum,
        search_term=search_term,
        google_search_term=google_search_term,
        location=location,
        distance=distance,
        is_remote=is_remote,
        job_type=job_type,
        easy_apply=easy_apply,
        description_format=description_format,
        linkedin_fetch_description=linkedin_fetch_description,
        results_wanted=results_wanted,
        linkedin_company_ids=linkedin_company_ids,
        offset=offset,
        hours_old=hours_old,
    )

    def scrape_site(site: Site) -> Tuple[str, JobResponse]:
        scraper_class = SCRAPER_MAPPING[site]
        scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        scraped_data: JobResponse = scraper.scrape(scraper_input)
        cap_name = site.value.capitalize()
        site_name = "ZipRecruiter" if cap_name == "Zip_recruiter" else cap_name
        site_name = "LinkedIn" if cap_name == "Linkedin" else cap_name
        create_logger(site_name).info(f"finished scraping")
        return site.value, scraped_data

    site_to_jobs_dict = {}
    site_statuses = {}

    def worker(site):
        site_val, scraped_info = scrape_site(site)
        return site_val, scraped_info

    with ThreadPoolExecutor() as executor:
        future_to_site = {
            executor.submit(worker, site): site for site in scraper_input.site_type
        }

        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                site_value, scraped_data = future.result()
                site_to_jobs_dict[site_value] = scraped_data
                job_count = len(scraped_data.jobs)
                if job_count > 0:
                    site_statuses[site.value] = {
                        "status": "success",
                        "message": f"Found {job_count} jobs",
                        "count": job_count,
                    }
                else:
                    site_statuses[site.value] = {
                        "status": "warning",
                        "message": "No jobs found (possibly blocked or no results)",
                        "count": 0,
                    }
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    error_msg = "Rate limited (429) — too many requests. Try using proxies."
                elif "403" in error_msg:
                    error_msg = "Forbidden (403) — blocked by the site. Try using proxies."
                site_statuses[site.value] = {
                    "status": "error",
                    "message": error_msg,
                    "count": 0,
                }
                create_logger(site.value).error(f"Scraper failed: {error_msg}")


    if fetch_emails:
        all_jobs = []
        for site, job_response in site_to_jobs_dict.items():
            all_jobs.extend(job_response.jobs)

        def scan_job(job):
            all_found_emails = set()
            if job.emails:
                all_found_emails.update(job.emails)

            # --- Step 1: Scrape LinkedIn company page for website + emails ---
            if job.company_url and "linkedin.com/company" in job.company_url:
                linkedin_website, linkedin_emails = _scrape_linkedin_company_page(job.company_url)
                if linkedin_emails:
                    all_found_emails.update(linkedin_emails)
                # Only set company_url_direct from LinkedIn if not already found via direct apply link
                if linkedin_website and not job.company_url_direct:
                    job.company_url_direct = linkedin_website

            # --- Step 2: External apply link (job_url_direct) ---
            if job.job_url_direct:
                if not job.company_url_direct:
                    root_domain = _extract_root_domain(job.job_url_direct)
                    if root_domain:
                        job.company_url_direct = root_domain
                # Scan external apply page for emails
                apply_emails = fetch_company_emails(job.job_url_direct, follow_links=False)
                if apply_emails:
                    all_found_emails.update(apply_emails)

            # --- Step 3: Scan the real company website (contact, about pages) ---
            if job.company_url_direct:
                from urllib.parse import urlparse
                # Avoid re-scanning LinkedIn
                if 'linkedin.com' not in job.company_url_direct:
                    website_emails = fetch_company_emails(job.company_url_direct, follow_links=True)
                    if website_emails:
                        all_found_emails.update(website_emails)

            if all_found_emails:
                job.emails = list(all_found_emails)

        with ThreadPoolExecutor(max_workers=10) as email_executor:
            list(email_executor.map(scan_job, all_jobs))

    jobs_dfs: list[pd.DataFrame] = []

    for site, job_response in site_to_jobs_dict.items():
        for job in job_response.jobs:
            job_data = job.dict()
            job_url = job_data["job_url"]
            job_data["site"] = site
            job_data["company"] = job_data["company_name"]
            job_data["job_type"] = (
                ", ".join(job_type.value[0] for job_type in job_data["job_type"])
                if job_data["job_type"]
                else None
            )
            job_data["emails"] = (
                ", ".join(job_data["emails"]) if job_data["emails"] else None
            )
            if job_data["location"]:
                job_data["location"] = Location(
                    **job_data["location"]
                ).display_location()

            # Handle compensation
            compensation_obj = job_data.get("compensation")
            if compensation_obj and isinstance(compensation_obj, dict):
                job_data["interval"] = (
                    compensation_obj.get("interval").value
                    if compensation_obj.get("interval")
                    else None
                )
                job_data["min_amount"] = compensation_obj.get("min_amount")
                job_data["max_amount"] = compensation_obj.get("max_amount")
                job_data["currency"] = compensation_obj.get("currency", "USD")
                job_data["salary_source"] = SalarySource.DIRECT_DATA.value
                if enforce_annual_salary and (
                    job_data["interval"]
                    and job_data["interval"] != "yearly"
                    and job_data["min_amount"]
                    and job_data["max_amount"]
                ):
                    convert_to_annual(job_data)
            else:
                if country_enum == Country.USA:
                    (
                        job_data["interval"],
                        job_data["min_amount"],
                        job_data["max_amount"],
                        job_data["currency"],
                    ) = extract_salary(
                        job_data["description"],
                        enforce_annual_salary=enforce_annual_salary,
                    )
                    job_data["salary_source"] = SalarySource.DESCRIPTION.value

            job_data["salary_source"] = (
                job_data["salary_source"]
                if "min_amount" in job_data and job_data["min_amount"]
                else None
            )

            #naukri-specific fields
            job_data["skills"] = (
                ", ".join(job_data["skills"]) if job_data["skills"] else None
            )
            job_data["experience_range"] = job_data.get("experience_range")
            job_data["company_rating"] = job_data.get("company_rating")
            job_data["company_reviews_count"] = job_data.get("company_reviews_count")
            job_data["vacancy_count"] = job_data.get("vacancy_count")
            job_data["work_from_home_type"] = job_data.get("work_from_home_type")

            job_df = pd.DataFrame([job_data])
            jobs_dfs.append(job_df)

    if jobs_dfs:
        # Step 1: Filter out all-NA columns from each DataFrame before concatenation
        filtered_dfs = [df.dropna(axis=1, how="all") for df in jobs_dfs]

        # Step 2: Concatenate the filtered DataFrames
        jobs_df = pd.concat(filtered_dfs, ignore_index=True)

        # Step 3: Ensure all desired columns are present, adding missing ones as empty
        for column in desired_order:
            if column not in jobs_df.columns:
                jobs_df[column] = None  # Add missing columns as empty

        # Reorder the DataFrame according to the desired order
        jobs_df = jobs_df[desired_order]

        # Step 4: Sort the DataFrame as required
        result_df = jobs_df.sort_values(
            by=["site", "date_posted"], ascending=[True, False]
        ).reset_index(drop=True)
        return result_df, site_statuses
    else:
        return pd.DataFrame(), site_statuses


# Add BDJobs to __all__
__all__ = [
    "BDJobs",
    "scrape_jobs",
    "scrape_jobs_with_status",
]