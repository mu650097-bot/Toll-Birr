"""Classic Keno (1-10 of 80, 20 drawn): exact RTP through the production scaler + the production /action path."""
import ast, copy, datetime, hashlib, json, math, random, secrets, sqlite3, tempfile, time
from pathlib import Path
from types import SimpleNamespace
import keno_math as K
ROOT = Path(__file__).resolve().parent
rt_tree = ast.parse((ROOT / 'realtime_engine_v3.py').read_text(encoding='utf-8'))
api_tree = ast.parse((ROOT / 'webapp_api.py').read_text(encoding='utf-8'))
def nodes(tree, names):
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            n = copy.deepcopy(n); n.decorator_list = []; out.append(n)
    assert {n.name for n in out} == set(names), names
    return out
body = nodes(api_tree, {'parse_money', '_cabinet_base_rtp', '_apply_cabinet_house_edge'}) + \
       nodes(rt_tree, {'_finish', 'rt_action', '_auto_target', '_validated_realtime_input', 'integer_value'})
ok = True
def check(name, cond, extra=''):
    global ok; ok &= bool(cond); print(('PASS ' if cond else 'FAIL ') + name, extra)

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'k.sqlite'
    c = sqlite3.connect(path); c.executescript('''
    CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL NOT NULL);
    CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount REAL,transaction_type TEXT,created_at TEXT);
    CREATE TABLE realtime_game_rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game_key TEXT,stake REAL,status TEXT,seed_commit TEXT,server_seed TEXT,crash_point REAL,started_at TEXT,finished_at TEXT,state_json TEXT,outcome_json TEXT);
    CREATE TABLE game_history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
    CREATE TABLE realtime_game_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,round_id INTEGER,user_id INTEGER,action TEXT,payload_json TEXT,created_at TEXT);
    INSERT INTO users(user_id,balance) VALUES(123,100000000);''')
    c.commit(); c.close()
    def db():
        x = sqlite3.connect(path, timeout=3); x.row_factory = sqlite3.Row; return x
    def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    env = {'db': db, 'g': SimpleNamespace(tg_user={'id': 123}), 'request': SimpleNamespace(get_json=lambda silent=True: {'action': 'play'}),
           'jsonify': lambda v: v, '_now': now, '_platform_record': lambda *a, **k: None, '_wheel_prizes': lambda: [0] * 10,
           'json': json, 'datetime': datetime.datetime, 'time': time, 'random': random, 'hashlib': hashlib, 'math': math, 'secrets': secrets,
           'REALTIME_ROUND_TIMEOUT_SEC': 120, 'MAX_ROUND_PAYOUT_ETB': 1350000.0, 'CABINET_GAME_KEYS': {'keno'},
           'ROAD_GAMES': ('chicken', 'rabbit'), 'ROAD_CFG': {}, 'CRASH_GAMES': ('aviator', 'jet'), '_eng': lambda k: k,
           'PLINKO_RISKS': (), 'PLINKO_ROWS': (), 'KENO80_POOL': K.POOL, 'KENO80_DRAW': K.DRAW, 'KENO80_MAX_PICK': K.MAX_PICK,
           'keno80_nominal': K.nominal_table, 'KENO_PAYTABLE': {0: 0.0, 1: 0.5, 2: 1.0, 3: 3.5, 4: 30.0, 5: 120.0}, 'KENO_BASE_RTP': .9034765221878225}
    exec(compile(ast.Module(body=body, type_ignores=[]), '<prod>', 'exec'), env)
    valid = env['_validated_realtime_input']; scale = env['_apply_cabinet_house_edge']

    # 1) math + production scaler, exact
    for edge in (.03, .05, .08, .10):
        for n in range(1, 11):
            nom = K.nominal_table(n)
            check(f'pmf sums to 1 (n={n})', abs(sum(K.pmf(n, h) for h in range(n + 1)) - 1) < 1e-12) if edge == .03 else None
            exp = 0.0
            for h in range(n + 1):
                out = {'keno_mode': '80', 'multiplier': nom[h]}
                pay, _ = scale('keno', 10000.0, 10000.0 * nom[h], out, edge)
                exp += K.pmf(n, h) * pay / 10000.0
            check(f'RTP n={n} edge={edge}', abs(exp - (1 - edge)) < 0.002, f'got {exp:.5f}')
    for n in range(1, 11):
        t = K.nominal_table(n)
        check(f'cap + monotone n={n}', max(t) <= K.MAX_NOMINAL + 1e-9 and all(b >= a - 1e-12 for a, b in zip(t, t[1:])) and t[0] == 0)
    check('legacy keno base rtp unchanged', abs(env['_cabinet_base_rtp']('keno', {}) - .9034765221878225) < 1e-12)

    # 2) validation
    good, err = valid('keno', {'stake': 10, 'numbers': [1, 40, 80], 'grid': 80}); check('valid 3 of 80', good and good['grid'] == 80 and good['numbers'] == [1, 40, 80], err or '')
    good, err = valid('keno', {'stake': 10, 'numbers': list(range(1, 11)), 'grid': 80}); check('valid 10 of 80', good is not None, err or '')
    good, err = valid('keno', {'stake': 10, 'numbers': [1, 2, 3, 4, 5]}); check('legacy 5-of-20 still valid', good and 'grid' not in good, err or '')
    for bad in ({'numbers': [], 'grid': 80}, {'numbers': list(range(1, 12)), 'grid': 80}, {'numbers': [1, 1], 'grid': 80}, {'numbers': [0, 5], 'grid': 80},
                {'numbers': [81], 'grid': 80}, {'numbers': [1, 2], 'grid': 40}, {'numbers': [1, 2], 'grid': True}, {'numbers': 'x', 'grid': 80}, {'numbers': [1.5], 'grid': 80}):
        g, e = valid('keno', dict(bad, stake=10)); check(f'rejects {bad}', g is None, e or '')

    # 3) production /action: structure + statistical RTP
    def play(picks, i):
        cl, err = valid('keno', {'stake': 100.0, 'numbers': picks, 'grid': 80}); assert not err, err
        x = db(); q = x.cursor()
        q.execute('INSERT INTO realtime_game_rounds(user_id,game_key,stake,status,seed_commit,server_seed,crash_point,started_at,state_json) VALUES(?,?,?,?,?,?,?,?,?)',
                  (123, 'keno', 100.0, 'ACTIVE', 'c', f'seed-{i}-{len(picks)}', None, now(), json.dumps({'house_edge': .08, 'input': cl})))
        rid = q.lastrowid; x.commit(); x.close()
        r = env['rt_action']('keno', rid); return r[0] if isinstance(r, tuple) else r
    rngp = random.Random(5)
    for n in (1, 3, 5, 8, 10):
        N = 2500; tot = 0.0; eff = K.effective_table(n, .08); bad = 0
        for i in range(N):
            picks = rngp.sample(range(1, 81), n); res = play(picks, i)
            o = res['outcome']; d = o['draw']
            if not (len(d) == 20 and len(set(d)) == 20 and all(1 <= v <= 80 for v in d) and o['selected'] == sorted(picks) and o['hits'] == len(set(d) & set(picks))): bad += 1
            if abs(res['payout'] / 100.0 - eff[o['hits']]) > 0.0051: bad += 1
            tot += res['payout'] / 100.0
        rtp = tot / N; tol = {1: .12, 3: .15, 5: .30, 8: .45, 10: .60}[n]
        check(f'/action structure + payout table n={n}', bad == 0, f'bad={bad}')
        check(f'/action sampled RTP n={n}', abs(rtp - .92) < tol, f'observed={rtp:.3f}')

print('KENO REGRESSION', 'PASS' if ok else 'FAIL'); raise SystemExit(0 if ok else 1)
