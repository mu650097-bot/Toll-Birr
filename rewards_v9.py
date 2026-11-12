# rewards_v9.py -- loaded by webapp_api.py via exec() (same globals as engagement_v8.py).
#   * Hourly free MYSTERY BOX  (admin decides prizes / budget / cooldown; prize = play-only bonus)
#   * Player LEVEL (from total wagered) + Daily Challenge summary (invite progress)
import json as _json, secrets as _secrets, time as _time

MBOX_DEFAULT_PRIZES = [[0, 40], [1, 30], [2, 15], [5, 10], [10, 4], [20, 1]]
LEVELS = [(0, "Bronze"), (100, "Silver"), (500, "Gold"), (1500, "Platinum"), (4000, "Diamond"),
          (10000, "Master"), (25000, "Champion"), (60000, "Legend"), (150000, "Mythic"), (400000, "King")]


def _init_rewards_v9():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS mbox_settings (id INTEGER PRIMARY KEY CHECK (id=1), enabled INTEGER NOT NULL DEFAULT 0,
        cooldown_min INTEGER NOT NULL DEFAULT 60, daily_budget REAL NOT NULL DEFAULT 500, prizes_json TEXT NOT NULL, updated_at TEXT)""")
    cur.execute("INSERT OR IGNORE INTO mbox_settings(id,enabled,cooldown_min,daily_budget,prizes_json,updated_at) VALUES (1,0,60,500,?,?)",
                (_json.dumps(MBOX_DEFAULT_PRIZES), _now()))
    cur.execute("""CREATE TABLE IF NOT EXISTS mbox_opens (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, prize REAL NOT NULL,
        ts REAL NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL)""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mbox_user_ts ON mbox_opens(user_id, ts DESC)")
    # ADMIN RELEASE mode: the box opens only when the admin releases it (one open per player per release).
    cols = {r[1] for r in cur.execute("PRAGMA table_info(mbox_settings)").fetchall()}
    if "mode" not in cols:
        cur.execute("ALTER TABLE mbox_settings ADD COLUMN mode TEXT NOT NULL DEFAULT 'admin'")
    cur.execute("""CREATE TABLE IF NOT EXISTS mbox_releases (id INTEGER PRIMARY KEY AUTOINCREMENT, released_ts REAL NOT NULL, expires_ts REAL NOT NULL,
        minutes INTEGER NOT NULL, closed INTEGER NOT NULL DEFAULT 0, released_by INTEGER, created_at TEXT NOT NULL)""")
    ocols = {r[1] for r in cur.execute("PRAGMA table_info(mbox_opens)").fetchall()}
    if "release_id" not in ocols:
        cur.execute("ALTER TABLE mbox_opens ADD COLUMN release_id INTEGER")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_mbox_user_release ON mbox_opens(user_id, release_id) WHERE release_id IS NOT NULL")
    conn.commit(); conn.close()


_init_rewards_v9()


def _mbox_settings(cur):
    cur.execute("SELECT * FROM mbox_settings WHERE id=1")
    return cur.fetchone()


def _mbox_prizes(st):
    try:
        p = [(float(a), max(0.0, float(w))) for a, w in _json.loads(st["prizes_json"])]
    except Exception:
        p = [(0.0, 1.0)]
    return p or [(0.0, 1.0)]


def _mbox_day():
    return datetime.now(_ADDIS).strftime("%Y-%m-%d")


def _mbox_mode(st):
    try:
        return "hourly" if str(st["mode"]) == "hourly" else "admin"
    except Exception:
        return "admin"


def _mbox_active_release(cur):
    cur.execute("SELECT * FROM mbox_releases WHERE closed=0 AND expires_ts>? ORDER BY id DESC LIMIT 1", (_time.time(),))
    return cur.fetchone()


@app.route("/api/mbox/status")
@require_telegram_auth
def mbox_status():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    st = _mbox_settings(cur); mode = _mbox_mode(st)
    cur.execute("SELECT prize, ts FROM mbox_opens WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
    last = cur.fetchone()
    cd = int(st["cooldown_min"]) * 60
    out = {"enabled": bool(st["enabled"]), "mode": mode, "cooldown_seconds": cd, "last_prize": float(last["prize"]) if last else None,
           "released": False, "release_seconds_left": 0, "opened_this_release": False}
    if mode == "admin":
        rel = _mbox_active_release(cur)
        if rel:
            cur.execute("SELECT 1 FROM mbox_opens WHERE user_id=? AND release_id=?", (uid, rel["id"]))
            opened = cur.fetchone() is not None
            out.update(released=True, release_seconds_left=max(0, int(rel["expires_ts"] - _time.time())), opened_this_release=opened)
        out.update(seconds_left=0, can_open=bool(st["enabled"]) and out["released"] and not out["opened_this_release"])
    else:
        left = max(0, int(cd - (_time.time() - float(last["ts"])))) if last else 0
        out.update(seconds_left=left, can_open=bool(st["enabled"]) and left == 0)
    conn.close()
    return jsonify(out)


@app.route("/api/mbox/open", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=6, window_seconds=60)
def mbox_open():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        st = _mbox_settings(cur); mode = _mbox_mode(st)
        if not st["enabled"]:
            conn.rollback(); return jsonify({"error": "Mystery Box ለጊዜው ዝግ ነው"}), 409
        cd = int(st["cooldown_min"]) * 60
        release_id = None
        if mode == "admin":
            rel = _mbox_active_release(cur)
            if not rel:
                conn.rollback(); return jsonify({"error": "ሳጥኑ ገና አልተለቀቀም -- አድሚኑ ሲለቅ ይክፈቱ"}), 409
            release_id = int(rel["id"])
            cur.execute("SELECT 1 FROM mbox_opens WHERE user_id=? AND release_id=?", (uid, release_id))
            if cur.fetchone():
                conn.rollback(); return jsonify({"error": "ይህንን ሳጥን አስቀድመው ከፍተዋል -- ቀጣዩን ልቀት ይጠብቁ"}), 409
        else:
            cur.execute("SELECT ts FROM mbox_opens WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
            last = cur.fetchone()
            if last and _time.time() - float(last["ts"]) < cd:
                left = int(cd - (_time.time() - float(last["ts"])))
                conn.rollback(); return jsonify({"error": "ገና አልደረሰም -- ጊዜው ሲደርስ ይክፈቱ", "seconds_left": left}), 409
        day = _mbox_day()
        cur.execute("SELECT COALESCE(SUM(prize),0) FROM mbox_opens WHERE day=?", (day,))
        spent = float(cur.fetchone()[0] or 0); budget = float(st["daily_budget"] or 0)
        pool = [(a, w) for a, w in _mbox_prizes(st) if a == 0 or budget <= 0 or spent + a <= budget]
        if budget > 0 and spent >= budget:
            pool = [(0.0, 1.0)]
        total = sum(w for _, w in pool) or 1.0
        roll = _secrets.randbelow(10**6) / 10**6 * total
        prize, acc = 0.0, 0.0
        for a, w in pool:
            acc += w
            if roll < acc:
                prize = a; break
        now_s = _now()
        cur.execute("INSERT INTO mbox_opens(user_id,prize,ts,day,created_at,release_id) VALUES (?,?,?,?,?,?)", (uid, prize, _time.time(), day, now_s, release_id))
        if prize > 0:
            _bonus.grant_locked_bonus(cur, uid, prize, "mbox_prize", now_s)   # play-only bonus
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return jsonify({"ok": True, "prize": prize, "mode": mode, "cooldown_seconds": cd, "seconds_left": 0 if mode == "admin" else cd, "locked": True})


@app.route("/api/admin/mbox/release", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_mbox_release():
    """Admin presses 'release': every player may open the box ONCE until it expires (default 60 min)."""
    b = request.get_json(silent=True) or {}
    try:
        minutes = int(b.get("minutes", 60))
        if not 1 <= minutes <= 1440: raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "minutes must be 1-1440"}), 400
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("UPDATE mbox_releases SET closed=1 WHERE closed=0")
        now_t = _time.time()
        cur.execute("INSERT INTO mbox_releases(released_ts,expires_ts,minutes,released_by,created_at) VALUES (?,?,?,?,?)",
                    (now_t, now_t + minutes * 60, minutes, g.tg_user["id"], _now()))
        rid = cur.lastrowid
        cur.execute("UPDATE mbox_settings SET enabled=1, mode='admin', updated_at=? WHERE id=1", (_now(),))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    _log_admin_action(g.tg_user["id"], "mbox_release", {"release_id": rid, "minutes": minutes})
    try:   # bell notification for everybody (best effort: never blocks the release)
        royal_add_announcement("🎁 Mystery Box ተለቋል! አሁን ይክፈቱ -- ለ %d ደቂቃ ብቻ።" % minutes, title="📦 Mystery Box", link_page="profile", created_by=g.tg_user["id"])
    except Exception:
        pass
    return jsonify({"ok": True, "release_id": rid, "minutes": minutes})


@app.route("/api/admin/mbox/close", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_mbox_close():
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE mbox_releases SET closed=1 WHERE closed=0"); n = cur.rowcount
    conn.commit(); conn.close()
    _log_admin_action(g.tg_user["id"], "mbox_close", {"closed": n})
    return jsonify({"ok": True, "closed": n})


@app.route("/api/admin/mbox", methods=["GET", "POST"])
@require_telegram_auth
@require_admin
def admin_mbox():
    conn = db(); cur = conn.cursor()
    if request.method == "POST":
        b = request.get_json(silent=True) or {}
        try:
            enabled = 1 if b.get("enabled") else 0
            mode = "hourly" if b.get("mode") == "hourly" else "admin"
            cd = int(b.get("cooldown_min", 60)); budget = float(b.get("daily_budget", 500))
            prizes = [[float(a), float(w)] for a, w in b.get("prizes", [])]
            if not (1 <= cd <= 1440 and 0 <= budget <= 1_000_000 and prizes and all(a >= 0 and w >= 0 for a, w in prizes)
                    and sum(w for _, w in prizes) > 0):
                raise ValueError
        except (ValueError, TypeError):
            conn.close(); return jsonify({"error": "invalid settings"}), 400
        cur.execute("UPDATE mbox_settings SET enabled=?,mode=?,cooldown_min=?,daily_budget=?,prizes_json=?,updated_at=? WHERE id=1",
                    (enabled, mode, cd, budget, _json.dumps(prizes), _now()))
        conn.commit()
        _log_admin_action(g.tg_user["id"], "mbox_settings", {"enabled": enabled, "cooldown_min": cd, "budget": budget})
    st = dict(_mbox_settings(cur)); st["prizes"] = _json.loads(st.pop("prizes_json"))
    cur.execute("SELECT COUNT(*), COALESCE(SUM(prize),0) FROM mbox_opens WHERE day=?", (_mbox_day(),))
    n, paid = cur.fetchone()
    rel = _mbox_active_release(cur); active = None
    if rel:
        cur.execute("SELECT COUNT(*), COALESCE(SUM(prize),0) FROM mbox_opens WHERE release_id=?", (rel["id"],)); ro, rp = cur.fetchone()
        active = {"id": rel["id"], "seconds_left": max(0, int(rel["expires_ts"] - _time.time())), "opens": ro, "paid": float(rp)}
    conn.close()
    return jsonify({"settings": st, "today_opens": n, "today_paid": float(paid), "active_release": active})


def _level_for(wagered):
    idx = 0
    for i, (need, _n) in enumerate(LEVELS):
        if wagered >= need: idx = i
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    return idx + 1, LEVELS[idx][1], LEVELS[idx][0], nxt


@app.route("/api/rewards/summary")
@require_telegram_auth
def rewards_summary():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(-SUM(amount),0) FROM transactions WHERE user_id=? AND amount<0 AND (transaction_type LIKE 'game\\_%\\_stake' ESCAPE '\\' OR transaction_type IN ('number_guess_bet','group_mines_bet','sports_bet'))", (uid,))
    wagered = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,)); invited = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM invite_bonuses WHERE inviter_id=? AND paid_at IS NOT NULL", (uid,)); earned = float(cur.fetchone()[0] or 0)
    _after_dep = _bonus.invite_requires_deposit(cur)
    conn.close()
    lvl, name, base, nxt = _level_for(wagered)
    return jsonify({"level": lvl, "level_name": name, "wagered": round(wagered, 2), "level_base": base, "next_level_at": nxt,
                    "invited": invited, "invite_target": 10, "bonus_per_invite": _bonus.INVITE_BONUS_ETB, "bonus_earned": earned,
                    "bonus_after_deposit": _after_dep})
