# BETPRO LAYER (exec'd by webapp_api.py right after engagement_v8.py, shares its globals).
#  1) promo images: the admin uploads ANY photo for the Sports hero banner, the Casino hero banner and for every game cover.
#  2) /api/betpro/stats: Total Wins / Games Played / Day Streak / Level for the profile header.
# Images live in the same data volume as the home banners (folder "banners"). Only JPG/PNG/WEBP, max 15 MB, validated by magic bytes.
import re as _re
import uuid as _uuid

_PROMO_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)) or ".", "banners")
_PROMO_FIXED = ("sports_hero", "casino_hero")
_PROMO_EXT = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}
_PROMO_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _init_betpro():
    os.makedirs(_PROMO_DIR, exist_ok=True)
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS promo_images (
        slot TEXT PRIMARY KEY, filename TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.commit(); conn.close()


_init_betpro()


def _promo_slot_ok(slot):
    return slot in _PROMO_FIXED or bool(_re.fullmatch(r"game_[a-z0-9_]{1,40}", slot or ""))


def save_promo_bytes(slot, data):
    if not _promo_slot_ok(slot):
        raise ValueError("unknown image slot")
    ext = next((e for magic, e in _PROMO_EXT.items() if data.startswith(magic)), None)
    if ext == "webp" and data[8:12] != b"WEBP":
        ext = None
    if not ext:
        raise ValueError("only JPG, PNG or WEBP images are allowed")
    if len(data) > 15 * 1024 * 1024:   # phone photos are often 5-10 MB
        raise ValueError("image too large (15MB max)")
    os.makedirs(_PROMO_DIR, exist_ok=True)
    name = f"promo_{_uuid.uuid4().hex}.{ext}"
    with open(os.path.join(_PROMO_DIR, name), "wb") as f:
        f.write(data)
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT filename FROM promo_images WHERE slot=?", (slot,)); old = cur.fetchone()
    cur.execute("INSERT INTO promo_images(slot,filename,updated_at) VALUES(?,?,?) ON CONFLICT(slot) DO UPDATE SET filename=excluded.filename, updated_at=excluded.updated_at",
                (slot, name, _now()))
    conn.commit(); conn.close()
    if old:
        try: os.remove(os.path.join(_PROMO_DIR, os.path.basename(old["filename"])))
        except OSError: pass
    return name


def _promo_items():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT slot, updated_at FROM promo_images"); rows = cur.fetchall(); conn.close()
    return {r["slot"]: {"image": f"/api/promo/{r['slot']}/image?v={abs(hash(r['updated_at'])) % 10**8}"} for r in rows}


@app.route("/api/promo/images")
@require_telegram_auth
def promo_images():
    return jsonify({"items": _promo_items()})


@app.route("/api/promo/<slot>/image")
def promo_image(slot):
    # Public on purpose (<img> cannot send the Telegram auth header); these are promo art, never user data.
    if not _promo_slot_ok(slot):
        return jsonify({"error": "not found"}), 404
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT filename FROM promo_images WHERE slot=?", (slot,)); row = cur.fetchone(); conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    name = os.path.basename(row["filename"]); ext = name.rsplit(".", 1)[-1]
    try:
        with open(os.path.join(_PROMO_DIR, name), "rb") as f: data = f.read()
    except OSError:
        return jsonify({"error": "not found"}), 404
    resp = app.response_class(data, mimetype=_PROMO_MIME.get(ext, "application/octet-stream"))
    resp.headers["Cache-Control"] = "public, max-age=3600"; resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.route("/api/admin/promo/<slot>", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_promo_set(slot):
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "photo is required"}), 400
    try:
        save_promo_bytes(slot, photo.read())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    _log_admin_action(g.tg_user["id"], "promo_image_set", {"slot": slot})
    return jsonify({"ok": True, "items": _promo_items()})


@app.route("/api/admin/promo/<slot>", methods=["DELETE"])
@require_telegram_auth
@require_admin
def admin_promo_delete(slot):
    if not _promo_slot_ok(slot):
        return jsonify({"error": "unknown image slot"}), 400
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT filename FROM promo_images WHERE slot=?", (slot,)); row = cur.fetchone()
    cur.execute("DELETE FROM promo_images WHERE slot=?", (slot,)); conn.commit(); conn.close()
    if row:
        try: os.remove(os.path.join(_PROMO_DIR, os.path.basename(row["filename"])))
        except OSError: pass
    _log_admin_action(g.tg_user["id"], "promo_image_delete", {"slot": slot})
    return jsonify({"ok": True, "items": _promo_items()})


@app.route("/api/betpro/stats")
@require_telegram_auth
def betpro_stats():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN payout>stake THEN 1 ELSE 0 END),0) w FROM game_history WHERE user_id=?", (uid,))
    r = cur.fetchone(); played, wins = int(r["n"] or 0), int(r["w"] or 0)
    cur.execute("SELECT DISTINCT substr(created_at,1,10) d FROM game_history WHERE user_id=? ORDER BY d DESC LIMIT 400", (uid,))
    days = [x["d"] for x in cur.fetchall()]; conn.close()
    streak = 0
    if days:
        cur_day = datetime.strptime(days[0], "%Y-%m-%d").date()
        today = datetime.now().date()
        if (today - cur_day).days <= 1:                       # played today or yesterday: the streak is still alive
            streak = 1
            for d in days[1:]:
                dd = datetime.strptime(d, "%Y-%m-%d").date()
                if (cur_day - dd).days == 1: streak += 1; cur_day = dd
                else: break
    level = 1 + played // 40                                  # a level every 40 rounds
    return jsonify({"level": level, "progress_pct": int((played % 40) * 100 / 40), "total_wins": wins, "games_played": played, "day_streak": streak})
