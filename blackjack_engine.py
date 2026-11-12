# blackjack_engine.py -- loaded by webapp_api.py via exec() with its globals (same pattern as realtime_engine_v3.py).
# Server-authoritative, provably-fair Blackjack: 6 decks, dealer stands on all 17, blackjack pays 3:2, double on any
# two cards, no split / insurance / surrender. The shoe is a deterministic shuffle of sha256(server_seed:client_seed),
# committed (hash) at the deal and revealed when the round ends. Payouts carry the disclosed house-edge haircut.
import hashlib, json, os, secrets, time
from datetime import datetime, timedelta

BJ_TIMEOUT_SEC = int(os.getenv('BLACKJACK_TIMEOUT_SEC', '300'))

def _bj_init():
    c = db(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS blackjack_rounds(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, stake REAL NOT NULL, total_stake REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE', seed_commit TEXT NOT NULL, server_seed TEXT NOT NULL, client_seed TEXT NOT NULL DEFAULT '',
        state_json TEXT NOT NULL, outcome_json TEXT, payout REAL, house_edge REAL NOT NULL DEFAULT 0.05,
        started_at TEXT NOT NULL, finished_at TEXT)''')
    q.execute('CREATE INDEX IF NOT EXISTS idx_bj_user_status ON blackjack_rounds(user_id,status,id DESC)')
    c.commit(); c.close()
_bj_init()

def _bj_mults(edge):
    k = 1.0 - float(edge)
    return {'win': round(BJ_NOMINAL_WIN * k, 4), 'blackjack': round(BJ_NOMINAL_BJ * k, 4), 'push': 1.0}

def _bj_public(r):
    """Client-safe view: while ACTIVE the dealer's hole card is never sent."""
    st = json.loads(r['state_json']); active = r['status'] == 'ACTIVE'
    player = st['player']; dealer = st['dealer']
    x = {'round_id': r['id'], 'round_code': f"BLACKJACK-{r['id']:08d}", 'status': r['status'], 'stake': r['stake'], 'total_stake': r['total_stake'],
         'seed_commit': r['seed_commit'], 'player': player, 'player_total': bj_value(player), 'house_edge': r['house_edge'],
         'multipliers': _bj_mults(r['house_edge']), 'started_at': r['started_at'], 'server_authoritative': True}
    if active:
        x.update(dealer=[dealer[0]], dealer_hidden=1, dealer_total=bj_card_val(dealer[0]),
                 actions=['hit', 'stand'] + (['double'] if len(player) == 2 else []))
    else:
        out = json.loads(r['outcome_json'] or '{}')
        x.update(dealer=dealer, dealer_hidden=0, dealer_total=bj_value(dealer), actions=[], outcome=out, payout=r['payout'],
                 won=r['status'] == 'WON', result=out.get('result'), server_seed=r['server_seed'], client_seed=r['client_seed'])
    return x

def _bj_settle(q, r, st, result):
    """Pay (or not) and close the round inside the caller's transaction. Returns the finished row."""
    edge = float(r['house_edge']); total = float(r['total_stake'])
    payout = min(MAX_ROUND_PAYOUT_ETB, bj_payout(total, result, edge)); now = _now()
    won = payout > total + 0.005
    status = 'WON' if won else ('PUSH' if (payout > 0 and abs(payout - total) < 0.005) else 'LOST')
    out = {'result': result, 'doubled': bool(st.get('doubled')), 'player': st['player'], 'dealer': st['dealer'],
           'player_total': bj_value(st['player']), 'dealer_total': bj_value(st['dealer']), 'payout': payout,
           'effective_multiplier': round(payout / total, 4) if payout > 0 else 0.0, 'house_edge': edge, 'rtp': round(1 - edge, 4),
           'server_seed': r['server_seed'], 'client_seed': r['client_seed'], 'decks': BJ_DECKS, 'server_authoritative': True}
    q.execute("UPDATE blackjack_rounds SET status=?,payout=?,outcome_json=?,state_json=?,finished_at=? WHERE id=? AND status='ACTIVE'",
              (status, payout, json.dumps(out, separators=(',', ':')), json.dumps(st, separators=(',', ':')), now, r['id']))
    if q.rowcount != 1: return False
    if payout > 0:
        q.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (payout, r['user_id']))
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (r['user_id'], payout, 'game_blackjack_rt_payout', now))
    _platform_record(q, 'game_house_result', round(total - payout, 2), f"bj:{r['id']}", 'blackjack settlement', now)
    q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',
              (r['user_id'], 'blackjack', total, payout, status, json.dumps(out, separators=(',', ':')), now))
    return True

def _bj_auto_stand(q, r):
    """Abandoned/expired round: the player STANDS on the current hand (never a free refund, never a free loss)."""
    st = json.loads(r['state_json']); shoe = bj_shoe(r['server_seed'], r['client_seed'])
    if bj_value(st['player']) <= 21:
        st['dealer'], st['pos'] = bj_dealer_play(shoe, st['pos'], st['dealer'])
    return _bj_settle(q, r, st, bj_result(st['player'], st['dealer'], st.get('doubled', False)))

def _bj_sweep(q, uid=None):
    cutoff = (datetime.now() - timedelta(seconds=BJ_TIMEOUT_SEC)).strftime('%Y-%m-%d %H:%M:%S')
    if uid is None: q.execute("SELECT * FROM blackjack_rounds WHERE status='ACTIVE' AND started_at<? LIMIT 50", (cutoff,))
    else: q.execute("SELECT * FROM blackjack_rounds WHERE status='ACTIVE' AND user_id=? AND started_at<?", (uid, cutoff))
    for r in q.fetchall(): _bj_auto_stand(q, r)

def _bj_load(q, round_id, uid):
    q.execute('SELECT * FROM blackjack_rounds WHERE id=? AND user_id=?', (round_id, uid)); return q.fetchone()

def _bj_clean_start(raw):
    if not isinstance(raw, dict) or set(raw) - {'stake', 'client_seed'}: return None, 'request body must contain only stake and client_seed'
    try: stake = round(float(raw.get('stake')), 2)
    except (TypeError, ValueError): return None, 'stake must be a number'
    if not (stake > 0) or stake != stake or stake == float('inf'): return None, 'stake must be a positive number'
    cs = str(raw.get('client_seed') or '')[:64]
    return {'stake': stake, 'client_seed': cs}, None

@app.route('/api/blackjack/start', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=12, window_seconds=10)
def bj_start():
    b, err = _bj_clean_start(request.get_json(silent=True))
    if err: return jsonify({'error': err}), 400
    enabled, mn, mx, edge = _cabinet_limits('blackjack')
    if not enabled: return jsonify({'error': 'game is temporarily disabled'}), 403
    stake = b['stake']
    if stake < mn or stake > mx: return jsonify({'error': f'stake must be between {mn:.2f} and {mx:.2f}'}), 400
    uid = g.tg_user['id']; seed = secrets.token_hex(32); commit = hashlib.sha256(seed.encode()).hexdigest(); now = _now()
    c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE'); _bj_sweep(q)
        q.execute("SELECT * FROM blackjack_rounds WHERE user_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1", (uid,)); old = q.fetchone()
        if old:   # never charge twice: resume the hand in progress
            c.commit(); pub = _bj_public(old); c.close(); pub['recovered'] = True; return jsonify({'ok': True, **pub})
        q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (stake, uid, stake))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance'}), 400
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -stake, 'game_blackjack_rt_stake', now))
        shoe = bj_shoe(seed, b['client_seed'])
        st = {'pos': 4, 'player': [shoe[0], shoe[2]], 'dealer': [shoe[1], shoe[3]], 'doubled': False}
        q.execute('INSERT INTO blackjack_rounds(user_id,stake,total_stake,seed_commit,server_seed,client_seed,state_json,house_edge,started_at) VALUES(?,?,?,?,?,?,?,?,?)',
                  (uid, stake, stake, commit, seed, b['client_seed'], json.dumps(st, separators=(',', ':')), edge, now))
        rid = q.lastrowid; q.execute('SELECT * FROM blackjack_rounds WHERE id=?', (rid,)); r = q.fetchone()
        up_val = bj_card_val(st['dealer'][0])
        if bj_is_blackjack(st['player']) or (up_val >= 10 and bj_is_blackjack(st['dealer'])):   # natural(s) end the hand immediately
            _bj_settle(q, r, st, bj_result(st['player'], st['dealer']))
            q.execute('SELECT * FROM blackjack_rounds WHERE id=?', (rid,)); r = q.fetchone()
        c.commit(); pub = _bj_public(r); c.close()
        return jsonify({'ok': True, **pub})
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise

@app.route('/api/blackjack/active')
@require_telegram_auth
def bj_active():
    c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE'); _bj_sweep(q, g.tg_user['id'])
        q.execute("SELECT * FROM blackjack_rounds WHERE user_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1", (g.tg_user['id'],)); r = q.fetchone()
        c.commit(); res = _bj_public(r) if r else {'active': False}; c.close(); return jsonify(res)
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise

@app.route('/api/blackjack/<int:round_id>/action', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=30, window_seconds=10)
def bj_action(round_id):
    b = request.get_json(silent=True)
    if not isinstance(b, dict) or set(b) - {'action', 'seq'}: return jsonify({'error': 'request body must contain only action and seq'}), 400
    action = str(b.get('action', '')).lower()
    if action not in ('hit', 'stand', 'double'): return jsonify({'error': 'invalid action'}), 400
    uid = g.tg_user['id']; c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE'); r = _bj_load(q, round_id, uid)
        if not r: c.rollback(); c.close(); return jsonify({'error': 'round not found'}), 404
        if r['status'] != 'ACTIVE': pub = _bj_public(r); c.rollback(); c.close(); return jsonify({'ok': False, 'error': 'round already finished', **pub}), 409
        if time.time() - datetime.strptime(r['started_at'], '%Y-%m-%d %H:%M:%S').timestamp() > BJ_TIMEOUT_SEC:
            _bj_auto_stand(q, r); q.execute('SELECT * FROM blackjack_rounds WHERE id=?', (round_id,)); r = q.fetchone()
            c.commit(); pub = _bj_public(r); c.close(); return jsonify({'ok': True, 'timed_out': True, **pub})
        st = json.loads(r['state_json']); shoe = bj_shoe(r['server_seed'], r['client_seed'])
        if b.get('seq') is not None and int(b.get('seq')) != len(st['player']):   # stale / duplicate tap: never act twice
            pub = _bj_public(r); c.rollback(); c.close(); return jsonify({'ok': False, 'error': 'stale action', **pub}), 409
        if action == 'double':
            if len(st['player']) != 2: c.rollback(); c.close(); return jsonify({'error': 'double is only allowed on your first two cards'}), 400
            extra = float(r['stake']); q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (extra, uid, extra))
            if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance to double'}), 400
            q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -extra, 'game_blackjack_rt_stake', _now()))
            q.execute('UPDATE blackjack_rounds SET total_stake=total_stake+? WHERE id=?', (extra, round_id))
            q.execute('SELECT * FROM blackjack_rounds WHERE id=?', (round_id,)); r = q.fetchone()
            st['player'].append(shoe[st['pos']]); st['pos'] += 1; st['doubled'] = True
            finish = True
        elif action == 'hit':
            st['player'].append(shoe[st['pos']]); st['pos'] += 1
            finish = bj_value(st['player']) >= 21      # bust ends it; 21 stands automatically
        else:
            finish = True
        if finish:
            if bj_value(st['player']) <= 21: st['dealer'], st['pos'] = bj_dealer_play(shoe, st['pos'], st['dealer'])
            _bj_settle(q, r, st, bj_result(st['player'], st['dealer'], st.get('doubled', False)))
        else:
            q.execute("UPDATE blackjack_rounds SET state_json=? WHERE id=? AND status='ACTIVE'", (json.dumps(st, separators=(',', ':')), round_id))
        q.execute('SELECT * FROM blackjack_rounds WHERE id=?', (round_id,)); r = q.fetchone()
        c.commit(); pub = _bj_public(r); c.close()
        return jsonify({'ok': True, **pub})
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
