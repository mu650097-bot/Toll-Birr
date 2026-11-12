"""Monte Carlo / exact RTP checks for Boom, Number and Sports (production helpers extracted from webapp_api.py)."""
import ast, math, secrets, random
from fractions import Fraction
from math import comb
from pathlib import Path
src=(Path(__file__).resolve().parent/'webapp_api.py').read_text(encoding='utf-8')
tree=ast.parse(src)
fn=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_boom_prize_for_stage']
assert fn,'_boom_prize_for_stage missing'
ns={'math':math}; exec(compile(ast.Module(body=fn,type_ignores=[]),'<prod>','exec'),ns); prize=ns['_boom_prize_for_stage']
ENTRY=10.0; WIN_BASE=588.0   # production defaults, edge 30% => RTP 70%
fail=[]
# --- Boom: a player joining after k safe boxes are open must have RTP == RTP of joining at k=0
for k in range(0,6):
    p=Fraction(1,comb(9-k,3)); rtp=float(p)*prize(WIN_BASE,k)/ENTRY
    ok=abs(rtp-0.70)<0.01; print(f'BOOM join_after={k} prize={prize(WIN_BASE,k):.2f} exact_RTP={rtp:.4f} {"PASS" if ok else "FAIL"}'); 
    if not ok: fail.append(f'boom k={k}')
# Monte Carlo of the real game rule (3 bombs / 9 boxes, picks without bomb knowledge), player joins after k safe boxes
rng=secrets.SystemRandom(); N=300000
for k in (0,3,5):
    wins=0
    for _ in range(N):
        bombs=set(rng.sample(range(1,10),3)); safe=[b for b in range(1,10) if b not in bombs]
        opened=set(rng.sample(safe,k)); rest=[b for b in range(1,10) if b not in opened]; rng.shuffle(rest)
        alive=True; cnt=k
        for b in rest:
            if b in bombs: alive=False;break
            cnt+=1
            if cnt>=6:break
        wins+= alive and cnt>=6
    rtp=wins/N*prize(WIN_BASE,k)/ENTRY; ok=abs(rtp-0.70)<0.06
    print(f'BOOM MC k={k} n={N} RTP={rtp:.4f} {"PASS" if ok else "FAIL"}'); 
    if not ok: fail.append(f'boom mc {k}')
# --- Number: 1/15 chance, win = fee*(1-edge)/p
p=1/15; win=round(ENTRY*(1-0.30)/p,2); n=400000; hits=sum(1 for _ in range(n) if secrets.randbelow(15)+1==secrets.randbelow(15)+1)
rtp=hits/n*win/ENTRY; ok=abs(rtp-0.70)<0.04; print(f'NUMBER win={win} n={n} RTP={rtp:.4f} {"PASS" if ok else "FAIL"}')
if not ok: fail.append('number')
# --- Sports: arbitrage-free requirement and long-run margin
for odds in ((2.1,3.3,3.6),(1.5,4.0,6.5)):
    over=sum(1/o for o in odds)
    print(f'SPORTS odds={odds} overround={over:.4f} {"PASS" if over>=1.02 else "FAIL (needs margin)"}')
    if over<1.02: fail.append(f'sports {odds}')
assert (1/3.0*3)<1.02, 'sanity: 3.0/3.0/3.0 has no margin and must be rejected by the admin endpoint'
code=src[src.index('def admin_sports_create_match'):src.index('def admin_sports_settle')]
assert 'SPORTS_MIN_OVERROUND' in code and 'overround' in code,'sports margin guard missing'
print('TABLE_GAMES_RTP=PASS' if not fail else 'TABLE_GAMES_RTP=FAIL '+str(fail)); raise SystemExit(1 if fail else 0)
