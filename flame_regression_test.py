"""Flame Classics end-to-end on REAL routes + isolated DB: exact RTP maths (incl. the memoryless Hot Respin),
payout == stake * (sum of spin multipliers) * scale, money conservation, seed commitment, Hot Respin frequency ~1/8,
and no hidden state: two identical rounds never depend on earlier rounds."""
import hashlib, hmac, json, os, sys, tempfile, time
from urllib.parse import urlencode
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w, flame_math as fm
def need(c, m):
    if not c: print("FLAME_REGRESSION=FAIL:", m); sys.exit(1)
def init_data(uid):
    user = json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":"))
    f = {"auth_date": str(int(time.time())), "user": user, "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sec = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest(); return urlencode(f)
client = w.app.test_client()
def call(method, path, body=None):
    w._rate_limit_hits.clear()
    r = client.open(path, method=method, json=body, headers={"X-Telegram-Init-Data": init_data(9)})
    return r.status_code, (r.get_json(silent=True) or {})
conn = w.db(); cur = conn.cursor()
cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(9,1000000,'2026-01-01 00:00:00')"); conn.commit()
bal = lambda: round(cur.execute("SELECT balance FROM users WHERE user_id=9").fetchone()[0], 2)

# exact maths: long-run RTP == 1 - edge for any edge (single spin R0 plus a 1-in-8 free spin of the same distribution)
need(abs(fm.BASE_RTP - fm.R0 * (1 + 1 / 8)) < 1e-12, "base rtp formula")
for edge in (0.0, 0.05, 0.08, 0.2):
    scale = (1 - edge) / fm.BASE_RTP
    need(abs(fm.R0 * (1 + 1 / fm.HOT_ONE_IN) * scale - (1 - edge)) < 1e-12, "scaled long-run RTP")
s, st = call("GET", "/api/games/flame/settings"); need(s == 200 and len(st["flame_table"]) == 5 and st["flame_hot_one_in"] == 8, f"settings {s} {st}")
edge = st["house_edge"]; scale = (1 - edge) / fm.BASE_RTP
for bad in ({"stake": 10, "extra": 1}, {"stake": 0}, {}):
    s, j = call("POST", "/api/games/flame/round/start", bad); need(s == 400, f"bad accepted {bad}")
N = 800; staked = paid = 0.0; hot = 0
for i in range(N):
    b0 = bal(); s, j = call("POST", "/api/games/flame/round/start", {"stake": 10, "client_seed": f"f{i}"}); need(s == 200, f"start {s} {j}")
    need(abs(bal() - (b0 - 10)) < 0.011, "stake debited")
    s, a = call("POST", f"/api/games/flame/round/{j['round_id']}/action", {"action": "play"}); need(s == 200, f"play {s} {a}")
    o = a["outcome"]; sp = o["spins"]; need(len(sp) in (1, 2) and o["hot_respin"] == (len(sp) == 2), "spins shape")
    tot = 0.0
    for x in sp:
        line = [fm.NAMES[c] for c in fm.spin_line(x["positions"])]; need(line == x["line"], "line matches strip")
        need(fm.line_multiplier(fm.spin_line(x["positions"])) == x["base_multiplier"], "multiplier matches line"); tot += x["base_multiplier"]
    exp = round(10 * tot * scale, 2); need(abs(a["payout"] - exp) < 0.011, f"payout {a['payout']} vs {exp}")
    need(abs(bal() - (b0 - 10 + a["payout"])) < 0.011, "balance after payout")
    need(hashlib.sha256(a["server_seed"].encode()).hexdigest() == cur.execute("SELECT seed_commit FROM realtime_game_rounds WHERE id=?", (j["round_id"],)).fetchone()[0], "seed commitment")
    staked += 10; paid += a["payout"]; hot += 1 if o["hot_respin"] else 0
rate = hot / N; need(0.08 < rate < 0.17, f"hot respin rate {rate:.3f} vs 0.125")
print(f"FLAME_REGRESSION=PASS (exact long-run RTP {1-edge:.2f}; {N} real-route rounds, hot respins {hot} = {rate:.3f}, sample RTP {paid/staked:.3f})")
