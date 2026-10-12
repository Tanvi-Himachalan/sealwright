"""One failing certificate must not stop the rest of the job."""
from app.services import pdf_generator


def test_one_generation_failure_does_not_stop_others(client, job_payload, monkeypatch):
    original = pdf_generator.render_certificate

    def flaky(path, **kwargs):
        if kwargs["name"] == "Arjun Mehta":
            raise RuntimeError("disk exploded")
        return original(path, **kwargs)

    monkeypatch.setattr(pdf_generator, "render_certificate", flaky)
    job = client.post("/api/jobs", json=job_payload).json()

    assert job["status"] == "completed_with_errors"
    assert job["counts"] == {"generated": 2, "invalid": 0, "failed": 1, "pending": 0}

    failed = client.get(f"/api/jobs/{job['id']}/certificates?status=failed").json()["items"]
    assert len(failed) == 1
    assert failed[0]["name"] == "Arjun Mehta"
    assert "disk exploded" in failed[0]["error"]
    assert failed[0]["file_url"] is None


def test_unrenderable_name_fails_only_that_row(client):
    payload = {
        "title": "Course", "issuer": "Org",
        "recipients": [{"name": "Good Person"}, {"name": "தன்வி சர்மா"}, {"name": "Another Good"}],
    }
    job = client.post("/api/jobs", json=payload).json()
    assert job["counts"]["generated"] == 2
    assert job["counts"]["failed"] == 1


def test_retry_regenerates_failed_certificates(client, job_payload, monkeypatch):
    original = pdf_generator.render_certificate
    state = {"broken": True}

    def flaky(path, **kwargs):
        if state["broken"] and kwargs["name"] == "Meera Iyer":
            raise RuntimeError("temporary glitch")
        return original(path, **kwargs)

    monkeypatch.setattr(pdf_generator, "render_certificate", flaky)
    job = client.post("/api/jobs", json=job_payload).json()
    assert job["counts"]["failed"] == 1

    state["broken"] = False  # the problem is fixed
    retried = client.post(f"/api/jobs/{job['id']}/retry")
    assert retried.status_code == 202

    final = client.get(f"/api/jobs/{job['id']}").json()
    assert final["status"] == "completed"
    assert final["counts"]["generated"] == 3


def test_retry_with_nothing_failed_is_409(client, job_payload):
    job = client.post("/api/jobs", json=job_payload).json()
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 409
