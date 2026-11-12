"""Turnover rule (behavioural) + sports cutoff / bankroll guard (source contracts)."""
import ast, sqlite3
from pathlib import Path
R=Path(__file__).resolve().parent
api=(R/'webapp_api.py').read_text(encoding='utf-8'); rt=(R/'realtime_engine_v3.py').read_text(encoding='utf-8')
fn=[n for n in ast.parse(api).body if isinstance(n,ast.FunctionDef) and n.name=='_turnover_shortfall'][0]
def load(mult):
    ns={'WITHDRAW_TURNOVER_MULTIPLIER':mult}; exec(compile(ast.Module(body=[fn],type_ignores=[]),'<p>','exec'),ns); return ns['_turnover_shortfall']
c=sqlite3.connect(':memory:'); c.execute('CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INT,amount REAL,transaction_type TEXT,created_at TEXT)')
rows=[(1,100,'deposit'),(1,50,'deposit_chapa'),(1,30,'deposit_bonus'),(1,-40,'game_dice_rt_stake'),(1,-10,'sports_bet'),(1,-5,'withdraw'),(1,25,'game_dice_rt_payout')]
c.executemany("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,'x')",rows); cur=c.cursor()
assert load(0)(cur,1)==0, 'disabled rule must allow'
s=load(1)(cur,1); assert s==100.0, f'1x of 150 real deposits, 50 wagered => 100 short, got {s}'   # bonus & withdraw & payouts excluded
c.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(1,-100,'number_guess_bet','x')")
assert load(1)(cur,1)==0.0, 'once wagered enough, withdrawal allowed'
sp=api[api.index('def place_sports_bet'):api.index('# Number Game: instant solo round')]
assert 'betting for this match is closed' in sp and 'closes_at' in sp, 'sports cutoff missing in bet path'
assert sp.index('BEGIN IMMEDIATE')<sp.index('closes_at'), 'cutoff must be checked inside the transaction'
assert "closes_at IS NOT NULL AND closes_at > ?" in api, 'closed matches must be hidden from listing'
assert '/api/admin/sports/close' in api
st=rt[rt.index('def rt_start('):rt.index("@app.route('/api/games/<key>/round/<int:round_id>/state'")]
assert 'PLATFORM_BANKROLL_ETB' in st and st.index('PLATFORM_BANKROLL_ETB')<st.index("UPDATE users SET balance=balance-?"), 'bankroll guard must run before stake debit'
print('RISK_CONTROLS_REGRESSION=PASS')
