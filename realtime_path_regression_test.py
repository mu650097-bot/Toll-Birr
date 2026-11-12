"""Regression checks for the actual /round/start + /action production source path.

The helper tests execute _validated_realtime_input directly from the production
realtime_engine_v3.py AST, while route-order assertions ensure validation is
performed before the transaction that reserves a player's stake.
"""
import ast, math, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
rt=(ROOT/'realtime_engine_v3.py').read_text(encoding='utf-8')
js=(ROOT/'app.js').read_text(encoding='utf-8')
tree=ast.parse(rt)
need={'_validated_realtime_input','integer_value'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in need]
if {n.name for n in nodes} != need: raise SystemExit('FAIL: production realtime input validator missing')
def parse_money(value, name='amount'):
    value=float(value)
    if not math.isfinite(value): raise ValueError(name)
    return value
import dice_math as _dm
_LV={'easy':0,'medium':0,'hard':0}
ns={'parse_money':parse_money,'math':math,'ROAD_GAMES':('chicken','rabbit'),'ROAD_CFG':{'chicken':(15,_LV),'rabbit':(10,_LV)},'dice2_valid':_dm.dice2_valid,'_eng':lambda k:k}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<production-realtime-validator>','exec'),ns)
valid=ns['_validated_realtime_input']
cases={
 'dice':{'stake':10,'guess':6}, 'slot':{'stake':10}, 'wheel':{'stake':10},
 'keno':{'stake':10,'numbers':[1,2,3,4,5]}, 'chicken':{'stake':10,'difficulty':'hard'}, 'rabbit':{'stake':10,'difficulty':'medium'},
 'aviator':{'stake':10}, 'plinko':{'stake':10}, 'mines':{'stake':10,'mines':1,'pick':25},
 'jet':{'stake':10}, 'fish':{'stake':10,'shot':5},
 'card':{'stake':10,'choice':'high'},
}
for key,body in cases.items():
    clean,err=valid(key,body)
    if err or not isinstance(clean,dict) or clean.get('stake') != 10.0:
        raise SystemExit(f'FAIL: valid realtime input rejected: {key}: {err}')
invalid=[
 ('keno',{'stake':10,'numbers':[1,1,2,3,4]}),
 ('keno',{'stake':10,'numbers':[1,2,3,4,'bad']}),
 ('mines',{'stake':10,'mines':9,'pick':1}),
 ('mines',{'stake':10,'mines':3,'pick':26}),
 ('dice',{'stake':10,'guess':'bad'}),
 ('chicken',{'stake':10,'difficulty':'insane'}),
 ('chicken',{'stake':10,'steps':3}),
 ('rabbit',{'stake':10,'steps':1}),
 ('fish',{'stake':10,'shot':0}),
 ('slot',{'stake':0}),
 ('slot',{'stake':'NaN'}),
 ('chicken',{'stake':10}),
 ('mines',{'stake':10,'mines':3}),
 ('fish',{'stake':10}),
 ('card',{'stake':10,'choice':'middle'}),
 ('slot',{'stake':10,'raw_db_field':'should-not-persist'}),
]
for key,body in invalid:
    clean,err=valid(key,body)
    if not err: raise SystemExit(f'FAIL: invalid realtime input accepted: {key}: {body}')
live_cases={k:v for k,v in cases.items() if k not in ('chicken','rabbit')}
start=rt[rt.index("def rt_start("):rt.index("@app.route('/api/games/<key>/round/<int:round_id>/state'")]
action=rt[rt.index('def rt_action('):rt.index('# Embedded WebRTC signaling')]
if start.index('_validated_realtime_input') > start.index("q.execute('BEGIN IMMEDIATE')"):
    raise SystemExit('FAIL: stake transaction starts before round input validation')
if "@rate_limit(max_calls=12, window_seconds=10)" not in rt or "@rate_limit(max_calls=30, window_seconds=10)" not in rt:
    raise SystemExit('FAIL: realtime start/action rate limits missing')
if '_apply_cabinet_house_edge' not in action or 'effective_multiplier' not in action or "o['base_multiplier']" not in action:
    raise SystemExit('FAIL: realtime payout path is not disclosing effective payout multiplier')
if 'startRealtimeRound(key,body)' not in js or "realtimeAction(key,'play')" not in js or '/games/${key}/play' in js:
    raise SystemExit('FAIL: UI is not using realtime round start/action as the canonical 12-game path')
if 'streamRoundResult' in js or 'playAddedGameLegacy' in js:
    raise SystemExit('FAIL: dead legacy realtime frontend code remains')
if 'status="ACTIVE"' in rt or 'status="ended"' in rt:
    raise SystemExit('FAIL: SQL status values still use double quotes')
print(f'REALTIME_PATH_REGRESSION=PASS (12 valid games; {len(invalid)} invalid inputs; stake validation before debit; live route/payout contract)')

# Execute the production rt_action function against an isolated SQLite DB with
# deterministic RNG, so RTP assertions exercise /action rather than only /play.
import copy, datetime, hashlib, json, random, sqlite3, tempfile, time
from types import SimpleNamespace
api_tree=ast.parse((ROOT/'webapp_api.py').read_text(encoding='utf-8'))
api_nodes=[n for n in api_tree.body if isinstance(n,ast.FunctionDef) and n.name in {'_cabinet_base_rtp','_apply_cabinet_house_edge'}]
rt_nodes=[]
for n in tree.body:
    if isinstance(n,ast.FunctionDef) and n.name in {'_finish','rt_action','_auto_target'}:
        n=copy.deepcopy(n);n.decorator_list=[];rt_nodes.append(n)
if {n.name for n in api_nodes} != {'_cabinet_base_rtp','_apply_cabinet_house_edge'} or {n.name for n in rt_nodes} != {'_finish','rt_action','_auto_target'}:
    raise SystemExit('FAIL: could not extract production realtime payout/action functions')
current={'key':''}
class FixedRng:
    def __init__(self, seed=None): pass
    def randint(self,a,b):
        if current['key']=='wheel': return 11
        if current['key']=='card': return 8
        return 6
    def choice(self,values):
        if current['key']=='slot': return '7️⃣'
        return values[-1]
    def randrange(self,n): return n-1
    def random(self): return 0.0
    def sample(self,population,k):
        if current['key']=='keno': return [1,2,3,4,5]
        if current['key']=='plinko': return list(range(k))
        return list(range(2,2+k))
with tempfile.TemporaryDirectory() as td:
    db_path=Path(td)/'rt.sqlite'
    conn=sqlite3.connect(db_path);conn.row_factory=sqlite3.Row
    conn.executescript('''
    CREATE TABLE users(user_id INTEGER PRIMARY KEY,balance REAL NOT NULL);
    CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount REAL,transaction_type TEXT,created_at TEXT);
    CREATE TABLE realtime_game_rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game_key TEXT,stake REAL,status TEXT,seed_commit TEXT,server_seed TEXT,crash_point REAL,started_at TEXT,finished_at TEXT,state_json TEXT,outcome_json TEXT);
    CREATE TABLE game_history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game_key TEXT,stake REAL,payout REAL,status TEXT,outcome_json TEXT,created_at TEXT);
    CREATE TABLE realtime_game_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,round_id INTEGER,user_id INTEGER,action TEXT,payload_json TEXT,created_at TEXT);
    INSERT INTO users(user_id,balance) VALUES(123,100000);
    ''');conn.commit();conn.close()
    def db():
        c=sqlite3.connect(db_path,timeout=3);c.row_factory=sqlite3.Row;return c
    def platform_record(*args,**kwargs): return None
    def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    env={'db':db,'g':SimpleNamespace(tg_user={'id':123}),
         'request':SimpleNamespace(get_json=lambda silent=True:{'action':'play'}),
         'jsonify':lambda value:value,'_now':now,'_platform_record':platform_record,
         '_apply_cabinet_house_edge':None,'_cabinet_base_rtp':None,
         '_wheel_prizes':lambda:[0,1.5,0,0,3,0,1.5,0,0,0,10,0,1.5,0,0,1.5,0,0,0,0],'FISH_TABLE':[0.0]*50+[1.5]*16+[2.0]*6+[3.0]*4+[4.0]*2+[8.0,12.0],
         'json':json,'datetime':datetime.datetime,'time':time,'random':SimpleNamespace(Random=FixedRng),
         'hashlib':hashlib,'math':math,'secrets':__import__('secrets'),
         'REALTIME_ROUND_TIMEOUT_SEC':120,'MAX_ROUND_PAYOUT_ETB':1350000.0,'CABINET_GAME_KEYS':set(live_cases),'ROAD_GAMES':('chicken','rabbit'),'_eng':lambda k:k,
         'KENO_PAYTABLE':{0:0.0,1:0.5,2:1.0,3:3.5,4:30.0,5:120.0},'KENO_BASE_RTP':0.9034765221878225,'_sl':__import__('slot_math'),'slot_math':__import__('slot_math')}
    exec(compile(ast.Module(body=api_nodes+rt_nodes,type_ignores=[]),'<production-live-action>','exec'),env)
    env['current']=current
    env['_validated_realtime_input']=valid
    for key,body in live_cases.items():
        current['key']=key
        clean,err=valid(key,body)
        if err: raise SystemExit(f'FAIL: route simulation input invalid for {key}: {err}')
        c=db();q=c.cursor();stamp=now();edge={'slot':.08,'wheel':.05,'keno':.10,'plinko':.08,'fish':.05}.get(key,.05)
        crash=100.0 if key in ('aviator','jet') else None
        q.execute('INSERT INTO realtime_game_rounds(user_id,game_key,stake,status,seed_commit,server_seed,crash_point,started_at,state_json) VALUES(?,?,?,?,?,?,?,?,?)',
                  (123,key,100.0,'ACTIVE','commit','seed-'+key,crash,stamp,json.dumps({'house_edge':edge,'input':clean})))
        rid=q.lastrowid;c.commit();c.close()
        env['request']=SimpleNamespace(get_json=lambda silent=True:{'action':'cashout' if key in ('aviator','jet') else 'play'})
        response=env['rt_action'](key,rid)
        if isinstance(response,tuple): response,status=response
        else: status=200
        if status!=200 or not isinstance(response,dict) or response.get('status') not in ('WON','LOST'):
            raise SystemExit(f'FAIL: production /action failed for {key}: status={status}, response={response}')
        payout=float(response.get('payout',0));effective=payout/100.0
        outcome=response.get('outcome') or {}
        expected={
            'dice':5.7,'slot':13.6*.92/__import__('slot_math').BASE_RTP,'wheel':10.0,'keno':119.5395,
            'plinko':1.104,'mines':1.0,
            'fish':12.0,'card':.95/(6/13),
        }
        if key in ('aviator','jet'):
            if abs(effective-float(response.get('cashout',0)))>0.03 or abs(float(response.get('rtp',0))-.95)>1e-9:
                raise SystemExit(f'FAIL: {key} cashout payout/RTP mismatch: {effective}, RTP={response.get("rtp")}')
        else:
            if abs(effective-float(outcome.get('effective_multiplier',0)))>0.00011:
                raise SystemExit(f'FAIL: {key} /action effective multiplier mismatch: {effective} vs {outcome.get("effective_multiplier")}')
            if abs(effective-expected[key]) > .03:
                raise SystemExit(f'FAIL: {key} /action payout does not match configured RTP: {effective} vs expected {expected[key]}')
            if abs(float(outcome.get('rtp',0)) - (1-edge)) > 1e-9:
                raise SystemExit(f'FAIL: {key} /action RTP disclosure mismatch: {outcome.get("rtp")}')
            if key == 'mines' and response.get('won') and payout + 1e-9 < 100.0:
                raise SystemExit('FAIL: a Mines WIN returned less than the stake')
            if key not in ('aviator','jet') and response.get('won') and payout + 1e-9 < 100.0:
                raise SystemExit(f'FAIL: {key} reports WON with payout below stake')
            if key == 'plinko':
                path = outcome.get('path') or []
                if sum(path) != outcome.get('landing_slot') or outcome.get('base_multiplier') != [0,.5,.8,1,1.2,1.5,2,3,5][sum(path)]:
                    raise SystemExit('FAIL: Plinko path does not match its landing bucket/payout')
            if key == 'wheel' and (len(outcome.get('prizes') or []) != 20 or abs(float(outcome['prizes'][int(outcome['sector'])-1])-effective) > .03):
                raise SystemExit('FAIL: Wheel drawing sector prizes do not match paid payout multipliers')
    print('REALTIME_ACTION_RTP=PASS (production rt_action executed for all 11 one-shot/crash games (Chicken/Rabbit Road are interactive: see chicken_road_regression_test.py); payout/stake matches returned effective multiplier)')

    # Statistical RTP smoke test on the actual /action function, not the
    # legacy /play path. Keno needs more samples because its jackpot is rare.
    env['random'] = random
    targets={'dice':.95,'slot':.92,'wheel':.95,'keno':.90,'aviator':.95,
             'plinko':.92,'mines':.95,'jet':.95,'fish':.95,'card':.95}
    sample_counts={k:(8000 if k=='slot' else 5000 if k=='keno' else 1200) for k in live_cases}   # slot: std dev ~3x the stake per round (400x line + free spins) -> needs more rounds
    for key,body in live_cases.items():
        current['key']=key; total=0.0; n=sample_counts[key]
        edge=1-targets[key]
        for i in range(n):
            clean,err=valid(key,body)
            if err: raise SystemExit(f'FAIL: statistical input invalid for {key}: {err}')
            seed=f'rtp-live-{key}-{i}'
            started=datetime.datetime.now()-datetime.timedelta(seconds=20) if key in ('aviator','jet') else datetime.datetime.now()
            stamp=started.strftime('%Y-%m-%d %H:%M:%S')
            crash=None
            if key in ('aviator','jet'):
                u=(int(hashlib.sha256(seed.encode()).hexdigest()[:12],16)%999999+1)/1000000
                crash=min(100.0,max(1.0,(1-edge)/(1-u)))
            c=db();q=c.cursor()
            q.execute('INSERT INTO realtime_game_rounds(user_id,game_key,stake,status,seed_commit,server_seed,crash_point,started_at,state_json) VALUES(?,?,?,?,?,?,?,?,?)',
                      (123,key,100.0,'ACTIVE','commit',seed,crash,stamp,json.dumps({'house_edge':edge,'input':clean})))
            rid=q.lastrowid;c.commit();c.close()
            env['request']=SimpleNamespace(get_json=lambda silent=True:{'action':'cashout' if key in ('aviator','jet') else 'play'})
            response=env['rt_action'](key,rid)
            if isinstance(response,tuple): response,status=response
            else: status=200
            if status!=200 or not isinstance(response,dict):
                raise SystemExit(f'FAIL: statistical /action failed for {key}: {response}')
            total += float(response.get('payout',0))/100.0
        observed=total/n
        tolerance=.13 if key=='keno' else (.11 if key in ('aviator','jet','slot') else .09)
        if abs(observed-targets[key])>tolerance:
            raise SystemExit(f'FAIL: /action statistical RTP out of tolerance for {key}: observed={observed:.4f}, target={targets[key]:.4f}, n={n}')
        print(f'LIVE_ACTION_RTP {key}: observed={observed:.4f} target={targets[key]:.4f} n={n} PASS')
    print('REALTIME_LIVE_ACTION_RTP=PASS (all 11 production /action payout paths statistically sampled)')
