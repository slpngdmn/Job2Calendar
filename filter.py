import logging
from typing import Any, Dict, List

from utils import clean_str

logger = logging.getLogger(__name__)

def filter_matching_jobs(jobs: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Filters a list of jobs based on a list of target keywords.
    A job is included if any keyword is found within its title (case-insensitive).
    
    Args:
        jobs: List of job dictionaries fetched from the Teletalk API.
        keywords: List of target job title strings (e.g., loaded from keywords.json).
        
    Returns:
        A list of job dictionaries that match the keyword criteria.
    """
    if not keywords:
        logger.warning("No keywords provided for filtering. Returning an empty list.")
        return []
        
    if not jobs:
        logger.warning("No jobs provided to filter.")
        return []

    filtered_jobs = []
    # Pre-compute lowercase keywords for efficiency
    lower_keywords = [kw.lower() for kw in keywords]
    
    for job in jobs:
        # Safely extract the job title, defaulting to empty string if the key is missing or None
        title_lower = clean_str(job.get("job_title")).lower()
        if not title_lower:
            continue
        
        # If any of our configured keywords are inside the job title, keep it
        if any(keyword in title_lower for keyword in lower_keywords):
            filtered_jobs.append(job)
            
    logger.info(f"Filtering complete: Kept {len(filtered_jobs)} out of {len(jobs)} total jobs.")
    
    return filtered_jobs