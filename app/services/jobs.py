"""Business logic around jobs: create, count, retry, serialise."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Certificate, CertStatus, Job, JobStatus, utcnow
from ..schemas import CertificateOut, JobCounts, JobLinks, JobOut
from .signing import new_code
from .validation import validate_batch


class JobBusyError(Exception):
    """The job is still being processed."""


class NothingToRetryError(Exception):
    """No failed certificates exist in the job."""


def create_job(
    db: Session,
    *,
    title: str,
    issuer: str,
    award_title: str,
    issue_date: date | None,
    signatory_name: str | None,
    signatory_title: str | None,
    recipients: list[dict],
) -> Job:
    """Validate every recipient, store one row each, return the (queued) job.

    Invalid rows are stored with status=invalid + a reason; valid rows get a
    verification code and wait as `pending` for the background worker.
    """
    job = Job(
        title=title,
        issuer=issuer,
        award_title=award_title or "Certificate of Completion",
        issue_date=issue_date or date.today(),
        signatory_name=signatory_name or None,
        signatory_title=signatory_title or None,
        status=JobStatus.QUEUED,
        total=len(recipients),
    )
    for row in validate_batch(recipients):
        if row.clean:
            cert = Certificate(
                row_number=row.row_number,
                recipient_name=row.clean.name,
                recipient_email=row.clean.email,
                remark=row.clean.remark,
                status=CertStatus.PENDING,
                code=new_code(),
            )
        else:
            cert = Certificate(
                row_number=row.row_number,
                recipient_name=row.raw_name,
                recipient_email=(row.raw_email or None) and row.raw_email[:254],
                remark=(row.raw_remark or None) and row.raw_remark[:120],
                status=CertStatus.INVALID,
                error=row.error,
            )
        job.certificates.append(cert)

    db.add(job)
    db.flush()
    if not any(c.status == CertStatus.PENDING for c in job.certificates):
        finalize_job(db, job)  # nothing to generate: every row was invalid
    db.commit()
    return job


def count_by_status(db: Session, job_id: str) -> JobCounts:
    rows = db.execute(
        select(Certificate.status, func.count()).where(Certificate.job_id == job_id).group_by(Certificate.status)
    ).all()
    data = {status.value: n for status, n in rows}
    return JobCounts(
        generated=data.get("generated", 0),
        invalid=data.get("invalid", 0),
        failed=data.get("failed", 0),
        pending=data.get("pending", 0),
    )


def finalize_job(db: Session, job: Job) -> None:
    counts = count_by_status(db, job.id)
    if counts.generated == job.total:
        job.status = JobStatus.COMPLETED
    elif counts.generated == 0:
        job.status = JobStatus.FAILED
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS
    job.finished_at = utcnow()


def retry_failed(db: Session, job: Job) -> int:
    """Re-queue certificates whose *generation* failed (invalid input is not retried)."""
    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
        raise JobBusyError()
    failed = db.scalars(
        select(Certificate).where(Certificate.job_id == job.id, Certificate.status == CertStatus.FAILED)
    ).all()
    if not failed:
        raise NothingToRetryError()
    for cert in failed:
        cert.status = CertStatus.PENDING
        cert.error = None
    job.status = JobStatus.QUEUED
    job.finished_at = None
    db.commit()
    return len(failed)


# ------------------------------------------------------------------ serialisers
def job_to_out(db: Session, job: Job) -> JobOut:
    counts = count_by_status(db, job.id)
    processed = counts.generated + counts.invalid + counts.failed
    progress = round(processed / job.total * 100, 1) if job.total else 100.0
    base = f"/api/jobs/{job.id}"
    return JobOut(
        id=job.id,
        title=job.title,
        issuer=job.issuer,
        award_title=job.award_title,
        issue_date=job.issue_date,
        signatory_name=job.signatory_name,
        signatory_title=job.signatory_title,
        status=job.status,
        total=job.total,
        counts=counts,
        processed=processed,
        progress_percent=progress,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        links=JobLinks(
            status=base,
            certificates=f"{base}/certificates",
            download_zip=f"{base}/download",
            retry_failed=f"{base}/retry",
        ),
    )


def cert_to_out(cert: Certificate) -> CertificateOut:
    generated = cert.status == CertStatus.GENERATED
    return CertificateOut(
        row_number=cert.row_number,
        name=cert.recipient_name,
        email=cert.recipient_email,
        remark=cert.remark,
        status=cert.status,
        error=cert.error,
        code=cert.code if generated else None,
        generated_at=cert.generated_at,
        file_url=f"/api/certificates/{cert.code}/file" if generated else None,
        verify_url=f"{settings.public_base_url.rstrip('/')}/verify/{cert.code}" if generated else None,
    )
