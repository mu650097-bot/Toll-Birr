"""Aviator/Jet Auto Cash-out: executes the PRODUCTION rt_action/_finish/_settle code against an isolated SQLite DB."""
import ast, copy, datetime, hashlib, json, math, random, secrets, sqlite3, tempfile, time
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parent
rt_tree = ast.parse((ROOT / 'realtime_engine_v3.py').read_text(encoding='utf-8'))
api_tree = ast.parse((ROOT / 'webapp_api.py').read_text(encoding='utf-8'))
def nodes(tree, names, strip=False):
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            n = copy.deepcopy(n); n.decorator_list = []; out.append(n)
    assert {n.name for n in out} == set(names), names
    return out
body = nodes(api_tree, {'parse_money', '_cabinet_base_rtp', '_apply_cabinet_house_edge'}) + \
       nodes(rt_tree, {'_finish', 'rt_action', '_auto_target', '_crash_reached', '_settle_crashed_round', '_validated_realtime_input'})
ok = True
def check(name, cond, extra=''):
    global ok; ok &= bool(cond); print(('PASS ' if cond else 'FAIL ') + name, extra)

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'a.sqlite'
    c = sqlite3.connect(path); c.executescript('''
    CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL NOT NULL);
    CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount REAL,transaction_type TEXT,created_at TEXT);
    CREATE TABLE realtime_game_rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game_key TEXT,stake REAL,status TEXT,seed_commit TEXT,server_seed TEXT,crash_point REAL,started_at TEXT,finished_at TEXT,state_json TEXT,outcome_json TEXT);
    CREATE TABLE game_history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
    CREATE TABLE realtime_game_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,round_id INTEGER,user_id INTEGER,action TEXT,payload_json TEXT,created_at TEXT);
    INSERT INTO users(user_id,balance) VALUES(123,100000);''')
    try:
        c.execute('SELECT outcome_json FROM realtime_game_rounds LIMIT 1')
    except Exception: pass
    c.commit(); c.close()
    def db():
        x = sqlite3.connect(path, timeout=3); x.row_factory = sqlite3.Row; return x
    def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    env = {'db': db, 'g': SimpleNamespace(tg_user={'id': 123}), 'request': SimpleNamespace(get_json=lambda silent=True: {'action': 'cashout'}),
           'jsonify': lambda v: v, '_now': now, '_platform_record': lambda *a, **k: None, '_wheel_prizes': lambda: [0] * 10,
           'json': json, 'datetime': datetime.datetime, 'time': time, 'random': random, 'hashlib': hashlib, 'math': math, 'secrets': secrets,
           'REALTIME_ROUND_TIMEOUT_SEC': 120, 'MAX_ROUND_PAYOUT_ETB': 1350000.0, 'CABINET_GAME_KEYS': {'aviator', 'jet'},
           'ROAD_GAMES': ('chicken', 'rabbit'), 'ROAD_CFG': {}, 'CRASH_GAMES': ('aviator', 'jet'), '_eng': lambda k: k,
           'PLINKO_RISKS': (), 'PLINKO_ROWS': (), 'KENO_PAYTABLE': {}, 'KENO_BASE_RTP': .9}
    exec(compile(ast.Module(body=body, type_ignores=[]), '<prod>', 'exec'), env)
    valid = env['_validated_realtime_input']

    def new_round(key, crash, auto, elapsed):
        inp = {'stake': 100.0}
        if auto is not None: inp['auto_cashout'] = auto
        cl, err = valid(key, dict(inp)); assert not err, err
        started = (datetime.datetime.now() - datetime.timedelta(seconds=elapsed)).strftime('%Y-%m-%d %H:%M:%S')
        x = db(); q = x.cursor()
        q.execute('INSERT INTO realtime_game_rounds(user_id,game_key,stake,status,seed_commit,server_seed,crash_point,started_at,state_json) VALUES(?,?,?,?,?,?,?,?,?)',
                  (123, key, 100.0, 'ACTIVE', 'c', 'seed', crash, started, json.dumps({'house_edge': .05, 'input': cl})))
        rid = q.lastrowid; x.commit(); x.close(); return rid
    def row(rid):
        x = db(); r = x.execute('SELECT * FROM realtime_game_rounds WHERE id=?', (rid,)).fetchone(); x.close(); return r
    def balance():
        x = db(); b = x.execute('SELECT balance FROM users WHERE user_id=123').fetchone()[0]; x.close(); return b
    def act(key, rid):
        r = env['rt_action'](key, rid)
        return r if isinstance(r, tuple) else (r, 200)

    # curve: 100**(t/120). multiplier 2.0 at ~18.1s, 5.0 at ~41.9s.
    for key in ('aviator', 'jet'):
        b0 = balance()
        rid = new_round(key, 5.0, 2.0, 25)      # target crossed, crash not yet
        res, st = act(key, rid); check(f'{key}: cash-out after target pays exactly the target', st == 200 and res['status'] == 'WON' and abs(res['payout'] - 200.0) < 1e-6, str(res.get('payout')))
        rid = new_round(key, 5.0, 2.0, 60)      # whole round crashed before the player returned
        res, st = act(key, rid); check(f'{key}: auto target below crash is a WIN even if crash already passed', res['status'] == 'WON' and abs(res['payout'] - 200.0) < 1e-6, str(res))
        rid = new_round(key, 5.0, None, 60)
        res, st = act(key, rid); check(f'{key}: no auto + crashed = LOST (unchanged)', res['status'] == 'LOST' and res['payout'] == 0)
        rid = new_round(key, 5.0, 6.0, 60)
        res, st = act(key, rid); check(f'{key}: auto target above crash point is ignored (LOST)', res['status'] == 'LOST')
        rid = new_round(key, 5.0, 2.0, 10)      # cur ~1.47, target not reached: manual cash-out at the live multiplier
        res, st = act(key, rid); check(f'{key}: manual cash-out before target pays live multiplier', res['status'] == 'WON' and 1.3 < res['payout'] / 100 < 1.7, str(res.get('payout')))
        check(f'{key}: balance credited exactly once per win', abs(balance() - b0 - (200 + 200 + 0 + 0 + res['payout'])) < 0.02, str(balance() - b0))

    # server-side settlement without any client action (state poll / cleanup path)
    rid = new_round('aviator', 5.0, 2.0, 10); r = row(rid)
    check('not decided before target', not env['_crash_reached'](r))
    rid = new_round('aviator', 5.0, 2.0, 25); r = row(rid)
    check('decided once target crossed (crash not yet)', env['_crash_reached'](r))
    x = db(); q = x.cursor(); q.execute('BEGIN IMMEDIATE'); out = env['_settle_crashed_round'](q, row(rid)); x.commit(); x.close()
    r = row(rid); check('settle -> WON at the target', r['status'] == 'WON' and abs(out['payout'] - 200.0) < 1e-6 and out['auto_cashout'] == 2.0)
    res, st = act('aviator', rid); check('late client action on a server-settled win returns the win (no error)', st == 200 and res['won'] is True and abs(res['payout'] - 200.0) < 1e-6, str(res)[:80])
    rid = new_round('aviator', 5.0, None, 25)
    check('no auto: not decided before crash', not env['_crash_reached'](row(rid)))

    # validation
    for good in (1.01, 2, 100, 7.5):
        cl, err = valid('aviator', {'stake': 10, 'auto_cashout': good}); check(f'valid auto {good}', cl and cl['auto_cashout'] == round(float(good), 2), err or '')
    for bad in (1.0, 0, -3, 100.01, 'abc', True, float('nan'), None):
        cl, err = valid('jet', {'stake': 10, 'auto_cashout': bad})
        check(f'auto {bad!r} -> ' + ('accepted as empty' if bad is None else 'rejected'), (cl is not None and 'auto_cashout' not in cl) if bad is None else cl is None, err or '')

print('AUTO CASHOUT REGRESSION', 'PASS' if ok else 'FAIL'); raise SystemExit(0 if ok else 1)
