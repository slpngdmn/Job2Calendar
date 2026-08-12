import json

import storage


def test_load_keywords_missing_file(tmp_path):
    assert storage.load_keywords(str(tmp_path / "nope.json")) == []


def test_load_keywords_strips_and_stringifies(tmp_path):
    path = tmp_path / "keywords.json"
    path.write_text(json.dumps(["  Programmer ", 42]), encoding="utf-8")
    assert storage.load_keywords(str(path)) == ["Programmer", "42"]


def test_load_keywords_rejects_non_list(tmp_path):
    path = tmp_path / "keywords.json"
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert storage.load_keywords(str(path)) == []


def test_load_keywords_invalid_json(tmp_path):
    path = tmp_path / "keywords.json"
    path.write_text("{not json", encoding="utf-8")
    assert storage.load_keywords(str(path)) == []


def test_load_keywords_unexpected_error(tmp_path, monkeypatch):
    path = tmp_path / "keywords.json"
    path.write_text("[]", encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(storage, "open", boom, raising=False)
    assert storage.load_keywords(str(path)) == []


def test_load_processed_jobs_missing_file(tmp_path):
    assert storage.load_processed_jobs(str(tmp_path / "nope.json")) == set()


def test_load_processed_jobs_converts_to_string_set(tmp_path):
    path = tmp_path / "processed.json"
    path.write_text(json.dumps([1, "2", 2]), encoding="utf-8")
    assert storage.load_processed_jobs(str(path)) == {"1", "2"}


def test_load_processed_jobs_rejects_non_list(tmp_path):
    path = tmp_path / "processed.json"
    path.write_text(json.dumps({"ids": [1]}), encoding="utf-8")
    assert storage.load_processed_jobs(str(path)) == set()


def test_load_processed_jobs_invalid_json(tmp_path):
    path = tmp_path / "processed.json"
    path.write_text("[[[", encoding="utf-8")
    assert storage.load_processed_jobs(str(path)) == set()


def test_load_processed_jobs_unexpected_error(tmp_path, monkeypatch):
    path = tmp_path / "processed.json"
    path.write_text("[]", encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk error")

    monkeypatch.setattr(storage, "open", boom, raising=False)
    assert storage.load_processed_jobs(str(path)) == set()


def test_save_processed_jobs_writes_sorted_list(tmp_path):
    path = tmp_path / "processed.json"
    storage.save_processed_jobs(str(path), {"3", "1", "2"})
    assert json.loads(path.read_text(encoding="utf-8")) == ["1", "2", "3"]


def test_save_processed_jobs_roundtrip(tmp_path):
    path = tmp_path / "processed.json"
    storage.save_processed_jobs(str(path), {"10", "20"})
    assert storage.load_processed_jobs(str(path)) == {"10", "20"}


def test_save_processed_jobs_swallows_errors(tmp_path):
    unwritable = tmp_path / "missing_dir" / "processed.json"
    storage.save_processed_jobs(str(unwritable), {"1"})
    assert not unwritable.exists()
