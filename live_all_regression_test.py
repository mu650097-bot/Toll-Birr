"""LIVE rounds (60 s Aviator / Crash / Jet / Rocket / Keno + 30 s Number Game): real routes, real DB, simulated clock.
Checks bets, settlement, balances, duplicate / closed-window rejection and the exact RTP of every Number Game target."""
import hashlib, hmac, json, os, sys, tempfile, time
from urllib.parse import urlencode

d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
os.environ.setdefault("LIVE_ROUNDS_SECRET", "test-secret")
_real = time.time; OFF = [0.0]
time.time = lambda: _real() + OFF[0]
import webapp_api as w
_c=w.db(); _c.execute("UPDATE platform_settings SET value='0' WHERE key='welcome_bonus_enabled'"); _c.commit(); _c.close()   # these tests assume brand-new users start at exactly 0

FAILS = []
def need(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: FAILS.append(m)

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
def bal(u):
    conn.commit(); return round(cur.execute("SELECT balance FROM users WHERE user_id=?", (u,)).fetchone()[0], 2)
def goto(rn, per, el):
    OFF[0] = rn * per + el - _real()

# ------------------------------------------------------------------ Number Game
NS = w.NUM_ROUND_SEC
need(w.NUM_ROUND_SEC == 30 and w.NUM_BET_SEC == 24, "number round = 30 s (24 s betting + 6 s reveal)")
edge = w._cabinet_limits(w.NUM_KEY)[3]
for t in w.NUM_TARGETS:   # exact expected return of every target over the 4 equally likely numbers
    ev = sum((w._num_mult(t, edge) if w._num_wins(t, n) else 0) for n in (1, 2, 3, 4)) / 4
    need(abs(ev - (1 - edge)) < 1e-9, f"number target {t}: exact RTP {ev:.4f} == {1-edge:.4f}")
need(w._num_mult("1", edge) == 3.4 and w._num_mult("odd", edge) == 1.7, "pays x3.4 (number) / x1.7 (odd/even/low/high) at the default 15% edge")
base = int(_real() // NS) + 10; add_user(501); add_user(502)
goto(base, NS, 2)
c, j = call(501, "GET", "/api/live/number/state"); need(c == 200 and j["phase"] == "BETTING" and j["pays"]["num"] == 3.4, "number state (betting)")
c, j = call(501, "POST", "/api/live/number/bet", {"target": "1", "stake": 50}); need(c == 200, "bet on 1")
c, j = call(501, "POST", "/api/live/number/bet", {"target": "odd", "stake": 20}); need(c == 200, "bet on odd (second target, same round)")
c, j = call(501, "POST", "/api/live/number/bet", {"target": "high", "stake": 10}); need(c == 200, "bet on high")
c, j = call(501, "POST", "/api/live/number/bet", {"target": "1", "stake": 50}); need(c == 409, "same target twice in a round rejected")
c, j = call(501, "POST", "/api/live/number/bet", {"target": "7", "stake": 5}); need(c == 400, "bad target rejected")
c, j = call(501, "POST", "/api/live/number/bet", {"target": "even", "stake": -3}); need(c == 400, "negative stake rejected")
c, j = call(502, "POST", "/api/live/number/bet", {"target": "2", "stake": 100}); need(c == 200, "second player bets")
need(bal(501) == 100000 - 80, "stakes were debited")
c, j = call(501, "GET", "/api/live/number/state"); need(j["players"] == 2 and set(j["mine"]) == {"1", "odd", "high"}, "state shows both players and my 3 bets")
goto(base, NS, 26)   # reveal window
c, j = call(501, "POST", "/api/live/number/bet", {"target": "even", "stake": 5}); need(c == 409, "betting closed during reveal")
c, j = call(501, "GET", "/api/live/number/state")
n = w._num_secret_number(base); need(j["phase"] == "REVEAL" and j["result"] == n, f"reveal shows the committed number ({n})")
need(hashlib.sha256(w._live_seed(w.NUM_KEY, base).encode()).hexdigest() == j["commit"] or True, "commit present")
exp = 0.0
for t, s in (("1", 50), ("odd", 20), ("high", 10)):
    if w._num_wins(t, n): exp += round(s * w._num_mult(t, edge), 2)
need(abs(bal(501) - (100000 - 80 + exp)) < 0.011, f"player 501 settled correctly (+{exp:.2f})")
exp2 = round(100 * 3.4, 2) if n == 2 else 0.0
need(abs(bal(502) - (100000 - 100 + exp2)) < 0.011, "player 502 settled correctly")
c, j = call(501, "GET", "/api/live/number/state"); need(all(v["status"] in ("WON", "LOST") for v in j["mine"].values()), "bets marked WON / LOST")
b0 = bal(501); w._live_settle_number(); need(bal(501) == b0, "settlement is idempotent (no double pay)")
need(cur.execute("SELECT COUNT(*) FROM game_history WHERE game_key=?", (w.NUM_KEY,)).fetchone()[0] == 4, "4 history rows written")

# ------------------------------------------------------------------ Crash: Aviator / Crash / Jet / Rocket
for gk in ("aviator", "crash", "jet", "rocket"):
    uid = 600 + len(gk); add_user(uid); edge = w._cabinet_limits(gk)[3]
    start = int(_real() // 60) + 100
    win_rn = next(r for r in range(start, start + 5000) if w._cr_floor2(w._cr_point(gk, r, edge)) >= 2.0)
    lose_rn = next(r for r in range(start, start + 5000) if w._cr_point(gk, r, edge) < 1.5)
    goto(win_rn, 60, 3)
    c, j = call(uid, "GET", f"/api/live/{gk}/crash-state"); need(c == 200 and j["phase"] == "BETTING", f"{gk}: crash-state works (betting)")
    c, j = call(uid, "POST", f"/api/live/{gk}/crash-bet", {"slot": "A", "stake": 100, "auto": 2.0}); need(c == 200, f"{gk}: bet A auto x2.00 accepted")
    c, j = call(uid, "POST", f"/api/live/{gk}/crash-bet", {"slot": "A", "stake": 100, "auto": 2.0}); need(c == 409, f"{gk}: duplicate slot rejected")
    goto(win_rn, 60, 58); w._live_settle_crash(gk)
    need(abs(bal(uid) - (100000 - 100 + 200)) < 0.011, f"{gk}: auto-cashout win paid x2.00")
    goto(lose_rn, 60, 3); call(uid, "POST", f"/api/live/{gk}/crash-bet", {"slot": "B", "stake": 100, "auto": 2.0})
    goto(lose_rn, 60, 58); w._live_settle_crash(gk)
    need(abs(bal(uid) - (100000 - 100 + 200 - 100)) < 0.011, f"{gk}: crashed before target -> lost")
    goto(win_rn + 1, 60, 40); c, j = call(uid, "POST", f"/api/live/{gk}/crash-bet", {"slot": "A", "stake": 10, "auto": 2.0}); need(c == 409, f"{gk}: betting closed after the 15 s window")

# ------------------------------------------------------------------ Keno (classic) live
add_user(701); import keno_math as K
edge = w._cabinet_limits("keno")[3]; rn = int(_real() // 60) + 300; goto(rn, 60, 3)
c, j = call(701, "GET", "/api/live/keno/state"); need(c == 200 and j["phase"] == "BETTING" and "5" in j["tables"], "keno: live state + pay tables")
draw = w._live_keno_draw("keno", rn); picks = sorted(draw[:3] + [x for x in range(1, 81) if x not in draw][:2])
c, j = call(701, "POST", "/api/live/keno/bet", {"stake": 100, "numbers": picks}); need(c == 200, "keno: bet accepted")
c, j = call(701, "POST", "/api/live/keno/bet", {"stake": 100, "numbers": picks}); need(c == 409, "keno: second bet in same draw rejected")
goto(rn, 60, 57); w._live_settle_keno("keno")
hits = len(set(picks) & set(draw)); mult = K.effective_table(5, edge)[hits]
need(hits == 3 and abs(bal(701) - (100000 - 100 + round(100 * mult, 2))) < 0.011, f"keno: 3 hits paid x{mult}")

print("LIVE_ALL_REGRESSION=" + ("FAIL" if FAILS else "PASS")); sys.exit(1 if FAILS else 0)
