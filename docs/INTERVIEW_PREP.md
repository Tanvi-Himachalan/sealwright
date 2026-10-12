# Interview prep - questions you may get, and where to change things

## Design questions
**Why background processing?** Bulk requests can be thousands of rows. Doing it in the request would
time out and block other users. We return 202 with a job id and let the client poll.

**Why threads, not Celery?** No extra infrastructure for a take-home project. The DB is the source of truth
(rows are `pending` until generated), so switching to Celery means replacing `dispatch()` only.

**What happens if the server crashes mid-job?** On startup `resume_unfinished_jobs()` re-dispatches
jobs in `queued`/`processing`; only `pending` rows are processed so nothing is generated twice.
PDFs are written atomically (temp file + `os.replace`).

**How do you keep one failure from stopping the rest?** `_generate_one` wraps each certificate in
`try/except`, rolls back, marks only that row `failed` with the error, and the loop continues.

**invalid vs failed?** `invalid` = the client's data is wrong (fix and resubmit). `failed` = our
generation crashed on valid data (retryable with `/retry`).

**Why store invalid rows?** The client gets a full per-row report instead of a vague error.

**How is the certificate tamper-evident?** HMAC-SHA256 over (code, name, title, issuer, date) with
`SECRET_KEY`; verify recomputes and uses `hmac.compare_digest` (constant-time).

**Scaling?** Move to Postgres, Celery/RQ + Redis workers, object storage, add pagination (already there),
rate limiting and auth.

**Concurrency concerns with SQLite?** WAL mode + a timeout, one session per thread. For heavy concurrent
writes use Postgres.

## "Changed requirement" drills - where you would edit
| Request | Change |
|---|---|
| Add a `course_hours` field on the certificate | `schemas.JobMeta`, `models.Job`, `jobs.create_job`, `processor._generate_one`, `pdf_generator` (+ test) |
| Email the PDF to each recipient | After success in `_generate_one` call a mail function (smtplib); add `email_status` column |
| Limit to 100 recipients | `MAX_RECIPIENTS` env var / `settings.max_recipients` |
| Webhook when job finishes | After `finalize_job` in `processor.process_job` POST to a `callback_url` stored on the Job |
| Support Tamil/Hindi names | Register a Unicode TTF in `pdf_generator.py` (`pdfmetrics.registerFont(TTFont(...))`) and remove the cp1252 check |
| Different template per job | Add `template` column + a dict of draw functions in `pdf_generator.py` |
| Delete a job | `DELETE /api/jobs/{id}`: delete DB row (cascade removes certificates) and `shutil.rmtree(storage/job_id)` |
| Rate-limit requests | Add `slowapi` or a dependency that counts per IP |

## Be ready to explain these lines
* `Mapped[...] = mapped_column(...)` - SQLAlchemy 2 typed columns.
* `Depends(get_db)` - FastAPI dependency injection; opens/closes a session per request.
* `status_code=202` - "accepted for processing".
* `RecipientIn` fields typed `Any` - lets us validate per row instead of rejecting the whole request.
* `finalize_job` rules - all generated → completed; none → failed; otherwise completed_with_errors.
* `PROCESS_INLINE` - lets tests run the worker synchronously.
