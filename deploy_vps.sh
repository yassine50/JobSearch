#!/usr/bin/env bash
set -e

echo "===================================================="
echo "🚀 Deploying CVtoMatch Backend on VPS (34.41.44.162)"
echo "===================================================="

# 1. Create 4GB Swap File so the server never runs out of RAM
if [ ! -f /swapfile ]; then
  echo "--> Creating 4GB Swap File..."
  sudo fallocate -l 4G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 2. Install Python, Nginx, Git & Build Dependencies
echo "--> Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git nginx build-essential ca-certificates curl

# 3. Clone or Update the Repository (while strictly preserving production DB & config!)
if [ ! -d "/opt/cvtomatch" ]; then
  echo "--> Cloning repository into /opt/cvtomatch..."
  sudo git clone https://github.com/yassine50/JobSearch.git /opt/cvtomatch
  sudo chown -R $USER:$USER /opt/cvtomatch
else
  echo "--> Safely checkpointing & backing up production database, JWT secret & config before pulling..."
  mkdir -p "$HOME/cvtomatch_backup"
  if [ -f "/opt/cvtomatch/web/backend/jobsearcher.db" ] && [ -x "/opt/cvtomatch/venv/bin/python" ]; then
    /opt/cvtomatch/venv/bin/python - <<'PY' || cp -p "/opt/cvtomatch/web/backend/jobsearcher.db" "$HOME/cvtomatch_backup/jobsearcher.db"
import os, sqlite3
backup_dir = os.path.expanduser("~/cvtomatch_backup")
src = sqlite3.connect("/opt/cvtomatch/web/backend/jobsearcher.db", timeout=30)
try:
    src.execute("PRAGMA wal_checkpoint(TRUNCATE);")
except Exception:
    pass
dst = sqlite3.connect(os.path.join(backup_dir, "jobsearcher.db"))
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
  elif [ -f "/opt/cvtomatch/web/backend/jobsearcher.db" ]; then
    cp -p "/opt/cvtomatch/web/backend/jobsearcher.db" "$HOME/cvtomatch_backup/jobsearcher.db"
  fi
  for f in scraper_config.json .jwt_secret; do
    if [ -f "/opt/cvtomatch/web/backend/$f" ]; then
      cp -p "/opt/cvtomatch/web/backend/$f" "$HOME/cvtomatch_backup/$f"
    fi
  done
  if [ -f "/opt/cvtomatch/.env" ]; then
    cp -p "/opt/cvtomatch/.env" "$HOME/cvtomatch_backup/.env"
  fi
  sudo systemctl stop cvtomatch 2>/dev/null || true
  echo "--> Pulling latest changes in /opt/cvtomatch..."
  cd /opt/cvtomatch
  git fetch origin main
  git reset --hard origin/main
  echo "--> Restoring production database, JWT secret & config..."
  rm -f /opt/cvtomatch/web/backend/jobsearcher.db-wal /opt/cvtomatch/web/backend/jobsearcher.db-shm
  for f in jobsearcher.db scraper_config.json .jwt_secret; do
    if [ -f "$HOME/cvtomatch_backup/$f" ]; then
      cp -p "$HOME/cvtomatch_backup/$f" "/opt/cvtomatch/web/backend/$f"
    fi
  done
  if [ -f "$HOME/cvtomatch_backup/.env" ]; then
    cp -p "$HOME/cvtomatch_backup/.env" "/opt/cvtomatch/.env"
  fi
fi

cd /opt/cvtomatch

# 4. Set up Python Virtual Environment & Install Packages
echo "--> Setting up Python virtual environment..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 5. Create systemd service (runs 24/7 and auto-restarts on reboot)
echo "--> Configuring systemd service (cvtomatch.service)..."
sudo tee /etc/systemd/system/cvtomatch.service > /dev/null <<EOF
[Unit]
Description=CVtoMatch FastAPI Backend
After=network.target

[Service]
User=$USER
WorkingDirectory=/opt/cvtomatch
EnvironmentFile=-/opt/cvtomatch/.env
Environment="PATH=/opt/cvtomatch/venv/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="PLATFORM_FROM_EMAIL=support@cvtomatch.com"
Environment="PLATFORM_REPLY_TO_EMAIL=support@cvtomatch.com"
Environment="PLATFORM_FROM_NAME=CVtoMatch AI"
ExecStart=/opt/cvtomatch/venv/bin/uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cvtomatch
sudo systemctl restart cvtomatch

# 5.5 Configure Daily Automated Database Backup Cron (keeps 14 days of hot snapshots)
echo "--> Configuring daily automated SQLite backup cron..."
sudo tee /etc/cron.daily/cvtomatch-db-backup > /dev/null <<'EOF'
#!/usr/bin/env bash
BACKUP_DIR="/opt/cvtomatch/web/backend/backups"
DB_FILE="/opt/cvtomatch/web/backend/jobsearcher.db"
mkdir -p "$BACKUP_DIR"
if [ -f "$DB_FILE" ]; then
  STAMP=$(date +%Y%m%d_%H%M)
  /opt/cvtomatch/venv/bin/python3 -c "import sqlite3; s=sqlite3.connect('$DB_FILE', timeout=30); d=sqlite3.connect('$BACKUP_DIR/jobsearcher_$STAMP.db'); s.backup(d); d.close(); s.close()"
  ls -1t "$BACKUP_DIR"/jobsearcher_*.db 2>/dev/null | tail -n +15 | xargs -r rm -f
fi
EOF
sudo chmod +x /etc/cron.daily/cvtomatch-db-backup

# 6. Configure Nginx Reverse Proxy on Port 80 -> 127.0.0.1:8000
echo "--> Configuring Nginx reverse proxy on port 80..."
sudo tee /etc/nginx/sites-available/cvtomatch > /dev/null <<'EOF'
upstream cvtomatch_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 25M;
    gzip on;
    gzip_min_length 800;
    gzip_comp_level 5;
    gzip_types application/json text/plain text/css application/javascript;

    location / {
        proxy_pass http://cvtomatch_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 180s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 180s;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/cvtomatch /etc/nginx/sites-enabled/cvtomatch
sudo nginx -t
sudo systemctl restart nginx

echo "===================================================="
echo "✅ CVtoMatch Backend is LIVE at: http://34.41.44.162/health"
echo "===================================================="
curl -s http://127.0.0.1:8000/health || true
echo ""
