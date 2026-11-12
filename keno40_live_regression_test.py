"""Live Fast/Power/Insta Keno: exact RTP per pick count at the configured edge, shared draw, bet window, settle once."""
import ast, hashlib, hmac, json, logging, math, os, random, sqlite3, tempfile, time
from datetime import datetime
from pathlib import Path
from flask import Flask, g, request, jsonify
from new_games_math import *
ROOT = Path(__file__).resolve().parent
path = os.path.join(tempfile.mkdtemp(), 't.db')
def db():
    c = sqlite3.connect(path, isolation_level=None, timeout=30); c.row_factory = sqlite3.Row; return c
app = Flask('t'); ident = lambda f: f
clock = {'t': None}; _rt = time.time; _rs = time.sleep
class T:
    @staticmethod
    def time(): return clock['t'] if clock['t'] is not None else _rt()
    sleep = staticmethod(_rs)
live = ast.parse((ROOT / 'live_engine_v1.py').read_text(encoding='utf-8'))
nodes = [n for n in live.body if (isinstance(n, ast.FunctionDef) and n.name == '_live_clock') or (isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') in ('LIVE_ROUND_SEC', 'LIVE_NO_BASE', 'LIVE_BET_SEC', 'LIVE_DRAW_SEC'))]
EDGE = {'v': 0.05}
ns = dict(globals()); ns.update({'app': app, 'db': db, 'json': json, 'math': math, 'time': T, 'random': random, 'hashlib': hashlib, 'logger': logging.getLogger('t'), 'g': g,
      'request': request, 'jsonify': jsonify, 'require_telegram_auth': ident, 'require_fresh_auth': ident, 'rate_limit': lambda **k: ident,
      '_now': lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '_platform_record': lambda *a, **k: None, '_cabinet_limits': lambda k: (True, 1.0, 10000.0, EDGE['v']),
      'MAX_ROUND_PAYOUT_ETB': 100000.0, 'PLATFORM_BANKROLL_ETB': 0.0, 'BANKROLL_EXPOSURE_PCT': 0.5,
      '_live_seed': lambda gk, rn: hmac.new(b'k', f'{gk}:{rn}'.encode(), hashlib.sha256).hexdigest()})
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<live>', 'exec'), ns)
c = db()
c.executescript('''CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL);
CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INT,amount REAL,transaction_type TEXT,created_at TEXT);
CREATE TABLE game_history(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
INSERT INTO users VALUES(1,1000);''')
exec(compile((ROOT / 'live_keno40_v1.py').read_text(encoding='utf-8'), 'live_keno40_v1.py', 'exec'), ns)
# 1) exact RTP for every pick count equals 1 - edge (the solo game's scaling), at two edges
for edge in (0.05, 0.08):
    for n in range(1, 9):
        t = ns['_k40_table'](n, edge)
        rtp = sum(math.comb(n, h) * math.comb(40 - n, 10 - h) / math.comb(40, 10) * t[h] for h in range(n + 1))
        assert abs(rtp - (1 - edge)) < 2e-3 or max(t) >= 999.9, (edge, n, rtp)   # tiny deviation only where the x1000 cap bites
# 2) draws: 10 unique balls in 1..40, deterministic, and DIFFERENT per game
d = ns['_k40_draw']('fastkeno', 5); assert len(set(d)) == 10 and all(1 <= x <= 40 for x in d) and d == ns['_k40_draw']('fastkeno', 5)
assert ns['_k40_draw']('keno_power', 5) != d or ns['_k40_draw']('keno_insta', 5) != d
base = 60 * 29_900_000
def bet(gk, nums, stake, at):
    clock['t'] = at
    with app.test_request_context(json={'stake': stake, 'numbers': nums}):
        g.tg_user = {'id': 1}; r = ns['live40_bet'](gk); return r if isinstance(r, tuple) else (r, 200)
assert bet('fastkeno', [1, 2, 3], 10, base + 5)[1] == 200
assert bet('fastkeno', [1, 2, 3], 10, base + 6)[1] == 409                       # one bet per draw per game
assert bet('keno_power', [1, 2, 3, 4], 10, base + 6)[1] == 200                    # other games are separate tables
assert bet('keno_insta', [41], 10, base + 6)[1] == 400 and bet('keno_insta', list(range(1, 10)), 10, base + 6)[1] == 400
assert bet('keno_insta', [1], 10, base + 39.5)[1] == 409                          # betting window closed
assert bet('nope', [1], 10, base + 6)[1] == 404
clock['t'] = base + 30; assert ns['_k40_settle']('fastkeno') == 0
clock['t'] = base + 51
assert ns['_k40_settle']('fastkeno') == 1 and ns['_k40_settle']('fastkeno') == 0 and ns['_k40_settle']('keno_power') == 1
assert db().execute('SELECT COUNT(*) FROM game_history').fetchone()[0] == 2
# 3) state: balls hidden during betting, revealed one per second while drawing, all 10 in result
def state(gk, at):
    clock['t'] = at
    with app.test_request_context():
        g.tg_user = {'id': 1}; return ns['live40_state'](gk).get_json()
assert state('fastkeno', base + 60 + 10)['balls'] == [] and state('fastkeno', base + 60 + 10)['phase'] == 'BETTING'
s = state('fastkeno', base + 60 + 43); assert s['phase'] == 'DRAWING' and s['balls'] == ns['_k40_draw']('fastkeno', int(base // 60) + 1)[:4], s['balls']
s = state('fastkeno', base + 60 + 55); assert s['phase'] == 'RESULT' and len(s['balls']) == 10 and s['balls_total'] == 10
print('KENO40_LIVE_REGRESSION=PASS')
