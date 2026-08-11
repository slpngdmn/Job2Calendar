import logging
import sys
import os
import requests

# Import our custom modules
import api
from filter import filter_matching_jobs
import storage
import Job2Calendar.calendar_manager as calendar_manager

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
    # আপনার চাওয়া ফরম্যাটে মেসেজ তৈরি
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
    keywords = storage.load_keywords("keywords.json")
    if not keywords:
        logger.warning("No keywords found to filter by. Exiting.")
        sys.exit(0)
        
    processed_jobs = storage.load_processed_jobs("processed_jobs.json")
    
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
    new_jobs_list = []  # নতুন job গুলোর নাম সেভ করার লিস্ট
    
    for job in matching_jobs:
        job_primary_id = str(job.get("job_primary_id", ""))
        
        if not job_primary_id or job_primary_id == "None":
            logger.warning(f"Job missing primary ID, skipping: {job.get('job_title', 'Unknown')}")
            continue
            
        # Check local storage first (fast O(1) lookup)
        if job_primary_id in processed_jobs:
            logger.debug(f"Job {job_primary_id} already in local processed list. Skipping.")
            continue
            
        logger.info(f"Processing new matching job: {job.get('job_title')} (ID: {job_primary_id})")
        
        # Attempt to create the event in the ICS calendar
        success = calendar_manager.create_job_event(job, cal_obj)
        
        if success:
            processed_jobs.add(job_primary_id)
            new_processed_count += 1
            
            # নোটিফিকেশনের জন্য job এর নাম ও প্রতিষ্ঠানের নাম যুক্ত করা
            job_title = job.get('job_title', 'Unknown')
            org_name = job.get('org_name_bn', 'Unknown')
            new_jobs_list.append(f"🔹 {job_title} ({org_name})")
        else:
            logger.error(f"Failed to process job {job_primary_id}. Will retry on next run.")
            
    # 5. Save State and Send Notification
    if new_processed_count > 0:
        calendar_manager.save_calendar(cal_obj)
        storage.save_processed_jobs("processed_jobs.json", processed_jobs)
        logger.info(f"Successfully added {new_processed_count} new jobs to the calendar.")
        
        # নতুন job পাওয়া গেলে Telegram এ মেসেজ পাঠানো হবে
        send_telegram_notification(new_jobs_list)
    else:
        calendar_manager.save_calendar(cal_obj)
        logger.info("No new jobs needed to be saved to local storage.")
        
    logger.info("Job2Calendar sync process completed successfully.")

if __name__ == "__main__":
    main()