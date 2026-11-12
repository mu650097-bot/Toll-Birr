"""Aztec Gold end-to-end on REAL routes + isolated DB: exact RTP maths, 5-line evaluation matches the shown grid,
payout == stake * sum(line pays)/5 * scale, money conservation, seed commitment, plausible sample."""
import hashlib, hmac, json, os, sys, tempfile, time
from urllib.parse import urlencode
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w, aztec_math as az
def need(c, m):
    if not c: print("AZTEC_REGRESSION=FAIL:", m); sys.exit(1)
def init_data(uid):
    user = json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":"))
    f = {"auth_date": str(int(time.time())), "user": user, "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sec = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest(); return urlencode(f)
client = w.app.test_client()
def call(method, path, body=None):
    w._rate_limit_hits.clear()
    r = client.open(path, method=method, json=body, headers={"X-Telegram-Init-Data": init_data(5)})
    return r.status_code, (r.get_json(silent=True) or {})
conn = w.db(); cur = conn.cursor()
cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(5,1000000,'2026-01-01 00:00:00')"); conn.commit()
bal = lambda: round(cur.execute("SELECT balance FROM users WHERE user_id=5").fetchone()[0], 2)
for edge in (0.0, 0.05, 0.08, 0.2):
    need(abs(az.BASE_RTP * (1 - edge) / az.BASE_RTP - (1 - edge)) < 1e-12, "scaled RTP")
need(0.30 < az.hit_frequency() < 0.5, "hit frequency")
s, st = call("GET", "/api/games/aztec/settings"); need(s == 200 and len(st["aztec_table"]) == 5 and len(st["aztec_lines"]) == 5, f"settings {s} {st}")
edge = st["house_edge"]; scale = (1 - edge) / az.BASE_RTP
for bad in ({"stake": 10, "extra": 1}, {"stake": 0}, {}):
    s, j = call("POST", "/api/games/aztec/round/start", bad); need(s == 400, f"bad accepted {bad}")
N = 600; staked = paid = 0.0; multi = 0
for i in range(N):
    b0 = bal(); s, j = call("POST", "/api/games/aztec/round/start", {"stake": 10, "client_seed": f"a{i}"}); need(s == 200, f"start {s} {j}")
    need(abs(bal() - (b0 - 10)) < 0.011, "stake debited")
    s, a = call("POST", f"/api/games/aztec/round/{j['round_id']}/action", {"action": "play"}); need(s == 200, f"play {s} {a}")
    o = a["outcome"]; pos = o["positions"]; g = az.grid(pos)
    need(o["grid"] == [[az.NAMES[x] for x in row] for row in g], "grid matches strip")
    wl = az.line_wins(pos); need([x["line"] for x in o["wins"]] == [x[0] for x in wl] and o["win_lines"] == [x[0] for x in wl], "winning lines match")
    for x in o["wins"]:
        L = az.LINES[x["line"]]; sy = {g[L[k]][k] for k in range(3)}; need(len(sy) == 1 and az.NAMES[next(iter(sy))] == x["symbol"], "line symbols")
    exp = round(10 * az.total_multiplier(pos) * scale, 2); need(abs(a["payout"] - exp) < 0.011, f"payout {a['payout']} vs {exp}")
    need(abs(bal() - (b0 - 10 + a["payout"])) < 0.011, "balance after payout")
    need(hashlib.sha256(a["server_seed"].encode()).hexdigest() == cur.execute("SELECT seed_commit FROM realtime_game_rounds WHERE id=?", (j["round_id"],)).fetchone()[0], "seed commitment")
    staked += 10; paid += a["payout"]; multi += 1 if len(wl) > 1 else 0
need(0.5 < paid / staked < 1.4, f"sample RTP {paid/staked:.3f}")
print(f"AZTEC_REGRESSION=PASS (exact nominal RTP {az.BASE_RTP:.4f} -> {1-edge:.2f}; {N} real-route rounds, sample RTP {paid/staked:.3f}, multi-line wins {multi})")
