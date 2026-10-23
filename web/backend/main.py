import os
import time
import threading
import urllib.request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .utils import ensure_project_root_on_path
ensure_project_root_on_path()

from .database import engine, Base, init_db
from . import gmail_oauth
from .routers import (
    auth,
    jobs,
    cv,
    recruiter,
    email,
    tracker,
    coverletter,
    linkedin_posts,
    power,
)

Base.metadata.create_all(bind=engine)
init_db()

app = FastAPI(title="CVtoMatch API", version="2.0.0")

app.add_middleware(GZipMiddleware, minimum_size=800)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def fix_double_api_prefix(request, call_next):
    if request.url.path.startswith("/api/api/"):
        request.scope["path"] = request.url.path[4:]
    return await call_next(request)


for router in [
    auth.router,
    jobs.router,
    cv.router,
    recruiter.router,
    gmail_oauth.router,
    email.router,
    tracker.router,
    coverletter.router,
    linkedin_posts.router,
    power.router,
]:
    app.include_router(router)

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
dist_dir = os.path.join(frontend_dir, "dist")
assets_dir = os.path.join(dist_dir, "assets")


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


def _render_keep_alive_worker():
    """Pings Render's external URL every 10 minutes so the free instance stays warm."""
    target_base = (
        os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("BACKEND_PUBLIC_URL")
        or "https://job-searcher-api-ux4i.onrender.com"
    ).rstrip("/")
    health_url = f"{target_base}/health"
    while True:
        time.sleep(600)  # 10 minutes
        try:
            req = urllib.request.Request(health_url, headers={"User-Agent": "CVtoMatch-KeepAlive/1.0"})
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass


def _warm_open_feeds_worker():
    """Pre-warms remote job boards, HN Who is Hiring, and ATS feeds in the background so first search is fast."""
    time.sleep(1.5)
    try:
        from .open_sources import fetch_open_source
        fetch_open_source("remote_boards", ["software engineer"])
        fetch_open_source("hackernews", ["software engineer"])
        fetch_open_source("ats", ["software engineer"])
    except Exception:
        pass


@app.on_event("startup")
def start_keep_alive():
    threading.Thread(target=_warm_open_feeds_worker, daemon=True).start()
    from .auto_dispatcher import run_daily_digest_for_all_users
    threading.Thread(target=run_daily_digest_for_all_users, daemon=True).start()
    if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_URL"):
        t = threading.Thread(target=_render_keep_alive_worker, daemon=True)
        t.start()


# Serve built React SPA in production
if os.path.exists(dist_dir) and os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="API endpoint not found")
        return FileResponse(os.path.join(dist_dir, "index.html"))
