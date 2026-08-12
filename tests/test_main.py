import pytest
import requests

import main


class DummyResponse:
    def __init__(self, error=None):
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error


def test_send_telegram_notification_skips_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def fail_post(*args, **kwargs):
        raise AssertionError("should not post without credentials")

    monkeypatch.setattr(requests, "post", fail_post)
    main.send_telegram_notification(["a job"])


def test_send_telegram_notification_posts_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat456")
    captured = {}

    def fake_post(url, json=None):
        captured["url"] = url
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    main.send_telegram_notification(["job A", "job B"])

    assert captured["url"] == "https://api.telegram.org/bottoken123/sendMessage"
    assert captured["json"]["chat_id"] == "chat456"
    assert "job A" in captured["json"]["text"]
    assert "job B" in captured["json"]["text"]
    assert "2" in captured["json"]["text"]


def test_send_telegram_notification_swallows_request_errors(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat456")
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: DummyResponse(error=requests.exceptions.HTTPError("400")),
    )
    main.send_telegram_notification(["job A"])


class FakeCalendar:
    def __init__(self):
        self.created = []


@pytest.fixture
def harness(monkeypatch):
    """Stubs out every collaborator of main.main() and records the interactions."""
    state = {
        "keywords": ["programmer"],
        "processed": set(),
        "jobs": [],
        "saved_calendar": 0,
        "saved_processed": None,
        "notified": None,
        "create_result": True,
    }
    calendar = FakeCalendar()

    monkeypatch.setattr(main.storage, "load_keywords", lambda path: state["keywords"])
    monkeypatch.setattr(main.storage, "load_processed_jobs", lambda path: state["processed"])
    monkeypatch.setattr(main.api, "fetch_all_jobs", lambda: state["jobs"])
    monkeypatch.setattr(main.calendar_manager, "load_calendar", lambda: calendar)

    def fake_create(job, cal):
        if state["create_result"]:
            cal.created.append(job["job_primary_id"])
        return state["create_result"]

    def fake_save_calendar(cal):
        state["saved_calendar"] += 1

    def fake_save_processed(path, processed):
        state["saved_processed"] = set(processed)

    monkeypatch.setattr(main.calendar_manager, "create_job_event", fake_create)
    monkeypatch.setattr(main.calendar_manager, "save_calendar", fake_save_calendar)
    monkeypatch.setattr(main.storage, "save_processed_jobs", fake_save_processed)
    monkeypatch.setattr(main, "send_telegram_notification", lambda jobs: state.__setitem__("notified", list(jobs)))

    state["calendar"] = calendar
    return state


def job(**overrides):
    base = {
        "job_primary_id": "100",
        "job_title": "Assistant Programmer",
        "org_name": "ICT Division",
        "vacancy": "5",
        "deadline_date": "2026-08-21",
    }
    base.update(overrides)
    return base


def test_main_exits_without_keywords(harness):
    harness["keywords"] = []
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0


def test_main_exits_when_no_jobs_fetched(harness):
    harness["jobs"] = []
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0


def test_main_creates_event_and_notifies(harness):
    harness["jobs"] = [job()]
    main.main()

    assert harness["calendar"].created == ["100"]
    assert harness["saved_processed"] == {"100"}
    assert harness["saved_calendar"] == 1
    assert harness["notified"] == ["🔹 Assistant Programmer (ICT Division) [Post: 5]"]


def test_main_skips_jobs_without_primary_id(harness):
    harness["jobs"] = [job(job_primary_id=""), job(job_primary_id="None")]
    main.main()
    assert harness["calendar"].created == []
    assert harness["notified"] is None
    assert harness["saved_calendar"] == 1


def test_main_skips_single_vacancy_jobs(harness):
    harness["jobs"] = [job(vacancy="01 post"), job(job_primary_id="101", vacancy="2 posts")]
    main.main()
    assert harness["calendar"].created == ["101"]


def test_main_keeps_jobs_with_unparseable_vacancy(harness):
    harness["jobs"] = [job(vacancy="Not Specific")]
    main.main()
    assert harness["calendar"].created == ["100"]


def test_main_skips_non_naogaon_dc_office_jobs(harness):
    harness["jobs"] = [
        job(job_primary_id="1", org_name="DC Office, Dhaka"),
        job(job_primary_id="2", org_name="জেলা প্রশাসক, বগুড়া"),
        job(job_primary_id="3", org_name="DC Office, Naogaon"),
        job(job_primary_id="4", org_name="জেলা প্রশাসক, নওগাঁ"),
    ]
    main.main()
    assert harness["calendar"].created == ["3", "4"]


def test_main_skips_already_processed_jobs(harness):
    harness["processed"] = {"100"}
    harness["jobs"] = [job()]
    main.main()
    assert harness["calendar"].created == []
    assert harness["saved_processed"] is None
    assert harness["saved_calendar"] == 1


def test_main_filters_by_keywords(harness):
    harness["keywords"] = ["cashier"]
    harness["jobs"] = [job()]
    main.main()
    assert harness["calendar"].created == []


def test_main_does_not_mark_processed_when_event_creation_fails(harness):
    harness["create_result"] = False
    harness["jobs"] = [job()]
    main.main()
    assert harness["saved_processed"] is None
    assert harness["notified"] is None
    assert harness["saved_calendar"] == 1
