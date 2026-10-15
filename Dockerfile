FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

# Install system dependencies required by lxml / curl_cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached Docker layer)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend and core scraping/matching engine
COPY . /app

# Hugging Face Spaces runs containers as UID 1000 — grant full write access for SQLite DB
RUN useradd -m -u 1000 user && \
    chown -R 1000:1000 /app && \
    chmod -R 775 /app/web/backend

USER user

EXPOSE 7860

CMD ["sh", "-c", "uvicorn web.backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
