# live_keno40_v1.py -- loaded by webapp_api.py via exec() after live_engine_v1.py (shares its globals).
#
# LIVE FAST KENO FAMILY: Fast Keno ('fastkeno'), Power Keno ('keno_power'), Insta Keno ('keno_insta').
# Same rules as the solo Fast Keno (pick 1-8 of 40, 10 balls drawn, FASTKENO_PAYTABLES scaled to the configured house edge),
# but every player shares ONE draw per game on the global 60 s clock:
#   0 .. K40_BET_SEC            betting window
#   K40_BET_SEC .. +K40_DRAW_SEC  10 balls revealed one per second
#   rest                        result on screen, then the next draw starts at :00
# Draw = random.Random(HMAC_SHA256(LIVE_SECRET, "<game>:<round_no>")).sample(1..40, 10) -> exists before bets but cannot be known;
# commit = sha256(seed) is shown during betting, the seed is revealed afterwards. Each game has its own draw, limits and house edge.
LIVE40_KEYS = ('fastkeno', 'keno_power', 'keno_insta')
K40_BET_SEC = 40
K40_DRAW_SEC = 10
K40_POOL, K40_DRAW, K40_MAXPICK = FASTKENO_POOL, FASTKENO_DRAW, FASTKENO_PICK_MAX


def _k40_draw(gk, round_no):
    return random.Random(_live_seed(gk, round_no)).sample(range(1, K40_POOL + 1), K40_DRAW)


def _k40_table(picks, edge):
    base = FASTKENO_RTP_BY_PICKS[picks]; scale = (1.0 - float(edge)) / base
    t = FASTKENO_PAYTABLES[picks]
    return [round(min(1000.0, t.get(h, 0.0) * scale), 4) for h in range(picks + 1)]


def _k40_tables(edge):
    return {str(n): _k40_table(n, edge) for n in range(1, K40_MAXPICK + 1)}


def _k40_init():
    c = db(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS live_keno40_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, game_key TEXT NOT NULL,
        round_no INTEGER NOT NULL, user_id INTEGER NOT NULL, stake REAL NOT NULL, picks_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING', hits INTEGER, payout REAL, created_at TEXT NOT NULL, settled_at TEXT)''')
    q.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_live_keno40_bet ON live_keno40_bets(game_key,round_no,user_id)')
    q.execute('CREATE INDEX IF NOT EXISTS idx_live_keno40_pending ON live_keno40_bets(game_key,status,round_no)')
    c.commit(); c.close()


_k40_init()


def _k40_settle(gk):
    cur_no, el, _, _ = _live_clock()
    done_before = cur_no if el >= K40_BET_SEC + K40_DRAW_SEC else cur_no - 1
    c = db(); q = c.cursor()
    q.execute("SELECT * FROM live_keno40_bets WHERE game_key=? AND status='PENDING' AND round_no<=? ORDER BY id LIMIT 500", (gk, done_before))
    rows = q.fetchall(); c.close()
    if not rows: return 0
    _, _, _, edge = _cabinet_limits(gk)
    n_done = 0
    for r in rows:
        try:
            picks = json.loads(r['picks_json']); draw = _k40_draw(gk, r['round_no'])
            hits = len(set(picks) & set(draw)); mult = _k40_table(len(picks), edge)[hits]
            payout = round(min(MAX_ROUND_PAYOUT_ETB, float(r['stake']) * mult), 2)
            st = 'WON' if payout > float(r['stake']) else ('PUSH' if payout > 0 and abs(payout - float(r['stake'])) < 0.005 else 'LOST')
            now = _now(); c = db(); q = c.cursor()
            try:
                q.execute('BEGIN IMMEDIATE')
                q.execute("UPDATE live_keno40_bets SET status=?,hits=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'", (st, hits, payout, now, r['id']))
                if q.rowcount != 1: c.rollback(); c.close(); continue
                if payout:
                    q.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (payout, r['user_id']))
                    q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (r['user_id'], payout, f'game_{gk}_live_payout', now))
                _platform_record(q, 'game_house_result', round(float(r['stake']) - payout, 2), f"live40:{r['id']}", 'live keno settlement', now)
                out = {'round_no': r['round_no'] - LIVE_NO_BASE, 'draw': draw, 'picks': picks, 'hits': hits, 'multiplier': mult, 'payout': payout, 'live': True}
                q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',
                          (r['user_id'], gk, r['stake'], payout, st, json.dumps(out, separators=(',', ':')), now))
                c.commit(); c.close(); n_done += 1
            except Exception:
                try: c.rollback(); c.close()
                except Exception: pass
                logger.warning('live keno40 settle failed bet=%s', r['id'], exc_info=True)
        except Exception:
            logger.warning('live keno40 settle error bet=%s', r['id'], exc_info=True)
    return n_done


def _k40_settler_loop():
    while True:
        time.sleep(2)
        for gk in LIVE40_KEYS:
            try: _k40_settle(gk)
            except Exception: logger.warning('live keno40 settler', exc_info=True)


try:
    import threading as _k40th
    _k40th.Thread(target=_k40_settler_loop, daemon=True, name='live-keno40-settler').start()
except Exception:
    logger.warning('live keno40 settler thread not started', exc_info=True)


def _k40_phase(el):
    if el < K40_BET_SEC: return 'BETTING', K40_BET_SEC - el
    if el < K40_BET_SEC + K40_DRAW_SEC: return 'DRAWING', K40_BET_SEC + K40_DRAW_SEC - el
    return 'RESULT', LIVE_ROUND_SEC - el


@app.route('/api/live40/<gk>/state')
@require_telegram_auth
@rate_limit(max_calls=40, window_seconds=10)
def live40_state(gk):
    if gk not in LIVE40_KEYS: return jsonify({'error': 'unknown game'}), 404
    try: _k40_settle(gk)
    except Exception: logger.warning('live keno40 settle (state) deferred', exc_info=True)
    now_t = time.time(); round_no, el, _, _ = _live_clock(now_t)
    phase, left = _k40_phase(el)
    enabled, mn, mx, edge = _cabinet_limits(gk)
    uid = g.tg_user['id']; seed = _live_seed(gk, round_no)
    shown = 0
    if phase == 'DRAWING': shown = min(K40_DRAW_SEC, int(el - K40_BET_SEC) + 1)
    elif phase == 'RESULT': shown = K40_DRAW
    draw = _k40_draw(gk, round_no)[:shown] if shown else []
    c = db(); q = c.cursor()
    q.execute('SELECT * FROM live_keno40_bets WHERE game_key=? AND user_id=? ORDER BY round_no DESC LIMIT 1', (gk, uid)); mine = q.fetchone()
    q.execute('SELECT COUNT(*),COALESCE(SUM(stake),0) FROM live_keno40_bets WHERE game_key=? AND round_no=?', (gk, round_no)); pc = q.fetchone()
    c.close()
    my = None
    if mine and mine['round_no'] >= round_no - 2:
        settled = mine['status'] != 'PENDING'
        my = {'round_no': mine['round_no'] - LIVE_NO_BASE, 'stake': mine['stake'], 'picks': json.loads(mine['picks_json']), 'status': mine['status'],
              'hits': mine['hits'] if settled else None, 'payout': mine['payout'] if settled else None}
    last = [{'draw_no': rn - LIVE_NO_BASE, 'balls': _k40_draw(gk, rn)} for rn in range(round_no - 1, round_no - 7, -1)]
    return jsonify({'ok': True, 'game': gk, 'draw_no': round_no - LIVE_NO_BASE, 'phase': phase, 'seconds_left': round(left, 1), 'elapsed': round(el, 2),
                    'bet_sec': K40_BET_SEC, 'draw_sec': K40_DRAW_SEC, 'round_sec': LIVE_ROUND_SEC, 'server_time': now_t,
                    'balls': draw, 'balls_total': K40_DRAW, 'commit': hashlib.sha256(seed.encode()).hexdigest(),
                    'players': pc[0], 'total_staked': round(float(pc[1]), 2), 'my_bet': my, 'last': last, 'last_seed': _live_seed(gk, round_no - 1),
                    'tables': _k40_tables(edge), 'pool': K40_POOL, 'max_pick': K40_MAXPICK, 'min_stake': mn, 'max_stake': mx, 'enabled': bool(enabled)})


@app.route('/api/live40/<gk>/bet', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=12, window_seconds=10)
def live40_bet(gk):
    if gk not in LIVE40_KEYS: return jsonify({'error': 'unknown game'}), 404
    b = request.get_json(silent=True) or {}
    try: stake = round(float(b.get('stake')), 2)
    except Exception: return jsonify({'error': 'bad stake'}), 400
    if not math.isfinite(stake): return jsonify({'error': 'bad stake'}), 400
    picks = b.get('numbers')
    if not isinstance(picks, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in picks): return jsonify({'error': 'bad numbers'}), 400
    picks = sorted(set(picks))
    if not 1 <= len(picks) <= K40_MAXPICK or picks[0] < 1 or picks[-1] > K40_POOL: return jsonify({'error': f'pick 1-{K40_MAXPICK} numbers from 1-{K40_POOL}'}), 400
    enabled, mn, mx, edge = _cabinet_limits(gk)
    if not enabled: return jsonify({'error': 'game is temporarily disabled'}), 403
    if not (mn <= stake <= mx): return jsonify({'error': f'stake must be between {mn:.2f} and {mx:.2f}'}), 400
    round_no, el, _, _ = _live_clock()
    if el >= K40_BET_SEC - 1.0: return jsonify({'error': 'betting is closed for this draw - bet on the next one', 'code': 'CLOSED'}), 409
    uid = g.tg_user['id']; now = _now(); c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE')
        q.execute('SELECT 1 FROM live_keno40_bets WHERE game_key=? AND round_no=? AND user_id=?', (gk, round_no, uid))
        if q.fetchone(): c.rollback(); c.close(); return jsonify({'error': 'you already have a bet in this draw'}), 409
        if PLATFORM_BANKROLL_ETB > 0:
            q.execute("SELECT COALESCE(SUM(stake),0) FROM live_keno40_bets WHERE game_key=? AND status='PENDING'", (gk,)); open_stake = float(q.fetchone()[0] or 0)
            worst = max(_k40_table(len(picks), edge))
            if min(MAX_ROUND_PAYOUT_ETB, (open_stake + stake) * worst) > PLATFORM_BANKROLL_ETB * BANKROLL_EXPOSURE_PCT:
                c.rollback(); c.close(); return jsonify({'error': 'table limit reached, please try again shortly'}), 503
        q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (stake, uid, stake))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance'}), 400
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -stake, f'game_{gk}_live_stake', now))
        q.execute('INSERT INTO live_keno40_bets(game_key,round_no,user_id,stake,picks_json,created_at) VALUES(?,?,?,?,?,?)', (gk, round_no, uid, stake, json.dumps(picks), now))
        c.commit(); c.close()
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
    return jsonify({'ok': True, 'draw_no': round_no - LIVE_NO_BASE, 'stake': stake, 'numbers': picks})
