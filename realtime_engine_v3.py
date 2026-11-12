# Loaded by webapp_api.py with its globals() so existing auth/db helpers are reused.
from datetime import datetime, timedelta
import hashlib, json, os, random, secrets, time, uuid, hmac, math
from keno_math import POOL as KENO80_POOL, DRAW as KENO80_DRAW, MAX_PICK as KENO80_MAX_PICK, nominal_table as keno80_nominal
import triplegold_math as _tg
import slot_math as _sl
import flame_math as _fl
import aztec_math as _az
import roast_math as _ro
import buffalo_math as _bf
from plinko_math import RISKS as PLINKO_RISKS, ROWS as PLINKO_ROWS, nominal_table as plinko_nominal

REALTIME_ROUND_TIMEOUT_SEC=int(os.getenv('REALTIME_ROUND_TIMEOUT_SEC','120'))
CALL_SESSION_TIMEOUT_SEC=int(os.getenv('CALL_SESSION_TIMEOUT_SEC','7200'))
PAYMENT_PROVIDER=os.getenv('PAYMENT_PROVIDER','manual')
PAYMENT_WEBHOOK_SECRET=os.getenv('PAYMENT_WEBHOOK_SECRET','')
TURN_URL=os.getenv('TURN_URL','').strip()
TURN_USERNAME=os.getenv('TURN_USERNAME','').strip()
TURN_CREDENTIAL=os.getenv('TURN_CREDENTIAL','').strip()

def _v3_init():
 c=db();q=c.cursor()
 q.execute('''CREATE TABLE IF NOT EXISTS realtime_game_rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,game_key TEXT NOT NULL,stake REAL NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',seed_commit TEXT NOT NULL,server_seed TEXT NOT NULL,crash_point REAL,started_at TEXT NOT NULL,finished_at TEXT,state_json TEXT NOT NULL DEFAULT '{}',outcome_json TEXT)''')
 q.execute('CREATE INDEX IF NOT EXISTS idx_rt_user_status ON realtime_game_rounds(user_id,status,id DESC)')
 q.execute('''CREATE TABLE IF NOT EXISTS realtime_game_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,round_id INTEGER NOT NULL,user_id INTEGER NOT NULL,action TEXT NOT NULL,payload_json TEXT,created_at TEXT NOT NULL)''')
 q.execute('''CREATE TABLE IF NOT EXISTS call_sessions(id TEXT PRIMARY KEY,tx_id TEXT,buyer_id INTEGER NOT NULL,seller_id INTEGER NOT NULL,media_type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'waiting',created_at TEXT NOT NULL,expires_at TEXT NOT NULL,started_at TEXT,ended_at TEXT)''')
 q.execute('''CREATE TABLE IF NOT EXISTS call_signals(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,sender_id INTEGER NOT NULL,signal_type TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)''')
 q.execute('CREATE INDEX IF NOT EXISTS idx_call_signals_session ON call_signals(session_id,id)')
 q.execute('''CREATE TABLE IF NOT EXISTS payment_intents(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,amount REAL NOT NULL,provider TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'created',provider_ref TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,metadata_json TEXT,credited_at TEXT)''')
 q.execute("PRAGMA table_info(payment_intents)")
 cols={x[1] for x in q.fetchall()}
 if 'credited_at' not in cols: q.execute('ALTER TABLE payment_intents ADD COLUMN credited_at TEXT')
 c.commit();c.close()
_v3_init()

CRASH_GAMES=('aviator','jet')

# ---- Chicken Road: interactive step-by-step game with cash-out at any time -------------------------
# Each step across the road is safe with probability p (by difficulty). The number of safe steps S is
# fixed at round start from sha256(server_seed:client_seed:difficulty) -- P(S>=n)=p**n -- and kept
# server-side (crash_point column) until the round ends, when server_seed is revealed so the player can
# recompute it. The multiplier after n safe steps is RTP/p**n, so the expected return is EXACTLY the
# configured RTP whatever the player's stopping rule is (no hidden payout scaling).
CHICKEN_MAX_STEPS=15
CHICKEN_LEVELS={'easy':0.90,'medium':0.82,'hard':0.75,'hardcore':0.735}
# Rabbit Road: same engine, tougher profile -- shorter track (10 hops), lower survival odds per hop, 60x max.
ROAST_MAX_STEPS=12
ROAST_LEVELS={'easy':0.88,'medium':0.78,'hard':0.70}   # hard max 0.95/0.70^12 = 69x
RABBIT_MAX_STEPS=10
RABBIT_LEVELS={'easy':0.86,'medium':0.76,'hard':0.66}
# Ladder games with the same maths as Chicken Road (survive n steps -> RTP / p**n), re-skinned:
PENALTYSTREAK_MAX_STEPS=10;PENALTYSTREAK_LEVELS={'easy':0.88,'medium':0.78,'hard':0.68}   # hard max 0.95/0.68^10 = 45x
TOWER_MAX_STEPS=8;TOWER_LEVELS={'easy':0.82,'medium':0.70,'hard':0.58}                  # hard max 0.95/0.58^8 = 74x
COINSTREAK_MAX_STEPS=6;COINSTREAK_LEVELS={'easy':0.5}    # fair coin: each flip survives with p=0.5; max 0.95/0.5^6 = 60.8x
CHICKEN2_MAX_STEPS=7;CHICKEN2_LEVELS={'calm':0.80,'rush':0.59}   # Chicken Road 2 (night road): MUST match P/MAX in kdm_chicken2.js; rush max 0.95/0.59^7 = ~38x
ROAD_GAMES=('chicken','rabbit','penaltystreak','tower','chicken2','coinstreak')   # 'roast' is now a 3x3 slot (roast_math.py)
ROAD_CFG={'chicken':(CHICKEN_MAX_STEPS,CHICKEN_LEVELS),'rabbit':(RABBIT_MAX_STEPS,RABBIT_LEVELS),
 'penaltystreak':(PENALTYSTREAK_MAX_STEPS,PENALTYSTREAK_LEVELS),'tower':(TOWER_MAX_STEPS,TOWER_LEVELS),'chicken2':(CHICKEN2_MAX_STEPS,CHICKEN2_LEVELS),'coinstreak':(COINSTREAK_MAX_STEPS,COINSTREAK_LEVELS)}
CHICKEN_ROUND_TIMEOUT_SEC=int(os.getenv('CHICKEN_ROUND_TIMEOUT_SEC','300'))

def _chicken_safe_steps(server_seed,client_seed,level,key='chicken'):
 mx,lvls=ROAD_CFG[key];p=lvls[level]
 h=hashlib.sha256(f'{server_seed}:{client_seed}:{level}'.encode()).hexdigest()
 u=(int(h[:13],16)+1)/float(16**13)  # uniform in (0,1]
 return max(0,min(mx,int(math.floor(math.log(u)/math.log(p)))))

def _chicken_multiplier(level,steps,rtp,key='chicken'):
 return float(rtp)/(ROAD_CFG[key][1][level]**int(steps))

def _chicken_payout(stake,level,steps,rtp,key='chicken'):
 return round(min(MAX_ROUND_PAYOUT_ETB,float(stake)*_chicken_multiplier(level,steps,rtp,key)),2)

def _rt_initial_state(key,edge,b):
 st={'house_edge':edge,'rtp':round(1-edge,4),'input':b}
 if key in ROAD_GAMES:
  lv=b['difficulty'];rtp=1-edge;mx,lvls=ROAD_CFG[key]
  st.update(progress=0,max_steps=mx,p=lvls[lv],
            multipliers=[round(_chicken_multiplier(lv,n,rtp,key),4) for n in range(1,mx+1)])
 if key=='minesx':
  mm=int(b['mines']);rtp_=1-edge
  st.update(progress=0,revealed=[],mines=mm,tiles=MINESX_TILES,max_steps=MINESX_TILES-mm,
            multipliers=[round(_minesx_multiplier(mm,n,rtp_),4) for n in range(1,MINESX_TILES-mm+1)])
 return st

def _chicken_settle(q,r,won,steps,hit_step=None,reason=None):
 """Finish a chicken round: pay the cash-out multiplier if won, else lose the stake. Reveals the seed."""
 st=json.loads(r['state_json'] or '{}');lv=st['input']['difficulty'];rtp=float(st.get('rtp',.95))
 gk=r['game_key'];payout=_chicken_payout(r['stake'],lv,steps,rtp,gk) if won else 0.0
 out={'difficulty':lv,'steps_cleared':int(steps),'hit_step':hit_step,'safe_steps':int(r['crash_point']),'server_seed':r['server_seed'],
      'client_seed':st['input'].get('client_seed',''),'rtp':rtp,'house_edge':float(st.get('house_edge',.05)),'server_authoritative':True,
      'multiplier':round(_chicken_multiplier(lv,steps,rtp,gk),4) if won else 0.0,'game':gk}
 if reason:out['reason']=reason
 out['effective_multiplier']=round(payout/float(r['stake']),4) if payout>0 else 0.0
 _finish(q,r,won,payout,out)
 return payout,out

def _chicken_close_idle(q,r):
 """Close an abandoned/expired chicken round inside the caller's transaction: pay what was already
 earned (cash-out at the current step) or, if the player never stepped, refund the stake."""
 st=json.loads(r['state_json'] or '{}');prog=int(st.get('progress',0))
 if prog>=1:
  _chicken_settle(q,r,True,prog,reason='auto_cashout');return
 now=_now();out={'reason':'timeout_refund','server_seed':r['server_seed'],'refunded':True,'payout':float(r['stake'])}
 q.execute("UPDATE realtime_game_rounds SET status='REFUNDED',finished_at=?,outcome_json=? WHERE id=? AND status='ACTIVE'",(now,json.dumps(out,separators=(',',':')),r['id']))
 if q.rowcount!=1:return
 q.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(r['stake'],r['user_id']))
 q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(r['user_id'],r['stake'],f"game_{r['game_key']}_rt_refund",now))
 q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',(r['user_id'],r['game_key'],r['stake'],r['stake'],'REFUNDED',json.dumps(out,separators=(',',':')),now))
 _platform_record(q,'game_house_result',0,f"rt:{r['id']}:timeout-refund",'expired round refunded',now)

def _auto_target(r):
 """Auto cash-out multiplier chosen at round start; only honoured when it is below the hidden crash point,
 so the live curve is guaranteed to cross it first. Time-based like the curve itself: no client needed."""
 try:a=json.loads(r['state_json'] or '{}').get('input',{}).get('auto_cashout')
 except Exception:return None
 if a is None or r['crash_point'] is None:return None
 a=float(a);return a if 1.0<a<float(r['crash_point']) else None

def _crash_reached(r):
 """True when an ACTIVE aviator/jet round is decided by time: it crossed its hidden crash point,
 or it crossed the player's auto cash-out target (always below the crash point)."""
 if _eng(r['game_key']) not in CRASH_GAMES or r['status']!='ACTIVE' or r['crash_point'] is None:return False
 elapsed=max(0,time.time()-datetime.strptime(r['started_at'],'%Y-%m-%d %H:%M:%S').timestamp())
 cur=min(float(r['crash_point']),max(1.0,100.0**(elapsed/max(1.0,REALTIME_ROUND_TIMEOUT_SEC))))
 a=_auto_target(r)
 return cur>=float(r['crash_point']) or (a is not None and cur>=a)

def _settle_crashed_round(q,r):
 """Settle a time-decided crash round. Auto cash-out reached first -> WON at exactly the target; otherwise an
 uncashed crashed round is LOST (a player must never avoid a loss by simply not sending cashout)."""
 edge=float(json.loads(r['state_json'] or '{}').get('house_edge',.05));a=_auto_target(r)
 if a is not None:
  payout=round(min(MAX_ROUND_PAYOUT_ETB,r['stake']*a),2);eff=round(payout/float(r['stake']),4)
  out={'cashout':round(payout/float(r['stake']),2),'auto_cashout':a,'crash':r['crash_point'],'server_seed':r['server_seed'],'effective_multiplier':eff,'rtp':round(1-edge,4),'house_edge':edge,'payout':payout}
  _finish(q,r,True,payout,out);return out
 out={'crash':r['crash_point'],'cashout':None,'reason':'crashed_without_cashout','server_seed':r['server_seed'],'effective_multiplier':0.0,'rtp':round(1-edge,4),'house_edge':edge}
 _finish(q,r,False,0,out);return out

def _settle_if_crashed(round_id):
 c=db();q=c.cursor()
 try:
  q.execute('BEGIN IMMEDIATE');q.execute('SELECT * FROM realtime_game_rounds WHERE id=?',(round_id,));r=q.fetchone()
  if r and _crash_reached(r):_settle_crashed_round(q,r);c.commit()
  else:c.rollback()
 except Exception:
  c.rollback();raise
 finally:c.close()

def _rt_payload(r):
 state=json.loads(r['state_json'] or '{}');out=json.loads(r['outcome_json']) if r['outcome_json'] else None
 elapsed=max(0,time.time()-datetime.strptime(r['started_at'],'%Y-%m-%d %H:%M:%S').timestamp())
 phase='SETTLED' if r['status']!='ACTIVE' else ('LIVE')
 x={'round_id':r['id'],'round_code':f"{r['game_key'].upper()}-RT-{r['id']:08d}",'game_key':r['game_key'],'stake':r['stake'],'status':r['status'],'phase':phase,'started_at':r['started_at'],'elapsed_seconds':round(elapsed,3),'state':state,'outcome':out,'payout':(out.get('payout') if out else None),'won':r['status']=='WON','refunded':r['status']=='REFUNDED','server_authoritative':True,'seed_commit':r['seed_commit']}
 if _eng(r['game_key']) in ('aviator','jet') and r['status']=='ACTIVE':
  live=min(float(r['crash_point']),max(1.0,100.0**(elapsed/max(1.0,REALTIME_ROUND_TIMEOUT_SEC))))
  x['live_multiplier']=round(live,2);x['server_time']=_now()
  # The round remains ACTIVE until a server action settles it, but the
  # state endpoint explicitly tells the client that the crash threshold
  # has been crossed so the UI never waits for a phase that cannot occur.
  if live >= float(r['crash_point']): x['phase']='CRASHED'
 return x

def _finish(cur,r,won,payout,out):
 now=_now();payout=round(min(MAX_ROUND_PAYOUT_ETB,max(0,float(payout))),2);out['payout']=payout
 if payout: cur.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(payout,r['user_id']));cur.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(r['user_id'],payout,f"game_{r['game_key']}_rt_payout",now))
 diff=round(float(r['stake'])-payout,2)
 _platform_record(cur,'game_house_result',diff,f"rt:{r['id']}",'realtime round settlement',now)
 st_='WON' if won else ('PUSH' if (payout>0 and abs(payout-float(r['stake']))<0.005) else 'LOST')
 cur.execute("UPDATE realtime_game_rounds SET status=?,finished_at=?,outcome_json=? WHERE id=? AND status='ACTIVE'",(st_,now,json.dumps(out,separators=(',',':')),r['id']))
 cur.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',(r['user_id'],r['game_key'],r['stake'],payout,st_,json.dumps(out,separators=(',',':')),now))
 return now

# ---- Mines (step by step): 5x5 board, open tiles one at a time, cash out whenever you like -----------------
# The mine layout is fixed at round start from sha256(server_seed:client_seed:mines) and is NOT stored or sent;
# it is recomputed server-side on every pick and revealed (with server_seed) when the round ends, so the
# player can verify it. Multiplier after k safe gems with m mines = RTP * C(25,k) / C(25-m,k), so the expected
# return is exactly the configured RTP whatever the player's stopping rule is.
MINESX_TILES=25;MINESX_OPTIONS=(1,3,5,10)
STEP_STATE_GAMES=ROAD_GAMES+('minesx',)

def _minesx_layout(server_seed,client_seed,m):
 rng=random.Random(hashlib.sha256(f'{server_seed}:{client_seed}:{int(m)}:mines'.encode()).hexdigest())
 return sorted(rng.sample(range(1,MINESX_TILES+1),int(m)))

def _minesx_multiplier(m,k,rtp):
 k=int(k)
 if k<1:return 1.0
 return float(rtp)*math.comb(MINESX_TILES,k)/math.comb(MINESX_TILES-int(m),k)

def _minesx_payout(stake,m,k,rtp):
 return round(min(MAX_ROUND_PAYOUT_ETB,float(stake)*_minesx_multiplier(m,k,rtp)),2)

def _minesx_settle(q,r,won,k,hit=None,reason=None):
 st=json.loads(r['state_json'] or '{}');m=int(st['mines']);rtp=float(st.get('rtp',.95));cs=st['input'].get('client_seed','')
 payout=_minesx_payout(r['stake'],m,k,rtp) if won else 0.0
 out={'mines':m,'gems':int(k),'hit_tile':hit,'revealed':st.get('revealed',[]),'mine_positions':_minesx_layout(r['server_seed'],cs,m),
      'server_seed':r['server_seed'],'client_seed':cs,'rtp':rtp,'house_edge':float(st.get('house_edge',.05)),'server_authoritative':True,
      'multiplier':round(_minesx_multiplier(m,k,rtp),4) if won else 0.0,'game':'minesx'}
 if reason:out['reason']=reason
 out['effective_multiplier']=round(payout/float(r['stake']),4) if payout>0 else 0.0
 _finish(q,r,won,payout,out)
 return payout,out

def _minesx_close_idle(q,r):
 st=json.loads(r['state_json'] or '{}');k=int(st.get('progress',0))
 if k>=1:
  _minesx_settle(q,r,True,k,reason='auto_cashout');return
 _chicken_close_idle(q,r)   # nothing opened yet: refund the stake

def _cleanup_expired_realtime_rounds():
 # Most state polls find nothing expired. Do a read-only probe first so
 # 300ms Aviator polling does not acquire SQLite's write lock every time.
 cutoff=(datetime.now()-timedelta(seconds=REALTIME_ROUND_TIMEOUT_SEC)).strftime('%Y-%m-%d %H:%M:%S')
 c=db();q=c.cursor()
 try:
  cutoff_c=(datetime.now()-timedelta(seconds=CHICKEN_ROUND_TIMEOUT_SEC)).strftime('%Y-%m-%d %H:%M:%S')
  q.execute("SELECT id FROM realtime_game_rounds WHERE status='ACTIVE' AND ((game_key NOT IN ('chicken','rabbit','penaltystreak','tower','chicken2','coinstreak','minesx') AND started_at < ?) OR (game_key IN ('chicken','rabbit','penaltystreak','tower','chicken2','coinstreak','minesx') AND started_at < ?)) LIMIT 1",(cutoff,cutoff_c))
  if q.fetchone() is None:return 0
  q.execute('BEGIN IMMEDIATE')
  q.execute("SELECT * FROM realtime_game_rounds WHERE status='ACTIVE' AND ((game_key NOT IN ('chicken','rabbit','penaltystreak','tower','chicken2','coinstreak','minesx') AND started_at < ?) OR (game_key IN ('chicken','rabbit','penaltystreak','tower','chicken2','coinstreak','minesx') AND started_at < ?))",(cutoff,cutoff_c))
  rows=q.fetchall(); refunded=0
  for r in rows:
   if _eng(r['game_key']) in CRASH_GAMES:
    _settle_crashed_round(q,r);continue
   if r['game_key']=='minesx':
    _minesx_close_idle(q,r);continue
   if r['game_key'] in ROAD_GAMES:
    _chicken_close_idle(q,r);continue
   now=_now();out={'reason':'timeout_refund','server_seed':r['server_seed'],'refunded':True,'payout':float(r['stake'])}
   q.execute("UPDATE realtime_game_rounds SET status='REFUNDED',finished_at=?,outcome_json=? WHERE id=? AND status='ACTIVE'",(now,json.dumps(out,separators=(',',':')),r['id']))
   if q.rowcount!=1: continue
   q.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(r['stake'],r['user_id']))
   q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(r['user_id'],r['stake'],f"game_{r['game_key']}_rt_refund",now))
   q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',(r['user_id'],r['game_key'],r['stake'],r['stake'],'REFUNDED',json.dumps(out,separators=(',',':')),now))
   _platform_record(q,'game_house_result',0,f"rt:{r['id']}:timeout-refund",'expired round refunded',now)
   refunded+=1
  c.commit();return refunded
 except Exception:
  c.rollback();raise
 finally:c.close()


def _validated_realtime_input(key, body):
 """Validate every game choice before a stake is reserved; return a small whitelist."""
 if not isinstance(body, dict): return None, 'request body must be a JSON object'
 allowed={
  'dice': {'stake','guess'}, 'dice2': {'stake','mode','target'}, 'slot': {'stake'}, 'triplegold': {'stake'}, 'flame': {'stake'}, 'aztec': {'stake'}, 'buffalo': {'stake'}, 'wheel': {'stake'},
  'keno': {'stake','numbers','grid'}, 'chicken': {'stake','difficulty'}, 'rabbit': {'stake','difficulty'}, 'roast': {'stake'}, 'penaltystreak': {'stake','difficulty'}, 'tower': {'stake','difficulty'}, 'chicken2': {'stake','difficulty'}, 'coinstreak': {'stake','difficulty'},
  'roulette': {'stake','bet','value'}, 'bingo': {'stake'}, 'fastkeno': {'stake','numbers'},
  'aviator': {'stake','auto_cashout'}, 'plinko': {'stake','risk','rows'}, 'mines': {'stake','mines','pick'},
  'jet': {'stake','auto_cashout'}, 'minesx': {'stake','mines'}, 'fish': {'stake','shot'},
  'card': {'stake','choice'}, 'coinflip': {'stake','choice'}, 'penalty': {'stake','choice'}, 'baccarat': {'stake','choice'}, 'dragontiger': {'stake','choice'}, 'andarbahar': {'stake','choice'},
 }
 if key not in allowed:return None,'unknown game'
 if set(body)-allowed[key]-{'client_seed'}:return None,'unsupported game input fields'
 client_seed=body.get('client_seed','')
 if not isinstance(client_seed,str) or len(client_seed)>128:return None,'client_seed must be text up to 128 characters'
 try:
  stake=parse_money(body.get('stake'), 'stake')
  if not math.isfinite(stake) or stake <= 0:return None,'stake must be a positive number'
 except (TypeError,ValueError,OverflowError):return None,'invalid stake'
 clean={'stake':stake,'client_seed':client_seed.strip()}
 def integer(name, default=None):
  value=body.get(name, default)
  if isinstance(value,bool):raise ValueError(name)
  if isinstance(value,float) and not value.is_integer():raise ValueError(name)
  parsed=int(value)
  if str(value).strip() not in (str(parsed), f'{parsed}.0') and not isinstance(value,int):raise ValueError(name)
  return parsed
 try:
  if key=='dice2':
   clean['mode']=str(body.get('mode','')).lower();clean['target']=integer('target')
   _ok,_err=dice2_valid(clean['mode'],clean['target'])
   if not _ok:raise ValueError(_err)
  elif key=='dice':
   clean['guess']=integer('guess')
   if clean['guess'] not in range(1,7):raise ValueError('guess must be 1-6')
  elif key=='keno':
   values=body.get('numbers')
   if body.get('grid') is not None:   # classic Keno: 1-10 picks out of 80, 20 drawn. Without `grid` the legacy 5-of-20 game is used.
    if isinstance(body.get('grid'),bool) or body.get('grid')!=80:raise ValueError('Keno grid must be 80')
    if not isinstance(values,list) or not 1<=len(values)<=KENO80_MAX_PICK:raise ValueError('Keno requires 1 to 10 unique numbers from 1-80')
    nums=[integer_value(x) for x in values]
    if len(set(nums))!=len(nums) or any(x<1 or x>KENO80_POOL for x in nums):raise ValueError('Keno requires 1 to 10 unique numbers from 1-80')
    clean['numbers']=nums;clean['grid']=80
   else:
    if not isinstance(values,list) or len(values)!=5:raise ValueError('Keno requires exactly 5 unique numbers from 1-20')
    nums=[integer_value(x) for x in values]
    if len(set(nums))!=5 or any(x<1 or x>20 for x in nums):raise ValueError('Keno requires exactly 5 unique numbers from 1-20')
    clean['numbers']=nums
  elif key=='roulette':
   clean['bet'],clean['value']=roulette_validate(body.get('bet'),body.get('value'))
  elif key=='fastkeno':
   values=body.get('numbers')
   if not isinstance(values,list) or not FASTKENO_PICK_MIN<=len(values)<=FASTKENO_PICK_MAX:raise ValueError(f'Fast Keno requires {FASTKENO_PICK_MIN}-{FASTKENO_PICK_MAX} unique numbers from 1-{FASTKENO_POOL}')
   nums=[integer_value(x) for x in values]
   if len(set(nums))!=len(nums) or any(x<1 or x>FASTKENO_POOL for x in nums):raise ValueError(f'Fast Keno requires {FASTKENO_PICK_MIN}-{FASTKENO_PICK_MAX} unique numbers from 1-{FASTKENO_POOL}')
   clean['numbers']=nums
  elif key in ROAD_GAMES:
   clean['difficulty']=str(body.get('difficulty','')).lower()
   if clean['difficulty'] not in ROAD_CFG[key][1]:raise ValueError('difficulty must be '+', '.join(ROAD_CFG[key][1]))
  elif key in ('aviator','jet'):
   if body.get('auto_cashout') not in (None,''):
    ac=body['auto_cashout']
    if isinstance(ac,bool) or not isinstance(ac,(int,float)) or ac!=ac or not 1.01<=float(ac)<=100:raise ValueError('auto_cashout must be a number between 1.01 and 100')
    clean['auto_cashout']=round(float(ac),2)
  elif key=='plinko':
   if 'risk' in body or 'rows' in body:   # new Risk/Rows mode; with neither field the legacy 8-row board is used
    clean['risk']=str(body.get('risk','med')).lower();clean['rows']=integer('rows',12)
    if clean['risk'] not in PLINKO_RISKS or clean['rows'] not in PLINKO_ROWS:raise ValueError('plinko risk must be low, med or high and rows 8, 12 or 16')
  elif key=='mines':
   clean['mines']=integer('mines');clean['pick']=integer('pick')
   if not 1<=clean['mines']<=8 or not 1<=clean['pick']<=25:raise ValueError('mines must be 1-8 and pick must be 1-25')
  elif key=='minesx':
   clean['mines']=integer('mines')
   if clean['mines'] not in MINESX_OPTIONS:raise ValueError('mines must be one of 1, 3, 5, 10')
  elif key=='fish':
   clean['shot']=integer('shot')
   if not 1<=clean['shot']<=5:raise ValueError('shot must be 1-5')
  elif key=='card':
   clean['choice']=str(body.get('choice','')).lower()
   if clean['choice'] not in ('high','low'):raise ValueError('choice must be high or low')
  elif key=='coinflip':
   clean['choice']=str(body.get('choice','')).lower()
   if clean['choice'] not in ('heads','tails'):raise ValueError('choice must be heads or tails')
  elif key=='dragontiger':
   clean['choice']=str(body.get('choice','')).lower()
   if clean['choice'] not in ('dragon','tiger','tie'):raise ValueError('choice must be dragon, tiger or tie')
  elif key=='andarbahar':
   clean['choice']=str(body.get('choice','')).lower()
   if clean['choice'] not in ('andar','bahar'):raise ValueError('choice must be andar or bahar')
  elif key=='baccarat':
   clean['choice']=str(body.get('choice','')).lower()
   if clean['choice'] not in ('player','banker','tie'):raise ValueError('choice must be player, banker or tie')
  elif key=='penalty':
   clean['choice']=str(body.get('choice','')).lower()
   if clean['choice'] not in ('left','center','right'):raise ValueError('choice must be left, center or right')
 except (TypeError,ValueError,OverflowError) as exc:
  return None, str(exc) if str(exc) else 'invalid game input'
 return clean,None


def integer_value(value):
 if isinstance(value,bool):raise ValueError('Keno numbers must be integers')
 if isinstance(value,float) and not value.is_integer():raise ValueError('Keno numbers must be integers')
 parsed=int(value)
 if not isinstance(value,int) and str(value).strip() not in (str(parsed),f'{parsed}.0'):
  raise ValueError('Keno numbers must be integers')
 return parsed

@app.route('/api/games/<key>/round/start',methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=12, window_seconds=10)
def rt_start(key):
 if key not in CABINET_GAME_KEYS:return jsonify({'error':'unknown game'}),404
 gk=key;key=_eng(gk)
 raw=request.get_json(silent=True)
 b,validation_error=_validated_realtime_input(key,raw)
 if validation_error:return jsonify({'error':validation_error}),400
 stake=b['stake'];enabled,mn,mx,edge=_cabinet_limits(gk)
 if not enabled:return jsonify({'error':'game is temporarily disabled'}),403
 if stake<mn or stake>mx:return jsonify({'error':f'stake must be between {mn:.2f} and {mx:.2f}'}),400
 try:_cleanup_expired_realtime_rounds()
 except Exception:logger.warning('realtime round cleanup deferred',exc_info=True)
 uid=g.tg_user['id'];seed=secrets.token_hex(32);commit=hashlib.sha256(seed.encode()).hexdigest();crash=None
 if key in ('aviator','jet'):
  # House-edge-aware crash distribution. Keep the internal crash point
  # unrounded and allow an instant 1.00x crash; rounding to 2 decimals is
  # presentation-only and must never create a guaranteed 1.01x win.
  u=(int(hashlib.sha256(seed.encode()).hexdigest()[:12],16)%999999+1)/1000000
  crash=min(100.0,max(1.0,(1.0-edge)/(1.0-u)))
 if key in ROAD_GAMES:crash=float(_chicken_safe_steps(seed,b.get('client_seed',''),b['difficulty'],key))
 now=_now();c=db();q=c.cursor()
 try:
  q.execute('BEGIN IMMEDIATE');q.execute("SELECT * FROM realtime_game_rounds WHERE user_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(uid,));old=q.fetchone()
  if old:
   old_input=json.loads(old['state_json'] or '{}').get('input',{})
   same=(old['game_key']==gk and abs(float(old['stake'])-float(stake))<0.001 and old_input.get('client_seed','')==b.get('client_seed','') and {k:v for k,v in old_input.items() if k!='client_seed'}=={k:v for k,v in b.items() if k!='client_seed'})
   if same:
    c.rollback();c.close();return jsonify({'ok':True,'status':'ACTIVE','round_id':old['id'],'round_code':f"{gk.upper()}-RT-{old['id']:08d}",'seed_commit':old['seed_commit'],'client_seed':b.get('client_seed',''),'server_authoritative':True,'server_time':old['started_at'],'recovered':True,'state':json.loads(old['state_json'] or '{}') if key in STEP_STATE_GAMES else None})
   if old['game_key'] not in STEP_STATE_GAMES:c.rollback();c.close();return jsonify({'error':'an active round already exists','round_id':old['id']}),409
   (_minesx_close_idle if old['game_key']=='minesx' else _chicken_close_idle)(q,old)
  if PLATFORM_BANKROLL_ETB>0:
   # Worst case a round can pay is bounded by 100x stake (crash cap) and MAX_ROUND_PAYOUT_ETB.
   q.execute("SELECT COALESCE(SUM(stake),0) FROM realtime_game_rounds WHERE status='ACTIVE'");open_stake=float(q.fetchone()[0] or 0)
   exposure=min(MAX_ROUND_PAYOUT_ETB,(open_stake+stake)*100.0)
   if exposure>PLATFORM_BANKROLL_ETB*BANKROLL_EXPOSURE_PCT:c.rollback();c.close();return jsonify({'error':'table limit reached, please try again shortly'}),503
  q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?',(stake,uid,stake))
  if q.rowcount!=1:c.rollback();c.close();return jsonify({'error':'insufficient balance'}),400
  q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(uid,-stake,f'game_{gk}_rt_stake',now));q.execute('INSERT INTO realtime_game_rounds(user_id,game_key,stake,seed_commit,server_seed,crash_point,started_at,state_json) VALUES(?,?,?,?,?,?,?,?)',(uid,gk,stake,commit,seed,crash,now,json.dumps(_rt_initial_state(key,edge,b),separators=(',',':'))));rid=q.lastrowid;c.commit();c.close()
 except Exception:
  try:c.rollback();c.close()
  except Exception:pass
  raise
 return jsonify({'ok':True,'status':'ACTIVE','round_id':rid,'round_code':f'{gk.upper()}-RT-{rid:08d}','seed_commit':commit,'client_seed':b.get('client_seed',''),'server_authoritative':True,'server_time':now,'state':_rt_initial_state(key,edge,b) if key in STEP_STATE_GAMES else None})

@app.route('/api/games/<key>/active')
@require_telegram_auth
def road_active_round(key):
 if key not in STEP_STATE_GAMES:return jsonify({'error':'unknown game'}),404
 try:_cleanup_expired_realtime_rounds()
 except Exception:logger.warning('realtime round cleanup deferred',exc_info=True)
 c=db();q=c.cursor();q.execute("SELECT * FROM realtime_game_rounds WHERE user_id=? AND game_key=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(g.tg_user['id'],key));r=q.fetchone();c.close()
 return jsonify(_rt_payload(r) if r else {'active':False})

@app.route('/api/games/<key>/live-wins')
@require_telegram_auth
def crash_live_wins(key):
 """REAL recent winning rounds of a crash game (all players, masked names). Nothing here is invented:
 rows come straight from game_history. Only payouts above the stake count as wins."""
 ek=_eng(key)
 if ek not in CRASH_GAMES:return jsonify({'error':'unknown game'}),404
 c=db();q=c.cursor()
 q.execute("SELECT h.user_id,h.stake,h.payout,h.created_at FROM game_history h WHERE h.game_key=? AND h.stake>0 AND h.payout>h.stake AND h.status IN ('WON','WIN') ORDER BY h.id DESC LIMIT 8",(ek,))
 rows=q.fetchall();c.close()
 items=[]
 for r in rows:
  uid=str(r['user_id']);st=float(r['stake']);po=float(r['payout'])
  items.append({'name':'***'+uid[-2:].rjust(2,'0'),'stake':round(st,2),'payout':round(po,2),'multiplier':round(po/st,2),'created_at':r['created_at']})
 return jsonify({'items':items})

@app.route('/api/games/<key>/round/<int:round_id>/state')
@require_telegram_auth
def rt_state(key,round_id):
 try:_cleanup_expired_realtime_rounds()
 except Exception:pass
 try:_settle_if_crashed(round_id)
 except Exception:logger.warning('crash settlement deferred',exc_info=True)
 c=db();q=c.cursor();q.execute('SELECT * FROM realtime_game_rounds WHERE id=? AND user_id=? AND game_key=?',(round_id,g.tg_user['id'],key));r=q.fetchone();c.close()
 if not r:return jsonify({'error':'round not found'}),404
 x=_rt_payload(r)
 if _eng(key) in CRASH_GAMES and r['status']=='LOST' and (x.get('outcome') or {}).get('crash') is not None:
  x['phase']='CRASHED';x['live_multiplier']=round(float(x['outcome']['crash']),2)
 return jsonify(x)

@app.route('/api/games/<key>/round/<int:round_id>/action',methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=30, window_seconds=10)
def rt_action(key,round_id):
 gk=key;key=_eng(gk)
 uid=g.tg_user['id'];b=request.get_json(silent=True)
 if b is None:b={}
 if not isinstance(b,dict):return jsonify({'error':'request body must be a JSON object'}),400
 action=str(b.get('action') or ('cashout' if key in ('aviator','jet') else 'pick' if key=='minesx' else 'step' if key in ROAD_GAMES else 'play')).lower()
 if set(b)-({'action','tile'} if key=='minesx' else {'action'}):return jsonify({'error':'unsupported action fields'}),400
 if action not in (('cashout',) if key in ('aviator','jet') else ('pick','cashout') if key=='minesx' else ('step','cashout') if key in ROAD_GAMES else ('play',)):
  return jsonify({'error':'invalid action for this game'}),400
 c=db();q=c.cursor();q.execute('BEGIN IMMEDIATE');q.execute('SELECT * FROM realtime_game_rounds WHERE id=? AND user_id=? AND game_key=?',(round_id,uid,gk));r=q.fetchone()
 if not r:c.rollback();c.close();return jsonify({'error':'round not found'}),404
 if r['status']!='ACTIVE':
  if key in CRASH_GAMES and r['status']=='LOST':
   o=json.loads(r['outcome_json'] or '{}');c.rollback();c.close()
   return jsonify({'ok':True,'won':False,'payout':0,'status':'LOST','crash':o.get('crash'),'server_seed':r['server_seed'],'effective_multiplier':0.0,'rtp':o.get('rtp'),'outcome':o})
  if key in CRASH_GAMES and r['status']=='WON':   # already settled by the server at the player's auto cash-out
   o=json.loads(r['outcome_json'] or '{}');c.rollback();c.close()
   return jsonify({'ok':True,'won':True,'payout':o.get('payout'),'status':'WON','cashout':o.get('cashout'),'server_seed':r['server_seed'],'round_code':f'{gk.upper()}-RT-{round_id:08d}','effective_multiplier':o.get('effective_multiplier'),'rtp':o.get('rtp'),'outcome':o})
  c.rollback();c.close();return jsonify(_rt_payload(r)),409
 saved=json.loads(r['state_json'] or '{}').get('input',{})
 valid_saved,save_error=_validated_realtime_input(key,saved)
 if save_error:
  # Defensive recovery for malformed ACTIVE rows created by an older release:
  # cancel and refund atomically instead of leaving the stake to time out as LOST.
  now=_now();reason={'reason':'invalid_saved_input_refund','detail':save_error,'server_seed':r['server_seed']};out=reason
  q.execute("UPDATE realtime_game_rounds SET status='REFUNDED',finished_at=?,outcome_json=? WHERE id=? AND status='ACTIVE'",(now,json.dumps(reason,separators=(',',':')),r['id']))
  refunded=q.rowcount==1
  if refunded:
   q.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(r['stake'],uid))
   q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(uid,r['stake'],f"game_{gk}_rt_refund",now))
   q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',(uid,gk,r['stake'],r['stake'],'REFUNDED',json.dumps(out,separators=(',',':')),now))
   _platform_record(q,'game_house_result',0,f"rt:{r['id']}:invalid-refund",'invalid legacy round refunded',now)
  c.commit();c.close();return jsonify({'error':'round input invalid; stake refunded','refunded':refunded}),400
 elapsed=max(0,time.time()-datetime.strptime(r['started_at'],'%Y-%m-%d %H:%M:%S').timestamp())
 if key=='minesx':
  if elapsed>CHICKEN_ROUND_TIMEOUT_SEC:
   _minesx_close_idle(q,r);c.commit();q.execute('SELECT * FROM realtime_game_rounds WHERE id=?',(round_id,));done=q.fetchone();c.close()
   return jsonify({**_rt_payload(done),'ok':True,'timed_out':True,'payout':float(done['stake'] if done['status']=='REFUNDED' else (json.loads(done['outcome_json'] or '{}').get('payout',0)))})
  st=json.loads(r['state_json'] or '{}');k=int(st.get('progress',0));m=int(st['mines']);rtp=float(st.get('rtp',.95));code=f"{gk.upper()}-RT-{round_id:08d}"
  def _logm():q.execute('INSERT INTO realtime_game_actions(round_id,user_id,action,payload_json,created_at) VALUES(?,?,?,?,?)',(round_id,uid,action,json.dumps(b),_now()))
  if action=='cashout':
   if k<1:c.rollback();c.close();return jsonify({'error':'open at least one tile before cashing out'}),400
   payout,out=_minesx_settle(q,r,True,k);_logm();c.commit();c.close()
   return jsonify({'ok':True,'won':True,'payout':payout,'status':'WON','round_id':round_id,'round_code':code,'outcome':out,'server_seed':r['server_seed']})
  tile=b.get('tile');rev=[int(x) for x in st.get('revealed',[])]
  if isinstance(tile,bool) or not isinstance(tile,int) or not 1<=tile<=MINESX_TILES:c.rollback();c.close();return jsonify({'error':'tile must be a whole number from 1 to 25'}),400
  if tile in rev:c.rollback();c.close();return jsonify({'error':'tile already opened'}),400
  layout=_minesx_layout(r['server_seed'],st['input'].get('client_seed',''),m)
  if tile in layout:
   payout,out=_minesx_settle(q,r,False,k,hit=tile);_logm();c.commit();c.close()
   return jsonify({'ok':True,'won':False,'safe':False,'payout':0,'status':'LOST','progress':k,'round_id':round_id,'round_code':code,'outcome':out,'server_seed':r['server_seed']})
  rev.append(tile);k+=1;st['progress']=k;st['revealed']=rev
  if k>=MINESX_TILES-m:
   q.execute("UPDATE realtime_game_rounds SET state_json=? WHERE id=? AND status='ACTIVE'",(json.dumps(st,separators=(',',':')),r['id']));r=dict(r);r['state_json']=json.dumps(st,separators=(',',':'))
   payout,out=_minesx_settle(q,r,True,k,reason='cleared');_logm();c.commit();c.close()
   return jsonify({'ok':True,'won':True,'safe':True,'payout':payout,'status':'WON','progress':k,'round_id':round_id,'round_code':code,'outcome':out,'server_seed':r['server_seed']})
  q.execute("UPDATE realtime_game_rounds SET state_json=? WHERE id=? AND status='ACTIVE'",(json.dumps(st,separators=(',',':')),r['id']));_logm();c.commit();c.close()
  return jsonify({'ok':True,'safe':True,'status':'ACTIVE','progress':k,'revealed':rev,'multiplier':round(_minesx_multiplier(m,k,rtp),4),'potential_payout':_minesx_payout(r['stake'],m,k,rtp),'next_multiplier':round(_minesx_multiplier(m,k+1,rtp),4),'round_id':round_id,'round_code':code})
 if key in ROAD_GAMES:
  if elapsed>CHICKEN_ROUND_TIMEOUT_SEC:
   _chicken_close_idle(q,r);c.commit();q.execute('SELECT * FROM realtime_game_rounds WHERE id=?',(round_id,));done=q.fetchone();c.close()
   return jsonify({**_rt_payload(done),'ok':True,'timed_out':True,'payout':float(done['stake'] if done['status']=='REFUNDED' else (json.loads(done['outcome_json'] or '{}').get('payout',0)))})
  st=json.loads(r['state_json'] or '{}');prog=int(st.get('progress',0));lv=st['input']['difficulty'];rtp=float(st.get('rtp',.95));S=int(r['crash_point']);code=f"{key.upper()}-RT-{round_id:08d}"
  def _log():q.execute('INSERT INTO realtime_game_actions(round_id,user_id,action,payload_json,created_at) VALUES(?,?,?,?,?)',(round_id,uid,action,json.dumps(b),_now()))
  if action=='cashout':
   if prog<1:c.rollback();c.close();return jsonify({'error':'take at least one step before cashing out'}),400
   payout,out=_chicken_settle(q,r,True,prog);_log();c.commit();c.close()
   return jsonify({'ok':True,'won':True,'payout':payout,'status':'WON','round_id':round_id,'round_code':code,'outcome':out,'server_seed':r['server_seed']})
  MX=ROAD_CFG[key][0]
  if prog>=MX:c.rollback();c.close();return jsonify({'error':'maximum steps reached; cash out'}),400
  new=prog+1
  if new>S:
   payout,out=_chicken_settle(q,r,False,prog,hit_step=new);_log();c.commit();c.close()
   return jsonify({'ok':True,'won':False,'safe':False,'payout':0,'status':'LOST','progress':prog,'round_id':round_id,'round_code':code,'outcome':out,'server_seed':r['server_seed']})
  if new>=MX:
   payout,out=_chicken_settle(q,r,True,new,reason='max_steps');_log();c.commit();c.close()
   return jsonify({'ok':True,'won':True,'safe':True,'payout':payout,'status':'WON','progress':new,'round_id':round_id,'round_code':code,'outcome':out,'server_seed':r['server_seed']})
  st['progress']=new;q.execute("UPDATE realtime_game_rounds SET state_json=? WHERE id=? AND status='ACTIVE'",(json.dumps(st,separators=(',',':')),r['id']));_log();c.commit();c.close()
  m=_chicken_multiplier(lv,new,rtp,key)
  return jsonify({'ok':True,'safe':True,'status':'ACTIVE','progress':new,'multiplier':round(m,4),'potential_payout':_chicken_payout(r['stake'],lv,new,rtp,key),'next_multiplier':round(_chicken_multiplier(lv,min(new+1,MX),rtp,key),4),'round_id':round_id,'round_code':code})
 if elapsed>REALTIME_ROUND_TIMEOUT_SEC and key not in CRASH_GAMES:
  now=_now();out={'reason':'timeout_refund','server_seed':r['server_seed'],'refunded':True,'payout':float(r['stake'])}
  q.execute("UPDATE realtime_game_rounds SET status='REFUNDED',finished_at=?,outcome_json=? WHERE id=? AND status='ACTIVE'",(now,json.dumps(out,separators=(',',':')),r['id']))
  if q.rowcount==1:
   q.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(r['stake'],uid))
   q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(uid,r['stake'],f"game_{gk}_rt_refund",now))
   q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',(uid,gk,r['stake'],r['stake'],'REFUNDED',json.dumps(out,separators=(',',':')),now))
   _platform_record(q,'game_house_result',0,f"rt:{r['id']}:timeout-refund",'expired round refunded',now)
  c.commit();c.close();return jsonify({'ok':True,'won':False,'refunded':True,'payout':float(r['stake']),'status':'REFUNDED','reason':'timeout','round_id':round_id,'server_seed':r['server_seed']})
 if key in ('aviator','jet'):
  edge=float(json.loads(r['state_json']).get('house_edge',.05));rtp=round(1-edge,4)
  cur=min(float(r['crash_point']),max(1.0,100.0**(elapsed/max(1.0,REALTIME_ROUND_TIMEOUT_SEC))))
  _at=_auto_target(r)
  if _at is not None and cur>=_at:cur=_at   # auto cash-out was reached first: pay exactly the target
  if action!='cashout':c.rollback();c.close();return jsonify({'error':'cashout required','live_multiplier':round(cur,2)}),400
  if cur>=float(r['crash_point']):
   out={'crash':r['crash_point'],'cashout':round(cur,2),'server_seed':r['server_seed'],'effective_multiplier':0.0,'rtp':rtp}
   _finish(q,r,False,0,out);c.commit();c.close();return jsonify({'ok':True,'won':False,'payout':0,'status':'LOST','crash':r['crash_point'],'server_seed':r['server_seed'],'effective_multiplier':0.0,'rtp':rtp,'outcome':out})
  payout=round(min(MAX_ROUND_PAYOUT_ETB,r['stake']*cur),2);out={'cashout':round(payout/float(r['stake']),2),'crash':r['crash_point'],'server_seed':r['server_seed'],'effective_multiplier':round(payout/float(r['stake']),4),'rtp':rtp,'payout':payout}
  _finish(q,r,True,payout,out);c.commit();c.close();return jsonify({'ok':True,'won':True,'payout':payout,'status':'WON','cashout':round(cur,2),'server_seed':r['server_seed'],'round_code':f'{gk.upper()}-RT-{round_id:08d}','effective_multiplier':out['effective_multiplier'],'rtp':rtp,'outcome':out})
 inp=valid_saved;rng=random.Random(int(hashlib.sha256(f"{r['server_seed']}:{valid_saved.get('client_seed','')}:{action}:{round_id}".encode()).hexdigest()[:16],16));o={'action':action,'server_seed':r['server_seed']};won=False;payout=0
 if key=='dice2':
  d1,d2=rng.randint(1,6),rng.randint(1,6);md,tg=inp['mode'],int(inp['target']);pp=dice2_chance(md,tg);won=dice2_won(md,tg,d1+d2);o.update(dice=[d1,d2],total=d1+d2,mode=md,target=tg,chance=round(pp,6));payout=r['stake']/pp if won else 0
 elif key=='dice':o.update(roll=rng.randint(1,6),guess=int(inp.get('guess',0)));won=o['roll']==o['guess'];payout=r['stake']*5.7 if won else 0
 elif key=='triplegold':
  pos=[rng.randrange(_tg.N) for _ in range(3)];gr_=_tg.grid(pos);m=_tg.line_multiplier(gr_[1]);o.update(positions=pos,grid=[[_tg.NAMES[x] for x in row] for row in gr_],line=[_tg.NAMES[x] for x in gr_[1]],multiplier=m,win_line=1 if m>0 else None);won=m>0;payout=r['stake']*m
 elif key=='buffalo':
  def _bfspin():
   sp_=[rng.randrange(_bf.N) for _ in range(5)];w_=_bf.ways_wins(sp_)
   return sp_,[[_bf.NAMES[x] for x in row] for row in _bf.grid(sp_)],[{'symbol':_bf.NAMES[x[0]],'reels':x[1],'ways':x[2],'multiple':x[3]} for x in w_],sum(x[3] for x in w_)
  bp,bg,bw,bm=_bfspin();bsc=_bf.scatter_count(bp);nfs=_bf.FREE_SPINS.get(bsc,0);frs=[];fm=0.0
  for _ in range(nfs):
   fp_,fg_,fw_,fb_=_bfspin();frs.append({'positions':fp_,'grid':fg_,'wins':fw_,'multiple':fb_*_bf.FS_MULT});fm+=fb_*_bf.FS_MULT
  m=bm+fm;o.update(positions=bp,grid=bg,wins=bw,scatters=bsc,free_spins=nfs,free_spin_rounds=frs,base_multiple=bm,feature_multiple=fm,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='aztec':
  zp=[rng.randrange(_az.N) for _ in range(3)];zg=_az.grid(zp);zw=_az.line_wins(zp);m=sum(x[2] for x in zw)/_az.LINE_COUNT
  o.update(positions=zp,grid=[[_az.NAMES[x] for x in row] for row in zg],wins=[{'line':x[0],'symbol':_az.NAMES[x[1]],'line_multiple':x[2]} for x in zw],win_lines=[x[0] for x in zw],lines=_az.LINE_COUNT,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='roast':
  rp=[rng.randrange(_ro.N) for _ in range(3)];rg=_ro.grid(rp);rw=_ro.line_wins(rp);m=sum(x[2] for x in rw)/_ro.LINE_COUNT
  o.update(positions=rp,grid=[[_ro.NAMES[x] for x in row] for row in rg],wins=[{'line':x[0],'symbol':_ro.NAMES[x[1]],'line_multiple':x[2]} for x in rw],win_lines=[x[0] for x in rw],lines=_ro.LINE_COUNT,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='flame':
  spins=[];tot=0.0;nspin=1
  while True:
   fp=[rng.randrange(_fl.N) for _ in range(3)];fl=_fl.spin_line(fp);fm=_fl.line_multiplier(fl);spins.append({'positions':fp,'line':[_fl.NAMES[x] for x in fl],'base_multiplier':fm});tot+=fm
   if nspin==1 and rng.randrange(_fl.HOT_ONE_IN)==0:nspin=2;continue
   break
  o.update(spins=spins,hot_respin=len(spins)==2,multiplier=tot);won=tot>0;payout=r['stake']*tot
 elif key=='slot':so,m=_sl.spin_round(rng);o.update(so);o['multiplier']=m;won=m>0;payout=r['stake']*m
 elif key=='wheel':o['sector']=rng.randint(1,len(_wheel_prizes()));o['multiplier']=_wheel_prizes()[o['sector']-1];won=o['multiplier']>0;payout=r['stake']*o['multiplier']
 elif key=='keno' and inp.get('grid')==80:
  sel=sorted(int(x) for x in inp['numbers']);draw=sorted(rng.sample(range(1,KENO80_POOL+1),KENO80_DRAW));h=len(set(sel)&set(draw));m=keno80_nominal(len(sel))[h]
  o.update(draw=draw,selected=sel,hits=h,multiplier=m,grid=80,keno_mode='80');won=m>0;payout=r['stake']*m
 elif key=='keno':
  selected=inp.get('numbers',[])
  try:selected=[int(x) for x in selected]
  except (TypeError,ValueError):selected=[]
  if len(selected)!=5 or len(set(selected))!=5 or any(x<1 or x>20 for x in selected):
   c.rollback();c.close();return jsonify({'error':'Keno requires exactly 5 unique numbers from 1-20'}),400
  o['draw']=sorted(rng.sample(range(1,21),5));o['selected']=sorted(selected);h=len(set(selected)&set(o['draw']));m=KENO_PAYTABLE.get(h,0);o.update(hits=h,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='plinko' and inp.get('risk'):
  rk,rw=inp['risk'],int(inp['rows']);path=[rng.randint(0,1) for _ in range(rw)];k=sum(path);m=plinko_nominal(rk,rw)[k]
  o.update(path=path,landing_slot=k,multiplier=m,risk=rk,rows=rw,plinko_mode='binomial');won=m>0;payout=r['stake']*m
 elif key=='plinko':
  slots=[0,.5,.8,1,1.2,1.5,2,3,5];bucket=rng.randint(0,8);ones=set(rng.sample(range(8),bucket));path=[1 if i in ones else 0 for i in range(8)];m=slots[sum(path)];o.update(path=path,landing_slot=sum(path),multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='mines':
  try:mc=int(inp.get('mines',3));pick=int(inp.get('pick',1))
  except (TypeError,ValueError):
   c.rollback();c.close();return jsonify({'error':'mines must be 1-8 and pick must be 1-25'}),400
  if not 1<=mc<=8 or not 1<=pick<=25:
   c.rollback();c.close();return jsonify({'error':'mines must be 1-8 and pick must be 1-25'}),400
  mins=sorted(rng.sample(range(1,26),mc));won=pick not in mins;m=round(25/(25-mc),2);o.update(pick=pick,mine_positions=mins,mine_count=mc,safe=won,multiplier=m);payout=r['stake']*m if won else 0
 elif key=='fish':m=rng.choice(FISH_TABLE);o.update(shot=int(inp.get('shot',1)),multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='roulette':
  bet=inp.get('bet');val=inp.get('value');spin=rng.randrange(ROULETTE_POCKETS);m=roulette_multiplier(spin,bet,val);o.update(spin=spin,label=roulette_label(spin),color=roulette_color(spin),bet=bet,value=val,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='fastkeno':
  sel=[int(x) for x in inp.get('numbers',[])]
  if not FASTKENO_PICK_MIN<=len(sel)<=FASTKENO_PICK_MAX or len(set(sel))!=len(sel) or any(x<1 or x>FASTKENO_POOL for x in sel):
   c.rollback();c.close();return jsonify({'error':'invalid Fast Keno numbers'}),400
  draw=rng.sample(range(1,FASTKENO_POOL+1),FASTKENO_DRAW);h=len(set(sel)&set(draw));m=FASTKENO_PAYTABLES[len(sel)].get(h,0);o.update(draw=draw,selected=sorted(sel),picks=len(sel),hits=h,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='bingo':
  card=bingo_make_card(rng);draws=rng.sample(range(1,76),BINGO_DRAWS);n,done,marked=bingo_score(card,draws);m=bingo_multiplier(n);o.update(card=card,draws=draws,lines=n,line_ids=done,marked=marked,multiplier=m);won=m>0;payout=r['stake']*m
 elif key=='dragontiger':
  ch=inp.get('choice','dragon');d=dt_deal(rng);push=d['winner']=='tie' and ch!='tie';won=d['winner']==ch;o.update(d);o.update(choice=ch,push=push);payout=r['stake']*DT_M[ch] if won else (float(r['stake']) if push else 0)
 elif key=='andarbahar':
  ch=inp.get('choice','andar');d=ab_deal(rng);won=d['winner']==ch;o.update(d);o.update(choice=ch);payout=r['stake']*AB_M[ch] if won else 0
 elif key=='baccarat':
  ch=inp.get('choice','player');d=bacc_deal(rng);push=d['winner']=='tie' and ch!='tie';won=d['winner']==ch;o.update(d);o.update(choice=ch,push=push);payout=r['stake']*BACC_M[ch] if won else (float(r['stake']) if push else 0)
 elif key=='coinflip':ch=inp.get('choice','heads');fl=rng.choice(['heads','tails']);won=fl==ch;o.update(flip=fl,choice=ch);payout=r['stake']*2.0 if won else 0
 elif key=='penalty':ch=inp.get('choice','center');kp=rng.choice(['left','center','right']);won=kp!=ch;o.update(keeper=kp,choice=ch,goal=won);payout=r['stake']*1.5 if won else 0
 elif key=='card':card=rng.randint(1,13);ch=inp.get('choice','high');won=(ch=='high' and card>=8) or (ch=='low' and card<=6);o.update(card=card,choice=ch);payout=r['stake']*1.85 if won else 0
 edge=float(json.loads(r['state_json']).get('house_edge',.05));
 if key in ('aviator','jet'):o['house_edge']=edge
 base_multiplier=o.get('multiplier');payout,scale=_apply_cabinet_house_edge(key,r['stake'],payout,o,edge);payout=min(MAX_ROUND_PAYOUT_ETB,payout)
 if key=='mines' and won:payout=max(float(r['stake']),payout)
 elif payout<float(r['stake']):won=False
 if key=='wheel':o['prizes']=[round(float(v)*scale,4) for v in _wheel_prizes()]
 if base_multiplier is not None:o['base_multiplier']=base_multiplier;o['multiplier']=round(payout/float(r['stake']),4) if payout>0 else 0.0
 o.update(effective_multiplier=round(payout/float(r['stake']),4) if payout>0 else 0.0,house_edge=edge,rtp=round(1-edge,4),payout_scale=scale,server_authoritative=True);_finish(q,r,won,payout,o);q.execute('INSERT INTO realtime_game_actions(round_id,user_id,action,payload_json,created_at) VALUES(?,?,?,?,?)',(round_id,uid,action,json.dumps(b),_now()));c.commit();c.close();return jsonify({'ok':True,'won':won,'payout':payout,'status':'WON' if won else ('PUSH' if (payout>0 and abs(payout-float(r['stake']))<0.005) else 'LOST'),'round_id':round_id,'round_code':f'{gk.upper()}-RT-{round_id:08d}','outcome':o,'server_seed':r['server_seed']})

# Embedded WebRTC signaling: media stays peer-to-peer; server stores only signaling metadata.
@app.route('/api/calls/session',methods=['POST'])
@require_telegram_auth
@require_fresh_auth
def call_session():
 b=request.get_json(silent=True) or {};tx=str(b.get('tx_id') or '').strip();uid=g.tg_user['id'];c=db();q=c.cursor();q.execute("SELECT t.*, p.service_type FROM marketplace_transactions t JOIN marketplace_posts p ON p.post_id=t.post_id WHERE t.tx_id=? AND (t.buyer_id=? OR t.creator_id=?) AND t.status='held_in_escrow'",(tx,uid,uid));t=q.fetchone()
 if not tx or not t or t['service_type'] not in ('video_call','audio_call'):c.close();return jsonify({'error':'eligible call purchase not found'}),400
 q.execute("SELECT * FROM call_sessions WHERE tx_id=? AND status<>'ended' ORDER BY created_at DESC LIMIT 1",(tx,));existing=q.fetchone()
 if existing:
  sid=existing['id'];exp=datetime.strptime(existing['expires_at'],'%Y-%m-%d %H:%M:%S')
 else:
  sid=uuid.uuid4().hex;now=datetime.now();exp=now+timedelta(seconds=CALL_SESSION_TIMEOUT_SEC);q.execute('INSERT INTO call_sessions(id,tx_id,buyer_id,seller_id,media_type,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)',(sid,tx,t['buyer_id'],t['creator_id'],t['service_type'],'waiting',now.strftime('%Y-%m-%d %H:%M:%S'),exp.strftime('%Y-%m-%d %H:%M:%S')))
 c.commit();c.close();ice=[{'urls':'stun:stun.l.google.com:19302'}]
 if TURN_URL and TURN_USERNAME and TURN_CREDENTIAL:ice.append({'urls':TURN_URL,'username':TURN_USERNAME,'credential':TURN_CREDENTIAL})
 return jsonify({'session_id':sid,'role':'buyer' if uid==t['buyer_id'] else 'seller','buyer_id':t['buyer_id'],'seller_id':t['creator_id'],'media_type':t['service_type'],'status':existing['status'] if existing else 'waiting','expires_at':exp.strftime('%Y-%m-%d %H:%M:%S'),'ice_servers':ice,'turn_configured':bool(TURN_URL and TURN_USERNAME and TURN_CREDENTIAL)})

@app.route('/api/calls/<sid>/signal',methods=['POST'])
@require_telegram_auth
@require_fresh_auth
def call_signal(sid):
 b=request.get_json(silent=True) or {};uid=g.tg_user['id'];typ=str(b.get('type') or 'candidate');payload=b.get('payload')
 if typ not in ('offer','answer','candidate'):return jsonify({'error':'invalid signal type'}),400
 raw=json.dumps(payload,separators=(',',':'))
 if len(raw.encode('utf-8'))>65536:return jsonify({'error':'signal payload too large'}),413
 c=db();q=c.cursor();q.execute('SELECT * FROM call_sessions WHERE id=? AND (buyer_id=? OR seller_id=?)',(sid,uid,uid));s=q.fetchone()
 if not s:c.close();return jsonify({'error':'call session not found'}),404
 now=datetime.now();exp=datetime.strptime(s['expires_at'],'%Y-%m-%d %H:%M:%S')
 if s['status']=='ended' or now>exp:
  if s['status']!='ended':q.execute("UPDATE call_sessions SET status='ended',ended_at=? WHERE id=?",(_now(),sid));c.commit()
  c.close();return jsonify({'error':'call session expired or ended'}),410
 q.execute('INSERT INTO call_signals(session_id,sender_id,signal_type,payload_json,created_at) VALUES(?,?,?,?,?)',(sid,uid,typ,raw,_now()));q.execute("UPDATE call_sessions SET status='connecting',started_at=COALESCE(started_at,?) WHERE id=?",(_now(),sid));c.commit();c.close();return jsonify({'ok':True})
@app.route('/api/calls/<sid>/signals')
@require_telegram_auth
def call_signals(sid):
 uid=g.tg_user['id'];after=max(0,int(request.args.get('after',0)));c=db();q=c.cursor();q.execute('SELECT * FROM call_sessions WHERE id=? AND (buyer_id=? OR seller_id=?)',(sid,uid,uid));s=q.fetchone()
 if not s:c.close();return jsonify({'error':'call session not found'}),404
 now=datetime.now();exp=datetime.strptime(s['expires_at'],'%Y-%m-%d %H:%M:%S')
 if s['status']=='ended' or now>exp:
  if s['status']!='ended':q.execute("UPDATE call_sessions SET status='ended',ended_at=? WHERE id=?",(_now(),sid));c.commit()
  c.close();return jsonify({'error':'call session expired or ended'}),410
 q.execute('SELECT id,sender_id,signal_type,payload_json,created_at FROM call_signals WHERE session_id=? AND id>? AND sender_id<>? ORDER BY id ASC LIMIT 100',(sid,after,uid));rows=[dict(x) for x in q.fetchall()];c.close()
 for x in rows:
  try:x['payload']=json.loads(x.pop('payload_json'))
  except Exception:x['payload']=None
 return jsonify({'signals':rows,'status':s['status']})
@app.route('/api/calls/<sid>/end',methods=['POST'])
@require_telegram_auth
def call_end(sid):
 uid=g.tg_user['id'];c=db();q=c.cursor();q.execute("UPDATE call_sessions SET status='ended',ended_at=? WHERE id=? AND (buyer_id=? OR seller_id=?)",(_now(),sid,uid,uid));c.commit();c.close();return jsonify({'ok':True})

# Provider-neutral payment E2E contract. Live gateway is enabled only with provider credentials.
@app.route('/api/payments/intent',methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=5, window_seconds=60)
def payment_intent():
 b=request.get_json(silent=True)
 if not isinstance(b,dict):return jsonify({'error':'request body must be a JSON object'}),400
 if set(b)-{'amount','client_reference'}:return jsonify({'error':'unsupported payment intent fields'}),400
 try:amount=parse_money(b.get('amount'),'amount')
 except (TypeError,ValueError,OverflowError):return jsonify({'error':'invalid amount'}),400
 if not math.isfinite(amount) or amount<=0:return jsonify({'error':'amount must be positive'}),400
 iid=uuid.uuid4().hex;now=_now();c=db();q=c.cursor();q.execute('INSERT INTO payment_intents(id,user_id,amount,provider,status,created_at,updated_at,metadata_json) VALUES(?,?,?,?,?,?,?,?)',(iid,g.tg_user['id'],amount,PAYMENT_PROVIDER,'created',now,now,json.dumps({'client_reference':str(b.get('client_reference',''))[:100]})));c.commit();c.close();return jsonify({'intent_id':iid,'provider':PAYMENT_PROVIDER,'status':'created','live_provider_ready':PAYMENT_PROVIDER!='manual'})

@app.route('/api/payments/webhook',methods=['POST'])
def payment_webhook():
 raw=request.get_data();sig=request.headers.get('X-Payment-Signature','')
 expected=hmac.new(PAYMENT_WEBHOOK_SECRET.encode('utf-8'),raw,hashlib.sha256).hexdigest() if PAYMENT_WEBHOOK_SECRET else ''
 try:
  sig_ok=hmac.compare_digest(sig.encode('utf-8'),expected.encode('ascii'))
 except (TypeError, UnicodeEncodeError):
  sig_ok=False
 if not PAYMENT_WEBHOOK_SECRET or not sig_ok:return jsonify({'error':'invalid webhook signature'}),401
 try:
  b=json.loads(raw.decode('utf-8'))
 except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
  return jsonify({'error':'invalid JSON'}),400
 if not isinstance(b,dict):
  return jsonify({'error':'JSON body must be an object'}),400
 iid=str(b.get('intent_id',''));status=str(b.get('status',''))
 if status not in ('paid','failed','cancelled'):return jsonify({'error':'invalid status'}),400
 c=db();q=c.cursor();q.execute('BEGIN IMMEDIATE');intent=q.execute('SELECT * FROM payment_intents WHERE id=?',(iid,)).fetchone()
 if not intent:c.rollback();c.close();return jsonify({'error':'payment intent not found'}),404
 if status=='paid':
  try: paid_amount=parse_money(b.get('amount'),'amount')
  except Exception: c.rollback();c.close();return jsonify({'error':'paid amount is required'}),400
  if round(float(intent['amount']),2)!=paid_amount:c.rollback();c.close();return jsonify({'error':'payment amount mismatch'}),400
  if not intent['credited_at']:
   now=_now();q.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(intent['amount'],intent['user_id']))
   if q.rowcount!=1:c.rollback();c.close();return jsonify({'error':'user wallet not found'}),404
   q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(intent['user_id'],intent['amount'],'deposit_provider',now))
   q.execute('UPDATE payment_intents SET status=?,provider_ref=?,updated_at=?,credited_at=? WHERE id=? AND credited_at IS NULL',('paid',str(b.get('provider_ref','')),now,now,iid))
  else:
   q.execute('UPDATE payment_intents SET status=?,provider_ref=?,updated_at=? WHERE id=?',('paid',str(b.get('provider_ref','')), _now(),iid))
 else:
  q.execute('UPDATE payment_intents SET status=?,provider_ref=?,updated_at=? WHERE id=? AND credited_at IS NULL',(status,str(b.get('provider_ref','')),_now(),iid))
 c.commit();c.close();return jsonify({'ok':True,'credited':status=='paid'})
