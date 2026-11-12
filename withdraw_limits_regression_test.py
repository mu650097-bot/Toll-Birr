"""Withdrawal minimum / caps through the real /api/withdraw route."""
import hashlib, hmac, json, os, random, sys, tempfile, time
from math import comb
from urllib.parse import urlencode

d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api",
                 ADMIN_PANEL_PIN="123456", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
import webapp_api as w


def need(c, msg):
    if not c:
        print("NEW_GAMES_REGRESSION=FAIL:", msg); sys.exit(1)


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

conn = w.db(); cur = conn.cursor(); UID = 5003
cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(?,?,?)", (UID, 10_000_000.0, "2026-01-01 00:00:00")); conn.commit()
bal = lambda: round(cur.execute("SELECT balance FROM users WHERE user_id=?", (UID,)).fetchone()[0], 2)


def wd(amount): return call(UID,"POST","/api/withdraw",{"amount":amount,"acc_name":"CBE | T","acc_number":"1000"})
st,r=wd(0.5); need(st==400,f"0.5 ETB must be rejected, got {st}")
b0=bal()
for i in range(6):
    st,r=wd(1); need(st==200,f"withdrawal #{i+1} of 1 ETB should be accepted, got {st} {r}")
need(round(b0-bal(),2)==6.0,"six 1-ETB withdrawals must reserve exactly 6 ETB")
st,r=wd(10_000_000.0); need(st==400,"over-balance withdrawal must be rejected")
cur.execute("SELECT COUNT(*) FROM withdrawals WHERE user_id=? AND status='pending'",(UID,)); need(cur.fetchone()[0]==6,"six pending rows expected")
# turnover rule still protects deposited funds
cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",(UID,100.0,"deposit","2026-01-01 00:00:00")); conn.commit()
st,r=wd(1); need(st==200,f"a depositor who never played must be able to withdraw (turnover default 0): {st} {r}")
w.WITHDRAW_TURNOVER_MULTIPLIER=3.0   # the rule must still work when the operator turns it back on
st,r=wd(1); need(st==400 and "wager" in r.get("error",""),f"turnover rule must apply when enabled: {st} {r}")
print("WITHDRAW_LIMITS_REGRESSION=PASS (min 1 ETB; no daily caps; no play-through by default; rule still works if enabled)")
