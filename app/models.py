"""Database tables.

Job 1 ──── * Certificate

A Job is one bulk request. A Certificate row exists for EVERY submitted
recipient (even invalid ones) so the client can see exactly what happened to
each input row.
"""
import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"                         # every row generated
    COMPLETED_WITH_ERRORS = "completed_with_errors"  # some rows invalid/failed
    FAILED = "failed"                               # nothing could be generated


class CertStatus(str, enum.Enum):
    PENDING = "pending"      # waiting to be generated
    GENERATED = "generated"  # PDF exists
    INVALID = "invalid"      # bad input data, rejected before generation
    FAILED = "failed"        # valid input but generation crashed (retryable)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(160))           # event / course name
    issuer: Mapped[str] = mapped_column(String(160))          # organisation name
    award_title: Mapped[str] = mapped_column(String(80), default="Certificate of Completion")
    issue_date: Mapped[date] = mapped_column(Date)
    signatory_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signatory_title: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False), default=JobStatus.QUEUED, index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="Certificate.row_number"
    )


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (Index("ix_cert_job_status", "job_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)          # 1-based position in the request

    recipient_name: Mapped[str] = mapped_column(String(200), default="")
    recipient_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(120), nullable=True)

    status: Mapped[CertStatus] = mapped_column(Enum(CertStatus, native_enum=False), default=CertStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)  # public verification ID
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True)           # HMAC proof
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="certificates")
