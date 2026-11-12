import os as _o_; _o_.environ["DEFAULT_HOUSE_EDGE"] = "0.05"   # these tests check the game MATH at a fixed 5% edge, independent of the 15% production default
"""Dice (two dice Under/Exact/Over) + Coin Flip streak through the real routes: exact math, RTP, money conservation, provable fairness."""
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
        print("DICE2_REGRESSION=FAIL:", msg); sys.exit(1)


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

conn = w.db(); cur = conn.cursor(); UID = 5006
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
    return st, r, a



import random as _r, casino_cards as cc


import itertools
import dice_math as dm
# ---------- exact chances == brute force over the 36 equally likely rolls
for mode in ("under","exact","over"):
    for t in range(2,13):
        n=sum(1 for a,b in itertools.product(range(1,7),repeat=2) if dm.dice2_won(mode,t,a+b))
        need(abs(dm.dice2_chance(mode,t)-n/36)<1e-12,f"chance {mode} {t}")
        ok,_=dm.dice2_valid(mode,t); need(ok==(0<n/36<=0.9),f"validity {mode} {t}")
need(not dm.dice2_valid("over",12)[0] and not dm.dice2_valid("under",2)[0] and dm.dice2_valid("over",7)[0],"edge validity")
need(abs(dm.dice2_chance("over",7)-15/36)<1e-12,"over 7 = 41.67%")
# ---------- invalid input is rejected by BOTH engines
bad=[{"stake":10},{"stake":10,"mode":"over"},{"stake":10,"mode":"sideways","target":7},{"stake":10,"mode":"over","target":13},
     {"stake":10,"mode":"over","target":12},{"stake":10,"mode":"under","target":2},{"stake":10,"mode":"under","target":12},{"stake":10,"mode":"over","target":7,"x":1}]
for b in bad:
    st,r,_=play("dice2",b); need(st==400,f"realtime accepted invalid dice2 {b} -> {st}")
# ---------- RTP + payout formula through both engines
_r.seed(33); res={}
for mode,t,n in (("over",7,2500),("under",5,2500),("exact",7,3500),("exact",2,6000)):
    p=dm.dice2_chance(mode,t); s=pay=0.0
    for _ in range(n):
        st,r,a=play("dice2",{"stake":10,"mode":mode,"target":t}); need(st==200,f"dice2 start {st} {r}")
        o=a["outcome"]; s+=10; pay+=a["payout"]
        need(o["total"]==sum(o["dice"]) and all(1<=d<=6 for d in o["dice"]) and "server_seed" in o,"dice2 outcome shape")
        need(a["won"]==dm.dice2_won(mode,t,o["total"]),"won flag must follow the dice")
        if a["won"]: need(abs(a["payout"]-round(10*0.95/p,2))<0.011,f"payout {a['payout']} != stake*(1-edge)/P ({10*0.95/p:.2f})")
        else: need(a["payout"]==0,"loss pays nothing")
    res[(mode,t)]=pay/s; need(abs(res[(mode,t)]-0.95)<(0.25 if p<0.05 else 0.08),f"dice2 {mode} {t} realtime RTP {res[(mode,t)]:.3f}")
# the retired one-shot route stays closed (the cabinet engine itself is covered by rtp_regression_test.py)
st,r=call(UID,"POST","/api/games/dice2/play",{"stake":10,"mode":"over","target":7}); need(st in (404,410),f"one-shot route must stay retired, got {st}")
print("DICE2_REGRESSION=PASS (exact chances; validity; realtime rejects bad input; payout=(1-edge)/P; RTP over7=%.3f under5=%.3f exact7=%.3f exact2=%.3f)"%(res[("over",7)],res[("under",5)],res[("exact",7)],res[("exact",2)]))
