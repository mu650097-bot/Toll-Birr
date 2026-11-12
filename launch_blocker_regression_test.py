"""Regression contracts for payment idempotency, escrow safety and launch blockers.

The SQLite races below exercise the same pending/status guards used by production
transactions. External Telegram/Chapa services are intentionally not contacted.
"""
import sqlite3, tempfile, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
api=(ROOT/'webapp_api.py').read_text(encoding='utf-8')
bot=(ROOT/'kdm_mini_app.py').read_text(encoding='utf-8')
rt=(ROOT/'realtime_engine_v3.py').read_text(encoding='utf-8')
js=(ROOT/'app.js').read_text(encoding='utf-8')

def need(ok, msg):
    if not ok: raise SystemExit('FAIL: '+msg)

need('p[\'status\'] != \'pending\'' in api and "p['credited_at'] and p['status']=='approved'" in api,
     'Chapa credit must be pending-only and idempotent')
need("verified_ref != tx_ref" in api and "credited_at IS NULL" in api,
     'Chapa verified reference/credit guard missing')
need('def reject_payment(payment_id):' in bot and 'BEGIN IMMEDIATE' in bot[bot.index('def reject_payment(payment_id):'):bot.index('# CLOSE AUCTION')],
     'bot payment rejection must serialize in an immediate transaction')
need('provider_verification_required' in bot[bot.index('def approve_payment(payment_id):'):bot.index('# CLOSE AUCTION')],
     'Chapa payments can still be manually approved by staff')
need("'timeout_refund'" in rt and "status='REFUNDED'" in rt and ('game_{key}_rt_refund' in rt or 'game_{gk}_rt_refund' in rt),
     'expired realtime rounds are still settled as losses instead of refunding the reserved stake')
need("old_input=json.loads(old['state_json'] or '{}').get('input',{})" in rt and 'pendingRoundStarts' in js and 'realtimeState(key)' in js,
     'lost /round/start or /action responses cannot recover the same round')
need('MAX_ROUND_PAYOUT_ETB' in api and 'MAX_ROUND_PAYOUT_ETB' in rt,
     'per-round maximum payout cap missing')
need('PRAGMA quick_check' in api, 'health endpoint still runs full integrity_check on every request')
need('def marketplace_confirm_receipt' in api and '/marketplace/confirm-receipt' in js,
     'buyer receipt confirmation flow missing')
need('ux_marketplace_reviews_tx' in api and 'COALESCE(delivered_at, created_at)' in api,
     'marketplace unique review / delivery-aware refund guards missing')
refund=api[api.index('def _auto_refund_stale_escrow'):api.index('def _marketplace_notification_worker')]
need('requests.post' not in refund and 'marketplace_notification_outbox' in refund,
     'marketplace refund sends Telegram while database transaction is open')
need('def _normalize_wheel_prizes' in api and "o['prizes']=[round(float(v)*scale,4) for v in _wheel_prizes()]" in rt,
     'wheel admin/animation payout values are not effective multipliers')
need("bucket=rng.randint(0,8)" in rt and "landing_slot=sum(path)" in rt,
     'Plinko path and payout bucket are not connected')
need("if key=='mines' and won:payout=max(float(r['stake']),payout)" in rt,
     'Mines WIN can pay less than stake')
need("elif payout<float(r['stake']):won=False" in rt and 'elif payout < stake:' in api,
     'a payout below the stake can still be recorded/announced as WON (all games)')
need('resultLine(' in js and '<pre>${escapeHtml(JSON.stringify(rr.outcome' not in js,
     'raw outcome JSON is shown to players or win message is not net of stake')
need('"WITHDRAW_TURNOVER_MULTIPLIER", "0"' in api and 'SEED_DEMO_MARKETPLACE' in api,
     'turnover default / demo marketplace seeding not production-safe')
need('MAX_ROUND_PAYOUT_ETB=100000' in (ROOT/'.env.example').read_text(), 'max payout cap missing from env template')
need('"MAX_ROUND_PAYOUT_ETB", "100000"' in api and 'max_stake REAL NOT NULL DEFAULT 500' in api, 'default payout cap / max stake are not bankroll-safe')
need('max_bonus REAL NOT NULL DEFAULT 1000.0' in api and 'WHERE id=1 AND max_bonus>=1000000000.0' in api, 'deposit bonus cap is unlimited by default')
need('WITHDRAW_TURNOVER_MULTIPLIER=0' in (ROOT/'.env.example').read_text(), 'env template turnover must be 0 (operator chose no play-through requirement)')
need('delay_hours REAL NOT NULL DEFAULT 6.0' in api and 'bonus_percent REAL NOT NULL DEFAULT 10.0' in api and 'min_deposit REAL NOT NULL DEFAULT 1.0' in api and "'deposit_bonus',now)" in api,
     'default deposit bonus is not 10% after 6 hours and credited to the ordinary withdrawable wallet')
need('def send_pending_withdrawal_reminders' in bot and 'pending_withdrawal_reminders' in bot and 'staff_reminded_at' in bot,
     'pending withdrawal staff reminder job missing')
need('random.randint(1, 15)' not in api and 'random.randint(1, 15)' not in bot,
     'Number game still uses non-cryptographic randint')

with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'race.sqlite'
    c=sqlite3.connect(path); c.executescript('''
      CREATE TABLE payments(id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT, credited_at TEXT);
      CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL NOT NULL);
      CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INTEGER,amount REAL,kind TEXT);
      INSERT INTO payments VALUES(1,7,100,'pending',NULL);
      INSERT INTO users VALUES(7,0);
      CREATE TABLE escrow(tx_id TEXT PRIMARY KEY,buyer_id INTEGER,creator_id INTEGER,amount REAL,status TEXT,delivered_at TEXT);
      CREATE TABLE reviews(tx_id TEXT UNIQUE, rating INTEGER);
      INSERT INTO escrow VALUES('x',7,8,50,'held_in_escrow','2026-01-01 00:00:00');
      INSERT INTO users VALUES(8,0);
    '''); c.commit(); c.close()
    barrier=threading.Barrier(2); results=[]
    def worker(kind):
        conn=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            barrier.wait(); conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT status,user_id,amount FROM payments WHERE id=1').fetchone()
            if row and row[0]=='pending':
                if kind=='approve':
                    changed=conn.execute("UPDATE payments SET status='approved',credited_at='now' WHERE id=1 AND status='pending' AND credited_at IS NULL").rowcount
                    if changed: conn.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(row[2],row[1])); conn.execute("INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)",(row[1],row[2],'deposit'))
                else:
                    changed=conn.execute("UPDATE payments SET status='rejected' WHERE id=1 AND status='pending'").rowcount
                results.append((kind,changed))
            conn.commit()
        finally: conn.close()
    ts=[threading.Thread(target=worker,args=(x,)) for x in ('approve','reject')]
    [t.start() for t in ts]; [t.join() for t in ts]
    c=sqlite3.connect(path)
    status=c.execute('SELECT status FROM payments WHERE id=1').fetchone()[0]
    balance=c.execute('SELECT balance FROM users WHERE user_id=7').fetchone()[0]
    ledger=c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    need(status in ('approved','rejected') and balance in (0,100) and ledger in (0,1), 'concurrent approve/reject double-processed payment')
    need((status=='approved' and balance==100 and ledger==1) or (status=='rejected' and balance==0 and ledger==0), 'payment status and wallet ledger diverged')
    # Exactly one review is permitted by the unique tx_id constraint.
    c.execute("INSERT INTO reviews VALUES('x',5)")
    try:
        c.execute("INSERT INTO reviews VALUES('x',4)")
        raise SystemExit('FAIL: duplicate marketplace review was accepted')
    except sqlite3.IntegrityError: pass
    c.close()

print('LAUNCH_BLOCKER_REGRESSION=PASS (Chapa idempotency; concurrent payment race; timeout refund; escrow; bonus; reminders; wheel/Plinko/Mines)')
