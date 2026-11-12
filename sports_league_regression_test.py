"""Sports: league + sport (football / basketball / tennis) on matches. Run from the project folder AFTER apply_sports_patch.py:
   python sports_league_regression_test.py"""
import hashlib, hmac, json, os, sys, tempfile, time
from urllib.parse import urlencode

d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
for k, v in dict(BOT_TOKEN="1:x", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1",
                 MINI_APP_URL="https://a.example", MINI_APP_API_URL="https://a.example/api", SUPPORT_CONTACT="@s").items():
    os.environ.setdefault(k, v)
os.environ["ADMIN_PANEL_PIN"] = "123456"
import webapp_api as w


def need(c, msg):
    if not c:
        print("SPORTS_LEAGUE_REGRESSION=FAIL:", msg); sys.exit(1)


def init_data(uid):
    f = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":")), "query_id": "q"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    f["hash"] = hmac.new(hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest(), dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(f)

client = w.app.test_client()
PIN_TOKEN = {}
def call(uid, method, path, body=None):
    w._rate_limit_hits.clear()
    h = {"X-Telegram-Init-Data": init_data(uid)}
    if uid in PIN_TOKEN: h["X-Admin-Pin-Token"] = PIN_TOKEN[uid]
    r = client.open(path, method=method, json=body, headers=h)
    return r.status_code, (r.get_json(silent=True) or {})

ADMIN, USER = 1, 7007
conn = w.db(); cur = conn.cursor()
for uid in (ADMIN, USER):
    cur.execute("INSERT OR REPLACE INTO users(user_id,balance,terms_accepted_at) VALUES(?,?,?)", (uid, 1000.0, "2026-01-01 00:00:00"))
conn.commit()
st, r = call(ADMIN, "POST", "/api/admin/verify-pin", {"pin": "123456"}); need(st == 200 and r.get("token"), f"admin PIN {st} {r}"); PIN_TOKEN[ADMIN] = r["token"]
fut = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 3 * 3600))
def create(**kw):
    b = dict(home_team="A", away_team="B", odds_home=2.0, odds_away=3.0, closes_at=fut); b.update(kw)
    return call(ADMIN, "POST", "/api/admin/sports/match", b)

st, r = create(home_team="Arsenal", away_team="Chelsea", odds_draw=3.4, league="Premier League", sport="football"); need(st == 200, f"football create {st} {r}")
st, r = create(home_team="Lakers", away_team="Celtics", odds_home=1.9, odds_away=1.9, league="NBA", sport="basketball"); need(st == 200, f"basketball create (no draw) {st} {r}")
st, r = create(home_team="Alcaraz", away_team="Sinner", odds_home=1.6, odds_away=2.4, sport="tennis"); need(st == 200, f"tennis create {st} {r}")
st, r = create(home_team="Old", away_team="Style", odds_draw=3.2); need(st == 200, f"legacy create (no league/sport) {st} {r}")
st, r = create(home_team="Long", away_team="League", odds_draw=3.2, league="L" * 80); need(st == 200, f"long league create {st} {r}")
st, r = create(sport="cricket", odds_draw=3.0); need(st == 400, f"unknown sport must be refused, got {st}")
st, r = create(home_team="X", away_team="Y", odds_home=2.1, odds_away=2.1, sport="tennis"); need(st == 400, f"two-way odds with no house margin must be refused, got {st}")
st, r = create(home_team="X", away_team="Y", sport="football"); need(st == 400, f"football without draw odds must be refused, got {st}")

st, r = call(USER, "GET", "/api/sports/matches"); need(st == 200, st)
by = {m["home_team"]: m for m in r["matches"]}
need(by["Arsenal"]["league"] == "Premier League" and by["Arsenal"]["sport"] == "football", "football league/sport returned")
need(by["Lakers"]["sport"] == "basketball" and by["Lakers"]["league"] == "NBA" and not by["Lakers"]["odds_draw"], "basketball has no draw odds")
need(by["Alcaraz"]["sport"] == "tennis" and by["Alcaraz"]["league"] is None, "tennis without league")
need(by["Old"]["sport"] == "football" and by["Old"]["league"] is None, "legacy match defaults to football")
need(len(by["Long"]["league"]) == 40, "league trimmed to 40 chars")

mid = by["Alcaraz"]["id"]
st, r = call(USER, "POST", "/api/sports/bet", {"match_id": mid, "selection": "HOME", "stake": 10}); need(st == 200, f"bet on a two-way HOME {st} {r}")
st, r = call(USER, "POST", "/api/sports/bet", {"match_id": mid, "selection": "DRAW", "stake": 10}); need(st == 400, f"DRAW bet on a two-way sport must be refused, got {st}")
st, r = call(USER, "POST", "/api/sports/bet", {"match_id": by["Arsenal"]["id"], "selection": "DRAW", "stake": 10}); need(st == 200, f"football DRAW bet still works {st} {r}")
print("SPORTS_LEAGUE_REGRESSION=PASS (league+sport stored and listed, two-way sports have no draw, margin guard holds, legacy matches unchanged)")
