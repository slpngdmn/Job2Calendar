import logging
import time
from typing import Any, Dict, List
import requests

logger = logging.getLogger(__name__)

# Configurable constants for the API
BASE_API_URL = "https://alljobs.teletalk.com.bd/api/v1/published-jobs/search"
DEFAULT_LIMIT = 100
DEFAULT_ORG = 1
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

def fetch_all_jobs() -> List[Dict[str, Any]]:
    """
    Fetches all published jobs from the Teletalk API, handling pagination
    and flattening the nested organization structure.
    """
    all_jobs: List[Dict[str, Any]] = []
    page = 1
    
    logger.info("Starting to fetch jobs from Teletalk API...")
    
    while True:
        url = f"{BASE_API_URL}?page={page}&limit={DEFAULT_LIMIT}&org={DEFAULT_ORG}"
        logger.debug(f"Fetching API page {page}: {url}")
        
        response_data = _make_request_with_retry(url)
        
        if response_data is None:
            logger.error(f"Failed to fetch data for page {page}. Stopping pagination.")
            break
            
        current_page_jobs = []
        
        # Parse the specific nested structure of the Teletalk API
        if isinstance(response_data, dict) and "govtOrgJobs" in response_data:
            org_list = response_data.get("govtOrgJobs", [])
            
            if not org_list:
                logger.info(f"No more organizations found on page {page}. Pagination complete.")
                break
                
            for org in org_list:
                # Extract organization-level details
                org_name_bn = org.get("name_bn") or org.get("name") or "Unknown Organization"
                org_url = org.get("website") or "No URL provided"
                
                # Extract the YYYY-MM-DD portion
                created_date_raw = str(org.get("job_created_at", ""))[:10]
                
                for job in org.get("govt_jobs", []):
                    job_mapped = {
                        "job_primary_id": str(job.get("id", "")),
                        "job_title": str(job.get("job_title", "")),
                        "org_name_bn": org_name_bn,
                        "vacancy": "N/A",  
                        "published_date": created_date_raw if created_date_raw else "Unknown",
                        "deadline_date": created_date_raw if created_date_raw else "2026-12-31", 
                        "application_site_url": org_url
                    }
                    current_page_jobs.append(job_mapped)
                    
        elif isinstance(response_data, dict) and "data" in response_data:
            current_page_jobs = response_data.get("data", [])
        elif isinstance(response_data, list):
            current_page_jobs = response_data
            
        if not current_page_jobs:
            logger.info(f"No valid jobs could be extracted from page {page}. Stopping.")
            break
            
        all_jobs.extend(current_page_jobs)
        logger.info(f"Extracted {len(current_page_jobs)} jobs from page {page}.")
        
        if isinstance(response_data, dict) and "govtOrgJobs" in response_data:
            if len(response_data["govtOrgJobs"]) < DEFAULT_LIMIT:
                break
        
        page += 1
        time.sleep(1)
        
    logger.info(f"Successfully fetched and flattened a total of {len(all_jobs)} jobs.")
    return all_jobs

def _make_request_with_retry(url: str) -> Any:
    """
    Makes an HTTP GET request with built-in retry logic and browser headers.
    """
    # Masquerade as a standard Google Chrome browser so Teletalk doesn't block us
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status() 
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except ValueError as e:
            logger.error(f"Failed to parse JSON response from {url}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
            
        if attempt < MAX_RETRIES:
            logger.info(f"Waiting {RETRY_DELAY_SECONDS} seconds before retrying...")
            time.sleep(RETRY_DELAY_SECONDS)
            
    return None