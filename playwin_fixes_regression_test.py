"""Play Win fixes: admin-release Mystery Box, invite bonus (play-only), every lobby game under admin control, BetPro routes loaded.
Run: python3 playwin_fixes_regression_test.py"""
import os, sys, tempfile, json, time, hmac, hashlib, urllib.parse, re
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
os.environ.update(dict(BOT_TOKEN="123:abc", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1", MINI_APP_URL="https://x.example/",
           MINI_APP_API_URL="https://x.example/api", ADMIN_PANEL_PIN="1234", SUPPORT_CONTACT="@s", DOMAIN="x.example"))
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import webapp_api as w
_c=w.db(); _c.execute("UPDATE platform_settings SET value='0' WHERE key='welcome_bonus_enabled'"); _c.commit(); _c.close()   # these tests assume brand-new users start at exactly 0
def init_data(uid):
    p = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "T%d" % uid}), "query_id": "q"}
    dcs = "\n".join(f"{k}={p[k]}" for k in sorted(p)); sk = hmac.new(b"WebAppData", b"123:abc", hashlib.sha256).digest()
    p["hash"] = hmac.new(sk, dcs.encode(), hashlib.sha256).hexdigest(); return urllib.parse.urlencode(p)
c = w.app.test_client(); H = lambda u: {"X-Telegram-Init-Data": init_data(u)}
w._verify_admin_pin_token = lambda t, u: True
conn = w.db(); cur = conn.cursor()
for u in (1, 50, 60): cur.execute("INSERT OR REPLACE INTO users(user_id,first_name,balance) VALUES (?,?,0)", (u, "U%d" % u))
cur.execute("UPDATE users SET terms_accepted_at=?", (w._now(),)); conn.commit(); conn.close()

# 1) BetPro routes are registered (admin photo upload used to answer 404)
rules = {r.rule for r in w.app.url_map.iter_rules()}
assert "/api/admin/promo/<slot>" in rules and "/api/promo/images" in rules, "betpro_v1.py is not loaded by webapp_api.py"

# 2) Mystery Box: closed until the admin releases; one open per player per release; closing works
st = lambda u: c.get("/api/mbox/status", headers=H(u)).get_json()
assert st(50)["mode"] == "admin" and not st(50)["can_open"]
assert c.post("/api/mbox/open", headers=H(50), json={}).status_code == 409
assert c.post("/api/admin/mbox/release", headers=H(50), json={"minutes": 10}).status_code == 403
c.post("/api/admin/mbox", headers=H(1), json={"enabled": True, "mode": "admin", "cooldown_min": 60, "daily_budget": 0, "prizes": [[2, 1]]})
assert c.post("/api/admin/mbox/release", headers=H(1), json={"minutes": 10}).status_code == 200
assert st(50)["can_open"] and st(50)["released"]
r = c.post("/api/mbox/open", headers=H(50), json={}); assert r.status_code == 200 and r.get_json()["prize"] == 2.0
assert c.post("/api/mbox/open", headers=H(50), json={}).status_code == 409                       # once per release
assert c.post("/api/mbox/open", headers=H(60), json={}).status_code == 200                        # other players still can
conn = w.db(); cur = conn.cursor(); cur.execute("SELECT balance,bonus_locked FROM users WHERE user_id=50"); b, lk = cur.fetchone(); conn.close()
assert (b, lk) == (2.0, 2.0), (b, lk)                                                              # prize is play-only
c.post("/api/admin/mbox/release", headers=H(1), json={"minutes": 5}); assert st(50)["can_open"]   # a new release re-opens it
assert c.post("/api/admin/mbox/close", headers=H(1)).get_json()["closed"] == 1 and not st(50)["can_open"]

_c = w.db(); _c.execute("INSERT OR REPLACE INTO platform_settings(key,value,updated_at) VALUES('invite_bonus_requires_deposit','0',?)", (w._now(),)); _c.commit(); _c.close()   # default is now 'pay after the invitee's first deposit' (anti-abuse); this test checks the immediate-pay mode
# 3) Invite: 1 ETB per invited person, play-only, counted once, works even when the claim is the account's first request
r = c.post("/api/referral/claim", headers=H(70), json={"code": "ref_50"}); assert r.get_json()["ok"] is True
assert c.post("/api/referral/claim", headers=H(70), json={"code": "ref_50"}).get_json()["ok"] is False
assert c.post("/api/referral/claim", headers=H(50), json={"code": "ref_50"}).get_json()["ok"] is False   # never yourself
conn = w.db(); cur = conn.cursor(); cur.execute("SELECT balance,bonus_locked FROM users WHERE user_id=50"); b, lk = cur.fetchone()
cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id=50 AND transaction_type='invite_bonus'"); nb = cur.fetchone()[0]; conn.close()
assert (b, lk, nb) == (3.0, 3.0, 1), (b, lk, nb)
import bonus_wallet
conn = w.db(); cur = conn.cursor(); assert bonus_wallet.withdrawable(cur, 50)[2] == 0.0; conn.close()  # 3 ETB all bonus -> nothing withdrawable

# 4) Admin controls EVERY lobby game (entry limits + house edge)
src = open(os.path.join(HERE, "app.js"), encoding="utf-8").read()
lobby = re.findall(r'\{ key: "([a-z0-9_]+)", icon:', src.split("const GAMES = [")[1].split("];")[0])
keys = {i["key"] for i in c.get("/api/admin/game-control", headers=H(1)).get_json()["items"]}
missing = [k for k in lobby if k not in keys and k not in ("boom", "number")]
assert not missing, missing
# per-game limits only apply while the admin's GLOBAL min bet is switched off (the global value overrides every game)
_c = w.db(); _c.execute("UPDATE platform_settings SET value='0' WHERE key='global_min_bet_enabled'"); _c.commit(); _c.close()
for k in ("buffalo", "aztec", "flame", "triplegold", "slot", "keno"):
    assert c.post("/api/admin/game-control", headers=H(1), json={"key": k, "enabled": True, "min_stake": 2, "max_stake": 50, "house_edge": 0.12}).status_code == 200, k
    assert w._cabinet_limits(k) == (True, 2.0, 50.0, 0.12), (k, w._cabinet_limits(k))
print("PLAYWIN_FIXES_REGRESSION=PASS (betpro routes; admin-release mystery box; invite 1 ETB play-only; %d lobby games admin-controlled)" % len(lobby))
