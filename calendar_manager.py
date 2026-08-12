import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from ics import Calendar, Event

from filter import normalize_keywords, title_matches_keywords

logger = logging.getLogger(__name__)

ICS_FILE_PATH = "jobs.ics"

# A job event is dropped once its deadline is this many days old.
RETENTION_DAYS = 1

UID_PREFIX = "teletalk-job-"
VACANCY_SUFFIX_RE = re.compile(r"\s*\(vacancy:(?P<vacancy>[^)]*)\)\s*$", re.IGNORECASE)


def extract_date(date_string: str) -> Optional[datetime]:
    """
    Attempts to extract a valid YYYY-MM-DD from a given date string.
    """
    if not date_string:
        return None

    match = re.search(r"\d{4}-\d{2}-\d{2}", str(date_string))
    if match:
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d")
        except ValueError:
            return None
    return None


def load_calendar() -> Calendar:
    """
    Loads the existing calendar from the local jobs.ics file.
    If the file doesn't exist or is corrupt, returns a new empty Calendar.
    """
    if os.path.exists(ICS_FILE_PATH):
        try:
            with open(ICS_FILE_PATH, "r", encoding="utf-8") as f:
                file_content = f.read()
                if file_content.strip():
                    return Calendar(file_content)
        except Exception as e:
            logger.error(f"Failed to load existing {ICS_FILE_PATH}: {e}. Starting fresh.")

    return Calendar()


def job_id_from_event(event: Event) -> Optional[str]:
    """
    Recovers the Teletalk job id encoded in an event UID.
    """
    uid = str(getattr(event, "uid", "") or "")
    if uid.startswith(UID_PREFIX):
        return uid[len(UID_PREFIX):].split("@", 1)[0] or None
    return None


def job_title_from_event(event: Event) -> str:
    """
    Returns the job title of an event without the trailing vacancy annotation.
    """
    name = str(getattr(event, "name", "") or "")
    return VACANCY_SUFFIX_RE.sub("", name).strip()


def vacancy_from_event(event: Event) -> Optional[int]:
    """
    Returns the vacancy count annotated in an event title, or None when unknown.
    """
    match = VACANCY_SUFFIX_RE.search(str(getattr(event, "name", "") or ""))
    if not match:
        return None

    numbers = re.findall(r"\d+", match.group("vacancy"))
    return int(numbers[0]) if numbers else None


def _event_date(event: Event) -> Optional[date]:
    begin = getattr(event, "begin", None)
    if begin is None:
        return None
    try:
        return begin.date()
    except AttributeError:
        return None


def purge_expired_events(calendar_obj: Calendar, today: Optional[date] = None) -> List[str]:
    """
    Removes events whose deadline is at least RETENTION_DAYS days old.

    Returns:
        The job ids of the removed events.
    """
    today = today or datetime.now().date()
    cutoff = today - timedelta(days=RETENTION_DAYS)

    removed: List[str] = []
    for event in list(calendar_obj.events):
        event_date = _event_date(event)
        if event_date is None or event_date > cutoff:
            continue

        calendar_obj.events.remove(event)
        job_id = job_id_from_event(event)
        if job_id:
            removed.append(job_id)
        logger.info(f"Removed expired job event ({event_date}): {event.name}")

    return removed


def purge_unmatched_events(calendar_obj: Calendar, keywords: Iterable[str]) -> List[str]:
    """
    Removes events whose job title no longer matches any configured keyword.

    Returns:
        The job ids of the removed events.
    """
    lower_keywords = normalize_keywords(keywords)
    if not lower_keywords:
        return []

    removed: List[str] = []
    for event in list(calendar_obj.events):
        title = job_title_from_event(event)
        if not title or title_matches_keywords(title, lower_keywords):
            continue

        calendar_obj.events.remove(event)
        job_id = job_id_from_event(event)
        if job_id:
            removed.append(job_id)
        logger.info(f"Removed job event not matching any keyword: {event.name}")

    return removed


def purge_low_vacancy_events(calendar_obj: Calendar, min_vacancy: int) -> List[str]:
    """
    Removes events for jobs with fewer than min_vacancy open positions.

    Returns:
        The job ids of the removed events.
    """
    removed: List[str] = []
    for event in list(calendar_obj.events):
        vacancy = vacancy_from_event(event)
        if vacancy is None or vacancy >= min_vacancy:
            continue

        calendar_obj.events.remove(event)
        job_id = job_id_from_event(event)
        if job_id:
            removed.append(job_id)
        logger.info(f"Removed job event with too few vacancies ({vacancy}): {event.name}")

    return removed


def save_calendar(calendar_obj: Calendar) -> None:
    """
    Saves the calendar object back to the local jobs.ics file.
    """
    try:
        with open(ICS_FILE_PATH, "w", encoding="utf-8") as f:
            f.writelines(calendar_obj.serialize_iter())

        logger.info(f"Successfully saved calendar updates to {ICS_FILE_PATH}.")
    except Exception as e:
        logger.exception(f"Failed to save calendar to {ICS_FILE_PATH}: {e}")


def existing_job_ids(calendar_obj: Calendar) -> Set[str]:
    """
    Returns the job ids currently present in the calendar.
    """
    return {job_id for job_id in (job_id_from_event(e) for e in calendar_obj.events) if job_id}


def create_job_event(job: Dict[str, Any], calendar_obj: Calendar) -> bool:
    """
    Creates an all-day calendar event for a specific job and adds it to the calendar.
    """
    job_primary_id = str(job.get("job_primary_id", "Unknown"))

    job_title = str(job.get("job_title", "Unknown Job Title")).strip()
    vacancy = str(job.get("vacancy", "N/A")).strip()
    org_name = str(job.get("org_name", "Unknown Organization")).strip()
    published_date = str(job.get("published_date", "Unknown")).strip()
    deadline_date_raw = str(job.get("deadline_date", "")).strip()
    application_site_url = str(job.get("application_site_url", "No URL provided")).strip()

    deadline_dt = extract_date(deadline_date_raw)
    if not deadline_dt:
        logger.error(
            f"Job {job_primary_id} has invalid/missing deadline date: {deadline_date_raw}. Cannot schedule."
        )
        return False

    title = f"{job_title} (Vacancy: {vacancy})"

    description = (
        f"Organization: {org_name}\n"
        f"Published: {published_date}\n"
        f"Deadline: {deadline_date_raw}\n"
        f"Application URL:\n{application_site_url}\n\n"
        f"Job Primary ID: {job_primary_id}"
    )

    event = Event()
    event.name = title
    event.description = description

    event.begin = deadline_dt.strftime("%Y-%m-%d")
    event.make_all_day()

    # Stable UID so re-runs update instead of duplicating the event.
    event.uid = f"{UID_PREFIX}{job_primary_id}@job2calendar"

    try:
        calendar_obj.events.add(event)
        logger.info(f"Added event for job: {title} (ID: {job_primary_id}) on {event.begin}")
        return True
    except Exception as e:
        logger.exception(f"Unexpected error adding event for job {job_primary_id}: {e}")
        return False
