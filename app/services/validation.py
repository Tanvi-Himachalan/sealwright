"""Recipient validation.

Rules are intentionally simple and explained to the client in plain English,
because the error text is shown to the end user in the UI.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
NAME_MIN, NAME_MAX = 2, 80
REMARK_MAX = 120


@dataclass
class CleanRecipient:
    name: str
    email: str | None
    remark: str | None


@dataclass
class ValidatedRow:
    row_number: int
    raw_name: str
    raw_email: str | None
    raw_remark: str | None
    clean: CleanRecipient | None
    error: str | None


def _has_control_chars(text: str) -> bool:
    return any(unicodedata.category(ch).startswith("C") for ch in text)


def _normalise(text: str) -> str:
    """NFC-normalise and collapse runs of whitespace."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _as_text(value: Any) -> str | None:
    return None if value is None else (value if isinstance(value, str) else None)


def validate_recipient(name: Any, email: Any, remark: Any) -> tuple[CleanRecipient | None, str | None]:
    errors: list[str] = []

    # ---- name (required) ----
    clean_name = ""
    if name is None or (isinstance(name, str) and not name.strip()):
        errors.append("name is required")
    elif not isinstance(name, str):
        errors.append("name must be text")
    else:
        clean_name = _normalise(name)
        if _has_control_chars(clean_name):
            errors.append("name contains invalid control characters")
        elif len(clean_name) < NAME_MIN:
            errors.append(f"name must be at least {NAME_MIN} characters")
        elif len(clean_name) > NAME_MAX:
            errors.append(f"name must be at most {NAME_MAX} characters")
        elif not any(ch.isalpha() for ch in clean_name):
            errors.append("name must contain letters")

    # ---- email (optional, but must be valid when present) ----
    clean_email: str | None = None
    if email is not None and not (isinstance(email, str) and not email.strip()):
        if not isinstance(email, str):
            errors.append("email must be text")
        else:
            candidate = email.strip().lower()
            if len(candidate) > 254 or not EMAIL_RE.match(candidate):
                errors.append("email is not a valid address")
            else:
                clean_email = candidate

    # ---- remark (optional short line printed under the name) ----
    clean_remark: str | None = None
    if remark is not None and not (isinstance(remark, str) and not remark.strip()):
        if not isinstance(remark, str):
            errors.append("remark must be text")
        else:
            candidate = _normalise(remark)
            if _has_control_chars(candidate):
                errors.append("remark contains invalid control characters")
            elif len(candidate) > REMARK_MAX:
                errors.append(f"remark must be at most {REMARK_MAX} characters")
            else:
                clean_remark = candidate

    if errors:
        return None, "; ".join(errors)
    return CleanRecipient(clean_name, clean_email, clean_remark), None


def validate_batch(recipients: list[dict[str, Any]]) -> list[ValidatedRow]:
    """Validate every recipient and flag duplicate emails inside the same job."""
    rows: list[ValidatedRow] = []
    seen_emails: dict[str, int] = {}

    for index, raw in enumerate(recipients, start=1):
        name, email, remark = raw.get("name"), raw.get("email"), raw.get("remark")
        clean, error = validate_recipient(name, email, remark)

        if clean and clean.email:
            first = seen_emails.get(clean.email)
            if first is not None:
                clean, error = None, f"duplicate email (already used in row {first})"
            else:
                seen_emails[clean.email] = index

        rows.append(
            ValidatedRow(
                row_number=index,
                raw_name=(_as_text(name) or (str(name) if name is not None else ""))[:200],
                raw_email=(_as_text(email) or (str(email) if email is not None else None)),
                raw_remark=_as_text(remark),
                clean=clean,
                error=error,
            )
        )
    return rows
