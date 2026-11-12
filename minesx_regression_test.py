"""Mines (step by step) end-to-end regression on the REAL routes + isolated SQLite DB.
Checks: exact expected return == RTP for several stopping rules, money conservation, layout never leaks while ACTIVE,
revealed seed reproduces the layout, rules (cash-out needs a gem, duplicate/invalid tile, no action after settle),
clearing the board auto-pays, abandoned rounds (progress -> auto cash-out, none -> refund), stuck round never blocks."""
import hashlib, hmac, json, math, os, sys, tempfile, time
from urllib.parse import urlencode
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w
_c=w.db(); _c.execute("UPDATE platform_settings SET value='0' WHERE key='welcome_bonus_enabled'"); _c.commit(); _c.close()   # these tests assume brand-new users start at exactly 0
def need(c, m):
    if not c:
        import traceback; traceback.print_stack(limit=3); print("MINESX_REGRESSION=FAIL:", m); sys.exit(1)
def init_data(uid):
    user = json.dumps({"id": uid, "first_name": "T%d" % uid}, separators=(",", ":"))
    f = {"auth_date": str(int(time.time())), "user": user, "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sec = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest(); return urlencode(f)
client = w.app.test_client()
def call(uid, method, path, body=None):
    w._rate_limit_hits.clear()
    r = client.open(path, method=method, json=body, headers={"X-Telegram-Init-Data": init_data(uid)})
    return r.status_code, (r.get_json(silent=True) or {})
conn = w.db(); cur = conn.cursor()
def add_user(uid, bal=100000.0):
    cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(?,?,?)", (uid, bal, "2026-01-01 00:00:00")); conn.commit()
bal = lambda u: round(cur.execute("SELECT balance FROM users WHERE user_id=?", (u,)).fetchone()[0], 2)
row = lambda rid: cur.execute("SELECT * FROM realtime_game_rounds WHERE id=?", (rid,)).fetchone()
G = "minesx"; A = "/api/games/minesx/round/"

# 1. exact math: E[return] with a "stop after k gems" rule == RTP for every mines option
for m in w.MINESX_OPTIONS:
    for k in (1, 2, 4):
        if k > 25 - m: continue
        p_survive = math.comb(25 - m, k) / math.comb(25, k)
        ev = p_survive * w._minesx_multiplier(m, k, 0.95)
        need(abs(ev - 0.95) < 1e-9, f"EV m={m} k={k} = {ev}")
need(len(set(w._minesx_layout("s", "c", 3))) == 3, "layout has 3 distinct mines")
need(w._minesx_layout("s", "c", 5) == w._minesx_layout("s", "c", 5), "layout deterministic")

# 2. validation
add_user(10)
for bad in ({"stake": 10, "mines": 2}, {"stake": 10}, {"stake": 10, "mines": True}, {"stake": 10, "mines": 3, "pick": 4}, {"stake": 0, "mines": 3}):
    s, j = call(10, "POST", A + "start", bad); need(s == 400, f"bad start accepted {bad} {s} {j}")
need(bal(10) == 100000.0, "no stake taken on invalid start")

def start(uid, mines=3, stake=50, seed=None):
    b = {"stake": stake, "mines": mines}
    if seed is not None: b["client_seed"] = seed
    s, j = call(uid, "POST", A + "start", b); need(s == 200, f"start {s} {j}"); return j
# 3. full flow: open gems until a mine, money conservation + no layout leak
add_user(11); b0 = bal(11); j = start(11, 3, 50, "abc"); rid = j["round_id"]
need(bal(11) == b0 - 50, "stake debited"); need("mine_positions" not in json.dumps(j), "layout leaked at start")
need(j["state"]["mines"] == 3 and j["state"]["progress"] == 0 and len(j["state"]["multipliers"]) == 22, "initial state")
s, j2 = call(11, "POST", A + f"{rid}/action", {"action": "cashout"}); need(s == 400, "cashout before any gem must fail")
s, j2 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": 0}); need(s == 400, "tile 0 invalid")
s, j2 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": "3"}); need(s == 400, "string tile invalid")
layout = w._minesx_layout(row(rid)["server_seed"], "abc", 3)
safe = [t for t in range(1, 26) if t not in layout]
s, j2 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": safe[0]}); need(s == 200 and j2["safe"] and j2["progress"] == 1, f"safe pick {j2}")
need("mine_positions" not in json.dumps(j2), "layout leaked on pick")
s, st = call(11, "GET", f"/api/games/minesx/round/{rid}/state"); need(s == 200 and "mine_positions" not in json.dumps(st) and st["state"]["revealed"] == [safe[0]], f"state leak/shape {st}")
s, j3 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": safe[0]}); need(s == 400, "duplicate tile must fail")
s, j2 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": safe[1]}); need(j2["progress"] == 2, "second gem")
exp = round(50 * w._minesx_multiplier(3, 2, 0.95), 2); need(abs(j2["potential_payout"] - exp) < 0.011, "potential payout")
s, j4 = call(11, "POST", A + f"{rid}/action", {"action": "cashout"}); need(s == 200 and j4["won"] and abs(j4["payout"] - exp) < 0.011, f"cashout {j4}")
need(abs(bal(11) - (b0 - 50 + j4["payout"])) < 0.011, "balance after cashout")
need(j4["outcome"]["mine_positions"] == layout, "revealed layout matches recomputed one")
need(hashlib.sha256(j4["server_seed"].encode()).hexdigest() == row(rid)["seed_commit"], "seed commitment")
s, j5 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": safe[2]}); need(s == 409 or s == 400, "no action after settlement")
# 4. hitting a mine loses the stake and reveals layout
b0 = bal(11); j = start(11, 5, 20, "x"); rid = j["round_id"]; lay = w._minesx_layout(row(rid)["server_seed"], "x", 5)
s, j2 = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": lay[0]}); need(s == 200 and not j2["won"] and j2["status"] == "LOST", "mine hit")
need(j2["outcome"]["mine_positions"] == lay and j2["outcome"]["hit_tile"] == lay[0], "mine reveal"); need(bal(11) == b0 - 20, "stake lost")
# 5. clearing the whole board auto-pays the max multiplier
b0 = bal(11); j = start(11, 10, 10, "z"); rid = j["round_id"]; lay = w._minesx_layout(row(rid)["server_seed"], "z", 10)
last = None
for t in [t for t in range(1, 26) if t not in lay]:
    s, last = call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": t}); need(s == 200, f"clear pick {last}")
need(last["won"] and last["status"] == "WON" and last["progress"] == 15, f"board cleared {last}")
need(abs(last["payout"] - round(min(w.MAX_ROUND_PAYOUT_ETB, 10 * w._minesx_multiplier(10, 15, 0.95)), 2)) < 0.011, "cleared payout")
# 6. timeouts: progress -> auto cash-out; none -> refund; a stuck round never blocks another game
w.CHICKEN_ROUND_TIMEOUT_SEC = 1
b0 = bal(11); j = start(11, 3, 40, "t"); rid = j["round_id"]; lay = w._minesx_layout(row(rid)["server_seed"], "t", 3)
call(11, "POST", A + f"{rid}/action", {"action": "pick", "tile": [t for t in range(1, 26) if t not in lay][0]})
cur.execute("UPDATE realtime_game_rounds SET started_at='2000-01-01 00:00:00' WHERE id=?", (rid,)); conn.commit()
s, jj = call(11, "POST", "/api/games/dice2/round/start", {"stake": 10, "mode": "over", "target": 7}); need(s == 200, f"stuck round blocked other game {s} {jj}")
call(11, "POST", f"/api/games/dice2/round/{jj['round_id']}/action", {"action": "play"})
need(row(rid)["status"] == "WON", "idle round with a gem is auto cashed out")
b1 = bal(11); j = start(11, 3, 30, "u"); rid2 = j["round_id"]
cur.execute("UPDATE realtime_game_rounds SET started_at='2000-01-01 00:00:00' WHERE id=?", (rid2,)); conn.commit()
w._cleanup_expired_realtime_rounds(); conn.commit()
need(row(rid2)["status"] == "REFUNDED", "no-progress round refunded")
# 7. ledger: the refund restored the stake exactly
need(abs(bal(11) - b1) < 0.011, "refund restored the stake exactly")
print("MINESX_REGRESSION=PASS")
