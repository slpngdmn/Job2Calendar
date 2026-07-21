import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from ics import Calendar, Event

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
    Saves the calendar object back to the local jobs.ics file.
    """
    try:
        with open(ICS_FILE_PATH, 'w', encoding='utf-8') as f:
            f.writelines(calendar_obj.serialize_iter())
        logger.info(f"Successfully saved calendar updates to {ICS_FILE_PATH}.")
    except Exception as e:
        logger.exception(f"Failed to save calendar to {ICS_FILE_PATH}: {e}")

def create_job_event(job: Dict[str, Any], calendar_obj: Calendar) -> bool:
    """
    Creates an all-day calendar event for a specific job and adds it to the calendar.
    
    Args:
        job: Dictionary containing job details.
        calendar_obj: The ics Calendar object to add the event to.
        
    Returns:
        True if successfully added, False otherwise.
    """
    job_primary_id = str(job.get("job_primary_id", "Unknown"))
    
    # 1. Extract necessary fields
    job_title = str(job.get("job_title", "Unknown Job Title")).strip()
    vacancy = str(job.get("vacancy", "N/A")).strip()
    org_name_bn = str(job.get("org_name_bn", "Unknown Organization")).strip()
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
        f"Organization: {org_name_bn}\n"
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
    # This guarantees calendar apps won't create duplicates if they process the feed multiple times.
    event.uid = f"teletalk-job-{job_primary_id}@job2calendar"
    
    # 5. Add to calendar
    try:
        calendar_obj.events.add(event)
        logger.info(f"Added event for job: {title} (ID: {job_primary_id}) on {event.begin}")
        return True
    except Exception as e:
        logger.exception(f"Unexpected error adding event for job {job_primary_id}: {e}")
        return False