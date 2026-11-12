"""Live Number Game: fixed odds RTP, one global round clock, settlement, bet window, no double settle."""
import ast, hashlib, hmac, json, math, os, sqlite3, tempfile, time, logging
from datetime import datetime
from pathlib import Path
from flask import Flask, g
ROOT = Path(__file__).resolve().parent
path = os.path.join(tempfile.mkdtemp(), 't.db')
def db():
    c = sqlite3.connect(path, isolation_level=None, timeout=30); c.row_factory = sqlite3.Row; return c
fmt = '%Y-%m-%d %H:%M:%S'
app = Flask('t'); ident = lambda f: f
clock = {'t': None}
real_time = time.time
class T:  # patched time module
    @staticmethod
    def time(): return clock['t'] if clock['t'] is not None else real_time()
    sleep = staticmethod(__import__('time').sleep)
live_src = ast.parse((ROOT / 'live_engine_v1.py').read_text(encoding='utf-8'))
want = {'_live_clock'}
nodes = [n for n in live_src.body if isinstance(n, ast.FunctionDef) and n.name in want] + \
        [n for n in live_src.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') in ('LIVE_ROUND_SEC', 'LIVE_BET_SEC', 'LIVE_DRAW_SEC', 'LIVE_NO_BASE')]
ns = {'app': app, 'db': db, 'json': json, 'math': math, 'hashlib': hashlib, 'time': T, 'logger': logging.getLogger('t'), 'g': g,
      'request': __import__('flask').request, 'jsonify': __import__('flask').jsonify,
      'require_telegram_auth': ident, 'require_fresh_auth': ident, 'rate_limit': lambda **k: ident,
      '_now': lambda: datetime.now().strftime(fmt), '_platform_record': lambda *a, **k: None,
      '_cabinet_limits': lambda k: (True, 1.0, 10000.0, 0.05), '_get_game_setting': lambda k: {'enabled': True},
      'MAX_ROUND_PAYOUT_ETB': 100000.0, 'PLATFORM_BANKROLL_ETB': 0.0, 'BANKROLL_EXPOSURE_PCT': 0.5,
      '_live_seed': lambda gk, rn: hmac.new(b'k', f'{gk}:{rn}'.encode(), hashlib.sha256).hexdigest()}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<live>', 'exec'), ns)
c = db()
c.executescript('''CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL);
CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INT,amount REAL,transaction_type TEXT,created_at TEXT);
CREATE TABLE game_history(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
INSERT INTO users VALUES(1,1000);''')
exec(compile((ROOT / 'live_number_v1.py').read_text(encoding='utf-8'), 'live_number_v1.py', 'exec'), ns)

# 1) fixed odds: x3.8 / x1.9 and exact 95% RTP for every option over the 4 equally likely draws
m = ns['_nm_mults'](0.05)
assert m['1'] == m['4'] == 3.8 and m['odd'] == m['even'] == m['high'] == 1.9, m
for sel, mult in m.items():
    rtp = sum(mult for n in (1, 2, 3, 4) if ns['_nm_hit'](sel, n)) / 4
    assert abs(rtp - 0.95) < 1e-9, (sel, rtp)
# 2) draw is deterministic per round and always 1..4; all four numbers appear
draws = {ns['_nm_draw'](r) for r in range(1000, 1200)}
assert draws == {1, 2, 3, 4} and ns['_nm_draw'](1234) == ns['_nm_draw'](1234)

def bet(sel, stake, at):
    clock['t'] = at
    with app.test_request_context(json={'sel': sel, 'stake': stake}):
        g.tg_user = {'id': 1, 'first_name': 'A'}
        r = ns['live_number_bet']()
        return r if isinstance(r, tuple) else (r, 200)
base = 60 * 29_900_000   # start of a round
# 3) bet accepted at second 10, rejected after second 49 (window closed), duplicate selection rejected
r, code = bet('1', 10, base + 10); assert code == 200, r.get_json()
r, code = bet('1', 10, base + 12); assert code == 409
r, code = bet('odd', 10, base + 49.5); assert code == 409 and r.get_json()['code'] == 'CLOSED'
r, code = bet('zz', 10, base + 12); assert code == 400
r, code = bet('even', 0.1, base + 12); assert code == 400
bet('2', 10, base + 20); bet('high', 10, base + 20)
bal = db().execute('SELECT balance FROM users').fetchone()[0]; assert abs(bal - 970) < 1e-9, bal
# 4) nothing is settled before the reveal (second 50); everything after, exactly once
clock['t'] = base + 30; assert ns['_nm_settle']() == 0
clock['t'] = base + 51; assert ns['_nm_settle']() == 3
assert ns['_nm_settle']() == 0, 'double settle'
n = ns['_nm_draw'](int(base // 60)); exp = sum(10 * m[s] for s in ('1', '2', 'high') if ns['_nm_hit'](s, n))
bal = db().execute('SELECT balance FROM users').fetchone()[0]; assert abs(bal - (970 + exp)) < 1e-6, (bal, exp, n)
assert db().execute('SELECT COUNT(*) FROM game_history').fetchone()[0] == 3
# 5) state endpoint: result hidden during betting, shown after reveal, history never leaks the current draw while betting
def state(at):
    clock['t'] = at
    with app.test_request_context():
        g.tg_user = {'id': 1}; return ns['live_number_state']().get_json()
s1 = state(base + 60 + 5); assert s1['phase'] == 'BETTING' and s1['result'] is None
cur = int(base // 60) + 1
assert all(h['round_no'] != cur - 29_897_000 for h in s1['history'])
s2 = state(base + 60 + 55); assert s2['phase'] == 'RESULT' and s2['result'] in (1, 2, 3, 4) and s2['history'][0]['draw'] == s2['result']
print('NUMBER_LIVE_REGRESSION=PASS')
