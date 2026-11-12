# live_number_v1.py -- loaded by webapp_api.py via exec() right after live_engine_v1.py (shares its globals:
# app, db, _now, require_telegram_auth, require_fresh_auth, rate_limit, _cabinet_limits, _platform_record,
# _get_game_setting, MAX_ROUND_PAYOUT_ETB, PLATFORM_BANKROLL_ETB, BANKROLL_EXPOSURE_PCT, logger, LIVE_ROUND_SEC, _live_seed ...).
#
# LIVE NUMBER GAME. Same global clock as every other live game: a new round every 60 s for ALL players.
#   0 .. NM_BET_SEC       betting window (countdown shown in the app)
#   NM_BET_SEC .. 60      the draw is revealed, bets are settled, result is on screen
# The drawn number (1-4) is a pure function of (server secret, round number):
#   seed = HMAC_SHA256(LIVE_SECRET, "number:<round_no>")   -> draw = 1 + int(seed[:16],16) % 4
# commit = sha256(seed) is shown during betting, the seed is revealed after the round (verifiable, nobody can change it).
# Fixed odds, uniform draw, so expected return = RTP for ANY betting pattern:
#   number 1/2/3/4 -> pays  4*(1-edge)  (x3.8 at the default 5% edge)
#   odd / even / high(3,4) -> pays 2*(1-edge)  (x1.9)
# One bet per (round, user, selection); a player may back several selections in the same round.
NM_GAME = 'number'
NM_BET_SEC = 50
NM_SELECTIONS = ('1', '2', '3', '4', 'odd', 'even', 'high')
NM_MAX_BETS_PER_ROUND = 7


def _nm_draw(round_no):
    return 1 + int(_live_seed(NM_GAME, round_no)[:16], 16) % 4


def _nm_hit(sel, n):
    if sel in ('1', '2', '3', '4'): return int(sel) == n
    if sel == 'odd': return n % 2 == 1
    if sel == 'even': return n % 2 == 0
    if sel == 'high': return n >= 3
    return False


def _nm_mults(edge):
    keep = 1.0 - float(edge)
    num = round(4 * keep, 2); half = round(2 * keep, 2)
    return {'1': num, '2': num, '3': num, '4': num, 'odd': half, 'even': half, 'high': half}


def _nm_limits():
    """enabled flag comes from the admin Number Game switch; stake limits / edge from cabinet settings (defaults 1..10000, 5%)."""
    try: on = bool(_get_game_setting('number')['enabled'])
    except Exception: on = True
    enabled, mn, mx, edge = _cabinet_limits(NM_GAME)
    return (enabled and on), mn, mx, edge


def _nm_init():
    c = db(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS live_number_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, round_no INTEGER NOT NULL,
        user_id INTEGER NOT NULL, sel TEXT NOT NULL, stake REAL NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
        mult REAL, payout REAL, created_at TEXT NOT NULL, settled_at TEXT)''')
    q.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_live_number_bet ON live_number_bets(round_no,user_id,sel)')
    q.execute('CREATE INDEX IF NOT EXISTS idx_live_number_pending ON live_number_bets(status,round_no)')
    c.commit(); c.close()


_nm_init()


def _nm_settle():
    """Settle every PENDING bet whose draw has been revealed. Idempotent (status guard) -> safe from many workers."""
    cur_no, el, _, _ = _live_clock()
    done_before = cur_no if el >= NM_BET_SEC else cur_no - 1
    c = db(); q = c.cursor()
    q.execute("SELECT * FROM live_number_bets WHERE status='PENDING' AND round_no<=? ORDER BY id LIMIT 1000", (done_before,))
    rows = q.fetchall(); c.close()
    if not rows: return 0
    _, _, _, edge = _nm_limits()
    mults = _nm_mults(edge)
    n_done = 0
    for r in rows:
        try:
            draw = _nm_draw(r['round_no']); mult = mults[r['sel']]
            won = _nm_hit(r['sel'], draw)
            payout = round(min(MAX_ROUND_PAYOUT_ETB, float(r['stake']) * mult), 2) if won else 0.0
            st = 'WON' if won else 'LOST'
            now = _now(); c = db(); q = c.cursor()
            try:
                q.execute('BEGIN IMMEDIATE')
                q.execute("UPDATE live_number_bets SET status=?,mult=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'", (st, mult, payout, now, r['id']))
                if q.rowcount != 1: c.rollback(); c.close(); continue
                if payout:
                    q.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (payout, r['user_id']))
                    q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (r['user_id'], payout, 'game_number_live_payout', now))
                _platform_record(q, 'game_house_result', round(float(r['stake']) - payout, 2), f"livenum:{r['id']}", 'live number settlement', now)
                out = {'round_no': r['round_no'] - LIVE_NO_BASE, 'draw': draw, 'sel': r['sel'], 'multiplier': mult, 'payout': payout, 'live': True}
                q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',
                          (r['user_id'], NM_GAME, r['stake'], payout, st, json.dumps(out, separators=(',', ':')), now))
                c.commit(); c.close(); n_done += 1
            except Exception:
                try: c.rollback(); c.close()
                except Exception: pass
                logger.warning('live number settle failed bet=%s', r['id'], exc_info=True)
        except Exception:
            logger.warning('live number settle error bet=%s', r['id'], exc_info=True)
    return n_done


def _nm_settler_loop():
    while True:
        time.sleep(2)
        try: _nm_settle()
        except Exception: logger.warning('live number settler', exc_info=True)


try:
    import threading as _nmth
    _nmth.Thread(target=_nm_settler_loop, daemon=True, name='live-number-settler').start()
except Exception:
    logger.warning('live number settler thread not started', exc_info=True)


@app.route('/api/live-number/state')
@require_telegram_auth
@rate_limit(max_calls=40, window_seconds=10)
def live_number_state():
    try: _nm_settle()
    except Exception: logger.warning('live number settle (state) deferred', exc_info=True)
    now_t = time.time(); round_no, el, phase, left = _live_clock(now_t)
    revealed = el >= NM_BET_SEC
    betting = not revealed
    left = (NM_BET_SEC - el) if betting else (LIVE_ROUND_SEC - el)
    enabled, mn, mx, edge = _nm_limits()
    uid = g.tg_user['id']
    seed = _live_seed(NM_GAME, round_no)
    c = db(); q = c.cursor()
    q.execute('SELECT sel,stake,status,mult,payout,round_no FROM live_number_bets WHERE user_id=? AND round_no>=? ORDER BY round_no DESC, id', (uid, round_no - 1))
    mine = q.fetchall()
    q.execute('SELECT COUNT(DISTINCT user_id),COALESCE(SUM(stake),0) FROM live_number_bets WHERE round_no=?', (round_no,)); pc = q.fetchone()
    c.close()
    my_now = [{'sel': r['sel'], 'stake': r['stake']} for r in mine if r['round_no'] == round_no]
    prev = [r for r in mine if r['round_no'] == round_no - 1]
    cur_done = [r for r in mine if r['round_no'] == round_no and r['status'] != 'PENDING']
    last_rows = cur_done if (revealed and cur_done) else prev
    my_last = None
    if last_rows:
        rn = last_rows[0]['round_no']
        my_last = {'round_no': rn - LIVE_NO_BASE, 'draw': _nm_draw(rn),
                   'bets': [{'sel': r['sel'], 'stake': r['stake'], 'status': r['status'], 'payout': r['payout']} for r in last_rows],
                   'total_payout': round(sum(float(r['payout'] or 0) for r in last_rows), 2),
                   'total_stake': round(sum(float(r['stake']) for r in last_rows), 2),
                   'settled': all(r['status'] != 'PENDING' for r in last_rows)}
    first_hist = round_no if revealed else round_no - 1
    history = [{'round_no': rn - LIVE_NO_BASE, 'draw': _nm_draw(rn)} for rn in range(first_hist, first_hist - 12, -1)]
    return jsonify({'ok': True, 'game': NM_GAME, 'round_no': round_no - LIVE_NO_BASE, 'phase': 'RESULT' if revealed else 'BETTING',
                    'seconds_left': round(max(0.0, left), 1), 'bet_sec': NM_BET_SEC, 'round_sec': LIVE_ROUND_SEC, 'server_time': now_t,
                    'result': _nm_draw(round_no) if revealed else None, 'commit': hashlib.sha256(seed.encode()).hexdigest(),
                    'last_seed': _live_seed(NM_GAME, round_no - 1), 'players': pc[0], 'total_staked': round(float(pc[1]), 2),
                    'my_bets': my_now, 'my_last': my_last, 'history': history, 'mults': _nm_mults(edge),
                    'min_stake': mn, 'max_stake': mx, 'enabled': bool(enabled)})


@app.route('/api/live-number/bet', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=15, window_seconds=10)
def live_number_bet():
    b = request.get_json(silent=True) or {}
    try: stake = round(float(b.get('stake')), 2)
    except Exception: return jsonify({'error': 'bad stake'}), 400
    if not math.isfinite(stake): return jsonify({'error': 'bad stake'}), 400
    sel = str(b.get('sel', '')).strip().lower()
    if sel not in NM_SELECTIONS: return jsonify({'error': 'bad selection'}), 400
    enabled, mn, mx, edge = _nm_limits()
    if not enabled: return jsonify({'error': 'Number Game is currently disabled'}), 403
    if not (mn <= stake <= mx): return jsonify({'error': f'stake must be between {mn:.2f} and {mx:.2f}'}), 400
    round_no, el, phase, left = _live_clock()
    if el >= NM_BET_SEC - 1.0: return jsonify({'error': 'betting is closed for this round - bet on the next one', 'code': 'CLOSED'}), 409
    mult = _nm_mults(edge)[sel]
    uid = g.tg_user['id']; now = _now(); c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE')
        q.execute('SELECT COUNT(*) FROM live_number_bets WHERE round_no=? AND user_id=?', (round_no, uid))
        if q.fetchone()[0] >= NM_MAX_BETS_PER_ROUND: c.rollback(); c.close(); return jsonify({'error': 'too many bets in this round'}), 409
        q.execute('SELECT 1 FROM live_number_bets WHERE round_no=? AND user_id=? AND sel=?', (round_no, uid, sel))
        if q.fetchone(): c.rollback(); c.close(); return jsonify({'error': 'you already have a bet on this option in this round'}), 409
        if PLATFORM_BANKROLL_ETB > 0:
            q.execute("SELECT COALESCE(SUM(stake),0) FROM live_number_bets WHERE status='PENDING'"); open_stake = float(q.fetchone()[0] or 0)
            if min(MAX_ROUND_PAYOUT_ETB, (open_stake + stake) * mult) > PLATFORM_BANKROLL_ETB * BANKROLL_EXPOSURE_PCT:
                c.rollback(); c.close(); return jsonify({'error': 'table limit reached, please try again shortly'}), 503
        q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (stake, uid, stake))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance'}), 400
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -stake, 'game_number_live_stake', now))
        q.execute('INSERT INTO live_number_bets(round_no,user_id,sel,stake,created_at) VALUES(?,?,?,?,?)', (round_no, uid, sel, stake, now))
        c.commit(); c.close()
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
    return jsonify({'ok': True, 'round_no': round_no - LIVE_NO_BASE, 'sel': sel, 'stake': stake, 'multiplier': mult})
