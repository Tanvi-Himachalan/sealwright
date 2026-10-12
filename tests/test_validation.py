"""Input validation: request level (422) and recipient level (marked invalid)."""
import pytest

from app.services.validation import validate_batch, validate_recipient


# ---- request-level: the whole request is malformed -> 422
def test_missing_title_is_rejected(client):
    res = client.post("/api/jobs", json={"issuer": "Org", "recipients": [{"name": "Tanvi"}]})
    assert res.status_code == 422


def test_empty_recipient_list_is_rejected(client):
    res = client.post("/api/jobs", json={"title": "Course", "issuer": "Org", "recipients": []})
    assert res.status_code == 422


def test_too_many_recipients_is_rejected(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_recipients", 2)
    payload = {"title": "Course", "issuer": "Org", "recipients": [{"name": f"Person {i}"} for i in range(3)]}
    assert client.post("/api/jobs", json=payload).status_code == 422


# ---- recipient-level: only that row is invalid, the rest continue
def test_invalid_recipients_do_not_block_valid_ones(client):
    payload = {
        "title": "Course", "issuer": "Org",
        "recipients": [
            {"name": "Valid Person", "email": "ok@example.com"},
            {"name": "", "email": "x@example.com"},
            {"name": "Bad Email", "email": "not-an-email"},
            {"name": 12345},
        ],
    }
    job = client.post("/api/jobs", json=payload).json()
    assert job["counts"] == {"generated": 1, "invalid": 3, "failed": 0, "pending": 0}
    assert job["status"] == "completed_with_errors"

    rows = client.get(f"/api/jobs/{job['id']}/certificates?status=invalid").json()["items"]
    assert [r["row_number"] for r in rows] == [2, 3, 4]
    assert "name is required" in rows[0]["error"]
    assert "email" in rows[1]["error"]
    assert "must be text" in rows[2]["error"]


def test_duplicate_email_in_same_job_is_flagged(client):
    payload = {
        "title": "Course", "issuer": "Org",
        "recipients": [
            {"name": "First Person", "email": "same@example.com"},
            {"name": "Second Person", "email": "SAME@example.com"},
        ],
    }
    job = client.post("/api/jobs", json=payload).json()
    assert job["counts"]["generated"] == 1
    bad = client.get(f"/api/jobs/{job['id']}/certificates?status=invalid").json()["items"][0]
    assert "duplicate email" in bad["error"]


def test_all_rows_invalid_marks_job_failed(client):
    job = client.post("/api/jobs", json={"title": "Course", "issuer": "Org", "recipients": [{"name": ""}]}).json()
    assert job["status"] == "failed"
    assert job["progress_percent"] == 100.0


@pytest.mark.parametrize(
    "name,ok",
    [("Tanvi Sharma", True), ("  Tanvi   Sharma  ", True), ("A", False), ("x" * 81, False), ("1234", False), ("Bad\x00Name", False)],
)
def test_name_rules(name, ok):
    clean, error = validate_recipient(name, None, None)
    assert (clean is not None) == ok
    assert (error is None) == ok


def test_name_whitespace_is_normalised():
    clean, _ = validate_recipient("  Tanvi    Sharma ", " T@Example.COM ", "  well   done ")
    assert clean.name == "Tanvi Sharma"
    assert clean.email == "t@example.com"
    assert clean.remark == "well done"


def test_validate_batch_keeps_row_numbers():
    rows = validate_batch([{"name": "Good Name"}, {"name": ""}])
    assert [r.row_number for r in rows] == [1, 2]
    assert rows[0].error is None and rows[1].error
