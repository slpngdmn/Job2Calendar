import logging
import os
import re
import tempfile
from datetime import datetime, timedelta  # <-- timedelta যুক্ত করা হয়েছে
from typing import Any, Dict, Optional

from ics import Calendar, Event

from errors import CalendarError

logger = logging.getLogger(__name__)

ICS_FILE_PATH = "jobs.ics"

def extract_date(date_string: str) -> Optional[datetime]:
    """
    Attempts to extract a valid YYYY-MM-DD from a given date string.
    """
    if not date_string:
        return None
        
    match = re.search(r'\d{4}-\d{2}-\d{2}', str(date_string))
    if match:
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d")
        except ValueError:
            return None
    return None

def load_calendar() -> Calendar:
    """
    Loads the existing calendar from the local jobs.ics file.
    An empty or absent file yields a new empty Calendar.

    Raises:
        CalendarError: if an existing feed cannot be read or parsed. Falling back
            to an empty calendar would silently drop every event already
            published to subscribers.
    """
    if not os.path.exists(ICS_FILE_PATH):
        logger.info(f"No existing {ICS_FILE_PATH} found. Starting a new calendar.")
        return Calendar()
        
    try:
        with open(ICS_FILE_PATH, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except OSError as e:
        raise CalendarError(f"Failed to read {ICS_FILE_PATH}: {e}") from e
        
    if not file_content.strip():
        logger.info(f"{ICS_FILE_PATH} is empty. Starting a new calendar.")
        return Calendar()
        
    try:
        return Calendar(file_content)
    except Exception as e:
        raise CalendarError(
            f"Existing {ICS_FILE_PATH} could not be parsed: {e}. "
            "Refusing to overwrite it with an empty calendar; fix or delete the file."
        ) from e

def save_calendar(calendar_obj: Calendar) -> None:
    """
    Saves the calendar object back to the local jobs.ics file,
    removing any events that are older than 2 days past their deadline.

    Raises:
        CalendarError: if the feed could not be serialized or written, so the
            caller does not report a successful sync for an update that was lost.
    """
    # Get today's date
    today = datetime.now().date()
    
    # ২ দিন আগের ডেট বের করা হলো
    expiration_date = today - timedelta(days=2) 
    
    for event in list(calendar_obj.events):
        event_start = getattr(event, "begin", None)
        if event_start is None:
            logger.warning(f"Keeping event without a start date (uid={event.uid}): {event.name}")
            continue
        
        # যদি জবের ডেডলাইন আজকের তারিখ থেকে ২ দিন বা তার বেশি পুরানো হয়, তবেই ডিলিট হবে
        if event_start.date() < expiration_date:
            calendar_obj.events.remove(event)
            logger.debug(f"Removed expired job event (older than 2 days): {event.name}")

    try:
        serialized = "".join(calendar_obj.serialize_iter())
    except Exception as e:
        raise CalendarError(f"Failed to serialize the calendar: {e}") from e
        
    try:
        _write_atomically(ICS_FILE_PATH, serialized)
    except OSError as e:
        raise CalendarError(f"Failed to write {ICS_FILE_PATH}: {e}") from e
        
    logger.info(f"Successfully saved calendar updates to {ICS_FILE_PATH}.")

def create_job_event(job: Dict[str, Any], calendar_obj: Calendar) -> bool:
    """
    Creates an all-day calendar event for a specific job and adds it to the calendar.
    """
    job_primary_id = str(job.get("job_primary_id", "Unknown"))
    
    # 1. Extract necessary fields
    job_title = str(job.get("job_title", "Unknown Job Title")).strip()
    vacancy = str(job.get("vacancy", "N/A")).strip()
    org_name = str(job.get("org_name", "Unknown Organization")).strip()
    published_date = str(job.get("published_date", "Unknown")).strip()
    deadline_date_raw = str(job.get("deadline_date", "")).strip()
    application_site_url = str(job.get("application_site_url", "No URL provided")).strip()
    
    # 2. Parse deadline for the all-day event
    deadline_dt = extract_date(deadline_date_raw)
    if not deadline_dt:
        logger.error(f"Job {job_primary_id} has invalid/missing deadline date: {deadline_date_raw}. Cannot schedule.")
        return False
        
    # 3. Construct event payload exactly to requirements
    title = f"{job_title} (Vacancy: {vacancy})"
    
    description = (
        f"Organization: {org_name}\n"
        f"Published: {published_date}\n"
        f"Deadline: {deadline_date_raw}\n"
        f"Application URL:\n{application_site_url}\n\n"
        f"Job Primary ID: {job_primary_id}"
    )
    
    # 4. Create the iCalendar event
    event = Event()
    event.name = title
    event.description = description
    
    # Set as an all-day event using the parsed deadline date
    event.begin = deadline_dt.strftime("%Y-%m-%d")
    event.make_all_day()
    
    # Crucial: Set a unique ID for this event based on the job_primary_id.
    event.uid = f"teletalk-job-{job_primary_id}@job2calendar"
    
    # 5. Add to calendar
    calendar_obj.events.add(event)
    logger.info(f"Added event for job: {title} (ID: {job_primary_id}) on {event.begin}")
    return True

def _write_atomically(filepath: str, content: str) -> None:
    """
    Writes content to a temporary file in the same directory and renames it into
    place, so a failed write can never leave a half-written feed for subscribers.
    """
    directory = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".ics")
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, filepath)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise