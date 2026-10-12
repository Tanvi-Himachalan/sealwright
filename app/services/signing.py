"""Verification codes and tamper-evident signatures.

Every certificate gets:
  * a short public code  (SW-7K3M9XQ2PA)  - printed on the PDF and in the QR URL
  * an HMAC-SHA256 signature over the important fields, using SECRET_KEY

When someone verifies a certificate we recompute the signature from the stored
data. If a database row was edited by hand (name, date...), the signature no
longer matches and the verify page says so.
"""
import hashlib
import hmac
import secrets
from datetime import date

from ..config import settings

# No 0/O/1/I/L so codes are easy to read aloud or type.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_code() -> str:
    return "SW-" + "".join(secrets.choice(_ALPHABET) for _ in range(10))


def _message(code: str, name: str, title: str, issuer: str, issue_date: date) -> bytes:
    return "\x1f".join([code, name, title, issuer, issue_date.isoformat()]).encode("utf-8")


def sign(code: str, name: str, title: str, issuer: str, issue_date: date) -> str:
    key = settings.secret_key.encode("utf-8")
    return hmac.new(key, _message(code, name, title, issuer, issue_date), hashlib.sha256).hexdigest()


def is_signature_valid(signature: str | None, code: str, name: str, title: str, issuer: str, issue_date: date) -> bool:
    if not signature:
        return False
    expected = sign(code, name, title, issuer, issue_date)
    return hmac.compare_digest(signature, expected)
