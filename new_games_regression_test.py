import os as _o_; _o_.environ["DEFAULT_HOUSE_EDGE"] = "0.05"   # these tests check the game MATH at a fixed 5% edge, independent of the 15% production default
"""Roulette, Bingo and Fast Keno regression: exact math + the real /round/start -> /action routes.

  * math: every roulette bet has RTP 36/38; Fast Keno / Bingo tables match their closed-form distributions
  * routes: input validation, money conservation (balance delta == payout - stake), server-side outcomes
  * statistics: sampled RTP through the production routes is within tolerance of the configured target
"""
import hashlib, hmac, json, os, random, sys, tempfile, time
from math import comb
from urllib.parse import urlencode

d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api",
                 ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w
import new_games_math as m


def need(c, msg):
    if not c:
        print("NEW_GAMES_REGRESSION=FAIL:", msg); sys.exit(1)


# ------------------------------------------------------------------ 1. exact math
for bet, vals in (("number", [0, 7, 37]), ("red", [None]), ("black", [None]), ("odd", [None]), ("even", [None]),
                  ("low", [None]), ("high", [None]), ("dozen", [1, 2, 3]), ("column", [1, 2, 3])):
    for v in vals:
        rtp = sum(m.roulette_multiplier(s, bet, v) for s in range(m.ROULETTE_POCKETS)) / m.ROULETTE_POCKETS
        need(abs(rtp - 36 / 38) < 1e-12, f"roulette {bet}/{v} RTP {rtp}")
need(abs(sum(m.BINGO_LINE_DIST) - 1) < 1e-9, "bingo line distribution must sum to 1")
# Bingo: Monte-Carlo the line-count distribution against the exact enumerated table (common outcomes)
rng = random.Random(2026); N = 120000; cnt = [0] * 13
for _ in range(N):
    card = m.bingo_make_card(rng); n, _, _ = m.bingo_score(card, rng.sample(range(1, 76), m.BINGO_DRAWS)); cnt[n] += 1
for j in range(4):
    need(abs(cnt[j] / N - m.BINGO_LINE_DIST[j]) < 0.006, f"bingo P(lines={j}) observed {cnt[j]/N:.4f} vs exact {m.BINGO_LINE_DIST[j]:.4f}")
card = m.bingo_make_card(random.Random(1))
need(card[12] == 0 and len(set(card) - {0}) == 24 and all(15 * (i % 5) < n <= 15 * (i % 5) + 15 for i, n in enumerate(card) if n), "bingo card layout invalid")
need(abs(m.FASTKENO_BASE_RTP - sum(comb(4, h) * comb(36, 10 - h) / comb(40, 10) * x for h, x in m.FASTKENO_PAYTABLE.items())) < 1e-12, "fast keno rtp")
import roast_math, slot_math
need(0.94 <= roast_math.BASE_RTP <= 0.96, f"chicken roast base RTP {roast_math.BASE_RTP:.4f}")
need(0.90 <= slot_math.BASE_RTP <= 0.97, f"slot base RTP {slot_math.BASE_RTP:.4f}")
for k in range(1, 9):
    need(0.945 <= m.FASTKENO_RTP_BY_PICKS[k] <= 0.95 + 1e-9, f"fast keno {k}-pick table RTP {m.FASTKENO_RTP_BY_PICKS[k]:.4f} must be 94.5-95.0%")
    need(max(m.FASTKENO_PAYTABLES[k].values()) <= 1000, "fast keno top prize cap")
for name, r in (("roulette", m.ROULETTE_BASE_RTP), ("fastkeno", m.FASTKENO_BASE_RTP), ("bingo", m.BINGO_BASE_RTP)):
    need(0.93 <= r <= 0.97, f"{name} base RTP {r} should be near the 95% platform target")


# ------------------------------------------------------------------ 2. real routes
def init_data(uid):
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":")), "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)

client = w.app.test_client()
def call(uid, method, path, body=None):
    w._rate_limit_hits.clear()
    r = client.open(path, method=method, json=body, headers={"X-Telegram-Init-Data": init_data(uid)})
    return r.status_code, (r.get_json(silent=True) or {})

conn = w.db(); cur = conn.cursor(); UID = 5001
cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(?,?,?)", (UID, 10_000_000.0, "2026-01-01 00:00:00")); conn.commit()
bal = lambda: round(cur.execute("SELECT balance FROM users WHERE user_id=?", (UID,)).fetchone()[0], 2)

def play(key, body):
    b0 = bal()
    st, r = call(UID, "POST", f"/api/games/{key}/round/start", dict(body, client_seed="s%d" % random.getrandbits(32)))
    if st != 200: return st, r, None
    st2, a = call(UID, "POST", f"/api/games/{key}/round/{r['round_id']}/action", {"action": "play"})
    need(st2 == 200, f"{key} action failed {st2} {a}")
    need(round(bal() - b0, 2) == round(a["payout"] - body["stake"], 2), f"{key}: balance delta != payout - stake")
    o = a.get("outcome") or {}
    exp = round(body["stake"] * float(o.get("base_multiplier", 0)) * float(o.get("payout_scale", 1)), 2) if a["payout"] > 0 else 0.0
    need(abs(a["payout"] - exp) < 0.011, f"{key}: payout {a['payout']} != stake * table multiplier * disclosed scale {exp}")
    if a["payout"] > 0: need(0.99 < float(o.get("payout_scale", 1)) < 1.01, f"{key}: disclosed payout scale should be ~1 for a correctly tuned table, got {o.get('payout_scale')}")
    return st, r, a

# validation
bad = [("roulette", {"stake": 10}), ("roulette", {"stake": 10, "bet": "number"}), ("roulette", {"stake": 10, "bet": "number", "value": 38}),
       ("roulette", {"stake": 10, "bet": "red", "value": 3}), ("roulette", {"stake": 10, "bet": "dozen", "value": 4}), ("roulette", {"stake": 10, "bet": "split", "value": 1}),
       ("fastkeno", {"stake": 10, "numbers": []}), ("fastkeno", {"stake": 10, "numbers": [1, 2, 3, 4, 5, 6, 7, 8, 9]}), ("fastkeno", {"stake": 10, "numbers": [1, 1, 2, 3]}), ("fastkeno", {"stake": 10, "numbers": [1, 2, 3, 41]}),
       ("bingo", {"stake": 10, "cards": 5}), ("bingo", {"stake": -5})]
for key, body in bad:
    st, r, _ = play(key, body); need(st == 400, f"invalid {key} input accepted: {body} -> {st}")

# roulette outcome shape
st, r, a = play("roulette", {"stake": 10, "bet": "number", "value": 17})
o = a["outcome"]; need(0 <= o["spin"] <= 37 and o["label"] == m.roulette_label(o["spin"]) and o["color"] == m.roulette_color(o["spin"]), "roulette outcome shape")
need(("server_seed" in o) and o["server_authoritative"], "roulette must reveal the seed and be server authoritative")

# statistical RTP through the production routes (mixed bets so one lucky straight-up does not dominate)
def sample(key, bodies, n):
    stake_total = pay_total = 0.0
    for i in range(n):
        body = random.choice(bodies); st, r, a = play(key, body); need(st == 200, f"{key} start failed {st} {r}")
        stake_total += body["stake"]; pay_total += a["payout"]
    return pay_total / stake_total
random.seed(99)
rb = [{"stake": 10, "bet": b} for b in ("red", "black", "odd", "even", "low", "high")] + [{"stake": 10, "bet": "dozen", "value": v} for v in (1, 2, 3)] \
     + [{"stake": 10, "bet": "column", "value": v} for v in (1, 2, 3)]
r1 = sample("roulette", rb, 2500); need(abs(r1 - 0.947) < 0.09, f"roulette sampled RTP {r1:.3f}")
kb = [{"stake": 10, "numbers": random.sample(range(1, 41), 4)} for _ in range(40)]
r2 = sample("fastkeno", kb, 1500)   # informational: variance too high for a tight bound; exact per-round payouts are asserted in play()
r3 = sample("bingo", [{"stake": 10}], 1500)    # informational (1000x tail); the exact table RTP is asserted above

# bingo outcome shape + scoring consistent with what the client displays
st, r, a = play("bingo", {"stake": 10}); o = a["outcome"]
need(len(o["card"]) == 25 and o["card"][12] == 0 and len(o["draws"]) == m.BINGO_DRAWS and len(set(o["draws"])) == m.BINGO_DRAWS, "bingo outcome shape")
n, done, marked = m.bingo_score(o["card"], o["draws"]); need(n == o["lines"] and done == o["line_ids"], "bingo lines must match the card and draw")
for picks in ([1, 2, 3, 4], [5], [1, 2, 3, 4, 5, 6, 7, 8]):
    st, r, a = play("fastkeno", {"stake": 10, "numbers": picks}); o = a["outcome"]
    need(st == 200 and len(o["draw"]) == 10 and o["hits"] == len(set(o["draw"]) & set(picks)) and o["picks"] == len(picks), "fast keno hits bookkeeping")
    need(abs(o["multiplier"] - m.FASTKENO_PAYTABLES[len(picks)].get(o["hits"], 0)) <= 0.01 * max(1, o["multiplier"]), "fast keno multiplier must come from the pick-count table")

# the ledger stays consistent: every settled round has history, no ACTIVE leftovers
cur.execute("SELECT COUNT(*) FROM realtime_game_rounds WHERE status='ACTIVE'"); need(cur.fetchone()[0] == 0, "no ACTIVE rounds should remain")
print("NEW_GAMES_REGRESSION=PASS (roulette 36/38 on every bet; fast keno + bingo exact tables; real-route RTP roulette=%.3f fastkeno=%.3f bingo=%.3f)" % (r1, r2, r3))
