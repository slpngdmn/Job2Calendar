from filter import filter_matching_jobs


def test_returns_empty_when_no_keywords():
    assert filter_matching_jobs([{"job_title": "Officer"}], []) == []


def test_returns_empty_when_no_jobs():
    assert filter_matching_jobs([], ["officer"]) == []


def test_matches_are_case_insensitive_and_partial():
    jobs = [
        {"job_title": "Assistant PROGRAMMER"},
        {"job_title": "Office Sohayok"},
    ]
    result = filter_matching_jobs(jobs, ["Programmer"])
    assert result == [jobs[0]]


def test_skips_jobs_with_missing_or_empty_title():
    jobs = [
        {"org_name": "Some Org"},
        {"job_title": None},
        {"job_title": ""},
        {"job_title": "Programmer"},
    ]
    assert filter_matching_jobs(jobs, ["programmer"]) == [jobs[3]]


def test_non_string_title_is_coerced():
    jobs = [{"job_title": 12345}]
    assert filter_matching_jobs(jobs, ["234"]) == jobs


def test_job_matching_multiple_keywords_is_kept_once():
    jobs = [{"job_title": "Assistant Programmer"}]
    assert filter_matching_jobs(jobs, ["assistant", "programmer"]) == jobs
