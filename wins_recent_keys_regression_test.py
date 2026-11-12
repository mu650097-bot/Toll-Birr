"""/api/wins/recent must give every win a REAL game key (so the rotating banner / ticker always has the game picture and opens the right page):
live rounds (game_<k>_live_payout), real-time (_rt_payout), classic and auction wins. Run: python3 wins_recent_keys_regression_test.py"""
import os, sys, tempfile, json, time, hmac, hashlib, urllib.parse
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
os.environ.update(dict(BOT_TOKEN="123:abc", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1", MINI_APP_URL="https://x.example/",
           MINI_APP_API_URL="https://x.example/api", ADMIN_PANEL_PIN="1234", SUPPORT_CONTACT="@s", DOMAIN="x.example"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webapp_api as w
def init_data(uid):
    p = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "T%d" % uid}), "query_id": "q"}
    dcs = "\n".join(f"{k}={p[k]}" for k in sorted(p)); sk = hmac.new(b"WebAppData", b"123:abc", hashlib.sha256).digest()
    p["hash"] = hmac.new(sk, dcs.encode(), hashlib.sha256).hexdigest(); return urllib.parse.urlencode(p)
c = w.app.test_client(); H = {"X-Telegram-Init-Data": init_data(5)}
conn = w.db(); cur = conn.cursor()
cur.execute("INSERT OR REPLACE INTO users(user_id,first_name,balance) VALUES (5,'Player',0)")
types = ["game_aviator_live_payout", "game_number_live_live_payout", "game_keno_super_live_payout", "game_keno_live_payout", "game_slot_rt_payout",
         "game_dice_payout", "game_crash_live_payout", "auction_win", "sports_win", "group_mines_win"]
for i, t in enumerate(types):
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES (5,?,?,?)", (100 + i, t, "2026-11-0%d 10:00:00" % (1 + i % 9)))
conn.commit(); conn.close()
r = c.get("/api/wins/recent", headers=H); assert r.status_code == 200, r.status_code
wins = {x["game"]: x for x in r.get_json()["wins"]}
for k in ("aviator", "number", "keno_super", "keno", "slot", "dice", "crash", "marketplace", "sports", "boom"):
    assert k in wins, (k, sorted(wins))
assert not any(str(k).endswith("_live") for k in wins), sorted(wins)      # no raw "..._live" engine keys leak to the client
assert all(x["game_name"] for x in wins.values()), wins
print("WINS_RECENT_KEYS_REGRESSION=PASS (live / real-time / auction wins map to real game keys with a name)")
