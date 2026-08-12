import logging
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)


def normalize_keywords(keywords: Iterable[str]) -> List[str]:
    """
    Lowercases and drops empty keywords so matching is cheap and case-insensitive.
    """
    return [str(kw).strip().lower() for kw in keywords if str(kw).strip()]


def title_matches_keywords(title: str, lower_keywords: Iterable[str]) -> bool:
    """
    Returns True when any keyword appears inside the given title.
    """
    if not title:
        return False

    title_lower = str(title).lower()
    return any(keyword in title_lower for keyword in lower_keywords)


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
    lower_keywords = normalize_keywords(keywords or [])

    if not lower_keywords:
        logger.warning("No keywords provided for filtering. Returning an empty list.")
        return []

    if not jobs:
        logger.warning("No jobs provided to filter.")
        return []

    filtered_jobs = [
        job for job in jobs if title_matches_keywords(job.get("job_title"), lower_keywords)
    ]

    logger.info(f"Filtering complete: Kept {len(filtered_jobs)} out of {len(jobs)} total jobs.")

    return filtered_jobs
