"""Crash live-wins feed: only REAL winning rounds (payout > stake), newest first, masked ids, max 8, crash games only."""
import ast, json, sqlite3, os, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
tree = ast.parse((ROOT / 'realtime_engine_v3.py').read_text(encoding='utf-8'))
fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'crash_live_wins']
assert fn, 'crash_live_wins missing'
fn[0].decorator_list = []
path = os.path.join(tempfile.mkdtemp(), 't.db')
def db():
    c = sqlite3.connect(path); c.row_factory = sqlite3.Row; return c
jsonify = lambda d, code=200: (d, code) if code != 200 else (d, 200)
ns = {'db': db, 'jsonify': jsonify, 'CRASH_GAMES': ('aviator', 'jet'), '_eng': lambda k: {'highflyer': 'aviator', 'rocket': 'jet'}.get(k, k)}
exec(compile(ast.Module(body=fn, type_ignores=[]), '<prod>', 'exec'), ns)
c = db()
c.execute('CREATE TABLE game_history(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT)')
rows = [(1234, 'aviator', 10, 25, 'WON'), (5, 'aviator', 10, 0, 'LOST'), (77, 'aviator', 10, 10, 'PUSH'), (88, 'aviator', 10, 9, 'WON'), (99, 'jet', 10, 50, 'WON')]
for i in range(10): rows.append((1000 + i, 'aviator', 20, 40, 'WON'))
for u, g, s, p, st in rows: c.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,created_at) VALUES(?,?,?,?,?,?)', (u, g, s, p, st, '2026-10-30 10:00:00'))
c.commit(); c.close()
res, code = ns['crash_live_wins']('highflyer')
items = res['items']
assert code == 200 and len(items) == 8, len(items)
assert all(x['payout'] > x['stake'] and x['multiplier'] == round(x['payout'] / x['stake'], 2) for x in items)
assert all(x['name'].startswith('***') and len(x['name']) == 5 for x in items), 'ids must be masked'
assert items[0]['name'] == '***09', items[0]            # newest first
assert all('user_id' not in x for x in items)
assert ns['crash_live_wins']('dice')[1] == 404          # non-crash game refused
jet, _ = ns['crash_live_wins']('rocket'); assert len(jet['items']) == 1 and jet['items'][0]['payout'] == 50
print('LIVE_WINS_REGRESSION=PASS (real wins only; masked; newest first; cap 8; crash games only)')
