import os as _o_; _o_.environ["DEFAULT_HOUSE_EDGE"] = "0.05"   # these tests check the game MATH at a fixed 5% edge, independent of the 15% production default
"""Dragon Tiger + Andar Bahar through the real routes: exact math, RTP, money conservation, provable fairness."""
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
        print("COIN_PENALTY_REGRESSION=FAIL:", msg); sys.exit(1)


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

# ---------- exact odds (re-derived independently) must match the constants used for scaling
from itertools import combinations
import math
tie=13*(32*31)/(416*415)
need(abs(cc.DT_W["tie"]-tie)<1e-12 and abs(cc.DT_W["dragon"]-(1-tie)/2)<1e-12,"Dragon Tiger probabilities")
# Andar wins when the FIRST matching card sits at an odd position among the 51 cards after the joker
tot=math.comb(51,3); andar=sum(math.comb(51-k,2) for k in range(1,52,2))/tot
need(abs(cc.AB_W["andar"]-andar)<1e-12 and abs(cc.AB_W["andar"]+cc.AB_W["bahar"]-1)<1e-12,"Andar Bahar probabilities")
_r.seed(5)
# a deal is always consistent: dragon/tiger ranks compare correctly; andar/bahar stop at the first match
for _ in range(3000):
    d=cc.dt_deal(_r.SystemRandom()); need(d["winner"]==("dragon" if d["dragon_rank"]>d["tiger_rank"] else "tiger" if d["tiger_rank"]>d["dragon_rank"] else "tie"),"dt winner")
    a=cc.ab_deal(_r.SystemRandom()); jr=a["joker"]%13; seq=[]
    for i in range(max(len(a["andar"]),len(a["bahar"]))):
        if i<len(a["andar"]): seq.append(("andar",a["andar"][i]))
        if i<len(a["bahar"]): seq.append(("bahar",a["bahar"][i]))
    hits=[s for s,c in seq if c%13==jr]; need(len(hits)==1 and hits[0]==a["winner"] and seq[-1][1]%13==jr,"ab must stop at the first matching rank")
# ---------- through the provably-fair routes
for key,bad in (("dragontiger",{"stake":10}),("dragontiger",{"stake":10,"choice":"andar"}),("andarbahar",{"stake":10}),("andarbahar",{"stake":10,"choice":"tie"}),("andarbahar",{"stake":10,"choice":"andar","x":1})):
    st,r,_=play(key,bad); need(st==400,f"invalid {key} input accepted: {bad} -> {st}")
_r.seed(21); res={}
for key,choices,n in (("dragontiger",("dragon","tiger","tie"),(1500,1500,4000)),("andarbahar",("andar","bahar"),(1500,1500))):
    for choice,cnt in zip(choices,n):
        s=p=0.0
        for _ in range(cnt):
            st,r,a=play(key,{"stake":10,"choice":choice}); need(st==200,f"{key} start failed {st} {r}")
            o=a["outcome"]; s+=10; p+=a["payout"]
            need("server_seed" in o and o["winner"] in (("dragon","tiger","tie") if key=="dragontiger" else ("andar","bahar")),f"{key} outcome shape")
            if key=="dragontiger" and o["push"]: need(abs(a["payout"]-10)<1e-9 and not a["won"],"push must return the exact stake and not count as a win")
            else: need(a["won"]==(o["winner"]==choice),f"{key} won flag mismatch")
        res[(key,choice)]=p/s
        need(abs(res[(key,choice)]-0.95)<(0.35 if choice=="tie" else 0.09),f"{key} {choice} RTP {res[(key,choice)]:.3f}")
print("CARDS2_REGRESSION=PASS (exact odds; deals consistent; DT RTP d=%.3f t=%.3f tie=%.3f; AB RTP andar=%.3f bahar=%.3f; money conserved; seeds revealed)"%(res[("dragontiger","dragon")],res[("dragontiger","tiger")],res[("dragontiger","tie")],res[("andarbahar","andar")],res[("andarbahar","bahar")]))
