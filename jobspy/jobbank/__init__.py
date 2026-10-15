from __future__ import annotations

import re
import time
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode, quote

from bs4 import BeautifulSoup
import requests

from jobspy.model import (
    JobPost,
    Location,
    JobResponse,
    JobType,
    Country,
    Compensation,
    CompensationInterval,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import create_logger

log = create_logger("JobBank")

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,10}")

class JobBank(Scraper):
    base_url = "https://www.jobbank.gc.ca"
    search_url = "https://www.jobbank.gc.ca/jobsearch/jobsearch"
    loader_url = "https://www.jobbank.gc.ca/jobsearch/job_search_loader.xhtml"

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        super().__init__(Site.JOB_BANK, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        ua = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        })
        if proxies:
            if isinstance(proxies, str):
                self.session.proxies = {"http": proxies, "https": proxies}
            elif isinstance(proxies, list) and proxies:
                self.session.proxies = {"http": proxies[0], "https": proxies[0]}
        if ca_cert:
            self.session.verify = ca_cert

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        log.info(f"Starting Job Bank Canada scrape for '{scraper_input.search_term}'...")
        params: Dict[str, Any] = {
            "searchstring": scraper_input.search_term or "",
            "sort": "M",  # Sort by most recent
        }
        if scraper_input.location:
            params["locationstring"] = scraper_input.location

        # Check international candidates filter
        is_intl_only = getattr(scraper_input, "international_only", False)
        if is_intl_only:
            # fglo=1: Filter for Canadian and International candidates (LMIA/foreign worker eligible)
            params["fglo"] = "1"

        # Hours old filter (Job Bank supports fage=2 for 48h, fage=30 for 30 days)
        if scraper_input.hours_old:
            if scraper_input.hours_old <= 48:
                params["fage"] = "2"
            elif scraper_input.hours_old <= 720:
                params["fage"] = "30"

        try:
            r = self.session.get(self.search_url, params=params, timeout=7)
            if r.status_code != 200:
                log.error(f"Search request failed with status {r.status_code}")
                return JobResponse(jobs=[])
        except Exception as e:
            log.error(f"Search request error: {e}")
            return JobResponse(jobs=[])

        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("article")
        log.info(f"Initial search returned {len(articles)} job postings")

        # Limit to max 18 per query to keep detail + AJAX enrichment under 2.5s
        target_results = min(scraper_input.results_wanted or 20, 18)
        articles = articles[:target_results]
        log.info(f"Harvested {len(articles)} job postings to enrich with full details & contact emails")

        # Enrich job details concurrently using pooled session
        jobs: List[JobPost] = []
        max_workers = min(12, len(articles)) if articles else 1

        ex = ThreadPoolExecutor(max_workers=max_workers)
        future_to_article = {
            ex.submit(self._parse_and_enrich_job, a, is_intl_only): a
            for a in articles
        }
        try:
            for future in as_completed(future_to_article, timeout=7.5):
                try:
                    job_post = future.result()
                    if job_post:
                        jobs.append(job_post)
                except Exception as e:
                    log.warning(f"Error enriching job post: {e}")
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

        log.info(f"Successfully scraped and enriched {len(jobs)} jobs from Job Bank Canada")
        return JobResponse(jobs=jobs)

    def _parse_and_enrich_job(self, article: BeautifulSoup, forced_intl: bool = False) -> Optional[JobPost]:
        try:
            # 1. Basic Listing Data
            raw_id = article.get("id", "")
            job_id = raw_id.replace("article-", "").strip() if raw_id else None

            title_elem = article.find("span", class_="noctitle") or article.find("h3", class_="title")
            title = title_elem.get_text(strip=True) if title_elem else "Job Posting"

            comp_elem = article.find("li", class_="business")
            company = comp_elem.get_text(strip=True) if comp_elem else "Job Bank Employer"

            loc_elem = article.find("li", class_="location")
            loc_raw = loc_elem.get_text(strip=True) if loc_elem else ""
            loc_clean = re.sub(r"^Location\s*", "", loc_raw).strip()

            city, state = None, None
            if "(" in loc_clean and ")" in loc_clean:
                m_loc = re.search(r"^(.*?)\s*\(([A-Za-z]{2})\)", loc_clean)
                if m_loc:
                    city = m_loc.group(1).strip()
                    state = m_loc.group(2).strip().upper()
                else:
                    city = loc_clean
            elif loc_clean:
                city = loc_clean

            location_obj = Location(
                city=city,
                state=state,
                country=Country.CANADA
            )

            # Salary extraction
            sal_elem = article.find("li", class_="salary")
            sal_raw = sal_elem.get_text(strip=True) if sal_elem else ""
            comp_obj = self._parse_compensation(sal_raw)

            # Date posted
            date_elem = article.find("li", class_="date")
            date_posted = None
            if date_elem:
                d_str = date_elem.get_text(strip=True)
                date_posted = self._parse_date(d_str)

            # Job URL
            a_link = article.find("a", href=True)
            rel_href = a_link.get("href", "") if a_link else ""
            if job_id:
                job_url = f"https://www.jobbank.gc.ca/jobsearch/jobposting/{job_id}"
            elif rel_href:
                clean_href = rel_href.split(";")[0].split("?")[0]
                job_url = f"https://www.jobbank.gc.ca{clean_href}"
            else:
                job_url = "https://www.jobbank.gc.ca/jobsearch"

            # 2. Detailed page fetch & application information
            description = ""
            emails: List[str] = []
            direct_apply_url = None
            is_intl_eligible = forced_intl
            is_remote_job = False
            easy_apply = False
            is_direct_apply = False
            job_types_list = [JobType.FULL_TIME]

            if job_id:
                det_url = f"https://www.jobbank.gc.ca/jobsearch/jobposting/{job_id}"
                thread_headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
                try:
                    r_det = self.session.get(det_url, headers=thread_headers, timeout=4.5)
                    if r_det.status_code == 200:
                        det_soup = BeautifulSoup(r_det.text, "html.parser")

                        # Remote/hybrid check
                        page_text_lower = det_soup.get_text().lower()
                        if "telework" in page_text_lower or "remote" in page_text_lower or "hybrid" in page_text_lower:
                            is_remote_job = True

                        # Job type check
                        if "part-time" in page_text_lower or "part time" in page_text_lower:
                            job_types_list = [JobType.PART_TIME]
                        elif "contract" in page_text_lower or "term or contract" in page_text_lower:
                            job_types_list = [JobType.CONTRACT]

                        # Check "Who can apply" eligibility section
                        who_can_apply_text = ""
                        for h in det_soup.find_all(["h2", "h3", "h4"]):
                            if "who can apply" in h.get_text(strip=True).lower():
                                parent = h.find_parent("div") or h.find_parent("section")
                                if parent:
                                    who_can_apply_text = parent.get_text(separator=" ", strip=True)
                                    break

                        if "other candidates" in who_can_apply_text.lower() or "without a valid" in who_can_apply_text.lower():
                            is_intl_eligible = True

                        # Requirements & description
                        jd_parts = []
                        req_div = det_soup.find("div", class_="job-posting-detail-requirements")
                        if req_div:
                            jd_parts.append(req_div.get_text(separator="\n", strip=True))
                        else:
                            main_sec = det_soup.find("section", id="job-posting-detail") or det_soup.find("main")
                            if main_sec:
                                jd_parts.append(main_sec.get_text(separator="\n", strip=True)[:3000])

                        # 3. How to Apply AJAX Extraction (Recruiter Emails hiding under 'Additional ways to apply')
                        payload = {
                            "jakarta.faces.partial.ajax": "true",
                            "jakarta.faces.source": "applynowbutton",
                            "jakarta.faces.partial.execute": "jobid",
                            "jakarta.faces.partial.render": "applynow markappliedgroup",
                            "jakarta.faces.behavior.event": "action",
                            "action": "applynowbutton",
                            "seekeractivity:jobid": job_id,
                            "seekeractivity_SUBMIT": "1",
                            "jakarta.faces.ViewState": "stateless",
                            "seekeractivity": "seekeractivity"
                        }
                        post_headers = {
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Faces-Request": "partial/ajax",
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": det_url,
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "Accept": "application/xml, text/xml, */*; q=0.01"
                        }
                        try:
                            r_hta = self.session.post(det_url, data=payload, headers=post_headers, timeout=4.5)
                            if r_hta.status_code == 200:
                                hta_cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", r_hta.text, re.DOTALL)
                                hta_raw = hta_cdata.group(1) if hta_cdata else r_hta.text
                                hta_soup = BeautifulSoup(hta_raw, "html.parser")

                                # Extract recruiter emails from mailto links
                                for a_tag in hta_soup.find_all("a", href=True):
                                    href = a_tag["href"]
                                    if href.startswith("mailto:"):
                                        em = href.replace("mailto:", "").split("?")[0].strip().lower()
                                        if "@" in em and em not in emails:
                                            emails.append(em)
                                    elif href.startswith("http") and "jobbank.gc.ca" not in href:
                                        if not direct_apply_url:
                                            direct_apply_url = href

                                # Regex search in HTA block (finds emails behind 'Additional ways to apply' accordion)
                                for em in EMAIL_REGEX.findall(hta_raw):
                                    em_clean = em.lower().strip()
                                    if em_clean not in emails and not any(em_clean.endswith(ext) for ext in [".png", ".jpg", ".css", ".js"]):
                                        emails.append(em_clean)

                                hta_details = hta_soup.find("details") or hta_soup.find("div", id="howtoapply")
                                if hta_details:
                                    instructions = hta_details.get_text(separator="\n", strip=True)
                                    jd_parts.append(f"\n### Additional ways to apply & Recruiter Instructions\n{instructions}")
                                    if "direct apply" in instructions.lower():
                                        easy_apply = True
                                        is_direct_apply = True

                                if emails:
                                    easy_apply = True
                        except Exception as e_hta:
                            log.debug(f"HTA extraction skipped for {job_id}: {e_hta}")

                        # Assemble description
                        base_desc = "\n\n".join(jd_parts)
                        if is_intl_eligible:
                            description = (
                                "### 🌐 International Candidate Eligibility\n"
                                "✅ **This employer accepts applications from Canadian citizens, permanent residents, "
                                "and international candidates (with or without a valid Canadian work permit / LMIA-eligible).**\n\n"
                                + base_desc
                            )
                        else:
                            description = base_desc
                except Exception as e_det:
                    log.debug(f"Detail fetch failed for {job_id}: {e_det}")

            if not description:
                description = f"{title} at {company} in {loc_clean}."

            return JobPost(
                id=job_id or str(hash(job_url)),
                title=title,
                company_name=company,
                job_url=job_url,
                job_url_direct=direct_apply_url,
                location=location_obj,
                description=description,
                compensation=comp_obj,
                date_posted=date_posted,
                emails=emails if emails else None,
                is_remote=is_remote_job,
                job_type=job_types_list,
                easy_apply=easy_apply,
                is_direct_apply=is_direct_apply,
                listing_type="Job Bank (Canada)",
                company_industry="International Candidates Accepted (LMIA)" if is_intl_eligible else "Canada Job Bank",
            )
        except Exception as e:
            log.warning(f"Error parsing job article: {e}")
            return None

    def _parse_compensation(self, sal_str: str) -> Optional[Compensation]:
        if not sal_str:
            return None
        cleaned = sal_str.replace("Salary", "").strip()
        interval = CompensationInterval.HOURLY
        if "annually" in cleaned or "yearly" in cleaned or "year" in cleaned:
            interval = CompensationInterval.YEARLY
        elif "monthly" in cleaned:
            interval = CompensationInterval.MONTHLY
        elif "weekly" in cleaned:
            interval = CompensationInterval.WEEKLY

        amounts = re.findall(r"\$([0-9,]+(?:\.[0-9]{2})?)", cleaned)
        if not amounts:
            return None
        try:
            nums = [float(a.replace(",", "")) for a in amounts]
            min_val = min(nums)
            max_val = max(nums) if len(nums) > 1 else min_val
            return Compensation(
                interval=interval,
                min_amount=min_val,
                max_amount=max_val,
                currency="CAD",
            )
        except Exception:
            return None

    def _parse_date(self, d_str: str) -> Optional[date]:
        if not d_str:
            return None
        cleaned = d_str.strip()
        formats = ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d/%m/%Y"]
        for fmt in formats:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.date()
            except ValueError:
                continue
        return None
