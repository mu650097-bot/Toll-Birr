"""Run ONCE at container start, BEFORE the API/bot. If the database is missing or empty
(Render wiped the disk / container slept on a plan without a disk), pull the newest
backup that backup_db.py pinned in the admin's bot chat and put it back.
A database that already has users or marketplace posts is NEVER touched."""
import os, sqlite3, sys, tempfile, time
import requests

DB_FILE = os.environ.get("DB_FILE", "auction_wallet.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()
BACKUP_CHAT_ID = os.environ.get("BACKUP_CHAT_ID", "").strip() or ADMIN_ID
MARKER = "KDM_AUTO_BACKUP"


def _count(path, table):
    try:
        c = sqlite3.connect(path, timeout=10)
        try:
            return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            c.close()
    except Exception:
        return 0


def db_has_data(path):
    return os.path.exists(path) and (_count(path, "users") > 0 or _count(path, "marketplace_posts") > 0)


def main():
    if db_has_data(DB_FILE):
        print("[restore_db] database already has data -- nothing to restore"); return 0
    if not BOT_TOKEN or not BACKUP_CHAT_ID:
        print("[restore_db] BOT_TOKEN/ADMIN_ID missing -- cannot restore"); return 0
    api = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        chat = requests.get(f"{api}/getChat", params={"chat_id": BACKUP_CHAT_ID}, timeout=20).json().get("result") or {}
        pm = chat.get("pinned_message") or {}
        doc = pm.get("document")
        if not doc or not str(pm.get("caption", "")).startswith(MARKER):
            print("[restore_db] no pinned KDM_AUTO_BACKUP file found -- starting with a fresh database"); return 0
        gf = requests.get(f"{api}/getFile", params={"file_id": doc["file_id"]}, timeout=20).json()
        path = (gf.get("result") or {}).get("file_path")
        if not gf.get("ok") or not path:
            print(f"[restore_db] getFile failed: {gf}"); return 0
        raw = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}", timeout=120)
        raw.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(DB_FILE)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".db", dir=os.path.dirname(os.path.abspath(DB_FILE)))
        os.close(fd)
        with open(tmp, "wb") as fh:
            fh.write(raw.content)
        c = sqlite3.connect(tmp)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.close()
        if ok != "ok" or not db_has_data(tmp):
            os.remove(tmp)
            print(f"[restore_db] backup rejected (integrity={ok}, has_data={db_has_data(tmp) if os.path.exists(tmp) else False})"); return 0
        for ext in ("-wal", "-shm"):
            if os.path.exists(DB_FILE + ext):
                os.remove(DB_FILE + ext)
        os.replace(tmp, DB_FILE)
        print(f"[restore_db] RESTORED database from Telegram backup: {pm.get('caption')}")
    except Exception as e:
        print(f"[restore_db] WARNING: restore failed ({type(e).__name__}: {e}) -- continuing with current database")
    return 0


if __name__ == "__main__":
    # Telegram can be briefly unreachable right after a cold start -> retry before giving up.
    for attempt in range(4):
        main()
        if db_has_data(DB_FILE):
            break
        if attempt < 3:
            print(f"[restore_db] still no data, retry {attempt + 1}/3 in 5s")
            time.sleep(5)
    sys.exit(0)
