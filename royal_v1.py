# royal_v1.py -- loaded by webapp_api.py via exec() (same pattern as engagement_v8.py / rewards_v9.py),
# so it shares that module's globals (app, db, _now, require_telegram_auth, require_admin, ...).
#
# Adds (no game math / payout / RNG is touched):
#   1) IN-APP ANNOUNCEMENTS -- admin posts a message (title, text, optional "play" button -> page/game);
#      players see it behind the bell icon with an unread badge. Broadcasts sent from the bot or the
#      Mini App admin panel are stored here too, so everything the admin announces is also inside the app.
#   2) PLAYER STATS for the profile card (total wins, games played, day streak, achievements, VIP tier).
#   3) DAILY MISSION -- "play N games today" -> claim bonus POINTS. Points are a loyalty counter only
#      (NOT cash, never added to balance). Mission size / points are read from env, defaults 5 games / 100 pts.

import json as _rjson
from datetime import timezone as _rtz

_R_ADDIS = _rtz(timedelta(hours=3))
ROYAL_MISSION_GAMES = max(1, int(os.environ.get("ROYAL_MISSION_GAMES", "5") or 5))
ROYAL_MISSION_POINTS = max(0, int(os.environ.get("ROYAL_MISSION_POINTS", "100") or 100))
ROYAL_MAX_ANNOUNCEMENTS = 30
_R_STAKE_SQL = ("(transaction_type LIKE 'game\\_%\\_stake' ESCAPE '\\' "
                "OR transaction_type IN ('number_guess_bet','group_mines_bet','sports_bet'))")
_R_ALLOWED_LINKS = {"", "lobby", "wallet", "sports", "marketplace", "profile", "invite", "wheel", "shamo"}


def _royal_today():
    return datetime.now(_R_ADDIS).strftime("%Y-%m-%d")


def _init_royal_v1():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS app_announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
        link_page TEXT NOT NULL DEFAULT '', pinned INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1, created_by INTEGER, created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS app_announcement_seen (
        user_id INTEGER PRIMARY KEY, last_seen_id INTEGER NOT NULL DEFAULT 0, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS royal_points (
        user_id INTEGER PRIMARY KEY, points INTEGER NOT NULL DEFAULT 0, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS royal_mission_claims (
        user_id INTEGER NOT NULL, day TEXT NOT NULL, points INTEGER NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, day))""")
    conn.commit(); conn.close()


_init_royal_v1()


def royal_add_announcement(body, title="", link_page="", pinned=0, created_by=None):
    """Shared by the admin endpoint and the broadcast endpoint. Returns the new id (or None)."""
    body = str(body or "").strip()[:2000]
    if not body:
        return None
    link = str(link_page or "").strip().lower()[:30]
    if link not in _R_ALLOWED_LINKS and not link.startswith("game:"):
        link = ""
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO app_announcements(title,body,link_page,pinned,active,created_by,created_at) VALUES (?,?,?,?,1,?,?)",
                (str(title or "").strip()[:80], body, link, 1 if pinned else 0, created_by, _now()))
    nid = cur.lastrowid
    # keep the table small: deactivate everything beyond the newest N
    cur.execute("UPDATE app_announcements SET active=0 WHERE active=1 AND id NOT IN "
                "(SELECT id FROM app_announcements WHERE active=1 ORDER BY pinned DESC, id DESC LIMIT ?)", (ROYAL_MAX_ANNOUNCEMENTS,))
    conn.commit(); conn.close()
    return nid


# ------------------------------------------------------------------ announcements (player side)
@app.route("/api/announcements")
@require_telegram_auth
def royal_announcements():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT id,title,body,link_page,pinned,created_at FROM app_announcements WHERE active=1 "
                "ORDER BY pinned DESC, id DESC LIMIT ?", (ROYAL_MAX_ANNOUNCEMENTS,))
    items = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT last_seen_id FROM app_announcement_seen WHERE user_id=?", (uid,))
    row = cur.fetchone(); seen = int(row[0]) if row else 0
    conn.close()
    unread = sum(1 for i in items if i["id"] > seen)
    return jsonify({"items": items, "unread": unread, "last_id": max([i["id"] for i in items] or [0])})


@app.route("/api/announcements/seen", methods=["POST"])
@require_telegram_auth
def royal_announcements_seen():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(id),0) FROM app_announcements WHERE active=1")
    top = int(cur.fetchone()[0] or 0)
    cur.execute("INSERT INTO app_announcement_seen(user_id,last_seen_id,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_seen_id=excluded.last_seen_id, updated_at=excluded.updated_at",
                (uid, top, _now()))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ announcements (admin side)
@app.route("/api/admin/app-announcements", methods=["GET", "POST"])
@require_telegram_auth
@require_admin
def royal_admin_announcements():
    if request.method == "GET":
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT id,title,body,link_page,pinned,created_at FROM app_announcements WHERE active=1 "
                    "ORDER BY pinned DESC, id DESC LIMIT ?", (ROYAL_MAX_ANNOUNCEMENTS,))
        items = [dict(r) for r in cur.fetchall()]; conn.close()
        return jsonify({"items": items})
    data = request.get_json(silent=True) or {}
    body = str(data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "መልዕክት ባዶ ነው"}), 400
    nid = royal_add_announcement(body, data.get("title"), data.get("link_page"), data.get("pinned"), g.tg_user["id"])
    _log_admin_action(g.tg_user["id"], "app_announcement_add", {"id": nid})
    return jsonify({"ok": True, "id": nid})


@app.route("/api/admin/app-announcements/<int:aid>", methods=["DELETE"])
@require_telegram_auth
@require_admin
def royal_admin_announcement_delete(aid):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE app_announcements SET active=0 WHERE id=?", (aid,))
    conn.commit(); conn.close()
    _log_admin_action(g.tg_user["id"], "app_announcement_delete", {"id": aid})
    return jsonify({"ok": True})


# ------------------------------------------------------------------ player stats + daily mission
def _royal_streak(day_rows, today):
    days = {r[0] for r in day_rows}
    d = datetime.strptime(today, "%Y-%m-%d")
    if today not in days:                       # streak is still alive if they played yesterday
        d -= timedelta(days=1)
    n = 0
    while d.strftime("%Y-%m-%d") in days:
        n += 1; d -= timedelta(days=1)
    return n


def _royal_local_day_sql():
    # created_at is stored as UTC text; shift +3h (Addis) before taking the date
    return "substr(datetime(created_at,'+3 hours'),1,10)"


@app.route("/api/royal/summary")
@require_telegram_auth
def royal_summary():
    uid = g.tg_user["id"]
    today = _royal_today()
    conn = db(); cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM transactions WHERE user_id=? AND amount<0 AND {_R_STAKE_SQL}", (uid,))
    played = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id=? AND amount>0 AND "
                "(transaction_type LIKE 'game\\_%\\_payout' ESCAPE '\\' OR transaction_type LIKE 'game\\_%\\_rt\\_payout' ESCAPE '\\' OR transaction_type='sports_win')", (uid,))
    wins = int(cur.fetchone()[0] or 0)
    day_expr = _royal_local_day_sql()
    cur.execute(f"SELECT DISTINCT {day_expr} FROM transactions WHERE user_id=? AND amount<0 AND {_R_STAKE_SQL} "
                "ORDER BY 1 DESC LIMIT 400", (uid,))
    streak = _royal_streak(cur.fetchall(), today)
    cur.execute(f"SELECT COUNT(*) FROM transactions WHERE user_id=? AND amount<0 AND {_R_STAKE_SQL} AND {day_expr}=?", (uid, today))
    today_played = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM royal_mission_claims WHERE user_id=? AND day=?", (uid, today))
    claimed = bool(cur.fetchone()[0])
    cur.execute("SELECT points FROM royal_points WHERE user_id=?", (uid,))
    r = cur.fetchone(); points = int(r[0]) if r else 0
    cur.execute(f"SELECT COALESCE(-SUM(amount),0) FROM transactions WHERE user_id=? AND amount<0 AND {_R_STAKE_SQL}", (uid,))
    wagered = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,)); invited = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id=? AND amount>0 AND transaction_type LIKE '%deposit%'", (uid,))
    deposits = int(cur.fetchone()[0] or 0)
    conn.close()
    lvl, name, base, nxt = _level_for(wagered)
    badges = [
        ("first_game", played >= 1), ("games_10", played >= 10), ("games_100", played >= 100),
        ("first_win", wins >= 1), ("wins_50", wins >= 50), ("streak_3", streak >= 3), ("streak_7", streak >= 7),
        ("invite_1", invited >= 1), ("deposit_1", deposits >= 1), ("level_5", lvl >= 5),
    ]
    return jsonify({
        "wins": wins, "games_played": played, "streak": streak, "points": points,
        "level": lvl, "level_name": name, "level_base": base, "next_level_at": nxt, "wagered": round(wagered, 2),
        "badges_earned": sum(1 for _k, ok in badges if ok), "badges_total": len(badges),
        "badges": [{"key": k, "earned": ok} for k, ok in badges],
        "mission": {"target": ROYAL_MISSION_GAMES, "played": min(today_played, ROYAL_MISSION_GAMES),
                    "points": ROYAL_MISSION_POINTS, "claimed": claimed,
                    "claimable": (not claimed) and today_played >= ROYAL_MISSION_GAMES and ROYAL_MISSION_POINTS > 0},
        "invited": invited,
    })


@app.route("/api/royal/mission/claim", methods=["POST"])
@require_telegram_auth
def royal_mission_claim():
    uid = g.tg_user["id"]
    today = _royal_today()
    day_expr = _royal_local_day_sql()
    conn = db(); cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM transactions WHERE user_id=? AND amount<0 AND {_R_STAKE_SQL} AND {day_expr}=?", (uid, today))
        if int(cur.fetchone()[0] or 0) < ROYAL_MISSION_GAMES:
            return jsonify({"error": f"ዛሬ ቢያንስ {ROYAL_MISSION_GAMES} ጨዋታ ይጫወቱ"}), 400
        try:   # PRIMARY KEY (user_id, day) makes a double-claim impossible, even with two taps at once
            cur.execute("INSERT INTO royal_mission_claims(user_id,day,points,created_at) VALUES (?,?,?,?)",
                        (uid, today, ROYAL_MISSION_POINTS, _now()))
        except Exception:
            return jsonify({"error": "ዛሬ ቀድሞ ወስደዋል"}), 409
        cur.execute("INSERT INTO royal_points(user_id,points,updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET points=points+excluded.points, updated_at=excluded.updated_at",
                    (uid, ROYAL_MISSION_POINTS, _now()))
        conn.commit()
        cur.execute("SELECT points FROM royal_points WHERE user_id=?", (uid,))
        total = int(cur.fetchone()[0])
    finally:
        conn.close()
    return jsonify({"ok": True, "points_added": ROYAL_MISSION_POINTS, "points": total})
