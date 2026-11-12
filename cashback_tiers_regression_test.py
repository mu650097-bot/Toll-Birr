import sqlite3, platform_controls as pc
conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row; cur = conn.cursor()
cur.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, bonus_locked REAL DEFAULT 0, first_name TEXT)")
cur.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INT,amount REAL,transaction_type TEXT,payment_id INT,created_at TEXT)")
for u in (1, 2, 3, 4): cur.execute("INSERT INTO users(user_id) VALUES(?)", (u,))
pc.init_platform_controls(conn)
def play(u, staked, returned):
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (u, -staked, "game_dice_stake", pc._now()))
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (u, returned, "game_dice_payout", pc._now()))
play(1, 500, 0)        # below Silver -> nothing
play(2, 2000, 1000)    # Silver 5% of 1000 = 50
play(3, 6000, 3000)    # Gold 8% of 3000 = 240
play(4, 30000, 10000)  # Platinum 12% of 20000 = 2400 -> capped by max_per_player
conn.commit()
c = pc.get_controls(cur); assert c["cashback_tiers_enabled"] is False and len(c["cashback_tiers"]) == 3
v = pc.validate_update({"cashback_enabled": True, "cashback_tiers_enabled": True, "cashback_mode": "percent_loss", "cashback_max_per_player": 1000}, 0.3)
pc.save_settings(cur, v); conn.commit()
c = pc.get_controls(cur)
res = {i["user_id"]: i for i in pc.cashback_candidates(cur, c, "2000-01-01 00:00:00", "2999-01-01 00:00:00")}
assert 1 not in res, res
assert res[2]["cashback"] == 50 and res[2]["tier"] == "Silver", res[2]
assert res[3]["cashback"] == 240 and res[3]["tier"] == "Gold", res[3]
assert res[4]["cashback"] == 1000 and res[4]["tier"] == "Platinum", res[4]   # cap keeps cost bounded
for bad in ([], [{"name": "x", "min_wager": -1, "percent": 5}], [{"name": "x", "min_wager": 5, "percent": 150}],
            [{"name": "a", "min_wager": 5, "percent": 1}, {"name": "b", "min_wager": 5, "percent": 2}]):
    try: pc.validate_update({"cashback_tiers": bad}, 0.3); raise SystemExit("FAIL: accepted " + str(bad))
    except ValueError: pass
v = pc.validate_update({"cashback_tiers": [{"name": "Gold", "min_wager": 100, "percent": 9}, {"name": "VIP", "min_wager": 10, "percent": 4}]}, 0.3)
pc.save_settings(cur, v); conn.commit()
assert [t["name"] for t in pc.get_controls(cur)["cashback_tiers"]] == ["VIP", "Gold"]   # sorted
v = pc.validate_update({"cashback_tiers_enabled": False}, 0.3); pc.save_settings(cur, v)
c = pc.get_controls(cur); assert pc.cashback_amount(c, 2000, 1000) == 100.0   # flat 10% again when tiers are off
print("CASHBACK_TIERS_REGRESSION=PASS")
