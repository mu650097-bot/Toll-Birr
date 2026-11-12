"""Sports: LIVE matches (score, ordering, expiry) and betting refused after kickoff."""
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

conn = w.db(); cur = conn.cursor(); UID = 5005
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



import time
now=time.strftime("%Y-%m-%d %H:%M:%S"); past=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time()-1800)); old=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time()-8*3600)); fut=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time()+3600))
for name,c in (("Live FC",past),("Future FC",fut),("Forgotten FC",old)):
    cur.execute("INSERT INTO sports_matches(home_team,away_team,odds_home,odds_draw,odds_away,status,created_at,closes_at,home_score,away_score,live_minute) VALUES(?,?,?,?,?,'OPEN',?,?,?,?,?)",(name,"Rivals",2.0,3.2,3.0,now,c,2,1,"67'"))
conn.commit()
st,r=call(UID,"GET","/api/sports/matches",None); need(st==200,st)
byname={m["home_team"]:m for m in r["matches"]}
need("Live FC" in byname and byname["Live FC"]["live"] and byname["Live FC"]["home_score"]==2 and byname["Live FC"]["live_minute"]=="67'","live match must be listed with score")
need("Future FC" in byname and not byname["Future FC"]["live"] and byname["Future FC"]["home_score"] is None,"upcoming match must not leak score")
need("Forgotten FC" not in byname,"match 8h past kickoff must disappear")
need(r["matches"][0]["home_team"]=="Live FC","live matches first")
mid=byname["Live FC"]["id"]
st,rr=call(UID,"POST","/api/sports/bet",{"match_id":mid,"selection":"HOME","stake":10}); need(st in (403,404),f"bet on live match must be refused, got {st}")
print("SPORTS_LIVE_REGRESSION=PASS (live listed with score; upcoming hides score; stale hidden; betting refused after kickoff)")
