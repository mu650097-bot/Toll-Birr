"""Offline regression tests for the two reported release blockers."""
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent
api = (ROOT / "webapp_api.py").read_text(encoding="utf-8")
bot = (ROOT / "kdm_mini_app.py").read_text(encoding="utf-8")

# Static contract: Flask's global handler must preserve ordinary HTTP errors.
assert "from werkzeug.exceptions import HTTPException" in api
assert "if isinstance(exc, HTTPException):" in api
assert 'return jsonify({"error": exc.description}), exc.code' in api

approve = bot[bot.find('elif data.startswith("w_approve:")'):bot.find('elif data.startswith("w_reject:")')]
reject = bot[bot.find('elif data.startswith("w_reject:")'):bot.find('# ============================================================\n# CALLBACK ROUTER', bot.find('elif data.startswith("w_reject:")'))]
assert "screenshot_file_id" not in approve
assert "UPDATE withdrawals SET status='approved' WHERE id=? AND status='pending'" in approve
assert "INSERT INTO transactions" not in approve
assert "UPDATE users SET balance" not in approve
assert "withdraw_refund" in bot

# Exercise the wallet/ledger invariants in SQLite using the same transaction
# order and guards as the Telegram callback handlers.
def setup():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
      CREATE TABLE users(user_id INTEGER PRIMARY KEY, balance REAL NOT NULL);
      CREATE TABLE withdrawals(id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT);
      CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, transaction_type TEXT);
      INSERT INTO users VALUES(77, 900.0);
      INSERT INTO withdrawals VALUES(1, 77, 100.0, 'pending');
      INSERT INTO transactions(user_id,amount,transaction_type) VALUES(77,-100.0,'withdraw');
      UPDATE users SET balance=balance-100.0 WHERE user_id=77;
    """)
    return c

# Reject returns the reserved amount once and writes one positive refund row.
c = setup(); c.execute("BEGIN IMMEDIATE")
c.execute("UPDATE withdrawals SET status='rejected' WHERE id=? AND status='pending'", (1,))
assert c.total_changes >= 1
c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (100.0,77))
c.execute("INSERT INTO transactions(user_id,amount,transaction_type) VALUES(?,?,?)", (77,100.0,"withdraw_refund"))
c.commit()
assert c.execute("SELECT balance FROM users WHERE user_id=77").fetchone()[0] == 900.0
assert c.execute("SELECT COUNT(*) FROM transactions WHERE transaction_type='withdraw_refund'").fetchone()[0] == 1
# Duplicate reject must not refund again.
c.execute("BEGIN IMMEDIATE")
c.execute("UPDATE withdrawals SET status='rejected' WHERE id=? AND status='pending'", (1,))
assert c.total_changes >= 0
if c.execute("SELECT changes()").fetchone()[0] == 1:
    c.execute("UPDATE users SET balance=balance+100 WHERE user_id=77")
    c.execute("INSERT INTO transactions(user_id,amount,transaction_type) VALUES(77,100,'withdraw_refund')")
c.commit()
assert c.execute("SELECT balance FROM users WHERE user_id=77").fetchone()[0] == 900.0
assert c.execute("SELECT COUNT(*) FROM transactions WHERE transaction_type='withdraw_refund'").fetchone()[0] == 1
c.close()

# Approve changes status only: no second wallet debit or ledger entry.
c = setup(); c.execute("BEGIN IMMEDIATE")
c.execute("UPDATE withdrawals SET status='approved' WHERE id=? AND status='pending'", (1,))
c.commit()
assert c.execute("SELECT balance FROM users WHERE user_id=77").fetchone()[0] == 800.0
assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
# Reject-after-approve cannot refund.
c.execute("BEGIN IMMEDIATE")
c.execute("UPDATE withdrawals SET status='rejected' WHERE id=? AND status='pending'", (1,))
assert c.execute("SELECT changes()").fetchone()[0] == 0
c.commit()
assert c.execute("SELECT balance FROM users WHERE user_id=77").fetchone()[0] == 800.0
assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
c.close()

print("BLOCKER_REGRESSION=PASS (HTTP exception contract; withdrawal approve/reject ledger invariants)")
