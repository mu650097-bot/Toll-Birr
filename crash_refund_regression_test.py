"""Aviator/Jet: a crashed round that is never cashed out must be LOST, not refunded."""
import ast, json, sqlite3, time, os, tempfile
from datetime import datetime, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent
src=(ROOT/'realtime_engine_v3.py').read_text(encoding='utf-8')
tree=ast.parse(src)
want={'_finish','_auto_target','_crash_reached','_settle_crashed_round','_settle_if_crashed','_cleanup_expired_realtime_rounds'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in want]
assign=[n for n in tree.body if isinstance(n,ast.Assign) and getattr(n.targets[0],'id','') in ('CRASH_GAMES',)]
assert {n.name for n in nodes}==want, 'production crash helpers missing'
path=os.path.join(tempfile.mkdtemp(),'t.db')
def db():
    c=sqlite3.connect(path,isolation_level=None);c.row_factory=sqlite3.Row;return c
fmt='%Y-%m-%d %H:%M:%S'
ns={'db':db,'json':json,'time':time,'datetime':datetime,'timedelta':timedelta,'REALTIME_ROUND_TIMEOUT_SEC':120,'CHICKEN_ROUND_TIMEOUT_SEC':300,'ROAD_GAMES':('chicken','rabbit'),'_eng':lambda k:{'crash':'aviator','rocket':'jet'}.get(k,k),
    'MAX_ROUND_PAYOUT_ETB':1350000.0,'_now':lambda:datetime.now().strftime(fmt),'_platform_record':lambda *a,**k:None}
exec(compile(ast.Module(body=assign+nodes,type_ignores=[]),'<prod>','exec'),ns)
c=db()
c.executescript('''CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL);
CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INT,amount REAL,transaction_type TEXT,created_at TEXT);
CREATE TABLE game_history(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
CREATE TABLE realtime_game_rounds(id INTEGER PRIMARY KEY,user_id INT,game_key TEXT,stake REAL,status TEXT DEFAULT 'ACTIVE',seed_commit TEXT,server_seed TEXT,crash_point REAL,started_at TEXT,finished_at TEXT,state_json TEXT,outcome_json TEXT);
INSERT INTO users VALUES(1,0);''')
def mk(game,crash,age):
    t=(datetime.now()-timedelta(seconds=age)).strftime(fmt)
    c.execute("INSERT INTO realtime_game_rounds(user_id,game_key,stake,seed_commit,server_seed,crash_point,started_at,state_json) VALUES(1,?,10,'c','s',?,?,'{\"house_edge\":0.05}')",(game,crash,t))
    return c.execute('SELECT last_insert_rowid()').fetchone()[0]
status=lambda i:c.execute('SELECT status FROM realtime_game_rounds WHERE id=?',(i,)).fetchone()[0]
# 1) crashed (1.5x reached after ~12s on the 100^(t/120) curve), polled at 60s -> LOST immediately
a=mk('aviator',1.5,60); ns['_settle_if_crashed'](a); assert status(a)=='LOST','crashed round was not settled LOST'
# 2) still flying (crash 50x, 10s in) -> stays ACTIVE
b=mk('jet',50.0,10); ns['_settle_if_crashed'](b); assert status(b)=='ACTIVE'
# 3) abandoned past timeout -> cleanup must LOSE crash games, still refund normal games
d=mk('aviator',90.0,500); e=mk('dice',None,500)
ns['_cleanup_expired_realtime_rounds']()
assert status(d)=='LOST','aviator abandoned after timeout must be LOST (was refunded)'
assert status(e)=='REFUNDED','non-crash abandoned round should still refund'
bal=c.execute('SELECT balance FROM users WHERE user_id=1').fetchone()[0]
assert abs(bal-10)<1e-9, f'only the dice stake should be refunded, balance={bal}'
# 4) catalog variants (own game_key, crash engine): a crashed 'crash'/'rocket' round is LOST too
v=mk('crash',1.5,60); ns['_settle_if_crashed'](v); assert status(v)=='LOST','variant crash round must settle like aviator'
w=mk('rocket',50.0,10); ns['_settle_if_crashed'](w); assert status(w)=='ACTIVE'
print('CRASH_REFUND_REGRESSION=PASS')
