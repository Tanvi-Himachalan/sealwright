"""Certificate generation (the PDF itself)."""
from datetime import date

from pypdf import PdfReader

from app.services.pdf_generator import CertificateRenderError, render_certificate
from app.services.signing import is_signature_valid, new_code, sign


def _render(tmp_path, **overrides):
    args = dict(
        name="Tanvi Sharma", remark="with Distinction", award_title="Certificate of Completion",
        title="Python Bootcamp 2026", issuer="Frontier Academy", issue_date=date(2026, 10, 8),
        signatory_name="Dr. A. Rao", signatory_title="Program Director",
        code="SW-TESTCODE12", verify_url="http://testserver/verify/SW-TESTCODE12",
    )
    args.update(overrides)
    path = tmp_path / "cert.pdf"
    render_certificate(path, **args)
    return path


def test_pdf_contains_recipient_specific_data(tmp_path):
    path = _render(tmp_path)
    text = PdfReader(str(path)).pages[0].extract_text()
    for expected in ("Tanvi Sharma", "Python Bootcamp 2026", "FRONTIER ACADEMY", "SW-TESTCODE12", "08 October 2026"):
        assert expected in text


def test_pdf_is_single_landscape_page(tmp_path):
    reader = PdfReader(str(_render(tmp_path)))
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert box.width > box.height


def test_very_long_name_and_title_still_render(tmp_path):
    path = _render(tmp_path, name="A" * 40 + " " + "B" * 39, title="Very long course title " * 12)
    assert path.stat().st_size > 1000


def test_unsupported_characters_raise_clear_error(tmp_path):
    try:
        _render(tmp_path, name="தன்வி")
    except CertificateRenderError as exc:
        assert "cannot render" in str(exc)
    else:
        raise AssertionError("expected CertificateRenderError")


def test_no_half_written_file_left_behind(tmp_path):
    try:
        _render(tmp_path, name="தன்வி")
    except CertificateRenderError:
        pass
    assert list(tmp_path.glob("*")) == []


def test_generated_files_exist_after_job(client, job_payload):
    from app.config import settings
    job = client.post("/api/jobs", json=job_payload).json()
    pdfs = list((settings.storage_dir / job["id"]).glob("*.pdf"))
    assert len(pdfs) == 3


def test_codes_are_unique_and_well_formed():
    codes = {new_code() for _ in range(500)}
    assert len(codes) == 500
    assert all(c.startswith("SW-") and len(c) == 13 for c in codes)


def test_signature_detects_tampering():
    sig = sign("SW-AAA", "Tanvi", "Course", "Org", date(2026, 1, 1))
    assert is_signature_valid(sig, "SW-AAA", "Tanvi", "Course", "Org", date(2026, 1, 1))
    assert not is_signature_valid(sig, "SW-AAA", "Someone Else", "Course", "Org", date(2026, 1, 1))
    assert not is_signature_valid(None, "SW-AAA", "Tanvi", "Course", "Org", date(2026, 1, 1))
