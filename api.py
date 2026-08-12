import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Base API Endpoints
ORG_LIST_URL = "https://alljobs.teletalk.com.bd/api/v1/govt-jobs/org-list"
JOB_LIST_URL = "https://alljobs.teletalk.com.bd/api/v1/govt-jobs/list"

MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
MAX_WORKERS = 16
MAX_ORG_PAGES = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _build_session() -> requests.Session:
    """
    Creates a connection-pooled session with automatic retries and backoff.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    retry = Retry(
        total=MAX_RETRIES - 1,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=MAX_WORKERS,
        pool_maxsize=MAX_WORKERS,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _extract_list(payload: Any, *keys: str) -> List[Any]:
    """
    Pulls a list out of an API payload, trying known wrapper keys first and
    falling back to the first list value found.
    """
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list) and value:
                return value
        for value in payload.values():
            if isinstance(value, list) and value:
                return value

    return []


def fetch_all_jobs() -> List[Dict[str, Any]]:
    """
    Two-step job fetching process:
    1. Retrieves all active organization IDs from the org-list endpoint.
    2. Queries the detailed job list endpoint for every organization concurrently
       to extract vacancy numbers, publication dates, deadlines and portal URLs.
    """
    logger.info("Starting two-step job fetching process from Teletalk API...")

    with _build_session() as session:
        org_ids = _fetch_organization_ids(session)
        if not org_ids:
            logger.error("No organization IDs retrieved. Aborting job fetch.")
            return []

        logger.info(f"Found {len(org_ids)} unique organizations. Fetching detailed job lists...")

        all_jobs: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = executor.map(lambda org_id: _fetch_org_jobs(session, org_id), org_ids)

            for jobs in results:
                for job in jobs:
                    job_id = job["job_primary_id"]
                    if job_id and job_id in seen_ids:
                        continue
                    if job_id:
                        seen_ids.add(job_id)
                    all_jobs.append(job)

    logger.info(f"Successfully retrieved and mapped {len(all_jobs)} detailed jobs.")
    return all_jobs


def _fetch_org_jobs(session: requests.Session, org_id: Any) -> List[Dict[str, Any]]:
    """
    Fetches and normalizes every job published by a single organization.
    """
    url = f"{JOB_LIST_URL}?orgId={org_id}&skipLimit=YES"
    jobs_data = _make_request(session, url)
    raw_jobs = _extract_list(jobs_data, "govt_jobs", "data")

    mapped: List[Dict[str, Any]] = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue

        org_info = job.get("job_utilities_govtorganization") or {}
        if not isinstance(org_info, dict):
            org_info = {}
        org_name = org_info.get("name") or "Unknown Organization"

        vacancy_val = str(job.get("vacancy", "")).strip()
        if not vacancy_val or vacancy_val.lower() == "none" or job.get("vacancy_not_specific"):
            vacancy_val = "Not Specific"

        # Extract YYYY-MM-DD from ISO timestamp (e.g., "2026-07-21T04:00:00.000Z")
        pub_date_raw = str(job.get("published_date") or "")
        pub_date = pub_date_raw[:10] if len(pub_date_raw) >= 10 else "Unknown"

        dl_date_raw = str(job.get("deadline_date") or "")
        dl_date = dl_date_raw[:10] if len(dl_date_raw) >= 10 else pub_date

        app_site = str(job.get("application_site") or "").strip()
        if not app_site or app_site.lower() == "none":
            app_site = str(org_info.get("website") or "https://alljobs.teletalk.com.bd").strip()

        mapped.append(
            {
                "job_primary_id": str(job.get("id") or job.get("job_id") or ""),
                "job_title": str(job.get("job_title") or "").strip(),
                "org_name": org_name,
                "vacancy": vacancy_val,
                "published_date": pub_date,
                "deadline_date": dl_date,
                "application_site_url": app_site,
            }
        )

    return mapped


def _fetch_organization_ids(session: requests.Session) -> List[int]:
    """
    Paginates through the org-list endpoint to gather all organization IDs.
    """
    org_ids: List[int] = []
    seen: Set[int] = set()

    for page in range(1, MAX_ORG_PAGES + 1):
        url = f"{ORG_LIST_URL}?page={page}&limit=50"
        response_data = _make_request(session, url)
        org_list = _extract_list(response_data, "govtOrgJobs", "data")

        if not org_list:
            break

        added_new = False
        for org in org_list:
            if isinstance(org, dict) and "id" in org and org["id"] not in seen:
                seen.add(org["id"])
                org_ids.append(org["id"])
                added_new = True

        # Stop paginating when a page yields zero new IDs
        # (some APIs repeatedly serve the last page for out-of-bounds requests)
        if not added_new:
            break

    return org_ids


def _make_request(session: requests.Session, url: str) -> Optional[Any]:
    """
    Makes an HTTP GET request, returning the decoded JSON body or None.
    """
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except ValueError as e:
        logger.error(f"Failed to parse JSON from {url}: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error for {url}: {e}")

    return None
