# ============================================================
# MINI APP BACKEND API
#
# This is a separate process from kdm_bot.py. It serves the HTTP API
# that the Mini App frontend (miniapp/index.html + app.js) calls.
# It reads/writes the SAME SQLite file the bot uses (config.DB_FILE),
# so a deposit approved by the bot, or a wallet balance changed by a
# game, shows up here immediately and vice versa.
#
# Run separately from the bot, e.g.:
#   python3 webapp_api.py
# and put it behind HTTPS (nginx / Caddy / a platform like Render,
# Railway, Fly.io, etc.) at the URL you set as MINI_APP_API_URL in
# config.py. Telegram requires MINI_APP_URL (the frontend) to be
# HTTPS -- plain http:// or localhost will not open inside Telegram.
# ============================================================

import keno_math
import plinko_math
import triplegold_math
import slot_math
import flame_math
import aztec_math
import roast_math
import buffalo_math
import hashlib
import html
import math
import secrets
import csv
import io
import random
import re
import os
import hmac
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
import traceback
import uuid
import threading
from functools import wraps
from logging.handlers import RotatingFileHandler
from urllib.parse import parse_qsl

import requests
from casino_cards import *   # Baccarat / Blackjack pure card logic
from dice_math import *       # two-dice Under / Exact / Over
from new_games_math import *  # Roulette / Bingo / Fast Keno pure math (exact RTP tables)
from flask import Flask, request, jsonify, g, Response
from werkzeug.exceptions import HTTPException

try:
    from flask_cors import CORS
    _HAS_CORS = True
except ImportError:
    _HAS_CORS = False

from config import (
    BOT_TOKEN, DB_FILE, ADMIN_ID,
    ACCOUNT_NAME, CBE_ACCOUNT, BOA_ACCOUNT, TELEBIRR_NUMBER,
    BOT_USERNAME, MINI_APP_SHORT_NAME, MINI_APP_MAIN, ADMIN_PANEL_PIN, OWNER_ID, SUPPORT_CONTACT, MINI_APP_URL, MINI_APP_API_URL,
    CHAPA_SECRET_KEY, CHAPA_MODE, CHAPA_CALLBACK_URL, CHAPA_RETURN_URL, CHAPA_WEBHOOK_SECRET,
)

import bonus_wallet as _bonus
import platform_controls as _pc
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
# Hard cap on what ONE round may pay. Keep it below ~2-5% of the real bankroll once PLATFORM_BANKROLL_ETB is set.
MAX_ROUND_PAYOUT_ETB = float(os.getenv("MAX_ROUND_PAYOUT_ETB", "100000"))
# Highest house edge an admin may configure (0.30 = player RTP never below 70%).
MAX_HOUSE_EDGE = float(os.getenv("MAX_HOUSE_EDGE", "0.30"))
# Every game starts at this house edge (15%). The admin can change it per game afterwards; the change is read fresh on every request.
DEFAULT_ALL_HOUSE_EDGE = float(os.getenv("DEFAULT_HOUSE_EDGE", "0.15"))   # env override only used by the math regression tests
# Minimum sum of implied probabilities for a sports match (1.0 = no margin, arbitrage-free).
SPORTS_MIN_OVERROUND = float(os.getenv("SPORTS_MIN_OVERROUND", "1.02"))
# Bankroll guard: 0 disables. Otherwise total worst-case payout of all in-flight realtime
# rounds may not exceed PLATFORM_BANKROLL_ETB * BANKROLL_EXPOSURE_PCT.
PLATFORM_BANKROLL_ETB = float(os.getenv("PLATFORM_BANKROLL_ETB", "0"))
BANKROLL_EXPOSURE_PCT = float(os.getenv("BANKROLL_EXPOSURE_PCT", "0.5"))
# Withdrawal turnover: 0 disables. Otherwise a user must have wagered at least
# WITHDRAW_TURNOVER_MULTIPLIER x their real deposits (bonus excluded) before withdrawing.
# Operator decision: default 0 = players may withdraw their balance whether or not they have played. The 10% deposit bonus has no wagering condition of
# its own, so the turnover rule is what pays for it: break-even is ~1.2x at the 8.2% average house
# edge and ~2x on the 5%-edge games, 3x leaves a margin. With 0 a deposit -> bonus -> withdraw
# cycle would be free money.
WITHDRAW_TURNOVER_MULTIPLIER = float(os.getenv("WITHDRAW_TURNOVER_MULTIPLIER", "0"))
if not math.isfinite(MAX_ROUND_PAYOUT_ETB) or MAX_ROUND_PAYOUT_ETB < 10000:
    raise RuntimeError("MAX_ROUND_PAYOUT_ETB must be finite and at least 10000 ETB")
# Bankroll-based per-round cap: when PLATFORM_BANKROLL_ETB is set, ONE round may never pay more than
# MAX_PAYOUT_BANKROLL_PCT of it (default 3%, recommended 2-5%). The effective cap is the lower of the
# fixed MAX_ROUND_PAYOUT_ETB and this percentage, applied everywhere MAX_ROUND_PAYOUT_ETB is used.
MAX_PAYOUT_BANKROLL_PCT = float(os.getenv("MAX_PAYOUT_BANKROLL_PCT", "0.03"))
if not (0 < MAX_PAYOUT_BANKROLL_PCT <= 0.10):
    raise RuntimeError("MAX_PAYOUT_BANKROLL_PCT must be between 0 and 0.10")
if PLATFORM_BANKROLL_ETB > 0:
    MAX_ROUND_PAYOUT_ETB = min(MAX_ROUND_PAYOUT_ETB, round(PLATFORM_BANKROLL_ETB * MAX_PAYOUT_BANKROLL_PCT, 2))
# Sports betting is pool (parimutuel) based: all stakes of a match form one pool, the house keeps
# SPORTS_RAKE_PCT first, and only the remainder is shared among the winning bets. The house cannot lose.
# Number and Boom are pool games too: the house takes GAME_POOL_RAKE_PCT of every entry fee, the rest
# goes into a prize pool that is paid ONLY to winners (never from the house bankroll). A pool with no
# winner rolls over to the next round. NUMBER_ROUND_SECONDS = how long a Number round accepts guesses.
GAME_POOL_RAKE_PCT = float(os.getenv("GAME_POOL_RAKE_PCT", "0.08"))
if not (0.05 <= GAME_POOL_RAKE_PCT <= 0.10):
    raise RuntimeError("GAME_POOL_RAKE_PCT must be between 0.05 and 0.10")
NUMBER_ROUND_SECONDS = int(os.getenv("NUMBER_ROUND_SECONDS", "60"))
if not (15 <= NUMBER_ROUND_SECONDS <= 600):
    raise RuntimeError("NUMBER_ROUND_SECONDS must be between 15 and 600")
SPORTS_RAKE_PCT = float(os.getenv("SPORTS_RAKE_PCT", "0.08"))
if not (0.05 <= SPORTS_RAKE_PCT <= 0.10):
    raise RuntimeError("SPORTS_RAKE_PCT must be between 0.05 and 0.10")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # multipart media hard cap

JSON_BODY_MAX_BYTES = 1024 * 1024

@app.before_request
def reject_oversized_json_bodies():
    if request.is_json and request.content_length is not None and request.content_length > JSON_BODY_MAX_BYTES:
        return jsonify({"error": "JSON request body too large"}), 413

if _HAS_CORS:
    # Only needed if the frontend is served from a DIFFERENT domain
    # than this API. If you serve miniapp/ and this API from the same
    # domain (recommended -- simpler and avoids CORS entirely), this
    # is harmless either way. Install with: pip install flask-cors
    CORS(app, resources={r"/api/*": {"origins": [MINI_APP_URL.rstrip("/")]}})

# ------------------------------------------------------------
# ERROR LOGGING
#
# Real money moves through this API, so silent failures are not
# acceptable -- every unhandled exception is (1) written to a
# rotating log file on disk so you have a permanent record, and
# (2) sent to the admin's Telegram DM so you find out immediately
# instead of a user reporting it to you days later.
# ------------------------------------------------------------
_log_handler = RotatingFileHandler(
    "webapp_api_errors.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
))
logger = logging.getLogger("webapp_api")
logger.setLevel(logging.INFO)
logger.addHandler(_log_handler)


_error_notice_lock = threading.Lock()
_error_notice_last = {}
_ERROR_NOTICE_INTERVAL = 60

def notify_admin_of_error(context: str, exc: Exception):
    """Best-effort, rate-limited Telegram DM; the rotating log keeps every error."""
    now = time.monotonic()
    key = (context.split(" (user=", 1)[0], type(exc).__name__)
    with _error_notice_lock:
        last = _error_notice_last.get(key, 0.0)
        if now - last < _ERROR_NOTICE_INTERVAL:
            return
        _error_notice_last[key] = now
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": (
                    f"🔴 webapp_api error\n"
                    f"Context: {context}\n"
                    f"{type(exc).__name__}: {exc}"
                )[:4000],
            },
            timeout=5,
        )
    except Exception:
        pass  # notification is best-effort; never raise from here


@app.errorhandler(Exception)
def handle_uncaught_exception(exc):
    # Expected HTTP errors (404 scanners, 405 wrong methods, 413 uploads,
    # etc.) are client-facing responses, not application crashes. Preserve
    # their status codes and never alert the admin for routine internet noise.
    if isinstance(exc, HTTPException):
        return jsonify({"error": exc.description}), exc.code

    uid = getattr(g, "tg_user", {}).get("id") if hasattr(g, "tg_user") else None
    context = f"{request.method} {request.path} (user={uid})"
    logger.error("%s\n%s", context, traceback.format_exc())
    notify_admin_of_error(context, exc)
    return jsonify({"error": "internal server error, please try again"}), 500


MAX_INIT_DATA_AGE_SECONDS = 86400  # 24h; Telegram re-issues initData
                                    # each time the Mini App is opened


# ------------------------------------------------------------
# Telegram WebApp initData validation
# https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
# ------------------------------------------------------------

def validate_init_data(init_data: str, bot_token: str):
    """Validates the initData string Telegram signs and the frontend
    sends with every request. Returns the parsed Telegram user dict
    (id, first_name, username, ...) on success. Raises ValueError on
    any failure -- NEVER trust an unvalidated initData string, since
    it's the only proof a request actually came from Telegram for
    the user it claims to be."""
    if not init_data:
        raise ValueError("Missing initData")

    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid initData signature")

    auth_date = int(parsed.get("auth_date", "0"))
    age = time.time() - auth_date
    if age < -60:
        raise ValueError("invalid auth_date")
    if MAX_INIT_DATA_AGE_SECONDS and age > MAX_INIT_DATA_AGE_SECONDS:
        raise ValueError("initData expired -- reopen the Mini App")

    user_json = parsed.get("user")
    if not user_json:
        raise ValueError("No user field in initData")

    return json.loads(user_json)


SENSITIVE_MAX_INIT_DATA_AGE_SECONDS = 3600  # 1h -- tighter window for money-moving endpoints


def require_fresh_auth(f):
    """Extra replay-window tightening for money-moving endpoints.
    require_telegram_auth already validated the signature and applies
    the normal 24h window; this additionally re-checks auth_date
    against a much shorter window on top of that, specifically for
    endpoints where a leaked/logged initData string (e.g. captured
    from a proxy access log) being replayed later would actually
    matter -- deposits, withdrawals, balance changes, bans, escrow
    actions. Read-only endpoints keep the normal 24h convenience
    window; this is layered on, not a replacement.

    Apply directly below @require_telegram_auth so g.tg_user already
    exists (though this check re-parses the header itself rather than
    relying on g.tg_user, since auth_date isn't carried through)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        try:
            parsed = dict(parse_qsl(init_data, strict_parsing=True))
            auth_date = int(parsed.get("auth_date", "0"))
        except (ValueError, TypeError):
            auth_date = 0
        age = time.time() - auth_date
        if age < -60 or age > SENSITIVE_MAX_INIT_DATA_AGE_SECONDS:
            return jsonify({
                "error": "session too old for this action -- please close and reopen the Mini App, then try again"
            }), 401
        # Real-money actions are blocked until the server has a durable
        # record of the user's 18+ / Terms acceptance. Client-side
        # localStorage is only a convenience, never the authority.
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT terms_accepted_at, manager FROM users WHERE user_id=?", (g.tg_user["id"],))
        row = cur.fetchone(); conn.close()
        is_staff = (g.get("tg_user", {}).get("id") == ADMIN_ID) or bool(row and row["manager"])
        if not is_staff and (not row or not row["terms_accepted_at"]):
            return jsonify({"error":"terms_not_accepted","message":"18+ age confirmation and Terms acceptance are required before money actions."}), 428
        return f(*args, **kwargs)
    return wrapper


def require_telegram_auth(f):
    """Decorator: validates the 'X-Telegram-Init-Data' header on every
    request and makes the authenticated Telegram user available as
    g.tg_user. Rejects the request with 401 if validation fails.
    Also blocks banned users with 403 -- checked here, in the ONE
    place every authenticated route already passes through, so a ban
    takes effect immediately everywhere rather than needing every
    route to remember to check it individually."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        try:
            g.tg_user = validate_init_data(init_data, BOT_TOKEN)
        except ValueError as e:
            return jsonify({"error": f"unauthorized: {e}"}), 401

        conn = db(); cur = conn.cursor()
        cur.execute("SELECT banned, self_excluded_until FROM users WHERE user_id=?", (g.tg_user["id"],))
        row = cur.fetchone()
        conn.close()
        if row and row["banned"]:
            return jsonify({"error": "account suspended"}), 403

        if row and row["self_excluded_until"]:
            try:
                until = datetime.strptime(row["self_excluded_until"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                until = None
            if until and datetime.now() < until:
                return jsonify({
                    "error": "self_excluded",
                    "until": row["self_excluded_until"],
                    "message": f"እርስዎ እራስዎን እስከ {row['self_excluded_until']} ድረስ አግደዋል -- ይህ ጊዜ እስኪያልቅ ድረስ መጠቀም አይቻልም።"
                }), 403

        return f(*args, **kwargs)
    return wrapper


def db():
    conn = sqlite3.connect(DB_FILE, timeout=8, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


# The shared schema MUST exist before any migration/helper below runs.
# Older versions initialized payments/users only later in this file, which
# made a completely fresh database fail during module import (for example
# the Chapa migration tried to ALTER payments before payments existed).
try:
    from extended_schema import init_extended_schema
    init_extended_schema(DB_FILE, ADMIN_ID)
except Exception as _schema_exc:
    # Fail at startup with the real schema error; serving a half-created
    # money API is more dangerous than refusing to start.
    logger.critical("shared schema initialization failed: %s", _schema_exc)
    raise


# ------------------------------------------------------------
# Simple in-memory rate limiting
#
# Keyed on the authenticated Telegram user id (not IP -- Telegram
# Mini Apps are often proxied/embedded so client IPs aren't reliable,
# but g.tg_user is always trustworthy after require_telegram_auth
# has run). This is intentionally dependency-free (no flask-limiter,
# no Redis) since a single-process Flask app is what's actually
# deployed here. NOTE: this resets on process restart and does NOT
# share state across multiple worker processes -- if you later run
# with `gunicorn -w N` (N>1) for this app, switch to a shared store
# (e.g. Redis) instead, since each worker would otherwise track its
# own separate counts.
# ------------------------------------------------------------
from collections import defaultdict, deque

_rate_limit_hits = defaultdict(deque)


def rate_limit(max_calls: int, window_seconds: int):
    """Decorator: allows at most `max_calls` requests per user to this
    endpoint within any rolling `window_seconds` window. Must be
    applied INSIDE @require_telegram_auth (i.e. listed below it) so
    g.tg_user is already populated when this runs."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            uid = g.tg_user["id"]
            key = (f.__name__, uid)
            now = time.time()
            hits = _rate_limit_hits[key]

            while hits and now - hits[0] > window_seconds:
                hits.popleft()

            if len(hits) >= max_calls:
                retry_after = int(window_seconds - (now - hits[0])) + 1
                resp = jsonify({
                    "error": "too many requests, please slow down",
                    "retry_after_seconds": retry_after,
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp

            hits.append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator


TRANSACTION_LABELS = {
    "deposit": "💳 ተቀማጭ",
    "shamo_prize": "🪙 Shamo Prize",
    "withdraw": "💸 ወጪ",
    "auction_ticket": "🎟 የጨረታ ትኬት",
    "auction_win": "🏆 የጨረታ ማሸነፍ",
    "aviator_bet": "✈️ Aviator Bet",
    "aviator_win": "✈️ Aviator Win",
    "group_mines_bet": "💣 ቦምብ Entry",
    "group_mines_win": "💣 ቦምብ Win",
    "number_guess_bet": "🔢 ቁጥር Entry",
    "number_guess_win": "🔢 ቁጥር Win",
    "sports_bet": "⚽ ስፖርት Bet",
    "sports_win": "⚽ ስፖርት Win",
    "marketplace_buy": "🛍️ Marketplace ግዢ (Escrow)",
    "marketplace_release": "🛍️ Marketplace ሽያጭ ገቢ",
    "marketplace_refund": "🛍️ Marketplace ተመላሽ",
    "admin_adjustment": "⚙️ Admin ማስተካከያ",
    "withdraw_refund": "🔄 ወጪ ተመላሽ (ውድቅ)",
}


# ------------------------------------------------------------
# Strict money parsing -- never allow NaN/Infinity or more than 2
# decimal places into a real-money field. SQLite REAL is retained for
# compatibility with the existing database, but every client-supplied
# money value is normalized before it reaches the DB.
# ------------------------------------------------------------
def parse_money(value, field_name="amount", allow_negative=False):
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid {field_name}")
    if not math.isfinite(x):
        raise ValueError(f"invalid {field_name}")
    if not allow_negative and x < 0:
        raise ValueError(f"invalid {field_name}")
    if abs(round(x, 2) - x) > 1e-9:
        raise ValueError(f"{field_name} must have at most 2 decimal places")
    return round(x, 2)


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route("/api/health")
def health():
    try:
        conn=db(); row=conn.execute("PRAGMA quick_check").fetchone(); conn.close(); integrity=(row[0] if row else "unknown")
        return jsonify({"ok": integrity == "ok", "db_integrity": integrity, "service": "kdm-mini-app-api", "version": "FINAL-V3"}), (200 if integrity == "ok" else 503)
    except Exception:
        logger.exception("health check failed")
        return jsonify({"ok": False, "error": "database unavailable", "service": "kdm-mini-app-api", "version": "FINAL-V3"}), 503


@app.route("/api/support-info")
def support_info():
    """Static, no-auth-needed contact info -- so the frontend can show
    a direct 'talk to a person' link (self-exclusion help, disputes,
    or just feeling like play has gotten out of hand) without it being
    buried only inside the Terms text."""
    return jsonify({"support_contact": SUPPORT_CONTACT})


# ------------------------------------------------------------
# LIVE PAYMENT PROVIDER: CHAPA
# ------------------------------------------------------------
# The gateway is intentionally opt-in via CHAPA_SECRET_KEY. Checkout is
# initialized server-side, and wallet credit happens ONLY after a server
# verification call reports status=success. Browser callbacks are never
# trusted as proof of payment.
def _init_chapa_columns():
    conn=db(); cur=conn.cursor(); cols={r['name'] for r in cur.execute('PRAGMA table_info(payments)').fetchall()}
    if 'provider' not in cols: cur.execute("ALTER TABLE payments ADD COLUMN provider TEXT")
    if 'provider_ref' not in cols: cur.execute("ALTER TABLE payments ADD COLUMN provider_ref TEXT")
    if 'credited_at' not in cols: cur.execute("ALTER TABLE payments ADD COLUMN credited_at TEXT")
    conn.commit(); conn.close()
_init_chapa_columns()

def _chapa_request(method,url,**kwargs):
    if not CHAPA_SECRET_KEY: raise RuntimeError('CHAPA_SECRET_KEY is not configured')
    headers=kwargs.pop('headers',{}); headers['Authorization']=f'Bearer {CHAPA_SECRET_KEY}'; headers.setdefault('Content-Type','application/json')
    return requests.request(method,url,headers=headers,timeout=20,**kwargs)

def _credit_verified_chapa(tx_ref, verified):
    if str(verified.get('status','')).lower()!='success': return False
    amount=float(verified.get('amount') or 0); currency=str(verified.get('currency') or 'ETB').upper()
    conn=db(); cur=conn.cursor()
    try:
        cur.execute('BEGIN IMMEDIATE'); p=cur.execute("SELECT * FROM payments WHERE provider='chapa' AND provider_ref=?",(tx_ref,)).fetchone()
        if not p: conn.rollback(); conn.close(); return False
        if p['credited_at'] and p['status']=='approved': conn.commit(); conn.close(); return True
        if p['status'] != 'pending': conn.rollback(); conn.close(); return False
        verified_ref=str(verified.get('tx_ref') or verified.get('reference') or tx_ref).strip()
        if verified_ref != tx_ref or currency!='ETB' or round(amount,2)!=round(float(p['amount']),2): raise ValueError('verified reference, amount, or currency mismatch')
        now=_now(); cur.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(p['amount'],p['user_id']))
        cur.execute('INSERT INTO transactions(user_id,amount,transaction_type,payment_id,created_at) VALUES(?,?,?,?,?)',(p['user_id'],p['amount'],'deposit_chapa',p['id'],now))
        cur.execute("UPDATE payments SET status='approved',approved_at=?,credited_at=? WHERE id=? AND status='pending' AND credited_at IS NULL",(now,now,p['id']))
        if cur.rowcount != 1: conn.rollback(); conn.close(); return False
        try: _pc.grant_welcome_after_deposit(cur,p['user_id'],p['amount'])
        except Exception: logger.exception('welcome bonus after deposit failed')
        _inv=None
        try: _inv=_bonus.release_invite_bonus(cur,p['user_id'],p['amount'],now)
        except Exception: logger.exception('invite bonus release failed')
        conn.commit(); conn.close()
        if _inv:
            try: tg_send_message(_inv[0],f"🎉 የጋበዙት ጓደኛ የመጀመሪያ ገንዘብ አስገብቷል!\n🎁 +{_inv[1]:g} ብር ቦነስ (ለመጫወት)")
            except Exception: pass
        try: _ensure_deposit_bonus_schedule(p['id'])
        except Exception: pass
        try: tg_send_message(p['user_id'],f"✅ Deposit ተረጋግጧል!\n💰 {float(p['amount']):.2f} ብር\n🧾 {tx_ref}")
        except Exception: pass
        return True
    except Exception:
        conn.rollback(); conn.close(); raise

@app.route('/api/payments/chapa/status')
def chapa_status():
    return jsonify({'configured':bool(CHAPA_SECRET_KEY),'mode':CHAPA_MODE,'callback_configured':bool(CHAPA_CALLBACK_URL or MINI_APP_API_URL)})

@app.route('/api/payments/chapa/initialize',methods=['POST'])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=5,window_seconds=60)
def chapa_initialize():
    if not CHAPA_SECRET_KEY:return jsonify({'error':'Chapa is not configured'}),503
    body=request.get_json(silent=True) or {}; amount=parse_money(body.get('amount'),'amount')
    if amount<1:return jsonify({'error':'minimum amount is 1 ETB'}),400
    uid=g.tg_user['id']; first=g.tg_user.get('first_name','User'); last=g.tg_user.get('last_name',''); email=str(body.get('email','')).strip()
    tx_ref=f'kdm-{uid}-{int(time.time())}-{secrets.token_hex(4)}'
    callback=CHAPA_CALLBACK_URL or f'{MINI_APP_API_URL}/payments/chapa/callback'
    payload={'amount':f'{amount:.2f}','currency':'ETB','first_name':first,'last_name':last,'tx_ref':tx_ref,'callback_url':callback,'return_url':CHAPA_RETURN_URL,'customization':{'title':'Play Win Deposit','description':'Play Win wallet deposit'}}
    if email: payload['email']=email
    try:r=_chapa_request('POST','https://api.chapa.co/v1/transaction/initialize',json=payload); data=r.json()
    except Exception as e:return jsonify({'error':f'Chapa initialize failed: {e}'}),502
    if r.status_code>=400 or data.get('status')!='success':return jsonify({'error':'Chapa rejected the transaction','provider_response':data}),502
    conn=db(); cur=conn.cursor(); cur.execute('INSERT INTO payments(user_id,first_name,amount,status,created_at,provider,provider_ref) VALUES(?,?,?,?,?,?,?)',(uid,first,amount,'pending',_now(),'chapa',tx_ref)); conn.commit(); conn.close()
    return jsonify({'ok':True,'tx_ref':tx_ref,'checkout_url':data.get('data',{}).get('checkout_url'),'mode':CHAPA_MODE})

@app.route('/api/payments/chapa/callback',methods=['GET','POST'])
def chapa_callback():
    tx_ref=(request.args.get('tx_ref') or request.args.get('trx_ref') or (request.get_json(silent=True) or {}).get('tx_ref') or '').strip()
    if not tx_ref:return jsonify({'error':'missing tx_ref'}),400
    if not re.fullmatch(r'kdm-[0-9]{1,20}-[0-9]{9,12}-[a-f0-9]{8}', tx_ref):return jsonify({'error':'invalid tx_ref format'}),400
    try:
        r=_chapa_request('GET',f'https://api.chapa.co/v1/transaction/verify/{tx_ref}'); data=r.json()
        verified=data.get('data') or data; credited=_credit_verified_chapa(tx_ref,verified)
        return jsonify({'ok':True,'verified_status':verified.get('status'),'credited':credited,'tx_ref':tx_ref})
    except Exception:
        logger.exception('Chapa callback verification failed')
        return jsonify({'ok':False,'error':'Chapa verification failed; no credit was applied'}),502

@app.route('/api/payments/chapa/webhook',methods=['POST'])
def chapa_webhook():
    # Chapa signs the raw webhook body with HMAC-SHA256. Verify the signature
    # before even parsing/processing the event, then independently re-query
    # Chapa below before crediting the wallet.
    if not CHAPA_WEBHOOK_SECRET:
        return jsonify({'ok':False,'error':'Chapa webhook secret is not configured'}),503
    raw=request.get_data(cache=True)
    expected_payload=hmac.new(CHAPA_WEBHOOK_SECRET.encode('utf-8'), raw, hashlib.sha256).hexdigest()
    expected_secret=hmac.new(CHAPA_WEBHOOK_SECRET.encode('utf-8'), CHAPA_WEBHOOK_SECRET.encode('utf-8'), hashlib.sha256).hexdigest()
    chapa_sig=(request.headers.get('Chapa-Signature') or '').strip().lower()
    x_chapa_sig=(request.headers.get('x-chapa-signature') or '').strip().lower()
    try:
        valid=bool(
            (x_chapa_sig and hmac.compare_digest(expected_payload.encode('ascii'), x_chapa_sig.encode('utf-8')))
            or (chapa_sig and (hmac.compare_digest(expected_payload.encode('ascii'), chapa_sig.encode('utf-8')) or hmac.compare_digest(expected_secret.encode('ascii'), chapa_sig.encode('utf-8'))))
        )
    except (TypeError, UnicodeEncodeError):
        valid=False
    if not valid:
        logger.warning('Rejected Chapa webhook: invalid signature')
        return jsonify({'ok':False,'error':'invalid webhook signature'}),401
    try:
        body=json.loads(raw.decode('utf-8') or '{}')
    except Exception:
        return jsonify({'ok':False,'error':'invalid JSON payload'}),400
    tx_ref=str(body.get('tx_ref') or body.get('trx_ref') or body.get('reference') or '').strip()
    if not tx_ref:return jsonify({'ok':False,'error':'missing tx_ref'}),400
    # Always verify against Chapa before crediting; never trust webhook amount/status alone.
    try:r=_chapa_request('GET',f'https://api.chapa.co/v1/transaction/verify/{tx_ref}'); verified=(r.json().get('data') or r.json()); credited=_credit_verified_chapa(tx_ref,verified); return jsonify({'ok':True,'credited':credited})
    except Exception:
        logger.exception('Chapa callback verification failed')
        return jsonify({'ok':False,'error':'Chapa verification failed; no credit was applied'}),502

@app.route('/api/payments/chapa/verify/<tx_ref>')
@require_telegram_auth
def chapa_verify(tx_ref):
    conn=db(); p=conn.execute('SELECT user_id,status,amount,credited_at FROM payments WHERE provider="chapa" AND provider_ref=?',(tx_ref,)).fetchone(); conn.close()
    if not p or p['user_id']!=g.tg_user['id']:return jsonify({'error':'transaction not found'}),404
    try:r=_chapa_request('GET',f'https://api.chapa.co/v1/transaction/verify/{tx_ref}'); data=r.json(); verified=data.get('data') or data; credited=_credit_verified_chapa(tx_ref,verified); return jsonify({'ok':True,'status':verified.get('status'),'credited':credited})
    except Exception:
        logger.exception('Chapa status verification failed')
        return jsonify({'error':'Chapa verification failed; no credit was applied'}),502

@app.route('/api/payments/chapa/smoke-test')
@require_telegram_auth
def chapa_smoke_test():
    if g.tg_user['id'] != ADMIN_ID:
        return jsonify({'error':'admin only'}),403
    if not CHAPA_SECRET_KEY:return jsonify({'ok':False,'configured':False,'message':'Set CHAPA_SECRET_KEY first'}),503
    try:r=_chapa_request('GET','https://api.chapa.co/v1/transaction/verify/KDM-NONEXISTENT-SMOKE'); return jsonify({'ok':r.status_code in (401,404),'configured':True,'http_status':r.status_code,'message':'Gateway reachable; a fake reference was intentionally used so no real charge was created.'})
    except Exception as e:return jsonify({'ok':False,'configured':True,'error':str(e)}),502

@app.route("/api/games/popular")
@require_telegram_auth
def popular_games():
    """Most played games (real rounds from game_history), last 7 days; all-time if the week is empty.
    Used by the home banner to show the game people play most. Nothing is invented."""
    conn = db(); cur = conn.cursor()
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    q = "SELECT game_key, COUNT(*) AS plays, COUNT(DISTINCT user_id) AS players FROM game_history {w} GROUP BY game_key ORDER BY plays DESC LIMIT 5"
    cur.execute(q.format(w="WHERE created_at >= ?"), (since,)); rows = [dict(r) for r in cur.fetchall()]
    scope = "week"
    if not rows:
        cur.execute(q.format(w="")); rows = [dict(r) for r in cur.fetchall()]; scope = "all"
    conn.close()
    out = []
    for r in rows:
        k = r["game_key"]; lk = {"boom": "bomb", "minesx": "mines"}.get(k, k)
        label = UNIFIED_GAME_LABELS.get(k) or UNIFIED_GAME_LABELS.get(lk) or GAME_VARIANT_LABELS.get(k) or k.replace("_", " ").title()
        out.append({"game": k, "name": label, "plays": int(r["plays"]), "players": int(r["players"])})
    return jsonify({"games": out, "scope": scope})

@app.route("/api/wins/recent")
@require_telegram_auth
def recent_wins():
    """Real recent win transactions across all players, for a casino-
    style 'Recent Big Wins' ticker. NOT fabricated data -- this reads
    the same transactions table everything else does, filtered to
    win-type rows. Names are truncated for privacy, similar to how
    the reference design shows partially-masked usernames."""
    conn = db(); cur = conn.cursor()
    cur.execute(
        """SELECT t.amount, t.transaction_type, t.created_at, t.user_id, u.first_name
           FROM transactions t
           JOIN users u ON u.user_id = t.user_id
           WHERE (t.transaction_type IN
               ('group_mines_win','number_guess_win','sports_win','aviator_win','auction_win')
               OR t.transaction_type LIKE 'game_%_payout'
               OR t.transaction_type LIKE 'game_%_rt_payout')
             -- partial (below-stake) realtime payouts are net losses, not wins
             AND NOT (t.transaction_type LIKE 'game_%_rt_payout' AND t.amount <= COALESCE(
                 (SELECT h.stake FROM game_history h WHERE h.user_id=t.user_id AND h.created_at=t.created_at
                  AND 'game_'||h.game_key||'_rt_payout'=t.transaction_type LIMIT 1), 0))
           ORDER BY t.created_at DESC
           LIMIT 50"""
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Blend "recent" with "big" -- take the most recent 50 wins, then
    # surface the largest 15 among them, so the ticker favors size
    # without ever showing a win that didn't actually happen recently.
    rows.sort(key=lambda r: r["amount"], reverse=True)
    top = rows[:15]

    icons = {
        "group_mines_win": "💣", "number_guess_win": "🔢",
        "sports_win": "⚽", "aviator_win": "✈️", "auction_win": "🏆",
        "game_dice_payout": "🎲", "game_slot_payout": "🎰", "game_wheel_payout": "🎡",
        "game_keno_payout": "🎯", "game_chicken_payout": "🐔", "game_aviator_payout": "✈️",
        "game_plinko_payout": "🟣", "game_mines_payout": "💣", "game_jet_payout": "🚀",
        "game_fish_payout": "🐟", "game_rabbit_payout": "🐇", "game_card_payout": "🃏",
    }
    icons.update({k.replace("_payout", "_rt_payout"): v for k, v in list(icons.items()) if k.startswith("game_")})
    icons.update({k.replace("_payout", "_live_payout"): v for k, v in list(icons.items()) if k.startswith("game_")})
    out = []
    conn2 = db()
    for r in top:
        name = (r["first_name"] or "Player").strip()
        masked = (name[:3] + "***") if len(name) > 3 else (name + "***")
        tt = r["transaction_type"]
        gkey = {"group_mines_win": "boom", "number_guess_win": "number", "sports_win": "sports", "aviator_win": "aviator", "auction_win": "marketplace"}.get(tt)
        if gkey is None and tt.startswith("game_"):
            gkey = re.sub(r"(_rt|_live)?_payout$", "", tt[5:])
            gkey = re.sub(r"_live$", "", gkey)   # live rounds log game_<key>_live_payout (Number: game_number_live_live_payout) -> the plain game key
        # "boom" is the front-end key of the Boom game, the labels table calls it "bomb"; unknown keys get a readable name
        # instead of an empty label, so EVERY win card shows which game was won.
        _lk = {"boom": "bomb", "minesx": "mines"}.get(gkey, gkey)
        label = (UNIFIED_GAME_LABELS.get(gkey) or UNIFIED_GAME_LABELS.get(_lk) or GAME_VARIANT_LABELS.get(gkey) or "") if gkey else ""
        if gkey and not label:
            label = str(gkey).replace("_", " ").title()
        icon = icons.get(tt)
        if label and " " in label and not label[0].isalnum():
            icon = icon or label.split(" ", 1)[0]
            label = label.split(" ", 1)[1]
        mult = None
        if gkey and tt.startswith("game_"):
            cur2 = conn2.cursor()
            cur2.execute("SELECT stake FROM game_history WHERE user_id=? AND created_at=? AND game_key=? LIMIT 1", (r["user_id"], r["created_at"], gkey))
            hs = cur2.fetchone()
            if hs and hs[0] and float(hs[0]) > 0: mult = round(float(r["amount"]) / float(hs[0]), 2)
        out.append({
            "name": masked,
            "icon": icon or "🎉",
            "game": gkey, "game_name": label or None, "multiplier": mult,
            "amount": r["amount"],
            "created_at": r["created_at"],
        })
    conn2.close()
    return jsonify({"wins": out})


@app.route("/api/profile")
@require_telegram_auth
def profile():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute(
        "SELECT user_id, first_name, username, balance, manager FROM users WHERE user_id=?",
        (uid,)
    )
    row = cur.fetchone()

    if not row:
        # First time this Telegram user opens the Mini App before ever
        # messaging the bot -- create them the same way register_user()
        # does on the bot side, so both surfaces stay in sync.
        conn.close()
        conn = db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(user_id, first_name, username, balance) VALUES (?,?,?,0)",
            (uid, g.tg_user.get("first_name", ""), g.tg_user.get("username", ""))
        )
        conn.commit()
        # Re-read instead of assuming 0: the welcome-bonus trigger credits the new row at insert time.
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        _nr = cur.fetchone()
        balance, is_staff = float(_nr["balance"] or 0) if _nr else 0.0, (uid == ADMIN_ID)
        has_pending = False
    else:
        balance, is_staff = float(row["balance"] or 0), bool(row["manager"]) or (uid == ADMIN_ID)
        # Used to show a small dot badge on the Wallet nav icon --
        # lets a user know something is still awaiting admin action
        # without having to open the Wallet tab to check.
        cur.execute(
            "SELECT COUNT(*) c FROM payments WHERE user_id=? AND status='pending'", (uid,)
        )
        pending_deposits = int(cur.fetchone()["c"] or 0)
        cur.execute(
            "SELECT COUNT(*) c FROM withdrawals WHERE user_id=? AND status='pending'", (uid,)
        )
        pending_withdrawals = int(cur.fetchone()["c"] or 0)
        has_pending = (pending_deposits + pending_withdrawals) > 0

    _bonus_info = _bonus.withdrawable(cur, uid)
    conn.close()

    return jsonify({
        "user_id": uid,
        "first_name": g.tg_user.get("first_name", ""),
        "username": g.tg_user.get("username", ""),
        "balance": balance,
        "bonus_locked": _bonus_info[1],
        "withdrawable": _bonus_info[2],
        "is_staff": is_staff,
        "has_pending": has_pending,
    })


SELF_EXCLUSION_OPTIONS_DAYS = (7, 30, 90)


@app.route("/api/self-exclude", methods=["POST"])
@require_telegram_auth
def self_exclude():
    """Lets a user lock themselves out for a fixed period. This is
    NOT reversible by an admin during the period (see require_admin
    endpoints below -- none of them touch self_excluded_until) --
    that irreversibility is what makes self-exclusion an actual
    responsible-gambling protection rather than just a suggestion."""
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    try:
        days = int(body.get("days"))
        if days not in SELF_EXCLUSION_OPTIONS_DAYS:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": f"days must be one of {SELF_EXCLUSION_OPTIONS_DAYS}"}), 400

    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET self_excluded_until=? WHERE user_id=?", (until, uid))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "self_excluded_until": until})


@app.route("/api/accept-terms", methods=["POST"])
@require_telegram_auth
def accept_terms():
    """Records WHEN a user accepted the Terms (not just that the age
    gate was clicked through client-side) -- meaningful evidence if a
    dispute ever needs it. Idempotent: only ever sets the timestamp
    once, so it always reflects the FIRST acceptance."""
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    # Store a durable versioned acceptance. Existing installations get
    # the columns lazily so no destructive migration is needed.
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "age_confirmed_at" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN age_confirmed_at TEXT")
    if "terms_version" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN terms_version TEXT")
    # FIX: the age gate runs BEFORE /api/me, so a brand-new user has no
    # row yet and the UPDATE below would silently change 0 rows.
    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, first_name, username, balance) VALUES (?,?,?,0)",
        (uid, g.tg_user.get("first_name", ""), g.tg_user.get("username", ""))
    )
    cur.execute(
        "UPDATE users SET terms_accepted_at=COALESCE(terms_accepted_at,?), age_confirmed_at=COALESCE(age_confirmed_at,?), terms_version=COALESCE(terms_version,?) WHERE user_id=?",
        (_now(), _now(), "2026-10-v7", uid)
    )
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "could not record acceptance"}), 500
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})


@app.route("/api/history")
@require_telegram_auth
def history():
    uid = g.tg_user["id"]
    page = int(request.args.get("page", 0))
    per = 20

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM transactions WHERE user_id=?", (uid,))
    total = int(cur.fetchone()["c"] or 0)

    cur.execute(
        "SELECT amount, transaction_type, created_at FROM transactions "
        "WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (uid, per, page * per)
    )
    rows = cur.fetchall()
    conn.close()

    items = []
    for r in rows:
        amt = r["amount"]
        # Ledger amounts are canonical: positive=inflow, negative=outflow.
        if r["transaction_type"] == "withdraw":
            amt = -abs(amt)
        items.append({
            "type": r["transaction_type"],
            "label": TRANSACTION_LABELS.get(r["transaction_type"], r["transaction_type"]),
            "amount": amt,
            "created_at": r["created_at"],
        })

    return jsonify({"total": total, "page": page, "per_page": per, "items": items})


def _platform_flag_enabled(key):
    conn=db(); cur=conn.cursor(); cur.execute("SELECT value FROM platform_settings WHERE key=?",(key,)); r=cur.fetchone(); conn.close()
    return bool(int(r["value"])) if r else True


CREST_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)) or ".", "crests")
_CREST_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _crest_url(name):
    return f"/api/crests/{name}" if name else None


def _save_crest(upload):
    """Validate (real image bytes, max 2 MB) and store a club logo; returns the stored file name or None."""
    if not upload or not getattr(upload, "filename", ""):
        return None
    raw = upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Logo must be 2 MB or smaller.")
    if raw.startswith(b"\xff\xd8\xff"): ext = "jpg"
    elif raw.startswith(b"\x89PNG"): ext = "png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP": ext = "webp"
    else: raise ValueError("Logo must be a JPG, PNG or WEBP image.")
    os.makedirs(CREST_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(CREST_DIR, name), "wb") as f:
        f.write(raw)
    return name


@app.route("/api/crests/<name>")
def crest_image(name):
    # Public on purpose: <img> tags cannot send the Telegram auth header.
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", name or ""):
        return jsonify({"error": "not found"}), 404
    path = os.path.join(CREST_DIR, name)
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, mimetype=_CREST_MIME[name.rsplit(".", 1)[-1]], headers={"Cache-Control": "public, max-age=86400"})


@app.route("/api/sports/matches")
@require_telegram_auth
def sports_matches():
    if not _platform_flag_enabled("sports_enabled"):
        return jsonify({"matches":[],"disabled":True})
    conn = db(); cur = conn.cursor()
    # Matches stay on screen after kickoff as LIVE (betting closed) until staff settle them, but a forgotten
    # match disappears 6 hours after kickoff.
    now = _now(); cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 6 * 3600))
    cur.execute(
        "SELECT id, home_team, away_team, odds_home, odds_draw, odds_away, closes_at, home_score, away_score, live_minute, league, sport, home_logo, away_logo "
        "FROM sports_matches WHERE status='OPEN' AND closes_at IS NOT NULL AND closes_at > ? "
        "ORDER BY (closes_at <= ?) DESC, closes_at ASC, id DESC",
        (cutoff, now)
    )
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["home_logo"] = _crest_url(r.get("home_logo")); r["away_logo"] = _crest_url(r.get("away_logo"))
        r["live"] = str(r["closes_at"]) <= now
        if not r["live"]:
            r["home_score"] = r["away_score"] = r["live_minute"] = None
    conn.close()
    return jsonify({"matches": rows})


def _bot_open_link(param, fallback_start=False):
    """t.me link that opens the Mini App itself (never the bot chat) when the Direct Link / Main Mini App is configured.
    Otherwise (fallback_start) a /start link: the bot then shows its King Bet button."""
    bot = (BOT_USERNAME or "").lstrip("@").strip("/")
    if not bot or bot == "YOUR_BOT_USERNAME":
        return None
    if MINI_APP_SHORT_NAME:
        return f"https://t.me/{bot}/{MINI_APP_SHORT_NAME}?startapp={param}"
    if MINI_APP_MAIN:
        return f"https://t.me/{bot}?startapp={param}"
    return f"https://t.me/{bot}?start={param}" if fallback_start else None


@app.route("/api/referral")
@require_telegram_auth
def referral():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users WHERE referred_by=?", (uid,))
    count = int(cur.fetchone()["c"] or 0)
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM invite_bonuses WHERE inviter_id=? AND paid_at IS NOT NULL", (uid,))
    earned = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM invite_bonuses WHERE inviter_id=? AND paid_at IS NULL", (uid,))
    pending = int(cur.fetchone()[0] or 0)
    needs_dep = _bonus.invite_requires_deposit(cur)
    conn.close()

    link = _bot_open_link(f"ref_{uid}", fallback_start=True)

    return jsonify({"link": link, "invited_count": count, "bonus_per_invite": _bonus.INVITE_BONUS_ETB, "bonus_earned": earned,
                    "pending_invites": pending, "bonus_after_deposit": needs_dep})


@app.route("/api/referral/claim", methods=["POST"])
@require_telegram_auth
def referral_claim():
    """Invite link opened straight in the Mini App (t.me/<bot>/<app>?startapp=ref_<id>): the client sends the start_param
    once. Counted only for a brand-new account (no inviter yet, no money movement), never for yourself."""
    uid = int(g.tg_user["id"])
    code = str((request.get_json(silent=True) or {}).get("code") or "").strip()
    if not (code.startswith("ref_") and code[4:].isdigit()):
        return jsonify({"ok": False})
    inviter = int(code[4:])
    if inviter == uid:
        return jsonify({"ok": False})
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,)); me = cur.fetchone()
    if me is None:
        # First request of a brand-new account can be this claim (it races /api/profile) -- create the row so the invite is not lost.
        cur.execute("INSERT OR IGNORE INTO users(user_id, first_name, username, balance) VALUES (?,?,?,0)",
                    (uid, g.tg_user.get("first_name", ""), g.tg_user.get("username", "")))
        conn.commit()
        cur.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,)); me = cur.fetchone()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (inviter,)); inv = cur.fetchone()
    cur.execute("SELECT 1 FROM transactions WHERE user_id=? LIMIT 1", (uid,)); used = cur.fetchone()
    ok = False
    if me is not None and inv is not None and me["referred_by"] is None and used is None:
        ok = _bonus.record_invite(cur, inviter, uid, _now())
        conn.commit()
    conn.close()
    return jsonify({"ok": ok})


@app.route("/api/games/settings")
@require_telegram_auth
def games_settings():
    """Live entry fee / win amount for Boom + Number Game, read
    straight from the game_settings table -- the same table
    kdm_bot.py's admin panel writes to on every ➖/➕ tap (see
    save_game_setting_to_db() in kdm_bot.py). This is always the
    real, current admin-configured value, not a hardcoded copy."""
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM game_settings WHERE key IN ('bomb','number')")
    rows = {r["key"]: r for r in cur.fetchall()}
    _ctl = _pc.get_controls(cur)
    conn.close()

    # Fallback only matters if the bot has genuinely never run once
    # (game_settings empty) -- kdm_bot.py seeds this table on its
    # very first startup, so in normal operation these defaults are
    # never actually used.
    defaults = {
        "bomb": {"entry_fee": 10.0, "win_amount": 588.0, "enabled": True},
        "number": {"entry_fee": 10.0, "win_amount": 105.0, "enabled": True},
    }

    out = {}
    for key in ("bomb", "number"):
        r = rows.get(key)
        if r:
            ov = _classic_overlay(r, _ctl)
            out[key] = {
                "entry_fee": ov["entry_fee"],
                "win_amount": ov["win_amount"],
                "enabled": ov["enabled"],
            }
        else:
            out[key] = defaults[key]
    return jsonify(out)


def _classic_overlay(r, c):
    """Boom / Number: entry fee >= global min bet, house edge = global edge (win amount recomputed with the
    same formula the DB trigger uses: fee*(1-edge)/win_probability)."""
    fee = _pc.effective_fixed_fee(float(r["entry_fee"]), c)
    edge = float(r["house_edge"]) if r["house_edge"] is not None else DEFAULT_HOUSE_EDGE
    if c["global_house_edge_enabled"]: edge = c["global_house_edge"]
    prob = float(r["win_probability"] or 0)
    win = float(r["win_amount"])
    if prob > 0 and (c["global_house_edge_enabled"] or abs(fee - float(r["entry_fee"])) > 1e-9):
        win = round(fee * (1.0 - edge) / prob, 2)
    return {"entry_fee": fee, "win_amount": win, "enabled": bool(r["enabled"]), "house_edge": edge}

def _get_game_setting(key):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM game_settings WHERE key=?", (key,))
    r = cur.fetchone()
    c = _pc.get_controls(cur)
    conn.close()
    if r:
        return _classic_overlay(r, c)
    fallback = {"bomb": (10.0, 588.0), "number": (10.0, 105.0)}
    fee, win = fallback.get(key, (10.0, 0.0))
    return {"entry_fee": fee, "win_amount": win, "enabled": True}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def require_admin(f):
    """Like require_telegram_auth, but additionally requires the
    authenticated user to be staff, AND (if ADMIN_PANEL_PIN is
    configured on the server) a short-lived PIN token obtained from
    /api/admin/verify-pin. This second factor matters because staff
    status alone is just "this Telegram account is on a list" -- if
    that account's Telegram session were ever compromised, the PIN is
    what stops the attacker from immediately being able to move
    balances or change game economics. If ADMIN_PANEL_PIN is left
    unset, this behaves exactly as before (staff check only) for
    backward compatibility -- set it in .env to turn the second
    factor on.

    Apply AFTER require_telegram_auth (i.e. listed below it) so
    g.tg_user already exists."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if g.tg_user["id"] not in get_staff_ids():
            return jsonify({"error": "admin only"}), 403
        if ADMIN_PANEL_PIN:
            token = request.headers.get("X-Admin-Pin-Token", "")
            if not _verify_admin_pin_token(token, g.tg_user["id"]):
                return jsonify({"error": "admin PIN required or expired", "pin_required": True}), 401
        return f(*args, **kwargs)
    return wrapper

def get_staff_ids():
    """Mirrors get_manager_ids() in kdm_bot.py -- admin plus every
    user flagged manager=1 -- so deposit/withdrawal notifications sent
    from this API reach the same people the bot itself would notify."""
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE manager=1")
    ids = [int(r["user_id"]) for r in cur.fetchall()]
    conn.close()
    seen, out = set(), []
    for uid in [ADMIN_ID, OWNER_ID] + ids:
        if uid not in seen:
            seen.add(uid)
            out.append(uid)
    return out


def tg_send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Sends a plain Telegram message via the raw Bot HTTP API. Used
    instead of python-telegram-bot's async Bot object because this
    Flask process has no asyncio event loop running -- a plain HTTP
    POST is simpler and avoids any event-loop plumbing here."""
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", data=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tg_send_photo_bytes(chat_id, file_bytes, filename, caption, reply_markup=None, parse_mode="Markdown"):
    """Uploads a raw image (from the Mini App's file input) straight
    to a Telegram chat via the Bot HTTP API's multipart upload, and
    returns the response JSON -- including the resulting photo's
    file_id, which we then store in `payments.photo_file_id` exactly
    like create_payment() does on the bot side, so the existing
    admin approve/reject handlers in kdm_bot.py work completely
    unmodified on deposits submitted through the Mini App."""
    payload = {"chat_id": chat_id, "caption": caption, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    files = {"photo": (filename, file_bytes)}
    try:
        r = requests.post(f"{TELEGRAM_API}/sendPhoto", data=payload, files=files, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------
# Deposit (submit payment proof, same review flow as the bot)
# ------------------------------------------------------------

@app.route("/api/deposit/info")
@require_telegram_auth
def deposit_info():
    return jsonify({
        "account_name": ACCOUNT_NAME,
        "cbe": CBE_ACCOUNT,
        "boa": BOA_ACCOUNT,
        "telebirr": TELEBIRR_NUMBER,
    })


@app.route("/api/deposit", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=3, window_seconds=60)
def submit_deposit():
    uid = g.tg_user["id"]
    first_name = g.tg_user.get("first_name", "")

    try:
        amount = parse_money(request.form.get("amount", ""), "amount")
        if amount <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "invalid amount"}), 400

    screenshot = request.files.get("screenshot")
    if not screenshot or not screenshot.filename:
        return jsonify({"error": "screenshot file is required"}), 400

    file_bytes = screenshot.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "file too large (10MB max)"}), 400

    # Duplicate-screenshot fraud check: the same image bytes (any
    # user, any status -- pending/approved/rejected) being submitted
    # again almost always means the same real deposit receipt is
    # being reused to claim a second (fake) deposit. Hash first,
    # before any Telegram upload happens, so a caught duplicate never
    # even reaches a staff member's chat.
    screenshot_hash = hashlib.sha256(file_bytes).hexdigest()
    conn = db(); cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, status FROM payments WHERE screenshot_hash=? LIMIT 1",
        (screenshot_hash,)
    )
    dup = cur.fetchone()
    conn.close()
    if dup:
        return jsonify({
            "error": "this screenshot has already been submitted before (payment #{}) -- "
                     "please upload a new screenshot for this deposit".format(dup["id"])
        }), 409

    # Upload to the FIRST staff member (usually admin) to obtain a
    # Telegram file_id -- this mirrors exactly what create_payment()
    # in kdm_bot.py stores, so the SAME 'payments' row and the SAME
    # existing approve/reject callback handlers work unchanged.
    staff_ids = get_staff_ids()
    if not staff_ids:
        return jsonify({"error": "no staff configured to receive this deposit"}), 500

    now = _now()
    conn = db(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO payments(user_id, first_name, amount, status, photo_file_id, created_at, screenshot_hash)
           VALUES (?,?,?,'pending',NULL,?,?)""",
        (uid, first_name, amount, now, screenshot_hash)
    )
    payment_id = cur.lastrowid
    conn.commit()

    caption = (
        f"💳 <b>New Deposit (Mini App)</b>\n\n"
        f"🆔 User: <code>{uid}</code>\n👤 {html.escape(first_name)}\n💰 <code>{amount:.2f}</code> ብር\n"
        f"🆔 Payment: <code>{payment_id}</code>"
    )
    reply_markup = {
        "inline_keyboard": [
            [{"text": "✅ APPROVE", "callback_data": f"approve:{payment_id}"}],
            [{"text": "❌ REJECT", "callback_data": f"reject:{payment_id}"}],
        ]
    }

    file_id = None
    for i, staff_id in enumerate(staff_ids):
        result = tg_send_photo_bytes(
            staff_id, file_bytes, screenshot.filename, caption,
            reply_markup=reply_markup, parse_mode="HTML"
        )
        if result.get("ok") and file_id is None:
            try:
                file_id = result["result"]["photo"][-1]["file_id"]
            except (KeyError, IndexError):
                pass

    if file_id:
        cur.execute("UPDATE payments SET photo_file_id=? WHERE id=?", (file_id, payment_id))
        conn.commit()
    conn.close()

    if not file_id:
        # Screenshot never reached any staff member -- delete the
        # payment row we just created rather than leaving an orphaned
        # 'pending' deposit with no proof attached for admin to see.
        conn = db(); cur = conn.cursor()
        cur.execute("DELETE FROM payments WHERE id=?", (payment_id,))
        conn.commit(); conn.close()
        return jsonify({"error": "could not deliver screenshot to staff, try again"}), 502

    return jsonify({"ok": True, "payment_id": payment_id, "amount": amount, "status": "pending"})


# ------------------------------------------------------------
# Withdrawal (identical DB effect + admin notification as the bot's
# own text-based withdrawal flow)
# ------------------------------------------------------------

# Withdrawal limits are operator settings (env). 0 on either daily cap = no cap.
# Every request still goes to staff for manual payout, and the turnover rule below still applies.
MIN_WITHDRAW_AMOUNT = float(os.getenv("MIN_WITHDRAW_AMOUNT", "1"))  # ብር -- reject anything below this
MAX_WITHDRAWALS_PER_DAY = int(os.getenv("MAX_WITHDRAWALS_PER_DAY", "0"))       # count, rolling 24h (0 = no cap)
MAX_WITHDRAWAL_AMOUNT_PER_DAY = float(os.getenv("MAX_WITHDRAWAL_AMOUNT_PER_DAY", "0"))  # ብር, rolling 24h (0 = no cap)


def _withdrawals_last_24h(cur, uid):
    """Returns (count, total_amount) of this user's withdrawals in the
    last rolling 24h that actually moved money out (pending or
    approved -- a rejected withdrawal never left the wallet, so it
    shouldn't count against the daily cap). Computed in Python against
    _now()'s local-time format rather than SQLite's own datetime()
    (which defaults to UTC) so both sides of the comparison use the
    same clock."""
    cur.execute(
        "SELECT amount, created_at FROM withdrawals WHERE user_id=? AND status IN ('pending','approved') "
        "ORDER BY id DESC LIMIT 200",
        (uid,)
    )
    cutoff = datetime.now() - timedelta(hours=24)
    count, total = 0, 0.0
    for row in cur.fetchall():
        try:
            ts = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            count += 1
            total += row["amount"]
    return count, total


def _turnover_shortfall(cur, uid):
    """Return ETB still to be wagered before this user may withdraw (0 = allowed)."""
    if WITHDRAW_TURNOVER_MULTIPLIER <= 0: return 0.0
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND transaction_type IN ('deposit','deposit_chapa')", (uid,))
    deposits = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT COALESCE(-SUM(amount),0) FROM transactions WHERE user_id=? AND amount<0 AND (transaction_type LIKE 'game\\_%\\_stake' ESCAPE '\\' OR transaction_type IN ('number_guess_bet','group_mines_bet','sports_bet'))", (uid,))
    wagered = float(cur.fetchone()[0] or 0)
    return max(0.0, round(deposits * WITHDRAW_TURNOVER_MULTIPLIER - wagered, 2))


@app.route("/api/withdraw", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=3, window_seconds=60)
def submit_withdraw():
    uid = g.tg_user["id"]
    first_name = str(g.tg_user.get("first_name", ""))[:100]
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        amount = parse_money(body.get("amount"), "amount")
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "invalid amount"}), 400
    if amount < MIN_WITHDRAW_AMOUNT:
        return jsonify({"error": f"minimum withdrawal is {MIN_WITHDRAW_AMOUNT:.0f} ብር"}), 400

    acc_name = str(body.get("acc_name") or "").strip()[:160]
    acc_number = str(body.get("acc_number") or "").strip()[:100]
    if not acc_name or not acc_number:
        return jsonify({"error": "account name and number are required"}), 400

    conn = db(); cur = conn.cursor()
    try:
        # Serialize the daily-limit check and wallet reservation. Concurrent
        # requests cannot both pass the limit using the same old snapshot.
        cur.execute("BEGIN IMMEDIATE")
        day_count, day_total = _withdrawals_last_24h(cur, uid)
        if MAX_WITHDRAWALS_PER_DAY > 0 and day_count >= MAX_WITHDRAWALS_PER_DAY:
            conn.rollback(); conn.close()
            return jsonify({"error": f"daily withdrawal limit reached ({MAX_WITHDRAWALS_PER_DAY} per 24 hours)"}), 429
        if MAX_WITHDRAWAL_AMOUNT_PER_DAY > 0 and day_total + amount > MAX_WITHDRAWAL_AMOUNT_PER_DAY:
            conn.rollback(); conn.close()
            return jsonify({"error": f"daily withdrawal amount limit reached ({MAX_WITHDRAWAL_AMOUNT_PER_DAY:.0f} ብር)"}), 429
        short = _turnover_shortfall(cur, uid)
        if short > 0:
            conn.rollback(); conn.close()
            return jsonify({"error": f"wager {short:.2f} ብር more before withdrawing (turnover requirement)"}), 400
        _bal, _locked, _can = _bonus.withdrawable(cur, uid)
        if _locked > 0 and amount > _can + 0.001:
            conn.rollback(); conn.close()
            return jsonify({"error": f"🎁 Bonus ({_locked:.2f} ብር) ለመጫወት ብቻ ነው -- ማውጣት የሚችሉት {_can:.2f} ብር ነው"}), 400
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (amount, uid, amount))
        if cur.rowcount != 1:
            conn.rollback(); conn.close()
            return jsonify({"error": "insufficient balance"}), 400
        now = _now()
        cur.execute("INSERT INTO withdrawals(user_id,amount,acc_name,acc_number,status,created_at) VALUES(?,?,?,?,'pending',?)", (uid, amount, acc_name, acc_number, now))
        w_id = cur.lastrowid
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (uid, -amount, "withdraw", now))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        logger.exception("withdrawal request failed for user_id=%s", uid)
        return jsonify({"error": "withdrawal failed; please retry or contact support"}), 500
    conn.close()

    esc = lambda value: html.escape(str(value), quote=True)
    text = (
        "💸 <b>Withdrawal Request (Mini App)</b>\n\n"
        f"🆔 User: <code>{uid}</code>\n👤 {esc(first_name)}\n💰 <code>{amount:.2f}</code> ብር\n"
        f"👤 Name: <code>{esc(acc_name)}</code>\n📱 Account: <code>{esc(acc_number)}</code>\n🆔 Withdrawal: <code>{w_id}</code>\n\n"
        "💳 ክፍያውን ከፈጸሙ በኋላ Payment Screenshot ይላኩ።"
    )
    reply_markup = {"inline_keyboard": [
        [{"text": "📸 Payment Screenshot ላክ", "callback_data": f"w_proof:{w_id}"}],
        [{"text": "❌ Reject", "callback_data": f"w_reject:{w_id}"}],
    ]}
    for staff_id in get_staff_ids():
        try:
            telegram_result = tg_send_message(staff_id, text, reply_markup=reply_markup, parse_mode="HTML")
            if not isinstance(telegram_result, dict) or not telegram_result.get("ok"):
                logger.error("Telegram rejected withdrawal staff notification withdrawal_id=%s staff_id=%s reason=%s", w_id, staff_id, (telegram_result or {}).get("description", "unknown Telegram API error") if isinstance(telegram_result, dict) else "invalid response")
        except Exception:
            logger.exception("could not notify withdrawal staff for withdrawal_id=%s", w_id)
    return jsonify({"ok": True, "withdrawal_id": w_id, "amount": amount, "status": "pending"})


@app.route("/api/sports/bet", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=10, window_seconds=30)
def place_sports_bet():
    if not _platform_flag_enabled("sports_enabled"):
        return jsonify({"error":"sports betting is disabled by admin"}),403
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    match_id = body.get("match_id")
    selection = body.get("selection")
    stake = body.get("stake")

    if selection not in ("HOME", "DRAW", "AWAY"):
        return jsonify({"error": "invalid selection"}), 400
    try:
        stake = parse_money(stake, "stake")
        if stake <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "invalid stake"}), 400

    if not math.isfinite(stake):
        return jsonify({"error": "invalid stake"}), 400
    _ctl = _controls()
    if _ctl["global_min_bet_enabled"] and stake < _ctl["global_min_bet"]:
        return jsonify({"error": f"minimum bet is {_ctl['global_min_bet']:.2f}"}), 400
    conn = db(); cur = conn.cursor()
    try:
        # Re-read the match INSIDE the write transaction so a bet cannot be
        # accepted on a match that was closed/settled a moment earlier.
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT * FROM sports_matches WHERE id=?", (match_id,))
        m = cur.fetchone()
        if not m or m["status"] != "OPEN":
            conn.rollback(); conn.close()
            return jsonify({"error": "match not open"}), 404
        if not m["closes_at"] or str(m["closes_at"]) <= _now():
            conn.rollback(); conn.close()
            return jsonify({"error": "betting for this match is closed"}), 403
        odds = m[{"HOME": "odds_home", "DRAW": "odds_draw", "AWAY": "odds_away"}[selection]]
        if not odds or float(odds) <= 1.0:
            conn.rollback(); conn.close()
            return jsonify({"error": "odds unavailable"}), 400
        if round(stake * float(odds), 2) > MAX_ROUND_PAYOUT_ETB:
            conn.rollback(); conn.close()
            return jsonify({"error": "stake too high for this match"}), 400
        cur.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
            (stake, uid, stake)
        )
        if cur.rowcount != 1:
            conn.rollback()
            conn.close()
            return jsonify({"error": "insufficient balance"}), 400

        now = _now()
        cur.execute(
            """INSERT INTO sports_bets(match_id,user_id,selection,stake,odds,status,created_at)
               VALUES(?,?,?,?,?,'PENDING',?)""",
            (match_id, uid, selection, stake, odds, now)
        )
        cur.execute(
            """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
               VALUES(?,?,?,?)""",
            (uid, -stake, "sports_bet", now)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        logger.exception("sports bet failed for user_id=%s", uid)
        return jsonify({"error": "bet failed; please retry"}), 500
    conn.close()

    return jsonify({
        "ok": True,
        "match": f"{m['home_team']} vs {m['away_team']}",
        "selection": selection,
        "stake": stake,
        "odds": odds,
        "potential_payout": round(stake * odds, 2),
        "pool_mode": True,
        "rake_pct": _sports_rake_pct(),
        "note": "indicative only: payout = your share of the match pool after the house rake",
    })


# ------------------------------------------------------------
# Number Game: instant solo round
# Each player gets exactly one guess, resolved immediately -- this
# maps naturally onto a single REST call, unlike the chat version's
# multiplayer shared-secret round (see the architecture notes for why
# Boom needs the shared-room approach below instead).
# ------------------------------------------------------------

def _pool_carry_get(cur, key):
    cur.execute("SELECT amount FROM pool_carry WHERE game_key=?", (key,))
    r = cur.fetchone()
    return float(r["amount"]) if r else 0.0


def _pool_carry_add(cur, key, delta):
    cur.execute("INSERT OR IGNORE INTO pool_carry(game_key, amount) VALUES(?,0)", (key,))
    cur.execute("UPDATE pool_carry SET amount=ROUND(amount+?,2) WHERE game_key=?", (round(float(delta), 2), key))


def _pool_rake_pct():
    """Number/Boom pool rake: the admin's global house edge when enabled, else GAME_POOL_RAKE_PCT."""
    return _pc.effective_rake(GAME_POOL_RAKE_PCT, _controls())


def _sports_rake_pct():
    return _pc.effective_rake(SPORTS_RAKE_PCT, _controls())


def _rake_split(stake):
    """(rake, pool_share) of one entry fee. rake + pool_share == stake exactly."""
    rake = round(float(stake) * _pool_rake_pct(), 2)
    return rake, round(float(stake) - rake, 2)


def _init_pool_games():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS pool_carry (
        game_key TEXT PRIMARY KEY, amount REAL NOT NULL DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS number_pool_rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL DEFAULT 'OPEN',
        opens_at TEXT NOT NULL, closes_at TEXT NOT NULL, secret INTEGER NOT NULL,
        server_seed TEXT NOT NULL, commitment TEXT NOT NULL,
        entries INTEGER NOT NULL DEFAULT 0, payout_total REAL NOT NULL DEFAULT 0, settled_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS number_pool_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        first_name TEXT, guess INTEGER NOT NULL, stake REAL NOT NULL, rake REAL NOT NULL DEFAULT 0,
        payout REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL,
        UNIQUE(round_id, user_id))""")
    cur.execute("INSERT OR IGNORE INTO pool_carry(game_key, amount) VALUES('number',0)")
    cur.execute("INSERT OR IGNORE INTO pool_carry(game_key, amount) VALUES('boom',0)")
    conn.commit(); conn.close()


_init_pool_games()


def _number_pool_new_round(cur):
    seed = secrets.token_hex(16)
    secret = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 15 + 1
    commitment = hashlib.sha256(seed.encode()).hexdigest()
    now = _now()
    closes = (datetime.now() + timedelta(seconds=NUMBER_ROUND_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO number_pool_rounds(status,opens_at,closes_at,secret,server_seed,commitment) VALUES('OPEN',?,?,?,?,?)",
        (now, closes, secret, seed, commitment))
    cur.execute("SELECT * FROM number_pool_rounds WHERE id=?", (cur.lastrowid,))
    return cur.fetchone()


def _number_pool_settle(cur, rnd, now):
    """Pay the pool to exact-guess winners. Winners share min(pool, MAX_ROUND_PAYOUT_ETB) equally; whatever
    is not paid (no winner, or capped) stays in the pool for the next round. The house never pays from
    its own money here: the payout is limited to money players put in."""
    cur.execute("SELECT * FROM number_pool_entries WHERE round_id=? ORDER BY id", (rnd["id"],))
    entries = cur.fetchall()
    winners = [e for e in entries if e["guess"] == rnd["secret"]]
    share = 0.0
    if winners:
        pool = _pool_carry_get(cur, "number")
        distributable = min(pool, MAX_ROUND_PAYOUT_ETB)
        share = math.floor(distributable * 100 / len(winners)) / 100.0
    paid = 0.0
    for e in entries:
        won = e["guess"] == rnd["secret"] and share > 0
        payout = share if won else 0.0
        if won:
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (payout, e["user_id"]))
            cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",
                        (e["user_id"], payout, "number_guess_win", now))
            paid += payout
        cur.execute("UPDATE number_pool_entries SET status=?, payout=? WHERE id=?",
                    ("WON" if won else "LOST", payout, e["id"]))
        cur.execute(
            "INSERT INTO webapp_number_rounds(user_id, first_name, guess, secret, won, entry_fee, payout, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (e["user_id"], e["first_name"], e["guess"], rnd["secret"], int(won), e["stake"], payout, now))
    if paid:
        _pool_carry_add(cur, "number", -paid)
    cur.execute("UPDATE number_pool_rounds SET status='SETTLED', payout_total=?, settled_at=? WHERE id=?",
                (round(paid, 2), now, rnd["id"]))


def _number_pool_tick(cur):
    """Lazy round clock (no background worker needed): called inside a write transaction by every
    Number endpoint. Settles an expired round and opens a fresh one."""
    now = _now()
    cur.execute("SELECT * FROM number_pool_rounds WHERE status='OPEN' ORDER BY id DESC LIMIT 1")
    r = cur.fetchone()
    if r and str(r["closes_at"]) > now:
        return r
    if r:
        _number_pool_settle(cur, r, now)
    return _number_pool_new_round(cur)


def _number_pool_join(cur, uid, name, guess, stake):
    """Returns (error_message|None, status_code). Caller commits/rolls back."""
    rnd = _number_pool_tick(cur)
    cur.execute("SELECT 1 FROM number_pool_entries WHERE round_id=? AND user_id=?", (rnd["id"], uid))
    if cur.fetchone():
        return "you already guessed in this round", 409
    cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (stake, uid, stake))
    if cur.rowcount != 1:
        return "insufficient balance", 400
    rake, share = _rake_split(stake)
    now = _now()
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",
                (uid, -stake, "number_guess_bet", now))
    cur.execute(
        "INSERT INTO number_pool_entries(round_id,user_id,first_name,guess,stake,rake,created_at) VALUES(?,?,?,?,?,?,?)",
        (rnd["id"], uid, name, guess, stake, rake, now))
    cur.execute("UPDATE number_pool_rounds SET entries=entries+1 WHERE id=?", (rnd["id"],))
    _pool_carry_add(cur, "number", share)
    _platform_record(cur, "number_pool_rake", rake, f"number:{rnd['id']}", "number pool rake", now)
    return None, 200


@app.route("/api/games/number/play", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=20, window_seconds=10)
def play_number_game():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    try:
        guess = int(body.get("guess"))
        if not (1 <= guess <= 15):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "guess must be an integer 1-15"}), 400
    settings = _get_game_setting("number")
    if not settings["enabled"]:
        return jsonify({"error": "Number Game is currently disabled"}), 403
    stake = settings["entry_fee"]
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        err, code = _number_pool_join(cur, uid, g.tg_user.get("first_name", "User"), guess, stake)
        if err:
            conn.rollback(); conn.close()
            return jsonify({"error": err}), code
        rnd = _number_pool_tick(cur)
        pool = _pool_carry_get(cur, "number")
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        logger.exception("number pool join failed for user_id=%s", uid)
        return jsonify({"error": "play failed; please retry"}), 500
    conn.close()
    return jsonify({"ok": True, "pending": True, "guess": guess, "entry_fee": stake, "round_id": rnd["id"],
                    "closes_at": rnd["closes_at"], "prize_pool": pool, "rake_pct": _pool_rake_pct()})


@app.route("/api/games/number/state")
@require_telegram_auth
def number_pool_state():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        rnd = _number_pool_tick(cur)
        pool = _pool_carry_get(cur, "number")
        cur.execute("SELECT guess FROM number_pool_entries WHERE round_id=? AND user_id=?", (rnd["id"], uid))
        mine = cur.fetchone()
        cur.execute("""SELECT e.guess, e.stake, e.payout, e.status, e.round_id, r.secret FROM number_pool_entries e
                       JOIN number_pool_rounds r ON r.id=e.round_id
                       WHERE e.user_id=? AND r.status='SETTLED' ORDER BY e.id DESC LIMIT 1""", (uid,))
        last = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        logger.exception("number pool state failed")
        return jsonify({"error": "state unavailable"}), 500
    conn.close()
    try:
        left = max(0, int((datetime.strptime(rnd["closes_at"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()))
    except (ValueError, TypeError):
        left = 0
    return jsonify({
        "round_id": rnd["id"], "closes_at": rnd["closes_at"], "seconds_left": left,
        "entries": rnd["entries"], "prize_pool": pool, "commitment": rnd["commitment"],
        "rake_pct": _pool_rake_pct(), "my_guess": mine["guess"] if mine else None,
        "my_last": dict(last) if last else None,
    })


# ------------------------------------------------------------
# SELF-CONTAINED CABINET GAMES
#
# These games are implemented in this API rather than opened through an
# external provider. Results are generated server-side; the browser never
# decides a win. Every settled round is written to game_history and the
# corresponding wallet transactions table.
# ------------------------------------------------------------

def _init_platform_ledger():
    """Separate platform-money ledger: commissions and game house result are tracked
    without silently changing any player wallet. Positive entries are platform revenue;
    negative entries are platform costs/refunds if ever needed.
    """
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS platform_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_type TEXT NOT NULL,
        amount REAL NOT NULL,
        reference_id TEXT,
        note TEXT,
        created_at TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_platform_ledger_created ON platform_ledger(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_platform_ledger_ref ON platform_ledger(reference_id)")
    conn.commit(); conn.close()


def _platform_record(cur, entry_type, amount, reference_id, note, created_at):
    """Record a signed platform result. Positive = platform revenue;
    negative = platform cost/house loss. Keeping the sign is important
    for games whose payout can exceed the stake (e.g. Aviator)."""
    amount = round(float(amount), 2)
    if amount == 0:
        return
    cur.execute(
        "INSERT INTO platform_ledger(entry_type,amount,reference_id,note,created_at) VALUES(?,?,?,?,?)",
        (entry_type, amount, str(reference_id) if reference_id is not None else None, note, created_at),
    )


def _platform_credit(cur, entry_type, amount, reference_id, note, created_at):
    amount = round(float(amount), 2)
    if amount <= 0:
        return
    _platform_record(cur, entry_type, amount, reference_id, note, created_at)


_init_platform_ledger()

def _init_cabinet_game_tables():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game_key TEXT NOT NULL,
            stake REAL NOT NULL,
            payout REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            outcome_json TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_game_history_user_game ON game_history(user_id, game_key, id DESC)")
    cur.execute("""CREATE TABLE IF NOT EXISTS cabinet_game_settings (
        game_key TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
        min_stake REAL NOT NULL DEFAULT 1, max_stake REAL NOT NULL DEFAULT 500,
        house_edge REAL NOT NULL DEFAULT 0.05,
        wheel_prizes TEXT,
        updated_at TEXT NOT NULL
    )""")
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(cabinet_game_settings)").fetchall()}
    if "house_edge" not in cols:
        cur.execute("ALTER TABLE cabinet_game_settings ADD COLUMN house_edge REAL NOT NULL DEFAULT 0.05")
    if "wheel_prizes" not in cols:
        cur.execute("ALTER TABLE cabinet_game_settings ADD COLUMN wheel_prizes TEXT")
    cur.execute("""CREATE TABLE IF NOT EXISTS game_idempotency (
        user_id INTEGER NOT NULL, idempotency_key TEXT NOT NULL, game_key TEXT NOT NULL,
        response_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, idempotency_key)
    )""")
    now = _now()
    for _k in CABINET_GAME_KEYS if 'CABINET_GAME_KEYS' in globals() else []:
        cur.execute("INSERT OR IGNORE INTO cabinet_game_settings(game_key,updated_at) VALUES(?,?)", (_k, now))
    conn.commit(); conn.close()

_init_cabinet_game_tables()

def _init_v7_tables():
    conn=db(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        subject TEXT, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS support_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
        sender_user_id INTEGER NOT NULL, sender_role TEXT NOT NULL, message_text TEXT,
        telegram_file_id TEXT, media_type TEXT, created_at TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_support_ticket_status ON support_tickets(status,updated_at DESC)")
    cur.execute("""CREATE TABLE IF NOT EXISTS announcement_broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, admin_user_id INTEGER NOT NULL,
        message_text TEXT NOT NULL, photo_file_id TEXT, created_at TEXT NOT NULL,
        total_targets INTEGER DEFAULT 0, sent_count INTEGER DEFAULT 0, failed_count INTEGER DEFAULT 0, status TEXT DEFAULT 'done'
    )""")
    # Lazy user columns for durable age/terms evidence.
    cols={r["name"] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "age_confirmed_at" not in cols: cur.execute("ALTER TABLE users ADD COLUMN age_confirmed_at TEXT")
    if "terms_version" not in cols: cur.execute("ALTER TABLE users ADD COLUMN terms_version TEXT")
    conn.commit(); conn.close()

_init_v7_tables()

# Keno pay table by number of hits (5 picks, 5 drawn from 20). Low-variance design: 2 hits already return
# the stake and 1 hit returns half, so ~36.6% of rounds pay >= 1x (the old table: 7.3%) and the top prize
# is 120x (old effective 128x at 7% hit rate). Base RTP is computed exactly from the hypergeometric odds.
KENO_PAYTABLE = {0: 0.0, 1: 0.5, 2: 1.0, 3: 3.5, 4: 30.0, 5: 120.0}
KENO_BASE_RTP = sum(math.comb(5, h) * math.comb(15, 5 - h) / math.comb(20, 5) * m for h, m in KENO_PAYTABLE.items())

CABINET_GAME_KEYS = {
    "dice", "slot", "wheel", "keno", "chicken", "aviator",
    "plinko", "mines", "jet", "fish", "rabbit", "card", "roast", "roulette", "bingo", "fastkeno", "penaltystreak", "tower", "chicken2", "dragontiger", "andarbahar", "dice2", "coinstreak", "minesx", "triplegold", "flame", "aztec", "buffalo",
    "coinflip", "penalty", "baccarat", "blackjack"
}

# ---------------------------------------------------------------------------
# GAME VARIANTS (catalog skins). Every variant is its OWN game_key -- own enable switch, stake limits,
# house edge/RTP, history and rounds -- but plays on one of the existing engines below, so the RNG and
# the payout maths are exactly the already-tested ones. _eng(key) gives the engine; DB rows keep the variant key.
_VARIANT_SLOT_NAMES = [["Abyssinian Lion", "🦁"], ["Mega Fruit 777", "7️⃣"], ["Gold 888", "🥇"], ["Lucky Clover 5", "☘️"], ["Fire Fruit 5", "🔥"], ["Fruity Wilds", "🍉"], ["Fruits Rush", "🍓"], ["Top Fire 5", "5️⃣"], ["Safari King", "🦁"], ["Sizzling Fruits", "🍒"], ["Royal Crown", "👑"], ["Fruity Fortune", "🍌"], ["Royal Bags", "💰"], ["Hot Strike 7", "⚡"], ["Sunshine Fruits", "☀️"], ["Royal Coins 5", "🪙"], ["Strike 777", "🎯"], ["Aztec Gold", "🗿"], ["Book of Dunes", "📖"], ["Penalty Kick", "🥅"], ["Hit Slot 2026", "🎰"], ["ሜዳ ፎርቹን", "⚽"], ["እንቁጣጣሽ", "🌼"], ["Habesha Fortune 5", "🦁"], ["Thunder Olympus", "⚡"], ["Buffalo Plains", "🦬"], ["Mother Hen", "🐓"], ["Hen & Fruits", "🍉"], ["Coin Hen", "🐔"], ["Coin Hen 5", "🪙"], ["Foxy Hot 20", "🦊"], ["Golden Bells", "🔔"], ["Flame Wins", "🔥"], ["Inferno Streak", "🌋"], ["Flame Classics", "🔥"], ["Triple Gold", "🪙"]]
GAME_ENGINE = {f"slot_{i+1:02d}": "slot" for i in range(len(_VARIANT_SLOT_NAMES))}
GAME_ENGINE.update({"crash": "aviator", "rocket": "jet", "highflyer": "aviator", "skymasters": "aviator",
                    "keno_power": "fastkeno", "keno_super": "fastkeno", "keno_insta": "fastkeno",
                    "triplegold_deluxe": "triplegold"})
GAME_VARIANT_LABELS = {f"slot_{i+1:02d}": f"{ic} {nm}" for i, (nm, ic) in enumerate(_VARIANT_SLOT_NAMES)}
GAME_VARIANT_LABELS.update({"crash": "📈 Crash", "rocket": "🚀 Rocket", "highflyer": "🛩️ High Flyer", "skymasters": "🛫 Sky Masters",
                            "keno_power": "🎱 Power Keno", "keno_super": "🟢 Super Keno", "keno_insta": "💎 Insta Keno", "triplegold_deluxe": "🔔 Triple Gold Deluxe"})
def _eng(key):
    return GAME_ENGINE.get(key, key)
CABINET_GAME_KEYS = set(CABINET_GAME_KEYS) | set(GAME_ENGINE)

# Seed settings for every self-contained cabinet game.
_conn = db(); _cur = _conn.cursor(); _nowv = _now()
CABINET_DEFAULT_HOUSE_EDGE = {
    "dice": 0.05, "slot": 0.08, "wheel": 0.05, "keno": 0.10,
    "chicken": 0.05, "aviator": 0.05, "plinko": 0.08, "mines": 0.05,
    "jet": 0.05, "fish": 0.05, "rabbit": 0.05, "card": 0.05, "roast": 0.05, "penaltystreak": 0.05, "tower": 0.05, "chicken2": 0.05, "triplegold_deluxe": 0.08, "roulette": ROULETTE_DEFAULT_EDGE, "bingo": 0.05, "fastkeno": 0.05,
    "coinflip": 0.05, "penalty": 0.05, "baccarat": 0.05, "blackjack": 0.05, "dragontiger": 0.05, "andarbahar": 0.05, "dice2": 0.05, "coinstreak": 0.05, "minesx": 0.05, "triplegold": 0.08, "flame": 0.08, "aztec": 0.08, "buffalo": 0.08,
}
CABINET_DEFAULT_HOUSE_EDGE = {_k: DEFAULT_ALL_HOUSE_EDGE for _k in CABINET_DEFAULT_HOUSE_EDGE}   # ALL games start at 15%
# Lucky Wheel (new): 20 equally likely sectors. 14 x Lose(0), 4 x Small(1.5), 1 x Big(3), 1 x Jackpot(10) -> mean 0.95 = RTP 95% at the default 5% edge,
# so the multipliers printed on the wheel are the real multipliers. Admin can still edit the 20 values; they are re-scaled to the configured RTP.
WHEEL_SECTORS = 20
# Fish (new): one shot = one draw from 80 equally likely outcomes. 50 miss, 16 x1.5, 6 x2, 4 x3, 2 x4, 1 x8, 1 x12 -> mean 0.95 (RTP 95% at the default 5% edge).
FISH_TABLE = [0.0]*50 + [1.5]*16 + [2.0]*6 + [3.0]*4 + [4.0]*2 + [8.0] + [12.0]
WHEEL_DEFAULT_PRIZES = [0, 1.5, 0, 0, 3.0, 0, 1.5, 0, 0, 0, 10.0, 0, 1.5, 0, 0, 1.5, 0, 0, 0, 0]
for _k in CABINET_GAME_KEYS:
    _edge = CABINET_DEFAULT_HOUSE_EDGE.get(_k, CABINET_DEFAULT_HOUSE_EDGE.get(_eng(_k), DEFAULT_ALL_HOUSE_EDGE))
    _cur.execute("INSERT OR IGNORE INTO cabinet_game_settings(game_key,house_edge,wheel_prizes,updated_at) VALUES(?,?,?,?)", (_k, _edge, json.dumps(WHEEL_DEFAULT_PRIZES if _k == "wheel" else None), _nowv))
    _cur.execute("UPDATE cabinet_game_settings SET house_edge=? WHERE game_key=? AND (house_edge IS NULL OR house_edge<0 OR house_edge>0.95)", (_edge, _k))
    if _k == "wheel":
        _cur.execute("UPDATE cabinet_game_settings SET wheel_prizes=? WHERE game_key='wheel' AND (wheel_prizes IS NULL OR wheel_prizes='')", (json.dumps(WHEEL_DEFAULT_PRIZES),))
# One-time: every existing game row starts at 15% (the admin edits it freely afterwards; this runs only once per database).
_cur.execute("CREATE TABLE IF NOT EXISTS platform_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
if not _cur.execute("SELECT 1 FROM platform_settings WHERE key='house_edge_start15_cabinet_v1'").fetchone():
    _cur.execute("UPDATE cabinet_game_settings SET house_edge=?, updated_at=?", (DEFAULT_ALL_HOUSE_EDGE, _nowv))
    _cur.execute("UPDATE platform_settings SET value=?, updated_at=? WHERE key='global_house_edge'", (str(DEFAULT_ALL_HOUSE_EDGE), _nowv))
    _cur.execute("INSERT OR REPLACE INTO platform_settings(key,value,updated_at) VALUES('house_edge_start15_cabinet_v1','1',?)", (_nowv,))

# One-time-compatible migration: stored wheel values become the actual displayed
# payout multipliers. Normalize their mean to the configured RTP so the generic
# scaler is ~1.0 rather than secretly changing the value shown to players.
_wrow = _cur.execute("SELECT wheel_prizes,house_edge FROM cabinet_game_settings WHERE game_key='wheel'").fetchone()
try:
    _wvals = [float(x) for x in json.loads(_wrow[0])]
    if len(_wvals) != WHEEL_SECTORS:   # old 10-sector wheel -> new 20-sector wheel (design: Lose / Small / Big / Jackpot)
        _wvals = [float(x) for x in WHEEL_DEFAULT_PRIZES]
        _cur.execute("UPDATE cabinet_game_settings SET house_edge=? WHERE game_key='wheel'", (DEFAULT_ALL_HOUSE_EDGE,))
        _wrow = (None, DEFAULT_ALL_HOUSE_EDGE)
    _target = 1.0 - float(_wrow[1] if _wrow[1] is not None else DEFAULT_ALL_HOUSE_EDGE)
    _mean = sum(_wvals) / len(_wvals)
    if _mean > 0 and abs(_mean - _target) > 0.00005:
        _wvals = [round(x * _target / _mean, 4) for x in _wvals]
        _cur.execute("UPDATE cabinet_game_settings SET wheel_prizes=? WHERE game_key='wheel'", (json.dumps(_wvals, separators=(",", ":")),))
except Exception:
    pass
_conn.commit(); _conn.close()


def _cabinet_stake(body):
    return parse_money(body.get("stake"), "stake")


def _controls():
    """Live admin controls (welcome bonus, global min bet / house edge, cashback). Read on every call: no cache."""
    conn=db()
    try: return _pc.get_controls(conn.cursor())
    finally: conn.close()

# The live Number game (rounds with many players) has NO cabinet row of its own: its house edge is the one the admin sets on the
# "Number" card (game_settings 'number'). Before this fix the live game silently kept a fixed 5% whatever the admin saved.
_EDGE_FROM_CLASSIC = {"number": "number", "number_live": "number"}

def _cabinet_limits(key):
    """(enabled, min_stake, max_stake, house_edge) for a game AFTER the admin's global min-bet / house-edge overrides.
    Every cabinet, live, realtime and blackjack endpoint reads its limits through this one function (no cache: a change the
    admin saves is used by the very next bet / round)."""
    conn=db(); cur=conn.cursor(); cur.execute("SELECT enabled,min_stake,max_stake,house_edge FROM cabinet_game_settings WHERE game_key=?",(key,)); r=cur.fetchone()
    classic_edge=None
    if key in _EDGE_FROM_CLASSIC:
        try:
            gr=cur.execute("SELECT house_edge FROM game_settings WHERE key=?",(_EDGE_FROM_CLASSIC[key],)).fetchone()
            if gr and gr["house_edge"] is not None: classic_edge=float(gr["house_edge"])
        except Exception: classic_edge=None
    c=_pc.get_controls(cur); conn.close()
    if not r:
        return _pc.apply_limits(True,1.0,10000.0,classic_edge if classic_edge is not None else DEFAULT_ALL_HOUSE_EDGE,c)
    edge=classic_edge if classic_edge is not None else (float(r["house_edge"]) if r["house_edge"] is not None else DEFAULT_ALL_HOUSE_EDGE)
    return _pc.apply_limits(bool(r["enabled"]), float(r["min_stake"]), float(r["max_stake"]), edge, c)

def _wheel_prizes():
    conn=db(); cur=conn.cursor(); cur.execute("SELECT wheel_prizes FROM cabinet_game_settings WHERE game_key='wheel'"); r=cur.fetchone(); conn.close()
    if not r or not r["wheel_prizes"]: return _normalize_wheel_prizes(WHEEL_DEFAULT_PRIZES, 0.05)
    try:
        vals=json.loads(r["wheel_prizes"])
        vals=[round(float(x),4) for x in vals]
        if len(vals)!=WHEEL_SECTORS or any(x<0 or x>1000 for x in vals): raise ValueError
        return vals
    except Exception:
        return _normalize_wheel_prizes(WHEEL_DEFAULT_PRIZES, 0.05)


def _normalize_wheel_prizes(values, house_edge):
    vals = [float(x) for x in values]
    if len(vals) != WHEEL_SECTORS or any(not math.isfinite(x) or x < 0 or x > 1000 for x in vals):
        raise ValueError("wheel prizes must contain 20 finite values from 0 to 1000")
    mean = sum(vals) / len(vals)
    target = 1.0 - float(house_edge)
    if mean <= 0:
        raise ValueError("at least one wheel prize must be greater than zero")
    return [round(x * target / mean, 4) for x in vals]


def _cabinet_base_rtp(key, outcome):
    # Expected return of the ORIGINAL game rule before applying the
    # disclosed house-edge scale. This lets each game keep its own
    # probabilities/rules while the configured RTP is mathematically
    # explicit rather than hidden outcome manipulation.
    if key == "dice": return (1/6) * 5.70
    if key == "dice2": return 1.0   # nominal payout is the fair 1/P; the disclosed edge is applied as the scale
    if key == "slot": return slot_math.BASE_RTP   # exact: 5x3, 10 lines, wild, scatter + free spins (see slot_math.py), scaled to 1 - house edge
    if key == "wheel": return sum(_wheel_prizes()) / len(_wheel_prizes())
    if key == "keno":
        if outcome.get("keno_mode") == "80": return 1.0   # nominal table is fair (mean 1.0); the disclosed edge is the scale
        return KENO_BASE_RTP
    if key == "roulette": return ROULETTE_BASE_RTP
    if key == "bingo": return BINGO_BASE_RTP
    if key == "fastkeno": return FASTKENO_RTP_BY_PICKS.get(int(outcome.get("picks") or FASTKENO_PICK), FASTKENO_BASE_RTP)
    if key in ("chicken", "rabbit", "penaltystreak", "tower", "chicken2", "coinstreak"):
        # Road games (Chicken Road / Rabbit Road) pay RTP/p**n by construction (see realtime_engine_v3.py); no scaling.
        return 1.0 - float(outcome.get("house_edge", 0.05))
    if key in ("aviator", "jet"):
        # The crash distribution itself contains the configured house edge.
        # Return the target RTP here so _apply_cabinet_house_edge leaves the
        # already-correct payout unchanged.
        return 1.0 - float(outcome.get("house_edge", 0.05))
    if key == "plinko":
        if outcome.get("plinko_mode") == "binomial": return 1.0   # nominal table is fair (mean 1.0); the disclosed edge is the scale
        return sum([0,0.5,0.8,1.0,1.2,1.5,2,3,5]) / 9
    if key == "buffalo": return buffalo_math.BASE_RTP   # exact analytic RTP of the 243-ways table incl. free spins, scaled to 1 - house edge
    if key == "roast": return roast_math.BASE_RTP   # exact nominal RTP of the 5-line pay table, scaled to 1 - house edge
    if key == "aztec": return aztec_math.BASE_RTP   # exact nominal RTP of the 5-line pay table, scaled to 1 - house edge
    if key == "flame": return flame_math.BASE_RTP   # nominal pay table incl. the 1-in-8 Hot Respin, scaled to 1 - house edge
    if key == "triplegold": return triplegold_math.BASE_RTP   # exact pay table RTP 1.0, scaled to 1 - house edge
    if key == "mines":
        mine_count = int(outcome["mine_count"]); mult = float(outcome["multiplier"])
        p = (25 - mine_count) / 25; return p * mult
    if key == "fish": return sum(FISH_TABLE) / len(FISH_TABLE)
    if key == "card": return (6/13) * 1.85
    if key in ("dragontiger", "andarbahar"): return 1.0   # scaled per bet in _apply_cabinet_house_edge
    if key == "baccarat": return 1.0            # per-bet scaling is done in _apply_cabinet_house_edge (bacc_scale)
    if key == "coinflip": return 0.5 * 2.0      # fair coin, nominal 2.00x -> base RTP 1.0, scaled to 1 - house edge
    if key == "penalty": return (2/3) * 1.5     # keeper covers 1 of 3 zones, nominal 1.50x -> base RTP 1.0
    return 1.0

def _apply_cabinet_house_edge(key, stake, payout, outcome, house_edge):
    if payout <= 0: return 0.0, 0.0
    if key == "dragontiger":
        sc = dt_scale(outcome["choice"], max(0.0, min(1.0, 1.0 - house_edge)), bool(outcome.get("push")))
        return round(payout * sc, 2), round(sc, 6)
    if key == "andarbahar":
        sc = ab_scale(outcome["choice"], max(0.0, min(1.0, 1.0 - house_edge)))
        return round(payout * sc, 2), round(sc, 6)
    if key == "baccarat":   # every bet (player / banker / tie) lands on exactly the target RTP; a push returns the stake untouched
        sc = bacc_scale(outcome["choice"], max(0.0, min(1.0, 1.0 - house_edge)), bool(outcome.get("push")))
        return round(payout * sc, 2), round(sc, 6)
    base_rtp = _cabinet_base_rtp(key, outcome)
    target_rtp = max(0.0, min(1.0, 1.0 - house_edge))
    if base_rtp <= 0: return 0.0, 0.0
    scale = target_rtp / base_rtp
    return round(payout * scale, 2), round(scale, 6)


def _iso_after(seconds):
    return (datetime.now()+timedelta(seconds=float(seconds))).strftime("%Y-%m-%d %H:%M:%S")

def _settle_cabinet_game(uid, key, stake, won, payout, outcome, idempotency_key=None):
    payout=round(min(MAX_ROUND_PAYOUT_ETB,max(0.0,float(payout))),2); conn=db(); cur=conn.cursor(); now=_now()
    try:
        cur.execute('BEGIN IMMEDIATE')
        if idempotency_key:
            cur.execute('SELECT response_json,game_key FROM game_idempotency WHERE user_id=? AND idempotency_key=?',(uid,idempotency_key)); cached=cur.fetchone()
            if cached:
                if cached['game_key']!=key: conn.rollback(); conn.close(); return None,(jsonify({'error':'idempotency key was already used for a different game'}),409)
                conn.rollback(); conn.close(); return json.loads(cached['response_json']),None
        cur.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?',(stake,uid,stake))
        if cur.rowcount!=1: conn.rollback(); conn.close(); return None,(jsonify({'error':'insufficient balance'}),400)
        cur.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(uid,-stake,f'game_{key}_stake',now))
        if payout>0:
            cur.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(payout,uid));cur.execute('INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)',(uid,payout,f'game_{key}_payout',now))
        house=round(stake-payout,2)
        _platform_record(cur,'game_house_result',house,f'{key}:{uid}:{now}',f'{key} stake/payout settlement',now)
        cur.execute('INSERT INTO game_history(user_id,game_key,stake,payout,status,outcome_json,created_at) VALUES(?,?,?,?,?,?,?)',(uid,key,stake,payout,'WON' if won else ('PUSH' if (payout>0 and abs(payout-stake)<0.005) else 'LOST'),json.dumps(outcome,separators=(',',':')),now));rid=cur.lastrowid
        response={'ok':True,'game':key,'won':bool(won),'stake':stake,'payout':payout,'outcome':outcome,'created_at':now,'round_id':int(rid),'round_code':f'{key.upper()}-{int(rid):08d}','server_authoritative':True}
        if idempotency_key:cur.execute('INSERT INTO game_idempotency(user_id,idempotency_key,game_key,response_json,created_at) VALUES(?,?,?,?,?)',(uid,idempotency_key,key,json.dumps(response,separators=(',',':')),now))
        conn.commit();conn.close();return response,None
    except Exception as e:
        conn.rollback();conn.close();logger.exception("cabinet game settlement failed")
        return None,(jsonify({'error':'game settlement failed; please retry'}),500)

def _cabinet_game_history(uid, key, limit=20):
    limit = max(1, min(int(limit), 100))
    conn = db(); cur = conn.cursor()
    cur.execute(
        "SELECT created_at,status,stake,payout,outcome_json FROM game_history WHERE user_id=? AND game_key=? ORDER BY id DESC LIMIT ?",
        (uid, key, limit),
    )
    rows = []
    for r in cur.fetchall():
        rows.append({"created_at": r["created_at"], "status": r["status"], "stake": r["stake"], "payout": r["payout"], "outcome": json.loads(r["outcome_json"] or "{}")})
    conn.close(); return rows


def _cabinet_game_route(key):
    def decorator(fn):
        endpoint = f"cabinet_{key}_play"
        legacy = require_telegram_auth(require_fresh_auth(rate_limit(max_calls=20, window_seconds=10)(fn)))
        def gated(*a, **kw):
            # Cabinet games are played only through the realtime /round/start + /action path.
            if os.getenv("ENABLE_LEGACY_CABINET_PLAY") != "1":
                return jsonify({"error": "use /round/start and /round/<id>/action"}), 410
            return legacy(*a, **kw)
        app.add_url_rule(f"/api/games/{key}/play", endpoint=endpoint, view_func=gated, methods=["POST"])
        return fn
    return decorator


def _cabinet_history_route(key):
    endpoint = f"cabinet_{key}_history"
    def view():
        uid = g.tg_user["id"]
        return jsonify({"items": _cabinet_game_history(uid, key, request.args.get("limit", 20))})
    app.add_url_rule(f"/api/games/{key}/history", endpoint=endpoint, view_func=require_telegram_auth(view), methods=["GET"])


@app.route("/api/games/<key>/settings")
@require_telegram_auth
def cabinet_game_settings(key):
    if key not in CABINET_GAME_KEYS: return jsonify({"error":"unknown game"}),404
    enabled, mn, mx, edge = _cabinet_limits(key)
    payload={"game":key,"enabled":enabled,"min_stake":mn,"max_stake":mx,"house_edge":edge,"rtp":round(1.0-edge,4)}
    if key == "wheel": payload["wheel_prizes"] = _wheel_prizes()
    if key == "keno":     # classic 80-ball tables: multiplier per hit count for 1..10 picks, edge already applied
        payload["keno_tables"] = {str(n): keno_math.effective_table(n, edge) for n in range(1, keno_math.MAX_PICK + 1)}
    if key == "buffalo":
        payload["buffalo_table"] = buffalo_math.effective_table(edge); payload["buffalo_free_spins"] = {str(k): v for k, v in buffalo_math.FREE_SPINS.items()}; payload["buffalo_fs_mult"] = buffalo_math.FS_MULT
    if key == "roast":
        payload["roast_table"] = roast_math.effective_table(edge); payload["roast_lines"] = roast_math.LINES
    if key == "aztec":
        payload["aztec_table"] = aztec_math.effective_table(edge); payload["aztec_lines"] = aztec_math.LINES
    if key == "flame":
        payload["flame_table"] = flame_math.effective_table(edge); payload["flame_hot_one_in"] = flame_math.HOT_ONE_IN
    if _eng(key) == "slot":   # the plain slot and all 36 themed slot games share one engine/table (edge may differ per variant)
        payload["slot_table"] = slot_math.effective_table(edge); payload["slot_lines"] = slot_math.LINES
    if _eng(key) == "triplegold":
        payload["triplegold_table"] = triplegold_math.effective_table(edge); payload["triplegold_strip"] = [triplegold_math.NAMES[x] for x in triplegold_math.STRIP]
    if key == "plinko":   # the exact multipliers the player is paid (disclosed edge already applied)
        payload["plinko_tables"] = {r: {str(n): plinko_math.effective_table(r, n, edge) for n in plinko_math.ROWS} for r in plinko_math.RISKS}
    return jsonify(payload)

@app.route("/api/games/<key>/verify/<int:round_id>")
@require_telegram_auth
def cabinet_verify_round(key, round_id):
    if key not in CABINET_GAME_KEYS: return jsonify({"error":"unknown game"}),404
    conn=db(); cur=conn.cursor(); cur.execute("SELECT id,user_id,game_key,stake,payout,status,outcome_json,created_at FROM game_history WHERE id=? AND user_id=? AND game_key=?",(round_id,g.tg_user["id"],key)); r=cur.fetchone(); conn.close()
    if not r: return jsonify({"error":"round not found"}),404
    return jsonify({"round_id":r["id"],"game":r["game_key"],"stake":r["stake"],"payout":r["payout"],"status":r["status"],"outcome":json.loads(r["outcome_json"] or "{}"),"created_at":r["created_at"]})

@app.route("/api/admin/all-game-economics", methods=["GET"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_all_game_economics():
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT * FROM game_settings WHERE key IN ('bomb','number')")
    classic={r["key"]:dict(r) for r in cur.fetchall()}
    cur.execute("SELECT * FROM cabinet_game_settings ORDER BY game_key")
    cabinet=[dict(r) for r in cur.fetchall()]
    conn.close()
    labels={"bomb":"💣 Boom Game","number":"🔢 Number Game","dice":"🎲 Dice","dice2":"🎲 Dice","coinstreak":"🪙 Coin Flip","minesx":"💣 Mines","triplegold":"🔔 Triple Gold","flame":"🔥 Flame Classics","aztec":"🗿 Aztec Gold","buffalo":"🦬 Buffalo Plains","slot":"🎰 777 Slot","wheel":"🎡 Lucky Wheel","keno":"🎯 Keno","chicken":"🐔 Chicken Road","aviator":"✈️ Aviator","plinko":"🟣 Plinko","mines":"💣 Mines","jet":"🚀 Jet","fish":"🐟 Fish","rabbit":"🐇 Rabbit Road","card":"🃏 Card Table","sports":"⚽ Sports Betting","marketplace":"🛍️ Marketplace"}
    items=[]
    for key in ("bomb","number"):
        r=classic.get(key)
        if r:
            edge=float(r["house_edge"] or 0); items.append({"key":key,"name":labels[key],"type":"house_edge","entry_fee":float(r["entry_fee"]),"house_edge":edge,"rtp":1-edge,"enabled":bool(r["enabled"])})
    for r in cabinet:
        edge=float(r.get("house_edge") or 0); items.append({"key":r["game_key"],"name":labels.get(r["game_key"],GAME_VARIANT_LABELS.get(r["game_key"],r["game_key"])),"type":"house_edge","min_stake":float(r["min_stake"]),"max_stake":float(r["max_stake"]),"house_edge":edge,"rtp":1-edge,"enabled":bool(r["enabled"])})
    rate=get_marketplace_commission_rate()
    items += [{"key":"sports","name":labels["sports"],"type":"odds_margin","note":"Sports odds are explicitly entered by Admin; no hidden per-user manipulation.","enabled":True},{"key":"marketplace","name":labels["marketplace"],"type":"commission","commission_rate":rate,"commission_percent":round(rate*100,2),"enabled":True}]
    return jsonify({"items":items,"total":len(items)})


# ---------------------------------------------------------------------------
# UNIFIED 16-GAME ADMIN CONTROL
# ---------------------------------------------------------------------------
UNIFIED_GAME_LABELS = {
    "bomb":"💣 Boom", "number":"🔢 Number", "dice":"🎲 Dice", "dice2":"🎲 Dice", "coinstreak":"🪙 Coin Flip", "slot":"🎰 777 Slot",
    "wheel":"🎡 Lucky Wheel", "keno":"🎯 Keno", "chicken":"🐔 Chicken Road",
    "aviator":"✈️ Aviator", "plinko":"🟣 Plinko", "mines":"💣 Mines",
    "jet":"🚀 Jet", "fish":"🐟 Fish", "rabbit":"🐇 Rabbit Road", "card":"🃏 Card Game", "coinflip":"🪙 Coin Flip", "penalty":"⚽ Penalty Shootout", "penaltystreak":"⚽ Penalty Streak", "chicken2":"🐔 Chicken Road 2", "tower":"🏗 Tower", "dragontiger":"🐉 Dragon Tiger", "andarbahar":"🃏 Andar Bahar", "baccarat":"🎴 Baccarat", "blackjack":"🃏 Blackjack", "roast":"🔥 Chicken Roast", "roulette":"🎡 Roulette", "bingo":"🎱 Bingo", "fastkeno":"⚡ Fast Keno",
    "sports":"⚽ Sports Betting", "marketplace":"🛍️ Marketplace",
}
UNIFIED_GAME_LABELS.update(GAME_VARIANT_LABELS)
# Games that exist in the lobby and in cabinet_game_settings but were missing from the admin "Game Economics" tab:
UNIFIED_GAME_LABELS.update({"minesx": "💣 Mines X", "buffalo": "🦬 Buffalo Plains", "aztec": "🗿 Aztec Gold", "flame": "🔥 Flame Classics", "triplegold": "🔔 Triple Gold"})
UNIFIED_GAME_KEYS = tuple(UNIFIED_GAME_LABELS.keys())

@app.route("/api/admin/game-control", methods=["GET","POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_game_control():
    conn=db(); cur=conn.cursor()
    if request.method == "POST":
        body=request.get_json(silent=True) or {}
        key=str(body.get("key") or "")
        if key not in UNIFIED_GAME_KEYS:
            conn.close(); return jsonify({"error":"unknown game"}),400
        try:
            enabled=bool(body.get("enabled",True))
            if key in ("bomb","number"):
                fee=parse_money(body.get("entry_fee"),"entry_fee")
                edge=float(body.get("house_edge"))
                if fee<=0 or not math.isfinite(edge) or not 0<=edge<=MAX_HOUSE_EDGE: raise ValueError(f"house edge must be 0-{MAX_HOUSE_EDGE*100:.0f}%")
                cur.execute("UPDATE game_settings SET entry_fee=?,house_edge=?,enabled=? WHERE key=?",(fee,edge,int(enabled),key))
                if cur.rowcount!=1: raise ValueError("game settings row missing")
                details={"key":key,"enabled":enabled,"entry_fee":fee,"house_edge":edge,"rtp":1-edge}
            elif key in CABINET_GAME_KEYS:
                mn=parse_money(body.get("min_stake"),"min_stake"); mx=parse_money(body.get("max_stake"),"max_stake"); edge=float(body.get("house_edge"))
                if mn<=0 or mx<mn or not math.isfinite(edge) or not 0<=edge<=MAX_HOUSE_EDGE: raise ValueError(f"invalid stake limits or house edge (max {MAX_HOUSE_EDGE*100:.0f}%)")
                cur.execute("UPDATE cabinet_game_settings SET enabled=?,min_stake=?,max_stake=?,house_edge=?,updated_at=? WHERE game_key=?",(int(enabled),mn,mx,edge,_now(),key))
                if cur.rowcount!=1: raise ValueError("cabinet settings row missing")
                if key=="wheel":
                    raw_prizes = body.get("wheel_prizes")
                    if not isinstance(raw_prizes, list):
                        raw_prizes = _wheel_prizes()
                    prizes = _normalize_wheel_prizes(raw_prizes, edge)
                    cur.execute("UPDATE cabinet_game_settings SET wheel_prizes=? WHERE game_key='wheel'",(json.dumps(prizes,separators=(",",":")),))
                details={"key":key,"enabled":enabled,"min_stake":mn,"max_stake":mx,"house_edge":edge,"rtp":1-edge}
            elif key=="sports":
                cur.execute("UPDATE platform_settings SET value=?,updated_at=? WHERE key='sports_enabled'",("1" if enabled else "0",_now()))
                details={"key":key,"enabled":enabled}
            else: # marketplace
                cur.execute("UPDATE platform_settings SET value=?,updated_at=? WHERE key='marketplace_enabled'",("1" if enabled else "0",_now()))
                rate=body.get("commission_percent")
                if rate is not None:
                    rate=float(rate)
                    if not math.isfinite(rate) or not 0<=rate<=95: raise ValueError("commission must be between 0% and 95%")
                    cur.execute("UPDATE platform_settings SET value=?,updated_at=? WHERE key='marketplace_commission_rate'",(str(rate/100.0),_now()))
                else:
                    rate=get_marketplace_commission_rate()*100
                details={"key":key,"enabled":enabled,"commission_percent":rate}
            conn.commit()
            _log_admin_action(g.tg_user["id"],"unified_game_control_update",details)
            return jsonify({"ok":True,**details})
        except (ValueError,TypeError) as e:
            conn.rollback(); return jsonify({"error":str(e)}),400
        finally:
            conn.close()
    # GET: return all 16, including revenue/stake/payout counts from the ledger/history.
    cur.execute("SELECT * FROM game_settings WHERE key IN ('bomb','number')")
    classic={r["key"]:dict(r) for r in cur.fetchall()}
    cur.execute("SELECT * FROM cabinet_game_settings")
    cabinet={r["game_key"]:dict(r) for r in cur.fetchall()}
    _gc=_pc.get_controls(cur)   # global min-bet / house-edge overrides (they beat every per-game value)
    cur.execute("SELECT value FROM platform_settings WHERE key='sports_enabled'")
    sr=cur.fetchone(); sports_enabled=bool(int(sr["value"])) if sr else True
    cur.execute("SELECT value FROM platform_settings WHERE key='marketplace_enabled'")
    mr=cur.fetchone(); marketplace_enabled=bool(int(mr["value"])) if mr else True
    cur.execute("SELECT COALESCE(SUM(amount),0) v FROM platform_ledger WHERE entry_type='marketplace_commission'")
    marketplace_revenue=float(cur.fetchone()["v"] or 0)
    items=[]
    for key in UNIFIED_GAME_KEYS:
        if key in classic:
            r=classic[key]; edge=float(r.get("house_edge") or 0)
            item={"key":key,"name":UNIFIED_GAME_LABELS[key],"enabled":bool(r["enabled"]),"entry_fee":float(r["entry_fee"]),"house_edge":edge,"rtp":1-edge,"min_stake":float(r["entry_fee"]),"max_stake":float(r["entry_fee"])}
            _eff_fee=_pc.effective_fixed_fee(float(r["entry_fee"]),_gc)
            item.update({"effective_entry_fee":_eff_fee,"entry_overridden":abs(_eff_fee-float(r["entry_fee"]))>1e-9,"effective_house_edge":(_gc["global_house_edge"] if _gc["global_house_edge_enabled"] else edge),"edge_overridden":bool(_gc["global_house_edge_enabled"]) and abs(_gc["global_house_edge"]-edge)>1e-9})
        elif key in cabinet:
            r=cabinet[key]; edge=float(r.get("house_edge") or 0)
            item={"key":key,"name":UNIFIED_GAME_LABELS[key],"enabled":bool(r["enabled"]),"min_stake":float(r["min_stake"]),"max_stake":float(r["max_stake"]),"house_edge":edge,"rtp":1-edge}
            _en,_emn,_emx,_eedge=_pc.apply_limits(bool(r["enabled"]),float(r["min_stake"]),float(r["max_stake"]),edge,_gc)
            item.update({"effective_min_stake":_emn,"effective_max_stake":_emx,"effective_house_edge":_eedge,
                         "min_overridden":abs(_emn-float(r["min_stake"]))>1e-9,"edge_overridden":abs(_eedge-edge)>1e-9})
            if key=="wheel": item["wheel_prizes"]=_wheel_prizes()
        elif key=="sports":
            item={"key":key,"name":UNIFIED_GAME_LABELS[key],"enabled":sports_enabled,"type":"sports"}
        else:
            item={"key":key,"name":UNIFIED_GAME_LABELS[key],"enabled":marketplace_enabled,"type":"marketplace","commission_percent":round(get_marketplace_commission_rate()*100,2),"revenue":round(marketplace_revenue,2)}
        if key == "bomb":
            cur.execute("""SELECT COUNT(*) rounds,
                       COALESCE(SUM(CASE WHEN p.status!='REFUNDED' THEN r.entry_fee ELSE 0 END),0) staked,
                       COALESCE(SUM(CASE WHEN p.status='WIN' THEN COALESCE(p.win_amount,r.win_amount) ELSE 0 END),0) paid,
                       COALESCE(SUM(CASE WHEN p.status!='REFUNDED' THEN r.entry_fee ELSE 0 END),0)-
                       COALESCE(SUM(CASE WHEN p.status='WIN' THEN COALESCE(p.win_amount,r.win_amount) ELSE 0 END),0) house_result,
                       COALESCE(SUM(CASE WHEN p.status='WIN' THEN 1 ELSE 0 END),0) wins,
                       COALESCE(SUM(CASE WHEN p.status='LOST' THEN 1 ELSE 0 END),0) losses
                       FROM webapp_boom_players p JOIN webapp_boom_rounds r ON r.id=p.round_id""")
            gstats=cur.fetchone()
            item["stats"]={"rounds":int(gstats["rounds"]),"staked":round(float(gstats["staked"]),2),"paid":round(float(gstats["paid"]),2),"house_result":round(float(gstats["house_result"]),2),"wins":int(gstats["wins"]),"losses":int(gstats["losses"])}
        elif key == "number":
            cur.execute("""SELECT COUNT(*) rounds,COALESCE(SUM(entry_fee),0) staked,
                       COALESCE(SUM(payout),0) paid,COALESCE(SUM(entry_fee-payout),0) house_result,
                       COALESCE(SUM(CASE WHEN won=1 THEN 1 ELSE 0 END),0) wins,
                       COALESCE(SUM(CASE WHEN won=0 THEN 1 ELSE 0 END),0) losses
                       FROM webapp_number_rounds""")
            gstats=cur.fetchone()
            item["stats"]={"rounds":int(gstats["rounds"]),"staked":round(float(gstats["staked"]),2),"paid":round(float(gstats["paid"]),2),"house_result":round(float(gstats["house_result"]),2),"wins":int(gstats["wins"]),"losses":int(gstats["losses"])}
        elif key == "sports":
            cur.execute("""SELECT COUNT(*) bets,COALESCE(SUM(stake),0) staked,COALESCE(SUM(payout),0) paid,
                       COALESCE(SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END),0) wins,
                       COALESCE(SUM(CASE WHEN status='LOST' THEN 1 ELSE 0 END),0) losses
                       FROM sports_bets""")
            gstats=cur.fetchone()
            item["stats"]={"rounds":int(gstats["bets"]),"staked":round(float(gstats["staked"]),2),"paid":round(float(gstats["paid"]),2),"house_result":round(float(gstats["staked"]-gstats["paid"]),2),"wins":int(gstats["wins"]),"losses":int(gstats["losses"])}
        elif key == "marketplace":
            cur.execute("SELECT COALESCE(SUM(amount),0) volume, COUNT(*) transactions FROM marketplace_transactions")
            gstats=cur.fetchone()
            item["stats"]={"rounds":int(gstats["transactions"]),"staked":round(float(gstats["volume"]),2),"paid":round(float(marketplace_revenue),2),"house_result":round(float(marketplace_revenue),2),"wins":0,"losses":0}
        else:
            cur.execute("SELECT COUNT(*) rounds,COALESCE(SUM(stake),0) staked,COALESCE(SUM(payout),0) paid,COALESCE(SUM(stake-payout),0) house_result,COALESCE(SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END),0) wins,COALESCE(SUM(CASE WHEN status='LOST' THEN 1 ELSE 0 END),0) losses FROM game_history WHERE game_key=?",(key,))
            gstats=cur.fetchone(); item["stats"]={"rounds":int(gstats["rounds"]),"staked":round(float(gstats["staked"]),2),"paid":round(float(gstats["paid"]),2),"house_result":round(float(gstats["house_result"]),2),"wins":int(gstats["wins"]),"losses":int(gstats["losses"])}
        items.append(item)
    conn.close(); return jsonify({"items":items,"total":len(items)})

# ---------------------------------------------------------------------------
# ADMIN: welcome bonus / global min bet / global house edge / high-stakes cashback
# ---------------------------------------------------------------------------
@app.route("/api/admin/platform-controls", methods=["GET","POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_platform_controls():
    conn=db(); cur=conn.cursor()
    try:
        if request.method=="POST":
            body=request.get_json(silent=True) or {}
            try: values=_pc.validate_update(body, MAX_HOUSE_EDGE)
            except ValueError as e: return jsonify({"error":str(e)}),400
            if not values: return jsonify({"error":"nothing to update"}),400
            before=_pc.get_controls(cur)
            cur.execute("BEGIN IMMEDIATE"); _pc.save_settings(cur,values); conn.commit()
            after=_pc.get_controls(cur)
            _log_admin_action(g.tg_user["id"],"platform_controls_update",{"changed":values,"before":before,"after":after})
            if before["global_house_edge_enabled"]!=after["global_house_edge_enabled"] or abs(before["global_house_edge"]-after["global_house_edge"])>1e-9:
                try: _notify_owner_of_sensitive_action(g.tg_user["id"],"house_edge_change",{"key":"ALL GAMES","old_edge":before["global_house_edge"] if before["global_house_edge_enabled"] else None,"new_edge":after["global_house_edge"] if after["global_house_edge_enabled"] else None})
                except Exception: logger.exception("owner notify failed")
            return jsonify({"ok":True,"controls":after})
        c=_pc.get_controls(cur)
        cur.execute("SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM welcome_bonus_grants"); w=cur.fetchone()
        cur.execute("SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM cashback_grants"); cb=cur.fetchone()
        return jsonify({"controls":c,"welcome_given":{"players":int(w["n"]),"total":round(float(w["t"]),2)},"cashback_given":{"grants":int(cb["n"]),"total":round(float(cb["t"]),2)}})
    finally:
        conn.close()

@app.route("/api/admin/cashback/preview", methods=["GET"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_cashback_preview():
    conn=db()
    try: return jsonify(_pc.preview_cashback(conn.cursor()))
    finally: conn.close()

@app.route("/api/admin/cashback/run", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_cashback_run():
    conn=db()
    try:
        res=_pc.run_cashback(conn,g.tg_user["id"])
    except ValueError as e:
        return jsonify({"error":str(e)}),400
    finally:
        conn.close()
    _log_admin_action(g.tg_user["id"],"cashback_run",res)
    return jsonify({"ok":True,**res})

@app.route("/api/admin/cashback/grant", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_cashback_grant():
    body=request.get_json(silent=True) or {}
    try:
        uid=int(body.get("user_id")); amount=parse_money(body.get("amount"),"amount")
    except (TypeError,ValueError) as e:
        return jsonify({"error":str(e) if str(e) else "user_id and amount are required"}),400
    conn=db()
    try:
        res=_pc.grant_cashback(conn,uid,amount,g.tg_user["id"],body.get("note",""))
    except ValueError as e:
        return jsonify({"error":str(e)}),400
    finally:
        conn.close()
    _log_admin_action(g.tg_user["id"],"cashback_manual_grant",res)
    return jsonify({"ok":True,**res})

@app.route("/api/admin/marketplace/commission", methods=["GET","POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_marketplace_commission():
    if request.method=="GET":
        rate=get_marketplace_commission_rate(); return jsonify({"commission_rate":rate,"commission_percent":round(rate*100,2)})
    body=request.get_json(silent=True) or {}
    try: rate=float(body.get("commission_percent"))/100.0
    except (TypeError,ValueError): return jsonify({"error":"commission_percent is required"}),400
    if not math.isfinite(rate) or rate<0 or rate>0.95: return jsonify({"error":"commission must be between 0% and 95%"}),400
    conn=db(); cur=conn.cursor(); old=get_marketplace_commission_rate(); cur.execute("UPDATE platform_settings SET value=?,updated_at=? WHERE key='marketplace_commission_rate'",(str(rate),_now())); conn.commit(); conn.close()
    _log_admin_action(g.tg_user["id"],"marketplace_commission_update",{"old_percent":old*100,"new_percent":rate*100})
    return jsonify({"status":"success","commission_rate":rate,"commission_percent":round(rate*100,2)})

@app.route("/api/admin/cabinet-games/settings", methods=["GET","POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_cabinet_game_settings():
    conn=db(); cur=conn.cursor()
    if request.method == "POST":
        body=request.get_json(silent=True) or {}; key=str(body.get("game_key") or "")
        if key not in CABINET_GAME_KEYS: conn.close(); return jsonify({"error":"unknown game"}),400
        try:
            mn=parse_money(body.get("min_stake",1),"min_stake")
            mx=parse_money(body.get("max_stake",500),"max_stake")
            # House edge is an explicit, per-game RTP setting; it is not
            # used to force wins/losses for a particular user or round.
            edge=float(body.get("house_edge", CABINET_DEFAULT_HOUSE_EDGE.get(key,DEFAULT_ALL_HOUSE_EDGE)))
        except (ValueError, TypeError) as e:
            conn.close(); return jsonify({"error":str(e)}),400
        if mn<=0 or mx<mn: conn.close(); return jsonify({"error":"invalid stake limits"}),400
        if not 0 <= edge <= MAX_HOUSE_EDGE: conn.close(); return jsonify({"error":f"house_edge must be between 0 and {MAX_HOUSE_EDGE}"}),400
        wheel_prizes = None
        if key == "wheel":
            raw = body.get("wheel_prizes")
            if not isinstance(raw, list): raw = _wheel_prizes()
            try: wheel_prizes = _normalize_wheel_prizes(raw, edge)
            except (TypeError,ValueError,OverflowError) as e:
                conn.close(); return jsonify({"error":str(e)}),400
        enabled=1 if bool(body.get("enabled",True)) else 0
        if key == "wheel":
            cur.execute("UPDATE cabinet_game_settings SET enabled=?,min_stake=?,max_stake=?,house_edge=?,wheel_prizes=?,updated_at=? WHERE game_key=?",(enabled,mn,mx,edge,json.dumps(wheel_prizes,separators=(",",":")),_now(),key))
        else:
            cur.execute("UPDATE cabinet_game_settings SET enabled=?,min_stake=?,max_stake=?,house_edge=?,updated_at=? WHERE game_key=?",(enabled,mn,mx,edge,_now(),key))
        conn.commit(); conn.close()
        details={"game_key":key,"enabled":bool(enabled),"min_stake":mn,"max_stake":mx,"house_edge":edge,"rtp":1-edge}
        if wheel_prizes is not None: details["wheel_prizes"]=wheel_prizes
        _log_admin_action(g.tg_user["id"],"cabinet_game_settings_update",details)
        return jsonify({"ok":True})
    cur.execute("SELECT * FROM cabinet_game_settings ORDER BY game_key"); rows=[dict(r) for r in cur.fetchall()]; conn.close()
    for row in rows:
        row["label"] = GAME_VARIANT_LABELS.get(row.get("game_key"))
        row["rtp"] = round(1.0 - float(row.get("house_edge",0.05)), 4)
        if row.get("game_key") == "wheel": row["wheel_prizes"] = _wheel_prizes()
    return jsonify({"items":rows})


def _run_cabinet(uid, key, body, settle=True):
    stake = _cabinet_stake(body)
    if stake <= 0:
        return None, (jsonify({"error": "stake must be greater than zero"}), 400)
    enabled, min_stake, max_stake, house_edge = _cabinet_limits(key)
    if not enabled:
        return None, (jsonify({"error": "game is temporarily disabled"}), 403)
    if stake < min_stake or stake > max_stake:
        return None, (jsonify({"error": f"stake must be between {min_stake:.2f} and {max_stake:.2f}"}), 400)
    orig_key, key = key, _eng(key)   # settings/history use the variant key; the maths use the engine
    idempotency_key = (request.headers.get("X-Idempotency-Key") or "").strip()[:128] or None

    if key == "dice2":
        mode = str(body.get("mode", "")).lower(); ok, err = dice2_valid(mode, body.get("target"))
        if not ok: return None, (jsonify({"error": err}), 400)
        target = int(body.get("target")); d1, d2 = secrets.randbelow(6) + 1, secrets.randbelow(6) + 1
        p = dice2_chance(mode, target); won = dice2_won(mode, target, d1 + d2); payout = stake / p if won else 0
        outcome = {"dice": [d1, d2], "total": d1 + d2, "mode": mode, "target": target, "chance": round(p, 6)}
    elif key == "dice":
        guess = int(body.get("guess", 0))
        if guess not in range(1, 7): return None, (jsonify({"error": "guess must be 1-6"}), 400)
        roll = secrets.randbelow(6) + 1; won = roll == guess; payout = stake * 5.70 if won else 0
        outcome = {"roll": roll, "guess": guess}
    elif key == "slot":
        so, mult = slot_math.spin_round(secrets.SystemRandom())
        won = mult > 0; payout = stake * mult; outcome = dict(so, multiplier=mult)
    elif key == "wheel":
        prizes = _wheel_prizes()
        sector = secrets.randbelow(len(prizes))
        mult = prizes[sector]
        won = mult > 0; payout = stake * mult; outcome = {"sector": sector + 1, "multiplier": mult, "prizes": prizes}
    elif key == "keno":
        nums = sorted(set(int(x) for x in body.get("numbers", [])))
        if len(nums) != 5 or any(x < 1 or x > 20 for x in nums): return None, (jsonify({"error": "choose exactly 5 numbers from 1-20"}), 400)
        draw = sorted(secrets.SystemRandom().sample(range(1, 21), 5)); hits = len(set(nums) & set(draw)); mult = KENO_PAYTABLE.get(hits, 0)
        won = mult > 0; payout = stake * mult; outcome = {"selected": nums, "draw": draw, "hits": hits, "multiplier": mult}
    elif key in ("chicken", "rabbit", "penaltystreak", "tower", "chicken2", "coinstreak"):
        return None, (jsonify({"error": "Road games are played step by step: use /round/start, then /action step|cashout"}), 400)
    elif key in ("aviator", "jet"):
        cashout = float(body.get("cashout", 2.0))
        if not (1.01 <= cashout <= 100): return None, (jsonify({"error": "cashout must be 1.01-100"}), 400)
        # Server-authoritative crash point. The configured house edge is
        # built directly into the distribution. Keep the settlement value
        # unrounded and allow an instant 1.00x crash; display rounding only
        # happens on the client. This avoids a hidden RTP floor at 101%.
        u = (secrets.randbelow(999999) + 1) / 1000000
        crash = min(100.0, max(1.0, (1.0 - house_edge) / (1.0 - u)))
        won = cashout <= crash; payout = stake * cashout if won else 0
        outcome = {"cashout": cashout, "crash": crash, "cashed_out": won}
    elif key == "plinko":
        slots = [0,0.5,0.8,1.0,1.2,1.5,2,3,5]
        bucket = secrets.randbelow(9)
        ones = set(secrets.SystemRandom().sample(range(8), bucket))
        path = [1 if i in ones else 0 for i in range(8)]
        mult = slots[sum(path)]; won = mult > 0; payout = stake * mult
        outcome = {"path": path, "landing_slot": sum(path), "multiplier": mult}
    elif key == "mines":
        mine_count = int(body.get("mines", 3)); pick = int(body.get("pick", 1))
        if not 1 <= mine_count <= 8 or not 1 <= pick <= 25: return None, (jsonify({"error": "mines 1-8 and pick 1-25"}), 400)
        mine_positions = set(secrets.SystemRandom().sample(range(1,26), mine_count)); won = pick not in mine_positions
        mult = round(25 / (25 - mine_count) * 0.92, 2); payout = stake * mult if won else 0
        outcome = {"pick": pick, "mine_count": mine_count, "mine_positions": sorted(mine_positions), "safe": won, "multiplier": mult}
    elif key == "fish":
        shot = int(body.get("shot", 1));
        if not 1 <= shot <= 5: return None, (jsonify({"error": "shot must be 1-5"}), 400)
        mult = secrets.choice(FISH_TABLE); won = mult > 0; payout = stake * mult; outcome = {"shot": shot, "multiplier": mult, "target": shot}
    elif key == "card":
        choice = str(body.get("choice", "high")).lower()
        if choice not in ("high", "low"): return None, (jsonify({"error": "choice must be high or low"}), 400)
        card = secrets.randbelow(13) + 1; won = (choice == "high" and card >= 8) or (choice == "low" and card <= 6); payout = stake * 1.85 if won else 0
        outcome = {"card": card, "choice": choice}
    elif key == "coinflip":
        choice = str(body.get("choice", "")).lower()
        if choice not in ("heads", "tails"): return None, (jsonify({"error": "choice must be heads or tails"}), 400)
        flip = "heads" if secrets.randbelow(2) == 0 else "tails"
        won = flip == choice; payout = stake * 2.0 if won else 0
        outcome = {"flip": flip, "choice": choice}
    elif key == "penalty":
        choice = str(body.get("choice", "")).lower()
        if choice not in ("left", "center", "right"): return None, (jsonify({"error": "choice must be left, center or right"}), 400)
        keeper = ("left", "center", "right")[secrets.randbelow(3)]
        won = keeper != choice; payout = stake * 1.5 if won else 0
        outcome = {"keeper": keeper, "choice": choice, "goal": won}
    elif key == "baccarat":
        choice = str(body.get("choice", "")).lower()
        if choice not in ("player", "banker", "tie"): return None, (jsonify({"error": "choice must be player, banker or tie"}), 400)
        deal = bacc_deal(random.SystemRandom())
        push = deal["winner"] == "tie" and choice != "tie"
        won = deal["winner"] == choice
        payout = stake * BACC_M[choice] if won else (stake if push else 0)
        outcome = dict(deal, choice=choice, push=push)
    elif key == "dragontiger":
        choice = str(body.get("choice", "")).lower()
        if choice not in ("dragon", "tiger", "tie"): return None, (jsonify({"error": "choice must be dragon, tiger or tie"}), 400)
        deal = dt_deal(random.SystemRandom())
        push = deal["winner"] == "tie" and choice != "tie"
        won = deal["winner"] == choice
        payout = stake * DT_M[choice] if won else (stake if push else 0)
        outcome = dict(deal, choice=choice, push=push)
    elif key == "andarbahar":
        choice = str(body.get("choice", "")).lower()
        if choice not in ("andar", "bahar"): return None, (jsonify({"error": "choice must be andar or bahar"}), 400)
        deal = ab_deal(random.SystemRandom())
        won = deal["winner"] == choice
        payout = stake * AB_M[choice] if won else 0
        outcome = dict(deal, choice=choice)
    else:
        return None, (jsonify({"error": "unknown game"}), 404)
    base_multiplier = outcome.get("multiplier")
    payout, applied_scale = _apply_cabinet_house_edge(key, stake, payout, outcome, house_edge)
    payout = min(payout, MAX_ROUND_PAYOUT_ETB)
    if key == "mines" and won:
        payout = max(stake, payout)
    elif payout < stake:
        # A payout below the stake is a net loss for the player: never record or
        # announce it as WON (applies to every game, not only Plinko/Fish).
        won = False
    if key == "wheel":
        outcome["prizes"] = [round(float(v) * applied_scale, 4) for v in _wheel_prizes()]
    if base_multiplier is not None:
        outcome["base_multiplier"] = base_multiplier
        outcome["multiplier"] = round(payout / stake, 4) if payout > 0 else 0.0
    outcome["effective_multiplier"] = round(payout / stake, 4) if payout > 0 else 0.0
    outcome["house_edge"] = house_edge
    outcome["rtp"] = round(1.0 - house_edge, 4)
    outcome["payout_scale"] = applied_scale
    outcome["server_authoritative"] = True
    outcome["validated_at"] = _now()
    if not settle:
        return {"ok": True, "game": orig_key, "won": bool(won), "stake": stake, "payout": payout, "outcome": outcome}, None
    return _settle_cabinet_game(uid, orig_key, stake, won, payout, outcome, idempotency_key)


for _game_key in CABINET_GAME_KEYS:
    _cabinet_history_route(_game_key)

for _game_key in CABINET_GAME_KEYS:
    def _make_play(key):
        def play():
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                return jsonify({"error": "request body must be a JSON object"}), 400
            try:
                result, error = _run_cabinet(g.tg_user["id"], key, body)
                if error is not None:
                    return error
                return jsonify(result)
            except (TypeError, ValueError, OverflowError):
                return jsonify({"error": "invalid game input"}), 400
        play.__name__ = f"cabinet_{key}_play_impl"
        return play
    _fn = _make_play(_game_key)
    _cabinet_game_route(_game_key)(_fn)

# ------------------------------------------------------------
# REAL-TIME CABINET ROUND ENGINE
#
# The canonical implementation is loaded from realtime_engine_v3.py at
# the end of this module. Keeping only one implementation prevents Flask
# from registering duplicate /round/start, /state and /action routes.
# ------------------------------------------------------------

# ------------------------------------------------------------
# LIVE CALL SIGNALING
# The canonical WebRTC implementation is loaded from
# realtime_engine_v3.py at the end of this module.  Keeping one
# implementation avoids duplicate Flask routes for /calls/* and one
# storage model for call sessions/signals.
# ------------------------------------------------------------

# ------------------------------------------------------------
# Boom Game (Mini App version): shared room, DB-backed.
#
# The chat version shares one board per Telegram GROUP (chat_id).
# The Mini App has no group concept -- it's a private per-user
# webview -- so Mini App players instead share ONE global room per
# active round. The frontend polls GET /state every second, exactly
# like the chat version's 1-second live tick, to see other players
# join/leave and see boxes opened in near-real-time.
#
# This is a fully separate game instance from EXTRA_GROUP_GAMES in
# kdm_bot.py -- a Mini App round and a group-chat round never share
# players, bombs, or state.
# ------------------------------------------------------------

BOOM_ROUND_TIMEOUT_MINUTES = 15


def _get_or_create_boom_round(cur):
    cur.execute(
        "SELECT * FROM webapp_boom_rounds WHERE game_over=0 ORDER BY id DESC LIMIT 1"
    )
    r = cur.fetchone()
    if r:
        try:
            age_minutes = (datetime.now() - datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
        except (ValueError, TypeError):
            age_minutes = 0
        if age_minutes < BOOM_ROUND_TIMEOUT_MINUTES:
            # Admin changed the min bet / house edge while a fresh round is still empty: re-price it now so the
            # change applies to the very next player instead of after the round ends. (Rounds with players keep
            # the price they were joined at, so nobody is charged a different fee mid-round.)
            cur.execute("SELECT COUNT(*) FROM webapp_boom_players WHERE round_id=?", (r["id"],))
            if int(cur.fetchone()[0]) == 0:
                _cfg = _get_game_setting("bomb")
                if abs(float(r["entry_fee"]) - _cfg["entry_fee"]) > 1e-9 or abs(float(r["win_amount"]) - _cfg["win_amount"]) > 1e-9:
                    cur.execute("UPDATE webapp_boom_rounds SET entry_fee=?, win_amount=? WHERE id=?",
                                (_cfg["entry_fee"], _cfg["win_amount"], r["id"]))
                    cur.execute("SELECT * FROM webapp_boom_rounds WHERE id=?", (r["id"],))
                    r = cur.fetchone()
            return r

        # Abandoned round (nobody finished it, e.g. the player closed
        # their browser mid-round) -- refund anyone still 'playing'
        # rather than silently keeping their entry fee for nothing,
        # close this round out, and fall through to start a fresh one.
        cur.execute(
            "SELECT user_id FROM webapp_boom_players WHERE round_id=? AND status='playing'",
            (r["id"],)
        )
        stuck_players = [row["user_id"] for row in cur.fetchall()]
        now = _now()
        for uid in stuck_players:
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r["entry_fee"], uid))
            cur.execute(
                "INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES (?,?,?,?)",
                (uid, r["entry_fee"], "group_mines_timeout_refund", now)
            )
            # Undo the pool contribution and the rake taken at join time, so the refund is exact.
            _rk, _sh = _rake_split(r["entry_fee"])
            _pool_carry_add(cur, "boom", -_sh)
            _platform_record(cur, "boom_pool_rake", -_rk, f"boom:{r['id']}", "boom timeout refund: rake reversed", now)
        cur.execute(
            "UPDATE webapp_boom_players SET status='ABANDONED' WHERE round_id=? AND status='playing'",
            (r["id"],)
        )
        cur.execute("UPDATE webapp_boom_rounds SET game_over=1 WHERE id=?", (r["id"],))

    settings = _get_game_setting("bomb")

    # PROVABLY FAIR: server_seed is generated now, BEFORE anyone has
    # played this round, and its bombs are a deterministic function of
    # it -- so the bombs are fixed at this exact moment and cannot be
    # changed later based on how the round goes. commitment (its
    # SHA-256 hash) is shown to players immediately via boom_state();
    # server_seed itself stays secret until the round ends, at which
    # point boom_history() reveals it so anyone can independently
    # recompute SHA-256(server_seed) == commitment and re-derive the
    # same bomb positions themselves.
    server_seed = secrets.token_hex(16)
    commitment = hashlib.sha256(server_seed.encode()).hexdigest()
    bombs = random.Random(server_seed).sample(range(1, 10), 3)

    cur.execute(
        """INSERT INTO webapp_boom_rounds(bombs, opened, game_over, entry_fee, win_amount, created_at, server_seed, commitment)
           VALUES (?,?,0,?,?,?,?,?)""",
        (json.dumps(bombs), json.dumps([]), settings["entry_fee"], settings["win_amount"], _now(),
         server_seed, commitment)
    )
    cur.execute("SELECT * FROM webapp_boom_rounds WHERE id=?", (cur.lastrowid,))
    return cur.fetchone()


def _boom_pool_shares(pool, winners):
    """winners = [(user_id, weight)]. Returns {user_id: payout}. Pays at most min(pool, cap) in total,
    in whole cents, proportionally to weight."""
    total_w = sum(w for _, w in winners)
    if total_w <= 0 or pool <= 0:
        return {uid: 0.0 for uid, _ in winners}
    distributable_c = int(min(pool, MAX_ROUND_PAYOUT_ETB) * 100)
    return {uid: math.floor(distributable_c * w / total_w) / 100.0 for uid, w in winners}


def _boom_prize_for_stage(base_win_amount, opened_count):
    """Fair prize for a player who joins after `opened_count` safe boxes are already open.
    Needing all remaining (6-k) safe boxes out of (9-k) with 3 bombs has probability
    1/C(9-k,3); at k=0 this is exactly base_win_amount (1/84). Without this, joining
    late (e.g. 5 safe boxes already open = 25% to win a 588 prize for 10) was a large +EV exploit."""
    k = max(0, min(5, int(opened_count)))
    return round(float(base_win_amount) / math.comb(9, 3) * math.comb(9 - k, 3), 2)


def _serialize_boom_round(cur, rnd):
    cur.execute(
        "SELECT user_id, name, status, win_amount FROM webapp_boom_players WHERE round_id=?",
        (rnd["id"],)
    )
    players = [dict(p) for p in cur.fetchall()]
    opened_list = json.loads(rnd["opened"])
    my_prize = None
    try:
        me = g.tg_user["id"]
        mine = next((p for p in players if p["user_id"] == me and p.get("win_amount") is not None), None)
        my_prize = mine["win_amount"] if mine else _boom_prize_for_stage(rnd["win_amount"], len(opened_list))
    except Exception:
        my_prize = _boom_prize_for_stage(rnd["win_amount"], len(opened_list))
    for p in players:
        p.pop("win_amount", None)
    # Pool model: the displayed prize is an ESTIMATE of your share of the current prize pool.
    _pool = _pool_carry_get(cur, "boom")
    try:
        cur.execute("SELECT user_id, win_amount FROM webapp_boom_players WHERE round_id=? AND status='playing'", (rnd["id"],))
        _ws = [(r_["user_id"], float(r_["win_amount"] or 0)) for r_ in cur.fetchall()]
    except Exception:
        _ws = []
    _join_w = _boom_prize_for_stage(rnd["win_amount"], len(opened_list))
    _rk, _sh = _rake_split(rnd["entry_fee"])
    _est_pool = min(_pool + _sh, MAX_ROUND_PAYOUT_ETB)
    _sum_w = sum(w for _, w in _ws) + _join_w
    _est_join = round(_est_pool * _join_w / _sum_w, 2) if _sum_w > 0 else 0.0
    _mine_w = next((w for u, w in _ws if u == g.tg_user["id"]), None) if getattr(g, "tg_user", None) else None
    _est_mine = round(min(_pool, MAX_ROUND_PAYOUT_ETB) * _mine_w / sum(w for _, w in _ws), 2) if _mine_w else _est_join
    my_prize = _est_mine
    # The client needs to know whether *it* is in this round (to confirm the entry fee before the
    # first pick and to enable/disable Leave), and -- only once the round is over -- where the bombs were.
    _me = g.tg_user["id"] if getattr(g, "tg_user", None) else None
    _mine_row = next((p for p in players if p["user_id"] == _me), None)
    return {
        "my_status": _mine_row["status"] if _mine_row else None,
        "bombs": json.loads(rnd["bombs"]) if rnd["game_over"] else None,
        "your_win_amount": my_prize,
        "join_win_amount": _est_join,
        "prize_pool": _pool,
        "rake_pct": _pool_rake_pct(),
        "pool_mode": True,
        "round_id": rnd["id"],
        "opened": json.loads(rnd["opened"]),
        "game_over": bool(rnd["game_over"]),
        "entry_fee": rnd["entry_fee"],
        "win_amount": rnd["win_amount"],
        # Other players' Telegram ids are not the client's business -- only name + status.
        "players": [{"name": p["name"], "status": p["status"]} for p in players],
        # Provably-fair commitment -- safe to show even mid-round,
        # since it reveals nothing about WHICH boxes are bombs, only
        # that they were fixed in advance. Save this before playing if
        # you want to verify it later against the revealed seed.
        "commitment": rnd["commitment"],
        # bomb positions themselves are NEVER sent to the client while
        # a round is open -- that would let a player see them in
        # devtools/network tab and defeat the whole game.
    }


@app.route("/api/games/boom/state")
@require_telegram_auth
def boom_state():
    settings = _get_game_setting("bomb")
    if not settings["enabled"]:
        return jsonify({"error": "Boom Game is currently disabled"}), 403

    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN")
    rnd = _get_or_create_boom_round(cur)
    conn.commit()
    data = _serialize_boom_round(cur, rnd)
    conn.close()
    return jsonify(data)


@app.route("/api/games/boom/history")
@require_telegram_auth
def boom_history():
    """Past COMPLETED rounds only, bomb positions included -- this is
    intentionally the only place bomb positions are ever revealed to
    the client, and only after the round is long over. Lets a player
    verify for themselves that bombs are placed once per round (not
    dynamically to deny wins) and see actual outcomes, which is the
    whole point of a transparency/fairness log.

    Also reveals server_seed and commitment: verify SHA-256(server_seed)
    == commitment, and that random.Random(server_seed).sample(range(1,10),3)
    reproduces the exact same bombs list -- proof the bombs were fixed
    the moment the round started (when commitment was first shown),
    not chosen afterward based on how anyone played."""
    limit = min(int(request.args.get("limit", 20)), 50)
    conn = db(); cur = conn.cursor()
    cur.execute(
        """SELECT id, bombs, opened, created_at, server_seed, commitment FROM webapp_boom_rounds
           WHERE game_over=1 ORDER BY id DESC LIMIT ?""",
        (limit,)
    )
    rounds = []
    for row in cur.fetchall():
        cur.execute(
            "SELECT name, status FROM webapp_boom_players WHERE round_id=?",
            (row["id"],)
        )
        players = [dict(p) for p in cur.fetchall()]
        rounds.append({
            "round_id": row["id"],
            "bombs": json.loads(row["bombs"]),
            "opened": json.loads(row["opened"]),
            "created_at": row["created_at"],
            "players": players,
            "server_seed": row["server_seed"],
            "commitment": row["commitment"],
        })
    conn.close()
    return jsonify({"rounds": rounds})


@app.route("/api/games/number/history")
@require_telegram_auth
def number_game_history():
    """Number Game's equivalent of Boom Game's fairness log -- every
    round already resolves and is forgotten instantly (unlike Boom,
    there's no 'ongoing round' state to protect), so every row here
    is always safe to show in full including the secret number."""
    limit = min(int(request.args.get("limit", 20)), 50)
    conn = db(); cur = conn.cursor()
    cur.execute(
        """SELECT first_name, guess, secret, won, entry_fee, payout, created_at
           FROM webapp_number_rounds ORDER BY id DESC LIMIT ?""",
        (limit,)
    )
    rounds = []
    for row in cur.fetchall():
        name = (row["first_name"] or "User").strip()
        masked = (name[:3] + "***") if len(name) > 3 else name  # same masking style as /api/wins/recent
        rounds.append({
            "name": masked,
            "guess": row["guess"],
            "secret": row["secret"],
            "won": bool(row["won"]),
            "entry_fee": row["entry_fee"],
            "payout": row["payout"],
            "created_at": row["created_at"],
        })
    conn.close()
    return jsonify({"rounds": rounds})


@app.route("/api/games/boom/pick", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=20, window_seconds=10)
def boom_pick():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    try:
        box = int(body.get("box"))
        if not (1 <= box <= 9):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "box must be 1-9"}), 400

    settings = _get_game_setting("bomb")
    if not settings["enabled"]:
        return jsonify({"error": "Boom Game is currently disabled"}), 403

    conn = db(); cur = conn.cursor()
    # BEGIN IMMEDIATE: this whole join+pick+resolve sequence must be
    # atomic, the same way close_auction() in kdm_bot.py locks around
    # its read-then-write -- otherwise two players' simultaneous picks
    # could both read "6 opened so far" and both trigger the win
    # payout, or both narrowly miss seeing a bomb the other just hit.
    cur.execute("BEGIN IMMEDIATE")

    rnd = _get_or_create_boom_round(cur)
    if rnd["game_over"]:
        conn.rollback(); conn.close()
        return jsonify({"error": "round already ended, refresh state"}), 409

    opened = json.loads(rnd["opened"])
    bombs = json.loads(rnd["bombs"])
    entry_fee = rnd["entry_fee"]
    win_amount = rnd["win_amount"]

    if box in opened:
        conn.rollback(); conn.close()
        return jsonify({"error": "box already opened"}), 409

    cur.execute(
        "SELECT * FROM webapp_boom_players WHERE round_id=? AND user_id=?",
        (rnd["id"], uid)
    )
    player = cur.fetchone()

    if player and player["status"] != "playing":
        conn.rollback(); conn.close()
        return jsonify({"error": "this round already ended for you"}), 409

    if not player:
        cur.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
            (entry_fee, uid, entry_fee)
        )
        if cur.rowcount != 1:
            conn.rollback(); conn.close()
            return jsonify({"error": "insufficient balance"}), 400

        now = _now()
        cur.execute(
            """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
               VALUES(?,?,?,?)""",
            (uid, -entry_fee, "group_mines_bet", now)
        )
        _rk, _sh = _rake_split(entry_fee)
        _pool_carry_add(cur, "boom", _sh)
        _platform_record(cur, "boom_pool_rake", _rk, f"boom:{rnd['id']}", "boom pool rake", now)
        cur.execute(
            """INSERT INTO webapp_boom_players(round_id,user_id,name,status,joined_at,win_amount)
               VALUES(?,?,?,?,?,?)""",
            (rnd["id"], uid, g.tg_user.get("first_name", "User"), "playing", now,
             _boom_prize_for_stage(win_amount, len(opened)))
        )

    if box in bombs:
        # BOOM -- round over, everyone still "playing" loses, no refund.
        cur.execute(
            "UPDATE webapp_boom_rounds SET game_over=1, opened=? WHERE id=?",
            (json.dumps(opened + [box]), rnd["id"])
        )
        cur.execute(
            "UPDATE webapp_boom_players SET status='LOST' WHERE round_id=? AND status='playing'",
            (rnd["id"],)
        )
        conn.commit()
        cur.execute("SELECT * FROM webapp_boom_rounds WHERE id=?", (rnd["id"],))
        data = _serialize_boom_round(cur, cur.fetchone())
        conn.close()
        data["result"] = "BOOM"
        return jsonify(data)

    opened = opened + [box]

    if len(opened) >= 6:
        # All 6 safe boxes cleared -- pay every still-playing player.
        cur.execute(
            "SELECT user_id, win_amount FROM webapp_boom_players WHERE round_id=? AND status='playing'",
            (rnd["id"],)
        )
        winners = [(r["user_id"], float(r["win_amount"] if r["win_amount"] is not None else win_amount)) for r in cur.fetchall()]
        now = _now()
        # POOL PAYOUT: winners share min(pool, MAX_ROUND_PAYOUT_ETB) in proportion to their risk weight
        # (a player who joined after k safe boxes were already open carried less risk, so has a smaller
        # weight). Unpaid remainder stays in the pool. The house bankroll is never used.
        for wid, prize in _boom_pool_shares(_pool_carry_get(cur, "boom"), winners).items():
            if prize <= 0:
                continue
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (prize, wid))
            cur.execute(
                """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
                   VALUES(?,?,?,?)""",
                (wid, prize, "group_mines_win", now)
            )
            _pool_carry_add(cur, "boom", -prize)
        cur.execute(
            "UPDATE webapp_boom_players SET status='WIN' WHERE round_id=? AND status='playing'",
            (rnd["id"],)
        )
        cur.execute(
            "UPDATE webapp_boom_rounds SET game_over=1, opened=? WHERE id=?",
            (json.dumps(opened), rnd["id"])
        )
        conn.commit()
        cur.execute("SELECT * FROM webapp_boom_rounds WHERE id=?", (rnd["id"],))
        data = _serialize_boom_round(cur, cur.fetchone())
        conn.close()
        data["result"] = "WIN"
        return jsonify(data)

    cur.execute(
        "UPDATE webapp_boom_rounds SET opened=? WHERE id=?",
        (json.dumps(opened), rnd["id"])
    )
    conn.commit()
    cur.execute("SELECT * FROM webapp_boom_rounds WHERE id=?", (rnd["id"],))
    data = _serialize_boom_round(cur, cur.fetchone())
    conn.close()
    data["result"] = "SAFE"
    return jsonify(data)


@app.route("/api/games/boom/leave", methods=["POST"])
@require_telegram_auth
def boom_leave():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")

    cur.execute(
        "SELECT * FROM webapp_boom_rounds WHERE game_over=0 ORDER BY id DESC LIMIT 1"
    )
    rnd = cur.fetchone()
    if not rnd:
        conn.rollback(); conn.close()
        return jsonify({"error": "no active round"}), 404

    cur.execute(
        "SELECT * FROM webapp_boom_players WHERE round_id=? AND user_id=?",
        (rnd["id"], uid)
    )
    player = cur.fetchone()
    if not player or player["status"] != "playing":
        conn.rollback(); conn.close()
        return jsonify({"error": "you are not an active player in this round"}), 400

    # Leaving forfeits the entry fee, same rule as the chat version.
    cur.execute(
        "UPDATE webapp_boom_players SET status='LEFT' WHERE id=?", (player["id"],)
    )
    conn.commit()

    cur.execute("SELECT * FROM webapp_boom_rounds WHERE id=?", (rnd["id"],))
    data = _serialize_boom_round(cur, cur.fetchone())
    conn.close()
    return jsonify(data)


# ------------------------------------------------------------
# MARKETPLACE (consulting/coaching services: photo report, video
# review, video call, audio call) -- shares the SAME users.balance
# wallet as the games, the same require_telegram_auth/rate_limit
# infrastructure, and logs into the SAME transactions table so it
# shows up in the existing /api/history feed automatically.
# ------------------------------------------------------------

def _init_marketplace_tables():
    conn = db(); cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_posts (
        post_id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        title TEXT,
        service_type TEXT, -- photo/video/voice/video_call/audio_call + legacy types
        price REAL,
        active INTEGER DEFAULT 1,
        description TEXT, sample_file_id TEXT, sample_media_type TEXT,
        sample_message_id INTEGER, created_at TEXT, category TEXT, duration_minutes INTEGER
    )
    """)
    cur.execute("SELECT COUNT(*) c FROM marketplace_posts")
    # Fake placeholder listings are DEMO-ONLY. In production they would be real,
    # purchasable services (owned by the admin) that nobody can deliver, and they
    # are not moderation-approved, so /view, /like etc. answered 404 for them.
    if os.getenv("SEED_DEMO_MARKETPLACE", "0").strip() == "1" and cur.fetchone()["c"] == 0:
        # Placeholder listings so the tab isn't empty on first run.
        sample = [
            (ADMIN_ID, "የቢዝነስ እቅድ ግምገማ (Photo Report)", "consult_photo", 30.0),
            (ADMIN_ID, "የCV/ Resume ግምገማ ቪዲዮ ማብራሪያ", "consult_video", 50.0),
            (ADMIN_ID, "1-on-1 የካሪየር ምክክር (Video Call)", "video_call", 150.0),
            (ADMIN_ID, "የፋይናንስ እቅድ ምክክር (Audio Call)", "audio_call", 100.0),
        ]
        cur.executemany(
            "INSERT INTO marketplace_posts (creator_id, title, service_type, price) VALUES (?,?,?,?)",
            sample
        )
    cur.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_transactions (
        tx_id TEXT PRIMARY KEY,
        buyer_id INTEGER,
        creator_id INTEGER,
        post_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'held_in_escrow', -- 'held_in_escrow','completed','refunded'
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_reviews (
        review_id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_id TEXT,
        buyer_id INTEGER,
        creator_id INTEGER,
        rating INTEGER,
        comment TEXT,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER,
        post_id INTEGER,
        creator_id INTEGER,
        reason TEXT,
        created_at TEXT,
        status TEXT DEFAULT 'open'
    )
    """)

    # Marketplace moderation / creator safety schema. Migrations are additive
    # so existing wallets, posts, escrow and social data are preserved.
    def _add_col(table, col, typ):
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    _add_col('marketplace_posts', 'moderation_status', "TEXT DEFAULT 'pending'")
    _add_col('marketplace_posts', 'moderation_note', 'TEXT')
    _add_col('marketplace_posts', 'moderated_by', 'INTEGER')
    _add_col('marketplace_posts', 'moderated_at', 'TEXT')
    _add_col('marketplace_posts', 'price_status', "TEXT DEFAULT 'pending'")
    _add_col('marketplace_posts', 'media_status', "TEXT DEFAULT 'pending'")
    _add_col('users', 'marketplace_verified', 'INTEGER DEFAULT 0')
    _add_col('users', 'marketplace_suspended', 'INTEGER DEFAULT 0')
    _add_col('users', 'marketplace_suspension_reason', 'TEXT')
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_moderation_actions (
        action_id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL,
        post_id INTEGER, creator_id INTEGER, media_index INTEGER, action TEXT NOT NULL,
        reason TEXT, note TEXT, created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_media_reviews (
        review_id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL,
        media_index INTEGER NOT NULL, admin_id INTEGER NOT NULL, status TEXT NOT NULL,
        reason TEXT, created_at TEXT NOT NULL, UNIQUE(post_id, media_index)
    )""")
    # Existing listings were already public before moderation existed; do not
    # unexpectedly hide them during migration. New listings are pending.
    cur.execute("UPDATE marketplace_posts SET moderation_status='approved' WHERE moderation_status IS NULL OR moderation_status=''" )
    cur.execute("UPDATE marketplace_posts SET price_status='approved' WHERE price_status IS NULL OR price_status=''" )
    cur.execute("UPDATE marketplace_posts SET media_status='approved' WHERE media_status IS NULL OR media_status=''" )
    conn.commit()
    conn.close()


_init_marketplace_tables()


def _marketplace_requires_review():
    """True only when the operator explicitly wants staff approval BEFORE a post goes live."""
    return os.getenv("MARKETPLACE_REQUIRE_REVIEW", "0").strip().lower() in ("1", "true", "yes", "on")


def _publish_pending_marketplace_posts():
    """Posts made while review was mandatory (or before this fix) stayed 'pending' forever and nobody could see them.
    When review is not required, publish them. Rejected / hidden / deleted posts are NOT touched."""
    if _marketplace_requires_review():
        return
    try:
        conn = db(); cur = conn.cursor()
        cur.execute("""UPDATE marketplace_posts SET moderation_status='approved', price_status='approved', media_status='approved'
                       WHERE active=1 AND (moderation_status='pending' OR price_status='pending' OR media_status='pending')
                         AND COALESCE(moderation_status,'pending') NOT IN ('rejected','hidden','deleted')""")
        conn.commit(); conn.close()
    except Exception as exc:
        app.logger.warning("publish pending marketplace posts failed: %s", exc)

_publish_pending_marketplace_posts()


DEFAULT_MARKETPLACE_COMMISSION_RATE = 0.25

def _init_platform_settings():
    conn=db(); cur=conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS platform_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
    cur.execute("INSERT OR IGNORE INTO platform_settings(key,value,updated_at) VALUES(?,?,?)", ("sports_enabled", "1", _now()))
    cur.execute("INSERT OR IGNORE INTO platform_settings(key,value,updated_at) VALUES(?,?,?)", ("marketplace_enabled", "1", _now()))
    cur.execute("INSERT OR IGNORE INTO platform_settings(key,value,updated_at) VALUES(?,?,?)", ("marketplace_commission_rate", str(DEFAULT_MARKETPLACE_COMMISSION_RATE), _now()))
    conn.commit(); conn.close()

def get_marketplace_commission_rate():
    conn=db(); cur=conn.cursor(); cur.execute("SELECT value FROM platform_settings WHERE key='marketplace_commission_rate'"); r=cur.fetchone(); conn.close()
    try: return max(0.0,min(0.95,float(r["value"]))) if r else DEFAULT_MARKETPLACE_COMMISSION_RATE
    except Exception: return DEFAULT_MARKETPLACE_COMMISSION_RATE

_init_platform_settings()

# Unlike Boom (auto-refunded after 15 min -- a round either resolves
# fast or was abandoned), a marketplace escrow genuinely needs time:
# a creator may need hours or days to deliver a consult/video/call.
# So this uses two tiers instead of one fixed timeout:
#   - ESCROW_OVERDUE_HOURS: just a visibility flag for the admin
#     panel ("this one needs attention"), nothing is touched.
#   - ESCROW_AUTO_REFUND_HOURS: a hard safety net -- if NOBODY (admin
#     or creator) has resolved it by then, the buyer is protected and
#     automatically refunded rather than the money staying stuck in
#     escrow forever with no way out.
ESCROW_OVERDUE_HOURS = 48
ESCROW_AUTO_REFUND_HOURS = 168  # 7 days


def _auto_refund_stale_escrow(cur):
    """Refunds any escrow transaction that has sat in
    'held_in_escrow' past ESCROW_AUTO_REFUND_HOURS. Called lazily at
    the top of marketplace endpoints (same pattern as
    _get_or_create_boom_round's timeout sweep) rather than needing a
    separate cron process. Cheap when there's nothing stale -- one
    indexed-ish SELECT on a small table."""
    cutoff = (datetime.now() - timedelta(hours=ESCROW_AUTO_REFUND_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "SELECT * FROM marketplace_transactions WHERE status='held_in_escrow' AND COALESCE(delivered_at, created_at) < ?",
        (cutoff,)
    )
    stale = cur.fetchall()
    if not stale:
        return
    now = _now()
    for tx in stale:
        cur.execute(
            "UPDATE marketplace_transactions SET status='refunded', resolution_note=? WHERE tx_id=? AND status='held_in_escrow'",
            (f"auto-refunded -- unresolved for over {ESCROW_AUTO_REFUND_HOURS}h", tx["tx_id"])
        )
        if cur.rowcount != 1:
            continue
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (tx["amount"], tx["buyer_id"]))
        cur.execute(
            """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
               VALUES (?,?, 'marketplace_refund', ?)""",
            (tx["buyer_id"], tx["amount"], now)
        )
        cur.execute("INSERT INTO marketplace_notification_outbox(buyer_id,tx_id,message,created_at) VALUES(?,?,?,?)",
                    (tx["buyer_id"], tx["tx_id"], f"🔄 Escrow ግዢዎ (Tx: {tx['tx_id']}) በ{ESCROW_AUTO_REFUND_HOURS} ሰዓት ውስጥ ስላልተፈታ ራስ-ሰር ተመላሽ ሆኗል።", now))


def _marketplace_notification_worker():
    """Send outbox messages only after the transaction that created them commits."""
    while True:
        try:
            conn = db(); cur = conn.cursor()
            rows = cur.execute("SELECT id,buyer_id,tx_id,message FROM marketplace_notification_outbox WHERE sent_at IS NULL ORDER BY id LIMIT 20").fetchall()
            conn.close()
            for row in rows:
                try:
                    result = requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": row["buyer_id"], "text": row["message"]}, timeout=5)
                    ok = result.ok and bool((result.json() or {}).get("ok"))
                except Exception:
                    ok = False
                conn = db(); cur = conn.cursor()
                if ok:
                    cur.execute("UPDATE marketplace_notification_outbox SET sent_at=?,attempts=attempts+1 WHERE id=? AND sent_at IS NULL", (_now(), row["id"]))
                else:
                    cur.execute("UPDATE marketplace_notification_outbox SET attempts=attempts+1 WHERE id=? AND sent_at IS NULL", (row["id"],))
                conn.commit(); conn.close()
        except Exception:
            logger.exception("marketplace notification outbox worker failed")
        time.sleep(2)

MARKETPLACE_MEDIA_URL_TTL = 900  # 15 minutes

def _make_marketplace_media_token(post_id, file_id, expires):
    payload = f"{post_id}:{file_id}:{expires}"
    return hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _marketplace_media_url(post_id, file_id):
    expires = int(time.time()) + MARKETPLACE_MEDIA_URL_TTL
    token = _make_marketplace_media_token(post_id, file_id, expires)
    return f"/api/marketplace/media/{post_id}?expires={expires}&token={token}"



# ------------------------------------------------------------
# MARKETPLACE SOCIAL / NETFLIX FEED
# ------------------------------------------------------------
def _mkt_counts(cur, post_id, uid):
    cur.execute("SELECT COUNT(*) c FROM marketplace_post_likes WHERE post_id=?", (post_id,)); likes=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM marketplace_post_saves WHERE post_id=?", (post_id,)); saves=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM marketplace_post_views WHERE post_id=?", (post_id,)); views=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM marketplace_comments WHERE post_id=?", (post_id,)); comments=cur.fetchone()["c"]
    cur.execute("SELECT 1 FROM marketplace_post_likes WHERE post_id=? AND user_id=?", (post_id,uid)); liked=bool(cur.fetchone())
    cur.execute("SELECT 1 FROM marketplace_post_saves WHERE post_id=? AND user_id=?", (post_id,uid)); saved=bool(cur.fetchone())
    return likes,saves,views,comments,liked,saved

@app.route("/api/marketplace/post/<int:post_id>/like", methods=["POST"])
@require_telegram_auth
def marketplace_like(post_id):
    uid=g.tg_user["id"]; conn=db(); cur=conn.cursor()
    cur.execute("SELECT p.post_id FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0",(post_id,))
    if not cur.fetchone(): conn.close(); return jsonify({"error":"post not found"}),404
    cur.execute("SELECT 1 FROM marketplace_post_likes WHERE post_id=? AND user_id=?",(post_id,uid))
    if cur.fetchone(): cur.execute("DELETE FROM marketplace_post_likes WHERE post_id=? AND user_id=?",(post_id,uid)); liked=False
    else: cur.execute("INSERT INTO marketplace_post_likes(post_id,user_id,created_at) VALUES(?,?,?)",(post_id,uid,_now())); liked=True
    conn.commit(); counts=_mkt_counts(cur,post_id,uid); conn.close()
    return jsonify({"liked":liked,"like_count":counts[0]})

@app.route("/api/marketplace/post/<int:post_id>/save", methods=["POST"])
@require_telegram_auth
def marketplace_save(post_id):
    uid=g.tg_user["id"]; conn=db(); cur=conn.cursor()
    cur.execute("SELECT 1 FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0",(post_id,))
    if not cur.fetchone(): conn.close(); return jsonify({"error":"post not found"}),404
    cur.execute("SELECT 1 FROM marketplace_post_saves WHERE post_id=? AND user_id=?",(post_id,uid))
    if cur.fetchone(): cur.execute("DELETE FROM marketplace_post_saves WHERE post_id=? AND user_id=?",(post_id,uid)); saved=False
    else: cur.execute("INSERT INTO marketplace_post_saves(post_id,user_id,created_at) VALUES(?,?,?)",(post_id,uid,_now())); saved=True
    conn.commit(); counts=_mkt_counts(cur,post_id,uid); conn.close()
    return jsonify({"saved":saved,"save_count":counts[1]})

@app.route("/api/marketplace/post/<int:post_id>/view", methods=["POST"])
@require_telegram_auth
def marketplace_view(post_id):
    uid=g.tg_user["id"]; conn=db(); cur=conn.cursor()
    cur.execute("SELECT 1 FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0",(post_id,))
    if not cur.fetchone(): conn.close(); return jsonify({"error":"post not found"}),404
    cur.execute("SELECT 1 FROM marketplace_post_views WHERE post_id=? AND user_id=? AND created_at > ?",(post_id,uid,(datetime.now()-timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S')))
    if not cur.fetchone(): cur.execute("INSERT INTO marketplace_post_views(post_id,user_id,created_at) VALUES(?,?,?)",(post_id,uid,_now()))
    conn.commit(); cur.execute("SELECT COUNT(*) c FROM marketplace_post_views WHERE post_id=?",(post_id,)); n=cur.fetchone()["c"]; conn.close()
    return jsonify({"view_count":n})

@app.route("/api/marketplace/post/<int:post_id>/comments")
@require_telegram_auth
def marketplace_comments_get(post_id):
    conn=db(); cur=conn.cursor(); cur.execute("""SELECT c.comment_id,c.comment,c.created_at,c.user_id,u.first_name,u.username
        FROM marketplace_comments c LEFT JOIN users u ON u.user_id=c.user_id WHERE c.post_id=? ORDER BY c.comment_id DESC LIMIT 100""",(post_id,)); rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify({"comments":rows})

@app.route("/api/marketplace/post/<int:post_id>/comments", methods=["POST"])
@require_telegram_auth
def marketplace_comments_add(post_id):
    uid=g.tg_user["id"]; body=request.get_json(silent=True) or {}; comment=(body.get("comment") or "").strip()
    if not comment or len(comment)>500: return jsonify({"error":"comment must be 1-500 characters"}),400
    conn=db(); cur=conn.cursor(); cur.execute("SELECT 1 FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0",(post_id,))
    if not cur.fetchone(): conn.close(); return jsonify({"error":"post not found"}),404
    cur.execute("INSERT INTO marketplace_comments(post_id,user_id,comment,created_at) VALUES(?,?,?,?)",(post_id,uid,comment,_now())); conn.commit(); cid=cur.lastrowid; conn.close(); return jsonify({"status":"success","comment_id":cid})

@app.route("/api/marketplace/creator/<int:creator_id>")
@require_telegram_auth
def marketplace_creator(creator_id):
    uid=g.tg_user["id"]; conn=db(); cur=conn.cursor(); cur.execute("SELECT user_id,first_name,username FROM users WHERE user_id=?",(creator_id,)); u=cur.fetchone()
    if not u: conn.close(); return jsonify({"error":"creator not found"}),404
    cur.execute("SELECT COUNT(*) c FROM marketplace_posts WHERE creator_id=? AND active=1",(creator_id,)); posts=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM marketplace_follows WHERE creator_id=?",(creator_id,)); followers=cur.fetchone()["c"]
    cur.execute("SELECT 1 FROM marketplace_follows WHERE creator_id=? AND follower_id=?",(creator_id,uid)); following=bool(cur.fetchone())
    cur.execute("SELECT COUNT(*) c,COALESCE(AVG(rating),0) a FROM marketplace_reviews WHERE creator_id=?",(creator_id,)); r=cur.fetchone()
    conn.close(); return jsonify({"creator":dict(u),"post_count":posts,"followers":followers,"following":following,"review_count":r["c"],"avg_rating":round(r["a"],1) if r["c"] else None})

@app.route("/api/marketplace/creator/<int:creator_id>/follow", methods=["POST"])
@require_telegram_auth
def marketplace_follow(creator_id):
    uid=g.tg_user["id"]
    if uid==creator_id: return jsonify({"error":"cannot follow yourself"}),400
    conn=db(); cur=conn.cursor(); cur.execute("SELECT 1 FROM users WHERE user_id=?",(creator_id,))
    if not cur.fetchone(): conn.close(); return jsonify({"error":"creator not found"}),404
    cur.execute("SELECT 1 FROM marketplace_follows WHERE creator_id=? AND follower_id=?",(creator_id,uid))
    if cur.fetchone(): cur.execute("DELETE FROM marketplace_follows WHERE creator_id=? AND follower_id=?",(creator_id,uid)); following=False
    else: cur.execute("INSERT INTO marketplace_follows(creator_id,follower_id,created_at) VALUES(?,?,?)",(creator_id,uid,_now())); following=True
    conn.commit(); cur.execute("SELECT COUNT(*) c FROM marketplace_follows WHERE creator_id=?",(creator_id,)); n=cur.fetchone()["c"]; conn.close(); return jsonify({"following":following,"followers":n})

@app.route("/api/marketplace/services")
@require_telegram_auth
def marketplace_services():
    if not _platform_flag_enabled("marketplace_enabled"):
        return jsonify({"services":[],"disabled":True})
    conn = db(); cur = conn.cursor()
    q=(request.args.get("q") or "").strip(); category=(request.args.get("category") or "").strip(); sort=(request.args.get("sort") or "new").strip()
    where=["p.active=1", "p.moderation_status='approved'", "p.price_status='approved'", "p.media_status='approved'", "COALESCE(u.marketplace_suspended,0)=0", "COALESCE(u.banned,0)=0"]; params=[]
    if q: where.append("(p.title LIKE ? OR p.description LIKE ? OR p.category LIKE ?)"); params += [f"%{q}%"]*3
    if category: where.append("p.category=?"); params.append(category)
    order = "p.post_id DESC" if sort=="new" else ("p.price ASC" if sort=="cheap" else "p.price DESC")
    cur.execute(f"""SELECT p.*, u.first_name AS creator_first_name, u.username AS creator_username
                   FROM marketplace_posts p LEFT JOIN users u ON u.user_id=p.creator_id
                   WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 100""", params)
    rows = [dict(r) for r in cur.fetchall()]

    # Reviews were being collected (marketplace_review POST) but never
    # surfaced anywhere -- a buyer had no way to see whether a creator
    # was any good before paying into escrow. Attach each creator's
    # aggregate rating (across ALL their posts, not just this one,
    # since reputation belongs to the creator) to every listing.
    creator_ids = list({r["creator_id"] for r in rows})
    ratings_by_creator = {}
    if creator_ids:
        placeholders = ",".join("?" * len(creator_ids))
        cur.execute(
            f"""SELECT creator_id, COUNT(*) c, AVG(rating) avg_rating
                FROM marketplace_reviews WHERE creator_id IN ({placeholders})
                GROUP BY creator_id""",
            creator_ids
        )
        for r in cur.fetchall():
            ratings_by_creator[r["creator_id"]] = {
                "review_count": r["c"],
                "avg_rating": round(r["avg_rating"], 1),
            }
    for row in rows:
        stats = ratings_by_creator.get(row["creator_id"])
        row["creator_review_count"] = stats["review_count"] if stats else 0
        row["creator_avg_rating"] = stats["avg_rating"] if stats else None
        # Frontend-compatible aliases: keep creator_* fields for API clarity.
        row["avg_rating"] = row["creator_avg_rating"]
        row["review_count"] = row["creator_review_count"]
        row["media_url"] = _marketplace_media_url(row["post_id"], row["sample_file_id"]) if row.get("sample_file_id") else None
        likes,saves,views,comments,liked,saved=_mkt_counts(cur,row["post_id"],g.tg_user["id"])
        row.update({"like_count":likes,"save_count":saves,"view_count":views,"comment_count":comments,"liked":liked,"saved":saved})
        try:
            row["media_items"] = json.loads(row.get("media_json") or "[]")
            row["media_urls"] = []
            for i,item in enumerate(row["media_items"]):
                if item.get("moderation_removed") or item.get("moderation_status")=="rejected":
                    continue
                exp=int(time.time())+MARKETPLACE_MEDIA_URL_TTL
                tok=_make_marketplace_media_token(row["post_id"], item["file_id"], exp)
                row["media_urls"].append(f"/api/marketplace/media/{row['post_id']}?expires={exp}&token={tok}&index={i}")
        except Exception:
            row["media_items"]=[]; row["media_urls"]=[]

    conn.close()
    return jsonify({"services": rows})


@app.route("/api/marketplace/media/<int:post_id>")
def marketplace_media(post_id):
    """Streams a preview from Telegram without persistent media storage on
    this server. Access is granted by a short-lived HMAC URL returned by
    /api/marketplace/services."""
    try:
        expires = int(request.args.get("expires", "0"))
        token = request.args.get("token", "")
    except (TypeError, ValueError):
        return jsonify({"error": "invalid media token"}), 401
    if expires < int(time.time()) or expires > int(time.time()) + MARKETPLACE_MEDIA_URL_TTL + 60:
        return jsonify({"error": "media link expired"}), 401

    media_index = request.args.get("index")
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT p.sample_file_id, p.sample_media_type, p.media_json FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0", (post_id,))
    row=cur.fetchone(); conn.close()
    if not row or not row["sample_file_id"]:
        return jsonify({"error":"media not found"}),404
    file_id=row["sample_file_id"]; media_type=row["sample_media_type"]
    if media_index is not None:
        try:
            items=json.loads(row["media_json"] or "[]"); item=items[int(media_index)]
            if item.get("moderation_removed") or item.get("moderation_status")=="rejected": return jsonify({"error":"media not available"}),404
            file_id=item["file_id"]; media_type=item.get("media_type") or media_type
        except Exception: return jsonify({"error":"media not found"}),404
    expected=_make_marketplace_media_token(post_id, file_id, expires)
    if not hmac.compare_digest(expected, token):
        return jsonify({"error":"invalid media token"}),401

    try:
        gf=requests.get(f"{TELEGRAM_API}/getFile", params={"file_id":file_id}, timeout=15).json()
        if not gf.get("ok"):
            return jsonify({"error":"Telegram file lookup failed"}),502
        path=(gf.get("result") or {}).get("file_path")
        if not path:
            return jsonify({"error":"Telegram file path unavailable"}),502
        media=requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}", timeout=60)
        if not media.ok:
            return jsonify({"error":"Telegram media fetch failed"}),502
        content_type=media.headers.get("Content-Type") or {
            "photo":"image/jpeg", "video":"video/mp4", "voice":"audio/ogg"
        }.get(media_type, "application/octet-stream")
        return Response(media.content, status=200, content_type=content_type,
                        headers={"Cache-Control":"private, max-age=300"})
    except Exception as exc:
        logger.warning("Marketplace media proxy failed post=%s: %s", post_id, exc)
        return jsonify({"error":"unable to load media"}),502


@app.route("/api/marketplace/services/<int:post_id>/reviews")
@require_telegram_auth
def marketplace_post_reviews_compat(post_id):
    # Backward/forward-compatible path used by the current Mini App frontend.
    # Keep the canonical query-string endpoint below as well.
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT creator_id FROM marketplace_posts WHERE post_id=?", (post_id,))
    post = cur.fetchone()
    if not post:
        conn.close()
        return jsonify({"error": "service not found"}), 404
    cur.execute(
        """SELECT rating, comment, created_at FROM marketplace_reviews
           WHERE creator_id=? ORDER BY created_at DESC LIMIT 50""",
        (post["creator_id"],)
    )
    reviews = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"reviews": reviews})


@app.route("/api/marketplace/reviews")
@require_telegram_auth
def marketplace_post_reviews():
    """Returns the review list for one post's creator (all their
    reviews, since a rating is a creator reputation signal, not a
    per-listing one) -- lets a buyer see actual comments, not just
    the average star number, before buying."""
    try:
        post_id = int(request.args.get("post_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid post_id"}), 400

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT creator_id FROM marketplace_posts WHERE post_id=?", (post_id,))
    post = cur.fetchone()
    if not post:
        conn.close()
        return jsonify({"error": "service not found"}), 404

    cur.execute(
        """SELECT rating, comment, created_at FROM marketplace_reviews
           WHERE creator_id=? ORDER BY created_at DESC LIMIT 50""",
        (post["creator_id"],)
    )
    reviews = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"reviews": reviews})


MARKETPLACE_SERVICE_TYPES = {"photo", "video", "voice", "video_call", "audio_call", "consult_photo", "consult_video"}
MARKETPLACE_MAX_PRICE = 100000.0
MARKETPLACE_MAX_ACTIVE_POSTS_PER_CREATOR = 20  # keeps one account from flooding the listing


@app.route("/api/marketplace/media/<int:post_id>/<int:media_index>")
def marketplace_media_item(post_id, media_index):
    conn=db(); cur=conn.cursor(); cur.execute("SELECT p.media_json FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0",(post_id,)); row=cur.fetchone(); conn.close()
    if not row: return jsonify({"error":"not found"}),404
    try: items=json.loads(row["media_json"] or "[]"); item=items[media_index]
    except Exception: return jsonify({"error":"media not found"}),404
    if item.get("moderation_removed") or item.get("moderation_status")=="rejected": return jsonify({"error":"media not available"}),404
    exp=int(time.time())+600; token=_make_marketplace_media_token(post_id,item["file_id"],exp)
    # Reuse the secure Telegram proxy logic by redirecting internally through the signed URL.
    return jsonify({"url":f"/api/marketplace/media/{post_id}?index={media_index}&expires={exp}&token={token}"})

@app.route("/api/marketplace/my-services")
@require_telegram_auth
def marketplace_my_services():
    """A creator's own listings -- previously services could only be
    added directly in the database, there was no in-app way for a
    creator to post or manage their own listing."""
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute(
        "SELECT * FROM marketplace_posts WHERE creator_id=? ORDER BY post_id DESC",
        (uid,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"services": rows})


@app.route("/api/marketplace/my-services", methods=["POST"])
@require_telegram_auth
@rate_limit(max_calls=10, window_seconds=300)
def marketplace_create_service():
    if not _platform_flag_enabled("marketplace_enabled"):
        return jsonify({"error":"marketplace is disabled by admin"}),403
    """Create a marketplace post. Optional sample media is uploaded once
    to Telegram and only Telegram's file_id/message_id are retained in DB.
    The Mini App/server never stores the media as a permanent file."""
    uid = g.tg_user["id"]
    _c=db(); _cc=_c.cursor(); _cc.execute("SELECT banned,COALESCE(marketplace_suspended,0) marketplace_suspended FROM users WHERE user_id=?",(uid,)); _u=_cc.fetchone(); _c.close()
    if _u and (_u["banned"] or _u["marketplace_suspended"]):
        return jsonify({"error":"marketplace creator access is suspended"}),403
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        title = (request.form.get("title") or "").strip()
        service_type = (request.form.get("service_type") or "").strip()
        description = (request.form.get("description") or "").strip()
        category = (request.form.get("category") or "").strip()
        duration_raw = request.form.get("duration_minutes")
        price_raw = request.form.get("price")
        samples = request.files.getlist("sample")
    else:
        body = request.get_json(silent=True) or {}
        title = (body.get("title") or "").strip()
        service_type = (body.get("service_type") or "").strip()
        description = (body.get("description") or "").strip()
        category = (body.get("category") or "").strip()
        duration_raw = body.get("duration_minutes")
        price_raw = body.get("price")
        samples = []
    try:
        price = parse_money(price_raw, "price")
    except (TypeError, ValueError):
        return jsonify({"error": "invalid price"}), 400
    if not title or len(title) > 120:
        return jsonify({"error": "title is required (max 120 characters)"}), 400
    if len(description) > 1000:
        return jsonify({"error": "description is too long (max 1000 characters)"}), 400
    if len(category) > 60:
        return jsonify({"error": "category is too long (max 60 characters)"}), 400
    try:
        duration_minutes = int(duration_raw) if duration_raw not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "duration_minutes must be a whole number"}), 400
    if duration_minutes is not None and not (1 <= duration_minutes <= 1440):
        return jsonify({"error": "duration_minutes must be between 1 and 1440"}), 400
    if service_type not in MARKETPLACE_SERVICE_TYPES:
        return jsonify({"error": f"service_type must be one of {sorted(MARKETPLACE_SERVICE_TYPES)}"}), 400
    if price <= 0 or price > MARKETPLACE_MAX_PRICE:
        return jsonify({"error": f"price must be between 0 and {MARKETPLACE_MAX_PRICE}"}), 400
    if service_type in ("video_call", "audio_call") and samples:
        return jsonify({"error": "live-call listings do not need a sample upload"}), 400
    if service_type in ("photo", "video", "voice", "consult_photo", "consult_video") and not samples:
        return jsonify({"error": "photo/video/voice posts require a media file; only live-call posts can be media-free"}), 400

    sample_file_id = None
    sample_media_type = None
    sample_message_id = None
    media_items = []
    if samples:
        if len(samples) > 10:
            return jsonify({"error":"maximum 10 media items per post"}),400
        for sample in samples:
            if not sample or not sample.filename: continue
            data = sample.read()
            if not data: return jsonify({"error":"one of the media files is empty"}),400
            filename = sample.filename; lower = filename.lower()
            if service_type in ("photo", "consult_photo"):
                mt="photo"; limit=10*1024*1024; method,field="sendPhoto","photo"
            elif service_type in ("video", "consult_video"):
                mt="video"; limit=50*1024*1024; method,field="sendVideo","video"
            elif service_type=="voice":
                mt="voice"; limit=50*1024*1024; method,field="sendVoice","voice"
            else:
                return jsonify({"error":"sample media is only supported for photo, video, or voice listings"}),400
            if len(data)>limit: return jsonify({"error":f"{mt} sample is too large"}),400
            try:
                resp=requests.post(f"{TELEGRAM_API}/{method}",data={"chat_id":uid,"caption":f"🛍️ Marketplace sample\n{title}"[:1024]},files={field:(filename,data)},timeout=60).json()
                if mt=="voice" and not resp.get("ok"):
                    resp=requests.post(f"{TELEGRAM_API}/sendAudio",data={"chat_id":uid,"caption":f"🛍️ Marketplace sample\n{title}"[:1024]},files={"audio":(filename,data)},timeout=60).json()
            except Exception as exc: return jsonify({"error":f"Telegram sample upload failed: {exc}"}),502
            if not resp.get("ok"): return jsonify({"error":"Telegram could not store one of the samples"}),502
            msg=resp.get("result") or {}; mid=msg.get("message_id")
            if mt=="photo": fid=(msg.get("photo") or [{}])[-1].get("file_id")
            elif mt=="video": fid=(msg.get("video") or {}).get("file_id")
            else: fid=(msg.get("audio") or {}).get("file_id")
            if not fid: return jsonify({"error":"Telegram returned no file_id"}),502
            media_items.append({"file_id":fid,"media_type":mt,"message_id":mid,"filename":filename})
        if media_items:
            sample_file_id=media_items[0]["file_id"]; sample_media_type=media_items[0]["media_type"]; sample_message_id=media_items[0]["message_id"]
    # Posts are published IMMEDIATELY so every player sees them in the Marketplace right away.
    # Staff can still hide/reject/delete any post afterwards (Admin -> Marketplace) and players can report it.
    # If the operator wants to review BEFORE publishing, set MARKETPLACE_REQUIRE_REVIEW=1 (default 0).
    mod_status = "pending" if _marketplace_requires_review() else "approved"
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM marketplace_posts WHERE creator_id=? AND active=1", (uid,))
    if cur.fetchone()["c"] >= MARKETPLACE_MAX_ACTIVE_POSTS_PER_CREATOR:
        conn.close()
        return jsonify({"error": f"you already have {MARKETPLACE_MAX_ACTIVE_POSTS_PER_CREATOR} active listings -- deactivate one first"}), 400
    cur.execute(
        """INSERT INTO marketplace_posts
           (creator_id,title,service_type,price,active,description,sample_file_id,sample_media_type,sample_message_id,created_at,category,duration_minutes,media_json,moderation_status,price_status,media_status)
           VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, title, service_type, price, description, sample_file_id, sample_media_type, sample_message_id, _now(), category, duration_minutes, json.dumps(media_items),
         mod_status, mod_status, mod_status)
    )
    post_id = cur.lastrowid
    conn.commit(); conn.close()
    for sid in get_staff_ids():   # tell staff about every new post (pending = needs approval, otherwise already live)
        try:
            if mod_status == "pending":
                tg_send_message(sid, f"🛍️ አዲስ Marketplace post #{post_id} ግምገማ ይጠብቃል\n{title} -- {price:g} ብር\nMini App → Admin → Marketplace ውስጥ ያጽድቁ።", parse_mode=None)
            else:
                tg_send_message(sid, f"🛍️ አዲስ Marketplace post #{post_id} ታትሟል\n{title} -- {price:g} ብር\nተገቢ ካልሆነ Mini App → Admin → Marketplace ውስጥ ይደብቁ።", parse_mode=None)
        except Exception: pass
    return jsonify({"status": "success", "post_id": post_id, "moderation_status": mod_status, "visible": mod_status == "approved",
                    "sample_stored_on_telegram": bool(sample_file_id)})


@app.route("/api/marketplace/sample/<int:post_id>", methods=["POST"])
@require_telegram_auth
@rate_limit(max_calls=20, window_seconds=300)
def marketplace_view_sample(post_id):
    """Forward a creator's Telegram-hosted sample to the viewer's Telegram
    chat using the stored file_id. No sample bytes are persisted by this app."""
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT p.* FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0", (post_id,))
    post = cur.fetchone(); conn.close()
    if not post:
        return jsonify({"error": "service not found"}), 404
    if not post["sample_file_id"]:
        return jsonify({"error": "this listing has no sample"}), 404
    media_type = post["sample_media_type"]
    method = {"photo":"sendPhoto", "video":"sendVideo", "voice":"sendVoice"}.get(media_type)
    field = {"photo":"photo", "video":"video", "voice":"voice"}.get(media_type)
    if not method:
        return jsonify({"error": "unsupported sample type"}), 400
    caption = f"🛍️ {post['title']}\nSample • Post #{post_id}"
    try:
        result = requests.post(
            f"{TELEGRAM_API}/{method}",
            data={"chat_id": uid, field: post["sample_file_id"], "caption": caption[:1024]},
            timeout=20,
        ).json()
    except Exception as exc:
        return jsonify({"error": f"Telegram preview failed: {exc}"}), 502
    if not result.get("ok") and media_type == "voice":
        result = requests.post(
            f"{TELEGRAM_API}/sendAudio",
            data={"chat_id": uid, "audio": post["sample_file_id"], "caption": caption[:1024]},
            timeout=20,
        ).json()
    if not result.get("ok"):
        return jsonify({"error": "Telegram could not send the sample"}), 502
    return jsonify({"status":"success","delivered_to":"telegram_chat"})


@app.route("/api/marketplace/my-services/<int:post_id>", methods=["POST"])
@require_telegram_auth
@rate_limit(max_calls=20, window_seconds=300)
def marketplace_update_service(post_id):
    """Edit or deactivate one of the caller's OWN listings only --
    ownership is checked server-side, never trusted from the client."""
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM marketplace_posts WHERE post_id=?", (post_id,))
    post = cur.fetchone()
    if not post:
        conn.close()
        return jsonify({"error": "service not found"}), 404
    if post["creator_id"] != uid:
        conn.close()
        return jsonify({"error": "you can only edit your own listings"}), 403

    title = post["title"]
    service_type = post["service_type"]
    price = post["price"]
    active = post["active"]
    description = post["description"] or ""
    category = post["category"] if "category" in post.keys() and post["category"] else "General"
    duration_minutes = post["duration_minutes"] if "duration_minutes" in post.keys() else None

    if "title" in body:
        title = (body.get("title") or "").strip()
        if not title or len(title) > 120:
            conn.close()
            return jsonify({"error": "title is required (max 120 characters)"}), 400
    if "description" in body:
        description = (body.get("description") or "").strip()
        if len(description) > 1000:
            conn.close()
            return jsonify({"error": "description is too long (max 1000 characters)"}), 400
    if "category" in body:
        category = (body.get("category") or "").strip()
        if len(category) > 60:
            conn.close()
            return jsonify({"error": "category is too long (max 60 characters)"}), 400
    if "duration_minutes" in body:
        try:
            duration_minutes = int(body.get("duration_minutes")) if body.get("duration_minutes") not in (None, "") else None
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "duration_minutes must be a whole number"}), 400
        if duration_minutes is not None and not (1 <= duration_minutes <= 1440):
            conn.close()
            return jsonify({"error": "duration_minutes must be between 1 and 1440"}), 400
    if "service_type" in body:
        service_type = (body.get("service_type") or "").strip()
        if service_type not in MARKETPLACE_SERVICE_TYPES:
            conn.close()
            return jsonify({"error": f"service_type must be one of {sorted(MARKETPLACE_SERVICE_TYPES)}"}), 400
    if "price" in body:
        try:
            price = parse_money(body.get("price"), "price")
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "invalid price"}), 400
        if price <= 0 or price > MARKETPLACE_MAX_PRICE:
            conn.close()
            return jsonify({"error": f"price must be between 0 and {MARKETPLACE_MAX_PRICE}"}), 400
    if "active" in body:
        active = 1 if body.get("active") else 0

    # Any material edit requires a fresh moderation pass. Deactivation is always allowed.
    material_edit = any(k in body for k in ("title","service_type","price","description","category","duration_minutes"))
    if material_edit and _marketplace_requires_review():
        active = 0 if active else 0
        cur.execute("UPDATE marketplace_posts SET title=?, service_type=?, price=?, active=?, description=?, category=?, duration_minutes=?, moderation_status='pending', price_status='pending', media_status=CASE WHEN media_json IS NULL OR media_json='[]' THEN 'approved' ELSE 'pending' END, moderation_note=NULL, moderated_by=NULL, moderated_at=NULL WHERE post_id=?",
                    (title, service_type, price, active, description, category, duration_minutes, post_id))
    elif material_edit:
        # review is not mandatory: the edited post stays live (staff may still hide it afterwards)
        cur.execute("UPDATE marketplace_posts SET title=?, service_type=?, price=?, active=?, description=?, category=?, duration_minutes=? WHERE post_id=?",
                    (title, service_type, price, active, description, category, duration_minutes, post_id))
    else:
        cur.execute("UPDATE marketplace_posts SET active=? WHERE post_id=?", (active, post_id))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})


@app.route("/api/marketplace/buy", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=5, window_seconds=60)
def marketplace_buy():
    if not _platform_flag_enabled("marketplace_enabled"):
        return jsonify({"error":"marketplace is disabled by admin"}),403
    buyer_id = g.tg_user["id"]  # authenticated -- request body is never trusted for identity
    body = request.get_json(silent=True) or {}
    try:
        post_id = int(body.get("post_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid post_id"}), 400

    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    _auto_refund_stale_escrow(cur)  # sweep before doing anything else, same as boom's round timeout

    cur.execute("SELECT balance FROM users WHERE user_id=?", (buyer_id,))
    buyer = cur.fetchone()
    if not buyer:
        conn.rollback(); conn.close()
        return jsonify({"error": "wallet not initialized -- open Profile tab first"}), 400

    cur.execute("SELECT p.* FROM marketplace_posts p JOIN users u ON u.user_id=p.creator_id WHERE p.post_id=? AND p.active=1 AND p.moderation_status='approved' AND p.price_status='approved' AND p.media_status='approved' AND COALESCE(u.marketplace_suspended,0)=0 AND COALESCE(u.banned,0)=0", (post_id,))
    post = cur.fetchone()
    if not post:
        conn.rollback(); conn.close()
        return jsonify({"error": "service not found or no longer available"}), 404

    if post["creator_id"] == buyer_id:
        conn.rollback(); conn.close()
        return jsonify({"error": "you cannot buy your own service"}), 400

    if buyer["balance"] < post["price"]:
        conn.rollback(); conn.close()
        return jsonify({"error": "insufficient balance"}), 400
    _b, _lk, _can = _bonus.withdrawable(cur, buyer_id)
    if _lk > 0 and post["price"] > _can + 0.001:
        conn.rollback(); conn.close()
        return jsonify({"error": f"🎁 Bonus ({_lk:.2f} ብር) ለጨዋታ ብቻ ነው -- ለ Marketplace መጠቀም የሚችሉት {_can:.2f} ብር ነው"}), 400

    new_balance = buyer["balance"] - post["price"]
    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, buyer_id))

    tx_id = f"mkt_{uuid.uuid4().hex[:10]}"
    now = _now()
    cur.execute(
        """INSERT INTO marketplace_transactions(tx_id,buyer_id,creator_id,post_id,amount,status,created_at)
           VALUES (?,?,?,?,?, 'held_in_escrow', ?)""",
        (tx_id, buyer_id, post["creator_id"], post_id, post["price"], now)
    )
    cur.execute(
        """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
           VALUES (?,?, 'marketplace_buy', ?)""",
        (buyer_id, -post["price"], now)
    )
    conn.commit()
    conn.close()

    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": (f"🛍️ New marketplace escrow purchase\nTx: {tx_id}\n"
                         f"Service: {post['title']}\nBuyer: {buyer_id} -> Creator: {post['creator_id']}\n"
                         f"Amount: {post['price']} ብር"),
            },
            timeout=5,
        )
    except Exception:
        pass

    return jsonify({
        "status": "success", "tx_id": tx_id,
        "message": "ክፍያዎ በ Escrow ተይዟል -- አቅራቢው አገልግሎቱን እስኪያደርስ ድረስ አይለቀቅም።",
    })


@app.route("/api/marketplace/admin/resolve", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
@rate_limit(max_calls=30, window_seconds=300)
def marketplace_resolve():
    """Releases or refunds an escrowed payment -- real money moves
    either way, so this now goes through @require_admin (staff check
    AND PIN token) instead of the staff-only check it had before,
    matching every other money-moving admin action in this file."""
    body = request.get_json(silent=True) or {}
    tx_id = body.get("tx_id")
    action = body.get("action")
    note = (body.get("note") or "").strip()

    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT * FROM marketplace_transactions WHERE tx_id=?", (tx_id,))
    tx = cur.fetchone()
    if not tx:
        conn.rollback(); conn.close()
        return jsonify({"error": "transaction not found"}), 404
    if tx["status"] != "held_in_escrow":
        conn.rollback(); conn.close()
        return jsonify({"error": "transaction already closed"}), 400

    now = _now()
    if action == "release":
        total = tx["amount"]
        commission_rate = get_marketplace_commission_rate()
        commission = round(total * commission_rate, 2)
        creator_amount = round(total - commission, 2)
        cur.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?", (creator_amount, tx["creator_id"])
        )
        cur.execute(
            "UPDATE marketplace_transactions SET status='completed', resolution_note=? WHERE tx_id=?",
            (note, tx_id)
        )
        cur.execute(
            """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
               VALUES (?,?, 'marketplace_release', ?)""",
            (tx["creator_id"], creator_amount, now)
        )
        _platform_credit(cur, "marketplace_commission", commission, tx_id,
                         f"Marketplace commission {commission_rate:.2%}", now)
        conn.commit(); conn.close()
        _log_admin_action(g.tg_user["id"], "marketplace_release", {"tx_id": tx_id, "note": note})
        return jsonify({"status": "success", "message": f"{creator_amount} ብር ለ creator ተለቋል, {commission} ብር commission"})

    elif action == "refund":
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (tx["amount"], tx["buyer_id"]))
        cur.execute(
            "UPDATE marketplace_transactions SET status='refunded', resolution_note=? WHERE tx_id=?",
            (note, tx_id)
        )
        cur.execute(
            """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
               VALUES (?,?, 'marketplace_refund', ?)""",
            (tx["buyer_id"], tx["amount"], now)
        )
        conn.commit(); conn.close()
        _log_admin_action(g.tg_user["id"], "marketplace_refund", {"tx_id": tx_id, "note": note})
        return jsonify({"status": "success", "message": "ሙሉ ገንዘቡ ለገዢው ተመልሷል"})

    else:
        conn.rollback(); conn.close()
        return jsonify({"error": "invalid action"}), 400



@app.route("/api/marketplace/my-purchases")
@require_telegram_auth
def marketplace_my_purchases():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    _auto_refund_stale_escrow(cur)
    conn.commit()
    cur.execute("""SELECT t.*, p.title, p.service_type
                   FROM marketplace_transactions t
                   LEFT JOIN marketplace_posts p ON p.post_id=t.post_id
                   WHERE t.buyer_id=? ORDER BY t.created_at DESC LIMIT 100""", (uid,))
    rows=[dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"purchases": rows})


@app.route("/api/marketplace/my-sales")
@require_telegram_auth
def marketplace_my_sales():
    uid = g.tg_user["id"]
    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    _auto_refund_stale_escrow(cur)
    conn.commit()
    cur.execute("""SELECT t.*, p.title, p.service_type
                   FROM marketplace_transactions t
                   LEFT JOIN marketplace_posts p ON p.post_id=t.post_id
                   WHERE t.creator_id=? ORDER BY t.created_at DESC LIMIT 100""", (uid,))
    rows=[dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"sales": rows})


@app.route("/api/marketplace/my-services/update", methods=["POST"])
@require_telegram_auth
@rate_limit(max_calls=20, window_seconds=300)
def marketplace_update_service_compat():
    body=request.get_json(silent=True) or {}
    try:
        post_id=int(body.get("post_id"))
    except (TypeError,ValueError):
        return jsonify({"error":"invalid post_id"}),400
    return marketplace_update_service(post_id)


def _tg_send_media_bytes(chat_id, media_type, file_bytes, filename, caption):
    """Send bytes directly from request memory to Telegram. No permanent
    media file is written by this application and only Telegram's returned
    file_id is retained in SQLite."""
    method = {"photo":"sendPhoto", "video":"sendVideo", "voice":"sendVoice"}.get(media_type)
    field = {"photo":"photo", "video":"video", "voice":"voice"}.get(media_type)
    if not method:
        return {"ok":False,"error":"unsupported media type"}
    try:
        r=requests.post(
            f"{TELEGRAM_API}/{method}",
            data={"chat_id":chat_id,"caption":caption[:1024]},
            files={field:(filename,file_bytes)},
            timeout=60,
        )
        result=r.json()
        if media_type == "voice" and not result.get("ok"):
            r=requests.post(
                f"{TELEGRAM_API}/sendAudio",
                data={"chat_id":chat_id,"caption":caption[:1024]},
                files={"audio":(filename,file_bytes)},
                timeout=60,
            )
            result=r.json()
        return result
    except Exception as e:
        return {"ok":False,"error":str(e)}


@app.route("/api/marketplace/request-contact", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
def marketplace_request_contact():
    uid=g.tg_user["id"]
    body=request.get_json(silent=True) or {}
    tx_id=body.get("tx_id")
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT * FROM marketplace_transactions WHERE tx_id=? AND status='held_in_escrow'",(tx_id,))
    tx=cur.fetchone()
    if not tx:
        conn.close(); return jsonify({"error":"transaction not found or already closed"}),404
    if uid not in (tx["buyer_id"],tx["creator_id"]):
        conn.close(); return jsonify({"error":"not a participant in this transaction"}),403
    other=tx["creator_id"] if uid==tx["buyer_id"] else tx["buyer_id"]
    cur.execute("SELECT first_name,username FROM users WHERE user_id=?",(uid,)); me=cur.fetchone()
    cur.execute("SELECT first_name,username FROM users WHERE user_id=?",(other,)); them=cur.fetchone()
    conn.close()
    if not them:
        return jsonify({"error":"other participant not found"}),404
    me_name=(me["first_name"] if me else "User") or "User"
    me_username=(me["username"] if me else "") or ""
    them_name=them["first_name"] or "User"
    them_username=them["username"] or ""
    my_link=f"https://t.me/{me_username}" if me_username else f"tg://user?id={uid}"
    other_link=f"https://t.me/{them_username}" if them_username else f"tg://user?id={other}"
    safe_me = html.escape(me_name)
    safe_them = html.escape(them_name)
    tg_send_message(other, f"📞 Marketplace ግንኙነት ጥያቄ\nTx: {tx_id}\n<a href=\"{my_link}\">{safe_me}</a>", parse_mode="HTML")
    tg_send_message(uid, f"📞 የግንኙነት ጥያቄ ተልኳል\n<a href=\"{other_link}\">{safe_them}</a>", parse_mode="HTML")
    return jsonify({"status":"success"})


@app.route("/api/marketplace/deliver", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=5, window_seconds=300)
def marketplace_deliver():
    uid=g.tg_user["id"]
    tx_id=(request.form.get("tx_id") or "").strip()
    media_type=(request.form.get("media_type") or "").strip()
    if media_type not in ("photo","video","voice"):
        return jsonify({"error":"media_type must be photo, video, or voice"}),400
    upload=request.files.get("file")
    if not tx_id or not upload or not upload.filename:
        return jsonify({"error":"tx_id and file are required"}),400
    data=upload.read()
    if not data:
        return jsonify({"error":"empty file"}),400
    if len(data)>55*1024*1024:
        return jsonify({"error":"file too large (55MB max)"}),400
    conn=db(); cur=conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT * FROM marketplace_transactions WHERE tx_id=?",(tx_id,))
    tx=cur.fetchone()
    if not tx:
        conn.rollback(); conn.close(); return jsonify({"error":"transaction not found"}),404
    if tx["creator_id"]!=uid:
        conn.rollback(); conn.close(); return jsonify({"error":"only the creator can deliver"}),403
    if tx["status"]!="held_in_escrow" or tx["delivered_at"]:
        conn.rollback(); conn.close(); return jsonify({"error":"transaction is not awaiting delivery"}),400
    claim=secrets.token_hex(16)
    cur.execute("UPDATE marketplace_transactions SET delivery_claim_token=?,delivery_claimed_at=? WHERE tx_id=? AND status='held_in_escrow' AND delivered_at IS NULL",(claim,_now(),tx_id))
    if cur.rowcount!=1:
        conn.rollback(); conn.close(); return jsonify({"error":"delivery already in progress"}),409
    conn.commit(); conn.close()

    caption=f"🛍️ የተገዛ አገልግሎት\nTx: {tx_id}"
    result=_tg_send_media_bytes(tx["buyer_id"],media_type,data,upload.filename,caption)
    if not result.get("ok"):
        conn=db(); cur=conn.cursor()
        cur.execute("UPDATE marketplace_transactions SET delivery_claim_token=NULL,delivery_claimed_at=NULL WHERE tx_id=? AND delivered_at IS NULL",(tx_id,))
        conn.commit(); conn.close()
        return jsonify({"error":"Telegram delivery failed; nothing was charged/released. Please try again."}),502

    try:
        msg=result.get("result",{})
        if media_type=="photo": file_id=(msg.get("photo") or [{}])[-1].get("file_id")
        else: file_id=msg.get("video",{}).get("file_id") or msg.get("audio",{}).get("file_id")
        now=_now()
        conn=db(); cur=conn.cursor()
        cur.execute("UPDATE marketplace_transactions SET delivery_file_id=?,delivery_type=?,delivered_at=?,delivery_caption=? WHERE tx_id=? AND delivered_at IS NULL",(file_id,media_type,now,caption,tx_id))
        if cur.rowcount!=1:
            conn.rollback(); conn.close(); return jsonify({"error":"delivery was sent but could not be recorded; contact support with tx_id"}),500
        conn.commit(); conn.close()
    except Exception:
        return jsonify({"error":"delivery was sent but could not be recorded; contact support with tx_id"}),500
    return jsonify({"status":"success","delivery_type":media_type,"delivered_at":now})


@app.route("/api/marketplace/confirm-receipt", methods=["POST"])
@require_telegram_auth
@require_fresh_auth
@rate_limit(max_calls=5, window_seconds=60)
def marketplace_confirm_receipt():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    tx_id = str(body.get("tx_id") or "").strip()[:80]
    if not tx_id:
        return jsonify({"error": "tx_id is required"}), 400
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        tx = cur.execute("SELECT * FROM marketplace_transactions WHERE tx_id=?", (tx_id,)).fetchone()
        if not tx:
            conn.rollback(); conn.close(); return jsonify({"error": "transaction not found"}), 404
        if tx["buyer_id"] != uid:
            conn.rollback(); conn.close(); return jsonify({"error": "only the buyer can confirm receipt"}), 403
        if tx["status"] != "held_in_escrow" or not tx["delivered_at"]:
            conn.rollback(); conn.close(); return jsonify({"error": "service has not been delivered or transaction is already closed"}), 409
        rate = get_marketplace_commission_rate()
        commission = round(float(tx["amount"]) * rate, 2)
        creator_amount = round(float(tx["amount"]) - commission, 2)
        cur.execute("UPDATE marketplace_transactions SET status='completed',resolution_note=? WHERE tx_id=? AND status='held_in_escrow' AND delivered_at IS NOT NULL", ("buyer confirmed receipt", tx_id))
        if cur.rowcount != 1:
            conn.rollback(); conn.close(); return jsonify({"error": "transaction already processed"}), 409
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (creator_amount, tx["creator_id"]))
        if cur.rowcount != 1:
            conn.rollback(); conn.close(); return jsonify({"error": "creator wallet not found"}), 500
        now = _now()
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?, 'marketplace_release', ?)", (tx["creator_id"], creator_amount, now))
        _platform_credit(cur, "marketplace_commission", commission, tx_id, f"Marketplace commission {rate:.2%}", now)
        conn.commit(); conn.close()
        return jsonify({"status": "success", "message": "receipt confirmed; escrow released", "creator_payout": creator_amount, "commission": commission})
    except Exception:
        conn.rollback(); conn.close(); logger.exception("marketplace receipt confirmation failed")
        return jsonify({"error": "could not confirm receipt; please retry"}), 500


@app.route("/api/marketplace/review", methods=["POST"])
@require_telegram_auth
def marketplace_review():
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    tx_id = body.get("tx_id")
    try:
        rating = int(body.get("rating"))
        if not (1 <= rating <= 5):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "rating must be 1-5"}), 400
    comment = (body.get("comment") or "").strip()[:500]

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM marketplace_transactions WHERE tx_id=? AND status='completed'", (tx_id,))
    tx = cur.fetchone()
    if not tx:
        conn.close()
        return jsonify({"error": "transaction not found or not completed"}), 400
    if tx["buyer_id"] != uid:
        conn.close()
        return jsonify({"error": "only the buyer of this transaction can review it"}), 403

    try:
        cur.execute(
            """INSERT INTO marketplace_reviews(tx_id,buyer_id,creator_id,rating,comment,created_at)
               VALUES (?,?,?,?,?,?)""",
            (tx_id, tx["buyer_id"], tx["creator_id"], rating, comment, _now())
        )
        conn.commit(); conn.close()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        return jsonify({"error": "a review has already been submitted for this purchase"}), 409
    return jsonify({"status": "success", "message": "አስተያየትዎ ተልኳል"})


@app.route("/api/marketplace/report", methods=["POST"])
@require_telegram_auth
@rate_limit(max_calls=10, window_seconds=300)
def marketplace_report():
    """Lets any user flag a service/creator for admin review -- e.g.
    policy violation (sexual content is against Terms), a no-show, or
    a misleading listing. Stored AND pushed to the admin's Telegram
    DM immediately."""
    uid = g.tg_user["id"]
    body = request.get_json(silent=True) or {}
    try:
        post_id = int(body.get("post_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid post_id"}), 400
    reason = (body.get("reason") or "").strip()[:500]
    if not reason:
        return jsonify({"error": "please describe the issue"}), 400

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM marketplace_posts WHERE post_id=?", (post_id,))
    post = cur.fetchone()
    if not post:
        conn.close()
        return jsonify({"error": "service not found"}), 404

    cur.execute(
        """INSERT INTO marketplace_reports(reporter_id,post_id,creator_id,reason,created_at)
           VALUES (?,?,?,?,?)""",
        (uid, post_id, post["creator_id"], reason, _now())
    )
    conn.commit(); conn.close()

    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": (f"🚩 New marketplace report\nService: {post['title']} (#{post_id})\n"
                         f"Creator: {post['creator_id']}\nReported by: {uid}\nReason: {reason}"),
            },
            timeout=5,
        )
    except Exception:
        pass

    return jsonify({"status": "success", "message": "ሪፖርትዎ ለአስተዳዳሪ ተልኳል -- እናመሰግናለን።"})


# ============================================================
# ADMIN PANEL
#
# Everything below is gated by require_admin (ADMIN_ID or any user
# with manager=1 -- the same get_staff_ids() list kdm_bot.py already
# uses for its own notifications, so "who counts as staff" is defined
# in exactly one place).
#
# IMPORTANT ABOUT kdm_bot.py: this file does not have access to
# kdm_bot.py's source, so nothing here can change what that file's own
# admin commands do. Where the two could conflict (see the house-edge
# lock below), the conflict and its resolution are called out
# explicitly in comments rather than silently overriding behavior we
# can't see.
# ============================================================

ADMIN_PIN_TOKEN_TTL = 1800  # 30 minutes


def _make_admin_pin_token(uid):
    expiry = int(time.time()) + ADMIN_PIN_TOKEN_TTL
    payload = f"{uid}:{expiry}"
    sig = hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_admin_pin_token(token, uid):
    try:
        token_uid, expiry, sig = token.split(":")
        if int(token_uid) != uid or time.time() > int(expiry):
            return False
        expected = hmac.new(BOT_TOKEN.encode(), f"{token_uid}:{expiry}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except (ValueError, AttributeError):
        return False


def require_staff_only(f):
    """Just the staff check, no PIN -- used ONLY by the PIN
    endpoints themselves (verify-pin, pin-status), since requiring a
    PIN token to obtain a PIN token would be circular."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if g.tg_user["id"] not in get_staff_ids():
            return jsonify({"error": "admin only"}), 403
        return f(*args, **kwargs)
    return wrapper



# ------------------------------------------------------------
# V7 SUPPORT INBOX + ADMIN ANNOUNCEMENTS
# ------------------------------------------------------------

def _send_admin_text(text_body):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": ADMIN_ID, "text": text_body[:4000]}, timeout=8)
    except Exception:
        pass

@app.route("/api/support/tickets", methods=["GET", "POST"])
@require_telegram_auth
def support_tickets():
    uid=g.tg_user["id"]
    conn=db(); cur=conn.cursor()
    if request.method=="POST":
        if request.files:
            msg=str(request.form.get("message") or "").strip()
            subject=str(request.form.get("subject") or "Support")[:120]
            photo=request.files.get("photo")
            if photo and photo.mimetype not in ("image/jpeg","image/png","image/webp"):
                conn.close(); return jsonify({"error":"only JPEG/PNG/WebP photos are allowed"}),400
            if photo and photo.content_length and photo.content_length > 8*1024*1024:
                conn.close(); return jsonify({"error":"photo must be <= 8MB"}),400
        elif request.mimetype == "multipart/form-data":
            # FormData with text only still arrives as multipart; do not
            # fall back to JSON and accidentally discard the message.
            msg=str(request.form.get("message") or "").strip()
            subject=str(request.form.get("subject") or "Support")[:120]
            photo=request.files.get("photo")
        else:
            body=request.get_json(silent=True) or {}; msg=str(body.get("message") or "").strip(); subject=str(body.get("subject") or "Support")[:120]; photo=None
        if not msg and not photo:
            conn.close(); return jsonify({"error":"message or photo is required"}),400
        if len(msg)>4000:
            conn.close(); return jsonify({"error":"message max 4000 chars"}),400
        now=_now()
        cur.execute("INSERT INTO support_tickets(user_id,subject,status,created_at,updated_at) VALUES(?,?,?,?,?)",(uid,subject,"open",now,now))
        tid=cur.lastrowid
        file_id=None
        if photo:
            try:
                rr=requests.post(f"{TELEGRAM_API}/sendPhoto",data={"chat_id":ADMIN_ID,"caption":f"📩 Support ticket #{tid}\nUser: {uid}\n{msg}"[:1024]},files={"photo":(photo.filename or "support.jpg",photo.stream,photo.mimetype)},timeout=15)
                if rr.ok and rr.json().get("ok"):
                    file_id=rr.json()["result"]["photo"][-1]["file_id"]
                else:
                    conn.rollback(); conn.close(); return jsonify({"error":"Telegram could not receive the photo"}),502
            except Exception:
                conn.rollback(); conn.close(); return jsonify({"error":"photo delivery failed"}),502
        cur.execute("INSERT INTO support_messages(ticket_id,sender_user_id,sender_role,message_text,telegram_file_id,media_type,created_at) VALUES(?,?,?,?,?,?,?)",(tid,uid,"user",msg,file_id,"photo" if photo else None,now))
        conn.commit(); conn.close()
        if not photo: _send_admin_text(f"📩 New support ticket #{tid}\nUser: {uid}\n\n{msg}")
        return jsonify({"ok":True,"ticket_id":tid})
    cur.execute("SELECT ticket_id,subject,status,created_at,updated_at FROM support_tickets WHERE user_id=? ORDER BY updated_at DESC LIMIT 50",(uid,))
    rows=[dict(r) for r in cur.fetchall()]
    conn.close(); return jsonify({"items":rows})

@app.route("/api/support/tickets/<int:ticket_id>")
@require_telegram_auth
def support_ticket_detail(ticket_id):
    uid=g.tg_user["id"]; conn=db(); cur=conn.cursor()
    cur.execute("SELECT * FROM support_tickets WHERE ticket_id=? AND user_id=?",(ticket_id,uid)); t=cur.fetchone()
    if not t: conn.close(); return jsonify({"error":"ticket not found"}),404
    cur.execute("SELECT sender_role,message_text,media_type,created_at FROM support_messages WHERE ticket_id=? ORDER BY id",(ticket_id,))
    msgs=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify({"ticket":dict(t),"messages":msgs})

@app.route("/api/support/tickets/<int:ticket_id>/reply", methods=["POST"])
@require_telegram_auth
def support_ticket_reply(ticket_id):
    uid=g.tg_user["id"]; body=request.get_json(silent=True) or {}; msg=str(body.get("message") or "").strip()
    if not msg or len(msg)>4000: return jsonify({"error":"message is required (max 4000 chars)"}),400
    conn=db(); cur=conn.cursor(); cur.execute("SELECT user_id,status FROM support_tickets WHERE ticket_id=?",(ticket_id,)); t=cur.fetchone()
    if not t or t["user_id"]!=uid: conn.close(); return jsonify({"error":"ticket not found"}),404
    now=_now(); cur.execute("INSERT INTO support_messages(ticket_id,sender_user_id,sender_role,message_text,created_at) VALUES(?,?,?,?,?)",(ticket_id,uid,"user",msg,now)); cur.execute("UPDATE support_tickets SET status='open',updated_at=? WHERE ticket_id=?",(now,ticket_id)); conn.commit(); conn.close()
    _send_admin_text(f"📩 Support reply #{ticket_id}\nUser: {uid}\n\n{msg}"); return jsonify({"ok":True})

@app.route("/api/admin/support/tickets")
@require_telegram_auth
@require_admin
def admin_support_tickets():
    conn=db(); cur=conn.cursor()
    cur.execute("""SELECT t.*,
        (SELECT message_text FROM support_messages m WHERE m.ticket_id=t.ticket_id ORDER BY m.id DESC LIMIT 1) AS last_message,
        (SELECT sender_role FROM support_messages m WHERE m.ticket_id=t.ticket_id ORDER BY m.id DESC LIMIT 1) AS last_sender
        FROM support_tickets t ORDER BY CASE t.status WHEN 'open' THEN 0 WHEN 'answered' THEN 1 ELSE 2 END, t.updated_at DESC LIMIT 100""")
    rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify({"items":rows})

@app.route("/api/admin/support/tickets/<int:ticket_id>")
@require_telegram_auth
@require_admin
def admin_support_ticket_detail(ticket_id):
    conn=db(); cur=conn.cursor(); cur.execute("SELECT * FROM support_tickets WHERE ticket_id=?",(ticket_id,)); t=cur.fetchone()
    if not t: conn.close(); return jsonify({"error":"ticket not found"}),404
    cur.execute("SELECT sender_role,message_text,media_type,created_at FROM support_messages WHERE ticket_id=? ORDER BY id",(ticket_id,))
    msgs=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify({"ticket":dict(t),"messages":msgs})

@app.route("/api/admin/support/tickets/<int:ticket_id>/reply", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_support_reply(ticket_id):
    body=request.get_json(silent=True) or {}; msg=str(body.get("message") or "").strip()
    if not msg or len(msg)>4000: return jsonify({"error":"message is required (max 4000 chars)"}),400
    conn=db(); cur=conn.cursor(); cur.execute("SELECT user_id,status FROM support_tickets WHERE ticket_id=?",(ticket_id,)); t=cur.fetchone()
    if not t: conn.close(); return jsonify({"error":"ticket not found"}),404
    now=_now(); cur.execute("INSERT INTO support_messages(ticket_id,sender_user_id,sender_role,message_text,created_at) VALUES(?,?,?,?,?)",(ticket_id,g.tg_user["id"],"admin",msg,now)); cur.execute("UPDATE support_tickets SET status='answered',updated_at=? WHERE ticket_id=?",(now,ticket_id)); conn.commit(); conn.close()
    try: requests.post(f"{TELEGRAM_API}/sendMessage",json={"chat_id":t["user_id"],"text":f"💬 Support #{ticket_id}\n\n{msg}"},timeout=8)
    except Exception: pass
    return jsonify({"ok":True})

@app.route("/api/admin/support/tickets/<int:ticket_id>/close", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_support_close(ticket_id):
    conn=db(); cur=conn.cursor(); cur.execute("UPDATE support_tickets SET status='closed',updated_at=? WHERE ticket_id=?",(_now(),ticket_id)); conn.commit(); changed=cur.rowcount; conn.close(); return jsonify({"ok":bool(changed)})

@app.route("/api/admin/announcements/broadcast", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_broadcast():
    """Admin/owner broadcast: text plus optional photo, video or voice note.
    Media is uploaded once to Telegram, then its file_id is reused for the
    remaining recipients and optional announcement channel.
    """
    upload = None
    media_type = None
    if request.mimetype == "multipart/form-data":
        msg = str(request.form.get("message") or "").strip()
        game_key = str(request.form.get("game") or "").strip().lower()
        upload = request.files.get("media")
        if upload and upload.filename:
            mime = (upload.mimetype or "").lower()
            if mime == "image/gif":
                media_type = "animation"
            elif mime.startswith("image/") and mime in ("image/jpeg", "image/png", "image/webp"):
                media_type = "photo"
            elif mime.startswith("video/") and mime in ("video/mp4", "video/quicktime", "video/webm"):
                media_type = "video"
            elif mime in ("audio/ogg", "audio/opus", "audio/webm", "audio/mpeg", "audio/mp4", "audio/aac", "audio/x-m4a"):
                media_type = "voice" if mime in ("audio/ogg", "audio/opus", "audio/webm") else "audio"
            else:
                return jsonify({"error":"Use JPG/PNG/WebP photo, GIF animation, MP4/MOV/WebM video, or a supported audio file."}),400
            raw = upload.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                return jsonify({"error":"Media must be 8 MB or smaller."}),400
            if not raw:
                return jsonify({"error":"Selected media file is empty."}),400
            upload.stream.seek(0)
        else:
            raw = None
    else:
        body=request.get_json(silent=True) or {}
        msg=str(body.get("message") or "").strip()
        game_key=str(body.get("game") or "").strip().lower()
        photo_id=str(body.get("photo_file_id") or "").strip() or None
        raw=None
        media_type="photo" if photo_id else None
    if not msg or len(msg)>4000:
        return jsonify({"error":"Announcement text is required (max 4000 characters)."}),400
    if media_type and media_type != "photo" and len(msg)>1024:
        return jsonify({"error":"For GIF/video/audio captions, keep the message under 1024 characters."}),400
    if request.mimetype == "multipart/form-data":
        photo_id=None
    else:
        photo_id=locals().get("photo_id")

    conn=db(); cur=conn.cursor(); cur.execute("SELECT user_id FROM users WHERE banned=0")
    users=[int(r["user_id"]) for r in cur.fetchall()]
    channel_id=os.environ.get("ANNOUNCEMENT_CHANNEL_ID", "").strip()
    now=_now()
    cur.execute("INSERT INTO announcement_broadcasts(admin_user_id,message_text,photo_file_id,created_at,total_targets,status) VALUES(?,?,?,?,?,?)",
                (g.tg_user["id"],msg,photo_id,now,len(users)+(1 if channel_id else 0),"running"))
    bid=cur.lastrowid; conn.commit(); conn.close()
    try: royal_add_announcement(msg, "📢 ማስታወቂያ", ("game:"+game_key if game_key and game_key not in ("lobby","sports","marketplace","wheel") else (game_key if game_key!="lobby" else "")), 0, g.tg_user["id"])
    except Exception: logger.exception("could not store broadcast as in-app announcement")

    method_by_type={"photo":"sendPhoto","animation":"sendAnimation","video":"sendVideo","voice":"sendVoice","audio":"sendAudio"}
    field_by_type={"photo":"photo","animation":"animation","video":"video","voice":"voice","audio":"audio"}
    # The post's button opens the Mini App on the game the admin picked ("" / "lobby" = home).
    # Private chats get a real Mini App button (player is logged in, no "Open Link" prompt); a channel can only hold a
    # t.me link, so it gets the direct startapp link.
    if not re.fullmatch(r"[a-z0-9_]{1,40}", game_key or "x") or game_key in ("none",):
        game_key = ""
    if game_key == "lobby":
        game_key = ""
    _sep = "&" if "?" in MINI_APP_URL else "?"
    _game_url = MINI_APP_URL + (f"{_sep}game={game_key}" if game_key else "")
    play_markup={"inline_keyboard":[[{"text":"🎮 Play Now","web_app":{"url":_game_url}}]]} if MINI_APP_URL.startswith("https://") else None
    _ch_link=_bot_open_link(f"g_{game_key or 'lobby'}")
    channel_markup={"inline_keyboard":[[{"text":"🎮 Play Now","url":_ch_link or _game_url}]]} if (_ch_link or MINI_APP_URL.startswith("https://")) else None
    _private_markup=play_markup
    media_file_id=photo_id
    sent=failed=0
    channel_sent=False

    def send_target(chat_id, allow_upload=False):
        nonlocal media_file_id
        play_markup = channel_markup if (channel_id and str(chat_id) == channel_id) else _private_markup
        if not media_type:
            payload={"chat_id":chat_id,"text":msg}
            if play_markup: payload["reply_markup"]=play_markup
            rr=requests.post(f"{TELEGRAM_API}/sendMessage",json=payload,timeout=12)
        else:
            method=method_by_type[media_type]; field=field_by_type[media_type]
            caption_key="caption"
            if media_file_id:
                payload={"chat_id":chat_id,field:media_file_id,caption_key:msg}
                if play_markup: payload["reply_markup"]=play_markup
                rr=requests.post(f"{TELEGRAM_API}/{method}",json=payload,timeout=12)
            elif allow_upload and raw:
                mime=upload.mimetype or "application/octet-stream"
                payload={"chat_id":chat_id,"caption":msg}
                if play_markup: payload["reply_markup"]=json.dumps(play_markup,ensure_ascii=False)
                rr=requests.post(f"{TELEGRAM_API}/{method}",data=payload,files={field:(upload.filename or "announcement-media",io.BytesIO(raw),mime)},timeout=20)
                if rr.ok:
                    try:
                        result=rr.json().get("result",{})
                        obj=result.get("photo",[])[-1] if media_type=="photo" and result.get("photo") else result.get(media_type,{})
                        if obj.get("file_id"): media_file_id=obj["file_id"]
                    except Exception:
                        pass
            else:
                return False
        try: return bool(rr.ok and rr.json().get("ok"))
        except Exception: return False

    # Upload media once to the channel if configured, otherwise to the first user.
    # The returned Telegram file_id is then reused for every subsequent send.
    if channel_id:
        try:
            ok=send_target(channel_id,allow_upload=True)
            channel_sent=bool(ok)
            if ok: sent+=1
            else: failed+=1
        except Exception: failed+=1
    for uid in users:
        try:
            ok=send_target(uid,allow_upload=(not media_file_id))
            if ok: sent+=1
            else: failed+=1
        except Exception: failed+=1

    conn=db(); cur=conn.cursor(); cur.execute("UPDATE announcement_broadcasts SET sent_count=?,failed_count=?,status='done' WHERE id=?",(sent,failed,bid)); conn.commit(); conn.close()
    _log_admin_action(g.tg_user["id"],"announcement_broadcast",{"broadcast_id":bid,"targets":len(users)+(1 if channel_id else 0),"sent":sent,"failed":failed,"media_type":media_type or "text"})
    return jsonify({"ok":True,"broadcast_id":bid,"total_targets":len(users)+(1 if channel_id else 0),"sent":sent,"failed":failed,"channel_posted":channel_sent,"media_type":media_type or "text","play_now_button":bool(play_markup)})

@app.route("/api/admin/announcements/history")
@require_telegram_auth
@require_admin
def admin_broadcast_history():
    conn=db(); cur=conn.cursor(); cur.execute("SELECT * FROM announcement_broadcasts ORDER BY id DESC LIMIT 50"); rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify({"items":rows})

@app.route("/api/admin/pin-status")
@require_telegram_auth
@require_staff_only
def admin_pin_status():
    return jsonify({"pin_required": bool(ADMIN_PANEL_PIN)})


ADMIN_PIN_MAX_ATTEMPTS = 5        # failed tries allowed per lockout window
ADMIN_PIN_LOCKOUT_SECONDS = 900   # 15 minutes -- persisted in DB, survives restarts/workers


def _init_admin_pin_lockout():
    conn = db(); cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_pin_attempts (
        user_id INTEGER PRIMARY KEY,
        fail_count INTEGER DEFAULT 0,
        locked_until REAL DEFAULT 0,
        last_attempt_at REAL DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()


_init_admin_pin_lockout()


def _admin_pin_lock_status(uid):
    """Returns seconds remaining locked (0 if not locked)."""
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT locked_until FROM admin_pin_attempts WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0
    remaining = row["locked_until"] - time.time()
    return max(0, remaining)


def _admin_pin_record_failure(uid):
    """Persistent failure counter -- DB-backed (not the in-memory
    rate_limit deque) so it survives process restarts and is shared
    across gunicorn workers, since a stolen staff session brute-forcing
    a 4-digit PIN is exactly the scenario that matters here."""
    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT fail_count FROM admin_pin_attempts WHERE user_id=?", (uid,))
    row = cur.fetchone()
    now = time.time()
    if row:
        new_count = row["fail_count"] + 1
        locked_until = now + ADMIN_PIN_LOCKOUT_SECONDS if new_count >= ADMIN_PIN_MAX_ATTEMPTS else 0
        cur.execute(
            "UPDATE admin_pin_attempts SET fail_count=?, locked_until=?, last_attempt_at=? WHERE user_id=?",
            (new_count, locked_until, now, uid)
        )
    else:
        new_count = 1
        locked_until = 0
        cur.execute(
            "INSERT INTO admin_pin_attempts(user_id, fail_count, locked_until, last_attempt_at) VALUES (?,?,?,?)",
            (uid, new_count, locked_until, now)
        )
    conn.commit(); conn.close()
    return new_count, locked_until


def _admin_pin_reset(uid):
    conn = db(); cur = conn.cursor()
    cur.execute("DELETE FROM admin_pin_attempts WHERE user_id=?", (uid,))
    conn.commit(); conn.close()


@app.route("/api/admin/verify-pin", methods=["POST"])
@require_telegram_auth
@require_staff_only
@rate_limit(max_calls=8, window_seconds=300)
def admin_verify_pin():
    if not ADMIN_PANEL_PIN:
        return jsonify({"error": "no PIN configured on the server -- admin panel is unlocked without one"}), 400

    uid = g.tg_user["id"]
    locked_seconds = _admin_pin_lock_status(uid)
    if locked_seconds > 0:
        return jsonify({
            "error": f"too many wrong PIN attempts -- locked for {int(locked_seconds)} more seconds",
            "locked_seconds": int(locked_seconds),
        }), 429

    body = request.get_json(silent=True) or {}
    pin = str(body.get("pin", ""))
    if not hmac.compare_digest(pin, ADMIN_PANEL_PIN):
        time.sleep(1)  # slows down brute-force PIN guessing even within the rate limit
        fail_count, locked_until = _admin_pin_record_failure(uid)
        if locked_until:
            _notify_owner_of_sensitive_action(uid, "admin_pin_lockout", {
                "staff_id": uid, "fail_count": fail_count,
                "note": "account locked out of the admin PIN after repeated wrong attempts",
            })
            return jsonify({
                "error": f"too many wrong PIN attempts -- locked for {ADMIN_PIN_LOCKOUT_SECONDS // 60} minutes",
                "locked_seconds": ADMIN_PIN_LOCKOUT_SECONDS,
            }), 429
        return jsonify({
            "error": "incorrect PIN",
            "attempts_remaining": max(0, ADMIN_PIN_MAX_ATTEMPTS - fail_count),
        }), 403

    _admin_pin_reset(uid)
    return jsonify({"token": _make_admin_pin_token(g.tg_user["id"]), "expires_in": ADMIN_PIN_TOKEN_TTL})


def _init_admin_tables():
    conn = db(); cur = conn.cursor()

    # Audit trail for every admin action taken through this API --
    # answers "who changed what, and when" when a dispute or a
    # mistake needs to be investigated later. This is intentionally
    # append-only: there is no UI anywhere to edit or delete a row.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action_type TEXT,
        details TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()


_init_admin_tables()


def _init_deposit_dedup():
    """Adds a screenshot_hash column to payments so the exact same
    image can't be submitted more than once (across any user, any
    status) -- a common fraud pattern is reusing one real deposit
    screenshot to claim several deposits."""
    conn = db(); cur = conn.cursor()
    cur.execute("PRAGMA table_info(payments)")
    cols = {r["name"] for r in cur.fetchall()}
    if "screenshot_hash" not in cols:
        cur.execute("ALTER TABLE payments ADD COLUMN screenshot_hash TEXT")
    if "approved_at" not in cols:
        cur.execute("ALTER TABLE payments ADD COLUMN approved_at TEXT")
    conn.commit()
    conn.close()


_init_deposit_dedup()


def _init_deposit_bonus_system():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS deposit_bonus_settings (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 1, bonus_percent REAL NOT NULL DEFAULT 10.0, delay_hours REAL NOT NULL DEFAULT 6.0, min_deposit REAL NOT NULL DEFAULT 1.0, max_bonus REAL NOT NULL DEFAULT 1000.0, updated_at TEXT)""")
    cur.execute("""INSERT OR IGNORE INTO deposit_bonus_settings (id,enabled,bonus_percent,delay_hours,min_deposit,max_bonus,updated_at) VALUES (1,1,10.0,6.0,1.0,1000.0,?)""", (_now(),))
    cur.execute("""CREATE TABLE IF NOT EXISTS deposit_bonuses (id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id INTEGER NOT NULL UNIQUE, user_id INTEGER NOT NULL, deposit_amount REAL NOT NULL, bonus_percent REAL NOT NULL, bonus_amount REAL NOT NULL, eligible_at TEXT NOT NULL, credited_at TEXT, status TEXT NOT NULL DEFAULT 'scheduled', created_at TEXT NOT NULL)""")
    cur.execute("UPDATE deposit_bonus_settings SET min_deposit=1.0 WHERE id=1 AND min_deposit=100.0")
    # The old "unlimited" default (1e9) is replaced by a sane 1000 ETB cap; admins can still change it.
    cur.execute("UPDATE deposit_bonus_settings SET max_bonus=1000.0 WHERE id=1 AND max_bonus>=1000000000.0")
    conn.commit(); conn.close()

_init_deposit_bonus_system()


def _ensure_deposit_bonus_schedule(payment_id):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT id,user_id,amount,status,approved_at FROM payments WHERE id=?", (payment_id,))
    pmt = cur.fetchone()
    if not pmt or pmt["status"] != "approved": conn.close(); return
    cur.execute("SELECT * FROM deposit_bonus_settings WHERE id=1"); st=cur.fetchone()
    if not st or not st["enabled"] or pmt["amount"] < st["min_deposit"]: conn.close(); return
    approved_at=pmt["approved_at"] or _now()
    eligible=(datetime.strptime(approved_at,"%Y-%m-%d %H:%M:%S")+timedelta(hours=float(st["delay_hours"]))).strftime("%Y-%m-%d %H:%M:%S")
    bonus=min(round(float(pmt["amount"])*float(st["bonus_percent"])/100,2),float(st["max_bonus"]))
    cur.execute("INSERT OR IGNORE INTO deposit_bonuses(payment_id,user_id,deposit_amount,bonus_percent,bonus_amount,eligible_at,created_at) VALUES (?,?,?,?,?,?,?)",(pmt["id"],pmt["user_id"],pmt["amount"],st["bonus_percent"],bonus,eligible,_now()))
    conn.commit(); conn.close()


def _process_due_deposit_bonuses():
    conn=db(); cur=conn.cursor(); now=_now()
    cur.execute("SELECT id,payment_id,user_id,bonus_amount FROM deposit_bonuses WHERE status='scheduled' AND eligible_at<=? ORDER BY id LIMIT 100",(now,))
    rows=cur.fetchall()
    for b in rows:
        try:
            cur.execute("BEGIN IMMEDIATE")
            cur.execute("SELECT status FROM deposit_bonuses WHERE id=?",(b["id"],)); state=cur.fetchone()
            if not state or state["status"]!='scheduled': conn.rollback(); continue
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(b["bonus_amount"],b["user_id"]))
            if cur.rowcount != 1: conn.rollback(); continue
            cur.execute("UPDATE deposit_bonuses SET status='credited',credited_at=? WHERE id=? AND status='scheduled'",(now,b["id"]))
            if cur.rowcount != 1: conn.rollback(); continue
            cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES (?,?,?,?)",(b["user_id"],b["bonus_amount"],'deposit_bonus',now))
            conn.commit()
            try: tg_send_message(b["user_id"],f"🎁 Deposit Bonus ተሰጥቷል!\n\n🎁 Bonus: {b['bonus_amount']:.2f} ብር\n🧾 Payment #{b['payment_id']}\n\nWallet ውስጥ ተጨምሯል።")
            except Exception: pass
        except Exception:
            try: conn.rollback()
            except Exception: pass
    conn.close()


def _deposit_bonus_worker():
    while True:
        try:
            conn=db(); cur=conn.cursor(); cur.execute("SELECT id FROM payments WHERE status='approved' AND id NOT IN (SELECT payment_id FROM deposit_bonuses)"); ids=[r["id"] for r in cur.fetchall()]; conn.close()
            for pid in ids: _ensure_deposit_bonus_schedule(pid)
            _process_due_deposit_bonuses()
        except Exception: logger.exception("deposit bonus worker failed")
        time.sleep(60)

threading.Thread(target=_deposit_bonus_worker, name="deposit-bonus-worker", daemon=True).start()


@app.route("/api/admin/deposit-bonus", methods=["GET","POST"])
@require_telegram_auth
@require_admin
def admin_deposit_bonus():
    conn=db(); cur=conn.cursor()
    if request.method == "POST":
        body=request.get_json(silent=True) or {}
        try:
            enabled=1 if bool(body.get("enabled",True)) else 0; bonus_percent=float(body.get("bonus_percent",10)); delay_hours=float(body.get("delay_hours",6)); min_deposit=float(body.get("min_deposit",100)); max_bonus=float(body.get("max_bonus",10000))
            if not (0<=bonus_percent<=100 and 0<=delay_hours<=168 and 0<=min_deposit<=1000000 and 0<=max_bonus<=1000000): raise ValueError
        except (TypeError,ValueError): conn.close(); return jsonify({"error":"invalid bonus settings"}),400
        cur.execute("UPDATE deposit_bonus_settings SET enabled=?,bonus_percent=?,delay_hours=?,min_deposit=?,max_bonus=?,updated_at=? WHERE id=1",(enabled,bonus_percent,delay_hours,min_deposit,max_bonus,_now())); conn.commit()
        _log_admin_action(g.tg_user["id"],"deposit_bonus_settings_update",{"enabled":enabled,"bonus_percent":bonus_percent,"delay_hours":delay_hours,"min_deposit":min_deposit,"max_bonus":max_bonus})
    cur.execute("SELECT * FROM deposit_bonus_settings WHERE id=1"); st=dict(cur.fetchone())
    cur.execute("SELECT b.*,p.created_at deposit_created_at,p.approved_at,u.first_name,u.username FROM deposit_bonuses b LEFT JOIN payments p ON p.id=b.payment_id LEFT JOIN users u ON u.user_id=b.user_id ORDER BY b.id DESC LIMIT 100"); rows=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) c,COALESCE(SUM(bonus_amount),0) total FROM deposit_bonuses WHERE status='credited'"); totals=cur.fetchone(); conn.close()
    return jsonify({"settings":st,"items":rows,"credited_count":totals["c"],"credited_total":round(totals["total"],2)})


def _init_number_game_history():
    """Number Game currently resolves and forgets -- there is no
    record of past rounds anywhere, unlike Boom Game's fairness log.
    This table gives it the same transparency: every play (guess,
    secret, win/lose) is recorded and readable via
    /api/games/number/history."""
    conn = db(); cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS webapp_number_rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        first_name TEXT,
        guess INTEGER,
        secret INTEGER,
        won INTEGER,
        entry_fee REAL,
        payout REAL,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()


_init_number_game_history()


def _init_self_exclusion():
    """Self-exclusion: a user can lock THEMSELVES out of the whole app
    for a fixed period. Unlike a ban, this is not reversible by an
    admin during the period -- that's the entire point of
    self-exclusion as a responsible-gambling tool, so it has to
    actually hold even against staff."""
    conn = db(); cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {r["name"] for r in cur.fetchall()}
    if "self_excluded_until" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN self_excluded_until TEXT")
    if "terms_accepted_at" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN terms_accepted_at TEXT")
    conn.commit()
    conn.close()


_init_self_exclusion()


def _init_admin_security():
    """Table backing the two-step confirmation flow for large balance
    adjustments (see LARGE_ADJUSTMENT_THRESHOLD below). The Admin
    Panel PIN itself is stateless (a signed token, verified by
    recomputing its HMAC -- see _make_admin_pin_token /
    _verify_admin_pin_token) so it needs no table of its own."""
    conn = db(); cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pending_admin_confirmations (
        token TEXT PRIMARY KEY,
        admin_id INTEGER,
        action_type TEXT,
        payload TEXT,
        expires_at REAL
    )
    """)
    conn.commit()
    conn.close()


_init_admin_security()


def _init_marketplace_resolution_notes():
    conn = db(); cur = conn.cursor()
    cur.execute("PRAGMA table_info(marketplace_transactions)")
    cols = {r["name"] for r in cur.fetchall()}
    if "resolution_note" not in cols:
        cur.execute("ALTER TABLE marketplace_transactions ADD COLUMN resolution_note TEXT")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace_notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER NOT NULL,
        tx_id TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL,
        sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0
    )""")
    # Keep one review per escrow transaction. Preserve the earliest review if
    # an older database already contains duplicates before adding the index.
    cur.execute("DELETE FROM marketplace_reviews WHERE tx_id IS NOT NULL AND review_id NOT IN (SELECT MIN(review_id) FROM marketplace_reviews WHERE tx_id IS NOT NULL GROUP BY tx_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_marketplace_reviews_tx ON marketplace_reviews(tx_id) WHERE tx_id IS NOT NULL")
    conn.commit()
    conn.close()


_init_marketplace_resolution_notes()
threading.Thread(target=_marketplace_notification_worker, name="marketplace-notification-outbox", daemon=True).start()


def _init_boom_provably_fair():
    """Adds the commit-reveal columns to Boom rounds: server_seed
    (kept secret until the round ends) and commitment (its SHA-256
    hash, shown to players via /api/games/boom/state THE MOMENT the
    round starts). Bombs are derived deterministically from
    server_seed, so once a round's commitment has been shown, nobody
    -- including an admin with direct DB access -- can change which
    boxes are bombs without it being detectable: a player who saved
    the commitment can, after the round ends and server_seed is
    revealed in the history endpoint, independently recompute
    SHA-256(server_seed) and the bomb positions themselves and confirm
    both match what was shown/what happened."""
    conn = db(); cur = conn.cursor()
    cur.execute("PRAGMA table_info(webapp_boom_rounds)")
    cols = {r["name"] for r in cur.fetchall()}
    if "server_seed" not in cols:
        cur.execute("ALTER TABLE webapp_boom_rounds ADD COLUMN server_seed TEXT")
    if "commitment" not in cols:
        cur.execute("ALTER TABLE webapp_boom_rounds ADD COLUMN commitment TEXT")
    conn.commit()
    conn.close()


_init_boom_provably_fair()


def _log_admin_action(admin_id, action_type, details: dict):
    conn = db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO admin_actions(admin_id, action_type, details, created_at) VALUES (?,?,?,?)",
        (admin_id, action_type, json.dumps(details, ensure_ascii=False), _now())
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------
# HOUSE EDGE LOCK
#
# The problem this solves: kdm_bot.py's own admin panel (➖/➕ buttons,
# not visible to us here) writes entry_fee and win_amount as two
# SEPARATE independent numbers. If an admin nudges one without
# recalculating the other, the game's house edge silently drifts --
# possibly to a value that loses the house money on every round, or
# to one so harsh players stop playing, with no one noticing until
# much later.
#
# The fix has to live at the DATABASE layer, not just in this file's
# own routes -- because kdm_bot.py can still write to this same table
# directly, and we have no way to add the same safety check there.
# So instead of trusting every writer to do the right thing, two
# SQLite triggers make win_amount a value the table itself keeps
# correct no matter who writes to it or how:
#
#   win_amount = ROUND(entry_fee * (1 - house_edge) / win_probability, 2)
#
# win_probability is fixed per game (a property of the game's actual
# rules, not a business decision):
#   - bomb:   9 boxes, 3 bombs, win = clear all 6 safe boxes first
#             P(win) = 6!*3!/9! = 1/84
#   - number: single guess out of 15                = 1/15
#
# house_edge is the ONE dial that actually represents a business
# decision, and it only changes when an admin explicitly changes it
# (via PUT /api/admin/games/settings) -- never as a side effect of
# adjusting entry_fee, and never because kdm_bot.py's win_amount
# ➕/➖ buttons were pressed (trigger 2 immediately reverts any
# win_amount write that doesn't match the locked formula, so those
# buttons stop changing the actual payout -- see the note in the
# chat response about this).
# ------------------------------------------------------------

from fractions import Fraction

WIN_PROBABILITY = {
    "bomb": float(Fraction(1, 84)),    # 6 safe boxes must all be cleared before any of 3 bombs (9 total)
    "number": float(Fraction(1, 15)),  # single guess, numbers 1-15
}
DEFAULT_HOUSE_EDGE = 0.15  # every game starts at 15%


def _init_house_edge_lock():
    conn = db(); cur = conn.cursor()

    cur.execute("PRAGMA table_info(game_settings)")
    cols = {r["name"] for r in cur.fetchall()}
    if "house_edge" not in cols:
        cur.execute("ALTER TABLE game_settings ADD COLUMN house_edge REAL")
    if "win_probability" not in cols:
        cur.execute("ALTER TABLE game_settings ADD COLUMN win_probability REAL")
    conn.commit()

    # Make sure both games have a row at all (a brand new install
    # where kdm_bot.py hasn't started even once yet would otherwise
    # have nothing here for the triggers to apply to).
    cur.execute("SELECT key FROM game_settings WHERE key IN ('bomb','number')")
    existing = {r["key"] for r in cur.fetchall()}
    if "bomb" not in existing:
        cur.execute("INSERT INTO game_settings(key, entry_fee, house_edge, win_amount, enabled, win_probability) VALUES ('bomb', 10.0, ?, 588.0, 1, ?)", (DEFAULT_HOUSE_EDGE, WIN_PROBABILITY['bomb']))
    if "number" not in existing:
        cur.execute("INSERT INTO game_settings(key, entry_fee, house_edge, win_amount, enabled, win_probability) VALUES ('number', 10.0, ?, 105.0, 1, ?)", (DEFAULT_HOUSE_EDGE, WIN_PROBABILITY['number']))
    conn.commit()

    for key, p in WIN_PROBABILITY.items():
        cur.execute(
            "UPDATE game_settings SET win_probability=? WHERE key=? AND (win_probability IS NULL OR win_probability<=0)",
            (p, key)
        )
    conn.commit()

    # Backfill house_edge from whatever entry/win values are ALREADY
    # live, so running this migration never silently changes a
    # payout that's currently in effect -- it only formalizes the
    # edge that's already there as the new locked value. An admin can
    # then deliberately change it afterwards if they want to.
    cur.execute(
        "SELECT key, entry_fee, win_amount, win_probability FROM game_settings "
        "WHERE key IN ('bomb','number') AND house_edge IS NULL"
    )
    for row in cur.fetchall():
        entry_fee, win_amount, p = row["entry_fee"], row["win_amount"], row["win_probability"]
        if entry_fee and p:
            implied = 1.0 - (win_amount * p / entry_fee)
            implied = max(0.0, min(0.95, implied))  # sanity clamp -- never store a nonsensical edge
        else:
            implied = DEFAULT_HOUSE_EDGE
        cur.execute("UPDATE game_settings SET house_edge=? WHERE key=?", (implied, row["key"]))
    conn.commit()

    # Trigger 1: entry_fee or house_edge changed (by ANY writer,
    # including kdm_bot.py) -> recompute win_amount from the formula.
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_gs_recalc_on_entry_or_edge
    AFTER UPDATE OF entry_fee, house_edge ON game_settings
    FOR EACH ROW
    WHEN NEW.win_probability IS NOT NULL AND NEW.win_probability > 0
    BEGIN
        UPDATE game_settings
        SET win_amount = ROUND(NEW.entry_fee * (1.0 - NEW.house_edge) / NEW.win_probability, 2)
        WHERE key = NEW.key;
    END;
    """)

    # Trigger 2: win_amount changed directly (e.g. kdm_bot.py's own
    # win-amount ➕/➖ button) to something that does NOT match the
    # locked formula -> immediately snap it back. This is what makes
    # the lock unconditional rather than "unconditional as long as
    # nobody touches win_amount directly."
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_gs_recalc_on_direct_win_amount_edit
    AFTER UPDATE OF win_amount ON game_settings
    FOR EACH ROW
    WHEN NEW.win_probability IS NOT NULL AND NEW.win_probability > 0
      AND ABS(NEW.win_amount - ROUND(NEW.entry_fee * (1.0 - NEW.house_edge) / NEW.win_probability, 2)) > 0.01
    BEGIN
        UPDATE game_settings
        SET win_amount = ROUND(NEW.entry_fee * (1.0 - NEW.house_edge) / NEW.win_probability, 2)
        WHERE key = NEW.key;
    END;
    """)
    conn.commit()
    # One-time: Boom and Number start at 15% (admin can change them freely afterwards). The trigger above recomputes win_amount.
    cur.execute("CREATE TABLE IF NOT EXISTS platform_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
    if not cur.execute("SELECT 1 FROM platform_settings WHERE key='house_edge_start15_classic_v2'").fetchone():
        cur.execute("UPDATE game_settings SET house_edge=?", (DEFAULT_ALL_HOUSE_EDGE,))
        cur.execute("INSERT OR REPLACE INTO platform_settings(key,value,updated_at) VALUES('house_edge_start15_classic_v2','1',?)", (_now(),))
        conn.commit()
    conn.close()


_init_house_edge_lock()


@app.route("/api/admin/games/settings")
@require_telegram_auth
@require_admin
def admin_games_settings():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM game_settings WHERE key IN ('bomb','number')")
    rows = {r["key"]: dict(r) for r in cur.fetchall()}
    conn.close()
    return jsonify({
        key: {
            "entry_fee": row["entry_fee"],
            "win_amount": row["win_amount"],
            "house_edge": row["house_edge"],
            "enabled": bool(row["enabled"]),
            "win_probability": row["win_probability"],
        }
        for key, row in rows.items()
    })


@app.route("/api/admin/games/settings", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_update_game_settings():
    body = request.get_json(silent=True) or {}
    key = body.get("key")
    if key not in ("bomb", "number"):
        return jsonify({"error": "key must be 'bomb' or 'number'"}), 400

    try:
        entry_fee = float(body["entry_fee"])
        house_edge = float(body["house_edge"])
        enabled = bool(body.get("enabled", True))
        if entry_fee <= 0:
            raise ValueError("entry_fee must be positive")
        if not (0 <= house_edge <= MAX_HOUSE_EDGE):
            raise ValueError(f"house_edge must be between 0 and {MAX_HOUSE_EDGE}")
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": f"invalid input: {e}"}), 400

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM game_settings WHERE key=?", (key,))
    before = dict(cur.fetchone() or {})
    cur.execute(
        "UPDATE game_settings SET entry_fee=?, house_edge=?, enabled=? WHERE key=?",
        (entry_fee, house_edge, int(enabled), key)
    )
    cur.execute("SELECT * FROM game_settings WHERE key=?", (key,))
    after = dict(cur.fetchone())
    conn.commit()
    conn.close()

    _log_admin_action(g.tg_user["id"], "game_settings_update", {
        "key": key, "before": before, "after": after,
    })

    if before.get("house_edge") is not None and abs(before["house_edge"] - house_edge) > 0.001:
        _notify_owner_of_sensitive_action(g.tg_user["id"], "house_edge_change", {
            "key": key, "old_edge": before["house_edge"], "new_edge": house_edge,
        })

    return jsonify({
        "key": key,
        "entry_fee": after["entry_fee"],
        "win_amount": after["win_amount"],  # server-computed by the trigger, never client-supplied
        "house_edge": after["house_edge"],
        "enabled": bool(after["enabled"]),
    })


@app.route("/api/admin/stats")
@require_telegram_auth
@require_admin
def admin_stats():
    conn = db(); cur = conn.cursor()

    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(balance),0) s FROM users")
    row = cur.fetchone()
    total_users, total_liability = row["c"], row["s"]

    cur.execute("SELECT COUNT(*) c FROM payments WHERE status='pending'")
    pending_deposits = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) c FROM withdrawals WHERE status='pending'")
    pending_withdrawals = cur.fetchone()["c"]

    cur.execute("BEGIN IMMEDIATE")
    _auto_refund_stale_escrow(cur)
    conn.commit()

    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM marketplace_transactions WHERE status='held_in_escrow'")
    row = cur.fetchone()
    pending_escrow_count, pending_escrow_amount = row["c"], row["s"]

    overdue_cutoff = (datetime.now() - timedelta(hours=ESCROW_OVERDUE_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "SELECT COUNT(*) c FROM marketplace_transactions WHERE status='held_in_escrow' AND created_at < ?",
        (overdue_cutoff,)
    )
    overdue_escrow_count = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) c FROM marketplace_reports WHERE status='open'")
    open_reports = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) c FROM users WHERE banned=1")
    banned_count = cur.fetchone()["c"]

    cur.execute("""SELECT
        COALESCE(SUM(CASE WHEN entry_type='marketplace_commission' THEN amount ELSE 0 END),0) marketplace_commission,
        COALESCE(SUM(CASE WHEN entry_type='game_house_result' THEN amount ELSE 0 END),0) game_house_result,
        COALESCE(SUM(amount),0) net
        FROM platform_ledger
    """)
    platform_totals = cur.fetchone()

    # Reconciliation: every balance-changing action in this file
    # always inserts a matching transactions row for the SAME user in
    # the SAME DB transaction, so per-user balance should always equal
    # the sum of that user's own transaction history. A mismatch means
    # something changed a balance without logging it (a bug) or vice
    # versa -- catch it here instead of discovering it during an
    # argument with a user about their balance.
    #
    # NOTE: 'withdraw' rows are stored as a POSITIVE amount (same
    # convention history() already flips for display -- see the
    # comment there), so they have to be negated here too before
    # summing, or every withdrawal looks double-counted.
    cur.execute("""
        SELECT COUNT(*) c FROM (
            SELECT u.user_id, u.balance,
                   COALESCE(SUM(t.amount), 0) AS tx_sum
            FROM users u LEFT JOIN transactions t ON t.user_id = u.user_id
            GROUP BY u.user_id
            HAVING ABS(u.balance - tx_sum) > 0.01
        )
    """)
    balance_mismatches = cur.fetchone()["c"]

    conn.close()
    return jsonify({
        "total_users": total_users,
        "total_liability": round(total_liability, 2),
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
        "pending_escrow_count": pending_escrow_count,
        "pending_escrow_amount": round(pending_escrow_amount, 2),
        "overdue_escrow_count": overdue_escrow_count,
        "balance_mismatches": balance_mismatches,
        "open_reports": open_reports,
        "banned_users": banned_count,
        "platform_revenue": {
            "marketplace_commission": round(platform_totals["marketplace_commission"], 2),
            "game_house_result": round(platform_totals["game_house_result"], 2),
            "net": round(platform_totals["net"], 2),
        },
    })


@app.route("/api/admin/platform-ledger")
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_platform_ledger():
    """Admin-only reconciliation view for platform revenue and game house result."""
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) positive, COALESCE(SUM(amount),0) net FROM platform_ledger")
    totals = cur.fetchone()
    cur.execute("""SELECT entry_type, COUNT(*) count, COALESCE(SUM(amount),0) total
                   FROM platform_ledger GROUP BY entry_type ORDER BY entry_type""")
    by_type = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT id,entry_type,amount,reference_id,note,created_at FROM platform_ledger ORDER BY id DESC LIMIT 100")
    recent = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({
        "positive_total": round(totals["positive"],2),
        "net_total": round(totals["net"],2),
        "by_type": by_type,
        "recent": recent,
        "marketplace_commission_rate": get_marketplace_commission_rate(),
    })


def _bonus_report_data(cur, days):
    """Shared by the admin report and the owner cost alert. days=0 -> all time."""
    since=(datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S") if days else "0000-00-00 00:00:00"
    BONUS_TYPES={"welcome_bonus":"welcome","invite_bonus":"invite","mbox_prize":"mystery_box","deposit_bonus":"deposit_bonus","cashback":"cashback"}
    given={v:{"count":0,"total":0.0} for v in BONUS_TYPES.values()}
    cur.execute("SELECT transaction_type t,COUNT(*) n,COALESCE(SUM(amount),0) s FROM transactions WHERE created_at>=? AND transaction_type IN (%s) GROUP BY transaction_type"%",".join("?"*len(BONUS_TYPES)),(since,*BONUS_TYPES))
    for r in cur.fetchall(): given[BONUS_TYPES[r["t"]]]={"count":int(r["n"]),"total":round(float(r["s"]),2)}
    total_given=round(sum(v["total"] for v in given.values()),2)
    cur.execute("SELECT COUNT(*) n,COALESCE(SUM(MIN(COALESCE(bonus_locked,0),COALESCE(balance,0))),0) s FROM users WHERE COALESCE(bonus_locked,0)>0 AND COALESCE(balance,0)>0")
    o=cur.fetchone(); outstanding={"players":int(o["n"]),"locked_bonus_in_wallets":round(float(o["s"]),2)}
    # house result per game (stake - payout - refund), same transaction types the cashback engine uses
    cur.execute("""SELECT transaction_type t,COALESCE(SUM(amount),0) s FROM transactions WHERE created_at>=?
                   AND (transaction_type LIKE 'game\\_%' ESCAPE '\\' OR transaction_type IN ('number_guess_bet','number_guess_win','group_mines_bet','group_mines_win','group_mines_timeout_refund','sports_bet','sports_win','sports_refund'))
                   GROUP BY transaction_type""",(since,))
    games={}
    for r in cur.fetchall():
        t=r["t"]; a=float(r["s"])
        if t.startswith("game_"):
            m=re.match(r"^game_(.+)_(stake|payout|refund)$",t)
            if not m: continue
            name,kind=m.group(1),m.group(2)
        else:
            name,kind=(t.split("_")[0] if t.startswith("sports") else t.rsplit("_",1)[0]),("stake" if t.endswith("_bet") else "payout" if t.endswith("_win") else "refund")
        g_=games.setdefault(name,{"game":name,"staked":0.0,"returned":0.0})
        if kind=="stake": g_["staked"]+=-a
        else: g_["returned"]+=a
    rows=[]
    for g_ in games.values():
        st,rt=round(g_["staked"],2),round(g_["returned"],2); prof=round(st-rt,2)
        rows.append({"game":g_["game"],"staked":st,"returned":rt,"house_profit":prof,"hold_pct":round(prof/st*100,2) if st>0 else None})
    rows.sort(key=lambda x:-x["house_profit"])
    house_total=round(sum(x["house_profit"] for x in rows),2)
    cashback_paid=given["cashback"]["total"]
    bonus_cost_vs_profit=round(total_given/house_total*100,1) if house_total>0 else None
    warnings=[]
    if PLATFORM_BANKROLL_ETB<=0: warnings.append("PLATFORM_BANKROLL_ETB=0: bankroll exposure guard is OFF. Set it to the real cash available for winners.")
    if house_total>0 and total_given>house_total*0.5: warnings.append("Bonus + cashback cost is more than 50% of the house profit in this period.")
    if house_total<=0 and total_given>0: warnings.append("House result is not positive while bonuses were given.")
    return ({"days":days,"bonus_given":given,"bonus_given_total":total_given,"cashback_paid":cashback_paid,
                    "outstanding":outstanding,"games":rows,"house_profit_total":house_total,
                    "bonus_cost_pct_of_house_profit":bonus_cost_vs_profit,
                    "net_after_bonus":round(house_total-total_given,2),
                    "bankroll_etb":PLATFORM_BANKROLL_ETB,"warnings":warnings})


@app.route("/api/admin/bonus-report")
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_bonus_report():
    """One-page cost view: bonuses given, cashback paid, bonus still sitting in player wallets, house result per game.
    ?days=N limits the flow figures (default 30, 0 = all time)."""
    try: days=max(0,min(3650,int(request.args.get("days","30"))))
    except ValueError: days=30
    conn=db(); cur=conn.cursor()
    try:
        return jsonify(_bonus_report_data(cur,days))
    finally:
        conn.close()


def _cost_alert_check():
    """Telegram the OWNER when bonus + cashback eat too much of the house profit (or the house result is negative
    while bonuses were given). At most one alert per 24h for the same condition; safe with several workers."""
    conn=db(); cur=conn.cursor()
    try:
        c=_pc.get_controls(cur)
        if not c["cost_alert_enabled"]: return False
        days=int(c["cost_alert_window_days"])
        r=_bonus_report_data(cur,days)
        given,house=r["bonus_given_total"],r["house_profit_total"]
        if given<c["cost_alert_min_bonus"]: return False
        if house<=0: key="negative_house"
        elif given>house*c["cost_alert_bonus_pct"]/100.0: key="bonus_share"
        else: return False
        cur.execute("SELECT value FROM platform_settings WHERE key='cost_alert_last'"); row=cur.fetchone()
        last=row[0] if row else ""
        if last:
            try:
                lk,lt=last.split("|",1)
                if lk==key and (datetime.now()-datetime.strptime(lt,"%Y-%m-%d %H:%M:%S")).total_seconds()<86400: return False
            except ValueError: pass
        new=f"{key}|{_now()}"
        if row is None:
            cur.execute("INSERT OR IGNORE INTO platform_settings(key,value,updated_at) VALUES('cost_alert_last',?,?)",(new,_now()))
        else:
            cur.execute("UPDATE platform_settings SET value=?,updated_at=? WHERE key='cost_alert_last' AND value=?",(new,_now(),last))
        if cur.rowcount!=1: conn.rollback(); return False   # another worker already sent it
        conn.commit()
        pct=r["bonus_cost_pct_of_house_profit"]
        msg=(f"⚠️ የቦነስ ወጪ ማስጠንቀቂያ (ያለፉት {days} ቀን)\n"
             f"🎁 ቦነስ + Cashback: {given:.2f} ብር\n🏠 የቤቱ ትርፍ: {house:.2f} ብር\n"
             +(f"📊 ቦነስ ከትርፍ የበላው: {pct}%\n" if pct is not None else "⛔ የቤቱ ውጤት አዎንታዊ አይደለም\n")
             +f"💼 ያልተጠቀሙበት ቦነስ በተጫዋቾች እጅ: {r['outstanding']['locked_bonus_in_wallets']:.2f} ብር\n"
             +"ዝርዝር፦ Admin → የቦነስ ወጪ ሪፖርት")
        try: tg_send_message(OWNER_ID,msg,parse_mode=None)
        except Exception: logger.exception("cost alert send failed")
        return True
    finally:
        conn.close()


def _cost_alert_worker():
    time.sleep(120)
    while True:
        try: _cost_alert_check()
        except Exception: logger.exception("cost alert worker failed")
        time.sleep(900)

if not os.getenv("DISABLE_COST_ALERT_WORKER"):
    threading.Thread(target=_cost_alert_worker,name="cost-alert-worker",daemon=True).start()


@app.route("/api/admin/marketplace/pending")
@require_telegram_auth
@require_admin
def admin_marketplace_pending():
    """Lists escrowed transactions awaiting release/refund -- the
    /api/marketplace/admin/resolve endpoint already existed to ACT on
    a tx_id, but nothing surfaced which tx_ids actually need a
    decision. Without this, an admin would have had to know a tx_id
    in advance from somewhere else."""
    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    _auto_refund_stale_escrow(cur)
    conn.commit()

    cur.execute("""
        SELECT t.tx_id, t.buyer_id, t.creator_id, t.amount, t.created_at, p.title
        FROM marketplace_transactions t
        LEFT JOIN marketplace_posts p ON p.post_id = t.post_id
        WHERE t.status='held_in_escrow'
        ORDER BY t.created_at ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    overdue_cutoff = (datetime.now() - timedelta(hours=ESCROW_OVERDUE_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    for r in rows:
        r["overdue"] = r["created_at"] < overdue_cutoff
    conn.close()
    return jsonify({"pending": rows, "overdue_after_hours": ESCROW_OVERDUE_HOURS, "auto_refund_after_hours": ESCROW_AUTO_REFUND_HOURS})


@app.route("/api/admin/marketplace/reports")
@require_telegram_auth
@require_admin
def admin_marketplace_reports():
    """Reports were previously write-only: /api/marketplace/report
    inserted a row and pinged the admin's DM, but there was no way to
    ever look the list back up afterwards (e.g. after the DM
    notification got buried)."""
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.report_id, r.reporter_id, r.post_id, r.creator_id, r.reason, r.created_at, r.status, p.title
        FROM marketplace_reports r
        LEFT JOIN marketplace_posts p ON p.post_id = r.post_id
        ORDER BY r.created_at DESC
        LIMIT 100
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"reports": rows})


@app.route("/api/admin/marketplace/reports/resolve", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_resolve_report():
    body = request.get_json(silent=True) or {}
    report_id = body.get("report_id")
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE marketplace_reports SET status='reviewed' WHERE report_id=?", (report_id,))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "report not found"}), 404
    conn.commit()
    conn.close()
    _log_admin_action(g.tg_user["id"], "report_resolved", {"report_id": report_id})
    return jsonify({"status": "success"})


# ------------------------------------------------------------
# MARKETPLACE MODERATION / TRUST & SAFETY
# ------------------------------------------------------------

@app.route("/api/admin/marketplace/moderation")
@require_telegram_auth
@require_admin
def admin_marketplace_moderation():
    status = (request.args.get("status") or "pending").strip()
    allowed = {"pending","approved","rejected","hidden","deleted","all"}
    if status not in allowed: return jsonify({"error":"invalid moderation status"}),400
    conn=db(); cur=conn.cursor()
    where="" if status=="all" else "WHERE p.moderation_status=?"
    params=[] if status=="all" else [status]
    cur.execute(f"""SELECT p.*, u.first_name creator_first_name, u.username creator_username,
        COALESCE(u.marketplace_verified,0) marketplace_verified, COALESCE(u.marketplace_suspended,0) marketplace_suspended
        FROM marketplace_posts p LEFT JOIN users u ON u.user_id=p.creator_id {where}
        ORDER BY p.post_id DESC LIMIT 200""", params)
    posts=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) c FROM marketplace_posts WHERE moderation_status='pending'"); pending_posts=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM marketplace_reports WHERE status='open'"); open_reports=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM marketplace_transactions WHERE status='held_in_escrow'"); disputes=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM users WHERE COALESCE(marketplace_suspended,0)=1"); suspended=cur.fetchone()["c"]
    conn.close()
    for p in posts:
        try:
            p["media_items"]=json.loads(p.get("media_json") or "[]")
        except Exception: p["media_items"]=[]
    return jsonify({"posts":posts,"stats":{"pending_posts":pending_posts,"open_reports":open_reports,"active_disputes":disputes,"suspended_creators":suspended}})


def _marketplace_admin_action(cur, admin_id, post_id, action, reason, note, creator_id=None):
    now=_now()
    cur.execute("""INSERT INTO marketplace_moderation_actions(admin_id,post_id,creator_id,action,reason,note,created_at)
                   VALUES (?,?,?,?,?,?,?)""", (admin_id,post_id,creator_id,action,reason,note,now))

@app.route("/api/admin/marketplace/posts/<int:post_id>/moderate", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_marketplace_moderate_post(post_id):
    body=request.get_json(silent=True) or {}
    action=(body.get("action") or "").strip().lower()
    reason=(body.get("reason") or "").strip()[:500]
    note=(body.get("note") or "").strip()[:1000]
    allowed={"approve","reject","hide","delete","restore","price_approve","price_reject","media_approve","media_reject"}
    if action not in allowed: return jsonify({"error":"invalid action"}),400
    conn=db(); cur=conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT * FROM marketplace_posts WHERE post_id=?",(post_id,)); p=cur.fetchone()
    if not p: conn.rollback(); conn.close(); return jsonify({"error":"post not found"}),404
    uid=g.tg_user["id"]
    if action=="approve":
        cur.execute("UPDATE marketplace_posts SET moderation_status='approved', active=1, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(note,uid,_now(),post_id))
    elif action=="reject":
        cur.execute("UPDATE marketplace_posts SET moderation_status='rejected', active=0, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(reason or note,uid,_now(),post_id))
    elif action=="hide":
        cur.execute("UPDATE marketplace_posts SET moderation_status='hidden', active=0, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(reason or note,uid,_now(),post_id))
    elif action=="delete":
        cur.execute("UPDATE marketplace_posts SET moderation_status='deleted', active=0, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(reason or note,uid,_now(),post_id))
    elif action=="restore":
        cur.execute("UPDATE marketplace_posts SET moderation_status='approved', active=1, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(note,uid,_now(),post_id))
    elif action=="price_approve":
        cur.execute("UPDATE marketplace_posts SET price_status='approved', moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(note,uid,_now(),post_id))
    elif action=="price_reject":
        cur.execute("UPDATE marketplace_posts SET price_status='rejected', active=0, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(reason or note,uid,_now(),post_id))
    elif action in ("media_approve","media_reject"):
        cur.execute("UPDATE marketplace_posts SET media_status=?, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",("approved" if action=="media_approve" else "rejected",reason or note,uid,_now(),post_id))
    _marketplace_admin_action(cur,uid,post_id,action,reason,note,p["creator_id"])
    conn.commit(); conn.close(); _log_admin_action(uid,"marketplace_post_moderated",{"post_id":post_id,"action":action,"reason":reason})
    return jsonify({"status":"success","post_id":post_id,"action":action})

@app.route("/api/admin/marketplace/posts/<int:post_id>/media/<int:media_index>/moderate", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_marketplace_moderate_media(post_id, media_index):
    body=request.get_json(silent=True) or {}; action=(body.get("action") or "").strip().lower(); reason=(body.get("reason") or "").strip()[:500]
    if action not in {"approve","reject","remove"}: return jsonify({"error":"invalid media action"}),400
    conn=db(); cur=conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT * FROM marketplace_posts WHERE post_id=?",(post_id,)); p=cur.fetchone()
    if not p: conn.rollback(); conn.close(); return jsonify({"error":"post not found"}),404
    try: items=json.loads(p["media_json"] or "[]")
    except Exception: items=[]
    if media_index<0 or media_index>=len(items): conn.rollback(); conn.close(); return jsonify({"error":"media not found"}),404
    uid=g.tg_user["id"]; now=_now()
    if action=="remove":
        items[media_index]["moderation_removed"]=True; items[media_index]["moderation_reason"]=reason
        cur.execute("UPDATE marketplace_posts SET media_json=?, moderation_note=?, moderated_by=?, moderated_at=? WHERE post_id=?",(json.dumps(items),reason,uid,now,post_id))
        status="removed"
    else:
        items[media_index]["moderation_status"]="approved" if action=="approve" else "rejected"; items[media_index]["moderation_reason"]=reason
        cur.execute("UPDATE marketplace_posts SET media_json=?, moderated_by=?, moderated_at=? WHERE post_id=?",(json.dumps(items),uid,now,post_id))
        status="approved" if action=="approve" else "rejected"
    cur.execute("INSERT INTO marketplace_media_reviews(post_id,media_index,admin_id,status,reason,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(post_id,media_index) DO UPDATE SET admin_id=excluded.admin_id,status=excluded.status,reason=excluded.reason,created_at=excluded.created_at",(post_id,media_index,uid,status,reason,now))
    _marketplace_admin_action(cur,uid,post_id,"media_"+action,reason,"",p["creator_id"])
    conn.commit(); conn.close(); _log_admin_action(uid,"marketplace_media_moderated",{"post_id":post_id,"media_index":media_index,"action":action,"reason":reason})
    return jsonify({"status":"success","media_index":media_index,"action":action})

@app.route("/api/admin/marketplace/creators/<int:creator_id>/moderate", methods=["POST"])
@require_telegram_auth
@require_admin
def admin_marketplace_moderate_creator(creator_id):
    body=request.get_json(silent=True) or {}; action=(body.get("action") or "").strip().lower(); reason=(body.get("reason") or "").strip()[:500]
    if action not in {"verify","unverify","suspend","unsuspend","ban"}: return jsonify({"error":"invalid creator action"}),400
    conn=db(); cur=conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT user_id,banned FROM users WHERE user_id=?",(creator_id,)); u=cur.fetchone()
    if not u: conn.rollback(); conn.close(); return jsonify({"error":"creator not found"}),404
    uid=g.tg_user["id"]; now=_now()
    if action=="verify": cur.execute("UPDATE users SET marketplace_verified=1 WHERE user_id=?",(creator_id,))
    elif action=="unverify": cur.execute("UPDATE users SET marketplace_verified=0 WHERE user_id=?",(creator_id,))
    elif action=="suspend": cur.execute("UPDATE users SET marketplace_suspended=1, marketplace_suspension_reason=? WHERE user_id=?",(reason,creator_id))
    elif action=="unsuspend": cur.execute("UPDATE users SET marketplace_suspended=0, marketplace_suspension_reason=NULL WHERE user_id=?",(creator_id,))
    elif action=="ban": cur.execute("UPDATE users SET banned=1, marketplace_suspended=1, marketplace_suspension_reason=? WHERE user_id=?",(reason,creator_id))
    _marketplace_admin_action(cur,uid,None,action,reason,"creator moderation",creator_id)
    if action in {"suspend","ban"}: cur.execute("UPDATE marketplace_posts SET active=0, moderation_status=CASE WHEN moderation_status='deleted' THEN 'deleted' ELSE 'hidden' END, moderation_note=?, moderated_by=?, moderated_at=? WHERE creator_id=? AND active=1",(reason,uid,now,creator_id))
    conn.commit(); conn.close(); _log_admin_action(uid,"marketplace_creator_moderated",{"creator_id":creator_id,"action":action,"reason":reason})
    return jsonify({"status":"success","creator_id":creator_id,"action":action})

@app.route("/api/admin/marketplace/moderation/history")
@require_telegram_auth
@require_admin
def admin_marketplace_moderation_history():
    conn=db(); cur=conn.cursor(); cur.execute("SELECT * FROM marketplace_moderation_actions ORDER BY action_id DESC LIMIT 200"); rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify({"history":rows})

@app.route("/api/admin/users/search")
@require_telegram_auth
@require_admin
def admin_user_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "missing query"}), 400

    conn = db(); cur = conn.cursor()
    if q.lstrip("-").isdigit():
        cur.execute(
            "SELECT user_id, first_name, username, balance, banned, manager, self_excluded_until "
            "FROM users WHERE user_id=?",
            (int(q),)
        )
    else:
        cur.execute(
            "SELECT user_id, first_name, username, balance, banned, manager, self_excluded_until FROM users "
            "WHERE username LIKE ? OR first_name LIKE ? LIMIT 20",
            (f"%{q}%", f"%{q}%")
        )
    rows = [dict(r) for r in cur.fetchall()]
    now_str = _now()
    for r in rows:
        # Surface it as a clean boolean + human label instead of a raw
        # timestamp the admin has to mentally compare -- this is the
        # field that was missing before: support had no way to see why
        # a user couldn't log in without checking the DB directly.
        until = r.get("self_excluded_until")
        r["self_excluded_active"] = bool(until and until > now_str)
    conn.close()
    return jsonify({"users": rows})


LARGE_ADJUSTMENT_THRESHOLD = 1000.0  # ብር -- above this, requires a second confirming call
PENDING_CONFIRMATION_TTL = 300  # 5 minutes to confirm before the token expires


def _create_pending_confirmation(admin_id, action_type, payload: dict) -> str:
    token = secrets.token_hex(16)
    conn = db(); cur = conn.cursor()
    # Opportunistic cleanup: a confirmation the admin never followed up
    # on (changed their mind, got distracted) used to sit in this
    # table forever since the only DELETE was on successful consume.
    # Sweeping expired rows here means no separate cron job is needed
    # and the table never grows unbounded.
    cur.execute("DELETE FROM pending_admin_confirmations WHERE expires_at < ?", (time.time(),))
    cur.execute(
        "INSERT INTO pending_admin_confirmations(token, admin_id, action_type, payload, expires_at) VALUES (?,?,?,?,?)",
        (token, admin_id, action_type, json.dumps(payload), time.time() + PENDING_CONFIRMATION_TTL)
    )
    conn.commit()
    conn.close()
    return token


def _consume_pending_confirmation(token, admin_id, action_type):
    """Returns the stored payload dict if the token is valid, unexpired,
    belongs to this admin, and matches the expected action -- and
    deletes it either way so a token can never be reused twice."""
    if not token:
        return None
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM pending_admin_confirmations WHERE token=?", (token,))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM pending_admin_confirmations WHERE token=?", (token,))
        conn.commit()
    conn.close()
    if not row:
        return None
    if row["admin_id"] != admin_id or row["action_type"] != action_type:
        return None
    if time.time() > row["expires_at"]:
        return None
    return json.loads(row["payload"])


def _notify_owner_of_sensitive_action(admin_id, action_type, details: dict):
    """A second, independent notification to OWNER_ID (which may or
    may not be the same person as the acting admin) whenever a
    large-money or house-edge action happens -- so a compromised or
    rogue staff account gets noticed quickly by someone OTHER than
    whoever just took the action, rather than only showing up in an
    audit log nobody's currently looking at."""
    if admin_id == OWNER_ID:
        return  # the owner IS the one who just acted -- no need to alert them about themselves
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": OWNER_ID,
                "text": f"⚠️ ትልቅ Admin Action\nBy admin: {admin_id}\nType: {action_type}\n{json.dumps(details, ensure_ascii=False)}"[:4000],
            },
            timeout=5,
        )
    except Exception:
        pass


@app.route("/api/admin/users/adjust-balance", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
@rate_limit(max_calls=15, window_seconds=300)  # even sub-threshold adjustments can't be spammed
def admin_adjust_balance():
    """Manual balance correction for support cases -- e.g. a deposit
    approved before a screenshot issue was caught, a game dispute, a
    goodwill credit. Every adjustment requires a reason and is logged
    both as a normal transaction (so it shows up in the user's own
    History) and in the admin audit trail.

    Amounts beyond LARGE_ADJUSTMENT_THRESHOLD require a SECOND call:
    the first returns a confirm_token instead of executing anything;
    the caller must POST again with that same token to actually apply
    it. This means a single leaked/replayed request can't move a
    large sum by itself -- the token is single-use and expires in
    5 minutes."""
    body = request.get_json(silent=True) or {}
    try:
        target_id = int(body["user_id"])
        amount = parse_money(body["amount"], "amount", allow_negative=True)
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "user_id and amount are required"}), 400

    reason = (body.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "a reason is required for any manual adjustment"}), 400
    if amount == 0:
        return jsonify({"error": "amount cannot be zero"}), 400

    admin_id = g.tg_user["id"]

    if abs(amount) > LARGE_ADJUSTMENT_THRESHOLD:
        confirm_token = body.get("confirm_token")
        payload = _consume_pending_confirmation(confirm_token, admin_id, "balance_adjustment")
        if payload is None:
            # First call (or an expired/invalid token) -- issue a
            # fresh confirmation instead of touching any balance.
            new_token = _create_pending_confirmation(admin_id, "balance_adjustment", {
                "user_id": target_id, "amount": amount, "reason": reason,
            })
            return jsonify({
                "confirmation_required": True,
                "confirm_token": new_token,
                "expires_in_seconds": PENDING_CONFIRMATION_TTL,
                "message": f"this is a large adjustment ({amount:+.2f} ብር) -- "
                           f"resubmit with confirm_token to actually apply it"
            }), 202
        # Confirmed -- but re-validate the confirmed payload still
        # matches what's being requested now (defends against a
        # confirm_token being reused with a different amount/user).
        if payload["user_id"] != target_id or payload["amount"] != amount or payload["reason"] != reason:
            return jsonify({"error": "confirm_token does not match the current request"}), 400

    conn = db(); cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT balance FROM users WHERE user_id=?", (target_id,))
    row = cur.fetchone()
    if not row:
        conn.rollback(); conn.close()
        return jsonify({"error": "user not found"}), 404

    if amount < 0 and row["balance"] + amount < 0:
        conn.rollback(); conn.close()
        return jsonify({"error": "adjustment would make balance negative"}), 400

    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_id))
    adjustment_time = _now()
    cur.execute(
        "INSERT INTO transactions(user_id, amount, transaction_type, created_at) VALUES (?,?,?,?)",
        (target_id, amount, "admin_adjustment", adjustment_time)
    )
    _platform_record(cur, "admin_balance_adjustment", -amount, f"admin:{admin_id}:target:{target_id}:{adjustment_time}", reason, adjustment_time)
    conn.commit()
    conn.close()

    _log_admin_action(admin_id, "balance_adjustment", {
        "target_user_id": target_id, "amount": amount, "reason": reason,
    })

    if abs(amount) > LARGE_ADJUSTMENT_THRESHOLD:
        _notify_owner_of_sensitive_action(admin_id, "large_balance_adjustment", {
            "target_user_id": target_id, "amount": amount, "reason": reason,
        })

    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": target_id,
                  "text": f"🛠️ ሂሳብዎ በአስተዳዳሪ ተስተካክሏል፦ {amount:+.2f} ብር\nምክንያት: {reason}"},
            timeout=5,
        )
    except Exception:
        pass

    return jsonify({"status": "success"})


@app.route("/api/admin/users/ban", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_ban_user():
    body = request.get_json(silent=True) or {}
    try:
        target_id = int(body["user_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "user_id is required"}), 400
    banned = bool(body.get("banned", True))
    reason = (body.get("reason") or "").strip()

    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET banned=? WHERE user_id=?", (int(banned), target_id))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "user not found"}), 404
    conn.commit()
    conn.close()

    _log_admin_action(g.tg_user["id"], "ban_toggle", {
        "target_user_id": target_id, "banned": banned, "reason": reason,
    })
    return jsonify({"status": "success", "banned": banned})


@app.route("/api/admin/errors/recent")
@require_telegram_auth
@require_admin
def admin_recent_errors():
    """Tails the same rotating log file every unhandled exception is
    already written to (see handle_uncaught_exception above) -- so
    troubleshooting a report of 'something broke' doesn't require
    shell access to the server, just the Mini App."""
    limit = min(int(request.args.get("limit", 50)), 200)
    try:
        with open("webapp_api_errors.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
        tail = lines[-limit:]
    except FileNotFoundError:
        tail = []
    return jsonify({"lines": tail})


@app.route("/api/admin/actions/recent")
@require_telegram_auth
@require_admin
def admin_recent_actions():
    """The audit trail itself -- every game-settings change, balance
    adjustment, ban, and report resolution taken via this admin
    panel, newest first."""
    limit = min(int(request.args.get("limit", 50)), 200)
    conn = db(); cur = conn.cursor()
    cur.execute(
        "SELECT * FROM admin_actions ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        try:
            r["details"] = json.loads(r["details"])
        except Exception:
            pass
    return jsonify({"actions": rows})


@app.route("/api/admin/reconciliation")
@require_telegram_auth
@require_admin
def admin_reconciliation():
    """Lists exactly which users' balance disagrees with the sum of
    their own transaction history, and by how much -- the detail
    view behind the balance_mismatches count on the dashboard.
    Same withdraw-sign normalization as admin_stats() -- see the note
    there."""
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT u.user_id, u.first_name, u.balance,
               COALESCE(SUM(t.amount), 0) AS tx_sum
        FROM users u LEFT JOIN transactions t ON t.user_id = u.user_id
        GROUP BY u.user_id
        HAVING ABS(u.balance - tx_sum) > 0.01
        ORDER BY ABS(u.balance - tx_sum) DESC
        LIMIT 100
    """)
    rows = []
    for r in cur.fetchall():
        rows.append({
            "user_id": r["user_id"],
            "first_name": r["first_name"],
            "balance": r["balance"],
            "transaction_sum": round(r["tx_sum"], 2),
            "difference": round(r["balance"] - r["tx_sum"], 2),
        })
    conn.close()
    return jsonify({"mismatches": rows})



@app.route("/api/admin/sports/match", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_sports_create_match():
    body=(request.form.to_dict() if request.mimetype=="multipart/form-data" else (request.get_json(silent=True) or {}))
    home=(body.get("home_team") or "").strip()[:80]
    away=(body.get("away_team") or "").strip()[:80]
    try:
        oh=parse_money(body.get("odds_home"),"odds_home")
        sport=str(body.get("sport") or "football").strip().lower()
        league=(str(body.get("league") or "").strip()[:40]) or None
        od=parse_money(body.get("odds_draw"),"odds_draw") if sport=="football" else 0.0   # basketball/tennis: two-way, no draw
        oa=parse_money(body.get("odds_away"),"odds_away")
    except ValueError as e:
        return jsonify({"error":str(e)}),400
    if sport not in ("football","basketball","tennis"):
        return jsonify({"error":"invalid sport"}),400
    odds_all=[x for x in ((oh,od,oa) if sport=="football" else (oh,oa))]
    if not home or not away or home==away or min(odds_all)<=1.0 or max(odds_all)>1000:
        return jsonify({"error":"invalid teams or odds"}),400
    # Bookmaker margin guard: if 1/H + 1/D + 1/A < 1 a player could back all three
    # outcomes and win money whatever the result (arbitrage). Require a positive margin.
    closes_at = str(body.get("closes_at") or "").strip().replace("T", " ")[:19]
    try:
        if len(closes_at) == 16: closes_at += ":00"
        closes_dt = datetime.strptime(closes_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return jsonify({"error":"closes_at is required, format YYYY-MM-DD HH:MM (server local time, = kickoff)"}),400
    if closes_dt <= datetime.now():
        return jsonify({"error":"closes_at must be in the future"}),400
    overround = sum(1.0/x for x in odds_all)
    if overround < SPORTS_MIN_OVERROUND:
        return jsonify({"error":f"odds give the house no margin (1/H+1/D+1/A={overround:.3f}, minimum {SPORTS_MIN_OVERROUND}); lower the odds"}),400
    try:
        home_logo=_save_crest(request.files.get("home_logo")) if request.mimetype=="multipart/form-data" else None
        away_logo=_save_crest(request.files.get("away_logo")) if request.mimetype=="multipart/form-data" else None
    except ValueError as e:
        return jsonify({"error":str(e)}),400
    conn=db(); cur=conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("INSERT INTO sports_matches(home_team,away_team,odds_home,odds_draw,odds_away,status,created_at,closes_at,league,sport,home_logo,away_logo) VALUES(?,?,?,?,?,'OPEN',?,?,?,?,?,?)",(home,away,oh,od,oa,_now(),closes_at,league,sport,home_logo,away_logo))
    mid=cur.lastrowid; conn.commit(); conn.close()
    _log_admin_action(g.tg_user["id"],"sports_match_create",{"match_id":mid,"home":home,"away":away,"odds":[oh,od,oa]})
    return jsonify({"status":"success","match_id":mid})


@app.route("/api/admin/sports/close", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_sports_close_betting():
    body=request.get_json(silent=True) or {}
    try: match_id=int(body.get("match_id"))
    except (TypeError,ValueError): return jsonify({"error":"invalid match_id"}),400
    conn=db(); cur=conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("UPDATE sports_matches SET closes_at=? WHERE id=? AND status='OPEN'",(_now(),match_id))
    changed=cur.rowcount; conn.commit(); conn.close()
    if changed!=1: return jsonify({"error":"open match not found"}),404
    _log_admin_action(g.tg_user["id"],"sports_close_betting",{"match_id":match_id})
    return jsonify({"status":"success"})


def _sports_pool_payouts(bets, result, rake_pct=None):
    """Pool (parimutuel) settlement. Returns ({bet_id: (payout, status)}, rake).
    - VOID, or nobody backed the winner, or nobody lost: everyone is refunded in full, no rake.
    - Otherwise: house takes SPORTS_RAKE_PCT of the whole pool; the rest is shared among winning
      bets pro-rata to their stake. Winners always get at least their stake back (the rake is
      reduced if needed), so the house can never pay out more than the pool: it cannot lose."""
    cents = lambda v: int(round(float(v) * 100))
    stakes = {b["id"]: cents(b["stake"]) for b in bets}
    pool = sum(stakes.values())
    win_ids = [b["id"] for b in bets if b["selection"] == result]
    win_total = sum(stakes[i] for i in win_ids)
    if result == "VOID" or win_total == 0 or win_total == pool:
        return {i: (stakes[i] / 100.0, "VOID") for i in stakes}, 0.0
    rake_pct = SPORTS_RAKE_PCT if rake_pct is None else rake_pct
    net = max(pool - (pool * int(round(rake_pct * 10000))) // 10000, win_total)
    out = {}
    for i in stakes:
        out[i] = ((net * stakes[i] // win_total) / 100.0, "WON") if i in win_ids else (0.0, "LOST")
    paid = sum(int(round(v[0] * 100)) for v in out.values())
    return out, (pool - paid) / 100.0


@app.route("/api/admin/sports/live", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_sports_live():
    """Staff-entered live score shown to players while a match is in play. Display only: it never settles bets."""
    body = request.get_json(silent=True) or {}
    try:
        match_id = int(body.get("match_id")); hs = int(body.get("home_score")); aws = int(body.get("away_score"))
    except (TypeError, ValueError):
        return jsonify({"error": "match_id, home_score and away_score must be whole numbers"}), 400
    if not (0 <= hs <= 99 and 0 <= aws <= 99):
        return jsonify({"error": "score must be between 0 and 99"}), 400
    minute = re.sub(r"[^0-9+'A-Za-z ]", "", str(body.get("minute") or "").strip())[:8] or None
    conn = db(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("UPDATE sports_matches SET home_score=?, away_score=?, live_minute=?, live_updated_at=? WHERE id=? AND status='OPEN'", (hs, aws, minute, _now(), match_id))
    changed = cur.rowcount; conn.commit(); conn.close()
    if not changed: return jsonify({"error": "match not found or already settled"}), 404
    _log_admin_action(g.tg_user["id"], "sports_live_score", {"match_id": match_id, "home": hs, "away": aws, "minute": minute})
    return jsonify({"status": "success"})


@app.route("/api/admin/sports/settle", methods=["POST"])
@require_telegram_auth
@require_admin
@require_fresh_auth
def admin_sports_settle():
    body=request.get_json(silent=True) or {}
    try: match_id=int(body.get("match_id"))
    except (TypeError,ValueError): return jsonify({"error":"invalid match_id"}),400
    result=(body.get("result") or "").upper().strip()
    if result not in ("HOME","DRAW","AWAY","VOID"):
        return jsonify({"error":"result must be HOME, DRAW, AWAY, or VOID"}),400
    conn=db(); cur=conn.cursor(); cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT * FROM sports_matches WHERE id=?",(match_id,)); m=cur.fetchone()
    if not m: conn.rollback(); conn.close(); return jsonify({"error":"match not found"}),404
    if m["status"]!="OPEN": conn.rollback(); conn.close(); return jsonify({"error":"match already settled"}),400
    cur.execute("SELECT * FROM sports_bets WHERE match_id=? AND status='PENDING'",(match_id,)); bets=cur.fetchall(); now=_now()
    payouts, rake = _sports_pool_payouts(bets, result, _sports_rake_pct())
    total_paid=0.0
    for b in bets:
        payout, status = payouts[b["id"]]
        if payout>0:
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(payout,b["user_id"]))
            cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)",(b["user_id"],payout,"sports_win" if status=="WON" else "sports_refund",now))
            total_paid += payout
        cur.execute("UPDATE sports_bets SET status=?,payout=?,settled_at=? WHERE id=? AND status='PENDING'",(status,payout,now,b["id"]))
    cur.execute("UPDATE sports_matches SET status='SETTLED',result=?,settled_at=? WHERE id=? AND status='OPEN'",(result,now,match_id))
    total_staked = round(sum(float(b['stake']) for b in bets), 2)
    _platform_record(cur, 'sports_house_result', round(total_staked-total_paid, 2), f'sports:{match_id}', f'sports {result} settlement', now)
    conn.commit(); conn.close()
    _log_admin_action(g.tg_user["id"],"sports_settle",{"match_id":match_id,"result":result,"bets":len(bets),"paid":round(total_paid,2)})
    return jsonify({"status":"success","bets_settled":len(bets),"paid":round(total_paid,2)})


@app.route("/api/admin/sports/overview")
@require_telegram_auth
@require_admin
def admin_sports_overview():
    """READ-ONLY visibility into sports matches and betting volume.
    Deliberately does NOT include a way to resolve a match or pay out
    bets -- kdm_bot.py already owns that (sports_win transactions are
    already a recognized type, meaning something already credits
    winners for it), and we can't see that file's code from here. A
    second resolve path in this API could pay winners twice if it
    ever ran against the same match kdm_bot.py already settled. This
    endpoint only helps an admin see what's outstanding; settling
    still happens wherever it already happens today."""
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM sports_matches ORDER BY id DESC LIMIT 50")
    matches = []
    for m in cur.fetchall():
        cur.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(stake),0) s FROM sports_bets WHERE match_id=?",
            (m["id"],)
        )
        agg = cur.fetchone()
        matches.append({
            "id": m["id"], "home_team": m["home_team"], "away_team": m["away_team"],
            "status": m["status"], "bet_count": agg["c"], "total_staked": round(agg["s"], 2),
            "closes_at": m["closes_at"], "home_score": m["home_score"], "away_score": m["away_score"], "live_minute": m["live_minute"], "result": m["result"],
            "home_logo": _crest_url(m["home_logo"]), "away_logo": _crest_url(m["away_logo"]),
        })
    conn.close()
    return jsonify({"matches": matches})


@app.route("/api/admin/multi-accounting")
@require_telegram_auth
@require_admin
def admin_multi_accounting():
    """Flags withdrawal bank/telebirr account numbers that have been
    used by MORE THAN ONE distinct Telegram user_id -- a common
    pattern when someone opens multiple accounts to farm signup or
    referral bonuses but cashes everything out to the same real bank
    account. This only flags a pattern for a human to look at; it
    never blocks anything automatically (a shared family account
    number is a legitimate false positive)."""
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT acc_number, GROUP_CONCAT(DISTINCT user_id) AS user_ids, COUNT(DISTINCT user_id) AS n
        FROM withdrawals
        WHERE acc_number IS NOT NULL AND TRIM(acc_number) != ''
        GROUP BY acc_number
        HAVING n > 1
        ORDER BY n DESC
        LIMIT 100
    """)
    rows = []
    for r in cur.fetchall():
        rows.append({
            "acc_number": r["acc_number"],
            "user_ids": [int(x) for x in r["user_ids"].split(",")],
            "distinct_user_count": r["n"],
        })
    conn.close()
    return jsonify({"flagged": rows})


@app.route("/api/admin/backups/status")
@require_telegram_auth
@require_admin
def admin_backup_status():
    """Reads the same ./backups/ directory backup_db.py (the
    standalone script, run via cron) writes into -- lets an admin
    confirm from inside the app itself that backups are actually
    still happening on schedule, instead of only finding out they
    silently stopped when it's too late to matter."""
    backup_dir = "backups"
    if not os.path.isdir(backup_dir):
        return jsonify({"latest_backup": None, "hours_ago": None, "file_count": 0, "warning": "backups/ directory not found -- has backup_db.py ever run?"})

    files = [f for f in os.listdir(backup_dir) if f.startswith("backup_") and f.endswith(".db")]
    if not files:
        return jsonify({"latest_backup": None, "hours_ago": None, "file_count": 0, "warning": "no backup files found"})

    files_with_mtime = [(f, os.path.getmtime(os.path.join(backup_dir, f))) for f in files]
    files_with_mtime.sort(key=lambda x: x[1], reverse=True)
    latest_name, latest_mtime = files_with_mtime[0]
    hours_ago = (time.time() - latest_mtime) / 3600

    return jsonify({
        "latest_backup": latest_name,
        "hours_ago": round(hours_ago, 1),
        "file_count": len(files),
        "warning": "backup is stale (>36h old) -- check that backup_db.py's cron job is still running" if hours_ago > 36 else None,
    })


@app.route("/api/admin/summary/daily")
@require_telegram_auth
@require_admin
def admin_daily_summary():
    """On-demand operational summary for the last 24h -- deposits,
    withdrawals, game volume, marketplace volume, new users. Meant to
    be checked proactively (open the panel each morning) rather than
    only reacting to alerts; also callable from a small cron script
    the same way backup_db.py is, to push this as a daily DM instead
    of requiring someone to remember to look."""
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db(); cur = conn.cursor()

    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM payments WHERE created_at >= ? AND status='approved'", (cutoff,))
    row = cur.fetchone(); deposits_count, deposits_sum = row["c"], row["s"]

    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals WHERE created_at >= ? AND status IN ('pending','approved')", (cutoff,))
    row = cur.fetchone(); withdrawals_count, withdrawals_sum = row["c"], row["s"]

    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) wagered, "
        "COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) paid_out "
        "FROM transactions WHERE created_at >= ? AND transaction_type IN "
        "('group_mines_bet','group_mines_win','number_guess_bet','number_guess_win')",
        (cutoff,)
    )
    row = cur.fetchone(); game_wagered, game_paid_out = row["wagered"], row["paid_out"]

    cur.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM marketplace_transactions WHERE created_at >= ?",
        (cutoff,)
    )
    row = cur.fetchone(); marketplace_count, marketplace_sum = row["c"], row["s"]

    # NOTE: a "new users in last 24h" figure would belong here too,
    # but the users table has no created_at/joined_at column to
    # compute it from -- adding one is a schema change on a table
    # kdm_bot.py also owns, so it's called out here rather than
    # guessed at or silently added.

    conn.close()
    return jsonify({
        "period": "last 24h",
        "deposits": {"count": deposits_count, "total": round(deposits_sum, 2)},
        "withdrawals": {"count": withdrawals_count, "total": round(withdrawals_sum, 2)},
        "games": {"wagered": round(game_wagered, 2), "paid_out": round(game_paid_out, 2),
                  "house_result": round(game_wagered - game_paid_out, 2)},
        "marketplace": {"count": marketplace_count, "volume": round(marketplace_sum, 2)},
    })


def _csv_response(filename, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    resp = app.response_class(buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@app.route("/api/admin/export/reconciliation.csv")
@require_telegram_auth
@require_admin
def admin_export_reconciliation_csv():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT u.user_id, u.first_name, u.balance,
               COALESCE(SUM(t.amount), 0) AS tx_sum
        FROM users u LEFT JOIN transactions t ON t.user_id = u.user_id
        GROUP BY u.user_id
        HAVING ABS(u.balance - tx_sum) > 0.01
    """)
    rows = [(r["user_id"], r["first_name"], r["balance"], round(r["tx_sum"], 2), round(r["balance"] - r["tx_sum"], 2)) for r in cur.fetchall()]
    conn.close()
    return _csv_response("reconciliation.csv", ["user_id", "first_name", "balance", "transaction_sum", "difference"], rows)


@app.route("/api/admin/export/actions.csv")
@require_telegram_auth
@require_admin
def admin_export_actions_csv():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM admin_actions ORDER BY id DESC LIMIT 1000")
    rows = [(r["id"], r["admin_id"], r["action_type"], r["details"], r["created_at"]) for r in cur.fetchall()]
    conn.close()
    return _csv_response("admin_actions.csv", ["id", "admin_id", "action_type", "details", "created_at"], rows)


@app.route("/api/admin/export/users.csv")
@require_telegram_auth
@require_admin
def admin_export_users_csv():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT user_id, first_name, username, balance, banned, manager FROM users ORDER BY user_id")
    rows = [(r["user_id"], r["first_name"], r["username"], r["balance"], r["banned"], r["manager"]) for r in cur.fetchall()]
    conn.close()
    return _csv_response("users.csv", ["user_id", "first_name", "username", "balance", "banned", "manager"], rows)


# V3 extensions: durable realtime rounds, WebRTC signaling, provider-neutral payment contract
exec(compile(open(os.path.join(os.path.dirname(__file__), 'realtime_engine_v3.py')).read(), os.path.join(os.path.dirname(__file__), 'realtime_engine_v3.py'), 'exec'), globals())
exec(compile(open(os.path.join(os.path.dirname(__file__), 'blackjack_engine.py'), encoding='utf-8').read(), os.path.join(os.path.dirname(__file__), 'blackjack_engine.py'), 'exec'), globals())

# V9 extensions: LIVE shared rounds (global 60 s clock; Super Keno first)
exec(compile(open(os.path.join(os.path.dirname(__file__), 'live_engine_v1.py'), encoding='utf-8').read(), os.path.join(os.path.dirname(__file__), 'live_engine_v1.py'), 'exec'), globals())

# V8 extensions: home banners carousel + Shamo daily mystery-box event
exec(compile(open(os.path.join(os.path.dirname(__file__), 'engagement_v8.py')).read(), os.path.join(os.path.dirname(__file__), 'engagement_v8.py'), 'exec'), globals())
exec(compile(open(os.path.join(os.path.dirname(__file__), 'betpro_v1.py')).read(), os.path.join(os.path.dirname(__file__), 'betpro_v1.py'), 'exec'), globals())  # BETPRO: promo images + profile stats

# V10 extensions: hourly Mystery Box + Level / Daily Challenge summary
exec(compile(open(os.path.join(os.path.dirname(__file__), 'rewards_v9.py'), encoding='utf-8').read(), os.path.join(os.path.dirname(__file__), 'rewards_v9.py'), 'exec'), globals())

# V11 extensions: in-app announcements (bell), profile stats, daily mission points
exec(compile(open(os.path.join(os.path.dirname(__file__), 'royal_v1.py'), encoding='utf-8').read(), os.path.join(os.path.dirname(__file__), 'royal_v1.py'), 'exec'), globals())

if __name__ == "__main__":
    # Development server only. In production, run this behind a real
    # WSGI server (gunicorn/uwsgi) and a reverse proxy terminating
    # HTTPS, e.g.:
    #   gunicorn -w 2 -b 127.0.0.1:8000 webapp_api:app
    app.run(host="0.0.0.0", port=8000, debug=False)
