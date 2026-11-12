"""royal_v1: in-app announcements (admin post -> player unread -> seen), player stats / streak / badges, and the
daily mission points claim (needs N stakes today, one claim per day, points never touch the balance)."""
import ast, os, sqlite3, tempfile, types
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent
path = os.path.join(tempfile.mkdtemp(), 't.db')
def db():
    c = sqlite3.connect(path); c.row_factory = sqlite3.Row; return c
c = db()
c.execute('CREATE TABLE transactions(id INTEGER PRIMARY KEY, user_id INT, amount REAL, transaction_type TEXT, payment_id INT, created_at TEXT)')
c.execute('CREATE TABLE users(user_id INT PRIMARY KEY, balance REAL DEFAULT 0, referred_by INT)')
c.execute('INSERT INTO users(user_id,balance) VALUES (1,100)'); c.commit(); c.close()

class _App:
    def route(self, *a, **k): return lambda f: f
class _Req: method = 'GET'; _json = {}
    
state = types.SimpleNamespace(json={}, method='GET')
class Req:
    @property
    def method(self): return state.method
    def get_json(self, silent=True): return state.json
G = types.SimpleNamespace(tg_user={'id': 1})
ident = lambda f: f
jsonify = lambda d, code=200: (d, code)
ns = dict(app=_App(), db=db, g=G, request=Req(), jsonify=jsonify, require_telegram_auth=ident, require_admin=ident,
          os=os, datetime=datetime, timedelta=timedelta, _now=lambda: datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
          _log_admin_action=lambda *a, **k: None)
r9 = ast.parse((ROOT / 'rewards_v9.py').read_text(encoding='utf-8'))
keep = [n for n in r9.body if (isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'LEVELS') or (isinstance(n, ast.FunctionDef) and n.name == '_level_for')]
exec(compile(ast.Module(body=keep, type_ignores=[]), '<r9>', 'exec'), ns)
exec(compile((ROOT / 'royal_v1.py').read_text(encoding='utf-8'), 'royal_v1.py', 'exec'), ns)

# ---- announcements ----
assert ns['royal_announcements']()[0]['items'] == []
state.method = 'POST'; state.json = {'body': '  '}
assert ns['royal_admin_announcements']()[1] == 400                       # empty refused
state.json = {'title': 'Bonus', 'body': 'Weekend bonus!', 'link_page': 'wheel', 'pinned': True}
assert ns['royal_admin_announcements']()[0]['ok']
state.json = {'body': 'New game', 'link_page': 'javascript:alert(1)'}
ns['royal_admin_announcements']()
r = ns['royal_announcements']()[0]
assert len(r['items']) == 2 and r['unread'] == 2 and r['items'][0]['pinned'] == 1, r      # pinned first
assert r['items'][1]['link_page'] == '', 'unsafe link must be dropped'
ns['royal_announcements_seen']()
assert ns['royal_announcements']()[0]['unread'] == 0
ns['royal_add_announcement']('later', 'T', 'game:keno')
assert ns['royal_announcements']()[0]['unread'] == 1                      # only the new one is unread
ns['royal_admin_announcement_delete'](1)
assert all(i['id'] != 1 for i in ns['royal_announcements']()[0]['items'])

# ---- stats / streak / mission ----
now = datetime.now(timezone.utc)
def tx(amount, typ, days_ago=0):
    c = db(); c.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES (1,?,?,?)',
                        (amount, typ, (now - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S'))); c.commit(); c.close()
tx(-10, 'game_dice_stake'); tx(25, 'game_dice_payout'); tx(-10, 'game_keno_stake')
s = ns['royal_summary']()[0]
assert s['games_played'] == 2 and s['wins'] == 1 and s['streak'] == 1, s
m = s['mission']; assert m['target'] == 5 and m['played'] == 2 and not m['claimable']
res = ns['royal_mission_claim'](); assert res[1] == 400, res                  # not enough games yet
for _ in range(3): tx(-5, 'game_slot_stake')
tx(-5, 'game_dice_stake', days_ago=1); tx(-5, 'game_dice_stake', days_ago=2)
s = ns['royal_summary']()[0]
assert s['streak'] == 3 and s['mission']['claimable'], s
assert 'streak_3' in [b['key'] for b in s['badges'] if b['earned']]
a = ns['royal_mission_claim'](); assert a[0]['ok'] and a[0]['points'] == 100, a
b = ns['royal_mission_claim'](); assert b[1] == 409, b                         # second claim same day refused
s = ns['royal_summary']()[0]; assert s['points'] == 100 and s['mission']['claimed'] and not s['mission']['claimable']
bal = db().execute('SELECT balance FROM users WHERE user_id=1').fetchone()[0]
assert bal == 100, 'points must never change the cash balance'
print('ROYAL_V1_REGRESSION=PASS (announcements+unread; link whitelist; stats; streak; mission claim once/day; balance untouched)')
