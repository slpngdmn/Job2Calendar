import re
from datetime import datetime
from typing import Any, Dict, List, Optional

PLACEHOLDER_VALUES = {"", "none", "null"}


def clean_str(value: Any, default: str = "") -> str:
    """
    Normalizes an arbitrary API value into a trimmed string.

    Returns `default` when the value is missing or is a placeholder such as
    "None"/"null" produced by upstream JSON payloads.
    """
    text = str(value).strip() if value is not None else ""
    if text.lower() in PLACEHOLDER_VALUES:
        return default
    return text


def extract_date(date_string: Any) -> Optional[datetime]:
    """
    Attempts to extract a valid YYYY-MM-DD date from a given string.
    """
    text = clean_str(date_string)
    if not text:
        return None

    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if not match:
        return None

    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d")
    except ValueError:
        return None


def iso_date_prefix(value: Any, default: str = "Unknown") -> str:
    """
    Extracts the YYYY-MM-DD prefix of an ISO timestamp
    (e.g., "2026-07-21T04:00:00.000Z" -> "2026-07-21").
    """
    text = clean_str(value)
    return text[:10] if len(text) >= 10 else default


def extract_list(payload: Any, *wrapper_keys: str) -> List[Any]:
    """
    Pulls a list out of an API response that may be a bare list or a mapping.

    Looks up each wrapper key in order and, if none of them hold a list,
    falls back to the first list value found in the mapping.
    """
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in wrapper_keys:
        value = payload.get(key)
        if isinstance(value, list) and value:
            return value

    for value in payload.values():
        if isinstance(value, list):
            return value

    return []


def first_int(value: Any) -> Optional[int]:
    """
    Returns the first integer found in a string (e.g., "3 posts" -> 3).
    """
    numbers = re.findall(r"\d+", clean_str(value))
    return int(numbers[0]) if numbers else None


def get_field(job: Dict[str, Any], key: str, default: str = "") -> str:
    """
    Reads a job field as a normalized string, falling back to `default`.
    """
    return clean_str(job.get(key), default)
