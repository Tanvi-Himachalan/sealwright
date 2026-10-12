"""Background processing.

Design: a small ThreadPoolExecutor inside the API process. The DATABASE is the
queue / source of truth (each certificate row is `pending` until generated), so:
  * the HTTP request returns immediately (202 Accepted),
  * progress is visible by polling the job,
  * after a crash/restart, unfinished jobs are simply picked up again
    (see `resume_unfinished_jobs`).
For multi-server scale you would swap this module for Celery/RQ + Redis; the
rest of the application would not change.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import Certificate, CertStatus, Job, JobStatus, utcnow
from . import pdf_generator
from .jobs import finalize_job
from .signing import sign

log = logging.getLogger("sealwright.processor")
_executor = ThreadPoolExecutor(max_workers=settings.worker_threads, thread_name_prefix="sealwright")


def certificate_path(job_id: str, code: str):
    return settings.storage_dir / job_id / f"{code}.pdf"


def dispatch(job_id: str) -> None:
    """Hand a job to the worker pool (or run it right now in inline/test mode)."""
    if settings.process_inline:
        process_job(job_id)
    else:
        _executor.submit(_safe_process, job_id)


def _safe_process(job_id: str) -> None:
    try:
        process_job(job_id)
    except Exception:  # never let a worker thread die silently
        log.exception("Unexpected error while processing job %s", job_id)


def process_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.PROCESSING
        job.started_at = job.started_at or utcnow()
        db.commit()

        pending_ids = db.scalars(
            select(Certificate.id)
            .where(Certificate.job_id == job_id, Certificate.status == CertStatus.PENDING)
            .order_by(Certificate.row_number)
        ).all()

        for cert_id in pending_ids:
            _generate_one(db, job_id, cert_id)  # one bad certificate never stops the loop
            if settings.generation_delay_ms:
                time.sleep(settings.generation_delay_ms / 1000)

        job = db.get(Job, job_id)
        finalize_job(db, job)
        db.commit()
    finally:
        db.close()


def _generate_one(db, job_id: str, cert_id: int) -> None:
    job = db.get(Job, job_id)
    cert = db.get(Certificate, cert_id)
    try:
        path = certificate_path(job.id, cert.code)
        pdf_generator.render_certificate(
            path,
            name=cert.recipient_name,
            remark=cert.remark,
            award_title=job.award_title,
            title=job.title,
            issuer=job.issuer,
            issue_date=job.issue_date,
            signatory_name=job.signatory_name,
            signatory_title=job.signatory_title,
            code=cert.code,
            verify_url=f"{settings.public_base_url.rstrip('/')}/verify/{cert.code}",
        )
        cert.signature = sign(cert.code, cert.recipient_name, job.title, job.issuer, job.issue_date)
        cert.file_path = f"{job.id}/{cert.code}.pdf"
        cert.status = CertStatus.GENERATED
        cert.error = None
        cert.generated_at = utcnow()
        db.commit()
    except Exception as exc:  # isolate the failure to THIS certificate
        db.rollback()
        cert = db.get(Certificate, cert_id)
        cert.status = CertStatus.FAILED
        message = str(exc) if isinstance(exc, pdf_generator.CertificateRenderError) else f"{type(exc).__name__}: {exc}"
        cert.error = message[:500]
        db.commit()
        log.warning("Certificate %s (row %s) failed: %s", cert_id, cert.row_number, cert.error)


def resume_unfinished_jobs() -> int:
    """Called on startup: pick up jobs that were queued/processing when the server stopped."""
    db = SessionLocal()
    try:
        ids = db.scalars(select(Job.id).where(Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]))).all()
    finally:
        db.close()
    for job_id in ids:
        dispatch(job_id)
    return len(ids)
