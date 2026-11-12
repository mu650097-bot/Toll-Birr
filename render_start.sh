#!/bin/bash
# Runs as root: Render mounts the persistent disk root-owned. Fix that, then drop privileges.
set -u
export PORT="${PORT:-10000}"
export DB_FILE="${DB_FILE:-/app/data/auction_wallet.db}"
export MINI_APP_DIR=/app WEBAPP_PORT=8080 TZ="${TZ:-Africa/Addis_Ababa}"

mkdir -p /app/data/backups
chown -R appuser:appuser /app/data
# backup_db.py and /api/admin/backups/status both use ./backups -> keep it ON the disk.
rm -rf /app/backups
ln -s /app/data/backups /app/backups
chown -h appuser:appuser /app/backups

# If the disk was wiped, bring the data back from the pinned Telegram backup BEFORE anything starts.
runuser -u appuser -- python /app/restore_db.py || true

exec runuser -u appuser -- /app/render_run.sh
