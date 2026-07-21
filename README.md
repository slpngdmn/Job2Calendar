# Job2Calendar

Job2Calendar is an automated Python application that monitors the Teletalk AllJobs API for specific job titles. When a match is found, it automatically generates a standard `.ics` (iCalendar) feed. You can subscribe to this feed directly in Google Calendar, Apple Calendar, or Outlook.

It is designed to run completely hands-off using GitHub Actions, executing every 12 hours. Best of all, it requires **zero API credentials, zero authentication, and no credit card**.

## Features

* **Automated Polling:** Fetches paginated job data from the Teletalk API.
* **Smart Filtering:** Matches target job titles (case-insensitive) using a customizable `keywords.json` file.
* **ICS Calendar Feed:** Automatically builds and updates a `jobs.ics` file containing all-day events on the job's application deadline.
* **Duplicate Prevention:** Uses a local `processed_jobs.json` file and unique event UIDs to ensure duplicate events are never created.
* **CI/CD Ready:** Includes a GitHub Actions workflow (`.github/workflows/sync.yml`) that runs every 12 hours and commits the updated calendar feed back to the repository.

## Project Structure

```text
teletalk-job-calendar/
│
├── .github/
│   └── workflows/
│       └── sync.yml          # GitHub Actions automation workflow
├── api.py                    # Handles fetching and paginating the Teletalk API
├── calendar.py               # Generates and manages the local jobs.ics file
├── filter.py                 # Logic for matching job titles
├── keywords.json             # Target job titles to monitor
├── main.py                   # Main orchestration script
├── processed_jobs.json       # Local database of already processed jobs
├── requirements.txt          # Python dependencies
├── storage.py                # Handles reading/writing JSON files
└── README.md                 # Project documentation