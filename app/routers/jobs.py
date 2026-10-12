"""Job + certificate endpoints."""
import csv
import io
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..config import settings
from ..database import get_db
from ..models import Certificate, CertStatus, Job
from ..schemas import CertificatePage, JobCreate, JobMeta, JobOut
from ..services import jobs as job_service
from ..services.processor import dispatch

router = APIRouter(prefix="/api", tags=["jobs"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB is ~30k CSV rows, far above MAX_RECIPIENTS

_COLUMN_ALIASES = {
    "name": {"name", "full name", "full_name", "fullname", "recipient", "participant", "student"},
    "email": {"email", "e-mail", "email address", "email_address", "mail"},
    "remark": {"remark", "remarks", "note", "notes", "comment", "comments", "grade"},
}


def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ----------------------------------------------------------------------------- create
@router.post("/jobs", response_model=JobOut, status_code=202, summary="Create a bulk certificate job (JSON)")
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    """Accepts the whole recipient list in ONE request and returns immediately (202).

    Poll `GET /api/jobs/{id}` for progress. Bad recipients do not reject the
    request: they are stored as `invalid` with a reason.
    """
    job = job_service.create_job(
        db,
        title=payload.title,
        issuer=payload.issuer,
        award_title=payload.award_title,
        issue_date=payload.issue_date,
        signatory_name=payload.signatory_name,
        signatory_title=payload.signatory_title,
        recipients=[r.model_dump() for r in payload.recipients],
    )
    if job.status.value == "queued":
        dispatch(job.id)
    db.refresh(job)
    return job_service.job_to_out(db, job)


def _parse_csv(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8 encoded") from None
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "CSV is empty")

    mapping: dict[str, str] = {}  # canonical field -> actual header
    for header in reader.fieldnames:
        key = (header or "").strip().lower()
        for field, aliases in _COLUMN_ALIASES.items():
            if key in aliases and field not in mapping:
                mapping[field] = header
    if "name" not in mapping:
        raise HTTPException(422, "CSV needs a 'name' column (optional: 'email', 'remark')")

    recipients = []
    for row in reader:
        values = {field: (row.get(header) or "").strip() for field, header in mapping.items()}
        if not any(values.values()):
            continue  # skip fully blank lines
        recipients.append(values)
        if len(recipients) > settings.max_recipients:
            raise HTTPException(422, f"A single job can contain at most {settings.max_recipients} recipients")
    if not recipients:
        raise HTTPException(422, "CSV has no recipient rows")
    return recipients


@router.post("/jobs/upload", response_model=JobOut, status_code=202, summary="Create a bulk job from a CSV file")
async def create_job_from_csv(
    file: UploadFile = File(..., description="CSV with columns: name, email (optional), remark (optional)"),
    title: str = Form(...),
    issuer: str = Form(...),
    award_title: str = Form("Certificate of Completion"),
    issue_date: date | None = Form(None),
    signatory_name: str | None = Form(None),
    signatory_title: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        meta = JobMeta(
            title=title, issuer=issuer, award_title=award_title, issue_date=issue_date,
            signatory_name=signatory_name or None, signatory_title=signatory_title or None,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "CSV file is larger than 2 MB")
    recipients = _parse_csv(raw)

    job = job_service.create_job(db, **meta.model_dump(), recipients=recipients)
    if job.status.value == "queued":
        dispatch(job.id)
    db.refresh(job)
    return job_service.job_to_out(db, job)


# ----------------------------------------------------------------------------- read
@router.get("/jobs", response_model=list[JobOut], summary="Recent jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit)).all()
    return [job_service.job_to_out(db, j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Job status and progress")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return job_service.job_to_out(db, _get_job_or_404(db, job_id))


@router.get("/jobs/{job_id}/certificates", response_model=CertificatePage, summary="Per-recipient results")
def list_certificates(
    job_id: str,
    status: CertStatus | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _get_job_or_404(db, job_id)
    query = select(Certificate).where(Certificate.job_id == job_id)
    if status:
        query = query.where(Certificate.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Certificate.row_number).limit(limit).offset(offset)).all()
    return CertificatePage(total=total, limit=limit, offset=offset, items=[job_service.cert_to_out(c) for c in items])


# ----------------------------------------------------------------------------- actions
@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202, summary="Retry failed certificates")
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    try:
        job_service.retry_failed(db, job)
    except job_service.JobBusyError:
        raise HTTPException(409, "Job is still processing") from None
    except job_service.NothingToRetryError:
        raise HTTPException(409, "No failed certificates to retry (invalid rows must be corrected and resubmitted)") from None
    dispatch(job.id)
    db.refresh(job)
    return job_service.job_to_out(db, job)


@router.get("/jobs/{job_id}/download", summary="Download every generated certificate as a ZIP")
def download_zip(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    certs = db.scalars(select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.row_number)).all()
    generated = [c for c in certs if c.status == CertStatus.GENERATED]
    if not generated:
        raise HTTPException(409, "No certificates have been generated yet")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in generated:
            file = settings.storage_dir / (c.file_path or "")
            if file.is_file():
                safe = "".join(ch if ch.isalnum() else "_" for ch in c.recipient_name).strip("_")[:40] or "recipient"
                zf.write(file, f"{c.row_number:04d}_{safe}_{c.code}.pdf")
        report = io.StringIO()
        writer = csv.writer(report)
        writer.writerow(["row", "name", "email", "status", "verification_code", "error"])
        for c in certs:
            writer.writerow([c.row_number, c.recipient_name, c.recipient_email or "", c.status.value, c.code or "", c.error or ""])
        zf.writestr("report.csv", report.getvalue())

    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"certificates_{job.id[:8]}.zip",
        background=BackgroundTask(os.unlink, tmp.name),  # delete the temp file after sending
    )


@router.get("/certificates/{code}/file", summary="Download / view one certificate PDF")
def get_certificate_file(code: str, download: bool = False, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.code == code))
    if cert is None or cert.status != CertStatus.GENERATED or not cert.file_path:
        raise HTTPException(404, "Certificate not found")
    path: Path = settings.storage_dir / cert.file_path
    if not path.is_file():
        raise HTTPException(404, "Certificate file is missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{code}.pdf",
        content_disposition_type="attachment" if download else "inline",
    )
