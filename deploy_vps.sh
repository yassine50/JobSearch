#!/usr/bin/env bash
set -e

echo "===================================================="
echo "🚀 Deploying CVtoMatch Backend on VPS (34.55.247.158)"
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
  echo "--> Backing up production database & config before pulling..."
  mkdir -p ~/cvtomatch_backup
  for f in jobsearcher.db jobsearcher.db-wal jobsearcher.db-shm scraper_config.json; do
    if [ -f "/opt/cvtomatch/web/backend/$f" ]; then
      cp -p "/opt/cvtomatch/web/backend/$f" "~/cvtomatch_backup/$f.bak" 2>/dev/null || cp -p "/opt/cvtomatch/web/backend/$f" "$HOME/cvtomatch_backup/$f"
    fi
  done
  echo "--> Pulling latest changes in /opt/cvtomatch..."
  cd /opt/cvtomatch
  git fetch origin main
  git reset --hard origin/main
  echo "--> Restoring production database & config..."
  for f in jobsearcher.db jobsearcher.db-wal jobsearcher.db-shm scraper_config.json; do
    if [ -f "$HOME/cvtomatch_backup/$f" ]; then
      cp -p "$HOME/cvtomatch_backup/$f" "/opt/cvtomatch/web/backend/$f"
    fi
  done
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
Environment="PATH=/opt/cvtomatch/venv/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/cvtomatch/venv/bin/uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cvtomatch
sudo systemctl restart cvtomatch

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
echo "✅ CVtoMatch Backend is LIVE at: http://34.55.247.158/health"
echo "===================================================="
curl -s http://127.0.0.1:8000/health || true
echo ""
