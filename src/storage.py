import json
import logging
import os
from typing import List, Set

logger = logging.getLogger(__name__)

def load_keywords(filepath: str = "keywords.json") -> List[str]:
    """
    Loads the list of target job titles from a JSON file.
    
    Args:
        filepath: Path to the JSON file containing keywords.
        
    Returns:
        A list of job title strings. Returns an empty list if 
        the file is missing, invalid, or cannot be read.
    """
    if not os.path.exists(filepath):
        logger.error(f"Keywords file not found: {filepath}")
        return []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            keywords = json.load(f)
            if isinstance(keywords, list):
                # Ensure all keywords are strings and remove leading/trailing whitespace
                return [str(k).strip() for k in keywords]
            
            logger.warning(f"Keywords file {filepath} must contain a JSON list.")
            return []
            
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {filepath}: {e}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error reading keywords from {filepath}: {e}")
        return []

def load_processed_jobs(filepath: str = "processed_jobs.json") -> Set[str]:
    """
    Loads the set of processed job_primary_id values.
    
    Args:
        filepath: Path to the JSON file containing processed job IDs.
        
    Returns:
        A set of string job IDs. Returns an empty set if the file 
        is missing or invalid.
    """
    if not os.path.exists(filepath):
        logger.info(f"Processed jobs file not found at {filepath}. Starting fresh.")
        return set()
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # Convert list to a set of strings for fast O(1) lookups
                return set(str(item) for item in data)
            
            logger.warning(f"Processed jobs file {filepath} must contain a JSON list.")
            return set()
            
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {filepath}: {e}")
        return set()
    except Exception as e:
        logger.exception(f"Unexpected error reading processed jobs from {filepath}: {e}")
        return set()

def save_processed_jobs(filepath: str, processed_jobs: Set[str]) -> None:
    """
    Saves the set of processed job_primary_id values back to the JSON file.
    
    Args:
        filepath: Path to the JSON file where IDs will be saved.
        processed_jobs: The set of job IDs to save.
    """
    try:
        # Convert set back to a sorted list for clean, consistent JSON output
        data_to_save = sorted(list(processed_jobs))
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=4)
            
        logger.info(f"Successfully saved {len(data_to_save)} processed jobs to {filepath}.")
        
    except Exception as e:
        logger.exception(f"Failed to save processed jobs to {filepath}: {e}")