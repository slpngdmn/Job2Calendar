import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set
import requests

from errors import ApiError

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

@dataclass
class JobFetchResult:
    """Outcome of a fetch run, including organizations that could not be read."""

    jobs: List[Dict[str, Any]] = field(default_factory=list)
    failed_org_ids: List[int] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return bool(self.failed_org_ids)


def fetch_all_jobs() -> JobFetchResult:
    """
    Two-step job fetching process:
    1. Retrieves all active organization IDs from the org-list endpoint.
    2. Queries the detailed job list endpoint for each organization to extract 
       exact vacancy numbers, publication dates, application deadlines, and portal URLs.

    Raises:
        ApiError: if the organization list is unavailable, or every organization
            query failed and the run therefore produced no trustworthy data.
    """
    logger.info("Starting two-step job fetching process from Teletalk API...")
    
    org_ids = _fetch_organization_ids()
        
    logger.info(f"Found {len(org_ids)} unique organizations. Fetching detailed job lists...")
    
    all_jobs: List[Dict[str, Any]] = []
    failed_org_ids: List[int] = []
    
    for idx, org_id in enumerate(org_ids, start=1):
        url = f"{JOB_LIST_URL}?orgId={org_id}&skipLimit=YES"
        logger.debug(f"[{idx}/{len(org_ids)}] Fetching detailed jobs for orgId={org_id}...")
        
        try:
            jobs_data = _make_request_with_retry(url)
        except ApiError as e:
            logger.error(f"Giving up on orgId={org_id}: {e}")
            failed_org_ids.append(org_id)
            time.sleep(0.5)
            continue
            
        raw_jobs = []
        if isinstance(jobs_data, list):
            raw_jobs = jobs_data
        elif isinstance(jobs_data, dict):
            # Check for common wrapper keys
            raw_jobs = jobs_data.get("govt_jobs", jobs_data.get("data", []))
            
            # If not found, dynamically find the first array/list in the JSON response
            if not raw_jobs:
                for val in jobs_data.values():
                    if isinstance(val, list):
                        raw_jobs = val
                        break
        
        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
                
            # Extract organization info from the nested object
            org_info = job.get("job_utilities_govtorganization", {}) or {}
            org_name = org_info.get("name") or "Unknown Organization"
            
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
                "org_name": org_name,
                "vacancy": vacancy_val,
                "published_date": pub_date,
                "deadline_date": dl_date,
                "application_site_url": app_site
            }
            
            all_jobs.append(job_mapped)
            
        # Brief pause between API calls to respect the server limits
        time.sleep(0.5)
        
    if failed_org_ids and len(failed_org_ids) == len(org_ids):
        raise ApiError(
            f"All {len(org_ids)} organization job queries failed; no job data could be retrieved."
        )
        
    if failed_org_ids:
        logger.error(
            f"Job data is incomplete: {len(failed_org_ids)}/{len(org_ids)} organizations "
            f"failed after retries (orgIds: {failed_org_ids})."
        )
        
    logger.info(f"Successfully retrieved and mapped {len(all_jobs)} detailed jobs.")
    return JobFetchResult(jobs=all_jobs, failed_org_ids=failed_org_ids)

def _fetch_organization_ids() -> List[int]:
    """
    Paginates through the org-list endpoint to gather all organization IDs.

    Raises:
        ApiError: if a page request fails after retries, or if no IDs were found.
            A failing page is never treated as the end of the pagination, so a
            transport error can not silently truncate the organization list.
    """
    org_ids_set: Set[int] = set()
    page = 1
    
    while True:
        url = f"{ORG_LIST_URL}?page={page}&limit=50"
        try:
            response_data = _make_request_with_retry(url)
        except ApiError as e:
            raise ApiError(f"Organization list page {page} could not be fetched: {e}") from e
            
        org_list = []
        if isinstance(response_data, dict):
            org_list = response_data.get("govtOrgJobs", response_data.get("data", []))
            # Fallback: scan for list dynamically
            if not org_list:
                for val in response_data.values():
                    if isinstance(val, list):
                        org_list = val
                        break
        elif isinstance(response_data, list):
            org_list = response_data
            
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
        time.sleep(0.5)
        
    if not org_ids_set:
        raise ApiError("The organization list endpoint returned no organization IDs.")
        
    return list(org_ids_set)

def _make_request_with_retry(url: str) -> Any:
    """
    Makes an HTTP GET request with browser headers and retry logic.

    Returns:
        The decoded JSON body.

    Raises:
        ApiError: if every attempt failed. The last error is chained as the cause.
    """
    last_error: Exception = ApiError(f"No request attempt was made for {url}.")
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status() 
            return response.json()
            
        except requests.exceptions.Timeout as e:
            last_error = e
            logger.warning(f"Timeout on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.ConnectionError as e:
            last_error = e
            logger.warning(f"Connection error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.HTTPError as e:
            last_error = e
            logger.warning(f"HTTP error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Request error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except ValueError as e:
            # A malformed body will not become valid on a retry.
            raise ApiError(f"Failed to parse JSON from {url}: {e}") from e
            
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS)
            
    raise ApiError(f"Request to {url} failed after {MAX_RETRIES} attempts: {last_error}") from last_error