from datetime import datetime, timedelta

from ics import Calendar, Event

import calendar_manager


def test_extract_date_parses_iso_prefix():
    assert calendar_manager.extract_date("2026-08-21T04:00:00.000Z") == datetime(2026, 8, 21)


def test_extract_date_finds_embedded_date():
    assert calendar_manager.extract_date("deadline is 2026-08-21 sharp") == datetime(2026, 8, 21)


def test_extract_date_rejects_empty_and_unparsable():
    assert calendar_manager.extract_date("") is None
    assert calendar_manager.extract_date("Unknown") is None
    assert calendar_manager.extract_date("2026-13-45") is None


def test_load_calendar_returns_empty_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(tmp_path / "jobs.ics"))
    assert len(calendar_manager.load_calendar().events) == 0


def test_load_calendar_returns_empty_when_file_blank(tmp_path, monkeypatch):
    path = tmp_path / "jobs.ics"
    path.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(path))
    assert len(calendar_manager.load_calendar().events) == 0


def test_load_calendar_reads_existing_events(tmp_path, monkeypatch):
    path = tmp_path / "jobs.ics"
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(path))

    cal = Calendar()
    event = Event()
    event.name = "Existing"
    event.begin = "2026-08-21"
    event.make_all_day()
    cal.events.add(event)
    path.write_text(cal.serialize(), encoding="utf-8")

    loaded = calendar_manager.load_calendar()
    assert [e.name for e in loaded.events] == ["Existing"]


def test_load_calendar_recovers_from_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "jobs.ics"
    path.write_text("this is not a calendar", encoding="utf-8")
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(path))
    assert len(calendar_manager.load_calendar().events) == 0


def _all_day_event(name, date):
    event = Event()
    event.name = name
    event.begin = date.strftime("%Y-%m-%d")
    event.make_all_day()
    return event


def test_save_calendar_drops_events_older_than_two_days(tmp_path, monkeypatch):
    path = tmp_path / "jobs.ics"
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(path))

    today = datetime.now().date()
    cal = Calendar()
    cal.events.add(_all_day_event("expired", today - timedelta(days=5)))
    cal.events.add(_all_day_event("boundary", today - timedelta(days=2)))
    cal.events.add(_all_day_event("future", today + timedelta(days=5)))

    calendar_manager.save_calendar(cal)

    names = {e.name for e in Calendar(path.read_text(encoding="utf-8")).events}
    assert names == {"boundary", "future"}


def test_save_calendar_keeps_events_without_a_begin_date(tmp_path, monkeypatch):
    path = tmp_path / "jobs.ics"
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(path))

    class NoBeginEvent:
        name = "undated"
        begin = None

    cal = Calendar()
    kept = _all_day_event("future", datetime.now().date() + timedelta(days=3))
    cal.events.add(kept)
    cal.events.add(NoBeginEvent())

    calendar_manager.save_calendar(cal)

    assert any(isinstance(e, NoBeginEvent) for e in cal.events)
    assert kept in cal.events


def test_save_calendar_swallows_write_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar_manager, "ICS_FILE_PATH", str(tmp_path / "missing_dir" / "jobs.ics"))
    calendar_manager.save_calendar(Calendar())
    assert not (tmp_path / "missing_dir").exists()


JOB = {
    "job_primary_id": "100",
    "job_title": " Assistant Programmer ",
    "vacancy": "5",
    "org_name": "ICT Division",
    "published_date": "2026-07-21",
    "deadline_date": "2026-08-21T04:00:00.000Z",
    "application_site_url": "https://apply.example.com",
}


def test_create_job_event_builds_all_day_event():
    cal = Calendar()
    assert calendar_manager.create_job_event(JOB, cal) is True

    event = next(iter(cal.events))
    assert event.name == "Assistant Programmer (Vacancy: 5)"
    assert event.uid == "teletalk-job-100@job2calendar"
    assert event.all_day is True
    assert event.begin.date() == datetime(2026, 8, 21).date()
    assert "Organization: ICT Division" in event.description
    assert "Published: 2026-07-21" in event.description
    assert "https://apply.example.com" in event.description
    assert "Job Primary ID: 100" in event.description


def test_create_job_event_uses_defaults_for_missing_fields():
    cal = Calendar()
    assert calendar_manager.create_job_event({"deadline_date": "2026-08-21"}, cal) is True

    event = next(iter(cal.events))
    assert event.name == "Unknown Job Title (Vacancy: N/A)"
    assert event.uid == "teletalk-job-Unknown@job2calendar"
    assert "Organization: Unknown Organization" in event.description


def test_create_job_event_rejects_invalid_deadline():
    cal = Calendar()
    assert calendar_manager.create_job_event({**JOB, "deadline_date": "Not Specific"}, cal) is False
    assert len(cal.events) == 0


def test_create_job_event_returns_false_when_add_fails(monkeypatch):
    class ExplodingEvents:
        def add(self, _event):
            raise RuntimeError("cannot add")

    cal = Calendar()
    monkeypatch.setattr(cal, "events", ExplodingEvents())
    assert calendar_manager.create_job_event(JOB, cal) is False


def test_create_job_event_same_job_id_produces_stable_uid():
    cal = Calendar()
    calendar_manager.create_job_event(JOB, cal)
    calendar_manager.create_job_event(JOB, cal)
    assert {e.uid for e in cal.events} == {"teletalk-job-100@job2calendar"}
