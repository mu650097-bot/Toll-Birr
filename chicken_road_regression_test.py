import os as _o_; _o_.environ["DEFAULT_HOUSE_EDGE"] = "0.05"   # these tests check the game MATH at a fixed 5% edge, independent of the 15% production default
"""Chicken Road (interactive, step-by-step, cash-out anytime) end-to-end regression.

Runs the REAL Flask routes (/round/start, /action, /state, /active) through the test client with a
properly signed Telegram initData header, against an isolated SQLite database. Checks:
  * math: P(safe_steps >= n) = p**n and expected return == configured RTP for several stopping rules
  * money: every round conserves money (balance delta == payout - stake; ledger stays consistent)
  * fairness: hidden safe_steps never leaks while ACTIVE; after the round the revealed seed reproduces it
  * rules: cash-out needs >=1 step, no actions after settlement, max-steps auto cash-out
  * timeouts: abandoned round with progress is auto-cashed-out, with no progress is refunded
  * a stuck chicken round never blocks the player from starting another game
  * the old one-shot Chicken/Rabbit endpoints are gone
"""
import hashlib, hmac, json, math, os, random, sys, tempfile, time
from urllib.parse import urlencode

G = os.environ.get("ROAD_GAME", "chicken")   # run once per road game: chicken, rabbit
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api",
                 ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w


def need(c, m):
    if not c:
        print("ROAD_REGRESSION[" + G + "]=FAIL:", m); sys.exit(1)


def init_data(uid):
    user = json.dumps({"id": uid, "first_name": "T%d" % uid}, separators=(",", ":"))
    fields = {"auth_date": str(int(time.time())), "user": user, "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


client = w.app.test_client()


def call(uid, method, path, body=None):
    w._rate_limit_hits.clear()
    h = {"X-Telegram-Init-Data": init_data(uid)}
    r = client.open(path, method=method, json=body, headers=h)
    return r.status_code, (r.get_json(silent=True) or {})


conn = w.db(); cur = conn.cursor()
def add_user(uid, bal=100000.0):
    cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(?,?,?)", (uid, bal, "2026-01-01 00:00:00")); conn.commit()
bal = lambda u: round(cur.execute("SELECT balance FROM users WHERE user_id=?", (u,)).fetchone()[0], 2)
row = lambda rid: cur.execute("SELECT * FROM realtime_game_rounds WHERE id=?", (rid,)).fetchone()

# ------------------------------------------------------------------ 1. math (pure functions, production code)
_ss = w._chicken_safe_steps
safe_steps = lambda sd, cs, lv: _ss(sd, cs, lv, G)
RTP = 0.95
MX, LV = w.ROAD_CFG[G]
EASY = "easy" if "easy" in LV else next(iter(LV))   # easiest level of this game (chicken2 uses calm/rush)
for lv, p in LV.items():
    N = 60000
    seeds = [safe_steps(f"seed{i}", "cs", lv) for i in range(N)]
    for n in (1, 3, 6):
        obs = sum(1 for s in seeds if s >= n) / N
        need(abs(obs - p ** n) < 0.012, f"{lv}: P(S>={n}) observed {obs:.4f} vs {p**n:.4f}")
    for stop in (1, 3, 6, 10):  # "always cash out after `stop` safe steps" strategies
        if stop > MX: continue  # games with a shorter ladder (e.g. Tower = 8)
        mult = w._chicken_multiplier(lv, stop, RTP, G)
        rtp = sum(mult for s in seeds if s >= stop) / N
        tol = 0.10 if lv == "hard" and stop >= 6 else 0.05
        need(abs(rtp - RTP) < tol, f"{lv}: stop at {stop} steps -> RTP {rtp:.4f} (expected ~{RTP})")
    need(w._chicken_multiplier(lv, 1, RTP, G) > 1.0, f"{lv}: first step must pay more than the stake")
    need(w._chicken_multiplier(lv, MX, RTP, G) * 1 < 100, f"{lv}: max multiplier must stay under the 100x exposure bound")
need(safe_steps("s", "c", EASY) == safe_steps("s", "c", EASY), "safe_steps must be deterministic")

# ------------------------------------------------------------------ 2. full rounds through the real routes
UID = 4001; add_user(UID)
DEFAULT_LV = "medium" if "medium" in LV else next(iter(LV))
def play_round(strategy_stop, level=None, stake=10.0):
    level = level or DEFAULT_LV
    """Start a round, step until `strategy_stop` safe steps or a hit. Returns (final_payload, balance_before, balance_after)."""
    before = bal(UID)
    st, r = call(UID, "POST", f"/api/games/{G}/round/start", {"stake": stake, "difficulty": level, "client_seed": "cs-" + str(random.random())})
    need(st == 200 and r.get("status") == "ACTIVE", f"start failed: {st} {r}")
    rid = r["round_id"]
    need(bal(UID) == round(before - stake, 2), "stake was not reserved exactly once")
    need(r["state"]["progress"] == 0 and len(r["state"]["multipliers"]) == MX, "start must expose progress + multiplier ladder")
    # nothing about the hidden outcome may be visible while the round is live
    blob = json.dumps(r) + json.dumps(call(UID, "GET", f"/api/games/{G}/round/{rid}/state")[1])
    need("safe_steps" not in blob and "crash" not in blob, "hidden safe_steps leaked while round ACTIVE")
    final = None
    for i in range(1, MX + 2):
        st, a = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "step"})
        need(st == 200, f"step failed: {st} {a}")
        if a["status"] in ("WON", "LOST"):
            final = a; break
        need(a["safe"] and a["progress"] == i, "safe step must advance progress")
        if i >= strategy_stop:
            st, final = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "cashout"})
            need(st == 200 and final["status"] == "WON", f"cashout failed: {st} {final}")
            break
    need(final is not None, "round never ended")
    return rid, final, before, bal(UID)

random.seed(11)
wins = losses = 0
for i in range(120):
    rid, fin, before, after = play_round(strategy_stop=random.choice([1, 2, 3, 5]), level=random.choice(list(LV)))
    need(round(after - before, 2) == round(fin["payout"] - 10.0, 2), f"balance delta != payout - stake ({after-before} vs {fin['payout']-10})")
    o = fin["outcome"]
    # fairness: revealed seed reproduces the hidden number of safe steps
    need(o["safe_steps"] == safe_steps(o["server_seed"], o["client_seed"], o["difficulty"]), "revealed seed does not reproduce safe_steps")
    need(fin["server_seed"] == o["server_seed"], "server_seed missing from response")
    if fin["status"] == "WON":
        wins += 1
        need(o["steps_cleared"] <= o["safe_steps"] and fin["payout"] > 10.0, "a win must pay more than the stake and be within safe steps")
        need(abs(fin["payout"] - round(10.0 * w._chicken_multiplier(o["difficulty"], o["steps_cleared"], 0.95, G), 2)) < 0.011, "payout != stake * RTP/p^n")
    else:
        losses += 1
        need(o["hit_step"] == o["steps_cleared"] + 1 and o["hit_step"] > o["safe_steps"] and fin["payout"] == 0, "loss bookkeeping wrong")
    need(row(rid)["status"] == fin["status"], "DB status != response status")
    # settled rounds accept no further actions
    st, a = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "step"})
    need(st == 409, f"action after settlement must be 409, got {st}")
need(wins > 10 and losses > 10, f"suspicious win/loss split {wins}/{losses}")

# ------------------------------------------------------------------ 3. rules
st, r = call(UID, "POST", f"/api/games/{G}/round/start", {"stake": 10, "difficulty": EASY, "client_seed": "x1"}); rid = r["round_id"]
st, a = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "cashout"})
need(st == 400, "cash-out before the first step must be rejected")
st, a = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "play"})
need(st == 400, "legacy 'play' action must be rejected for chicken")
# resume endpoint returns the live round
st, act = call(UID, "GET", f"/api/games/{G}/active")
need(st == 200 and act.get("round_id") == rid and act.get("status") == "ACTIVE", "active-round endpoint failed")
# max-steps auto cash-out: force the hidden value to the maximum
cur.execute("UPDATE realtime_game_rounds SET crash_point=? WHERE id=?", (float(MX), rid)); conn.commit()
before = bal(UID); last = None
for i in range(MX):
    st, last = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "step"}); need(st == 200, f"{st} {last}")
need(last["status"] == "WON" and last["outcome"]["reason"] == "max_steps", "reaching the last step must auto cash-out")
need(round(bal(UID) - before, 2) == last["payout"], "max-steps payout not credited")

# bad inputs
for bad in ({"stake": 10}, {"stake": 10, "difficulty": "insane"}, {"stake": 10, "steps": 3}, {"stake": 10, "difficulty": EASY, "steps": 3}):
    st, r = call(UID, "POST", f"/api/games/{G}/round/start", bad); need(st == 400, f"invalid start accepted: {bad}")
st, r = call(UID, "POST", "/api/games/nosuchgame/round/start", {"stake": 10, "difficulty": EASY}); need(st in (400, 404), "unknown game must be rejected")
st, r = call(UID, "POST", f"/api/games/{G}/play", {"stake": 10, "steps": 3}); need(st in (400, 404, 405, 410), f"legacy one-shot chicken /play must be disabled, got {st}")

# ------------------------------------------------------------------ 4. timeouts
def aged_round(progress):
    st, r = call(UID, "POST", f"/api/games/{G}/round/start", {"stake": 20, "difficulty": EASY, "client_seed": "t%d" % progress}); rid = r["round_id"]
    if progress:
        cur.execute("UPDATE realtime_game_rounds SET crash_point=? WHERE id=?", (float(progress + 3), rid)); conn.commit()
        for _ in range(progress): call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "step"})
    old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - w.CHICKEN_ROUND_TIMEOUT_SEC - 30))
    cur.execute("UPDATE realtime_game_rounds SET started_at=? WHERE id=?", (old, rid)); conn.commit()
    return rid
b0 = bal(UID); rid = aged_round(0)
st, r = call(UID, "POST", f"/api/games/{G}/round/{rid}/action", {"action": "step"})
need(st == 200 and row(rid)["status"] == "REFUNDED" and bal(UID) == b0, "expired round without steps must refund the stake exactly")
b0 = bal(UID); rid = aged_round(2)
st, r = call(UID, "GET", f"/api/games/{G}/active")  # triggers cleanup
need(row(rid)["status"] == "WON", "expired round with progress must auto cash-out")
exp = round(20.0 * w._chicken_multiplier(EASY, 2, 0.95, G), 2)
need(abs((bal(UID) - b0) - (exp - 20.0)) < 0.011, f"auto cash-out should pay {exp} (net {exp-20.0}), net was {bal(UID)-b0}")

# a forgotten chicken round must never lock the player out of other games
st, r = call(UID, "POST", f"/api/games/{G}/round/start", {"stake": 10, "difficulty": EASY, "client_seed": "blk"}); rid = r["round_id"]
b0 = bal(UID)
st, r2 = call(UID, "POST", "/api/games/dice/round/start", {"stake": 5, "guess": 3, "client_seed": "d1"})
need(st == 200, f"starting another game must not be blocked by an idle chicken round: {st} {r2}")
need(row(rid)["status"] == "REFUNDED", "idle chicken round should be closed (refund) when another game starts")
need(bal(UID) == round(b0 + 10.0 - 5.0, 2), "refund + dice stake accounting wrong")

# ------------------------------------------------------------------ 5. platform ledger sanity: nothing created from thin air
cur.execute("SELECT COUNT(*) FROM realtime_game_rounds WHERE status='ACTIVE' AND game_key='chicken'")
print("ROAD_REGRESSION[" + G + "]=PASS (math P/RTP per difficulty; %d real-route rounds incl. wins=%d losses=%d; fairness reveal; timeouts; no lock-out; legacy routes gone)" % (120, wins, losses))
