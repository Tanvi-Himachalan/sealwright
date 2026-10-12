"""Retrieving generated certificates + public verification."""
import io
import zipfile

from pypdf import PdfReader
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Certificate


def _create(client, job_payload):
    job = client.post("/api/jobs", json=job_payload).json()
    items = client.get(f"/api/jobs/{job['id']}/certificates").json()["items"]
    return job, items


def test_download_single_certificate_pdf(client, job_payload):
    _, items = _create(client, job_payload)
    res = client.get(items[0]["file_url"])
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert "Tanvi Sharma" in PdfReader(io.BytesIO(res.content)).pages[0].extract_text()


def test_download_flag_sets_attachment_header(client, job_payload):
    _, items = _create(client, job_payload)
    res = client.get(items[0]["file_url"] + "?download=true")
    assert res.headers["content-disposition"].startswith("attachment")


def test_unknown_certificate_is_404(client):
    assert client.get("/api/certificates/SW-NOPE/file").status_code == 404


def test_zip_contains_all_pdfs_and_report(client, job_payload):
    job, _ = _create(client, job_payload)
    res = client.get(f"/api/jobs/{job['id']}/download")
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()
    assert sum(n.endswith(".pdf") for n in names) == 3
    assert "report.csv" in names
    assert "Arjun" in "".join(names)


def test_zip_with_nothing_generated_is_409(client):
    job = client.post("/api/jobs", json={"title": "Course", "issuer": "Org", "recipients": [{"name": ""}]}).json()
    assert client.get(f"/api/jobs/{job['id']}/download").status_code == 409


def test_failed_certificate_file_is_not_retrievable(client):
    job = client.post("/api/jobs", json={"title": "Course", "issuer": "Org", "recipients": [{"name": "தன்வி"}]}).json()
    with SessionLocal() as db:
        cert = db.scalar(select(Certificate).where(Certificate.job_id == job["id"]))
        assert cert.status.value == "failed"
        code = cert.code
    assert client.get(f"/api/certificates/{code}/file").status_code == 404


def test_verify_valid_certificate(client, job_payload):
    _, items = _create(client, job_payload)
    code = items[1]["code"]
    body = client.get(f"/api/verify/{code}").json()
    assert body["valid"] is True
    assert body["recipient_name"] == "Arjun Mehta"
    assert body["remark"] == "with Distinction"
    assert body["issuer"] == "Frontier Academy"


def test_verify_unknown_code(client):
    assert client.get("/api/verify/SW-UNKNOWN123").json()["valid"] is False


def test_verify_detects_tampered_record(client, job_payload):
    _, items = _create(client, job_payload)
    code = items[0]["code"]
    with SessionLocal() as db:
        cert = db.scalar(select(Certificate).where(Certificate.code == code))
        cert.recipient_name = "Forged Person"
        db.commit()
    body = client.get(f"/api/verify/{code}").json()
    assert body["valid"] is False
    assert "altered" in body["message"]
