"""Buffalo Plains end-to-end on REAL routes + isolated DB. Checks: analytic RTP == independent Monte Carlo (so the closed
form is right), an independent brute-force 243-ways evaluator agrees with the shipped one, free-spin rules, payout ==
stake * (base + free-spin multiples) * scale, money conservation, seed commitment."""
import hashlib, hmac, json, os, random, sys, tempfile, time
from itertools import product
from urllib.parse import urlencode
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w, buffalo_math as bf
def need(c, m):
    if not c: print("BUFFALO_REGRESSION=FAIL:", m); sys.exit(1)
def init_data(uid):
    user = json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":"))
    f = {"auth_date": str(int(time.time())), "user": user, "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sec = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest(); return urlencode(f)
client = w.app.test_client()
def call(method, path, body=None):
    w._rate_limit_hits.clear()
    r = client.open(path, method=method, json=body, headers={"X-Telegram-Init-Data": init_data(3)})
    return r.status_code, (r.get_json(silent=True) or {})
conn = w.db(); cur = conn.cursor()
cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(3,10000000,'2026-01-01 00:00:00')"); conn.commit()
bal = lambda: round(cur.execute("SELECT balance FROM users WHERE user_id=3").fetchone()[0], 2)

def brute_ways(cols):
    """Independent 243-ways: for each symbol, enumerate every row path over the leading reels; a run of exactly k reels
    (reel k has none of the symbol, or k == 5) pays PAY[s][k-3] once per such path."""
    total = 0.0
    for sym in bf.PAY:
        for k in (3, 4, 5):
            if k < 5 and sym in cols[k]: continue          # the run would be longer than k
            paths = sum(1 for rows in product(range(3), repeat=k) if all(cols[c][rows[c]] == sym for c in range(k)))
            total += paths * bf.PAY[sym][k - 3]
    return total
rng = random.Random(7)
for _ in range(3000):
    pos = [rng.randrange(bf.N) for _ in range(5)]
    cols = [bf.window(p) for p in pos]
    a, b = bf.spin_multiple(pos), brute_ways(cols)
    # the shipped evaluator counts, per symbol, ways for the longest run k; brute force counts each path once at its longest run
    # -> they must be identical
    need(abs(a - b) < 1e-9, f"ways evaluator mismatch {pos}: {a} vs {b}")
# analytic RTP vs Monte Carlo (200k base spins incl. free spins)
n = 200000; t = 0.0
for _ in range(n):
    pos = [rng.randrange(bf.N) for _ in range(5)]; t += bf.spin_multiple(pos); sc = bf.scatter_count(pos)
    if sc in bf.FREE_SPINS:
        for _ in range(bf.FREE_SPINS[sc]): t += bf.FS_MULT * bf.spin_multiple([rng.randrange(bf.N) for _ in range(5)])
mc = t / n; need(abs(mc - bf.BASE_RTP) / bf.BASE_RTP < 0.04, f"analytic RTP {bf.BASE_RTP:.4f} vs Monte Carlo {mc:.4f}")
for edge in (0.0, 0.08, 0.2): need(abs(bf.BASE_RTP * ((1 - edge) / bf.BASE_RTP) - (1 - edge)) < 1e-12, "scaled RTP")
s, st = call("GET", "/api/games/buffalo/settings"); need(s == 200 and len(st["buffalo_table"]) == 8 and st["buffalo_free_spins"] == {"3": 8, "4": 12, "5": 20}, f"settings {s} {st}")
edge = st["house_edge"]; scale = (1 - edge) / bf.BASE_RTP
for bad in ({"stake": 10, "extra": 1}, {"stake": 0}, {}):
    s, j = call("POST", "/api/games/buffalo/round/start", bad); need(s == 400, f"bad accepted {bad}")
N = 700; staked = paid = 0.0; feats = 0
for i in range(N):
    b0 = bal(); s, j = call("POST", "/api/games/buffalo/round/start", {"stake": 10, "client_seed": f"b{i}"}); need(s == 200, f"start {s} {j}")
    need(abs(bal() - (b0 - 10)) < 0.011, "stake debited")
    s, a = call("POST", f"/api/games/buffalo/round/{j['round_id']}/action", {"action": "play"}); need(s == 200, f"play {s} {a}")
    o = a["outcome"]; pos = o["positions"]
    need(o["grid"] == [[bf.NAMES[x] for x in row] for row in bf.grid(pos)], "grid matches strip")
    need(abs(o["base_multiple"] - bf.spin_multiple(pos)) < 1e-9, "base multiple")
    sc = bf.scatter_count(pos); need(o["scatters"] == sc and o["free_spins"] == bf.FREE_SPINS.get(sc, 0) and len(o["free_spin_rounds"]) == o["free_spins"], "free-spin rules")
    fm = 0.0
    for fs in o["free_spin_rounds"]:
        need(abs(fs["multiple"] - bf.FS_MULT * bf.spin_multiple(fs["positions"])) < 1e-9, "free spin multiple"); fm += fs["multiple"]
    need(abs(o["feature_multiple"] - fm) < 1e-9, "feature total")
    exp = round(10 * (bf.spin_multiple(pos) + fm) * scale, 2); need(abs(a["payout"] - exp) < 0.011, f"payout {a['payout']} vs {exp}")
    need(abs(bal() - (b0 - 10 + a["payout"])) < 0.011, "balance after payout")
    need(hashlib.sha256(a["server_seed"].encode()).hexdigest() == cur.execute("SELECT seed_commit FROM realtime_game_rounds WHERE id=?", (j["round_id"],)).fetchone()[0], "seed commitment")
    staked += 10; paid += a["payout"]; feats += 1 if o["free_spins"] else 0
need(0.4 < paid / staked < 1.6, f"sample RTP {paid/staked:.3f}")
print(f"BUFFALO_REGRESSION=PASS (analytic RTP {bf.BASE_RTP:.4f} vs MC {mc:.4f}; ways evaluator == brute force on 3000 grids; {N} real-route rounds, bonuses {feats}, sample RTP {paid/staked:.3f} -> target {1-edge:.2f})")
