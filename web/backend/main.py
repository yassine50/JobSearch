import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

app = FastAPI(title="Job Searcher API", version="2.0.0")

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


ROUTERS = [
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
]

for router in ROUTERS:
    app.include_router(router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
dist_dir = os.path.join(frontend_dir, "dist")
assets_dir = os.path.join(dist_dir, "assets")


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# Serve built React SPA in production
if os.path.exists(dist_dir) and os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        return FileResponse(os.path.join(dist_dir, "index.html"))
