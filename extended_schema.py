"""Shared production schema/migrations for the Mini App.
Safe to call from both bot and API processes.
"""
import sqlite3
import time


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def init_extended_schema(db_file, admin_id=0):
    conn = sqlite3.connect(db_file, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=15000')
    conn.execute('PRAGMA journal_mode=WAL')
    cur = conn.cursor()

    # Core tables: allows API-first startup on a fresh database too.
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
        balance REAL DEFAULT 0, banned INTEGER DEFAULT 0, manager INTEGER DEFAULT 0,
        self_excluded_until TEXT, terms_accepted_at TEXT, referred_by INTEGER
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, first_name TEXT,
        amount REAL, status TEXT DEFAULT 'pending', photo_file_id TEXT,
        created_at TEXT, screenshot_hash TEXT, approved_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
        acc_name TEXT, acc_number TEXT, status TEXT DEFAULT 'pending', created_at TEXT,
        screenshot_file_id TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
        transaction_type TEXT, payment_id INTEGER, created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS game_settings (
        key TEXT PRIMARY KEY, entry_fee REAL DEFAULT 10, house_edge REAL DEFAULT 0.30,
        win_amount REAL DEFAULT 0, enabled INTEGER DEFAULT 1, win_probability REAL
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS webapp_number_rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, first_name TEXT,
        guess INTEGER, secret INTEGER, won INTEGER, entry_fee REAL, payout REAL, created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS webapp_boom_rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, bombs INTEGER, opened TEXT, game_over INTEGER,
        entry_fee REAL, win_amount REAL, created_at TEXT, server_seed TEXT, commitment TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS webapp_boom_players (
        id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER, user_id INTEGER,
        name TEXT, status TEXT, joined_at TEXT, win_amount REAL
    )''')
    if 'win_amount' not in {r[1] for r in cur.execute('PRAGMA table_info(webapp_boom_players)').fetchall()}:
        cur.execute('ALTER TABLE webapp_boom_players ADD COLUMN win_amount REAL')
    cur.execute('''CREATE TABLE IF NOT EXISTS sports_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
        odds_home REAL NOT NULL, odds_draw REAL NOT NULL, odds_away REAL NOT NULL,
        status TEXT DEFAULT 'OPEN', result TEXT, created_at TEXT, settled_at TEXT, closes_at TEXT
    )''')
    if 'closes_at' not in {r[1] for r in cur.execute('PRAGMA table_info(sports_matches)').fetchall()}:
        cur.execute('ALTER TABLE sports_matches ADD COLUMN closes_at TEXT')
    cur.execute('''CREATE TABLE IF NOT EXISTS sports_bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        selection TEXT NOT NULL, stake REAL NOT NULL, odds REAL NOT NULL,
        status TEXT DEFAULT 'PENDING', payout REAL DEFAULT 0, created_at TEXT, settled_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS mini_game_rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, game_key TEXT NOT NULL,
        input_json TEXT, outcome_json TEXT, stake REAL NOT NULL, payout REAL NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL
    )''')

    # Marketplace tables/columns needed by the API.
    cur.execute('''CREATE TABLE IF NOT EXISTS marketplace_posts (
        post_id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER, title TEXT,
        service_type TEXT, price REAL, active INTEGER DEFAULT 1,
        description TEXT, sample_file_id TEXT, sample_media_type TEXT,
        sample_message_id INTEGER, created_at TEXT, category TEXT, duration_minutes INTEGER
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS marketplace_transactions (
        tx_id TEXT PRIMARY KEY, buyer_id INTEGER, creator_id INTEGER, post_id INTEGER,
        amount REAL, status TEXT DEFAULT 'held_in_escrow', created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS marketplace_reviews (
        review_id INTEGER PRIMARY KEY AUTOINCREMENT, tx_id TEXT, buyer_id INTEGER,
        creator_id INTEGER, rating INTEGER, comment TEXT, created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS marketplace_reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER, post_id INTEGER,
        creator_id INTEGER, reason TEXT, created_at TEXT, status TEXT DEFAULT 'open'
    )''')

    # Social/Netflix-style marketplace interactions.
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_post_likes (
        post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT,
        PRIMARY KEY(post_id,user_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_post_saves (
        post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT,
        PRIMARY KEY(post_id,user_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_post_views (
        post_id INTEGER NOT NULL, user_id INTEGER, created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_comments (
        comment_id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL, comment TEXT NOT NULL, created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_follows (
        creator_id INTEGER NOT NULL, follower_id INTEGER NOT NULL, created_at TEXT,
        PRIMARY KEY(creator_id,follower_id)
    )""")
    cols = {r[1] for r in cur.execute('PRAGMA table_info(marketplace_posts)').fetchall()}
    if 'media_json' not in cols:
        cur.execute('ALTER TABLE marketplace_posts ADD COLUMN media_json TEXT')
    if 'thumbnail_file_id' not in cols:
        cur.execute('ALTER TABLE marketplace_posts ADD COLUMN thumbnail_file_id TEXT')

    # Migrate the older API-first schema which used withdrawal_id as the
    # primary key.  The application contract is now withdrawals.id.  Keep
    # existing IDs/data instead of silently creating a second incompatible
    # schema.
    withdrawal_cols = {r[1] for r in cur.execute('PRAGMA table_info(withdrawals)').fetchall()}
    if 'id' not in withdrawal_cols and 'withdrawal_id' in withdrawal_cols:
        legacy_cols = {r[1] for r in cur.execute('PRAGMA table_info(withdrawals)').fetchall()}
        cur.execute('ALTER TABLE withdrawals RENAME TO withdrawals_legacy')
        cur.execute('''CREATE TABLE withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
            acc_name TEXT, acc_number TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT, screenshot_file_id TEXT
        )''')
        screenshot_expr = 'screenshot_file_id' if 'screenshot_file_id' in legacy_cols else 'NULL'
        cur.execute(f'''INSERT INTO withdrawals
            (id,user_id,amount,acc_name,acc_number,status,created_at,screenshot_file_id)
            SELECT withdrawal_id,user_id,amount,acc_name,acc_number,status,created_at,{screenshot_expr}
            FROM withdrawals_legacy''')
        cur.execute('DROP TABLE withdrawals_legacy')

    # Add columns to older installations without disturbing existing data.
    def add_col(table, col, typ):
        cols = {r[1] for r in cur.execute(f'PRAGMA table_info({table})').fetchall()}
        if col not in cols:
            cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')

    # Older bot-owned databases may have created game_settings with only
    # the original five columns. Add the newer columns before seeding the
    # unified settings so both startup orders (bot-first or API-first) work.
    add_col('game_settings', 'house_edge', 'REAL DEFAULT 0.30')
    add_col('game_settings', 'win_amount', 'REAL DEFAULT 0')
    add_col('game_settings', 'enabled', 'INTEGER DEFAULT 1')
    add_col('game_settings', 'win_probability', 'REAL')
    add_col('users', 'self_excluded_until', 'TEXT')
    add_col('users', 'terms_accepted_at', 'TEXT')
    add_col('users', 'referred_by', 'INTEGER')
    add_col('payments', 'screenshot_hash', 'TEXT')
    add_col('payments', 'approved_at', 'TEXT')
    add_col('transactions', 'payment_id', 'INTEGER')
    add_col('withdrawals', 'screenshot_file_id', 'TEXT')
    add_col('marketplace_transactions', 'resolution_note', 'TEXT')
    add_col('marketplace_transactions', 'delivery_file_id', 'TEXT')
    add_col('marketplace_transactions', 'delivery_type', 'TEXT')
    add_col('marketplace_transactions', 'delivered_at', 'TEXT')
    add_col('marketplace_transactions', 'delivery_caption', 'TEXT')
    add_col('marketplace_transactions', 'delivery_claim_token', 'TEXT')
    add_col('marketplace_transactions', 'delivery_claimed_at', 'TEXT')
    add_col('withdrawals', 'staff_reminded_at', 'TEXT')
    add_col('marketplace_posts', 'description', 'TEXT')
    add_col('marketplace_posts', 'sample_file_id', 'TEXT')
    add_col('marketplace_posts', 'sample_media_type', 'TEXT')
    add_col('marketplace_posts', 'sample_message_id', 'INTEGER')
    add_col('marketplace_posts', 'created_at', 'TEXT')
    add_col('marketplace_posts', 'category', 'TEXT')
    add_col('marketplace_posts', 'duration_minutes', 'INTEGER')
    add_col('marketplace_posts', 'moderation_status', "TEXT DEFAULT 'pending'")
    add_col('marketplace_posts', 'moderation_note', 'TEXT')
    add_col('marketplace_posts', 'moderated_by', 'INTEGER')
    add_col('marketplace_posts', 'moderated_at', 'TEXT')
    add_col('marketplace_posts', 'price_status', "TEXT DEFAULT 'pending'")
    add_col('marketplace_posts', 'media_status', "TEXT DEFAULT 'pending'")
    add_col('users', 'marketplace_verified', 'INTEGER DEFAULT 0')
    add_col('users', 'marketplace_suspended', 'INTEGER DEFAULT 0')
    add_col('users', 'marketplace_suspension_reason', 'TEXT')
    cur.execute("CREATE TABLE IF NOT EXISTS marketplace_moderation_actions (action_id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL, post_id INTEGER, creator_id INTEGER, media_index INTEGER, action TEXT NOT NULL, reason TEXT, note TEXT, created_at TEXT NOT NULL)")
    cur.execute("CREATE TABLE IF NOT EXISTS marketplace_media_reviews (review_id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL, media_index INTEGER NOT NULL, admin_id INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL, UNIQUE(post_id,media_index))")
    add_col('sports_matches', 'result', 'TEXT')
    add_col('sports_matches', 'settled_at', 'TEXT')
    add_col('sports_matches', 'home_score', 'INTEGER')
    add_col('sports_matches', 'away_score', 'INTEGER')
    add_col('sports_matches', 'live_minute', 'TEXT')
    add_col('sports_matches', 'live_updated_at', 'TEXT')
    add_col('sports_matches', 'league', 'TEXT')
    add_col('sports_matches', 'sport', 'TEXT')
    add_col('sports_matches', 'home_logo', 'TEXT')
    add_col('users', 'bonus_locked', 'REAL DEFAULT 0')
    cur.execute('''CREATE TABLE IF NOT EXISTS invite_bonuses (invitee_id INTEGER PRIMARY KEY, inviter_id INTEGER NOT NULL, amount REAL NOT NULL, created_at TEXT NOT NULL)''')
    # Play-only bonus: whenever balance drops below the locked bonus, the locked part shrinks with it (covers every game).
    cur.execute('''CREATE TRIGGER IF NOT EXISTS trg_bonus_locked_cap AFTER UPDATE OF balance ON users
                   WHEN COALESCE(NEW.bonus_locked,0) > COALESCE(NEW.balance,0)
                   BEGIN UPDATE users SET bonus_locked = MAX(COALESCE(NEW.balance,0),0) WHERE user_id = NEW.user_id; END''')
    add_col('sports_matches', 'away_logo', 'TEXT')
    add_col('sports_bets', 'payout', 'REAL DEFAULT 0')
    add_col('sports_bets', 'settled_at', 'TEXT')

    # Canonical ledger sign: withdrawals are outflows, so their transaction
    # rows must be negative just like game stakes. This is a one-time migration
    # for old releases that stored them positive and compensated in reports.
    cur.execute("UPDATE transactions SET amount=-ABS(amount) WHERE transaction_type='withdraw' AND amount>0")

    # Duplicate-proof deposit screenshots. If an old DB already contains
    # duplicates, preserve the oldest record's hash and clear later duplicates
    # before creating the unique index.
    dupes = cur.execute('''SELECT screenshot_hash FROM payments
                           WHERE screenshot_hash IS NOT NULL AND screenshot_hash != ''
                           GROUP BY screenshot_hash HAVING COUNT(*) > 1''').fetchall()
    for d in dupes:
        rows = cur.execute('SELECT id FROM payments WHERE screenshot_hash=? ORDER BY id', (d[0],)).fetchall()
        for r in rows[1:]:
            cur.execute('UPDATE payments SET screenshot_hash=NULL WHERE id=?', (r[0],))
    cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_screenshot_hash ON payments(screenshot_hash) WHERE screenshot_hash IS NOT NULL')
    cur.execute('''CREATE TABLE IF NOT EXISTS deposit_bonus_settings (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 1, bonus_percent REAL NOT NULL DEFAULT 10.0, delay_hours REAL NOT NULL DEFAULT 6.0, min_deposit REAL NOT NULL DEFAULT 1.0, max_bonus REAL NOT NULL DEFAULT 1000.0, updated_at TEXT)''')
    cur.execute('''INSERT OR IGNORE INTO deposit_bonus_settings (id,enabled,bonus_percent,delay_hours,min_deposit,max_bonus,updated_at) VALUES (1,1,10.0,6.0,1.0,1000.0,?)''', (_now(),))
    cur.execute('''CREATE TABLE IF NOT EXISTS deposit_bonuses (id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id INTEGER NOT NULL UNIQUE, user_id INTEGER NOT NULL, deposit_amount REAL NOT NULL, bonus_percent REAL NOT NULL, bonus_amount REAL NOT NULL, eligible_at TEXT NOT NULL, credited_at TEXT, status TEXT NOT NULL DEFAULT 'scheduled', created_at TEXT NOT NULL)''')
    cur.execute('CREATE INDEX IF NOT EXISTS ix_deposit_bonuses_user_status ON deposit_bonuses(user_id,status,eligible_at)')
    cur.execute('CREATE INDEX IF NOT EXISTS ix_deposit_bonuses_eligible ON deposit_bonuses(status,eligible_at)')
    cur.execute('CREATE INDEX IF NOT EXISTS ix_sports_bets_match_status ON sports_bets(match_id, status)')
    cur.execute('CREATE INDEX IF NOT EXISTS ix_mini_game_rounds_user_game ON mini_game_rounds(user_id, game_key, id DESC)')
    cur.execute('CREATE INDEX IF NOT EXISTS ix_market_delivery_claim ON marketplace_transactions(delivery_claim_token)')

    # Seed settings for all games. Existing values are left untouched.
    defaults = {
        'bomb': (10.0, 0.15, 588.0, 1.0/84),
        'number': (10.0, 0.15, 105.0, 1.0/15),
        'dice': (10.0, 0.15, 10.0, 1.0/6),
        'slot': (10.0, 0.15, 10.0, 1.0/20),
        'wheel': (10.0, 0.15, 10.0, 1.0),
        'keno': (10.0, 0.15, 10.0, 1.0/15),
        'chicken': (10.0, 0.15, 10.0, 0.50),
        'aviator': (10.0, 0.15, 10.0, 0.50),
    }
    for key, (fee, edge, win_amount, prob) in defaults.items():
        cur.execute('''INSERT OR IGNORE INTO game_settings(key,entry_fee,house_edge,win_amount,enabled,win_probability)
                       VALUES(?,?,?,?,1,?)''', (key, fee, edge, win_amount, prob))
        cur.execute('UPDATE game_settings SET win_probability=? WHERE key=? AND (win_probability IS NULL OR win_probability<=0)', (prob, key))

    conn.commit()
    # Admin-controlled economics: welcome bonus trigger, global min bet / house edge, high-stakes cashback tables.
    from platform_controls import init_platform_controls
    init_platform_controls(conn)
    conn.close()
