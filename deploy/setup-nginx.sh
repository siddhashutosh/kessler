#!/usr/bin/env bash
# KESSLER public gateway — run ON the VPS after reboot:
#   bash setup-nginx.sh
# Memory-safe: stops kessler during apt install (414 MB box), restarts after.
set -euo pipefail

echo "[1/4] freeing memory during install..."
sudo systemctl stop kessler

echo "[2/4] installing nginx (minimal)..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends nginx

echo "[3/4] writing site config..."
sudo tee /etc/nginx/sites-available/kessler > /dev/null << 'CONF'
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=screen:10m rate=6r/m;

server {
    listen 80 default_server;
    server_name _;

    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;

    # admin-only refresh trigger stays private
    location = /api/v1/pipeline/refresh { return 403; }

    # screening is compute-heavy: tight per-IP budget
    location = /api/v1/screening/run {
        limit_req zone=screen burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
CONF
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/kessler /etc/nginx/sites-enabled/kessler
sudo nginx -t

echo "[4/4] starting services..."
sudo systemctl reload nginx
sudo systemctl start kessler
sleep 20
curl -s -o /dev/null -w "kessler via nginx: HTTP %{http_code}\n" http://localhost/api/v1/health
echo "Done. If Lightsail firewall allows TCP 80 (default), KESSLER is now public on this instance's IP."
