"""Triple Gold end-to-end on the REAL routes + isolated DB: exact RTP of the pay table, scaled RTP == 1-edge,
shown grid is consistent with the strip, payout == stake * effective multiplier, money conservation, and a
statistical check over many real-route rounds."""
import hashlib, hmac, json, os, random, sys, tempfile, time
from urllib.parse import urlencode
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w, triplegold_math as tg
def need(c, m):
    if not c: print("TRIPLEGOLD_REGRESSION=FAIL:", m); sys.exit(1)
def init_data(uid):
    user = json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":"))
    f = {"auth_date": str(int(time.time())), "user": user, "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sec = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest(); return urlencode(f)
client = w.app.test_client()
def call(method, path, body=None):
    w._rate_limit_hits.clear()
    r = client.open(path, method=method, json=body, headers={"X-Telegram-Init-Data": init_data(7)})
    return r.status_code, (r.get_json(silent=True) or {})
conn = w.db(); cur = conn.cursor()
cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(7,1000000,'2026-01-01 00:00:00')"); conn.commit()
bal = lambda: round(cur.execute("SELECT balance FROM users WHERE user_id=7").fetchone()[0], 2)

# exact math
need(abs(tg.base_rtp() - 1.0) < 1e-12, "nominal RTP must be exactly 1.0")
for edge in (0.0, 0.05, 0.08, 0.2):
    scale = (1 - edge) / tg.BASE_RTP
    need(abs(tg.base_rtp() * scale - (1 - edge)) < 1e-12, "scaled RTP")
s, st = call("GET", "/api/games/triplegold/settings"); need(s == 200 and len(st["triplegold_table"]) == 5 and len(st["triplegold_strip"]) == 20, f"settings {s} {st}")
eff = {(r["symbol"], r["kind"]): r["multiplier"] for r in st["triplegold_table"]}
edge = st["house_edge"]; need(abs(eff[("seven", "three")] - round(80 * (1 - edge), 2)) < 1e-9, "effective table")
# bad input
for bad in ({"stake": 10, "extra": 1}, {"stake": 0}, {}):
    s, j = call("POST", "/api/games/triplegold/round/start", bad); need(s == 400, f"bad accepted {bad}")
# real rounds
N = 600; staked = paid = wins = 0.0; seen = set()
for i in range(N):
    b0 = bal()
    s, j = call("POST", "/api/games/triplegold/round/start", {"stake": 10, "client_seed": f"s{i}"}); need(s == 200, f"start {s} {j}")
    need(abs(bal() - (b0 - 10)) < 0.011, "stake debited")
    s, a = call("POST", f"/api/games/triplegold/round/{j['round_id']}/action", {"action": "play"}); need(s == 200, f"play {s} {a}")
    o = a["outcome"]; pos = o["positions"]; g = tg.grid(pos)
    need(o["grid"] == [[tg.NAMES[x] for x in row] for row in g] and o["line"] == o["grid"][1], "grid matches strip")
    need(tg.multiplier(pos) == o["base_multiplier"], "nominal multiplier matches line")
    need(abs(o["multiplier"] - (round(a["payout"] / 10, 4))) < 1e-9, "outcome multiplier is the effective one")
    exp = round(10 * o["base_multiplier"] * (1 - edge), 2) if o["base_multiplier"] > 0 else 0.0
    need(abs(a["payout"] - exp) < 0.011, f"payout {a['payout']} vs {exp} for {o['line']}")
    need(abs(bal() - (b0 - 10 + a["payout"])) < 0.011, "balance after payout")
    need("server_seed" in a and hashlib.sha256(a["server_seed"].encode()).hexdigest() == cur.execute("SELECT seed_commit FROM realtime_game_rounds WHERE id=?", (j["round_id"],)).fetchone()[0], "seed commitment")
    staked += 10; paid += a["payout"]; wins += 1 if a["payout"] > 0 else 0; seen.add(tuple(o["line"]))
rtp = paid / staked; hit = wins / N
need(0.55 < rtp < 1.35, f"sample RTP {rtp:.3f} implausible")   # 600 rounds is a sanity check; the exact RTP is proven above
need(0.30 < hit < 0.47, f"hit rate {hit:.3f} vs exact 0.388")
print(f"TRIPLEGOLD_REGRESSION=PASS (exact RTP 1.0 -> {1-edge:.2f} after edge; {int(N)} real-route rounds, sample RTP {rtp:.3f}, hit {hit:.3f})")
