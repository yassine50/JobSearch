
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import engine, Base
from .routers import auth, jobs, cv, recruiter

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Searcher API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(cv.router)
app.include_router(recruiter.router)

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
assets_dir   = os.path.join(frontend_dir, "assets")

if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/")
def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/dashboard")
def dashboard():
    return FileResponse(os.path.join(frontend_dir, "dashboard.html"))

@app.get("/seeker")
def seeker():
    return FileResponse(os.path.join(frontend_dir, "seeker.html"))

@app.get("/recruiter-page")
def recruiter_page():
    return FileResponse(os.path.join(frontend_dir, "recruiter.html"))

@app.get("/health")
def health():
    return {"status": "ok", "service": "Job Searcher API"}
