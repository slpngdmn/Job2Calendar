import logging
import time
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

# Base API Endpoints
ORG_LIST_URL = "https://alljobs.teletalk.com.bd/api/v1/govt-jobs/org-list"
JOB_LIST_URL = "https://alljobs.teletalk.com.bd/api/v1/govt-jobs/list"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3

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
        
    logger.info(f"Found {len(org_ids)} organizations. Fetching detailed job lists...")
    
    all_jobs: List[Dict[str, Any]] = []
    
    for idx, org_id in enumerate(org_ids, start=1):
        url = f"{JOB_LIST_URL}?orgId={org_id}&skipLimit=YES"
        logger.debug(f"[{idx}/{len(org_ids)}] Fetching detailed jobs for orgId={org_id}...")
        
        jobs_data = _make_request_with_retry(url)
        
        if not jobs_data:
            continue
            
        raw_jobs = jobs_data if isinstance(jobs_data, list) else jobs_data.get("data", [])
        
        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
                
            # Extract organization info from the nested object
            org_info = job.get("job_utilities_govtorganization", {}) or {}
            org_name_bn = org_info.get("name_bn") or org_info.get("name") or "Unknown Organization"
            
            # Extract vacancy string
            vacancy_val = str(job.get("vacancy", "")).strip()
            if not vacancy_val or vacancy_val.lower() == "none" or job.get("vacancy_not_specific"):
                vacancy_val = "Not Specific"
                
            # Extract YYYY-MM-DD from ISO timestamp (e.g., "2026-07-21T04:00:00.000Z")
            pub_date_raw = str(job.get("published_date", ""))
            pub_date = pub_date_raw[:10] if len(pub_date_raw) >= 10 else "Unknown"
            
            dl_date_raw = str(job.get("deadline_date", ""))
            dl_date = dl_date_raw[:10] if len(dl_date_raw) >= 10 else pub_date
            
            # Extract application site URL
            app_site = str(job.get("application_site", "")).strip()
            if not app_site or app_site.lower() == "none":
                app_site = str(org_info.get("website", "https://alljobs.teletalk.com.bd")).strip()
                
            job_mapped = {
                "job_primary_id": str(job.get("id", job.get("job_id", ""))),
                "job_title": str(job.get("job_title", "")).strip(),
                "org_name_bn": org_name_bn,
                "vacancy": vacancy_val,
                "published_date": pub_date,
                "deadline_date": dl_date,
                "application_site_url": app_site
            }
            
            all_jobs.append(job_mapped)
            
        # Brief pause between API calls to respect the server limits
        time.sleep(0.3)
        
    logger.info(f"Successfully retrieved and mapped {len(all_jobs)} detailed jobs.")
    return all_jobs

def _fetch_organization_ids() -> List[int]:
    """
    Paginates through the org-list endpoint to gather all organization IDs.
    """
    org_ids: List[int] = []
    page = 1
    limit = 50
    
    while True:
        url = f"{ORG_LIST_URL}?page={page}&limit={limit}"
        response_data = _make_request_with_retry(url)
        
        if not response_data:
            break
            
        org_list = []
        if isinstance(response_data, dict):
            org_list = response_data.get("govtOrgJobs", response_data.get("data", []))
        elif isinstance(response_data, list):
            org_list = response_data
            
        if not org_list:
            break
            
        for org in org_list:
            if isinstance(org, dict) and "id" in org:
                org_ids.append(org["id"])
                
        if len(org_list) < limit:
            break
            
        page += 1
        time.sleep(0.3)
        
    return org_ids

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