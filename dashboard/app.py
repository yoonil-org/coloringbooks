"""
KDP Coloring Books — Admin Dashboard
FastAPI + Jinja2, served on port 8082
"""
from __future__ import annotations

import io
import shutil
import sqlite3
import subprocess
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ── Paths ──────────────────────────────────────────────────────────────────
BASE         = Path("/home/worker/Workspace/coloring-books")
DB_PATH      = BASE / "data" / "coloring_books.db"
LOG_PATH     = BASE / "logs" / "coloring_books.log"
OUTPUT_DIR   = BASE / "output"
ORCHESTRATOR = BASE / "orchestrator.py"
VENV_PYTHON  = BASE / ".venv" / "bin" / "python3"

DASHBOARD_DIR = Path(__file__).parent
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR    = DASHBOARD_DIR / "static"

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(title="KDP Coloring Books Dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── DB helpers ─────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params=()) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params=()):
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()


# ── Pipeline process tracker ───────────────────────────────────────────────
_pipeline_proc: Optional[subprocess.Popen] = None


def pipeline_is_running() -> bool:
    global _pipeline_proc
    if _pipeline_proc is None:
        return False
    if _pipeline_proc.poll() is not None:
        _pipeline_proc = None
        return False
    return True


def launch_pipeline(args: list[str]) -> dict:
    global _pipeline_proc
    if pipeline_is_running():
        return {"ok": False, "error": "Pipeline already running"}
    log_file = open(str(LOG_PATH), "a")
    cmd = [str(VENV_PYTHON), str(ORCHESTRATOR)] + args
    _pipeline_proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(BASE),
    )
    return {"ok": True, "pid": _pipeline_proc.pid}


# ── Helpers ────────────────────────────────────────────────────────────────

def get_last_run():
    return query_one("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")


def ollama_status() -> dict:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": []}


def disk_info() -> dict:
    total, used, free = shutil.disk_usage(str(BASE))
    return {
        "total_gb":  round(total / 1e9, 1),
        "used_gb":   round(used  / 1e9, 1),
        "free_gb":   round(free  / 1e9, 1),
        "pct_used":  round(used  / total * 100, 1),
    }


def sd_cached() -> bool:
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    if not cache.exists():
        return False
    return any(cache.iterdir())


def tail_log(n: int = 50) -> list[str]:
    if not LOG_PATH.exists():
        return []
    with open(str(LOG_PATH), "r", errors="replace") as f:
        lines = f.readlines()
    return [ln.rstrip() for ln in lines[-n:]]


def format_duration(sec) -> str:
    if sec is None:
        return "—"
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def tmpl(request: Request, name: str, ctx: dict):
    """Starlette 1.x TemplateResponse: (request, name, context)."""
    return templates.TemplateResponse(request, name, ctx)


# ── Page routes ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    running   = pipeline_is_running()
    last_run  = get_last_run()
    disk      = disk_info()
    ollama    = ollama_status()
    sd        = sd_cached()
    log_lines = tail_log(50)

    total_royalties = query_one(
        "SELECT COALESCE(SUM(royalties_usd),0) FROM earnings WHERE is_aggregate=0"
    )[0]
    total_units = query_one(
        "SELECT COALESCE(SUM(units_sold),0) FROM earnings WHERE is_aggregate=0"
    )[0]

    return tmpl(request, "index.html", {
        "running":          running,
        "last_run":         last_run,
        "disk":             disk,
        "ollama":           ollama,
        "sd_cached":        sd,
        "log_lines":        log_lines,
        "total_royalties":  total_royalties,
        "total_units":      total_units,
        "format_duration":  format_duration,
    })


@app.get("/earnings", response_class=HTMLResponse)
async def earnings_page(request: Request):
    daily = query(
        """
        SELECT scrape_date,
               SUM(royalties_usd) AS royalties,
               SUM(units_sold)    AS units
        FROM   earnings
        WHERE  is_aggregate = 0
          AND  scrape_date >= date('now', '-30 days')
        GROUP  BY scrape_date
        ORDER  BY scrape_date DESC
        """,
    )
    per_book = query(
        """
        SELECT b.title,
               b.asin,
               b.kdp_status,
               COALESCE(SUM(e.royalties_usd), 0) AS royalties,
               COALESCE(SUM(e.units_sold),    0) AS units
        FROM   books b
        LEFT   JOIN earnings e ON e.book_id = b.id AND e.is_aggregate = 0
        GROUP  BY b.id
        ORDER  BY royalties DESC
        """,
    )
    total_royalties = sum(r["royalties"] for r in per_book)
    total_units     = sum(r["units"]     for r in per_book)

    return tmpl(request, "earnings.html", {
        "daily":            daily,
        "per_book":         per_book,
        "total_royalties":  total_royalties,
        "total_units":      total_units,
    })


@app.get("/books", response_class=HTMLResponse)
async def books_page(request: Request):
    books = query("SELECT * FROM books ORDER BY created_at DESC")
    return tmpl(request, "books.html", {"books": books})


@app.get("/books/{book_id}", response_class=HTMLResponse)
async def book_detail(request: Request, book_id: int):
    book = query_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    images: list[str] = []
    slug     = book["slug"]     or ""
    run_date = book["run_date"] or ""
    img_dir  = OUTPUT_DIR / run_date / slug / "images"
    if img_dir.exists():
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() in (".png", ".jpg", ".jpeg"):
                rel = img.relative_to(OUTPUT_DIR)
                images.append(f"/output/{rel}")

    return tmpl(request, "book_detail.html", {"book": book, "images": images})


@app.get("/niches", response_class=HTMLResponse)
async def niches_page(request: Request):
    niches = query(
        """
        SELECT * FROM niches
        WHERE  run_date >= date('now', '-30 days')
        ORDER  BY run_date DESC, opp_score DESC
        """,
    )
    return tmpl(request, "niches.html", {
        "niches":  niches,
        "running": pipeline_is_running(),
    })


# ── API endpoints ──────────────────────────────────────────────────────────

@app.post("/api/run")
async def api_run():
    return launch_pipeline([])


@app.post("/api/dry-run")
async def api_dry_run():
    return launch_pipeline(["--dry-run"])


@app.post("/api/run-niche")
async def api_run_niche(niche: str = Form(...)):
    if not niche.strip():
        return JSONResponse({"ok": False, "error": "Niche cannot be empty"}, status_code=400)
    return launch_pipeline(["--niche", niche.strip()])


@app.post("/api/research-niches")
async def api_research_niches():
    global _pipeline_proc
    if pipeline_is_running():
        return {"ok": False, "error": "Pipeline already running"}
    log_file = open(str(LOG_PATH), "a")
    _pipeline_proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "modules.niche_researcher"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(BASE),
    )
    return {"ok": True, "pid": _pipeline_proc.pid}


@app.post("/api/stop")
async def api_stop():
    global _pipeline_proc
    if not pipeline_is_running():
        return {"ok": False, "error": "No pipeline running"}
    _pipeline_proc.kill()
    _pipeline_proc = None
    return {"ok": True}


@app.get("/api/status")
async def api_status():
    last_run = get_last_run()
    return {
        "running":  pipeline_is_running(),
        "last_run": dict(last_run) if last_run else None,
    }


@app.get("/api/log")
async def api_log(n: int = 50):
    return {"lines": tail_log(n)}


@app.get("/books/{book_id}/download/pdf")
async def download_pdf(book_id: int):
    book = query_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    pdf_path = book["interior_pdf"]
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    filename = f"{book['slug'] or book_id}_interior.pdf"
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@app.get("/books/{book_id}/download/images")
async def download_images(book_id: int):
    book = query_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    slug     = book["slug"]     or str(book_id)
    run_date = book["run_date"] or ""
    img_dir  = OUTPUT_DIR / run_date / slug / "images"
    if not img_dir.exists():
        raise HTTPException(status_code=404, detail="Images not found")
    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if not images:
        raise HTTPException(status_code=404, detail="No images found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            zf.write(img, img.name)
    buf.seek(0)
    filename = f"{slug}_images.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/approve-publish/{book_id}")
async def api_approve_publish(book_id: int):
    book = query_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    slug     = book["slug"]     or str(book_id)
    run_date = book["run_date"] or ""
    book_dir = OUTPUT_DIR / run_date / slug
    if not book_dir.exists():
        raise HTTPException(status_code=404, detail="Book output directory not found")
    approval_file = book_dir / "APPROVE_PUBLISH"
    approval_file.touch()
    return {"ok": True, "path": str(approval_file)}


@app.get("/api/system")
async def api_system():
    last_run = get_last_run()
    return {
        "running":   pipeline_is_running(),
        "ollama":    ollama_status(),
        "sd_cached": sd_cached(),
        "disk":      disk_info(),
        "last_run":  dict(last_run) if last_run else None,
    }
