# KESSLER — Lightsail VPS deployment (Option A)

Deployed 21 Jul 2026 to `mumbai-vps` (ap-south-1, 13.127.244.0), co-hosted with
existing workloads — single systemd service, FastAPI serves both API and built UI.

## Layout on the VPS

```
/opt/kessler/backend        app code + .venv (Python 3.12.3) + .env (chmod 600)
/opt/kessler/ui/dist        built UI (served by FastAPI static/SPA fallback)
/etc/systemd/system/kessler.service
```

## Operations

```bash
ssh -i ~/.ssh/lightsail-ap-south-1.pem ubuntu@13.127.244.0

sudo systemctl status kessler        # status
sudo systemctl restart kessler       # restart
journalctl -u kessler -f             # live logs (also backend/logs/kessler.log)
```

## Redeploy (from Windows dev machine)

```bash
cd /d/PROJECT/kessler
npm --prefix ui run build
tar --exclude='.venv' --exclude='node_modules' --exclude='logs/*' \
    --exclude='app/data/cache.db' --exclude='.env' \
    -czf /tmp/kessler-deploy.tar.gz backend ui/dist README.md
scp -i ~/.ssh/lightsail-ap-south-1.pem /tmp/kessler-deploy.tar.gz ubuntu@13.127.244.0:/tmp/
ssh -i ~/.ssh/lightsail-ap-south-1.pem ubuntu@13.127.244.0 \
  'tar -xzf /tmp/kessler-deploy.tar.gz -C /opt/kessler &&
   /opt/kessler/backend/.venv/bin/pip install -q -r /opt/kessler/backend/requirements.txt &&
   sudo systemctl restart kessler'
```

Note: the tarball intentionally excludes `.env` — credentials live only on the
VPS (`/opt/kessler/backend/.env`) and the local dev machine.

## Access

Port 8000 is bound on 0.0.0.0 but the **Lightsail firewall does not expose it**
(deliberate default). Two options:

1. **SSH tunnel (current, private):**
   `ssh -i ~/.ssh/lightsail-ap-south-1.pem -L 8000:localhost:8000 ubuntu@13.127.244.0`
   then open http://localhost:8000
2. **Public:** open TCP 8000 in the Lightsail console (Networking → Firewall) —
   recommend adding nginx + HTTPS + a subdomain before doing this.

## Resource guardrails

- systemd `MemoryMax=280M` (observed usage ~66 MB; VPS has 414 MB total)
- Space-Track client enforces <20 req/min, 250 req/hr — account-safe
- Pipeline refresh every 30 min; catalogue TTL 1 h; CDM TTL 30 min
