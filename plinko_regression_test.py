"""Plinko Risk/Rows: exact RTP through the production scaler + production input validation."""
import ast, math, random, secrets, json
from pathlib import Path
import plinko_math as P

ROOT = Path(__file__).resolve().parent
def grab(file, names):
    tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]

ns = {'math': math, 'random': random, 'secrets': secrets, 'json': json, 'MAX_ROUND_PAYOUT_ETB': 1350000.0,
      'PLINKO_RISKS': P.RISKS, 'PLINKO_ROWS': P.ROWS, 'FASTKENO_PICK': 5, 'FASTKENO_POOL': 37, 'ROAD_GAMES': set(), 'ROAD_CFG': {}}
exec(compile(ast.Module(body=grab('webapp_api.py', {'parse_money', '_cabinet_base_rtp', '_apply_cabinet_house_edge'}), type_ignores=[]), 'w', 'exec'), ns)
exec(compile(ast.Module(body=grab('realtime_engine_v3.py', {'_validated_realtime_input'}), type_ignores=[]), 'r', 'exec'), ns)

ok = True
def check(name, cond, extra=''):
    global ok
    ok &= bool(cond); print(('PASS ' if cond else 'FAIL ') + name, extra)

# 1) exact RTP for every risk/rows/edge using the production scaler (payout of stake 100 per bucket)
for edge in (.03, .05, .08, .10):
    for risk in P.RISKS:
        for rows in P.ROWS:
            nom = P.nominal_table(risk, rows); pr = P.probs(rows)
            check(f'probs sum {risk}/{rows}', abs(sum(pr) - 1) < 1e-12)
            check(f'symmetric {risk}/{rows}', all(abs(nom[k] - nom[rows - k]) < 1e-12 for k in range(rows + 1)))
            exp = 0.0
            for k in range(rows + 1):
                out = {'plinko_mode': 'binomial', 'risk': risk, 'rows': rows, 'multiplier': nom[k]}
                pay, _ = ns['_apply_cabinet_house_edge']('plinko', 100.0, 100.0 * nom[k], out, edge)
                exp += pr[k] * pay / 100.0
            # payouts are rounded to cents by the production scaler -> tiny tolerance
            check(f'RTP {risk}/{rows} edge={edge}', abs(exp - (1 - edge)) < 0.002, f'got {exp:.5f}')
            check(f'effective_table matches {risk}/{rows}', abs(P.expected_rtp(P.effective_table(risk, rows, edge), rows) - (1 - edge)) < 0.002)

# 2) legacy board unchanged
leg = ns['_cabinet_base_rtp']('plinko', {})
check('legacy plinko base rtp unchanged', abs(leg - sum([0, .5, .8, 1, 1.2, 1.5, 2, 3, 5]) / 9) < 1e-12)

# 3) production validation
V = ns['_validated_realtime_input']
good, err = V('plinko', {'stake': 10, 'risk': 'high', 'rows': 16}); check('valid high/16', good and good['risk'] == 'high' and good['rows'] == 16, err or '')
good, err = V('plinko', {'stake': 10, 'risk': 'low'}); check('rows default 12', good and good['rows'] == 12, err or '')
good, err = V('plinko', {'stake': 10, 'rows': 8}); check('risk default med', good and good['risk'] == 'med', err or '')
good, err = V('plinko', {'stake': 10}); check('legacy body still valid and has no risk', good and 'risk' not in good, err or '')
for bad in ({'risk': 'extreme', 'rows': 12}, {'risk': 'low', 'rows': 10}, {'risk': 'low', 'rows': 12.5}, {'risk': 'low', 'rows': True}, {'risk': 'low', 'rows': 12, 'x': 1}):
    g, e = V('plinko', dict(bad, stake=10)); check(f'rejects {bad}', g is None, e or '')

print('PLINKO REGRESSION', 'PASS' if ok else 'FAIL'); raise SystemExit(0 if ok else 1)
