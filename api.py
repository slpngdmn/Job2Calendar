import logging
import time
from typing import Any, Dict, List, Set
import requests

from utils import clean_str, extract_list, iso_date_prefix

logger = logging.getLogger(__name__)

# Base API Endpoints
ORG_LIST_URL = "https://alljobs.teletalk.com.bd/api/v1/govt-jobs/org-list"
JOB_LIST_URL = "https://alljobs.teletalk.com.bd/api/v1/govt-jobs/list"
DEFAULT_APPLICATION_SITE = "https://alljobs.teletalk.com.bd"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3
REQUEST_INTERVAL_SECONDS = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

def fetch_all_jobs() -> List[Dict[str, Any]]:
    """
    Two-step job fetching process:
    1. Retrieves all active organization IDs from the org-list endpoint.
    2. Queries the detailed job list endpoint for each organization to extract 
       exact vacancy numbers, publication dates, application deadlines, and portal URLs.
    """
    logger.info("Starting two-step job fetching process from Teletalk API...")
    
    org_ids = _fetch_organization_ids()
    if not org_ids:
        logger.error("No organization IDs retrieved. Aborting job fetch.")
        return []
        
    logger.info(f"Found {len(org_ids)} unique organizations. Fetching detailed job lists...")
    
    all_jobs: List[Dict[str, Any]] = []
    
    for idx, org_id in enumerate(org_ids, start=1):
        url = f"{JOB_LIST_URL}?orgId={org_id}&skipLimit=YES"
        logger.debug(f"[{idx}/{len(org_ids)}] Fetching detailed jobs for orgId={org_id}...")
        
        jobs_data = _make_request_with_retry(url)
        
        if not jobs_data:
            continue
            
        raw_jobs = extract_list(jobs_data, "govt_jobs", "data")

        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
                
            # Extract organization info from the nested object
            org_info = job.get("job_utilities_govtorganization", {}) or {}
            org_name = clean_str(org_info.get("name"), "Unknown Organization")
            
            # Extract vacancy string
            vacancy_val = clean_str(job.get("vacancy"), "Not Specific")
            if job.get("vacancy_not_specific"):
                vacancy_val = "Not Specific"
                
            # Extract YYYY-MM-DD from ISO timestamp (e.g., "2026-07-21T04:00:00.000Z")
            pub_date = iso_date_prefix(job.get("published_date"))
            dl_date = iso_date_prefix(job.get("deadline_date"), default=pub_date)
            
            # Extract application site URL
            app_site = clean_str(
                job.get("application_site"),
                clean_str(org_info.get("website"), DEFAULT_APPLICATION_SITE),
            )
                
            job_mapped = {
                "job_primary_id": clean_str(job.get("id", job.get("job_id"))),
                "job_title": clean_str(job.get("job_title")),
                "org_name": org_name,
                "vacancy": vacancy_val,
                "published_date": pub_date,
                "deadline_date": dl_date,
                "application_site_url": app_site
            }
            
            all_jobs.append(job_mapped)
            
        # Brief pause between API calls to respect the server limits
        time.sleep(REQUEST_INTERVAL_SECONDS)
        
    logger.info(f"Successfully retrieved and mapped {len(all_jobs)} detailed jobs.")
    return all_jobs

def _fetch_organization_ids() -> List[int]:
    """
    Paginates through the org-list endpoint to gather all organization IDs.
    """
    org_ids_set: Set[int] = set()
    page = 1
    
    while True:
        url = f"{ORG_LIST_URL}?page={page}&limit=50"
        response_data = _make_request_with_retry(url)
        
        if not response_data:
            break
            
        org_list = extract_list(response_data, "govtOrgJobs", "data")

        if not org_list:
            break
            
        added_new = False
        for org in org_list:
            if isinstance(org, dict) and "id" in org:
                if org["id"] not in org_ids_set:
                    org_ids_set.add(org["id"])
                    added_new = True
                    
        # Stop paginating when we reach a page that yields zero new IDs 
        # (Handles cases where APIs repeatedly serve the last page on out-of-bounds requests)
        if not added_new:
            break
            
        page += 1
        time.sleep(REQUEST_INTERVAL_SECONDS)
        
    return list(org_ids_set)

def _make_request_with_retry(url: str) -> Any:
    """
    Makes an HTTP GET request with browser headers and retry logic.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status() 
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except ValueError as e:
            logger.error(f"Failed to parse JSON from {url}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
            
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS)
            
    return None