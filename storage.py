import json
import logging
import os
import tempfile
from typing import Any, List, Set

from errors import StorageError

logger = logging.getLogger(__name__)

def load_keywords(filepath: str = "keywords.json") -> List[str]:
    """
    Loads the list of target job titles from a JSON file.
    
    Args:
        filepath: Path to the JSON file containing keywords.
        
    Returns:
        A list of job title strings.
        
    Raises:
        StorageError: if the file is missing, unreadable, or does not contain a
            JSON list. A missing or broken keyword file is a configuration
            problem, so the run must fail instead of filtering nothing.
    """
    data = _load_json(filepath)
    
    if not isinstance(data, list):
        raise StorageError(
            f"Keywords file {filepath} must contain a JSON list, got {type(data).__name__}."
        )
        
    # Ensure all keywords are strings and remove leading/trailing whitespace
    return [str(k).strip() for k in data]

def load_processed_jobs(filepath: str = "processed_jobs.json") -> Set[str]:
    """
    Loads the set of processed job_primary_id values.
    
    Args:
        filepath: Path to the JSON file containing processed job IDs.
        
    Returns:
        A set of string job IDs. Returns an empty set only when the file does
        not exist yet (first run).
        
    Raises:
        StorageError: if the file exists but is unreadable or malformed.
            Treating that as "nothing processed yet" would re-add every job and
            overwrite the existing history.
    """
    if not os.path.exists(filepath):
        logger.info(f"Processed jobs file not found at {filepath}. Starting fresh.")
        return set()
        
    data = _load_json(filepath)
    
    if not isinstance(data, list):
        raise StorageError(
            f"Processed jobs file {filepath} must contain a JSON list, got {type(data).__name__}."
        )
        
    # Convert list to a set of strings for fast O(1) lookups
    return set(str(item) for item in data)

def save_processed_jobs(filepath: str, processed_jobs: Set[str]) -> None:
    """
    Saves the set of processed job_primary_id values back to the JSON file.
    
    Args:
        filepath: Path to the JSON file where IDs will be saved.
        processed_jobs: The set of job IDs to save.
        
    Raises:
        StorageError: if the file could not be written. The caller must know,
            because a lost write means the same jobs are processed again.
    """
    # Convert set back to a sorted list for clean, consistent JSON output
    data_to_save = sorted(processed_jobs)
    payload = json.dumps(data_to_save, indent=4)
    
    try:
        _write_atomically(filepath, payload)
    except OSError as e:
        raise StorageError(f"Failed to save processed jobs to {filepath}: {e}") from e
        
    logger.info(f"Successfully saved {len(data_to_save)} processed jobs to {filepath}.")

def _load_json(filepath: str) -> Any:
    """
    Reads and decodes a JSON file, converting failures into StorageError.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise StorageError(f"Required JSON file not found: {filepath}") from e
    except json.JSONDecodeError as e:
        raise StorageError(f"Error decoding JSON from {filepath}: {e}") from e
    except OSError as e:
        raise StorageError(f"Error reading {filepath}: {e}") from e

def _write_atomically(filepath: str, content: str) -> None:
    """
    Writes content to a temporary file in the same directory and renames it into
    place, so an interrupted run can never leave a truncated JSON file behind.
    """
    directory = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise