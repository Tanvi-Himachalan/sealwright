# Build guide: Sealwright from scratch in VS Code

Use this to understand every piece (you will be asked to explain and modify it in the interview).
If you just want to run the finished project, follow `README.md`.

---
## Phase 0 - Tools (one time)
1. Install **Python 3.10+** from python.org (tick *Add python.exe to PATH*). Check: `python --version`.
2. Install **VS Code** and the extensions: **Python** and **Pylance** (Microsoft). Optional: *Thunder Client* or *REST Client* for calling the API.

## Phase 1 - Project + virtual environment
1. Create a folder `sealwright`, then in VS Code: **File → Open Folder**.
2. Open the terminal: **Terminal → New Terminal**.
3. `python -m venv .venv`
4. Activate: `.venv\Scripts\Activate.ps1` (PowerShell) - your prompt shows `(.venv)`.
5. `Ctrl+Shift+P` → **Python: Select Interpreter** → choose the one inside `.venv`.
6. Create `requirements.txt` (fastapi, uvicorn, sqlalchemy, reportlab, python-multipart, pydantic-settings) and `requirements-dev.txt` (adds pytest, httpx, pypdf), then `pip install -r requirements-dev.txt`.

*Why a venv?* Keeps this project's libraries separate from everything else on your machine.

## Phase 2 - Folder structure
Create these folders/files (empty `__init__.py` files make folders importable packages):

```
app/__init__.py   app/routers/__init__.py   app/services/__init__.py   app/static/
tests/__init__.py   docs/   storage/
```

## Phase 3 - Build bottom-up (each step can be run/tested on its own)

| # | File | What you write | Why |
|---|------|----------------|-----|
| 1 | `app/config.py` | `Settings` class (pydantic-settings) | One place for all settings; `.env` support |
| 2 | `app/database.py` | engine, `SessionLocal`, `Base`, `get_db` | Connection to the relational DB |
| 3 | `app/models.py` | `Job` and `Certificate` tables + status enums | The data model: 1 job → many certificates |
| 4 | `app/services/validation.py` | `validate_recipient`, `validate_batch` | Rules for name/email/remark + duplicate emails |
| 5 | `app/services/signing.py` | `new_code`, `sign`, `is_signature_valid` | Verification IDs + tamper detection |
| 6 | `app/services/pdf_generator.py` | `render_certificate()` | The ONE template (frame, rosette, seal, QR) |
| 7 | `app/schemas.py` | request/response models | API contract + automatic docs |
| 8 | `app/services/jobs.py` | `create_job`, `count_by_status`, `retry_failed`, serialisers | Business logic, kept out of the routes |
| 9 | `app/services/processor.py` | thread pool, `process_job`, `_generate_one` | Background work + failure isolation |
| 10 | `app/routers/jobs.py`, `verify.py` | endpoints | HTTP layer (thin) |
| 11 | `app/main.py` | app, routers, startup | Wires everything; creates tables; resumes jobs |
| 12 | `app/static/*` | dashboard + verify page | The UI |
| 13 | `tests/*` | pytest suite | Proof it works |
| 14 | `README.md` | docs | Required by the assignment |

**Tip:** after step 6, test the PDF alone from a Python shell (see the snippet in the README or `tests/test_generation.py`) and open the PDF. After step 11 run the server and use `/docs`.

## Phase 4 - Run and debug
* Run: `uvicorn app.main:app --reload` → open http://127.0.0.1:8000
* Debug in VS Code: **Run and Debug** panel → *Sealwright: run server (debug)* (uses `.vscode/launch.json`). Set a breakpoint inside `_generate_one` in `processor.py`, submit a batch, and step through.
* Tests: `pytest` in the terminal, or the **Testing** (flask icon) panel in VS Code.

## Phase 5 - How one request flows (memorise this)
1. Browser/curl → `POST /api/jobs` with title, issuer and recipients.
2. FastAPI/Pydantic checks the job-level fields (bad → `422`).
3. `create_job()` validates each recipient; stores a `Certificate` row for every recipient (`pending` with a code, or `invalid` with a reason).
4. Response `202` + job id returns immediately.
5. `dispatch(job_id)` puts the job on the thread pool.
6. Worker loops over `pending` rows: render PDF → sign → commit; on exception mark that row `failed` and continue.
7. Worker finalises the job status (`completed`, `completed_with_errors`, `failed`).
8. Client polls `GET /api/jobs/{id}` (counts + percent) and fetches PDFs/ZIP.
9. QR on the PDF opens `/verify/{code}`, which recomputes the HMAC signature.

## Phase 6 - Demo script for the interview (3 minutes)
1. Start the server with `GENERATION_DELAY_MS=150`.
2. Click **load demo data** → **Generate**. Watch the live progress bar.
3. Point out: 1 invalid email, 1 duplicate email, 1 non-Latin name that *failed* - while 5 others succeeded.
4. **Preview** a certificate, scan the QR (or click *Copy verify link*), show the verified page.
5. Edit a name directly in the database → verify page now warns about tampering.
6. **Download all (ZIP)** and open `report.csv`.

## Phase 7 - Submit
* `git init`, `git add .`, `git commit -m "Bulk certificate generator"`, push to GitHub (the `.gitignore` already excludes `.venv`, DB and generated PDFs).
* Or zip the folder **without** `.venv`.
