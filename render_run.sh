#!/bin/bash
# Runs as appuser. If ANY child process dies the whole container exits so Render restarts it
# (a half-running service, e.g. API up but bot dead, must never stay "healthy").
cd /app || exit 1
stop_all() { kill $(jobs -p) 2>/dev/null; }
# On shutdown/sleep (SIGTERM) take one last backup so nothing written since the last interval is lost.
trap 'echo "[render_run] SIGTERM -> final backup" >&2; timeout 20 python backup_db.py --force; stop_all; exit 143' TERM INT

gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120 webapp_api:app &

for i in $(seq 1 90); do
  python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)" 2>/dev/null && break
  sleep 1
done

python kdm_mini_app.py &

# DB backup every 10 min; the newest copy is kept pinned in the admin's bot chat (restore_db.py uses it).
# Runs every 2 min but only does work when the DB actually changed.
( sleep 45; while true; do python backup_db.py; sleep "${BACKUP_INTERVAL:-120}"; done ) &

# Keep the free instance awake (Render sleeps after ~15 min without inbound HTTP traffic).
if [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
  ( sleep 120; while true; do
      python -c "import urllib.request,os;urllib.request.urlopen(os.environ['RENDER_EXTERNAL_URL'].rstrip('/')+'/api/health',timeout=20)" 2>/dev/null
      sleep 540
    done ) &
fi

XDG_DATA_HOME=/tmp/caddy-data XDG_CONFIG_HOME=/tmp/caddy-config \
  caddy run --config /app/Caddyfile.render --adapter caddyfile &

wait -n
echo "[render_run] a process exited -- stopping container so Render restarts it" >&2
stop_all
exit 1
