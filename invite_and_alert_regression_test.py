import os, sqlite3, tempfile, importlib
os.environ.setdefault("DISABLE_COST_ALERT_WORKER", "1")
import bonus_wallet as bw, platform_controls as pc

conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row; cur = conn.cursor()
cur.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, bonus_locked REAL DEFAULT 0, first_name TEXT, referred_by INTEGER)")
cur.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INT,amount REAL,transaction_type TEXT,payment_id INT,created_at TEXT)")
cur.execute("CREATE TABLE invite_bonuses (invitee_id INTEGER PRIMARY KEY, inviter_id INTEGER NOT NULL, amount REAL NOT NULL, created_at TEXT NOT NULL)")
cur.execute("INSERT INTO invite_bonuses VALUES(900,1,1,'2020-01-01 00:00:00')")           # legacy row (paid at the time)
for u in (1, 2, 3, 4): cur.execute("INSERT INTO users(user_id) VALUES(?)", (u,))
pc.init_platform_controls(conn)
assert cur.execute("SELECT paid_at FROM invite_bonuses WHERE invitee_id=900").fetchone()[0] == "2020-01-01 00:00:00", "legacy rows must be marked paid"
pc.init_platform_controls(conn)                                                           # idempotent
now = "2026-01-01 00:00:00"

# default: deferred
assert bw.invite_requires_deposit(cur) is True
assert bw.record_invite(cur, 1, 2, now) is True
assert cur.execute("SELECT balance FROM users WHERE user_id=1").fetchone()[0] == 0, "inviter must NOT be paid at signup"
assert cur.execute("SELECT paid_at FROM invite_bonuses WHERE invitee_id=2").fetchone()[0] is None
assert bw.record_invite(cur, 1, 2, now) is False, "same invitee counted once"
assert bw.record_invite(cur, 3, 3, now) is False, "self invite refused"
assert bw.release_invite_bonus(cur, 2, 5, now) is None, "deposit below minimum does not release"
assert bw.release_invite_bonus(cur, 2, 50, now) == (1, 1.0)
r = cur.execute("SELECT balance,bonus_locked FROM users WHERE user_id=1").fetchone(); assert (r[0], r[1]) == (1.0, 1.0)
assert bw.release_invite_bonus(cur, 2, 50, now) is None, "paid exactly once"
assert cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id=1 AND transaction_type='invite_bonus'").fetchone()[0] == 1

# immediate mode still works
pc.save_settings(cur, pc.validate_update({"invite_bonus_requires_deposit": False}, 0.3))
assert bw.record_invite(cur, 1, 3, now) is True
assert cur.execute("SELECT balance FROM users WHERE user_id=1").fetchone()[0] == 2.0
assert cur.execute("SELECT paid_at FROM invite_bonuses WHERE invitee_id=3").fetchone()[0] == now
assert bw.release_invite_bonus(cur, 3, 50, now) is None

# alert settings validate
v = pc.validate_update({"cost_alert_bonus_pct": 40, "cost_alert_window_days": 14, "cost_alert_min_bonus": 50, "cost_alert_enabled": True}, 0.3)
pc.save_settings(cur, v); c = pc.get_controls(cur)
assert c["cost_alert_bonus_pct"] == 40 and c["cost_alert_window_days"] == 14 and c["cost_alert_min_bonus"] == 50
for bad in ({"cost_alert_window_days": 0}, {"cost_alert_bonus_pct": 0}, {"invite_bonus_min_deposit": -1}):
    try: pc.validate_update(bad, 0.3); raise SystemExit("FAIL accepted " + str(bad))
    except ValueError: pass
print("INVITE_AND_ALERT_CORE=PASS")
