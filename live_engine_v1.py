# live_engine_v1.py -- loaded by webapp_api.py via exec() (same pattern as realtime_engine_v3.py), so it shares
# its globals: app, db, _now, require_telegram_auth, require_fresh_auth, rate_limit, _cabinet_limits,
# _platform_record, MAX_ROUND_PAYOUT_ETB, logger ...
#
# LIVE SHARED ROUNDS. Every game here runs on ONE global clock: a new round every LIVE_ROUND_SEC (60 s).
# All players see the same round number, the same countdown and the same draw -- the draw is a pure function
# of (server secret, game, round number), so it exists before anyone bets but cannot be known in advance:
#   seed   = HMAC_SHA256(LIVE_SECRET, "<game>:<round_no>")
#   commit = sha256(seed)         -> shown to everybody during the betting window
#   seed is revealed after the round so anyone can recompute the draw.
# Nothing is invented: player counts / totals come from real bets in the DB.
#
# Round timeline (seconds inside the minute):  0..BET_SEC betting | BET_SEC..BET_SEC+DRAW_SEC draw | rest = result.
import hmac as _lhmac

LIVE_ROUND_SEC = 60
LIVE_BET_SEC = 35
LIVE_DRAW_SEC = 20            # Super Keno: one ball per second -> 20 balls
LIVE_NO_BASE = 29_897_000     # only to make the displayed "Draw #" short (round_no = epoch//60)
LIVE_KENO_KEYS = ('keno_super', 'keno')   # Super Keno + the classic Keno tile: both run on the shared 60 s draw (own limits / edge each)


def _live_secret():
    s = os.getenv('LIVE_ROUNDS_SECRET', '').strip()
    if s:
        return s.encode()
    c = db(); q = c.cursor()
    q.execute('CREATE TABLE IF NOT EXISTS live_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)')
    q.execute("SELECT v FROM live_meta WHERE k='secret'"); r = q.fetchone()
    if not r:
        q.execute("INSERT OR IGNORE INTO live_meta(k,v) VALUES('secret',?)", (secrets.token_hex(32),)); c.commit()
        q.execute("SELECT v FROM live_meta WHERE k='secret'"); r = q.fetchone()
    c.close()
    return r[0].encode()


_LIVE_SECRET_CACHE = {}


def _live_seed(gk, round_no):
    if 's' not in _LIVE_SECRET_CACHE:
        _LIVE_SECRET_CACHE['s'] = _live_secret()
    return _lhmac.new(_LIVE_SECRET_CACHE['s'], f'{gk}:{round_no}'.encode(), hashlib.sha256).hexdigest()


def _live_init():
    c = db(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS live_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, game_key TEXT NOT NULL,
        round_no INTEGER NOT NULL, user_id INTEGER NOT NULL, stake REAL NOT NULL, picks_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'PENDING', hits INTEGER, payout REAL, created_at TEXT NOT NULL, settled_at TEXT)''')
    q.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_live_bet ON live_bets(game_key,round_no,user_id)')
    q.execute('CREATE INDEX IF NOT EXISTS idx_live_pending ON live_bets(game_key,status,round_no)')
    c.commit(); c.close()


_live_init()


def _live_clock(t=None):
    t = time.time() if t is None else t
    round_no = int(t // LIVE_ROUND_SEC)
    el = t - round_no * LIVE_ROUND_SEC
    if el < LIVE_BET_SEC: phase = 'BETTING'; left = LIVE_BET_SEC - el
    elif el < LIVE_BET_SEC + LIVE_DRAW_SEC: phase = 'DRAWING'; left = LIVE_BET_SEC + LIVE_DRAW_SEC - el
    else: phase = 'RESULT'; left = LIVE_ROUND_SEC - el
    return round_no, el, phase, left


def _live_keno_draw(gk, round_no):
    """The 20 balls IN DRAWN ORDER (80 numbers)."""
    rng = random.Random(_live_seed(gk, round_no))
    return rng.sample(range(1, keno_math.POOL + 1), keno_math.DRAW)


def _live_keno_table(gk):
    enabled, mn, mx, edge = _cabinet_limits(gk)
    return {str(n): keno_math.effective_table(n, edge) for n in range(1, keno_math.MAX_PICK + 1)}, enabled, mn, mx, edge


def _live_settle_keno(gk):
    """Settle every PENDING bet whose draw has finished. Idempotent (status guard) -> safe from many workers."""
    cur_no, el, _, _ = _live_clock()
    done_before = cur_no if el >= LIVE_BET_SEC + LIVE_DRAW_SEC else cur_no - 1   # last round whose draw is finished
    c = db(); q = c.cursor()
    q.execute("SELECT * FROM live_bets WHERE game_key=? AND status='PENDING' AND round_no<=? ORDER BY id LIMIT 500", (gk, done_before))
    rows = q.fetchall(); c.close()
    if not rows: return 0
    _, _, _, _, edge = _live_keno_table(gk)
    n_done = 0
    for r in rows:
        try:
            picks = json.loads(r['picks_json']); draw = _live_keno_draw(gk, r['round_no'])
            hits = len(set(picks) & set(draw))
            mult = keno_math.effective_table(len(picks), edge)[hits]
            payout = round(min(MAX_ROUND_PAYOUT_ETB, float(r['stake']) * mult), 2)
            won = payout > float(r['stake']); st = 'WON' if won else ('PUSH' if payout > 0 and abs(payout - float(r['stake'])) < 0.005 else 'LOST')
            now = _now(); c = db(); q = c.cursor()
            try:
                q.execute('BEGIN IMMEDIATE')
                q.execute("UPDATE live_bets SET status=?,hits=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'", (st, hits, payout, now, r['id']))
                if q.rowcount != 1: c.rollback(); c.close(); continue
                if payout:
                    q.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (payout, r['user_id']))
                    q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (r['user_id'], payout, f'game_{gk}_live_payout', now))
                _platform_record(q, 'game_house_result', round(float(r['stake']) - payout, 2), f"live:{r['id']}", 'live round settlement', now)
                out = {'round_no': r['round_no'], 'draw': draw, 'picks': picks, 'hits': hits, 'multiplier': mult, 'payout': payout, 'live': True}
                q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',
                          (r['user_id'], gk, r['stake'], payout, st, json.dumps(out, separators=(',', ':')), now))
                c.commit(); c.close(); n_done += 1
            except Exception:
                try: c.rollback(); c.close()
                except Exception: pass
                logger.warning('live settle failed bet=%s', r['id'], exc_info=True)
        except Exception:
            logger.warning('live settle error bet=%s', r['id'], exc_info=True)
    return n_done


def _live_settler_loop():
    while True:
        time.sleep(2)
        for gk in LIVE_KENO_KEYS:
            try: _live_settle_keno(gk)
            except Exception: logger.warning('live settler', exc_info=True)


try:
    import threading as _lth
    _lth.Thread(target=_live_settler_loop, daemon=True, name='live-settler').start()
except Exception:
    logger.warning('live settler thread not started', exc_info=True)


@app.route('/api/live/<gk>/state')
@require_telegram_auth
@rate_limit(max_calls=40, window_seconds=10)
def live_state(gk):
    if gk not in LIVE_KENO_KEYS: return jsonify({'error': 'unknown game'}), 404
    try: _live_settle_keno(gk)
    except Exception: logger.warning('live settle (state) deferred', exc_info=True)
    now_t = time.time(); round_no, el, phase, left = _live_clock(now_t)
    tables, enabled, mn, mx, edge = _live_keno_table(gk)
    uid = g.tg_user['id']
    seed = _live_seed(gk, round_no)
    shown = 0
    if phase == 'DRAWING': shown = min(LIVE_DRAW_SEC, int(el - LIVE_BET_SEC) + 1)
    elif phase == 'RESULT': shown = LIVE_DRAW_SEC
    draw = _live_keno_draw(gk, round_no)[:shown] if shown else []
    c = db(); q = c.cursor()
    q.execute('SELECT * FROM live_bets WHERE game_key=? AND user_id=? ORDER BY round_no DESC LIMIT 1', (gk, uid)); mine = q.fetchone()
    q.execute("SELECT COUNT(*),COALESCE(SUM(stake),0) FROM live_bets WHERE game_key=? AND round_no=?", (gk, round_no)); pc = q.fetchone()
    c.close()
    my = None
    if mine:
        settled = mine['status'] != 'PENDING'
        if mine['round_no'] >= round_no - 2:
            my = {'round_no': mine['round_no'] - LIVE_NO_BASE, 'stake': mine['stake'], 'picks': json.loads(mine['picks_json']), 'status': mine['status'],
                  'hits': mine['hits'] if settled else None, 'payout': mine['payout'] if settled else None}
    last = []
    for rn in range(round_no - 1, round_no - 7, -1):          # last finished draws (their seeds are revealed)
        last.append({'draw_no': rn - LIVE_NO_BASE, 'balls': _live_keno_draw(gk, rn)})
    return jsonify({'ok': True, 'game': gk, 'draw_no': round_no - LIVE_NO_BASE, 'phase': phase, 'seconds_left': round(left, 1), 'elapsed': round(el, 2),
                    'bet_sec': LIVE_BET_SEC, 'draw_sec': LIVE_DRAW_SEC, 'round_sec': LIVE_ROUND_SEC, 'server_time': now_t,
                    'balls': draw, 'balls_total': keno_math.DRAW, 'commit': hashlib.sha256(seed.encode()).hexdigest(),
                    'players': pc[0], 'total_staked': round(float(pc[1]), 2),
                    'my_bet': my, 'last': last, 'last_seed': _live_seed(gk, round_no - 1),
                    'tables': tables, 'pool': keno_math.POOL, 'max_pick': keno_math.MAX_PICK, 'min_stake': mn, 'max_stake': mx, 'enabled': bool(enabled)})


@app.route('/api/live/<gk>/bet', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=12, window_seconds=10)
def live_bet(gk):
    if gk not in LIVE_KENO_KEYS: return jsonify({'error': 'unknown game'}), 404
    b = request.get_json(silent=True) or {}
    try: stake = round(float(b.get('stake')), 2)
    except Exception: return jsonify({'error': 'bad stake'}), 400
    picks = b.get('numbers')
    if not isinstance(picks, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in picks): return jsonify({'error': 'bad numbers'}), 400
    picks = sorted(set(picks))
    if not 1 <= len(picks) <= keno_math.MAX_PICK or picks[0] < 1 or picks[-1] > keno_math.POOL: return jsonify({'error': f'pick 1-{keno_math.MAX_PICK} numbers from 1-{keno_math.POOL}'}), 400
    enabled, mn, mx, edge = _cabinet_limits(gk)
    if not enabled: return jsonify({'error': 'game is temporarily disabled'}), 403
    if not (mn <= stake <= mx): return jsonify({'error': f'stake must be between {mn:.2f} and {mx:.2f}'}), 400
    round_no, el, phase, left = _live_clock()
    if phase != 'BETTING' or left < 1.0: return jsonify({'error': 'betting is closed for this draw - bet on the next one', 'code': 'CLOSED'}), 409
    uid = g.tg_user['id']; now = _now(); c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE')
        q.execute('SELECT 1 FROM live_bets WHERE game_key=? AND round_no=? AND user_id=?', (gk, round_no, uid))
        if q.fetchone(): c.rollback(); c.close(); return jsonify({'error': 'you already have a bet in this draw'}), 409
        if PLATFORM_BANKROLL_ETB > 0:
            q.execute("SELECT COALESCE(SUM(stake),0) FROM live_bets WHERE game_key=? AND status='PENDING'", (gk,)); open_stake = float(q.fetchone()[0] or 0)
            worst = max(keno_math.effective_table(len(picks), edge))
            if min(MAX_ROUND_PAYOUT_ETB, (open_stake + stake) * worst) > PLATFORM_BANKROLL_ETB * BANKROLL_EXPOSURE_PCT:
                c.rollback(); c.close(); return jsonify({'error': 'table limit reached, please try again shortly'}), 503
        q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (stake, uid, stake))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance'}), 400
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -stake, f'game_{gk}_live_stake', now))
        q.execute('INSERT INTO live_bets(game_key,round_no,user_id,stake,picks_json,created_at) VALUES(?,?,?,?,?,?)', (gk, round_no, uid, stake, json.dumps(picks), now))
        c.commit(); c.close()
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
    return jsonify({'ok': True, 'draw_no': round_no - LIVE_NO_BASE, 'stake': stake, 'numbers': picks})


# =====================================================================================================
# LIVE CRASH (High Flyer). Same global 60 s slot:  0..CR_BET_SEC betting | then ONE shared flight whose
# multiplier is exp(CR_K * t) until the round's crash point | then idle until the minute ends.
# crash = clamp((1-edge)/(1-u), 1, 100) with u from the round seed -> expected return = RTP for ANY cash-out rule.
# The crash point is never sent to clients before it happens.
# =====================================================================================================
LIVE_CRASH_KEYS = ('highflyer', 'skymasters', 'aviator', 'crash', 'jet', 'rocket')   # Aviator / Crash / Rocket / Jet now share ONE flight per minute too
CR_BET_SEC = 15
CR_MAX = 100.0
CR_K = math.log(CR_MAX) / 35.0        # x100 is reached after 35 s of flight -> always fits in the 60 s slot
_ADDIS_OFF = 3 * 3600


def _live_crash_init():
    c = db(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS live_crash_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, game_key TEXT NOT NULL,
        round_no INTEGER NOT NULL, user_id INTEGER NOT NULL, slot TEXT NOT NULL, stake REAL NOT NULL, auto REAL,
        status TEXT NOT NULL DEFAULT 'PENDING', mult REAL, payout REAL, created_at TEXT NOT NULL, settled_at TEXT)''')
    q.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_live_crash_bet ON live_crash_bets(game_key,round_no,user_id,slot)')
    q.execute('CREATE INDEX IF NOT EXISTS idx_live_crash_pending ON live_crash_bets(game_key,status,round_no)')
    c.commit(); c.close()


_live_crash_init()


def _cr_point(gk, round_no, edge):
    h = _live_seed(gk, round_no)
    u = int(h[:13], 16) / float(16 ** 13)                      # [0,1)
    return min(CR_MAX, max(1.0, (1.0 - edge) / (1.0 - u)))


def _cr_floor2(x):
    return math.floor(x * 100 + 1e-9) / 100.0


def _cr_phase(gk, edge, t=None):
    round_no, el, _, _ = _live_clock(t)
    crash = _cr_point(gk, round_no, edge); t_crash = math.log(crash) / CR_K
    if el < CR_BET_SEC: ph = 'BETTING'; left = CR_BET_SEC - el
    elif el < CR_BET_SEC + t_crash: ph = 'FLYING'; left = CR_BET_SEC + t_crash - el
    else: ph = 'CRASHED'; left = LIVE_ROUND_SEC - el
    return round_no, el, ph, left, crash, t_crash


def _cr_credit(q, gk, bet_id, user_id, stake, status, mult, payout, now, round_no, crash):
    if payout: 
        q.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (payout, user_id))
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (user_id, payout, f'game_{gk}_live_payout', now))
    _platform_record(q, 'game_house_result', round(float(stake) - payout, 2), f'livecrash:{bet_id}', 'live crash settlement', now)
    out = {'round_no': round_no, 'crash': round(crash, 2), 'multiplier': mult, 'payout': payout, 'live': True}
    q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',
              (user_id, gk, stake, payout, status, json.dumps(out, separators=(',', ':')), now))


def _live_settle_crash(gk):
    enabled, mn, mx, edge = _cabinet_limits(gk)
    cur_no, el, ph, left, crash_now, t_crash_now = _cr_phase(gk, edge)
    done_before = cur_no if ph == 'CRASHED' else cur_no - 1
    c = db(); q = c.cursor()
    q.execute("SELECT * FROM live_crash_bets WHERE game_key=? AND status='PENDING' AND round_no<=? ORDER BY id LIMIT 500", (gk, done_before))
    rows = q.fetchall(); c.close(); n = 0
    for r in rows:
        try:
            crash = _cr_point(gk, r['round_no'], edge); cf = _cr_floor2(crash)
            auto = r['auto']; won = auto is not None and auto <= cf and auto >= 1.01
            mult = float(auto) if won else 0.0
            payout = round(min(MAX_ROUND_PAYOUT_ETB, float(r['stake']) * mult), 2) if won else 0.0
            st = 'WON' if won else 'LOST'; now = _now(); c = db(); q = c.cursor()
            try:
                q.execute('BEGIN IMMEDIATE')
                q.execute("UPDATE live_crash_bets SET status=?,mult=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'", (st, mult, payout, now, r['id']))
                if q.rowcount != 1: c.rollback(); c.close(); continue
                _cr_credit(q, gk, r['id'], r['user_id'], r['stake'], st, mult, payout, now, r['round_no'], crash)
                c.commit(); c.close(); n += 1
            except Exception:
                try: c.rollback(); c.close()
                except Exception: pass
                logger.warning('live crash settle failed bet=%s', r['id'], exc_info=True)
        except Exception:
            logger.warning('live crash settle error', exc_info=True)
    return n


_CR_BEST = {}


def _cr_best_today(gk, edge, round_no):
    day0 = int((time.time() + _ADDIS_OFF) // 86400) * 86400 - _ADDIS_OFF
    first = int(day0 // LIVE_ROUND_SEC); key = (gk, first)
    ent = _CR_BEST.get(key)
    if ent and ent[0] == round_no: return ent[1]
    start = ent[0] if ent else first
    best = ent[1] if ent else 1.0
    for rn in range(start, round_no):                         # only FINISHED rounds
        best = max(best, _cr_floor2(_cr_point(gk, rn, edge)))
    _CR_BEST.clear(); _CR_BEST[key] = (round_no, best)
    return best


try:
    _prev_loop_started = True
    def _live_crash_settler_loop():
        while True:
            time.sleep(2)
            for gk in LIVE_CRASH_KEYS:
                try: _live_settle_crash(gk)
                except Exception: logger.warning('live crash settler', exc_info=True)
    _lth.Thread(target=_live_crash_settler_loop, daemon=True, name='live-crash-settler').start()
except Exception:
    logger.warning('live crash settler thread not started', exc_info=True)


@app.route('/api/live/<gk>/crash-state')
@require_telegram_auth
@rate_limit(max_calls=60, window_seconds=10)
def live_crash_state(gk):
    if gk not in LIVE_CRASH_KEYS: return jsonify({'error': 'unknown game'}), 404
    try: _live_settle_crash(gk)
    except Exception: logger.warning('live crash settle (state) deferred', exc_info=True)
    enabled, mn, mx, edge = _cabinet_limits(gk)
    t = time.time(); round_no, el, ph, left, crash, t_crash = _cr_phase(gk, edge, t)
    uid = g.tg_user['id']
    mult = None; crashed_at = None
    if ph == 'FLYING': mult = _cr_floor2(math.exp(CR_K * (el - CR_BET_SEC)))
    if ph == 'CRASHED': crashed_at = _cr_floor2(crash)
    c = db(); q = c.cursor()
    q.execute('SELECT * FROM live_crash_bets WHERE game_key=? AND user_id=? AND round_no>=? ORDER BY round_no DESC, slot', (gk, uid, round_no - 1)); mine = q.fetchall()
    q.execute('SELECT COUNT(DISTINCT user_id),COUNT(*),COALESCE(SUM(stake),0) FROM live_crash_bets WHERE game_key=? AND round_no=?', (gk, round_no)); pc = q.fetchone()
    q.execute("SELECT user_id,stake,payout,mult FROM live_crash_bets WHERE game_key=? AND status='WON' AND id>(SELECT COALESCE(MAX(id),0)-3000 FROM live_crash_bets) ORDER BY payout DESC LIMIT 5", (gk,)); top = q.fetchall()
    c.close()
    my = {}
    for r in mine:                                            # newest round wins per slot
        if r['slot'] in my: continue
        my[r['slot']] = {'round_no': r['round_no'] - LIVE_NO_BASE, 'stake': r['stake'], 'auto': r['auto'], 'status': r['status'], 'mult': r['mult'], 'payout': r['payout']}
    last = [_cr_floor2(_cr_point(gk, rn, edge)) for rn in range(round_no - 1, round_no - 9, -1)]
    return jsonify({'ok': True, 'game': gk, 'draw_no': round_no - LIVE_NO_BASE, 'phase': ph, 'seconds_left': round(left, 1), 'elapsed': round(el, 2),
                    'server_time': t, 'flight_start': round_no * LIVE_ROUND_SEC + CR_BET_SEC, 'k': CR_K, 'bet_sec': CR_BET_SEC, 'round_sec': LIVE_ROUND_SEC,
                    'multiplier': mult, 'crash': crashed_at, 'last': last, 'best_today': _cr_best_today(gk, edge, round_no),
                    'players': pc[0], 'bets': pc[1], 'total_staked': round(float(pc[2]), 2), 'my': my,
                    'top': [{'name': '***' + str(r['user_id'])[-2:].rjust(2, '0'), 'mult': r['mult'], 'payout': r['payout']} for r in top],
                    'min_stake': mn, 'max_stake': mx, 'enabled': bool(enabled), 'max_mult': CR_MAX})


@app.route('/api/live/<gk>/crash-bet', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=15, window_seconds=10)
def live_crash_bet(gk):
    if gk not in LIVE_CRASH_KEYS: return jsonify({'error': 'unknown game'}), 404
    b = request.get_json(silent=True) or {}
    slot = b.get('slot')
    if slot not in ('A', 'B'): return jsonify({'error': 'bad slot'}), 400
    try: stake = round(float(b.get('stake')), 2)
    except Exception: return jsonify({'error': 'bad stake'}), 400
    auto = b.get('auto')
    if auto is not None:
        try: auto = round(float(auto), 2)
        except Exception: return jsonify({'error': 'bad auto cash-out'}), 400
        if isinstance(b.get('auto'), bool) or not (1.01 <= auto <= CR_MAX): return jsonify({'error': 'auto cash-out must be between 1.01 and 100'}), 400
    enabled, mn, mx, edge = _cabinet_limits(gk)
    if not enabled: return jsonify({'error': 'game is temporarily disabled'}), 403
    if not (mn <= stake <= mx): return jsonify({'error': f'stake must be between {mn:.2f} and {mx:.2f}'}), 400
    round_no, el, ph, left, _, _ = _cr_phase(gk, edge)
    if ph != 'BETTING' or left < 1.0: return jsonify({'error': 'betting is closed for this round', 'code': 'CLOSED'}), 409
    uid = g.tg_user['id']; now = _now(); c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE')
        q.execute('SELECT 1 FROM live_crash_bets WHERE game_key=? AND round_no=? AND user_id=? AND slot=?', (gk, round_no, uid, slot))
        if q.fetchone(): c.rollback(); c.close(); return jsonify({'error': f'Bet {slot} is already placed in this round'}), 409
        if PLATFORM_BANKROLL_ETB > 0:
            q.execute("SELECT COALESCE(SUM(stake),0) FROM live_crash_bets WHERE game_key=? AND status='PENDING'", (gk,)); open_stake = float(q.fetchone()[0] or 0)
            if min(MAX_ROUND_PAYOUT_ETB, (open_stake + stake) * CR_MAX) > PLATFORM_BANKROLL_ETB * BANKROLL_EXPOSURE_PCT:
                c.rollback(); c.close(); return jsonify({'error': 'table limit reached, please try again shortly'}), 503
        q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (stake, uid, stake))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance'}), 400
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -stake, f'game_{gk}_live_stake', now))
        q.execute('INSERT INTO live_crash_bets(game_key,round_no,user_id,slot,stake,auto,created_at) VALUES(?,?,?,?,?,?,?)', (gk, round_no, uid, slot, stake, auto, now))
        c.commit(); c.close()
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
    return jsonify({'ok': True, 'draw_no': round_no - LIVE_NO_BASE, 'slot': slot, 'stake': stake, 'auto': auto})


@app.route('/api/live/<gk>/cashout', methods=['POST'])
@require_telegram_auth
@rate_limit(max_calls=20, window_seconds=10)
def live_crash_cashout(gk):
    if gk not in LIVE_CRASH_KEYS: return jsonify({'error': 'unknown game'}), 404
    slot = (request.get_json(silent=True) or {}).get('slot')
    if slot not in ('A', 'B'): return jsonify({'error': 'bad slot'}), 400
    enabled, mn, mx, edge = _cabinet_limits(gk)
    t = time.time(); round_no, el, ph, left, crash, t_crash = _cr_phase(gk, edge, t)
    if ph != 'FLYING': return jsonify({'error': 'the plane is not flying', 'code': 'NOT_FLYING'}), 409
    raw = math.exp(CR_K * (el - CR_BET_SEC)); uid = g.tg_user['id']; now = _now(); c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE')
        q.execute("SELECT * FROM live_crash_bets WHERE game_key=? AND round_no=? AND user_id=? AND slot=? AND status='PENDING'", (gk, round_no, uid, slot)); r = q.fetchone()
        if not r: c.rollback(); c.close(); return jsonify({'error': 'no active bet'}), 404
        mult = _cr_floor2(raw)
        if r['auto'] is not None and r['auto'] <= raw: mult = float(r['auto'])     # auto target was already reached
        payout = round(min(MAX_ROUND_PAYOUT_ETB, float(r['stake']) * mult), 2)
        st = 'WON' if payout > float(r['stake']) else ('PUSH' if payout > 0 and abs(payout - float(r['stake'])) < 0.005 else 'LOST')
        q.execute("UPDATE live_crash_bets SET status='WON',mult=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'", (mult, payout, now, r['id']))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'already settled'}), 409
        _cr_credit(q, gk, r['id'], uid, r['stake'], st, mult, payout, now, round_no, crash)
        c.commit(); c.close()
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
    return jsonify({'ok': True, 'slot': slot, 'multiplier': mult, 'payout': payout})


# =====================================================================================================
# LIVE NUMBER GAME (fixed odds, FAST rounds). One shared draw every NUM_ROUND_SEC for ALL players.
# Secret number 1..4 is a pure function of (server secret, round) -> committed before betting, revealed after.
# Targets: "1".."4" pay  4*(1-edge)  (x3.8 at 5%)   |   "odd","even","low","high" pay  2*(1-edge)  (x1.9 at 5%)
# Every target has the SAME expected return (1-edge). A player may back several targets in one round.
# =====================================================================================================
NUM_ROUND_SEC = 30
NUM_BET_SEC = 24                 # last (NUM_ROUND_SEC-NUM_BET_SEC) seconds = reveal
NUM_NO_BASE = 58_700_000         # only to keep the displayed "Round #" short
NUM_KEY = 'number_live'
NUM_TARGETS = ('1', '2', '3', '4', 'odd', 'even', 'low', 'high')


def _num_init():
    c = db(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS live_number_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, round_no INTEGER NOT NULL,
        user_id INTEGER NOT NULL, target TEXT NOT NULL, stake REAL NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
        payout REAL, created_at TEXT NOT NULL, settled_at TEXT)''')
    q.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_live_number_bet ON live_number_bets(round_no,user_id,target)')
    q.execute("CREATE INDEX IF NOT EXISTS idx_live_number_pending ON live_number_bets(status,round_no)")
    q.execute("INSERT OR IGNORE INTO cabinet_game_settings(game_key,house_edge,wheel_prizes,updated_at) VALUES(?,?,?,?)", (NUM_KEY, 0.15, None, _now()))
    c.commit(); c.close()


_num_init()


def _num_clock(t=None):
    t = time.time() if t is None else t
    rn = int(t // NUM_ROUND_SEC); el = t - rn * NUM_ROUND_SEC
    if el < NUM_BET_SEC: ph = 'BETTING'; left = NUM_BET_SEC - el
    else: ph = 'REVEAL'; left = NUM_ROUND_SEC - el
    return rn, el, ph, left


def _num_secret_number(round_no):
    return 1 + int(_live_seed(NUM_KEY, round_no)[:8], 16) % 4


def _num_mult(target, edge):
    return round((4.0 if target in ('1', '2', '3', '4') else 2.0) * (1.0 - edge), 4)


def _num_wins(target, n):
    if target in ('1', '2', '3', '4'): return int(target) == n
    if target == 'odd': return n % 2 == 1
    if target == 'even': return n % 2 == 0
    if target == 'low': return n <= 2
    return n >= 3          # high


def _live_settle_number():
    cur_no, el, ph, _ = _num_clock()
    done_before = cur_no if ph == 'REVEAL' else cur_no - 1
    c = db(); q = c.cursor()
    q.execute("SELECT * FROM live_number_bets WHERE status='PENDING' AND round_no<=? ORDER BY id LIMIT 800", (done_before,))
    rows = q.fetchall(); c.close()
    if not rows: return 0
    _, _, _, edge = _cabinet_limits(NUM_KEY); n_done = 0
    for r in rows:
        try:
            n = _num_secret_number(r['round_no']); won = _num_wins(r['target'], n)
            mult = _num_mult(r['target'], edge) if won else 0.0
            payout = round(min(MAX_ROUND_PAYOUT_ETB, float(r['stake']) * mult), 2) if won else 0.0
            st = 'WON' if won else 'LOST'; now = _now(); c = db(); q = c.cursor()
            try:
                q.execute('BEGIN IMMEDIATE')
                q.execute("UPDATE live_number_bets SET status=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'", (st, payout, now, r['id']))
                if q.rowcount != 1: c.rollback(); c.close(); continue
                if payout:
                    q.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (payout, r['user_id']))
                    q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (r['user_id'], payout, f'game_{NUM_KEY}_live_payout', now))
                _platform_record(q, 'game_house_result', round(float(r['stake']) - payout, 2), f"livenum:{r['id']}", 'live number settlement', now)
                out = {'round_no': r['round_no'] - NUM_NO_BASE, 'secret': n, 'target': r['target'], 'multiplier': mult, 'payout': payout, 'live': True}
                q.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',
                          (r['user_id'], NUM_KEY, r['stake'], payout, st, json.dumps(out, separators=(',', ':')), now))
                c.commit(); c.close(); n_done += 1
            except Exception:
                try: c.rollback(); c.close()
                except Exception: pass
                logger.warning('live number settle failed bet=%s', r['id'], exc_info=True)
        except Exception:
            logger.warning('live number settle error', exc_info=True)
    return n_done


def _live_number_settler_loop():
    while True:
        time.sleep(2)
        try: _live_settle_number()
        except Exception: logger.warning('live number settler', exc_info=True)


try:
    _lth.Thread(target=_live_number_settler_loop, daemon=True, name='live-number-settler').start()
except Exception:
    logger.warning('live number settler thread not started', exc_info=True)


@app.route('/api/live/number/state')
@require_telegram_auth
@rate_limit(max_calls=40, window_seconds=10)
def live_number_state():
    try: _live_settle_number()
    except Exception: logger.warning('live number settle (state) deferred', exc_info=True)
    enabled, mn, mx, edge = _cabinet_limits(NUM_KEY)
    t = time.time(); rn, el, ph, left = _num_clock(t); uid = g.tg_user['id']
    seed = _live_seed(NUM_KEY, rn)
    c = db(); q = c.cursor()
    q.execute('SELECT round_no,target,stake,status,payout FROM live_number_bets WHERE user_id=? AND round_no>=? ORDER BY round_no DESC,id', (uid, rn - 1)); mine = q.fetchall()
    q.execute('SELECT COUNT(DISTINCT user_id),COALESCE(SUM(stake),0) FROM live_number_bets WHERE round_no=?', (rn,)); pc = q.fetchone()
    c.close()
    cur = {}; prev = []
    for r in mine:
        row = {'target': r['target'], 'stake': r['stake'], 'status': r['status'], 'payout': r['payout']}
        if r['round_no'] == rn: cur[r['target']] = row
        else: prev.append(row)
    result = _num_secret_number(rn) if ph == 'REVEAL' else None
    last = [_num_secret_number(x) for x in range(rn - 1, rn - 13, -1)]
    return jsonify({'ok': True, 'game': NUM_KEY, 'round': rn - NUM_NO_BASE, 'phase': ph, 'seconds_left': round(left, 1), 'elapsed': round(el, 2),
                    'bet_sec': NUM_BET_SEC, 'round_sec': NUM_ROUND_SEC, 'server_time': t, 'commit': hashlib.sha256(seed.encode()).hexdigest(),
                    'result': result, 'last': last, 'last_seed': _live_seed(NUM_KEY, rn - 1), 'mine': cur, 'prev': prev,
                    'players': pc[0], 'total_staked': round(float(pc[1]), 2),
                    'pays': {'num': _num_mult('1', edge), 'side': _num_mult('odd', edge)},
                    'min_stake': mn, 'max_stake': mx, 'enabled': bool(enabled)})


@app.route('/api/live/number/bet', methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=20, window_seconds=10)
def live_number_bet():
    b = request.get_json(silent=True) or {}
    target = str(b.get('target', '')).lower()
    if target not in NUM_TARGETS: return jsonify({'error': 'bad target'}), 400
    try: stake = round(float(b.get('stake')), 2)
    except Exception: return jsonify({'error': 'bad stake'}), 400
    if not math.isfinite(stake): return jsonify({'error': 'bad stake'}), 400
    enabled, mn, mx, edge = _cabinet_limits(NUM_KEY)
    if not enabled: return jsonify({'error': 'game is temporarily disabled'}), 403
    if not (mn <= stake <= mx): return jsonify({'error': f'stake must be between {mn:.2f} and {mx:.2f}'}), 400
    rn, el, ph, left = _num_clock()
    if ph != 'BETTING' or left < 1.0: return jsonify({'error': 'betting is closed for this round - bet on the next one', 'code': 'CLOSED'}), 409
    uid = g.tg_user['id']; now = _now(); c = db(); q = c.cursor()
    try:
        q.execute('BEGIN IMMEDIATE')
        q.execute('SELECT 1 FROM live_number_bets WHERE round_no=? AND user_id=? AND target=?', (rn, uid, target))
        if q.fetchone(): c.rollback(); c.close(); return jsonify({'error': 'you already backed this in this round'}), 409
        if PLATFORM_BANKROLL_ETB > 0:
            q.execute("SELECT COALESCE(SUM(stake),0) FROM live_number_bets WHERE status='PENDING'"); open_stake = float(q.fetchone()[0] or 0)
            if min(MAX_ROUND_PAYOUT_ETB, (open_stake + stake) * _num_mult('1', edge)) > PLATFORM_BANKROLL_ETB * BANKROLL_EXPOSURE_PCT:
                c.rollback(); c.close(); return jsonify({'error': 'table limit reached, please try again shortly'}), 503
        q.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?', (stake, uid, stake))
        if q.rowcount != 1: c.rollback(); c.close(); return jsonify({'error': 'insufficient balance'}), 400
        q.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)', (uid, -stake, f'game_{NUM_KEY}_live_stake', now))
        q.execute('INSERT INTO live_number_bets(round_no,user_id,target,stake,created_at) VALUES(?,?,?,?,?)', (rn, uid, target, stake, now))
        c.commit(); c.close()
    except Exception:
        try: c.rollback(); c.close()
        except Exception: pass
        raise
    return jsonify({'ok': True, 'round': rn - NUM_NO_BASE, 'target': target, 'stake': stake})
