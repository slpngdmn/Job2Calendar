import logging
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set

import requests

import api
import calendar_manager
import storage
from filter import filter_matching_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

KEYWORDS_FILE = "keywords.json"
PROCESSED_JOBS_FILE = "processed_jobs.json"

TELEGRAM_TIMEOUT = 10
TELEGRAM_MAX_CHARS = 3800
MIN_VACANCY = 2


def _split_message(header: str, lines: List[str]) -> List[str]:
    """
    Splits notification lines into Telegram-sized chunks (4096 char API limit).
    """
    chunks: List[str] = []
    current = header

    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > TELEGRAM_MAX_CHARS and current:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def send_telegram_notification(new_jobs: List[str]) -> None:
    """
    Sends a formatted notification to Telegram with the newly added jobs.
    """
    if not new_jobs:
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram credentials not found in environment variables. Skipping notification.")
        return

    header = f"আজকে {len(new_jobs)}টি নতুন job add হয়েছে।\nসবগুলো হলো:\n"
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    with requests.Session() as session:
        for chunk in _split_message(header, new_jobs):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            try:
                response = session.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
                response.raise_for_status()
                logger.info("Telegram notification sent successfully.")
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
                return


def _vacancy_count(vacancy_str: str) -> int:
    """
    Returns the first number found in a vacancy string, or -1 when unknown.
    """
    numbers = re.findall(r"\d+", vacancy_str)
    return int(numbers[0]) if numbers else -1


def _is_excluded_dc_office(org_name: str) -> bool:
    """
    Drops district-specific DC Office jobs from every district except Naogaon.
    """
    org_name_lower = org_name.lower()
    is_dc_office = "dc office" in org_name_lower or "জেলা প্রশাসক" in org_name
    if not is_dc_office:
        return False

    return not ("naogaon" in org_name_lower or "নওগাঁ" in org_name)


def _should_skip(job: Dict[str, Any]) -> bool:
    """
    Applies the vacancy and DC Office business rules to a single job.
    """
    job_title = job.get("job_title", "Unknown")

    vacancy_count = _vacancy_count(str(job.get("vacancy", "")))
    if 0 <= vacancy_count < MIN_VACANCY:
        logger.info(f"Skipping '{job_title}' because vacancy is only {vacancy_count}.")
        return True

    org_name = str(job.get("org_name", "Unknown"))
    if _is_excluded_dc_office(org_name):
        logger.info(f"Skipping '{job_title}' because it is a district-specific DC Office job ({org_name}).")
        return True

    return False


def main() -> None:
    logger.info("Starting Job2Calendar ICS sync process...")

    keywords = storage.load_keywords(KEYWORDS_FILE)
    if not keywords:
        logger.warning("No keywords found to filter by. Exiting.")
        return

    processed_jobs = storage.load_processed_jobs(PROCESSED_JOBS_FILE)
    cal_obj = calendar_manager.load_calendar()

    # Retention runs on every sync, independent of what the API returns.
    expired_ids: Set[str] = set(calendar_manager.purge_expired_events(cal_obj))
    unmatched_ids: Set[str] = set(calendar_manager.purge_unmatched_events(cal_obj, keywords))
    unmatched_ids.update(calendar_manager.purge_low_vacancy_events(cal_obj, MIN_VACANCY))

    # Jobs dropped by the current filters may return if the filters change again.
    processed_jobs.difference_update(unmatched_ids)

    all_jobs = api.fetch_all_jobs()
    matching_jobs = filter_matching_jobs(all_jobs, keywords) if all_jobs else []
    logger.info(f"Found {len(matching_jobs)} jobs matching the target keywords.")

    calendar_ids = calendar_manager.existing_job_ids(cal_obj)
    today = datetime.now().date()
    cutoff = today - timedelta(days=calendar_manager.RETENTION_DAYS)

    added_count = 0
    new_jobs_list: List[str] = []

    for job in matching_jobs:
        job_primary_id = str(job.get("job_primary_id") or "")

        if not job_primary_id or job_primary_id == "None":
            logger.warning(f"Job missing primary ID, skipping: {job.get('job_title', 'Unknown')}")
            continue

        if job_primary_id in expired_ids or job_primary_id in calendar_ids:
            continue

        if _should_skip(job):
            continue

        deadline = calendar_manager.extract_date(job.get("deadline_date", ""))
        if deadline and deadline.date() <= cutoff:
            logger.info(f"Skipping '{job.get('job_title')}' because its deadline already passed.")
            continue

        is_new = job_primary_id not in processed_jobs
        logger.info(f"Processing matching job: {job.get('job_title')} (ID: {job_primary_id})")

        if not calendar_manager.create_job_event(job, cal_obj):
            logger.error(f"Failed to process job {job_primary_id}. Will retry on next run.")
            continue

        processed_jobs.add(job_primary_id)
        calendar_ids.add(job_primary_id)
        added_count += 1

        if is_new:
            new_jobs_list.append(
                f"🔹 {job.get('job_title', 'Unknown')} ({job.get('org_name', 'Unknown')}) "
                f"[Post: {job.get('vacancy', 'N/A')}]"
            )

    # Notify before disk I/O so the alert lands as early as possible.
    send_telegram_notification(new_jobs_list)

    calendar_manager.save_calendar(cal_obj)
    storage.save_processed_jobs(PROCESSED_JOBS_FILE, processed_jobs)

    logger.info(
        f"Sync complete: {added_count} Job added, "
        f"{len(expired_ids)} expired job removed, {len(unmatched_ids)} filtered out."
    )


if __name__ == "__main__":
    main()
