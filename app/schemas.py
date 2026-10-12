"""Pydantic models = the shape of requests and responses."""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings
from .models import CertStatus, JobStatus


class RecipientIn(BaseModel):
    """One recipient as sent by the client.

    Fields are deliberately typed `Any`: if a single recipient has a bad value
    (a number instead of a name, a broken email...) we do NOT want FastAPI to
    reject the whole 5000-row request with a 422. Instead the row is accepted,
    checked by services/validation.py and reported back as `invalid`.
    """

    model_config = ConfigDict(extra="ignore")

    name: Any = None
    email: Any = None
    remark: Any = None


class JobMeta(BaseModel):
    """Job-level (certificate-wide) information. Errors here DO reject the request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=2, max_length=160, description="Event or course name")
    issuer: str = Field(min_length=2, max_length=160, description="Issuing organisation")
    award_title: str = Field(default="Certificate of Completion", min_length=2, max_length=80)
    issue_date: date | None = None
    signatory_name: str | None = Field(default=None, max_length=100)
    signatory_title: str | None = Field(default=None, max_length=100)


class JobCreate(JobMeta):
    recipients: list[RecipientIn] = Field(min_length=1)

    @field_validator("recipients")
    @classmethod
    def _limit(cls, v: list[RecipientIn]) -> list[RecipientIn]:
        if len(v) > settings.max_recipients:
            raise ValueError(f"A single job can contain at most {settings.max_recipients} recipients")
        return v


class JobCounts(BaseModel):
    generated: int = 0
    invalid: int = 0
    failed: int = 0
    pending: int = 0


class JobLinks(BaseModel):
    status: str
    certificates: str
    download_zip: str
    retry_failed: str


class JobOut(BaseModel):
    id: str
    title: str
    issuer: str
    award_title: str
    issue_date: date
    signatory_name: str | None
    signatory_title: str | None
    status: JobStatus
    total: int
    counts: JobCounts
    processed: int
    progress_percent: float
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    links: JobLinks


class CertificateOut(BaseModel):
    row_number: int
    name: str
    email: str | None
    remark: str | None
    status: CertStatus
    error: str | None
    code: str | None
    generated_at: datetime | None
    file_url: str | None
    verify_url: str | None


class CertificatePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CertificateOut]


class VerifyOut(BaseModel):
    valid: bool
    code: str
    recipient_name: str | None = None
    remark: str | None = None
    award_title: str | None = None
    title: str | None = None
    issuer: str | None = None
    issue_date: date | None = None
    signatory_name: str | None = None
    generated_at: datetime | None = None
    message: str
