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
    Fetches all published jobs from the Teletalk API, handling pagination.
    
    Returns:
        A list of dictionaries containing job data. Returns an empty list 
        if the API fails or no jobs are found.
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
            
        # Parse the JSON response. Standard REST APIs usually wrap lists in a 'data' key,
        # but we also handle the case where the root is directly a list.
        current_page_jobs = []
        if isinstance(response_data, list):
            current_page_jobs = response_data
        elif isinstance(response_data, dict):
            # Commonly paginated APIs put the array in 'data'
            current_page_jobs = response_data.get("data", [])
        
        if not current_page_jobs:
            logger.info(f"No more jobs found on page {page}. Pagination complete.")
            break
            
        all_jobs.extend(current_page_jobs)
        logger.info(f"Retrieved {len(current_page_jobs)} jobs from page {page}.")
        
        page += 1
        # Brief pause to respect the API server rate limits
        time.sleep(1)
        
    logger.info(f"Successfully fetched a total of {len(all_jobs)} jobs.")
    return all_jobs

def _make_request_with_retry(url: str) -> Any:
    """
    Makes an HTTP GET request with built-in retry logic for transient errors.
    
    Args:
        url: The API endpoint URL to fetch.
        
    Returns:
        The parsed JSON payload (Dict or List), or None if all retries fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
        except ValueError as e:
            logger.error(f"Failed to parse JSON response from {url}: {e}")
            # If we get a bad JSON response, retrying might not help, but we still try
        except Exception as e:
            logger.exception(f"Unexpected error on attempt {attempt}/{MAX_RETRIES} for {url}: {e}")
            
        if attempt < MAX_RETRIES:
            logger.info(f"Waiting {RETRY_DELAY_SECONDS} seconds before retrying...")
            time.sleep(RETRY_DELAY_SECONDS)
            
    return None