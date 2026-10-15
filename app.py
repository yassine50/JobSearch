"""
Hugging Face Spaces Entrypoint (Gradio SDK Free Tier — 2 vCPU / 16 GB RAM).
Boots the FastAPI backend directly on port 7860.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("GRADIO_SERVER_PORT", 7860)))
    uvicorn.run("web.backend.main:app", host="0.0.0.0", port=port)
