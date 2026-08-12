import logging
import sys
import os
import requests

# Import our custom modules
import api
from filter import filter_matching_jobs
import storage
import calendar_manager
from utils import first_int, get_field

KEYWORDS_FILE = "keywords.json"
PROCESSED_JOBS_FILE = "processed_jobs.json"

# Configure logging for the application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def send_telegram_notification(new_jobs: list):
    """
    Sends a formatted notification to Telegram with the newly added jobs.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.warning("Telegram credentials not found in environment variables. Skipping notification.")
        return
        
    count = len(new_jobs)
    message = f"আজকে {count}টি নতুন job add হয়েছে।\nসবগুলো হলো:\n\n" + "\n".join(new_jobs)
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def main() -> None:
    logger.info("Starting Job2Calendar ICS sync process...")
    
    # 1. Load Local Data
    keywords = storage.load_keywords(KEYWORDS_FILE)
    if not keywords:
        logger.warning("No keywords found to filter by. Exiting.")
        sys.exit(0)
        
    processed_jobs = storage.load_processed_jobs(PROCESSED_JOBS_FILE)
    
    # 2. Fetch and Filter Jobs
    all_jobs = api.fetch_all_jobs()
    if not all_jobs:
        logger.info("No jobs fetched from the API. Exiting.")
        sys.exit(0)
        
    matching_jobs = filter_matching_jobs(all_jobs, keywords)
    logger.info(f"Found {len(matching_jobs)} jobs matching the target keywords.")
    
    # 3. Load existing calendar
    cal_obj = calendar_manager.load_calendar()
    
    # 4. Process Matching Jobs
    new_processed_count = 0
    new_jobs_list = []
    
    for job in matching_jobs:
        job_primary_id = get_field(job, "job_primary_id")
        
        if not job_primary_id:
            logger.warning(f"Job missing primary ID, skipping: {get_field(job, 'job_title', 'Unknown')}")
            continue
            
        # --- NEW 1: Vacancy Filter (১টি পদ থাকলে বাদ দেওয়া) ---
        vacancy_str = get_field(job, "vacancy")
        vacancy_count = first_int(vacancy_str)
        if vacancy_count is not None and vacancy_count <= 1:
            logger.info(f"Skipping '{job.get('job_title')}' because vacancy is only {vacancy_count}.")
            continue
        # -----------------------------------------------------

        # --- NEW 2: DC Office Filter (নওগাঁ বাদে বাকি সব জেলার জব বাদ দেওয়া) ---
        org_name = get_field(job, "org_name", "Unknown")
        org_name_lower = org_name.lower()
        
        # চেক করবে এটি ডিসি অফিসের জব কি না
        if "dc office" in org_name_lower or "জেলা প্রশাসক" in org_name:
            # যদি ডিসি অফিস হয়, তবে চেক করবে এটি নওগাঁ কি না
            if "naogaon" in org_name_lower or "নওগাঁ" in org_name:
                logger.info(f"Keeping '{job.get('job_title')}' because it is from Naogaon DC Office.")
            else:
                logger.info(f"Skipping '{job.get('job_title')}' because it is a district-specific DC Office job ({org_name}).")
                continue
        # -----------------------------------------------------
            
        # Check local storage first
        if job_primary_id in processed_jobs:
            logger.debug(f"Job {job_primary_id} already in local processed list. Skipping.")
            continue
            
        logger.info(f"Processing new matching job: {job.get('job_title')} (ID: {job_primary_id})")
        
        # Attempt to create the event in the ICS calendar
        success = calendar_manager.create_job_event(job, cal_obj)
        
        if success:
            processed_jobs.add(job_primary_id)
            new_processed_count += 1
            
            job_title = get_field(job, "job_title", "Unknown")
            # Telegram মেসেজে পদের সংখ্যাও (vacancy) দেখিয়ে দেওয়া হলো
            new_jobs_list.append(f"🔹 {job_title} ({org_name}) [Post: {vacancy_str}]")
        else:
            logger.error(f"Failed to process job {job_primary_id}. Will retry on next run.")
            
    # 5. Save State and Send Notification
    if new_processed_count > 0:
        calendar_manager.save_calendar(cal_obj)
        storage.save_processed_jobs(PROCESSED_JOBS_FILE, processed_jobs)
        logger.info(f"Successfully added {new_processed_count} new jobs to the calendar.")
        
        send_telegram_notification(new_jobs_list)
    else:
        calendar_manager.save_calendar(cal_obj)
        logger.info("No new jobs needed to be saved to local storage.")
        
    logger.info("Job2Calendar sync process completed successfully.")

if __name__ == "__main__":
    main()