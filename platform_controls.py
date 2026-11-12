"""Admin-controlled platform economics, shared by the API process and the bot process.

Everything is stored in the existing ``platform_settings`` table (key/value), so a change made by the admin is
read on the very next request/bet -- nothing is cached and no restart is needed.

1. WELCOME BONUS      -- every NEW user row gets ``welcome_bonus_amount`` ETB (default 10) exactly once.
                         Done by a SQLite trigger so it covers every place a user can be created (Mini App API,
                         bot /start, age gate, invite claim). Play-only by default (see bonus_wallet.py).
2. GLOBAL MIN BET     -- one minimum stake that replaces the per-game minimum for ALL games.
3. GLOBAL HOUSE EDGE  -- one house edge that replaces the per-game edge (and the pool/sports rake) for ALL games.
4. HIGH-STAKES CASHBACK -- admin picks who qualifies (wagered >= threshold) and how much they get back
                         (% of net loss, % of turnover, or a flat amount), with a per-player cap.
"""
import json
import time

# --- keys / defaults -------------------------------------------------------------------------------------------
DEFAULTS = {
    # welcome bonus
    "welcome_bonus_enabled": "1",
    "welcome_bonus_amount": "10",
    "welcome_bonus_locked": "1",          # 1 = play-only (winnings withdrawable), 0 = fully withdrawable
    "welcome_bonus_requires_deposit": "1",  # 1 = bonus is paid after the FIRST approved deposit (anti multi-account), 0 = at signup
    "welcome_bonus_min_deposit": "10",    # smallest first deposit that unlocks the welcome bonus
    # invite bonus (anti multi-account): inviter is paid after the INVITED person's first qualifying deposit
    "invite_bonus_requires_deposit": "1",
    "invite_bonus_min_deposit": "10",
    # owner alert (Telegram) when bonus + cashback eat too much of the house profit
    "cost_alert_enabled": "1",
    "cost_alert_window_days": "7",
    "cost_alert_bonus_pct": "50",         # alert when bonus+cashback > this % of house profit in the window
    "cost_alert_min_bonus": "100",        # ...and at least this many ETB were given (avoids noise on tiny numbers)
    # global limits
    "global_min_bet_enabled": "1",
    "global_min_bet": "1",
    "global_house_edge_enabled": "0",     # off by default so each game keeps its tuned edge until the admin opts in
    "global_house_edge": "0.15",
    # high-stakes cashback
    "cashback_enabled": "0",
    "cashback_mode": "percent_loss",      # percent_loss | percent_wager | fixed
    "cashback_percent": "10",
    "cashback_fixed_amount": "50",
    "cashback_min_wager": "1000",         # a player qualifies when staked >= this inside the window
    "cashback_max_per_player": "1000",    # 0 = no cap
    "cashback_period_days": "7",
    "cashback_locked": "1",
    # VIP tiers: when enabled, the % (and the qualifying wager) come from the player's tier for the window
    "cashback_tiers_enabled": "0",
    "cashback_tiers": '[{"name":"Silver","min_wager":1000,"percent":5},{"name":"Gold","min_wager":5000,"percent":8},{"name":"Platinum","min_wager":20000,"percent":12}]',
}
MAX_TIERS = 10
CASHBACK_MODES = ("percent_loss", "percent_wager", "fixed")

_STAKE_SQL = ("(transaction_type LIKE 'game\\_%\\_stake' ESCAPE '\\' "
              "OR transaction_type IN ('number_guess_bet','group_mines_bet','sports_bet'))")
_RETURN_SQL = ("(transaction_type LIKE 'game\\_%\\_payout' ESCAPE '\\' "
               "OR transaction_type LIKE 'game\\_%\\_refund' ESCAPE '\\' "
               "OR transaction_type IN ('number_guess_win','group_mines_win','group_mines_timeout_refund',"
               "'sports_win','sports_refund'))")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# --- schema ----------------------------------------------------------------------------------------------------
def init_platform_controls(conn):
    """Create tables, default settings and the welcome-bonus trigger. Idempotent; safe from both processes.
    ``conn`` is a sqlite3 connection (any row_factory). Commits."""
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS platform_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
    now = _now()
    for k, v in DEFAULTS.items():
        cur.execute("INSERT OR IGNORE INTO platform_settings(key,value,updated_at) VALUES(?,?,?)", (k, v, now))
    cols = {r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
    if cols and "bonus_locked" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN bonus_locked REAL DEFAULT 0")
    cur.execute("""CREATE TABLE IF NOT EXISTS welcome_bonus_grants (
        user_id INTEGER PRIMARY KEY, amount REAL NOT NULL, locked INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)""")
    icols = {r[1] for r in cur.execute("PRAGMA table_info(invite_bonuses)").fetchall()}
    if icols and "paid_at" not in icols:           # old rows were paid immediately -> mark them paid
        cur.execute("ALTER TABLE invite_bonuses ADD COLUMN paid_at TEXT")
        cur.execute("UPDATE invite_bonuses SET paid_at=created_at")
    cur.execute("""CREATE TABLE IF NOT EXISTS cashback_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
        mode TEXT NOT NULL, players INTEGER NOT NULL DEFAULT 0, total_paid REAL NOT NULL DEFAULT 0,
        admin_id INTEGER, created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS cashback_grants (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, user_id INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'auto',
        staked REAL NOT NULL DEFAULT 0, net_loss REAL NOT NULL DEFAULT 0, amount REAL NOT NULL,
        locked INTEGER NOT NULL DEFAULT 1, admin_id INTEGER, note TEXT, created_at TEXT NOT NULL,
        UNIQUE(run_id, user_id))""")
    # One trigger = every code path that creates a user gets the bonus exactly once, with the CURRENT admin values.
    cur.execute("DROP TRIGGER IF EXISTS trg_welcome_bonus")
    cur.execute("""
    CREATE TRIGGER trg_welcome_bonus AFTER INSERT ON users
    WHEN COALESCE((SELECT value FROM platform_settings WHERE key='welcome_bonus_enabled'),'0')='1'
     AND COALESCE((SELECT value FROM platform_settings WHERE key='welcome_bonus_requires_deposit'),'1')!='1'
     AND COALESCE(CAST((SELECT value FROM platform_settings WHERE key='welcome_bonus_amount') AS REAL),0) > 0
     AND NOT EXISTS (SELECT 1 FROM welcome_bonus_grants WHERE user_id=NEW.user_id)
    BEGIN
      INSERT INTO welcome_bonus_grants(user_id,amount,locked,created_at)
        VALUES(NEW.user_id,
               ROUND(CAST((SELECT value FROM platform_settings WHERE key='welcome_bonus_amount') AS REAL),2),
               CASE WHEN COALESCE((SELECT value FROM platform_settings WHERE key='welcome_bonus_locked'),'1')='1' THEN 1 ELSE 0 END,
               strftime('%Y-%m-%d %H:%M:%S','now','localtime'));
      UPDATE users SET
        balance = COALESCE(balance,0) + (SELECT amount FROM welcome_bonus_grants WHERE user_id=NEW.user_id),
        bonus_locked = COALESCE(bonus_locked,0) +
            (SELECT amount*locked FROM welcome_bonus_grants WHERE user_id=NEW.user_id)
      WHERE user_id=NEW.user_id;
      INSERT INTO transactions(user_id,amount,transaction_type,created_at)
        VALUES(NEW.user_id,(SELECT amount FROM welcome_bonus_grants WHERE user_id=NEW.user_id),'welcome_bonus',
               strftime('%Y-%m-%d %H:%M:%S','now','localtime'));
    END""")
    conn.commit()


def grant_welcome_after_deposit(cur, uid, deposit_amount):
    """Pay the welcome bonus once, right after a user's FIRST approved deposit (when welcome_bonus_requires_deposit=1).
    Call inside the deposit-approval transaction (caller commits). Idempotent: welcome_bonus_grants.user_id is unique.
    Returns the amount granted (0.0 when nothing was paid)."""
    r = read_raw(cur)
    if r["welcome_bonus_enabled"] != "1" or r["welcome_bonus_requires_deposit"] != "1":
        return 0.0
    amount = round(max(0.0, _f(r["welcome_bonus_amount"], 0.0)), 2)
    if amount <= 0 or float(deposit_amount) < _f(r["welcome_bonus_min_deposit"], 0.0):
        return 0.0
    locked = 1 if r["welcome_bonus_locked"] == "1" else 0
    now = _now()
    cur.execute("INSERT OR IGNORE INTO welcome_bonus_grants(user_id,amount,locked,created_at) VALUES(?,?,?,?)",
                (uid, amount, locked, now))
    if cur.rowcount != 1:
        return 0.0
    cur.execute("UPDATE users SET balance=COALESCE(balance,0)+?, bonus_locked=COALESCE(bonus_locked,0)+? WHERE user_id=?",
                (amount, amount * locked, uid))
    if cur.rowcount != 1:
        cur.execute("DELETE FROM welcome_bonus_grants WHERE user_id=?", (uid,))
        return 0.0
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",
                (uid, amount, "welcome_bonus", now))
    return amount


# --- settings --------------------------------------------------------------------------------------------------
def _f(v, d=0.0):
    try:
        x = float(v)
        return x if x == x and x not in (float("inf"), float("-inf")) else d
    except (TypeError, ValueError):
        return d


def read_raw(cur):
    cur.execute("SELECT key,value FROM platform_settings")
    raw = dict(DEFAULTS)
    for r in cur.fetchall():
        raw[r[0]] = r[1]
    return raw


def parse_tiers(raw):
    """JSON text -> clean list of {name,min_wager,percent} sorted by min_wager. Bad data -> []."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        out = []
        for t in data[:MAX_TIERS]:
            mw, pc = _f(t.get("min_wager"), None), _f(t.get("percent"), None)
            if mw is None or pc is None or mw < 0 or not (0 <= pc <= 100):
                continue
            out.append({"name": str(t.get("name", ""))[:20] or "Tier", "min_wager": round(mw, 2), "percent": round(pc, 4)})
        return sorted(out, key=lambda x: x["min_wager"])
    except Exception:
        return []


def tier_for(c, staked):
    """Highest tier whose min_wager <= staked, or None."""
    best = None
    for t in c["cashback_tiers"]:
        if staked >= t["min_wager"]:
            best = t
    return best


def get_controls(cur):
    """Typed view of every admin control. Reads the DB each call (a few rows) so changes apply instantly."""
    r = read_raw(cur)
    mode = r["cashback_mode"] if r["cashback_mode"] in CASHBACK_MODES else "percent_loss"
    return {
        "welcome_bonus_enabled": r["welcome_bonus_enabled"] == "1",
        "welcome_bonus_amount": round(max(0.0, _f(r["welcome_bonus_amount"], 10.0)), 2),
        "welcome_bonus_locked": r["welcome_bonus_locked"] == "1",
        "welcome_bonus_requires_deposit": r["welcome_bonus_requires_deposit"] == "1",
        "invite_bonus_requires_deposit": r["invite_bonus_requires_deposit"] == "1",
        "invite_bonus_min_deposit": max(0.0, _f(r["invite_bonus_min_deposit"], 10.0)),
        "cost_alert_enabled": r["cost_alert_enabled"] == "1",
        "cost_alert_window_days": min(90.0, max(1.0, _f(r["cost_alert_window_days"], 7.0))),
        "cost_alert_bonus_pct": max(1.0, _f(r["cost_alert_bonus_pct"], 50.0)),
        "cost_alert_min_bonus": max(0.0, _f(r["cost_alert_min_bonus"], 100.0)),
        "welcome_bonus_min_deposit": max(0.0, _f(r["welcome_bonus_min_deposit"], 10.0)),
        "global_min_bet_enabled": r["global_min_bet_enabled"] == "1",
        "global_min_bet": round(max(0.01, _f(r["global_min_bet"], 1.0)), 2),
        "global_house_edge_enabled": r["global_house_edge_enabled"] == "1",
        "global_house_edge": min(0.95, max(0.0, _f(r["global_house_edge"], 0.15))),
        "cashback_enabled": r["cashback_enabled"] == "1",
        "cashback_mode": mode,
        "cashback_percent": max(0.0, _f(r["cashback_percent"], 10.0)),
        "cashback_fixed_amount": max(0.0, _f(r["cashback_fixed_amount"], 0.0)),
        "cashback_min_wager": max(0.0, _f(r["cashback_min_wager"], 0.0)),
        "cashback_max_per_player": max(0.0, _f(r["cashback_max_per_player"], 0.0)),
        "cashback_period_days": max(0.04, _f(r["cashback_period_days"], 7.0)),
        "cashback_locked": r["cashback_locked"] == "1",
        "cashback_tiers_enabled": r["cashback_tiers_enabled"] == "1",
        "cashback_tiers": parse_tiers(r["cashback_tiers"]),
    }


def apply_limits(enabled, mn, mx, edge, c):
    """Per-game (enabled, min, max, edge) -> effective values after the admin's global overrides."""
    if c["global_min_bet_enabled"]:
        mn = c["global_min_bet"]
        mx = max(float(mx), mn)           # a game's max can never sit below the global minimum
    if c["global_house_edge_enabled"]:
        edge = c["global_house_edge"]
    return enabled, float(mn), float(mx), float(edge)


def effective_rake(default_rake, c):
    """Pool-game / sports rake: the global house edge when the admin enabled it, else the configured default."""
    return c["global_house_edge"] if c["global_house_edge_enabled"] else float(default_rake)


def effective_fixed_fee(entry_fee, c):
    """Fixed-entry games (Boom / Number): the fee can never be below the global minimum bet."""
    return max(float(entry_fee), c["global_min_bet"]) if c["global_min_bet_enabled"] else float(entry_fee)


def validate_update(body, max_house_edge):
    """Validate a partial admin update -> {key: str_value}. Raises ValueError with a readable message."""
    out = {}

    def flag(name):
        if name in body:
            out[name] = "1" if bool(body[name]) else "0"

    def num(name, lo, hi, scale=1.0):
        if name in body and body[name] is not None and body[name] != "":
            v = _f(body[name], None)
            if v is None:
                raise ValueError(f"{name} must be a number")
            v = v * scale
            if not (lo <= v <= hi):
                raise ValueError(f"{name} must be between {lo/scale:g} and {hi/scale:g}")
            out[name] = repr(round(v, 6))

    for k in ("welcome_bonus_enabled", "welcome_bonus_locked", "welcome_bonus_requires_deposit", "invite_bonus_requires_deposit", "cost_alert_enabled", "global_min_bet_enabled",
              "global_house_edge_enabled", "cashback_enabled", "cashback_locked", "cashback_tiers_enabled"):
        flag(k)
    num("welcome_bonus_amount", 0, 100000)
    num("welcome_bonus_min_deposit", 0, 100000000)
    num("invite_bonus_min_deposit", 0, 100000000)
    num("cost_alert_window_days", 1, 90)
    num("cost_alert_bonus_pct", 1, 1000)
    num("cost_alert_min_bonus", 0, 1000000000)
    num("global_min_bet", 0.01, 1000000)
    if "global_house_edge_percent" in body and body["global_house_edge_percent"] not in (None, ""):
        v = _f(body["global_house_edge_percent"], None)
        if v is None or not (0 <= v / 100.0 <= max_house_edge):
            raise ValueError(f"house edge must be between 0% and {max_house_edge*100:g}%")
        out["global_house_edge"] = repr(round(v / 100.0, 6))
    num("cashback_percent", 0, 100)
    num("cashback_fixed_amount", 0, 1000000)
    num("cashback_min_wager", 0, 1000000000)
    num("cashback_max_per_player", 0, 1000000000)
    num("cashback_period_days", 0.04, 365)
    if "cashback_tiers" in body:
        tiers = body["cashback_tiers"]
        if not isinstance(tiers, list) or not (1 <= len(tiers) <= MAX_TIERS):
            raise ValueError(f"cashback_tiers must be a list of 1-{MAX_TIERS} tiers")
        clean = parse_tiers(tiers)
        if len(clean) != len(tiers):
            raise ValueError("each tier needs name, min_wager >= 0 and percent between 0 and 100")
        if len({t["min_wager"] for t in clean}) != len(clean):
            raise ValueError("tier min_wager values must be different")
        out["cashback_tiers"] = json.dumps(clean, separators=(",", ":"))
    if "cashback_mode" in body:
        if body["cashback_mode"] not in CASHBACK_MODES:
            raise ValueError("cashback_mode must be one of: " + ", ".join(CASHBACK_MODES))
        out["cashback_mode"] = body["cashback_mode"]
    return out


def save_settings(cur, values):
    now = _now()
    for k, v in values.items():
        cur.execute("INSERT INTO platform_settings(key,value,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (k, v, now))


# --- cashback --------------------------------------------------------------------------------------------------
def _window(cur, c, now_ts=None):
    """(start, end). Starts where the previous run ended so nobody is paid twice for the same play."""
    end = now_ts or _now()
    cur.execute("SELECT MAX(period_end) FROM cashback_runs")
    last = cur.fetchone()[0]
    if last:
        return last, end
    t = time.time() - c["cashback_period_days"] * 86400
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)), end


def cashback_amount(c, staked, net_loss):
    pct = c["cashback_percent"]
    if c["cashback_tiers_enabled"] and c["cashback_tiers"] and c["cashback_mode"] != "fixed":
        t = tier_for(c, staked)
        pct = t["percent"] if t else 0.0
    if c["cashback_mode"] == "fixed":
        amt = c["cashback_fixed_amount"]
    elif c["cashback_mode"] == "percent_wager":
        amt = staked * pct / 100.0
    else:
        amt = max(0.0, net_loss) * pct / 100.0
    if c["cashback_max_per_player"] > 0:
        amt = min(amt, c["cashback_max_per_player"])
    return round(max(0.0, amt), 2)


def cashback_candidates(cur, c, start, end):
    """High-stakes players of the window with the cashback each would receive."""
    cur.execute(f"""
        SELECT user_id,
               COALESCE(SUM(CASE WHEN {_STAKE_SQL} AND amount<0 THEN -amount ELSE 0 END),0) AS staked,
               COALESCE(SUM(CASE WHEN {_RETURN_SQL} AND amount>0 THEN amount ELSE 0 END),0) AS returned
        FROM transactions WHERE created_at>? AND created_at<=? GROUP BY user_id""", (start, end))
    use_tiers = c["cashback_tiers_enabled"] and c["cashback_tiers"] and c["cashback_mode"] != "fixed"
    min_wager = c["cashback_tiers"][0]["min_wager"] if use_tiers else c["cashback_min_wager"]
    out = []
    for r in cur.fetchall():
        staked, returned = float(r[1]), float(r[2])
        if staked <= 0 or staked < min_wager:
            continue
        net_loss = round(staked - returned, 2)
        amt = cashback_amount(c, staked, net_loss)
        if amt > 0:
            item = {"user_id": int(r[0]), "staked": round(staked, 2), "net_loss": net_loss, "cashback": amt}
            if use_tiers:
                item["tier"] = (tier_for(c, staked) or {}).get("name")
            out.append(item)
    out.sort(key=lambda x: -x["staked"])
    return out


def _credit(cur, uid, amount, locked, now):
    cur.execute("UPDATE users SET balance=COALESCE(balance,0)+?, bonus_locked=COALESCE(bonus_locked,0)+? WHERE user_id=?",
                (amount, amount if locked else 0.0, uid))
    if cur.rowcount != 1:
        return False
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",
                (uid, amount, "cashback", now))
    return True


def preview_cashback(cur):
    c = get_controls(cur)
    start, end = _window(cur, c)
    items = cashback_candidates(cur, c, start, end)
    return {"enabled": c["cashback_enabled"], "mode": c["cashback_mode"], "tiers_enabled": c["cashback_tiers_enabled"], "tiers": c["cashback_tiers"], "period_start": start, "period_end": end,
            "players": len(items), "total": round(sum(i["cashback"] for i in items), 2), "items": items[:200]}


def run_cashback(conn, admin_id=None):
    """Pay every qualifying player once for the window. Caller passes a connection with no open transaction."""
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        c = get_controls(cur)
        if not c["cashback_enabled"]:
            raise ValueError("cashback is disabled")
        start, end = _window(cur, c)
        items = cashback_candidates(cur, c, start, end)
        cur.execute("INSERT INTO cashback_runs(period_start,period_end,mode,admin_id,created_at) VALUES(?,?,?,?,?)",
                    (start, end, c["cashback_mode"], admin_id, _now()))
        run_id, paid, n = cur.lastrowid, 0.0, 0
        locked = 1 if c["cashback_locked"] else 0
        for it in items:
            if _credit(cur, it["user_id"], it["cashback"], locked, end):
                cur.execute("INSERT INTO cashback_grants(run_id,user_id,kind,staked,net_loss,amount,locked,admin_id,created_at) "
                            "VALUES(?,?,'auto',?,?,?,?,?,?)",
                            (run_id, it["user_id"], it["staked"], it["net_loss"], it["cashback"], locked, admin_id, _now()))
                paid += it["cashback"]; n += 1
        cur.execute("UPDATE cashback_runs SET players=?, total_paid=? WHERE id=?", (n, round(paid, 2), run_id))
        conn.commit()
        return {"run_id": run_id, "period_start": start, "period_end": end, "players": n, "total_paid": round(paid, 2)}
    except Exception:
        conn.rollback()
        raise


def grant_cashback(conn, uid, amount, admin_id=None, note="", locked=None):
    """Manual cashback of any amount to one player (admin's free choice)."""
    amount = round(float(amount), 2)
    if not (amount > 0) or amount > 10_000_000:
        raise ValueError("amount must be greater than zero")
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        if locked is None:
            locked = 1 if get_controls(cur)["cashback_locked"] else 0
        if not _credit(cur, int(uid), amount, int(bool(locked)), _now()):
            raise ValueError("user not found")
        cur.execute("INSERT INTO cashback_grants(run_id,user_id,kind,amount,locked,admin_id,note,created_at) "
                    "VALUES(NULL,?,'manual',?,?,?,?,?)", (int(uid), amount, int(bool(locked)), admin_id, str(note)[:200], _now()))
        conn.commit()
        return {"user_id": int(uid), "amount": amount, "locked": bool(locked)}
    except Exception:
        conn.rollback()
        raise
