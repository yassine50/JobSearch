
import uvicorn, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
if __name__ == "__main__":
    uvicorn.run("web.backend.main:app", host="0.0.0.0", port=8000, reload=True)
