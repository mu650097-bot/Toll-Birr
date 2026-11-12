"""Live shared rounds: Aviator, Rocket and classic Keno must run on the same global 60 s clock, settle idempotently and keep the RTP maths."""
import os, sys, time, json, math, sqlite3, tempfile, hashlib, random, secrets, logging
from pathlib import Path
from datetime import datetime
ROOT = Path(__file__).resolve().parent; sys.path.insert(0, str(ROOT))
import keno_math
from flask import Flask
path = os.path.join(tempfile.mkdtemp(), 't.db')
def db():
    c = sqlite3.connect(path, isolation_level=None, timeout=20); c.row_factory = sqlite3.Row; return c
c = db(); c.executescript('''CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL);
CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INT,amount REAL,transaction_type TEXT,created_at TEXT);
CREATE TABLE game_history(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
CREATE TABLE cabinet_game_settings(game_key TEXT PRIMARY KEY,house_edge REAL,wheel_prizes TEXT,updated_at TEXT);
INSERT INTO users VALUES(1,0);'''); c.close()
ident = lambda f: f
ns = {'__name__': 'live_test', 'os': os, 'time': time, 'json': json, 'math': math, 'hashlib': hashlib, 'random': random, 'secrets': secrets, 'logger': logging.getLogger('t'),
      'db': db, 'app': Flask('t'), 'require_telegram_auth': ident, 'require_fresh_auth': ident, 'rate_limit': lambda **k: ident, 'keno_math': keno_math,
      '_cabinet_limits': lambda k: (True, 1.0, 10000.0, 0.05), '_platform_record': lambda *a, **k: None, 'MAX_ROUND_PAYOUT_ETB': 1350000.0, 'PLATFORM_BANKROLL_ETB': 0, 'BANKROLL_EXPOSURE_PCT': 0.2,
      '_now': lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'g': None, 'request': None, 'jsonify': dict}
os.environ['LIVE_ROUNDS_SECRET'] = 'test-secret'
exec(compile((ROOT / 'live_engine_v1.py').read_text(encoding='utf-8'), 'live_engine_v1.py', 'exec'), ns)
assert 'aviator' in ns['LIVE_CRASH_KEYS'] and 'rocket' in ns['LIVE_CRASH_KEYS'] and 'keno' in ns['LIVE_KENO_KEYS']
now_no = ns['_live_clock']()[0]
# every game has its own deterministic draw per round, identical for all players
assert ns['_live_keno_draw']('keno', now_no - 3) == ns['_live_keno_draw']('keno', now_no - 3)
assert len(set(ns['_live_keno_draw']('keno', now_no - 3))) == 20
assert ns['_cr_point']('aviator', now_no - 3, 0.05) != ns['_cr_point']('rocket', now_no - 3, 0.05)
# crash RTP over many rounds for a fixed cash-out target = 1-edge (house edge 5%)
for gk in ('aviator', 'rocket'):
    N = 40000; tgt = 2.0; w = sum(1 for r in range(N) if ns['_cr_floor2'](ns['_cr_point'](gk, r, 0.05)) >= tgt)
    rtp = w * tgt / N; assert 0.92 < rtp < 0.98, (gk, rtp)
# settle a past Keno bet + a past Aviator bet + a past Rocket bet, twice (idempotent)
c = db(); old = now_no - 5
picks = ns['_live_keno_draw']('keno', old)[:3]
c.execute("INSERT INTO live_bets(game_key,round_no,user_id,stake,picks_json,created_at) VALUES('keno',?,1,10,?,'x')", (old, json.dumps(sorted(picks))))
for gk in ('aviator', 'rocket'):
    c.execute("INSERT INTO live_crash_bets(game_key,round_no,user_id,slot,stake,auto,created_at) VALUES(?,?,1,'A',10,1.01,'x')", (gk, old))
c.close()
for _ in range(2):
    ns['_live_settle_keno']('keno'); ns['_live_settle_crash']('aviator'); ns['_live_settle_crash']('rocket')
c = db(); n = c.execute("SELECT COUNT(*) FROM game_history").fetchone()[0]; assert n == 3, n
assert c.execute("SELECT COUNT(*) FROM live_bets WHERE status='PENDING'").fetchone()[0] == 0
assert c.execute("SELECT COUNT(*) FROM live_crash_bets WHERE status='PENDING'").fetchone()[0] == 0
c.close()
# --- Number Game: 4 numbers x3.8, odd/even/low/high x1.9, same draw for everybody, RTP = 95 %, idempotent settlement
nn = ns['_num_clock']()[0]
assert {t: round(ns['_num_mult'](t, 0.05), 2) for t in ns['NUM_TARGETS']} == {'1': 3.8, '2': 3.8, '3': 3.8, '4': 3.8, 'odd': 1.9, 'even': 1.9, 'low': 1.9, 'high': 1.9}
cnt = {1: 0, 2: 0, 3: 0, 4: 0}
for r in range(40000): cnt[ns['_num_secret_number'](r)] += 1
assert all(9300 < v < 10700 for v in cnt.values()), cnt
for t in ns['NUM_TARGETS']:
    w = sum(1 for r in range(40000) if ns['_num_wins'](t, ns['_num_secret_number'](r)))
    assert 0.92 < w / 40000 * ns["_num_mult"](t, 0.05) < 0.98, (t, w)
old = nn - 3; d = ns['_num_secret_number'](old)
c = db()
for t in ('1', '2', '3', '4', 'odd', 'even', 'low', 'high'):
    c.execute("INSERT INTO live_number_bets(round_no,user_id,target,stake,created_at) VALUES(?,1,?,10,'x')", (old, t))
bal0 = c.execute('SELECT balance FROM users WHERE user_id=1').fetchone()[0]; c.close()
for _ in range(2): ns['_live_settle_number']()
c = db(); won = c.execute("SELECT COUNT(*),COALESCE(SUM(payout),0) FROM live_number_bets WHERE status='WON'").fetchone()
assert won[0] == 3 and abs(won[1] - (38 + 19 * 2)) < 0.01, tuple(won)      # exactly one number + one parity + one low/high win
assert c.execute("SELECT COUNT(*) FROM live_number_bets WHERE status='PENDING'").fetchone()[0] == 0
assert abs(c.execute('SELECT balance FROM users WHERE user_id=1').fetchone()[0] - bal0 - won[1]) < 0.01
c.close(); print('LIVE_ENGINE_TEST=PASS')
