# ============================================================
# KENO 80  (exec'd into webapp_api's globals, same pattern as realtime_engine_v3.py)
#
#  * CLASSIC 80 : one shared round for everybody (70 s cycle: 50 s betting + ~20 s drawing).
#                 20 numbers are drawn from 1..80 by the SERVER the moment betting closes.
#  * INSTANT 80 : private round, drawn immediately for that player only.
#  * Players pick 1..10 numbers. Payout = stake x multiplier(picks, hits).
#  * The paytable is GENERATED from the hypergeometric distribution so the long-run RTP is exactly
#    (1 - house_edge) from the admin setting (cabinet_game_settings 'keno'), never hidden manipulation.
#  * "Live" bets / top bets are REAL bets only -- nothing is fabricated.
# ============================================================
import threading as _k80_threading
from math import comb as _k80_comb
from datetime import datetime as _k80_dt, timezone as _k80_tz

K80_N, K80_DRAW, K80_MAXPICK = 80, 20, 10
K80_CYCLE = int(os.getenv("KENO80_CYCLE_SEC", "70"))
K80_BET_SEC = int(os.getenv("KENO80_BET_SEC", "50"))
K80_MAX_BETS_PER_ROUND = int(os.getenv("KENO80_MAX_BETS_PER_ROUND", "5"))
K80_MAX_MULT = float(os.getenv("KENO80_MAX_MULT", "2000"))
K80_EPOCH = _k80_dt(2026, 10, 1, tzinfo=_k80_tz.utc).timestamp()
K80_REVEAL_SEC = 0.7   # client reveals one ball every 0.7 s after betting closes

_k80_conn = db(); _k80_cur = _k80_conn.cursor()
_k80_cur.execute("""CREATE TABLE IF NOT EXISTS keno80_rounds (
    round_id INTEGER PRIMARY KEY, draw_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
_k80_cur.execute("""CREATE TABLE IF NOT EXISTS keno80_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    mode TEXT NOT NULL DEFAULT 'classic', picks_json TEXT NOT NULL, stake REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', hits INTEGER, multiplier REAL, payout REAL,
    draw_json TEXT, created_at TEXT NOT NULL, settled_at TEXT)""")
_k80_cur.execute("CREATE INDEX IF NOT EXISTS idx_k80_bets_round ON keno80_bets(round_id, status)")
_k80_cur.execute("CREATE INDEX IF NOT EXISTS idx_k80_bets_user ON keno80_bets(user_id, id DESC)")
_k80_conn.commit(); _k80_conn.close()


# ------------------------------------------------------------------ paytable
def _k80_p(k, h):
    return _k80_comb(k, h) * _k80_comb(K80_N - k, K80_DRAW - h) / _k80_comb(K80_N, K80_DRAW)


def k80_build_paytable(rtp):
    """{k: {hits: multiplier}} with exact long-run RTP == rtp (multipliers floored to 2 decimals, so the
    real RTP is never above target). Winning hit-counts are those in the top ~30% tail; shares grow with hits."""
    table = {}
    for k in range(1, K80_MAXPICK + 1):
        tail, hmin = 0.0, k
        for h in range(k, 0, -1):             # smallest h whose upper tail stays <= 30%
            tail += _k80_p(k, h)
            if tail <= 0.30:
                hmin = h
            else:
                break
        while True:
            hits = list(range(hmin, k + 1))
            w = {h: float(h - hmin + 1) for h in hits}
            sw = sum(w.values())
            base = {h: (w[h] / sw) / _k80_p(k, h) for h in hits}     # multiplier per unit of RTP scale

            def ret(scale):
                return sum(_k80_p(k, h) * min(K80_MAX_MULT, scale * base[h]) for h in hits)
            lo, hi = 0.0, rtp
            while ret(hi) < rtp and hi < 1e6:                         # grow until the cap-limited curve can reach rtp
                hi *= 2
            for _ in range(80):                                       # bisection: monotone in scale
                mid = (lo + hi) / 2
                if ret(mid) < rtp:
                    lo = mid
                else:
                    hi = mid
            mult = {h: min(K80_MAX_MULT, hi * base[h]) for h in hits}
            if len(hits) > 1 and mult[hits[0]] < 1.0:
                hmin += 1                      # lowest tier would pay less than the stake: drop it
                continue
            break
        table[k] = {h: max(0.0, int(mult[h] * 100) / 100.0) for h in hits}
    return table


_k80_pt_cache = {}


def k80_paytable():
    _enabled, _mn, _mx, edge = _cabinet_limits("keno")
    edge = min(max(float(edge), 0.0), 0.5)
    key = round(edge, 4)
    if key not in _k80_pt_cache:
        _k80_pt_cache.clear()
        _k80_pt_cache[key] = k80_build_paytable(1.0 - edge)
    return _k80_pt_cache[key]


def k80_rtp(table, k):
    return sum(_k80_p(k, h) * m for h, m in table[k].items())


# ------------------------------------------------------------------ timing
def _k80_now():
    return time.time()


def k80_round_of(ts):
    return int((ts - K80_EPOCH) // K80_CYCLE) + 1


def k80_round_start(rid):
    return K80_EPOCH + (rid - 1) * K80_CYCLE


def k80_close_ts(rid):
    return k80_round_start(rid) + K80_BET_SEC


# ------------------------------------------------------------------ draw + settlement
def _k80_mask(name):
    name = (name or "Player").strip() or "Player"
    return (name[0] + "***" + name[-1]) if len(name) > 2 else (name[0] + "***")


def _k80_new_draw():
    return secrets.SystemRandom().sample(range(1, K80_N + 1), K80_DRAW)   # kept in DRAW ORDER (balls are revealed one by one)


def _k80_ensure_draw(cur, rid):
    """Draw exists only AFTER betting closed (called by settle/state), created exactly once."""
    row = cur.execute("SELECT draw_json FROM keno80_rounds WHERE round_id=?", (rid,)).fetchone()
    if row:
        return json.loads(row[0])
    if _k80_now() < k80_close_ts(rid):
        return None
    draw = _k80_new_draw()
    cur.execute("INSERT OR IGNORE INTO keno80_rounds(round_id,draw_json,created_at) VALUES(?,?,?)",
                (rid, json.dumps(draw), _now()))
    row = cur.execute("SELECT draw_json FROM keno80_rounds WHERE round_id=?", (rid,)).fetchone()
    return json.loads(row[0])


def _k80_pay_bet(cur, bet, draw, table):
    picks = json.loads(bet["picks_json"])
    hits = len(set(picks) & set(draw))
    mult = float(table.get(len(picks), {}).get(hits, 0.0))
    stake = float(bet["stake"])
    payout = round(min(stake * mult, MAX_ROUND_PAYOUT_ETB), 2)
    now = _now()
    cur.execute("UPDATE keno80_bets SET status=?,hits=?,multiplier=?,payout=?,settled_at=? WHERE id=? AND status='pending'",
                ("won" if payout > 0 else "lost", hits, mult, payout, now, bet["id"]))
    if cur.rowcount == 1 and payout > 0:
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (payout, bet["user_id"]))
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",
                    (bet["user_id"], payout, "game_keno80_payout", now))
    return hits, mult, payout


def k80_settle_due():
    """Settle every classic round whose betting window is closed. Idempotent; safe from any thread."""
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        rids = [r[0] for r in cur.execute("SELECT DISTINCT round_id FROM keno80_bets WHERE status='pending' AND mode='classic'").fetchall()]
        table = None
        for rid in rids:
            if _k80_now() < k80_close_ts(rid):
                continue
            draw = _k80_ensure_draw(cur, rid)
            if draw is None:
                continue
            table = table or k80_paytable()
            for bet in cur.execute("SELECT * FROM keno80_bets WHERE round_id=? AND status='pending'", (rid,)).fetchall():
                _k80_pay_bet(cur, bet, draw, table)
        conn.commit()
    except Exception:
        conn.rollback(); logger.exception("keno80 settle failed")
    finally:
        conn.close()


def _k80_loop():
    while True:
        time.sleep(2)
        try:
            k80_settle_due()
        except Exception:
            logger.exception("keno80 loop")


if os.getenv("KENO80_DISABLE_THREAD", "0") != "1":
    _k80_threading.Thread(target=_k80_loop, daemon=True, name="keno80-settle").start()


# ------------------------------------------------------------------ validation
def _k80_clean_picks(raw):
    try:
        picks = sorted({int(x) for x in (raw or [])})
    except (TypeError, ValueError):
        raise ValueError("invalid numbers")
    if not (1 <= len(picks) <= K80_MAXPICK) or picks[0] < 1 or picks[-1] > K80_N:
        raise ValueError(f"pick 1 to {K80_MAXPICK} numbers between 1 and {K80_N}")
    return picks


def _k80_check_stake(stake, picks_n, table):
    enabled, mn, mx, _edge = _cabinet_limits("keno")
    if not enabled:
        raise ValueError("Keno is disabled by admin")
    if stake < mn or stake > mx:
        raise ValueError(f"stake must be between {mn:.0f} and {mx:.0f} ብር")
    top = max(table[picks_n].values())
    if stake * top > MAX_ROUND_PAYOUT_ETB:
        raise ValueError(f"max win would exceed the {MAX_ROUND_PAYOUT_ETB:.0f} ብር payout limit -- lower the stake or picks")


def _k80_debit(cur, uid, stake):
    cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (stake, uid, stake))
    if cur.rowcount != 1:
        raise ValueError("insufficient balance")
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",
                (uid, -stake, "game_keno80_stake", _now()))


# ------------------------------------------------------------------ endpoints
@app.route("/api/keno80/state")
@require_telegram_auth
def keno80_state():
    uid = g.tg_user["id"]
    now = _k80_now()
    rid = k80_round_of(now)
    start, close = k80_round_start(rid), k80_close_ts(rid)
    phase = "betting" if now < close else "drawing"
    table = k80_paytable()
    k80_settle_due()
    conn = db(); cur = conn.cursor()
    draw_now = None
    if phase == "drawing":
        cur.execute("BEGIN IMMEDIATE"); draw_now = _k80_ensure_draw(cur, rid); conn.commit()
    # live feed: current round while betting, the same round while its draw is shown
    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(stake),0) s FROM keno80_bets WHERE round_id=? AND mode='classic'", (rid,))
    agg = cur.fetchone()
    cur.execute("""SELECT b.picks_json,b.stake,b.status,b.payout,u.first_name FROM keno80_bets b JOIN users u ON u.user_id=b.user_id
                   WHERE b.round_id=? AND b.mode='classic' ORDER BY b.stake DESC, b.id ASC LIMIT 20""", (rid,))
    top = [{"name": _k80_mask(r["first_name"]), "picks": json.loads(r["picks_json"]), "stake": r["stake"],
            "status": r["status"], "payout": r["payout"]} for r in cur.fetchall()]
    cur.execute("SELECT id,round_id,mode,picks_json,stake,status,hits,multiplier,payout,draw_json FROM keno80_bets WHERE user_id=? AND round_id=? AND mode='classic' ORDER BY id DESC", (uid, rid))
    mine = [dict(picks=json.loads(r["picks_json"]), **{k: r[k] for k in ("id", "stake", "status", "hits", "multiplier", "payout")}) for r in cur.fetchall()]
    cur.execute("SELECT round_id,draw_json FROM keno80_rounds ORDER BY round_id DESC LIMIT 12")
    results = [{"round_id": r["round_id"], "draw": json.loads(r["draw_json"])} for r in cur.fetchall()]
    conn.close()
    _en, mn, mx, edge = _cabinet_limits("keno")
    return jsonify({
        "server_time": now, "round_id": rid, "phase": phase, "bet_seconds_left": max(0.0, close - now),
        "round_seconds_left": max(0.0, start + K80_CYCLE - now), "start_ts": start, "close_ts": close, "end_ts": start + K80_CYCLE,
        "reveal_sec": K80_REVEAL_SEC, "draw": draw_now,
        "live": {"count": agg["c"], "total": round(agg["s"], 2), "top": top},
        "my_bets": mine, "results": results,
        "limits": {"min": mn, "max": mx, "max_picks": K80_MAXPICK, "max_bets_per_round": K80_MAX_BETS_PER_ROUND},
        "paytable": {str(k): {str(h): m for h, m in v.items()} for k, v in table.items()},
        "rtp": round(1 - edge, 4),
    })


@app.route("/api/keno80/bet", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=12, window_seconds=30)
def keno80_bet():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    try:
        picks = _k80_clean_picks(body.get("picks"))
        stake = parse_money(body.get("stake"), "stake")
        table = k80_paytable()
        _k80_check_stake(stake, len(picks), table)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        now = _k80_now(); rid = k80_round_of(now)
        if now >= k80_close_ts(rid):
            conn.rollback(); conn.close()
            return jsonify({"error": "betting is closed -- the draw has started. Bet on the next round."}), 409
        n = cur.execute("SELECT COUNT(*) FROM keno80_bets WHERE round_id=? AND user_id=? AND mode='classic'", (rid, uid)).fetchone()[0]
        if n >= K80_MAX_BETS_PER_ROUND:
            conn.rollback(); conn.close()
            return jsonify({"error": f"max {K80_MAX_BETS_PER_ROUND} bets per round"}), 429
        _k80_debit(cur, uid, stake)
        cur.execute("INSERT INTO keno80_bets(round_id,user_id,mode,picks_json,stake,created_at) VALUES(?,?,?,?,?,?)",
                    (rid, uid, "classic", json.dumps(picks), stake, _now()))
        bet_id = cur.lastrowid
        conn.commit()
    except ValueError as e:
        conn.rollback(); conn.close(); return jsonify({"error": str(e)}), 400
    except Exception:
        conn.rollback(); conn.close(); logger.exception("keno80 bet failed")
        return jsonify({"error": "bet failed; please retry"}), 500
    conn.close()
    return jsonify({"ok": True, "bet_id": bet_id, "round_id": rid, "picks": picks, "stake": stake})


@app.route("/api/keno80/instant", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=20, window_seconds=30)
def keno80_instant():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    try:
        picks = _k80_clean_picks(body.get("picks"))
        stake = parse_money(body.get("stake"), "stake")
        table = k80_paytable()
        _k80_check_stake(stake, len(picks), table)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        _k80_debit(cur, uid, stake)
        draw = _k80_new_draw()
        cur.execute("INSERT INTO keno80_bets(round_id,user_id,mode,picks_json,stake,draw_json,created_at) VALUES(0,?,?,?,?,?,?)",
                    (uid, "instant", json.dumps(picks), stake, json.dumps(draw), _now()))
        bet = cur.execute("SELECT * FROM keno80_bets WHERE id=?", (cur.lastrowid,)).fetchone()
        hits, mult, payout = _k80_pay_bet(cur, bet, draw, table)
        bal = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()[0]
        conn.commit()
    except ValueError as e:
        conn.rollback(); conn.close(); return jsonify({"error": str(e)}), 400
    except Exception:
        conn.rollback(); conn.close(); logger.exception("keno80 instant failed")
        return jsonify({"error": "bet failed; please retry"}), 500
    conn.close()
    return jsonify({"ok": True, "draw": draw, "picks": picks, "hits": hits, "multiplier": mult,
                    "payout": payout, "stake": stake, "balance": bal})


@app.route("/api/keno80/history")
@require_telegram_auth
def keno80_history():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT id,round_id,mode,picks_json,stake,status,hits,multiplier,payout,draw_json,created_at FROM keno80_bets WHERE user_id=? ORDER BY id DESC LIMIT 40", (uid,))
    rows = []
    for r in cur.fetchall():
        d = dict(r); d["picks"] = json.loads(d.pop("picks_json")); dj = d.pop("draw_json")
        d["draw"] = json.loads(dj) if dj else None
        rows.append(d)
    conn.close()
    return jsonify({"bets": rows})
