"""Integration test: home banners + Shamo (run: python3 engagement_v8_test.py)."""
import os, sys, tempfile, json, time, hmac, hashlib, urllib.parse, io, sqlite3
d=tempfile.mkdtemp(); os.environ["DB_FILE"]=os.path.join(d,"t.db")
env=dict(BOT_TOKEN="123:abc",ADMIN_ID="1",ACCOUNT_NAME="a",CBE_ACCOUNT="1",BOA_ACCOUNT="1",TELEBIRR_NUMBER="1",
 MINI_APP_URL="https://x.example/",MINI_APP_API_URL="https://x.example/api",ADMIN_PANEL_PIN="1234",SUPPORT_CONTACT="@s",DOMAIN="x.example")
for k,v in env.items(): os.environ[k]=v
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); 
import webapp_api as w
_c=w.db(); _c.execute("UPDATE platform_settings SET value='0' WHERE key='welcome_bonus_enabled'"); _c.commit(); _c.close()   # these tests assume brand-new users start at exactly 0
print("routes:",sorted(r.rule for r in w.app.url_map.iter_rules() if "banner" in r.rule or "shamo" in r.rule))

def init_data(uid):
    pairs={"auth_date":str(int(time.time())),"user":json.dumps({"id":uid,"first_name":"T"}),"query_id":"q"}
    dcs="\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    sk=hmac.new(b"WebAppData",b"123:abc",hashlib.sha256).digest()
    pairs["hash"]=hmac.new(sk,dcs.encode(),hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs)
c=w.app.test_client()
H=lambda uid:{"X-Telegram-Init-Data":init_data(uid)}

conn=w.db(); cur=conn.cursor()
cur.execute("INSERT OR REPLACE INTO users(user_id,first_name,balance) VALUES (50,'U',0)")
cur.execute("INSERT OR REPLACE INTO users(user_id,first_name,balance) VALUES (51,'V',0)")
cur.execute("UPDATE users SET terms_accepted_at=?",(w._now(),))
conn.commit(); conn.close()

# ---- banners
png=b"\x89PNG\r\n\x1a\n"+b"0"*100
r=c.get("/api/banners",headers=H(50)); assert r.get_json()["items"]==[],r.data
# non-admin cannot add
r=c.post("/api/admin/banners",headers=H(50),data={"photo":(io.BytesIO(png),"a.png")}); assert r.status_code==403,r.status_code
# add 7 via helper, only newest 5 survive
for i in range(7): w.save_banner_bytes(png, "shamo" if i==6 else "", 3)
items=c.get("/api/banners",headers=H(50)).get_json()["items"]; assert len(items)==5,len(items)
assert items[0]["link_page"]=="shamo" and items[0]["seconds"]==3
img=c.get(items[0]["image"]); assert img.status_code==200 and img.mimetype=="image/png"
try: w.save_banner_bytes(b"GIF89a"+b"0"*50); raise SystemExit("bad image accepted")
except ValueError: pass
print("banners OK")

# ---- shamo
def set_settings(**kw):
    conn=w.db(); cur=conn.cursor()
    for k,v in kw.items(): cur.execute(f"UPDATE shamo_settings SET {k}=? WHERE id=1",(v,))
    conn.commit(); conn.close()
st=c.get("/api/shamo/status",headers=H(50)).get_json(); assert st["enabled"] is False
r=c.post("/api/shamo/pick",headers=H(50),json={"box":0}); assert r.status_code==409,(r.status_code,r.data)
now=w.datetime.now(w._ADDIS)
set_settings(enabled=1,open_hour=now.hour,open_minute=0,window_minutes=120,require_deposit=1,
             prizes_json=json.dumps([[10,1]]),daily_budget=20)
st=c.get("/api/shamo/status",headers=H(50)).get_json(); assert st["is_open"] and st["seconds_to_close"]>0,st
r=c.post("/api/shamo/pick",headers=H(50),json={"box":0}); assert r.status_code==403,(r.status_code,r.data)  # no deposit yet
conn=w.db(); cur=conn.cursor()
for u in (50,51): cur.execute("INSERT INTO payments(user_id,first_name,amount,status,created_at) VALUES (?,?,?,?,?)",(u,'x',100,'approved',w._now()))
conn.commit(); conn.close()
assert c.post("/api/shamo/pick",headers=H(50),json={"box":99}).status_code==400
r=c.post("/api/shamo/pick",headers=H(50),json={"box":3}); assert r.status_code==200 and r.get_json()["prize"]==10,r.data
assert c.post("/api/shamo/pick",headers=H(50),json={"box":4}).status_code==409          # one pick per day
bal=lambda u:w.db().execute("SELECT balance FROM users WHERE user_id=?",(u,)).fetchone()[0]
assert bal(50)==10
st=c.get("/api/shamo/status",headers=H(50)).get_json(); assert st["picked"]=={"box":3,"prize":10.0},st
conn=w.db(); cur=conn.cursor()
for u in range(60,63):
    cur.execute("INSERT OR REPLACE INTO users(user_id,first_name,balance) VALUES (?, 'z',0)",(u,))
    cur.execute("INSERT INTO payments(user_id,first_name,amount,status,created_at) VALUES (?,?,?,?,?)",(u,'x',100,'approved',w._now()))
cur.execute("UPDATE users SET terms_accepted_at=?",(w._now(),))
conn.commit(); conn.close()
prizes=[c.post("/api/shamo/pick",headers=H(u),json={"box":0}).get_json()["prize"] for u in (51,60,61,62)]
print("prizes after budget 20:",prizes); assert sum(prizes)+10<=20,prizes   # budget cap respected
# closed window
set_settings(open_hour=(now.hour+5)%24)
assert c.get("/api/shamo/status",headers=H(50)).get_json()["is_open"] is False
print("shamo OK")
