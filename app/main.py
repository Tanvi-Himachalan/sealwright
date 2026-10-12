"""Application entry point.  Run with:  uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import jobs, verify
from .services.processor import resume_unfinished_jobs

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)          # creates tables on first run
    resumed = resume_unfinished_jobs()        # crash recovery
    if resumed:
        logging.getLogger("sealwright").info("Resumed %d unfinished job(s)", resumed)
    yield


app = FastAPI(
    title="Sealwright - Bulk Certificate Generator",
    description="Generate, track and verify certificates in bulk.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(jobs.router)
app.include_router(verify.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/verify/{code}", include_in_schema=False)
def verify_page(code: str):
    return FileResponse(STATIC_DIR / "verify.html")
