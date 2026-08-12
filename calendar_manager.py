import logging
import os
import re
from datetime import datetime, timedelta  # <-- timedelta যুক্ত করা হয়েছে
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ics import Calendar, Event

logger = logging.getLogger(__name__)

ICS_FILE_PATH = "jobs.ics"

MAX_FIELD_LENGTH = 500
ALLOWED_URL_SCHEMES = ("http", "https")
CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

def sanitize_text(value: Any, fallback: str = "") -> str:
    """
    Normalises a remote API string for safe inclusion in an iCalendar property:
    strips control characters (including CR/LF, which could otherwise forge
    additional ICS properties) and caps the length.
    """
    text = CONTROL_CHARS_PATTERN.sub(" ", str(value)).strip()
    text = re.sub(r"\s{2,}", " ", text)
    if not text:
        return fallback
    return text[:MAX_FIELD_LENGTH]

def sanitize_url(value: Any, fallback: str = "No URL provided") -> str:
    """
    Accepts only plain http(s) URLs from the remote API so that schemes such as
    javascript: or data: never reach a calendar client.
    """
    url = sanitize_text(value)
    if not url:
        return fallback
    try:
        parsed = urlparse(url)
    except ValueError:
        return fallback
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.netloc:
        logger.warning(f"Discarding untrusted application URL: {url}")
        return fallback
    return url

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
    If the file doesn't exist or is corrupt, returns a new empty Calendar.
    """
    if os.path.exists(ICS_FILE_PATH):
        try:
            with open(ICS_FILE_PATH, 'r', encoding='utf-8') as f:
                file_content = f.read()
                if file_content.strip():
                    return Calendar(file_content)
        except Exception as e:
            logger.error(f"Failed to load existing {ICS_FILE_PATH}: {e}. Starting fresh.")
    
    return Calendar()

def save_calendar(calendar_obj: Calendar) -> None:
    """
    Saves the calendar object back to the local jobs.ics file,
    removing any events that are older than 2 days past their deadline.
    """
    try:
        # Get today's date
        today = datetime.now().date()
        
        # ২ দিন আগের ডেট বের করা হলো
        expiration_date = today - timedelta(days=2) 
        
        for event in list(calendar_obj.events):
            try:
                # যদি জবের ডেডলাইন আজকের তারিখ থেকে ২ দিন বা তার বেশি পুরানো হয়, তবেই ডিলিট হবে
                if event.begin.date() < expiration_date:
                    calendar_obj.events.remove(event)
                    logger.debug(f"Removed expired job event (older than 2 days): {event.name}")
            except AttributeError:
                pass

        with open(ICS_FILE_PATH, 'w', encoding='utf-8') as f:
            f.writelines(calendar_obj.serialize_iter())
            
        logger.info(f"Successfully saved calendar updates to {ICS_FILE_PATH}.")
    except Exception as e:
        logger.exception(f"Failed to save calendar to {ICS_FILE_PATH}: {e}")

def create_job_event(job: Dict[str, Any], calendar_obj: Calendar) -> bool:
    """
    Creates an all-day calendar event for a specific job and adds it to the calendar.
    """
    job_primary_id = sanitize_text(job.get("job_primary_id"), "Unknown")
    
    # 1. Extract necessary fields (every value comes from a remote API and is untrusted)
    job_title = sanitize_text(job.get("job_title"), "Unknown Job Title")
    vacancy = sanitize_text(job.get("vacancy"), "N/A")
    org_name = sanitize_text(job.get("org_name"), "Unknown Organization")
    published_date = sanitize_text(job.get("published_date"), "Unknown")
    deadline_date_raw = sanitize_text(job.get("deadline_date"))
    application_site_url = sanitize_url(job.get("application_site_url"))
    
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
    event.uid = f"teletalk-job-{re.sub(r'[^A-Za-z0-9._-]', '', job_primary_id)}@job2calendar"
    
    # 5. Add to calendar
    try:
        calendar_obj.events.add(event)
        logger.info(f"Added event for job: {title} (ID: {job_primary_id}) on {event.begin}")
        return True
    except Exception as e:
        logger.exception(f"Unexpected error adding event for job {job_primary_id}: {e}")
        return False