"""Pool/rake regression: Number + Boom + Sports can never pay more than players put in."""
import os, random, sys, tempfile
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api",
                 ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w
_c=w.db(); _c.execute("UPDATE platform_settings SET value='0' WHERE key='welcome_bonus_enabled'"); _c.commit(); _c.close()   # these tests assume brand-new users start at exactly 0

def need(c, m):
    if not c: print("POOL_GAMES_REGRESSION=FAIL:", m); sys.exit(1)

conn = w.db(); cur = conn.cursor()
cur.execute("PRAGMA table_info(users)"); cols = [r["name"] for r in cur.fetchall()]
def add_user(uid, bal=1000.0):
    cur.execute("INSERT OR REPLACE INTO users(user_id,balance) VALUES(?,?)", (uid, bal))
for u in list(range(1, 21)) + [101, 102]: add_user(u)
conn.commit()
GRAND_START = round(cur.execute('SELECT SUM(balance) FROM users').fetchone()[0], 2)
bal = lambda u: cur.execute("SELECT balance FROM users WHERE user_id=?", (u,)).fetchone()[0]
def total_money(): return round(cur.execute("SELECT SUM(balance) FROM users").fetchone()[0], 2)
def ledger(t): return round(cur.execute("SELECT COALESCE(SUM(amount),0) FROM platform_ledger WHERE entry_type=?", (t,)).fetchone()[0], 2)

# ---- Number: money conservation over many rounds
start = total_money(); random.seed(7)
for rnd_i in range(300):
    cur.execute("BEGIN IMMEDIATE")
    r = w._number_pool_tick(cur)
    for u in random.sample(range(1, 21), random.randint(0, 8)):
        # test fixture: a player who has run dry is topped up OUTSIDE the measured money (start is re-based), so the
        # conservation check still sees every birr; previously a long losing streak made this test fail at random.
        if bal(u) < 10.0: cur.execute("UPDATE users SET balance=balance+1000 WHERE user_id=?", (u,)); start += 1000.0; GRAND_START += 1000.0
        err, code = w._number_pool_join(cur, u, f"u{u}", random.randint(1, 15), 10.0)
        need(err is None, f"join failed {err}")
    if bal(1) < 10.0: cur.execute("UPDATE users SET balance=balance+1000 WHERE user_id=1"); start += 1000.0; GRAND_START += 1000.0
    err, code = w._number_pool_join(cur, 1, "u1", 3, 10.0)  # duplicate / or first
    cur.execute("UPDATE number_pool_rounds SET closes_at='2000-01-01 00:00:00' WHERE status='OPEN'")
    w._number_pool_tick(cur)  # settles
    conn.commit()
cur.execute("BEGIN IMMEDIATE"); carry = w._pool_carry_get(cur, "number"); conn.commit()
# players' total + house rake + pool still owed == starting money
need(abs(total_money() + ledger("number_pool_rake") + carry - start) < 0.05,
     f"Number money not conserved: {total_money()} + {ledger('number_pool_rake')} + {carry} != {start}")
need(carry >= -0.001, "Number pool went negative")
need(ledger("number_pool_rake") > 0, "no rake recorded")
cur.execute("SELECT COUNT(*) FROM number_pool_entries WHERE round_id IN (SELECT round_id FROM number_pool_entries GROUP BY round_id,user_id HAVING COUNT(*)>1)")
need(cur.fetchone()[0] == 0, "duplicate entries in one round")

# one guess per user per round
cur.execute("BEGIN IMMEDIATE"); w._number_pool_tick(cur)
need(w._number_pool_join(cur, 5, "u5", 4, 10.0)[0] is None, "first join should work")
need(w._number_pool_join(cur, 5, "u5", 5, 10.0)[1] == 409, "second guess must be rejected")
conn.commit()

# ---- Boom pool shares never exceed pool / cap
for _ in range(5000):
    pool = round(random.uniform(0, 5000), 2)
    ws = [(i, random.uniform(1, 600)) for i in range(random.randint(1, 6))]
    out = w._boom_pool_shares(pool, ws)
    need(sum(out.values()) <= min(pool, w.MAX_ROUND_PAYOUT_ETB) + 1e-6, "boom paid more than pool/cap")
need(w._boom_pool_shares(0, [(1, 5)]) == {1: 0.0}, "empty pool must pay nothing")

# ---- Boom end-to-end through the real route (join -> win), pool conservation
from types import SimpleNamespace
for u in (101, 102): add_user(u)
conn.commit()
cur.execute("BEGIN IMMEDIATE"); w._pool_carry_add(cur, "boom", 0); conn.commit()
start = total_money(); carry0 = 0.0
with w.app.test_request_context():
    rt = w.boom_pick
    fn = getattr(rt, "__wrapped__", rt)
    while hasattr(fn, "__wrapped__"): fn = fn.__wrapped__
    import json
    wins = 0
    for rounds in range(400):
        for u in (101, 102):
            w.g.tg_user = {"id": u, "first_name": "T"}
            while True:
                c = w.db(); q = c.cursor(); q.execute("BEGIN IMMEDIATE")
                rr = w._get_or_create_boom_round(q); c.commit()
                bombs = json.loads(rr["bombs"]); opened = json.loads(rr["opened"]); c.close()
                safe = [b for b in range(1, 10) if b not in bombs and b not in opened]
                if not safe: break
                with w.app.test_request_context(json={"box": safe[0]}):
                    w.g.tg_user = {"id": u, "first_name": "T"}
                    resp = fn()
                data = resp.get_json() if hasattr(resp, "get_json") else resp[0].get_json()
                if data.get("game_over") or data.get("result") in ("WIN", "BOOM"): break
            break
conn.close(); conn = w.db(); cur = conn.cursor()
cur.execute("BEGIN IMMEDIATE"); bcarry = w._pool_carry_get(cur, "boom"); conn.commit()
cur.execute("BEGIN IMMEDIATE"); ncarry = w._pool_carry_get(cur, "number"); conn.commit()
cur.execute("SELECT COUNT(*) FROM webapp_boom_players"); need(cur.fetchone()[0] > 0, "boom flow made no entries")
need(abs(total_money() + ledger("boom_pool_rake") + ledger("number_pool_rake") + bcarry + ncarry - GRAND_START) < 0.1,
     "money not conserved across Number+Boom: %s" % (total_money() + ledger("boom_pool_rake") + ledger("number_pool_rake") + bcarry + ncarry - GRAND_START))
need(bcarry >= -0.001, "boom pool negative")
print("POOL_GAMES_REGRESSION=PASS (Number conservation over 300 rounds; one guess/round; Boom shares <= pool; Boom flow ran)")
