"""Public verification endpoint (what the QR code on each certificate opens)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Certificate, CertStatus
from ..schemas import VerifyOut
from ..services.signing import is_signature_valid

router = APIRouter(prefix="/api", tags=["verify"])


@router.get("/verify/{code}", response_model=VerifyOut, summary="Verify a certificate by its code")
def verify(code: str, db: Session = Depends(get_db)):
    code = code.strip().upper()
    cert = db.scalar(select(Certificate).where(Certificate.code == code))
    if cert is None or cert.status != CertStatus.GENERATED:
        return VerifyOut(valid=False, code=code, message="No certificate with this ID was issued by this system.")

    job = cert.job
    intact = is_signature_valid(cert.signature, cert.code, cert.recipient_name, job.title, job.issuer, job.issue_date)
    if not intact:
        return VerifyOut(
            valid=False, code=code,
            message="Warning: this record exists but its signature does not match. The data may have been altered.",
        )
    return VerifyOut(
        valid=True,
        code=code,
        recipient_name=cert.recipient_name,
        remark=cert.remark,
        award_title=job.award_title,
        title=job.title,
        issuer=job.issuer,
        issue_date=job.issue_date,
        signatory_name=job.signatory_name,
        generated_at=cert.generated_at,
        message="This certificate is authentic.",
    )
