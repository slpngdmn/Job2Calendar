import requests

import api


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def make_get(responses):
    """Returns a fake requests.get that serves responses by URL substring match."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        for needle, response in responses:
            if needle in url:
                if callable(response):
                    return response(url)
                return response
        return FakeResponse({})

    fake_get.calls = calls
    return fake_get


def install(monkeypatch, fake_get):
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(api.time, "sleep", lambda *_: None)


def test_make_request_with_retry_returns_json(monkeypatch):
    install(monkeypatch, make_get([("", FakeResponse({"ok": True}))]))
    assert api._make_request_with_retry("http://example.com") == {"ok": True}


def test_make_request_with_retry_retries_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def flaky(url):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return FakeResponse(error=requests.exceptions.ConnectionError("down"))
        return FakeResponse({"ok": True})

    install(monkeypatch, make_get([("", flaky)]))
    assert api._make_request_with_retry("http://example.com") == {"ok": True}
    assert attempts["n"] == 3


def test_make_request_with_retry_gives_up_after_max_retries(monkeypatch):
    fake_get = make_get([("", FakeResponse(error=requests.exceptions.HTTPError("500")))])
    install(monkeypatch, fake_get)
    assert api._make_request_with_retry("http://example.com") is None
    assert len(fake_get.calls) == api.MAX_RETRIES


def test_make_request_with_retry_handles_timeout_and_bad_json(monkeypatch):
    install(monkeypatch, make_get([("", FakeResponse(error=requests.exceptions.Timeout()))]))
    assert api._make_request_with_retry("http://example.com") is None

    install(monkeypatch, make_get([("", FakeResponse(payload=ValueError("bad json")))]))
    assert api._make_request_with_retry("http://example.com") is None


def test_make_request_with_retry_handles_unexpected_error(monkeypatch):
    install(monkeypatch, make_get([("", FakeResponse(error=RuntimeError("boom")))]))
    assert api._make_request_with_retry("http://example.com") is None


def test_fetch_organization_ids_paginates_until_no_new_ids(monkeypatch):
    pages = {
        "page=1": FakeResponse({"govtOrgJobs": [{"id": 1}, {"id": 2}]}),
        "page=2": FakeResponse({"govtOrgJobs": [{"id": 3}]}),
        "page=3": FakeResponse({"govtOrgJobs": [{"id": 3}]}),
    }
    install(monkeypatch, make_get([(k, v) for k, v in pages.items()]))
    assert sorted(api._fetch_organization_ids()) == [1, 2, 3]


def test_fetch_organization_ids_supports_list_response_and_data_key(monkeypatch):
    install(monkeypatch, make_get([("page=1", FakeResponse([{"id": 7}])), ("page=2", FakeResponse([]))]))
    assert api._fetch_organization_ids() == [7]

    install(monkeypatch, make_get([("page=1", FakeResponse({"data": [{"id": 8}]})), ("page=2", FakeResponse({"data": []}))]))
    assert api._fetch_organization_ids() == [8]


def test_fetch_organization_ids_falls_back_to_first_list_value(monkeypatch):
    install(
        monkeypatch,
        make_get([("page=1", FakeResponse({"meta": 1, "weird_key": [{"id": 9}]})), ("page=2", FakeResponse({}))]),
    )
    assert api._fetch_organization_ids() == [9]


def test_fetch_organization_ids_skips_entries_without_id(monkeypatch):
    install(
        monkeypatch,
        make_get([("page=1", FakeResponse({"govtOrgJobs": ["nope", {"name": "x"}, {"id": 4}]})), ("page=2", FakeResponse({}))]),
    )
    assert api._fetch_organization_ids() == [4]


def test_fetch_organization_ids_empty_on_failed_request(monkeypatch):
    install(monkeypatch, make_get([("", FakeResponse(error=requests.exceptions.HTTPError("500")))]))
    assert api._fetch_organization_ids() == []


def test_fetch_all_jobs_returns_empty_without_orgs(monkeypatch):
    monkeypatch.setattr(api, "_fetch_organization_ids", lambda: [])
    assert api.fetch_all_jobs() == []


def test_fetch_all_jobs_maps_fields(monkeypatch):
    monkeypatch.setattr(api, "_fetch_organization_ids", lambda: [11])
    monkeypatch.setattr(api.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        api,
        "_make_request_with_retry",
        lambda url: {
            "govt_jobs": [
                {
                    "id": 100,
                    "job_title": "  Assistant Programmer ",
                    "vacancy": " 5 ",
                    "published_date": "2026-07-21T04:00:00.000Z",
                    "deadline_date": "2026-08-21T04:00:00.000Z",
                    "application_site": " https://apply.example.com ",
                    "job_utilities_govtorganization": {"name": "ICT Division"},
                }
            ]
        },
    )

    assert api.fetch_all_jobs() == [
        {
            "job_primary_id": "100",
            "job_title": "Assistant Programmer",
            "org_name": "ICT Division",
            "vacancy": "5",
            "published_date": "2026-07-21",
            "deadline_date": "2026-08-21",
            "application_site_url": "https://apply.example.com",
        }
    ]


def test_fetch_all_jobs_applies_fallbacks(monkeypatch):
    monkeypatch.setattr(api, "_fetch_organization_ids", lambda: [11])
    monkeypatch.setattr(api.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        api,
        "_make_request_with_retry",
        lambda url: [
            {
                "job_id": 200,
                "job_title": "Office Sohayok",
                "vacancy": None,
                "vacancy_not_specific": False,
                "published_date": "2026-07-21T04:00:00.000Z",
                "deadline_date": "",
                "application_site": "none",
                "job_utilities_govtorganization": None,
            }
        ],
    )

    job = api.fetch_all_jobs()[0]
    assert job["job_primary_id"] == "200"
    assert job["vacancy"] == "Not Specific"
    assert job["org_name"] == "Unknown Organization"
    assert job["deadline_date"] == job["published_date"] == "2026-07-21"
    assert job["application_site_url"] == "https://alljobs.teletalk.com.bd"


def test_fetch_all_jobs_uses_org_website_and_vacancy_flag(monkeypatch):
    monkeypatch.setattr(api, "_fetch_organization_ids", lambda: [11])
    monkeypatch.setattr(api.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        api,
        "_make_request_with_retry",
        lambda url: {
            "data": [
                {
                    "id": 300,
                    "job_title": "Cashier",
                    "vacancy": "3",
                    "vacancy_not_specific": True,
                    "published_date": "short",
                    "job_utilities_govtorganization": {"name": "Org", "website": " https://org.example.com "},
                }
            ]
        },
    )

    job = api.fetch_all_jobs()[0]
    assert job["vacancy"] == "Not Specific"
    assert job["published_date"] == "Unknown"
    assert job["deadline_date"] == "Unknown"
    assert job["application_site_url"] == "https://org.example.com"


def test_fetch_all_jobs_finds_nested_list_and_skips_non_dicts(monkeypatch):
    monkeypatch.setattr(api, "_fetch_organization_ids", lambda: [1, 2])
    monkeypatch.setattr(api.time, "sleep", lambda *_: None)

    responses = {
        "orgId=1": {"total": 1, "results": ["junk", {"id": 1, "job_title": "A", "deadline_date": "2026-01-01T00:00:00Z"}]},
        "orgId=2": None,
    }
    monkeypatch.setattr(
        api,
        "_make_request_with_retry",
        lambda url: next(v for k, v in responses.items() if k in url),
    )

    jobs = api.fetch_all_jobs()
    assert [j["job_title"] for j in jobs] == ["A"]
