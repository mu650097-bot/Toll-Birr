import os as _o_; _o_.environ["DEFAULT_HOUSE_EDGE"] = "0.05"   # these tests check the game MATH at a fixed 5% edge, independent of the 15% production default
"""Coin Flip + Penalty Shootout through the real /round/start -> /action routes."""
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

conn = w.db(); cur = conn.cursor(); UID = 5002
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
    nominal = {"coinflip": 2.0, "penalty": 1.5}[key]
    exp = round(body["stake"] * nominal * 0.95, 2) if a["payout"] > 0 else 0.0
    need(abs(a["payout"] - exp) < 0.011, f"{key}: payout {a['payout']} != stake * {nominal} * (1-edge) = {exp}")
    need(a["won"] == (a["payout"] > 0), f"{key}: won flag must match payout")
    return st, r, a


bad=[("coinflip",{"stake":10}),("coinflip",{"stake":10,"choice":"edge"}),("coinflip",{"stake":10,"choice":"high"}),
     ("penalty",{"stake":10}),("penalty",{"stake":10,"choice":"up"}),("penalty",{"stake":-5,"choice":"left"}),("coinflip",{"stake":10,"choice":"heads","x":1})]
for key,b in bad:
    st,r,_=play(key,b); need(st==400,f"invalid {key} input accepted: {b} -> {st}")
random.seed(7)
def sample(key,choices,n):
    s=p=0.0; wins=0
    for _ in range(n):
        c=random.choice(choices); st,r,a=play(key,{"stake":10,"choice":c}); need(st==200,f"{key} start failed {st} {r}")
        s+=10; p+=a["payout"]; wins+=1 if a["won"] else 0
        o=a["outcome"]; need(o.get("server_authoritative") and "server_seed" in o,f"{key} must be server authoritative and reveal seed")
        if key=="coinflip": need(o["flip"] in ("heads","tails") and (a["won"]==(o["flip"]==c)),"coinflip outcome/won mismatch")
        else: need(o["keeper"] in ("left","center","right") and (a["won"]==(o["keeper"]!=c)),"penalty outcome/won mismatch")
    return p/s, wins/n
r1,w1=sample("coinflip",["heads","tails"],3000); need(abs(r1-0.95)<0.07,f"coinflip route RTP {r1:.3f}"); need(abs(w1-0.5)<0.04,f"coinflip win rate {w1:.3f}")
r2,w2=sample("penalty",["left","center","right"],3000); need(abs(r2-0.95)<0.07,f"penalty route RTP {r2:.3f}"); need(abs(w2-2/3)<0.04,f"penalty win rate {w2:.3f}")
cur.execute("SELECT COUNT(*) FROM realtime_game_rounds WHERE status='ACTIVE'"); need(cur.fetchone()[0]==0,"no ACTIVE rounds should remain")
print("COIN_PENALTY_REGRESSION=PASS (validation; money conservation; route RTP coinflip=%.3f penalty=%.3f; win rates %.3f/%.3f)"%(r1,r2,w1,w2))
