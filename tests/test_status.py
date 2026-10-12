"""Job status and progress reporting."""
from app.models import Job, JobStatus
from app.database import SessionLocal


def test_completed_job_reports_full_progress(client, job_payload):
    job = client.post("/api/jobs", json=job_payload).json()
    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "completed"
    assert status["counts"] == {"generated": 3, "invalid": 0, "failed": 0, "pending": 0}
    assert status["processed"] == 3
    assert status["progress_percent"] == 100.0
    assert status["started_at"] and status["finished_at"]


def test_partial_progress_is_reported(client, job_payload):
    """Simulate a job that is half way through: some rows pending, status processing."""
    from app.models import Certificate, CertStatus
    job = client.post("/api/jobs", json=job_payload).json()
    with SessionLocal() as db:
        cert = db.query(Certificate).filter_by(job_id=job["id"], row_number=3).one()
        cert.status = CertStatus.PENDING
        db.get(Job, job["id"]).status = JobStatus.PROCESSING
        db.commit()
    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "processing"
    assert status["counts"]["pending"] == 1
    assert status["progress_percent"] == 66.7


def test_job_list_returns_newest_first(client, job_payload):
    first = client.post("/api/jobs", json=job_payload).json()
    second = client.post("/api/jobs", json={**job_payload, "title": "Second Course"}).json()
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert ids[:2] == [second["id"], first["id"]]


def test_certificate_list_supports_filter_and_paging(client, job_payload):
    job = client.post("/api/jobs", json=job_payload).json()
    page = client.get(f"/api/jobs/{job['id']}/certificates?limit=2&offset=1").json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert page["items"][0]["row_number"] == 2
    assert client.get(f"/api/jobs/{job['id']}/certificates?status=bogus").status_code == 422


def test_unfinished_jobs_resume_on_startup(client, job_payload):
    from app.models import Certificate, CertStatus
    from app.services.processor import resume_unfinished_jobs
    job = client.post("/api/jobs", json=job_payload).json()
    with SessionLocal() as db:  # pretend the server crashed half way
        db.query(Certificate).filter_by(job_id=job["id"], row_number=2).update({"status": CertStatus.PENDING})
        db.get(Job, job["id"]).status = JobStatus.PROCESSING
        db.commit()
    assert resume_unfinished_jobs() == 1
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "completed"
