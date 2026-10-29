#!/bin/zsh
# ─────────────────────────────────────────────────────────────────────────────
# CVtoMatch v2.0 — 1-Click Back Office Launcher (macOS)
# Starts the FastAPI backend on port 8000 (if not already running) and opens
# the Back Office Admin Control Center in your default browser.
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT="/Users/yassine/Downloads/JobSpy-main"
PYTHON_BIN="/usr/local/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(which python3)"
fi

echo "========================================================"
echo "  🛡️  CVtoMatch v2.0 — Platform Back Office Launcher"
echo "========================================================"

if lsof -iTCP:8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "✅ Backend API is already running on http://127.0.0.1:8000"
else
  echo "🚀 Starting CVtoMatch FastAPI backend on http://127.0.0.1:8000 ..."
  cd "$PROJECT_ROOT" || exit 1
  nohup "$PYTHON_BIN" -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 > /tmp/cvtomatch_backend.log 2>&1 &
  sleep 2
  echo "✅ Backend started (logs at /tmp/cvtomatch_backend.log)"
fi

echo "🌐 Opening Back Office Control Center..."
open "/Users/yassine/Desktop/backoffice/index.html"
