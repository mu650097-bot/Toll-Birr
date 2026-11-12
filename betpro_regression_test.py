"""BetPro layer: admin-only promo images (sports/casino/game covers) + profile stats. Run: python3 betpro_regression_test.py"""
import os, sys, tempfile, json, time, hmac, hashlib, urllib.parse, io
d = tempfile.mkdtemp(); os.environ["DB_FILE"] = os.path.join(d, "t.db")
env = dict(BOT_TOKEN="123:abc", ADMIN_ID="1", ACCOUNT_NAME="a", CBE_ACCOUNT="1", BOA_ACCOUNT="1", TELEBIRR_NUMBER="1", MINI_APP_URL="https://x.example/",
           MINI_APP_API_URL="https://x.example/api", ADMIN_PANEL_PIN="1234", SUPPORT_CONTACT="@s", DOMAIN="x.example")
os.environ.update(env); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webapp_api as w
def init_data(uid):
    p = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "T"}), "query_id": "q"}
    dcs = "\n".join(f"{k}={p[k]}" for k in sorted(p)); sk = hmac.new(b"WebAppData", b"123:abc", hashlib.sha256).digest()
    p["hash"] = hmac.new(sk, dcs.encode(), hashlib.sha256).hexdigest(); return urllib.parse.urlencode(p)
c = w.app.test_client(); H = lambda u: {"X-Telegram-Init-Data": init_data(u)}
w._verify_admin_pin_token = lambda t, u: True      # the PIN second factor is covered by its own tests
conn = w.db(); cur = conn.cursor()
for u in (1, 50): cur.execute("INSERT OR REPLACE INTO users(user_id,first_name,balance) VALUES (?,?,0)", (u, "U%d" % u))
cur.execute("UPDATE users SET terms_accepted_at=?", (w._now(),)); conn.commit(); conn.close()
png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
assert "/api/promo/images" in {r.rule for r in w.app.url_map.iter_rules()}
# a normal player can read but not write
assert c.get("/api/promo/images", headers=H(50)).get_json()["items"] == {}
assert c.post("/api/admin/promo/sports_hero", headers=H(50), data={"photo": (io.BytesIO(png), "a.png")}).status_code == 403
assert c.delete("/api/admin/promo/sports_hero", headers=H(50)).status_code == 403
# admin uploads for the three kinds of slot; bad slot / bad file rejected
for slot in ("sports_hero", "casino_hero", "game_aviator"):
    r = c.post("/api/admin/promo/" + slot, headers=H(1), data={"photo": (io.BytesIO(png), "a.png")}); assert r.status_code == 200, (slot, r.data)
assert c.post("/api/admin/promo/evil", headers=H(1), data={"photo": (io.BytesIO(png), "a.png")}).status_code == 400
assert c.post("/api/admin/promo/..%2Fx", headers=H(1), data={"photo": (io.BytesIO(png), "a.png")}).status_code in (400, 404)
assert c.post("/api/admin/promo/sports_hero", headers=H(1), data={"photo": (io.BytesIO(b"GIF89a" + b"0" * 50), "a.gif")}).status_code == 400
items = c.get("/api/promo/images", headers=H(50)).get_json()["items"]; assert set(items) == {"sports_hero", "casino_hero", "game_aviator"}, items
img = c.get(items["sports_hero"]["image"]); assert img.status_code == 200 and img.mimetype == "image/png" and img.data == png
# replacing removes the old file; delete removes the row
before = set(os.listdir(w._PROMO_DIR)); c.post("/api/admin/promo/sports_hero", headers=H(1), data={"photo": (io.BytesIO(png + b"1"), "b.png")})
assert len(os.listdir(w._PROMO_DIR)) == len(before)
assert c.delete("/api/admin/promo/casino_hero", headers=H(1)).status_code == 200
assert "casino_hero" not in c.get("/api/promo/images", headers=H(50)).get_json()["items"]
assert c.get("/api/promo/casino_hero/image").status_code == 404
# stats
conn = w.db(); cur = conn.cursor(); from datetime import datetime, timedelta
for i, (st, po) in enumerate([(10, 38), (10, 0), (10, 19)]):
    day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d 12:00:00")
    cur.execute("INSERT INTO game_history(user_id,game_key,stake,payout,status,created_at) VALUES(50,'aviator',?,?,'X',?)", (st, po, day))
conn.commit(); conn.close()
s = c.get("/api/betpro/stats", headers=H(50)).get_json(); assert s["games_played"] == 3 and s["total_wins"] == 2 and s["day_streak"] == 3 and s["level"] == 1, s
print("BETPRO_TEST=PASS")
