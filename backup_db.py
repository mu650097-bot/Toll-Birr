"""
Standalone SQLite backup script -- run this on a schedule (cron,
systemd timer, or your platform's scheduled-jobs feature), NOT as
part of the web process. It has no Flask app to keep alive; it does
one backup and exits.

The Admin Panel's "🗄️ Latest Backup" status (GET /api/admin/backups/status
in webapp_api.py) reads whatever this script writes into ./backups/ --
so the file naming here (backup_<timestamp>.db, in a ./backups/ folder
relative to wherever this script runs from) is not arbitrary, it must
match what that endpoint looks for.

Usage (typical cron entry, every 6 hours):
    0 */6 * * * cd /path/to/app && /usr/bin/python3 backup_db.py >> backup_db.log 2>&1

Run it from the SAME working directory the web app runs from (or set
DB_FILE below to an absolute path), so it finds the same database file.
"""
import os
import shutil
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import mimetypes
from datetime import datetime

# Keep this in sync with config.py's DB_FILE. Not imported directly
# from config.py because config.py enforces BOT_TOKEN/ADMIN_ID/etc via
# _require() at import time -- this script has no reason to fail (or
# need those secrets) just because it wants the DB filename.
DB_FILE = os.environ.get("DB_FILE", "auction_wallet.db")

BACKUP_DIR = "backups"
KEEP_LAST_N = int(os.environ.get("BACKUP_KEEP", "200"))  # local copies kept on the disk (backup runs every ~10 min on Render)
BACKUP_MARKER = "KDM_AUTO_BACKUP"  # restore_db.py looks for the pinned Telegram file whose caption starts with this
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()
# Optional: a dedicated private chat for the pinned backup, so nobody pinning another message in the
# admin chat can hide it from restore_db.py. Defaults to ADMIN_ID.
BACKUP_CHAT_ID = os.environ.get("BACKUP_CHAT_ID", "").strip() or ADMIN_ID
STAMP_FILE = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), ".last_backup_mtime")


def _count(path, table):
    try:
        c = sqlite3.connect(path, timeout=10)
        try:
            return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            c.close()
    except Exception:
        return 0


def _db_mtime():
    return max((os.path.getmtime(p) for p in (DB_FILE, DB_FILE + "-wal") if os.path.exists(p)), default=0)


def backup(force=False):
    if not os.path.exists(DB_FILE):
        print(f"[backup_db] ERROR: {DB_FILE} not found in {os.getcwd()} -- nothing to back up")
        sys.exit(1)

    # SAFETY: never let an empty/fresh database replace a good backup (e.g. when a restore failed at boot).
    if _count(DB_FILE, "users") == 0 and _count(DB_FILE, "marketplace_posts") == 0:
        print("[backup_db] database has no users/posts -- skipping so a good backup is never overwritten")
        return

    # Nothing written since the last backup -> nothing to do (lets us run every 2 min cheaply).
    mt = _db_mtime()
    try:
        last = float(open(STAMP_FILE).read().strip())
    except Exception:
        last = 0.0
    if not force and mt <= last:
        print("[backup_db] no changes since last backup -- skipped")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")

    # sqlite3's own backup API (not a plain file copy) -- this is safe
    # to run while the web app is live and writing to the DB. A raw
    # `shutil.copy` of a SQLite file that's mid-write can copy a
    # half-written page and produce a corrupt backup; the backup API
    # takes its own consistent snapshot instead.
    src = sqlite3.connect(DB_FILE, timeout=30)
    dst = sqlite3.connect(dest_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    # Verify the snapshot before reporting success. A backup job that writes
    # a corrupt file is worse than a job that fails loudly.
    check = sqlite3.connect(dest_path, timeout=30)
    try:
        row = check.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise RuntimeError(f"backup integrity_check failed: {row[0] if row else 'no result'}")
    finally:
        check.close()

    size_kb = os.path.getsize(dest_path) / 1024
    print(f"[backup_db] OK: wrote {dest_path} ({size_kb:.1f} KB); integrity=ok")
    _notify_admin(f"🗄️ KDM DB backup OK\n\nFile: {os.path.basename(dest_path)}\nSize: {size_kb:.1f} KB\nIntegrity: OK\nTime: {timestamp}", dest_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    try:
        with open(STAMP_FILE, "w") as fh:
            fh.write(str(mt))
    except OSError:
        pass

    _prune_old_backups()


def _telegram_post(method, fields, file_field=None, file_path=None):
    if not BOT_TOKEN or not BACKUP_CHAT_ID:
        return
    boundary = "----KDMBackupBoundary" + str(int(time.time() * 1000))
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")
    if file_field and file_path:
        filename = os.path.basename(file_path)
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode())
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
        with open(file_path, "rb") as fh:
            body.extend(fh.read())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram HTTP {resp.status}")


def _store_backup_on_telegram(backup_path, stamp):
    """Keep ONE pinned backup file in the admin's bot chat (Telegram = off-server storage).
    Edits the pinned message in place, so the chat is not spammed; falls back to send+pin."""
    import json, requests
    api = f"https://api.telegram.org/bot{BOT_TOKEN}"
    caption = f"{BACKUP_MARKER} {stamp}"
    pinned_id = None
    try:
        chat = requests.get(f"{api}/getChat", params={"chat_id": BACKUP_CHAT_ID}, timeout=20).json().get("result") or {}
        pm = chat.get("pinned_message") or {}
        if pm.get("document") and str(pm.get("caption", "")).startswith(BACKUP_MARKER):
            pinned_id = pm.get("message_id")
    except Exception as e:
        print(f"[backup_db] WARNING: getChat failed: {e}")
    with open(backup_path, "rb") as fh:
        data = fh.read()
    if pinned_id:
        try:
            r = requests.post(f"{api}/editMessageMedia",
                              data={"chat_id": BACKUP_CHAT_ID, "message_id": pinned_id,
                                    "media": json.dumps({"type": "document", "media": "attach://file", "caption": caption})},
                              files={"file": (os.path.basename(backup_path), data)}, timeout=90).json()
            if r.get("ok"):
                print("[backup_db] pinned Telegram backup updated in place"); return
            print(f"[backup_db] edit failed, sending a new one: {r}")
        except Exception as e:
            print(f"[backup_db] edit failed, sending a new one: {e}")
    r = requests.post(f"{api}/sendDocument",
                      data={"chat_id": BACKUP_CHAT_ID, "caption": caption, "disable_notification": "true"},
                      files={"document": (os.path.basename(backup_path), data)}, timeout=90).json()
    if not r.get("ok"):
        raise RuntimeError(f"sendDocument failed: {r}")
    requests.post(f"{api}/pinChatMessage",
                  data={"chat_id": BACKUP_CHAT_ID, "message_id": r["result"]["message_id"], "disable_notification": "true"}, timeout=20)
    print("[backup_db] new pinned Telegram backup created")


def _notify_admin(message, backup_path=None, stamp=""):
    # The newest backup lives as the PINNED file in the admin's bot chat so the data
    # survives even if the Render disk/container is wiped (restore_db.py reads it back).
    if not BOT_TOKEN or not BACKUP_CHAT_ID:
        return
    try:
        if backup_path and os.path.getsize(backup_path) <= 19 * 1024 * 1024:   # Bot API getFile limit is 20 MB
            _store_backup_on_telegram(backup_path, stamp)
        else:
            _telegram_post("sendMessage", {"chat_id": BACKUP_CHAT_ID, "text": message + "\n\n⚠️ Backup file is too large for Telegram restore (20 MB limit); keep the local/cloud copy."})
    except Exception as e:
        print(f"[backup_db] WARNING: Telegram backup upload failed: {type(e).__name__}: {e}")


def _prune_old_backups():
    files = [f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_") and f.endswith(".db")]
    files_with_mtime = sorted(
        ((f, os.path.getmtime(os.path.join(BACKUP_DIR, f))) for f in files),
        key=lambda x: x[1],
        reverse=True,
    )
    for name, _ in files_with_mtime[KEEP_LAST_N:]:
        path = os.path.join(BACKUP_DIR, name)
        try:
            os.remove(path)
            print(f"[backup_db] pruned old backup: {name}")
        except OSError as e:
            print(f"[backup_db] WARNING: could not remove {name}: {e}")


if __name__ == "__main__":
    started = time.time()
    try:
        backup(force="--force" in sys.argv)
    except Exception as e:
        # A cron job's stderr is easy to never look at. Anything that
        # gets this far and still fails is worth a print with enough
        # detail to diagnose from logs alone (cron mail, journalctl,
        # or wherever backup_db.log ends up).
        print(f"[backup_db] FAILED: {type(e).__name__}: {e}")
        sys.exit(1)
    print(f"[backup_db] done in {time.time() - started:.2f}s")
