from datetime import date, timedelta

import calendar_manager
import main
from filter import filter_matching_jobs

KEYWORDS = ["office assistant", "cashier"]
TODAY = date(2026, 8, 12)


def _job(job_id, title, deadline, vacancy="5", org="Some Org"):
    return {
        "job_primary_id": job_id,
        "job_title": title,
        "org_name": org,
        "vacancy": vacancy,
        "published_date": "2026-08-01",
        "deadline_date": deadline.isoformat(),
        "application_site_url": "https://example.com",
    }


def _calendar(jobs):
    cal = calendar_manager.Calendar()
    for job in jobs:
        assert calendar_manager.create_job_event(job, cal)
    return cal


def test_expired_events_are_purged_after_one_day():
    cal = _calendar(
        [
            _job("1", "Office Assistant", TODAY - timedelta(days=1)),
            _job("2", "Cashier", TODAY),
            _job("3", "Office Assistant", TODAY + timedelta(days=3)),
        ]
    )

    removed = calendar_manager.purge_expired_events(cal, today=TODAY)

    assert removed == ["1"]
    assert calendar_manager.existing_job_ids(cal) == {"2", "3"}


def test_unmatched_events_are_purged():
    cal = _calendar(
        [
            _job("1", "Office Assistant", TODAY + timedelta(days=3)),
            _job("2", "Security Guard", TODAY + timedelta(days=3)),
        ]
    )

    removed = calendar_manager.purge_unmatched_events(cal, KEYWORDS)

    assert removed == ["2"]
    assert calendar_manager.existing_job_ids(cal) == {"1"}


def test_low_vacancy_events_are_purged_but_unknown_vacancy_kept():
    cal = _calendar(
        [
            _job("1", "Office Assistant", TODAY + timedelta(days=3), vacancy="01"),
            _job("2", "Cashier", TODAY + timedelta(days=3), vacancy="Not Specific"),
            _job("3", "Cashier", TODAY + timedelta(days=3), vacancy="04"),
        ]
    )

    removed = calendar_manager.purge_low_vacancy_events(cal, main.MIN_VACANCY)

    assert removed == ["1"]
    assert calendar_manager.existing_job_ids(cal) == {"2", "3"}


def test_event_title_and_id_round_trip():
    cal = _calendar([_job("42", "Office Assistant (Grade 16)", TODAY + timedelta(days=3))])
    event = list(cal.events)[0]

    assert calendar_manager.job_id_from_event(event) == "42"
    assert calendar_manager.job_title_from_event(event) == "Office Assistant (Grade 16)"
    assert calendar_manager.vacancy_from_event(event) == 5


def test_keyword_filter_is_case_insensitive():
    jobs = [
        _job("1", "OFFICE ASSISTANT cum Typist", TODAY),
        _job("2", "Driver", TODAY),
    ]

    assert [j["job_primary_id"] for j in filter_matching_jobs(jobs, KEYWORDS)] == ["1"]


def test_business_rules():
    assert main._should_skip(_job("1", "Cashier", TODAY, vacancy="1"))
    assert not main._should_skip(_job("2", "Cashier", TODAY, vacancy="Not Specific"))
    assert main._should_skip(_job("3", "Cashier", TODAY, org="DC Office Kurigram"))
    assert not main._should_skip(_job("4", "Cashier", TODAY, org="DC Office Naogaon"))


def test_telegram_messages_stay_under_limit():
    chunks = main._split_message("header", ["line " + "x" * 200] * 60)

    assert len(chunks) > 1
    assert all(len(chunk) <= main.TELEGRAM_MAX_CHARS for chunk in chunks)
    assert sum(chunk.count("line ") for chunk in chunks) == 60
