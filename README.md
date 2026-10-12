# Sealwright — Bulk Certificate Generator

A backend API (plus a small web dashboard) that takes **one request with many recipients**,
generates a PDF certificate for each valid recipient from a single predefined template,
tracks progress, and lets you retrieve the results.

Every certificate carries a **QR code + signed verification ID**. Scanning it opens a public page that
confirms the certificate is authentic (and detects tampering) — that is the project's signature feature.

## Features

| Required by the assignment | Extras (small, optional) |
|---|---|
| Bulk request: JSON list of recipients | CSV upload endpoint (`/api/jobs/upload`) |
| Per-recipient validation | Duplicate-email detection inside a job |
| One predefined PDF template | QR code + HMAC-signed verification page (`/verify/<id>`) |
| Background processing + status/progress | Live progress dashboard with preview, filters, paging |
| One failure never blocks the others | **Retry failed** endpoint (only for real generation failures) |
| Retrieve single PDFs | Download everything as ZIP (with a `report.csv`) |
| Tests, README | Crash recovery: unfinished jobs resume on restart |

**Stack:** Python 3.10+, FastAPI, SQLAlchemy 2 + SQLite (relational), ReportLab (PDF), vanilla JS front-end.

## 1. Set up

```bash
# from the project folder
python -m venv .venv

# activate it
#   Windows PowerShell:  .venv\Scripts\Activate.ps1
#   Windows cmd:         .venv\Scripts\activate.bat
#   macOS / Linux:       source .venv/bin/activate

pip install -r requirements-dev.txt
```

Optional: `copy .env.example .env` (Windows) / `cp .env.example .env` and edit values.
The app works without a `.env` file.

> PowerShell blocks the activate script? Run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 2. Run the application

```bash
uvicorn app.main:app --reload
```

* Dashboard: http://127.0.0.1:8000
* Interactive API docs (Swagger): http://127.0.0.1:8000/docs

Tables are created automatically on first start. To *see* the progress bar move during a demo,
set `GENERATION_DELAY_MS=150` in `.env` (adds a small delay per certificate).

## 3. Run the tests

```bash
pytest
```

The tests use a temporary database and process jobs inline, so they are fast and deterministic.

| File | Covers |
|---|---|
| `test_create_job.py` | creating a job, many recipients in one request, CSV upload |
| `test_validation.py` | request-level 422s, per-row invalid data, duplicates, name rules |
| `test_generation.py` | PDF content, layout, long names, unsupported characters, codes, signatures |
| `test_status.py` | status/progress, partial progress, paging/filtering, resume after crash |
| `test_failure_handling.py` | one failing certificate doesn't stop others, retry |
| `test_retrieval.py` | single PDF, ZIP, 404s, public verification, tamper detection |

## 4. Submit a certificate generation request

`POST /api/jobs` → **202 Accepted** immediately; processing continues in the background.

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Full-Stack Python Bootcamp 2026",
    "issuer": "Frontier Academy",
    "award_title": "Certificate of Completion",
    "issue_date": "2026-10-08",
    "signatory_name": "Dr. A. Rao",
    "signatory_title": "Program Director",
    "recipients": [
      {"name": "Tanvi Sharma", "email": "tanvi@example.com", "remark": "with Distinction"},
      {"name": "Arjun Mehta", "email": "arjun@example.com"},
      {"name": "Meera Iyer"}
    ]
  }'
```

PowerShell equivalent:

```powershell
$body = @{
  title = "Full-Stack Python Bootcamp 2026"; issuer = "Frontier Academy"
  recipients = @(
    @{ name = "Tanvi Sharma"; email = "tanvi@example.com"; remark = "with Distinction" },
    @{ name = "Arjun Mehta" }
  )
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/jobs -Method Post -ContentType "application/json" -Body $body
```

(Easiest of all: open `/docs`, click **POST /api/jobs → Try it out**.)

**Fields.** Job level: `title`, `issuer` (required); `award_title`, `issue_date`, `signatory_name`,
`signatory_title` (optional). Recipient: `name` (required), `email`, `remark` (optional).

**CSV instead of JSON:**

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/upload \
  -F title="Bootcamp" -F issuer="Frontier Academy" -F file=@app/static/sample.csv
```

### Check progress

```bash
curl http://127.0.0.1:8000/api/jobs/<job_id>
```

```json
{
  "id": "…", "status": "processing", "total": 3,
  "counts": {"generated": 2, "invalid": 0, "failed": 0, "pending": 1},
  "processed": 2, "progress_percent": 66.7
}
```

Job `status`: `queued` → `processing` → `completed` | `completed_with_errors` | `failed`.
Per-recipient status: `pending`, `generated`, `invalid` (bad input), `failed` (generation error).

Per-recipient detail (with the exact error for each bad row):

```bash
curl "http://127.0.0.1:8000/api/jobs/<job_id>/certificates?status=invalid&limit=50&offset=0"
```

## 5. Retrieve generated certificates

| Need | Request |
|---|---|
| One PDF (view in browser) | `GET /api/certificates/<code>/file` |
| One PDF (force download) | `GET /api/certificates/<code>/file?download=true` |
| Everything as ZIP (+ `report.csv`) | `GET /api/jobs/<job_id>/download` |
| Public verification | `GET /verify/<code>` (page) or `GET /api/verify/<code>` (JSON) |
| Retry failed rows | `POST /api/jobs/<job_id>/retry` |

`<code>` is the `code` field of each generated item in the certificates list (looks like `SW-7K3M9XQ2PA`).

## 6. Project layout

```
app/
  main.py            app + startup (create tables, resume unfinished jobs)
  config.py          settings from env / .env
  database.py        SQLAlchemy engine + session
  models.py          Job, Certificate tables
  schemas.py         request / response models
  routers/jobs.py    job + certificate endpoints
  routers/verify.py  public verification endpoint
  services/
    validation.py    recipient rules
    pdf_generator.py the single certificate template (ReportLab)
    processor.py     background worker
    jobs.py          create / count / retry / serialise
    signing.py       verification codes + HMAC signatures
  static/            dashboard (index.html, app.js, style.css) + verify page
tests/               pytest suite
```

## 7. Design decisions (and why)

1. **Background processing, not synchronous.** A request may hold thousands of recipients; generating
   them inside the HTTP request would time out and block the server. The API validates, stores, replies
   `202 Accepted` with a job id, and a `ThreadPoolExecutor` generates the PDFs. The client polls the job.
   *Why threads and not Celery/Redis?* Zero extra infrastructure (one command to run). The design keeps the
   door open: the **database is the queue** (each certificate row is `pending` until done), so swapping
   `processor.dispatch()` for a Celery task would not change anything else.
2. **A row per recipient, always.** Even invalid recipients are stored, with a reason. The client gets
   a complete, per-row result instead of "something was wrong with your 2,000 rows".
3. **Two levels of validation.** Malformed *request* (missing title, empty list, too many recipients) → `422`.
   A bad *recipient* never fails the request — the row is marked `invalid` and the rest proceed.
   `invalid` (fix the data and resubmit) is deliberately separate from `failed` (system problem; retryable).
4. **Failure isolation.** Each certificate is generated and committed independently inside `try/except`.
   An error marks only that row `failed`. PDFs are written to a temp file then atomically renamed, so a
   crash never leaves a half-written certificate.
5. **Crash recovery.** On startup, jobs still `queued`/`processing` are re-dispatched; only `pending`
   rows are processed, so nothing is generated twice.
6. **Verifiable certificates.** Each certificate gets a random ID and an HMAC-SHA256 signature over
   (id, name, title, issuer, date) using `SECRET_KEY`. The verify endpoint recomputes it, so edited
   database rows are detected.
7. **Relational DB.** SQLite by default (zero setup); change `DATABASE_URL` to use PostgreSQL.
8. **Honest font limitation.** The built-in PDF fonts support Latin (Windows-1252) text. Names in other
   scripts (e.g. Tamil) are reported as a clear per-row `failed` error instead of printing empty boxes.
   Fix: register a Unicode TTF font in `pdf_generator.py` (see "Known limitations").
9. **Safe UI.** The dashboard inserts user text with `textContent` (never `innerHTML`) to prevent XSS.

## 8. Known limitations / next steps

* Threads live inside the API process: for multiple servers use Celery/RQ + Redis.
* `create_all()` builds tables; a production app would use Alembic migrations.
* No authentication (out of scope). Certificate IDs are random and unguessable, but the API is open.
* Non-Latin names need a bundled Unicode font (e.g. Noto Sans) registered with ReportLab.
* Certificates are kept on local disk; for production use object storage (S3).
