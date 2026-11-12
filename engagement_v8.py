# engagement_v8.py -- loaded by webapp_api.py via exec(), same pattern as realtime_engine_v3.py,
# so it shares that module's globals (app, db, _now, require_* decorators, requests, ...).
#
# Adds:
#   1) Home-screen BANNERS (max 5, slide sideways, per-banner seconds) -- admin uploads in the Mini App
#      admin panel; the bot also adds a banner automatically when an admin posts a PHOTO announcement.
#   2) SHAMO -- daily 9:00 PM (Addis Ababa) mystery-box event. One pick per user per day, prize drawn
#      SERVER-SIDE, credited atomically. Disabled by default; admin turns it on and sets prizes/budget.

from datetime import timezone as _tz

MAX_BANNERS = 5
BANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)) or ".", "banners")
_ADDIS = _tz(timedelta(hours=3))  # Africa/Addis_Ababa has no DST (UTC+3)
_BANNER_EXT = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}
_BANNER_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _init_engagement_v8():
    os.makedirs(BANNER_DIR, exist_ok=True)
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS banners (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, link_page TEXT,
        seconds INTEGER NOT NULL DEFAULT 4, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS shamo_settings (
        id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
        open_hour INTEGER NOT NULL DEFAULT 21, open_minute INTEGER NOT NULL DEFAULT 0,
        window_minutes INTEGER NOT NULL DEFAULT 10, boxes INTEGER NOT NULL DEFAULT 8,
        prizes_json TEXT NOT NULL DEFAULT '[[0,50],[5,25],[10,15],[20,8],[50,2]]',
        daily_budget REAL NOT NULL DEFAULT 500.0, require_deposit INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT)""")
    cur.execute("INSERT OR IGNORE INTO shamo_settings(id,updated_at) VALUES (1,?)", (_now(),))
    cur.execute("""CREATE TABLE IF NOT EXISTS shamo_picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, user_id INTEGER NOT NULL,
        box_index INTEGER NOT NULL, prize REAL NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(day, user_id))""")
    conn.commit(); conn.close()


_init_engagement_v8()


# ------------------------------------------------------------------ banners
def _banner_row(r):
    return {"id": r["id"], "image": f"/api/banners/{r['id']}/image", "link_page": r["link_page"] or "",
            "seconds": int(r["seconds"] or 4)}


@app.route("/api/banners")
@require_telegram_auth
def list_banners():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM banners WHERE active=1 ORDER BY id DESC LIMIT ?", (MAX_BANNERS,))
    items = [_banner_row(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"items": items})


@app.route("/api/banners/<int:bid>/image")
def banner_image(bid):
    # Public on purpose: <img> tags cannot send the Telegram auth header, and banners are promo art.
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT filename FROM banners WHERE id=? AND active=1", (bid,))
    row = cur.fetchone(); conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    path = os.path.join(BANNER_DIR, os.path.basename(row["filename"]))
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404
    ext = path.rsplit(".", 1)[-1]
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, mimetype=_BANNER_MIME.get(ext, "application/octet-stream"),
                    headers={"Cache-Control": "public, max-age=3600"})


def save_banner_bytes(file_bytes, link_page="", seconds=4):
    """Validates + stores an image and inserts a banner row. Keeps only the newest MAX_BANNERS active
    (older ones are deactivated and their files removed). Returns banner id."""
    ext = next((e for magic, e in _BANNER_EXT.items() if file_bytes.startswith(magic)), None)
    if ext == "webp" and file_bytes[8:12] != b"WEBP":
        ext = None
    if not ext:
        raise ValueError("only JPG, PNG or WEBP images are allowed")
    if len(file_bytes) > 5 * 1024 * 1024:
        raise ValueError("image too large (5MB max)")
    seconds = max(2, min(30, int(seconds or 4)))
    os.makedirs(BANNER_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(BANNER_DIR, name), "wb") as f:
        f.write(file_bytes)
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO banners(filename,link_page,seconds,active,created_at) VALUES (?,?,?,1,?)",
                (name, (link_page or "")[:30], seconds, _now()))
    bid = cur.lastrowid
    cur.execute("SELECT id, filename FROM banners WHERE active=1 ORDER BY id DESC")
    extra = cur.fetchall()[MAX_BANNERS:]
    for r in extra:
        cur.execute("UPDATE banners SET active=0 WHERE id=?", (r["id"],))
        try:
            os.remove(os.path.join(BANNER_DIR, os.path.basename(r["filename"])))
        except OSError:
            pass
    conn.commit(); conn.close()
    return bid


@app.route("/api/admin/banners", methods=["GET", "POST"])
@require_telegram_auth
@require_admin
def admin_banners():
    if request.method == "GET":
        return _admin_banner_list()
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "photo is required"}), 400
    try:
        bid = save_banner_bytes(photo.read(), request.form.get("link_page", ""), request.form.get("seconds", 4))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    _log_admin_action(g.tg_user["id"], "banner_add", {"banner_id": bid})
    return jsonify({"ok": True, "id": bid})


def _admin_banner_list():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM banners WHERE active=1 ORDER BY id DESC LIMIT ?", (MAX_BANNERS,))
    items = [_banner_row(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"items": items, "max": MAX_BANNERS})


@app.route("/api/admin/banners/<int:bid>", methods=["DELETE"])
@require_telegram_auth
@require_admin
def admin_banner_delete(bid):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT filename FROM banners WHERE id=? AND active=1", (bid,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE banners SET active=0 WHERE id=?", (bid,))
        conn.commit()
        try:
            os.remove(os.path.join(BANNER_DIR, os.path.basename(row["filename"])))
        except OSError:
            pass
    conn.close()
    _log_admin_action(g.tg_user["id"], "banner_delete", {"banner_id": bid})
    return jsonify({"ok": bool(row)})


# -------------------------------------------------------------------- shamo
def _shamo_settings(cur):
    cur.execute("SELECT * FROM shamo_settings WHERE id=1")
    return cur.fetchone()


def _shamo_clock(st, now=None):
    """Returns (day_key, opens_at, closes_at, now) in Addis time for the CURRENT or NEXT round."""
    now = now or datetime.now(_ADDIS)
    opens = now.replace(hour=int(st["open_hour"]), minute=int(st["open_minute"]), second=0, microsecond=0)
    closes = opens + timedelta(minutes=int(st["window_minutes"]))
    if now >= closes:  # today's round is over -> next round is tomorrow
        opens += timedelta(days=1)
        closes += timedelta(days=1)
    return opens.strftime("%Y-%m-%d"), opens, closes, now


def _shamo_prizes(st):
    try:
        prizes = [(float(a), max(0.0, float(w))) for a, w in json.loads(st["prizes_json"])]
    except Exception:
        prizes = [(0.0, 1.0)]
    return prizes or [(0.0, 1.0)]


@app.route("/api/shamo/status")
@require_telegram_auth
def shamo_status():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    st = _shamo_settings(cur)
    day, opens, closes, now = _shamo_clock(st)
    cur.execute("SELECT box_index, prize FROM shamo_picks WHERE day=? AND user_id=?", (day, uid))
    mine = cur.fetchone()
    # Also report today's earlier pick if the round already closed today (so the UI can show the result).
    if not mine:
        today = now.strftime("%Y-%m-%d")
        cur.execute("SELECT box_index, prize FROM shamo_picks WHERE day=? AND user_id=?", (today, uid))
        mine = cur.fetchone()
    conn.close()
    is_open = opens <= now < closes
    return jsonify({
        "enabled": bool(st["enabled"]), "boxes": int(st["boxes"]),
        "is_open": is_open and bool(st["enabled"]),
        "seconds_to_open": 0 if is_open else max(0, int((opens - now).total_seconds())),
        "seconds_to_close": max(0, int((closes - now).total_seconds())) if is_open else 0,
        "cycle_seconds": 24 * 3600,
        "open_label": opens.strftime("%I:%M %p").lstrip("0"),
        "picked": ({"box": mine["box_index"], "prize": mine["prize"]} if mine else None),
    })


@app.route("/api/shamo/pick", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=10, window_seconds=60)
def shamo_pick():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        st = _shamo_settings(cur)
        if not st["enabled"]:
            conn.rollback(); return jsonify({"error": "Shamo is not active right now"}), 409
        day, opens, closes, now = _shamo_clock(st)
        if not (opens <= now < closes):
            conn.rollback(); return jsonify({"error": "Shamo is closed -- wait for the countdown"}), 409
        try:
            box = int(body.get("box"))
        except (TypeError, ValueError):
            conn.rollback(); return jsonify({"error": "invalid box"}), 400
        if not (0 <= box < int(st["boxes"])):
            conn.rollback(); return jsonify({"error": "invalid box"}), 400
        if st["require_deposit"]:
            cur.execute("SELECT 1 FROM payments WHERE user_id=? AND status='approved' LIMIT 1", (uid,))
            if not cur.fetchone():
                conn.rollback(); return jsonify({"error": "make your first deposit to join Shamo"}), 403
        cur.execute("SELECT 1 FROM shamo_picks WHERE day=? AND user_id=?", (day, uid))
        if cur.fetchone():
            conn.rollback(); return jsonify({"error": "you already picked a box today"}), 409
        # Daily budget cap: once the day's prizes would exceed the budget, the draw falls back to 0.
        cur.execute("SELECT COALESCE(SUM(prize),0) FROM shamo_picks WHERE day=?", (day,))
        spent = float(cur.fetchone()[0] or 0)
        budget = float(st["daily_budget"] or 0)
        pool = [(a, w) for a, w in _shamo_prizes(st) if a == 0 or budget <= 0 or spent + a <= budget]
        if budget > 0 and spent >= budget:
            pool = [(0.0, 1.0)]
        total = sum(w for _, w in pool) or 1.0
        roll = secrets.randbelow(10**6) / 10**6 * total
        prize, acc = 0.0, 0.0
        for amount, weight in pool:
            acc += weight
            if roll < acc:
                prize = amount
                break
        now_s = _now()
        cur.execute("INSERT INTO shamo_picks(day,user_id,box_index,prize,created_at) VALUES (?,?,?,?,?)",
                    (day, uid, box, prize, now_s))
        if prize > 0:
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (prize, uid))
            cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES (?,?,?,?)",
                        (uid, prize, "shamo_prize", now_s))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        return jsonify({"error": "you already picked a box today"}), 409
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return jsonify({"ok": True, "box": box, "prize": prize})


@app.route("/api/admin/shamo", methods=["GET", "POST"])
@require_telegram_auth
@require_admin
def admin_shamo():
    conn = db(); cur = conn.cursor()
    if request.method == "POST":
        b = request.get_json(silent=True) or {}
        try:
            enabled = 1 if b.get("enabled") else 0
            hour = int(b.get("open_hour", 21)); minute = int(b.get("open_minute", 0))
            window = int(b.get("window_minutes", 10)); boxes = int(b.get("boxes", 8))
            budget = float(b.get("daily_budget", 500)); req_dep = 1 if b.get("require_deposit", True) else 0
            prizes = [[float(a), float(w)] for a, w in b.get("prizes", [])]
            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 1 <= window <= 240 and 2 <= boxes <= 20
                    and 0 <= budget <= 1_000_000 and prizes and all(a >= 0 and w >= 0 for a, w in prizes)
                    and sum(w for _, w in prizes) > 0):
                raise ValueError
        except (ValueError, TypeError):
            conn.close(); return jsonify({"error": "invalid settings"}), 400
        cur.execute("""UPDATE shamo_settings SET enabled=?,open_hour=?,open_minute=?,window_minutes=?,boxes=?,
                       prizes_json=?,daily_budget=?,require_deposit=?,updated_at=? WHERE id=1""",
                    (enabled, hour, minute, window, boxes, json.dumps(prizes), budget, req_dep, _now()))
        conn.commit()
        _log_admin_action(g.tg_user["id"], "shamo_settings", {"enabled": enabled, "budget": budget})
    st = dict(_shamo_settings(cur))
    st["prizes"] = json.loads(st.pop("prizes_json"))
    cur.execute("SELECT COUNT(*), COALESCE(SUM(prize),0) FROM shamo_picks WHERE day=?",
                (datetime.now(_ADDIS).strftime("%Y-%m-%d"),))
    n, paid = cur.fetchone()
    conn.close()
    return jsonify({"settings": st, "today_picks": n, "today_paid": float(paid)})
