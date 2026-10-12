"""Certificate rendering with ReportLab (pure Python, no external binaries).

ONE predefined template: landscape A4, navy frame, gold ornaments, a guilloche
rosette in the background, a drawn "seal" and a vector QR code that points to
the public verification page.
"""
import math
import os
from datetime import date
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A4)  # 841.9 x 595.3 pt

NAVY = HexColor("#0f1b3d")
GOLD = HexColor("#b8923a")
GOLD_LIGHT = HexColor("#d9b75f")
GOLD_DARK = HexColor("#8c6d24")
CREAM = HexColor("#fbf7ec")
INK = HexColor("#1b2340")
MUTED = HexColor("#6b7280")


class CertificateRenderError(Exception):
    """Raised when a certificate cannot be drawn (e.g. unsupported characters)."""


# --------------------------------------------------------------------------- helpers
def _ensure_renderable(label: str, text: str | None) -> None:
    """Built-in PDF fonts only cover Windows-1252. Fail loudly instead of printing boxes."""
    if not text:
        return
    for ch in text:
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            raise CertificateRenderError(
                f"{label} contains the character '{ch}' which the certificate font cannot render"
            ) from None


def _fit_size(text: str, font: str, max_size: float, max_width: float, min_size: float = 12) -> float:
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _wrap(text: str, font: str, size: float, max_width: float, max_lines: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if stringWidth(trial, font, size) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while stringWidth(lines[-1] + "...", font, size) > max_width and len(lines[-1]) > 1:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
    return lines


def _spaced_centered(c: canvas.Canvas, text: str, cx: float, y: float, font: str, size: float, spacing: float) -> None:
    width = stringWidth(text, font, size) + spacing * (len(text) - 1)
    t = c.beginText()
    t.setFont(font, size)
    t.setCharSpace(spacing)
    t.setTextOrigin(cx - width / 2, y)
    t.textOut(text)
    t.setCharSpace(0)  # reset, otherwise the spacing leaks into all later text
    c.drawText(t)


def _diamond(c: canvas.Canvas, x: float, y: float, r: float, fill=GOLD) -> None:
    p = c.beginPath()
    p.moveTo(x, y + r)
    p.lineTo(x + r, y)
    p.lineTo(x, y - r)
    p.lineTo(x - r, y)
    p.close()
    c.setFillColor(fill)
    c.drawPath(p, stroke=0, fill=1)


def _rosette(c: canvas.Canvas, cx: float, cy: float, orbit: float, radius: float, n: int, alpha: float) -> None:
    """Guilloche-style flower made of n overlapping circles."""
    c.saveState()
    c.setStrokeColor(GOLD)
    c.setStrokeAlpha(alpha)
    c.setLineWidth(0.5)
    for i in range(n):
        a = 2 * math.pi * i / n
        c.circle(cx + orbit * math.cos(a), cy + orbit * math.sin(a), radius, stroke=1, fill=0)
    c.restoreState()


def _seal(c: canvas.Canvas, cx: float, cy: float) -> None:
    # ribbon tails
    for dx, tilt in ((-14, -1), (14, 1)):
        p = c.beginPath()
        p.moveTo(cx + dx - 9, cy - 20)
        p.lineTo(cx + dx + 9, cy - 20)
        p.lineTo(cx + dx + 9 + tilt * 6, cy - 62)
        p.lineTo(cx + dx + tilt * 6, cy - 54)
        p.lineTo(cx + dx - 9 + tilt * 6, cy - 62)
        p.close()
        c.setFillColor(NAVY)
        c.drawPath(p, stroke=0, fill=1)
    # 16-point star medallion
    points, outer, inner = 16, 40, 34
    p = c.beginPath()
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = math.pi * i / points
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
    p.close()
    c.setFillColor(GOLD)
    c.setStrokeColor(GOLD_DARK)
    c.setLineWidth(0.8)
    c.drawPath(p, stroke=1, fill=1)
    c.setFillColor(NAVY)
    c.circle(cx, cy, 27, stroke=0, fill=1)
    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(1.2)
    c.circle(cx, cy, 23, stroke=1, fill=0)
    # check mark = "verified"
    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(3.2)
    c.setLineCap(1)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(cx - 10, cy - 1)
    p.lineTo(cx - 3, cy - 8)
    p.lineTo(cx + 11, cy + 8)
    c.drawPath(p, stroke=1, fill=0)


def _qr(c: canvas.Canvas, url: str, x: float, y: float, size: float) -> None:
    widget = QrCodeWidget(url)
    widget.barLevel = "M"
    x0, y0, x1, y1 = widget.getBounds()
    scale = size / (x1 - x0)
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, -x0 * scale, -y0 * scale])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


# --------------------------------------------------------------------------- main API
def render_certificate(
    path: Path,
    *,
    name: str,
    remark: str | None,
    award_title: str,
    title: str,
    issuer: str,
    issue_date: date,
    signatory_name: str | None,
    signatory_title: str | None,
    code: str,
    verify_url: str,
) -> None:
    """Draw one certificate to `path` (written atomically)."""
    for label, text in (
        ("name", name), ("remark", remark), ("award title", award_title), ("course/event title", title),
        ("issuer", issuer), ("signatory name", signatory_name), ("signatory title", signatory_title),
    ):
        _ensure_renderable(label, text)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".pdf.tmp")
    cx = PAGE_W / 2

    c = canvas.Canvas(str(tmp_path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"{award_title} - {name}")
    c.setAuthor(issuer)
    c.setSubject(title)
    c.setCreator("Sealwright")

    # --- background + frame
    c.setFillColor(NAVY)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    c.setFillColor(CREAM)
    c.rect(16, 16, PAGE_W - 32, PAGE_H - 32, stroke=0, fill=1)
    _rosette(c, cx, PAGE_H / 2 - 10, 70, 150, 36, 0.10)
    _rosette(c, cx, PAGE_H / 2 - 10, 120, 210, 48, 0.05)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.6)
    c.rect(26, 26, PAGE_W - 52, PAGE_H - 52, stroke=1, fill=0)
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.6)
    c.rect(33, 33, PAGE_W - 66, PAGE_H - 66, stroke=1, fill=0)
    for x, y in ((26, 26), (PAGE_W - 26, 26), (26, PAGE_H - 26), (PAGE_W - 26, PAGE_H - 26)):
        _diamond(c, x, y, 8)

    # --- header
    issuer_txt = issuer.upper()
    size = _fit_size(issuer_txt, "Helvetica-Bold", 11, PAGE_W - 260, 7)
    c.setFillColor(GOLD_DARK)
    _spaced_centered(c, issuer_txt, cx, PAGE_H - 88, "Helvetica-Bold", size, 3)

    award_size = _fit_size(award_title, "Times-Bold", 42, PAGE_W - 200, 20)
    c.setFillColor(NAVY)
    c.setFont("Times-Bold", award_size)
    c.drawCentredString(cx, PAGE_H - 140, award_title)

    # ornament divider
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(cx - 130, PAGE_H - 160, cx - 14, PAGE_H - 160)
    c.line(cx + 14, PAGE_H - 160, cx + 130, PAGE_H - 160)
    _diamond(c, cx, PAGE_H - 160, 5)

    c.setFillColor(MUTED)
    c.setFont("Times-Italic", 15)
    c.drawCentredString(cx, PAGE_H - 192, "This certificate is proudly presented to")

    # --- recipient name (auto-shrinks for long names)
    name_font = "Times-BoldItalic"
    name_size = _fit_size(name, name_font, 48, PAGE_W - 220, 12)
    c.setFillColor(NAVY)
    c.setFont(name_font, name_size)
    c.drawCentredString(cx, PAGE_H - 250, name)
    line_half = min(max(stringWidth(name, name_font, name_size) / 2 + 30, 150), PAGE_W / 2 - 110)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(cx - line_half, PAGE_H - 262, cx + line_half, PAGE_H - 262)

    y = PAGE_H - 285
    if remark:
        r_size = _fit_size(remark, "Helvetica-Oblique", 13, PAGE_W - 260, 8)
        c.setFillColor(GOLD_DARK)
        c.setFont("Helvetica-Oblique", r_size)
        c.drawCentredString(cx, y, remark)
        y -= 24

    # --- body
    c.setFillColor(MUTED)
    c.setFont("Times-Italic", 15)
    c.drawCentredString(cx, y - 4, "in recognition of successfully completing")
    y -= 34
    c.setFillColor(INK)
    for line in _wrap(title, "Helvetica-Bold", 20, PAGE_W - 260, 2):
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(cx, y, line)
        y -= 25

    # --- footer: date | seal | signature | QR
    base = 110
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    date_cx, sig_cx = 190, PAGE_W - 262
    c.line(date_cx - 80, base, date_cx + 80, base)
    c.line(sig_cx - 90, base, sig_cx + 90, base)

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(date_cx, base + 6, f"{issue_date.day:02d} {issue_date.strftime('%B %Y')}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(date_cx, base - 13, "DATE OF ISSUE")

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(sig_cx, base - 14, signatory_name or "Authorised Signatory")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(sig_cx, base - 27, (signatory_title or issuer)[:60])

    _seal(c, cx, base + 22)

    _qr(c, verify_url, PAGE_W - 130, 62, 64)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(PAGE_W - 98, 54, "SCAN TO VERIFY")

    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawCentredString(cx, 46, f"Verification ID: {code}")

    c.showPage()
    c.save()
    os.replace(tmp_path, path)  # atomic: a half-written PDF is never visible
