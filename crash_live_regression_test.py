"""Live Crash engine for jet / crash (shared 60 s flight): registered keys, exact-ish RTP at any auto cash-out, settlement once."""
import ast, hashlib, hmac, json, logging, math, os, sqlite3, tempfile, time
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent
tree = ast.parse((ROOT / 'live_engine_v1.py').read_text(encoding='utf-8'))
keys = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'LIVE_CRASH_KEYS')
assert 'jet' in keys and 'crash' in keys and 'highflyer' in keys and 'skymasters' in keys, keys
want = {'_live_clock', '_cr_point', '_cr_floor2', '_cr_phase', '_cr_credit', '_live_settle_crash'}
consts = {'LIVE_ROUND_SEC', 'LIVE_BET_SEC', 'LIVE_DRAW_SEC', 'LIVE_NO_BASE', 'CR_BET_SEC', 'CR_MAX', 'CR_K'}
nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in want) or (isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') in consts)]
path = os.path.join(tempfile.mkdtemp(), 't.db')
def db():
    c = sqlite3.connect(path, isolation_level=None, timeout=30); c.row_factory = sqlite3.Row; return c
clock = {'t': None}
class T:
    @staticmethod
    def time(): return clock['t'] if clock['t'] is not None else time.time()
ns = {'db': db, 'json': json, 'math': math, 'time': T, 'logger': logging.getLogger('t'), '_now': lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      '_platform_record': lambda *a, **k: None, '_cabinet_limits': lambda k: (True, 1.0, 10000.0, 0.05), 'MAX_ROUND_PAYOUT_ETB': 100000.0,
      '_live_seed': lambda gk, rn: hmac.new(b'k', f'{gk}:{rn}'.encode(), hashlib.sha256).hexdigest()}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<live>', 'exec'), ns)
for gk in ('jet', 'crash'):
    for auto in (1.5, 2.0, 5.0, 10.0):                      # RTP of "always auto cash-out at x": P(crash>=x) * x  ~ 0.95
        N = 40000; ret = sum(auto for rn in range(N) if auto <= ns['_cr_floor2'](ns['_cr_point'](gk, rn, 0.05)))
        rtp = ret / N; assert abs(rtp - 0.95) < 0.04, (gk, auto, rtp)
c = db()
c.executescript('''CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL);
CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INT,amount REAL,transaction_type TEXT,created_at TEXT);
CREATE TABLE game_history(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
CREATE TABLE live_crash_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, game_key TEXT NOT NULL, round_no INTEGER NOT NULL, user_id INTEGER NOT NULL, slot TEXT NOT NULL, stake REAL NOT NULL, auto REAL,
  status TEXT NOT NULL DEFAULT 'PENDING', mult REAL, payout REAL, created_at TEXT NOT NULL, settled_at TEXT);
INSERT INTO users VALUES(1,0);''')
# find one past round that crashes high (auto 1.01 wins) and one that crashes at the minimum (auto 50 loses)
base = 29_900_000
hi = next(rn for rn in range(base, base + 5000) if ns['_cr_floor2'](ns['_cr_point']('jet', rn, 0.05)) >= 3.0)
hic = next(rn for rn in range(base, base + 5000) if ns['_cr_floor2'](ns['_cr_point']('crash', rn, 0.05)) >= 3.0)
lo = next(rn for rn in range(base, base + 5000) if ns['_cr_floor2'](ns['_cr_point']('jet', rn, 0.05)) < 1.5)
for rn, auto, slot in ((hi, 2.0, 'A'), (lo, 2.0, 'A'), (hi, None, 'B')):
    c.execute("INSERT INTO live_crash_bets(game_key,round_no,user_id,slot,stake,auto,created_at) VALUES('jet',?,1,?,10,?,'x')", (rn, slot, auto))
c.execute("INSERT INTO live_crash_bets(game_key,round_no,user_id,slot,stake,auto,created_at) VALUES('crash',?,1,'A',10,2.0,'x')", (hic,))
clock['t'] = (max(hi, lo, hic) + 3) * 60 + 59                      # all those rounds are over
assert ns['_live_settle_crash']('jet') == 3 and ns['_live_settle_crash']('jet') == 0, 'settle once'
assert ns['_live_settle_crash']('crash') == 1
st = {(r['game_key'], r['round_no'], r['slot']): r['status'] for r in db().execute('SELECT * FROM live_crash_bets')}
assert st[('jet', hi, 'A')] == 'WON' and st[('jet', lo, 'A')] == 'LOST' and st[('jet', hi, 'B')] == 'LOST' and st[('crash', hic, 'A')] == 'WON', st
assert abs(db().execute('SELECT balance FROM users').fetchone()[0] - 40.0) < 1e-9          # two wins x2.0 on 10 ETB
assert db().execute("SELECT COUNT(*) FROM game_history WHERE game_key IN ('jet','crash')").fetchone()[0] == 4
print('CRASH_LIVE_REGRESSION=PASS')
