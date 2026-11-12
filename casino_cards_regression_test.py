import os as _o_; _o_.environ["DEFAULT_HOUSE_EDGE"] = "0.05"   # these tests check the game MATH at a fixed 5% edge, independent of the 15% production default
"""Baccarat + Blackjack through the real routes: exact math, RTP, money conservation, provable fairness."""
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
# ---------- exact baccarat probabilities (enumerate an 8-deck shoe without replacement) must equal the constants used for scaling
def exact():
    CNT=[128]+[32]*9; out={"player":0.0,"banker":0.0,"tie":0.0}; c=list(CNT)
    def draw(cb):
        n=sum(c)
        for v in range(10):
            if c[v]: pr=c[v]/n; c[v]-=1; cb(v,pr); c[v]+=1
    def fin(p,b,pr): p%=10;b%=10; out["player" if p>b else "banker" if b>p else "tie"]+=pr
    def bd(b,p3):
        if b<=2: return True
        if b==7: return False
        if p3 is None: return b<=5
        return {3:p3!=8,4:2<=p3<=7,5:4<=p3<=7,6:6<=p3<=7}[b]
    def l1(v1,p1):
      def l2(v2,p2):
        def l3(v3,p3_):
          def l4(v4,p4_):
            pr=p1*p2*p3_*p4_; P=(v1+v3)%10; B=(v2+v4)%10
            if P>=8 or B>=8: fin(P,B,pr); return
            if P<=5:
              def l5(v5,p5):
                Pn=(P+v5)%10
                if bd(B,v5): draw(lambda v6,p6: fin(Pn,B+v6,pr*p5*p6))
                else: fin(Pn,B,pr*p5)
              draw(l5)
            else:
              if bd(B,None): draw(lambda v6,p6: fin(P,B+v6,pr*p6))
              else: fin(P,B,pr)
          draw(l4)
        draw(l3)
      draw(l2)
    draw(l1); return out
ex=exact()
for k in ex: need(abs(ex[k]-cc.BACC_W[k])<1e-8,f"baccarat {k}: exact {ex[k]} != constant {cc.BACC_W[k]}")
# ---------- baccarat through the provably-fair routes
for bad in ({"stake":10},{"stake":10,"choice":"dragon"},{"stake":10,"choice":"player","x":1}):
    st,r,_=play("baccarat",bad); need(st==400,f"invalid baccarat input accepted: {bad} -> {st}")
_r.seed(11); res={}
for choice,n in (("player",1200),("banker",1200),("tie",4000)):
    s=p=0.0; pushes=0
    for _ in range(n):
        st,r,a=play("baccarat",{"stake":10,"choice":choice}); need(st==200,f"baccarat start failed {st} {r}")
        o=a["outcome"]; s+=10; p+=a["payout"]
        need(o["winner"] in ("player","banker","tie") and len(o["player"])>=2 and len(o["banker"])>=2,"baccarat outcome shape")
        need(o["player_total"]==sum(cc.bacc_val(x) for x in o["player"])%10 and o["banker_total"]==sum(cc.bacc_val(x) for x in o["banker"])%10,"totals must match cards")
        if o["push"]:
            pushes+=1; need(abs(a["payout"]-10)<1e-9 and not a["won"],"push must return the exact stake and not count as a win")
        else: need(a["won"]==(o["winner"]==choice),"won flag mismatch")
        need("server_seed" in o,"seed must be revealed")
    res[choice]=p/s
    need(abs(res[choice]-0.95)<(0.35 if choice=="tie" else 0.09),f"baccarat {choice} RTP {res[choice]:.3f}")
# ---------- blackjack
def bj(m,path,body=None): return call(UID,m,path,body)
for bad in ({},{"stake":"x"},{"stake":-1},{"stake":10,"foo":1},{"stake":0}):
    st,r=bj("POST","/api/blackjack/start",bad); need(st==400,f"invalid blackjack start accepted {bad} -> {st}")
cur.execute("UPDATE users SET balance=100000 WHERE user_id=?",(UID,)); conn.commit()
def bal():
    cur.execute("SELECT balance FROM users WHERE user_id=?",(UID,)); return cur.fetchone()[0]
b0=bal(); st,r=bj("POST","/api/blackjack/start",{"stake":10,"client_seed":"abc"}); need(st==200,f"{st} {r}")
if r["status"]=="ACTIVE":
    need("dealer_hidden" in r and r["dealer_hidden"]==1 and len(r["dealer"])==1,"hole card must stay hidden while ACTIVE")
    need("server_seed" not in r,"server seed must not leak while ACTIVE")
    need(abs(b0-bal()-10)<1e-9,"stake must be deducted at the deal")
    st2,r2=bj("POST","/api/blackjack/start",{"stake":10}); need(st2==200 and r2.get("recovered") and r2["round_id"]==r["round_id"],"second start must resume, not charge again")
    need(abs(b0-bal()-10)<1e-9,"resume must not charge again")
    st3,r3=bj("POST",f"/api/blackjack/{r['round_id']}/action",{"action":"stand","seq":len(r["player"])+5}); need(st3==409,"stale seq must be rejected")
    st4,r4=bj("POST",f"/api/blackjack/{r['round_id']}/action",{"action":"fly"}); need(st4==400,"invalid action")
    st5,r5=bj("POST",f"/api/blackjack/{r['round_id']}/action",{"action":"stand","seq":len(r["player"])}); need(st5==200 and r5["status"]!="ACTIVE","stand must finish the hand")
    st6,r6=bj("POST",f"/api/blackjack/{r['round_id']}/action",{"action":"hit"}); need(st6==409,"acting on a finished round must be refused")
# play many hands with basic strategy; verify conservation, fairness reveal and RTP
tot_stake=tot_pay=0.0; start_bal=bal(); wins=pushes=0
for i in range(600):
    st,r=bj("POST","/api/blackjack/start",{"stake":10,"client_seed":f"t{i}"}); need(st==200,f"start {st} {r}")
    staked=10.0
    while r["status"]=="ACTIVE":
        act=cc.bj_basic_action(r["player"],r["dealer"][0],"double" in r["actions"])
        st,r=bj("POST",f"/api/blackjack/{r['round_id']}/action",{"action":act,"seq":len(r["player"])}); need(st==200,f"action {act} -> {st} {r}")
    o=r["outcome"]; staked=r["total_stake"]; tot_stake+=staked; tot_pay+=r["payout"]
    wins+= r["status"]=="WON"; pushes+= r["status"]=="PUSH"
    shoe=cc.bj_shoe(o["server_seed"],o["client_seed"])
    need(r["player"][:2]==[shoe[0],shoe[2]] and r["dealer"][:2]==[shoe[1],shoe[3]],"revealed seed must reproduce the opening deal")
    need(abs(r["payout"]-cc.bj_payout(staked,o["result"],0.05))<0.011,f"payout must follow the disclosed table: {o['result']} {r['payout']}")
need(abs((start_bal-bal())-(tot_stake-tot_pay))<0.05,"balance change must equal staked minus paid (money conservation)")
rtp=tot_pay/tot_stake; need(0.86<rtp<1.03,f"blackjack basic-strategy RTP {rtp:.3f} outside the expected band")
# abandoned hand: auto-stand on expiry (never a free refund)
st,r=bj("POST","/api/blackjack/start",{"stake":10,"client_seed":"idle"}); 
if r["status"]=="ACTIVE":
    cur.execute("UPDATE blackjack_rounds SET started_at='2000-01-01 00:00:00' WHERE id=?",(r["round_id"],)); conn.commit()
    st,a=bj("GET","/api/blackjack/active"); need(st==200 and a.get("active") is False,"expired round must be settled, not left open")
    cur.execute("SELECT status FROM blackjack_rounds WHERE id=?",(r["round_id"],)); need(cur.fetchone()[0] in ("WON","LOST","PUSH"),"expired round must be settled by auto-stand")
print("CASINO_CARDS_REGRESSION=PASS (baccarat exact odds; RTP player=%.3f banker=%.3f tie=%.3f; blackjack RTP=%.3f over 600 hands; hole card hidden; provably fair; money conserved; auto-stand on timeout)"%(res["player"],res["banker"],res["tie"],rtp))
