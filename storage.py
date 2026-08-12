import json
import logging
import os
from typing import Any, List, Optional, Set

logger = logging.getLogger(__name__)


def _load_json_list(filepath: str, description: str, missing_is_error: bool) -> Optional[List[Any]]:
    """
    Reads a JSON file that is expected to contain a list.

    Returns None when the file is missing, unreadable, or does not hold a list.
    """
    if not os.path.exists(filepath):
        message = f"{description} file not found: {filepath}"
        if missing_is_error:
            logger.error(message)
        else:
            logger.info(f"{message}. Starting fresh.")
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {filepath}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error reading {description.lower()} from {filepath}: {e}")
        return None

    if not isinstance(data, list):
        logger.warning(f"{description} file {filepath} must contain a JSON list.")
        return None

    return data


def load_keywords(filepath: str = "keywords.json") -> List[str]:
    """
    Loads the list of target job titles from a JSON file.

    Args:
        filepath: Path to the JSON file containing keywords.

    Returns:
        A list of job title strings. Returns an empty list if
        the file is missing, invalid, or cannot be read.
    """
    data = _load_json_list(filepath, "Keywords", missing_is_error=True)
    if data is None:
        return []

    # Ensure all keywords are strings and remove leading/trailing whitespace
    return [str(k).strip() for k in data]


def load_processed_jobs(filepath: str = "processed_jobs.json") -> Set[str]:
    """
    Loads the set of processed job_primary_id values.

    Args:
        filepath: Path to the JSON file containing processed job IDs.

    Returns:
        A set of string job IDs. Returns an empty set if the file
        is missing or invalid.
    """
    data = _load_json_list(filepath, "Processed jobs", missing_is_error=False)
    if data is None:
        return set()

    # Convert list to a set of strings for fast O(1) lookups
    return {str(item) for item in data}


def save_processed_jobs(filepath: str, processed_jobs: Set[str]) -> None:
    """
    Saves the set of processed job_primary_id values back to the JSON file.

    Args:
        filepath: Path to the JSON file where IDs will be saved.
        processed_jobs: The set of job IDs to save.
    """
    try:
        # Convert set back to a sorted list for clean, consistent JSON output
        data_to_save = sorted(processed_jobs)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=4)

        logger.info(f"Successfully saved {len(data_to_save)} processed jobs to {filepath}.")

    except Exception as e:
        logger.exception(f"Failed to save processed jobs to {filepath}: {e}")
