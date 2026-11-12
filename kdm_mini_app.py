# ============================================================
# KDM COMBINED FINAL BASE
# This file is based on the latest LIVE/HOUSE30 code.
# The previously merged auction/wallet/admin code is already
# present in this base; functions are not duplicated.
# ============================================================

import sqlite3
import random
import secrets
import logging
import asyncio
import time
import os
import json
import html
import hmac
import hashlib
from io import BytesIO
from urllib.parse import parse_qsl

from aiohttp import web
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

from bonus_wallet import record_invite, release_invite_bonus, invite_requires_deposit, withdrawable as _withdrawable, INVITE_BONUS_ETB

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ANNOUNCEMENT_CHANNEL_ID = os.getenv("ANNOUNCEMENT_CHANNEL_ID", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")

# ============================================================
# TELEGRAM MINI APP CONFIG
# ============================================================
# IMPORTANT: Telegram Mini Apps must be served from HTTPS in production.
# Example: https://your-domain.com/
WEBAPP_URL = os.getenv("MINI_APP_URL", "").strip()
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))
MINI_APP_DIR = os.getenv("MINI_APP_DIR", os.path.dirname(os.path.abspath(__file__)))
MINI_APP_MAX_AUTH_AGE = 86400

# ============================================================
# ADMIN / MANAGER PERMISSIONS
# ============================================================

def is_admin(user_id):
    return int(user_id) == ADMIN_ID

def is_manager(user_id):
    if int(user_id) == ADMIN_ID:
        return True
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT manager FROM users WHERE user_id=?", (int(user_id),))
    row = cur.fetchone()
    conn.close()
    return bool(row and row["manager"])

def is_staff(user_id):
    return is_admin(user_id) or is_manager(user_id)

def get_manager_ids():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE manager=1")
    ids = [int(r["user_id"]) for r in cur.fetchall()]
    conn.close()
    return list(dict.fromkeys([ADMIN_ID] + ids))

async def send_staff_message(context, text, reply_markup=None, parse_mode="Markdown"):
    for staff_id in get_manager_ids():
        try:
            await context.bot.send_message(chat_id=staff_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logging.warning(f"Staff message delivery failed for {staff_id}: {e}")

async def send_staff_photo(context, photo_id, caption, reply_markup=None):
    for staff_id in get_manager_ids():
        try:
            await context.bot.send_photo(chat_id=staff_id, photo=photo_id, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e:
            logging.warning(f"Staff photo delivery failed for {staff_id}: {e}")


ACCOUNT_NAME = os.getenv("ACCOUNT_NAME", "").strip()
CBE_ACCOUNT = os.getenv("CBE_ACCOUNT", "").strip()
BOA_ACCOUNT = os.getenv("BOA_ACCOUNT", "").strip()
TELEBIRR_NUMBER = os.getenv("TELEBIRR_NUMBER", "").strip()
ADMIN_PANEL_PIN = os.getenv("ADMIN_PANEL_PIN", "").strip()

DB_FILE = os.getenv("DB_FILE", "auction_wallet.db")

# Shared canonical schema/migrations. This runs before bot-local helpers so
# API-first and bot-first startup produce the same money tables.
from extended_schema import init_extended_schema

def _schedule_bot_coro(bot_application, coro):
    loop = bot_application.bot_data.get("event_loop")
    if loop is None or loop.is_closed():
        raise RuntimeError("Telegram application event loop is not available")
    return asyncio.run_coroutine_threadsafe(coro, loop)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ============================================================
# HIGH-TRAFFIC LIVE CONFIG
# ============================================================
# This protects a weak server from creating an unbounded number of
# simultaneous Telegram API requests.
LIVE_EDIT_CONCURRENCY = 20
LIVE_EDIT_TIMEOUT = 8
LIVE_MAX_RECENT_PLAYERS = 30
LIVE_EDIT_BATCH_SIZE = 100

LIVE_EDIT_SEMAPHORE = asyncio.Semaphore(LIVE_EDIT_CONCURRENCY)


# ============================================================
# OLD AUCTION TIERS
# Used only for automatic fallback auctions
# ============================================================

AUCTION_TIERS = [
    {
        "level": 1,
        "ticket_price": 35.0,
        "prize_amount": 1000.0,
        "days": 0,
        "hours": 23,
    },
    {
        "level": 2,
        "ticket_price": 50.0,
        "prize_amount": 2000.0,
        "days": 1,
        "hours": 23,
    },
    {
        "level": 3,
        "ticket_price": 100.0,
        "prize_amount": 5000.0,
        "days": 2,
        "hours": 23,
    },
    {
        "level": 4,
        "ticket_price": 250.0,
        "prize_amount": 10000.0,
        "days": 3,
        "hours": 23,
    },
    {
        "level": 5,
        "ticket_price": 500.0,
        "prize_amount": 25000.0,
        "days": 4,
        "hours": 23,
    },
]


# ============================================================
# DATABASE
# ============================================================

def db():
    # High-traffic SQLite connection. WAL is enabled once in init_db(),
    # not on every request (journal_mode is expensive when repeated).
    conn = sqlite3.connect(
        DB_FILE,
        timeout=8,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def add_column_if_missing(cur, table, column, definition):
    try:
        cur.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
    except sqlite3.OperationalError:
        pass


def init_db():
    init_extended_schema(DB_FILE, ADMIN_ID)
    conn = db()
    cur = conn.cursor()

    # Set SQLite journal mode once at startup, not once per user request.
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            balance REAL DEFAULT 0,
            manager INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            admin_message_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT,
            direction TEXT DEFAULT 'user_to_admin',
            content_type TEXT DEFAULT 'text'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            first_name TEXT,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            photo_file_id TEXT,
            created_at TEXT,
            approved_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            acc_name TEXT,
            acc_number TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_type TEXT,
            payment_id INTEGER,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS aviator_rounds (
            round_id INTEGER PRIMARY KEY AUTOINCREMENT,
            crash_multiplier REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'betting',
            created_at TEXT,
            crashed_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS aviator_bets (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bet_amount REAL NOT NULL,
            cashout_multiplier REAL,
            payout REAL DEFAULT 0,
            status TEXT DEFAULT 'placed',
            created_at TEXT,
            FOREIGN KEY(round_id) REFERENCES aviator_rounds(round_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier_level INTEGER NOT NULL DEFAULT 1,
            prize_amount REAL NOT NULL,
            ticket_price REAL NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TEXT,
            ends_at TEXT,
            warning_sent INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER,
            user_id INTEGER,
            bid_amount REAL NOT NULL,
            created_at TEXT,
            FOREIGN KEY(auction_id) REFERENCES auctions(id)
        )
    """)

    # --------------------------------------------------------
    # Admin-only auction simulation participants
    # These are intentionally kept separate from real bids/users.
    # They never affect winner calculation or real-user wallets.
    # --------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auction_simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL,
            simulated_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            created_by INTEGER
        )
    """)

    # --------------------------------------------------------
    # Database compatibility
    # --------------------------------------------------------

    add_column_if_missing(
        cur, "auctions",
        "tier_level",
        "INTEGER NOT NULL DEFAULT 1"
    )

    add_column_if_missing(
        cur, "auctions",
        "ends_at",
        "TEXT"
    )

    add_column_if_missing(
        cur, "auctions",
        "warning_sent",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        cur, "auctions",
        "winner_user_id",
        "INTEGER"
    )

    add_column_if_missing(
        cur, "auctions",
        "winning_bid",
        "REAL"
    )

    add_column_if_missing(
        cur, "auctions",
        "total_collected",
        "REAL DEFAULT 0"
    )

    add_column_if_missing(
        cur, "auctions",
        "closed_at",
        "TEXT"
    )

    add_column_if_missing(
        cur, "withdrawals",
        "acc_name",
        "TEXT"
    )

    add_column_if_missing(cur, "withdrawals", "acc_number", "TEXT")
    add_column_if_missing(cur, "withdrawals", "screenshot_file_id", "TEXT")
    add_column_if_missing(cur, "withdrawals", "staff_reminded_at", "TEXT")
    add_column_if_missing(cur, "auctions", "post_chat_id", "TEXT")
    add_column_if_missing(cur, "auctions", "post_message_id", "INTEGER")
    add_column_if_missing(cur, "users", "last_seen", "TEXT")
    add_column_if_missing(cur, "users", "manager", "INTEGER DEFAULT 0")
    add_column_if_missing(cur, "support_messages", "direction", "TEXT DEFAULT 'user_to_admin'")
    add_column_if_missing(cur, "support_messages", "content_type", "TEXT DEFAULT 'text'")

    # Critical indexes for high-volume users/bets.
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_round_status ON aviator_bets(round_id, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_round_user_status ON aviator_bets(round_id, user_id, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_round_bet_id ON aviator_bets(round_id, bet_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_created ON transactions(user_id, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bids_auction_user ON bids(auction_id, user_id)")
    conn.commit()

    # Auctions are created manually by Admin only.

    conn.close()


# ============================================================
# AUCTION CREATION
# ============================================================

def create_next_automatic_auction(cur):
    cur.execute("""
        SELECT tier_level
        FROM auctions
        ORDER BY id DESC
        LIMIT 1
    """)

    last_auc = cur.fetchone()

    if not last_auc:
        next_level = 1
    else:
        current_level = int(
            last_auc["tier_level"] or 1
        )

        next_level = (
            current_level % len(AUCTION_TIERS)
        ) + 1

    tier = AUCTION_TIERS[next_level - 1]

    now = datetime.now()

    ends_at = now + timedelta(
        days=tier["days"],
        hours=tier["hours"]
    )

    cur.execute("""
        INSERT INTO auctions (
            tier_level,
            prize_amount,
            ticket_price,
            status,
            created_at,
            ends_at,
            warning_sent
        )
        VALUES (?, ?, ?, 'ACTIVE', ?, ?, 0)
    """, (
        tier["level"],
        tier["prize_amount"],
        tier["ticket_price"],
        now.strftime("%Y-%m-%d %H:%M:%S"),
        ends_at.strftime("%Y-%m-%d %H:%M:%S")
    ))


def create_custom_auction(prize, ticket, hours, minutes):
    conn = db()
    cur = conn.cursor()

    now = datetime.now()
    ends_at = now + timedelta(
        hours=hours,
        minutes=minutes
    )

    cur.execute("""
        INSERT INTO auctions (
            tier_level,
            prize_amount,
            ticket_price,
            status,
            created_at,
            ends_at,
            warning_sent
        )
        VALUES (
            0, ?, ?, 'ACTIVE', ?, ?, 0
        )
    """, (
        prize,
        ticket,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        ends_at.strftime("%Y-%m-%d %H:%M:%S")
    ))

    auction_id = cur.lastrowid

    conn.commit()
    conn.close()

    return auction_id


# ============================================================
# AUCTION POST + PARTICIPANT HELPERS
# ============================================================

def build_auction_post(auction):
    # User-facing view: show ONLY the combined participant count.
    # Real/Simulation breakdown remains Admin-only.
    real_participants, _ = get_auction_participant_stats(auction["id"])
    simulated_participants = get_auction_simulation_count(auction["id"])
    total_participants = real_participants + simulated_participants

    return (f"🎯 **ጨረታ #{auction['id']}**\n\n"
            f"🏆 ሽልማት: `{float(auction['prize_amount']):.2f}` ብር\n"
            f"🎟 Ticket: `{float(auction['ticket_price']):.2f}` ብር\n"
            f"⏰ የሚያበቃው: `{auction['ends_at']}`\n"
            f"👥 ተሳታፊዎች: `{total_participants}` ሰዎች\n\n"
            f"💡 Bid ከ 1 ብር ጀምሮ ይቻላል።\n"
            f"🏆 Lowest Unique Bid ያሸንፋል።")

def get_user_auction_bids(auction_id, user_id):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT bid_amount FROM bids WHERE auction_id=? AND user_id=? ORDER BY created_at ASC, id ASC", (auction_id, user_id))
    rows = [float(r["bid_amount"]) for r in cur.fetchall()]
    conn.close()
    return rows


async def _send_auction_results_to_participants(bot_application, final_auction):
    participants, bid_count = get_auction_participant_stats(final_auction["id"])
    if final_auction["winner_user_id"]:
        result_text = (f"📢 **የጨረታ ውጤት**\n\nጨረታ #{final_auction['id']} ተጠናቋል።\n"
                       f"🏆 አሸናፊ: {get_winner_name(final_auction['winner_user_id'])}\n"
                       f"🎯 Unique Bid: `{final_auction['winning_bid']}` ብር\n"
                       f"👥 ተሳታፊዎች: `{participants}` ሰዎች\n🎟 ጠቅላላ Bids: `{bid_count}`")
    else:
        result_text = (f"📢 **የጨረታ ውጤት**\n\nጨረታ #{final_auction['id']} ተጠናቋል።\n"
                       f"❌ Unique Bid ስላልተገኘ አሸናፊ የለም።\n"
                       f"👥 ተሳታፊዎች: `{participants}` ሰዎች\n🎟 ጠቅላላ Bids: `{bid_count}`")
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id FROM bids WHERE auction_id=?", (final_auction["id"],))
    user_ids = [int(r["user_id"]) for r in cur.fetchall()]
    conn.close()
    # Telegram Bot API is rate limited. Send only to actual participants and
    # pace the messages instead of scheduling one coroutine per DB user.
    for i, uid in enumerate(user_ids):
        try:
            bids = get_user_auction_bids(final_auction["id"], uid)
            personal = result_text
            if bids:
                personal += f"\n\n🎯 **የእርስዎ Bid-ዎች:** `{', '.join(f'{x:g}' for x in bids)}` ብር\n"
                if final_auction["winner_user_id"] == uid:
                    personal += "🏆 **እርስዎ አሸንፈዋል!**\n💰 ሽልማቱ Wallet ውስጥ ገብቷል።"
                elif final_auction["winner_user_id"]:
                    personal += f"❌ አላሸነፉም።\n🎯 አሸናፊው Unique Bid: `{final_auction['winning_bid']}` ብር"
                else:
                    personal += "❌ Unique Bid ስላልተገኘ አሸናፊ የለም።"
            await bot_application.bot.send_message(chat_id=uid, text=personal, parse_mode="Markdown")
        except Exception as exc:
            logging.warning("Auction result delivery failed for user %s: %s", uid, exc)
        if i + 1 < len(user_ids):
            await asyncio.sleep(0.05)


def get_auction_participant_stats(auction_id):
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT user_id) participants, COUNT(*) bids FROM bids WHERE auction_id=?",(auction_id,))
    r=cur.fetchone(); conn.close(); return int(r['participants'] or 0), int(r['bids'] or 0)


def get_auction_simulation_count(auction_id):
    conn = db(); cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(SUM(simulated_count), 0) AS cnt "
        "FROM auction_simulations WHERE auction_id = ?",
        (auction_id,)
    )
    row = cur.fetchone()
    conn.close()
    return int(row["cnt"] or 0)


def add_auction_simulations(auction_id, count, admin_id):
    conn = db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO auction_simulations (
            auction_id, simulated_count, created_at, created_by
        ) VALUES (?, ?, ?, ?)
    """, (
        auction_id,
        count,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        admin_id
    ))
    conn.commit()
    conn.close()

def save_auction_post(aid, chat_id, message_id):
    conn=db(); cur=conn.cursor(); cur.execute("UPDATE auctions SET post_chat_id=?,post_message_id=? WHERE id=?",(str(chat_id),message_id,aid)); conn.commit(); conn.close()

async def admin_post_auction(update, context):
    q=update.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer(); return
    if not ANNOUNCEMENT_CHANNEL_ID: await q.answer("⚠️ ANNOUNCEMENT_CHANNEL_ID ያስገቡ።",show_alert=True); return
    aid=int(q.data.split(':')[1])
    conn=db(); cur=conn.cursor(); cur.execute("SELECT * FROM auctions WHERE id=?",(aid,)); auc=cur.fetchone(); conn.close()
    try:
        post=await context.bot.send_message(chat_id=ANNOUNCEMENT_CHANNEL_ID,text=build_auction_post(auc),parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ተሳተፍ",callback_data=f"select_auc:{aid}")]]))
        save_auction_post(aid,ANNOUNCEMENT_CHANNEL_ID,post.message_id); await q.answer("✅ Post ተለጥፏል።",show_alert=True)
    except Exception as e: logging.error(f"Post error: {e}"); await q.answer("❌ Post አልተሳካም። Channel ID/Bot Admin ያረጋግጡ።",show_alert=True)
    await admin_manage_auctions(update,context)

async def admin_edit_auction_post(update, context):
    q=update.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer(); return
    aid=int(q.data.split(':')[1])
    conn=db(); cur=conn.cursor(); cur.execute("SELECT * FROM auctions WHERE id=?",(aid,)); auc=cur.fetchone(); conn.close()
    if not auc or not auc['post_chat_id'] or not auc['post_message_id']: await q.answer("❌ Post የለም።",show_alert=True); return
    try:
        await context.bot.edit_message_text(chat_id=auc['post_chat_id'],message_id=auc['post_message_id'],text=build_auction_post(auc),parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ተሳተፍ",callback_data=f"select_auc:{aid}")]])); await q.answer("✅ Post ተስተካክሏል።",show_alert=True)
    except Exception as e: logging.error(f"Edit post error: {e}"); await q.answer("❌ Post ማስተካከል አልተቻለም።",show_alert=True)
    await admin_manage_auctions(update,context)

async def admin_delete_auction_post(update, context):
    q=update.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer(); return
    aid=int(q.data.split(':')[1])
    conn=db(); cur=conn.cursor(); cur.execute("SELECT post_chat_id,post_message_id FROM auctions WHERE id=?",(aid,)); row=cur.fetchone(); conn.close()
    if not row or not row['post_chat_id'] or not row['post_message_id']: await q.answer("❌ Post የለም።",show_alert=True); return
    try:
        await context.bot.delete_message(chat_id=row['post_chat_id'],message_id=row['post_message_id'])
        conn=db(); cur=conn.cursor(); cur.execute("UPDATE auctions SET post_chat_id=NULL,post_message_id=NULL WHERE id=?",(aid,)); conn.commit(); conn.close(); await q.answer("🗑 Post ተሰርዟል።",show_alert=True)
    except Exception as e: logging.error(f"Delete post error: {e}"); await q.answer("❌ Post መሰረዝ አልተቻለም።",show_alert=True)
    await admin_manage_auctions(update,context)

# ============================================================
# USERS
# ============================================================

def register_user(user):
    conn = db()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO users (user_id, first_name, username, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name=excluded.first_name, username=excluded.username, last_seen=excluded.last_seen
    """, (user.id, user.first_name or "", user.username or "", now))
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()

    conn.close()

    return float(row["balance"]) if row else 0.0


# ============================================================
# PAYMENTS
# ============================================================

def create_payment(
    user_id,
    first_name,
    amount,
    photo_file_id
):
    conn = db()
    cur = conn.cursor()

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cur.execute("""
        INSERT INTO payments (
            user_id,
            first_name,
            amount,
            status,
            photo_file_id,
            created_at
        )
        VALUES (?, ?, ?, 'pending', ?, ?)
    """, (
        user_id,
        first_name,
        amount,
        photo_file_id,
        now
    ))

    payment_id = cur.lastrowid

    conn.commit()
    conn.close()

    return payment_id


def approve_payment(payment_id):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        payment = cur.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not payment or payment["status"] != "pending":
            conn.rollback(); conn.close(); return payment, "already_processed"
        if "provider" in payment.keys() and payment["provider"] == "chapa":
            conn.rollback(); conn.close(); return payment, "provider_verification_required"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE payments SET status='approved', approved_at=? WHERE id=? AND status='pending'", (now, payment_id))
        if cur.rowcount != 1:
            conn.rollback(); conn.close(); return payment, "already_processed"
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (payment["amount"], payment["user_id"]))
        if cur.rowcount != 1:
            conn.rollback(); conn.close(); return None, "user_not_found"
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,payment_id,created_at) VALUES(?,?,?,?,?)", (payment["user_id"], payment["amount"], "deposit", payment_id, now))
        try:
            import platform_controls as _pcw
            _pcw.grant_welcome_after_deposit(cur, payment["user_id"], payment["amount"])
        except Exception:
            pass
        _inv = None
        try:
            _inv = release_invite_bonus(cur, payment["user_id"], payment["amount"], now)
        except Exception:
            _inv = None
        conn.commit(); conn.close()
        if _inv and BOT_TOKEN:   # best-effort heads-up to the inviter
            try:
                import requests
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                              json={"chat_id": _inv[0], "text": f"🎉 የጋበዙት ጓደኛ የመጀመሪያ ገንዘብ አስገብቷል! 🎁 +{_inv[1]:g} ብር ቦነስ (ለመጫወት)"}, timeout=5)
            except Exception:
                pass
        return payment, "approved"
    except Exception:
        conn.rollback(); conn.close(); raise


def reject_payment(payment_id):
    """Reject a pending payment exactly once; serialize against approval."""
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        payment = cur.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not payment or payment["status"] != "pending":
            conn.rollback(); conn.close()
            return payment, "already_processed"
        if "provider" in payment.keys() and payment["provider"] == "chapa":
            conn.rollback(); conn.close()
            return payment, "provider_verification_required"
        cur.execute("UPDATE payments SET status='rejected' WHERE id=? AND status='pending'", (payment_id,))
        if cur.rowcount != 1:
            conn.rollback(); conn.close()
            return payment, "already_processed"
        conn.commit(); conn.close()
        return payment, "rejected"
    except Exception:
        conn.rollback(); conn.close()
        raise


# ============================================================
# CLOSE AUCTION + CALCULATE WINNER
# ============================================================

def close_auction(auction_id):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE id = ?
    """, (auction_id,))

    auction = cur.fetchone()

    if not auction:
        conn.close()
        return None

    if auction["status"] == "CLOSED":
        conn.close()
        return auction

    # --------------------------------------------------------
    # Total collected
    # Every bid/ticket pays the auction ticket price
    # --------------------------------------------------------

    cur.execute("""
        SELECT
            COUNT(*) AS bid_count
        FROM bids
        WHERE auction_id = ?
    """, (auction_id,))

    bid_count = cur.fetchone()["bid_count"] or 0

    total_collected = (
        float(bid_count)
        * float(auction["ticket_price"])
    )

    # --------------------------------------------------------
    # Lowest unique bid
    # --------------------------------------------------------

    cur.execute("""
        SELECT
            b.user_id,
            b.bid_amount
        FROM bids b
        WHERE b.auction_id = ?
        AND b.bid_amount IN (
            SELECT bid_amount
            FROM bids
            WHERE auction_id = ?
            GROUP BY bid_amount
            HAVING COUNT(*) = 1
        )
        ORDER BY b.bid_amount ASC
        LIMIT 1
    """, (
        auction_id,
        auction_id
    ))

    winner = cur.fetchone()

    winner_id = None
    winning_bid = None

    if winner:
        winner_id = winner["user_id"]
        winning_bid = winner["bid_amount"]

        # Award prize only once
        cur.execute("""
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ?
        """, (
            auction["prize_amount"],
            winner_id
        ))

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cur.execute("""
            INSERT INTO transactions (
                user_id,
                amount,
                transaction_type,
                created_at
            )
            VALUES (?, ?, 'auction_win', ?)
        """, (
            winner_id,
            auction["prize_amount"],
            now
        ))

    closed_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cur.execute("""
        UPDATE auctions
        SET status = 'CLOSED',
            winner_user_id = ?,
            winning_bid = ?,
            total_collected = ?,
            closed_at = ?
        WHERE id = ?
    """, (
        winner_id,
        winning_bid,
        total_collected,
        closed_at,
        auction_id
    ))

    conn.commit()

    # Get final auction
    cur.execute("""
        SELECT *
        FROM auctions
        WHERE id = ?
    """, (auction_id,))

    final_auction = cur.fetchone()

    conn.close()

    return final_auction


def get_winner_name(user_id):
    if not user_id:
        return "አሸናፊ የለም"

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT first_name, username
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    row = cur.fetchone()

    conn.close()

    if not row:
        return str(user_id)

    if row["username"]:
        return (
            f"{row['first_name']} "
            f"(@{row['username']})"
        )

    return row["first_name"] or str(user_id)


# ============================================================
# SEND AUCTION RESULT
# ============================================================

def send_auction_result(bot_application, auction):
    auction_id = auction["id"]

    winner_id = auction["winner_user_id"]
    winning_bid = auction["winning_bid"]
    prize = float(auction["prize_amount"])
    collected = float(
        auction["total_collected"] or 0
    )

    winner_name = get_winner_name(
        winner_id
    )

    # --------------------------------------------------------
    # Admin result
    # --------------------------------------------------------

    if winner_id:
        winner_text = (
            f"🏆 አሸናፊ: {winner_name}\n"
            f"🆔 User ID: `{winner_id}`\n"
            f"🎯 Unique Bid: `{winning_bid}` ብር"
        )
    else:
        winner_text = (
            "🏆 አሸናፊ: የለም\n"
            "🎯 Unique Bid: የለም"
        )

    profit = collected - prize

    admin_text = (
        f"🏁 **የጨረታ ውጤት**\n\n"
        f"📌 Auction ID: `#{auction_id}`\n"
        f"{winner_text}\n"
        f"💰 ሽልማት: `{prize:.2f}` ብር\n"
        f"💵 ከተሳታፊዎች የተሰበሰበ: "
        f"`{collected:.2f}` ብር\n"
        f"📊 ልዩነት: `{profit:.2f}` ብር\n"
        f"📅 የተዘጋበት: `{auction['closed_at']}`"
    )

    try:
        _schedule_bot_coro(
            bot_application,
            bot_application.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                parse_mode="Markdown"
            ),
        )
    except Exception as e:
        logging.error(
            f"Admin result error: {e}"
        )

    # --------------------------------------------------------
    # Winner notification
    # --------------------------------------------------------

    if winner_id:

        try:
            _schedule_bot_coro(
            bot_application,
            bot_application.bot.send_message(
                    chat_id=winner_id,
                    text=(
                        f"🎉 **እንኳን ደስ አለዎት!**\n\n"
                        f"🏆 ጨረታ #{auction_id}\n"
                        f"🎯 Unique Bid: "
                        f"`{winning_bid}` ብር\n"
                        f"💰 ሽልማት: "
                        f"`{prize:.2f}` ብር\n\n"
                        f"ሽልማቱ ወደ Walletዎ ገብቷል።"
                    ),
                    parse_mode="Markdown"
                ),
                )
        except Exception as e:
            logging.error(
                f"Winner notification error: {e}"
            )


# ============================================================
# AUTOMATIC AUCTION CHECKER
# ============================================================

def check_and_close_auctions(bot_application):

    conn = db()
    cur = conn.cursor()

    now = datetime.now()

    # --------------------------------------------------------
    # One-hour warning
    # --------------------------------------------------------

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE status = 'ACTIVE'
        AND warning_sent = 0
    """)

    active_auctions = cur.fetchall()

    for auc in active_auctions:

        try:
            ends_dt = datetime.strptime(
                auc["ends_at"],
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            continue

        remaining_seconds = (
            ends_dt - now
        ).total_seconds()

        if 0 < remaining_seconds <= 3600:

            cur.execute("""
                UPDATE auctions
                SET warning_sent = 1
                WHERE id = ?
            """, (auc["id"],))

            conn.commit()

            cur.execute("""
                SELECT DISTINCT user_id
                FROM bids
                WHERE auction_id = ?
            """, (auc["id"],))

            bidders = cur.fetchall()

            for b in bidders:

                try:
                    _schedule_bot_coro(
                                bot_application,
                                bot_application.bot.send_message(
                            chat_id=b["user_id"],
                            text=(
                                f"⚠️ **ማስታወሻ**\n\n"
                                f"ጨረታ #{auc['id']} "
                                f"በ1 ሰዓት ውስጥ ይጠናቀቃል።\n"
                                f"💰 ሽልማት: "
                                f"`{auc['prize_amount']}` ብር"
                            ),
                            parse_mode="Markdown"
                        ),
                                )
                except Exception as e:
                    logging.error(
                        f"Warning error: {e}"
                    )

    # --------------------------------------------------------
    # Expired auctions
    # --------------------------------------------------------

    now_str = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE status = 'ACTIVE'
        AND ends_at <= ?
    """, (now_str,))

    expired = cur.fetchall()

    conn.close()

    for auc in expired:

        try:

            final_auction = close_auction(
                auc["id"]
            )

            if final_auction:
                send_auction_result(
                    bot_application,
                    final_auction
                )

                # Notify only real auction participants, paced below Telegram
                # rate limits. Never broadcast a private auction result to every user.
                try:
                    _schedule_bot_coro(
                        bot_application,
                        _send_auction_results_to_participants(bot_application, final_auction)
                    )
                except Exception as e:
                    logging.error(f"Auction result scheduling error: {e}")

            # ------------------------------------------------
            # Create automatic next auction only if there is
            # no active auction
            # ------------------------------------------------

            conn3 = db()
            cur3 = conn3.cursor()

            cur3.execute("""
                SELECT COUNT(*) AS cnt
                FROM auctions
                WHERE status = 'ACTIVE'
            """)

            active_count = cur3.fetchone()["cnt"]

            # No automatic next auction. Admin creates the next one manually.

            conn3.close()

        except Exception as e:

            logging.error(
                f"Auction closing error: {e}"
            )


# ============================================================
# HOURLY ADMIN REPORT
# ============================================================

def send_hourly_admin_report(bot_application):

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM users"
    )

    total_users = cur.fetchone()["cnt"]

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE status = 'ACTIVE'
        ORDER BY id DESC
        LIMIT 1
    """)

    active_auc = cur.fetchone()

    active_users = 0
    total_ticket_money = 0.0

    if active_auc:

        cur.execute("""
            SELECT
                COUNT(DISTINCT user_id) AS users_cnt,
                COUNT(*) AS bid_count
            FROM bids
            WHERE auction_id = ?
        """, (active_auc["id"],))

        info = cur.fetchone()

        active_users = (
            info["users_cnt"] or 0
        )

        bid_count = info["bid_count"] or 0

        total_ticket_money = (
            bid_count
            * float(active_auc["ticket_price"])
        )

    cur.execute(
        "SELECT SUM(balance) AS total_bal FROM users"
    )

    total_balance = (
        cur.fetchone()["total_bal"] or 0
    )

    conn.close()

    text = (
        f"📊 **የሰዓት ሪፖርት**\n\n"
        f"👥 Users: `{total_users}`\n"
        f"🏃 Active participants: `{active_users}`\n"
        f"🎟 የተሰበሰበ Ticket: "
        f"`{total_ticket_money:.2f}` ብር\n"
        f"💳 Total Wallet: "
        f"`{total_balance:.2f}` ብር\n"
        f"🎯 Active Auction: "
        f"`#{active_auc['id'] if active_auc else 'N/A'}`"
    )

    try:
        _schedule_bot_coro(
            bot_application,
            bot_application.bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                parse_mode="Markdown"
            ),
        )
    except Exception as e:
        logging.error(
            f"Hourly report error: {e}"
        )



# ============================================================
# BACKUP
# ============================================================
# Database backups are handled by the dedicated backup_db.py container/service.
# Do not schedule DB-file uploads from the bot process.


# ============================================================
# TELEGRAM MINI APP BACKEND
# ============================================================

def _mini_json(data, status=200):
    return web.json_response(data, status=status, dumps=lambda x: json.dumps(x, ensure_ascii=False))


def validate_mini_app_init_data(init_data: str):
    """Validate Telegram.WebApp.initData before trusting user identity."""
    if not init_data:
        raise web.HTTPUnauthorized(text="Missing Telegram initData")
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise web.HTTPUnauthorized(text="Invalid initData")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise web.HTTPUnauthorized(text="Missing initData hash")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise web.HTTPUnauthorized(text="Invalid initData signature")

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        raise web.HTTPUnauthorized(text="Invalid auth_date")
    if auth_date <= 0 or time.time() - auth_date > MINI_APP_MAX_AUTH_AGE:
        raise web.HTTPUnauthorized(text="Expired initData")

    try:
        tg_user = json.loads(parsed["user"])
    except Exception:
        raise web.HTTPUnauthorized(text="Invalid Telegram user data")
    if not tg_user.get("id"):
        raise web.HTTPUnauthorized(text="Telegram user id missing")
    return tg_user


# Only these frontend files are public (source/.env/DB must never be reachable over HTTP).
MINI_PUBLIC_ASSETS = {
    "/app.js": "application/javascript; charset=utf-8",
    "/kdm_fix.js": "application/javascript; charset=utf-8",
    "/kdm_betpro.css": "text/css; charset=utf-8",
    "/kdm_betpro.js": "application/javascript; charset=utf-8",
    "/kdm_neon.css": "text/css; charset=utf-8",
    "/megaplay_theme.css": "text/css; charset=utf-8",
    "/kdm_neon.js": "application/javascript; charset=utf-8",
    "/rewards.js": "application/javascript; charset=utf-8",
    "/kdm_skin_skymasters.js": "application/javascript; charset=utf-8",
    "/kdm_skin_highflyer.js": "application/javascript; charset=utf-8",
    "/kdm_skin_crash.js": "application/javascript; charset=utf-8",
    "/kdm_skin_aviator.js": "application/javascript; charset=utf-8",
    "/kdm_skin_jet.js": "application/javascript; charset=utf-8",
    "/kdm_covers.js": "application/javascript; charset=utf-8",
    "/kdm_fix.css": "text/css; charset=utf-8",
    "/premium.js": "application/javascript; charset=utf-8",
    "/engagement.js": "application/javascript; charset=utf-8",
    "/game_stage.js": "application/javascript; charset=utf-8",
    "/style.css": "text/css; charset=utf-8",
    "/premium.css": "text/css; charset=utf-8",
    "/engagement.css": "text/css; charset=utf-8",
    "/visual_refresh.css": "text/css; charset=utf-8",
    "/onboarding.js": "application/javascript; charset=utf-8",
    "/onboarding.css": "text/css; charset=utf-8",
    "/road_game.js": "application/javascript; charset=utf-8",
    "/road_game.css": "text/css; charset=utf-8",
    "/new_games.js": "application/javascript; charset=utf-8",
    "/new_games.css": "text/css; charset=utf-8",
    "/kdm_design.css": "text/css; charset=utf-8",
    "/kdm_ui.js": "application/javascript; charset=utf-8",
    "/kdm_art.js": "application/javascript; charset=utf-8",
    "/game_catalog.js": "application/javascript; charset=utf-8",
    "/game_help.js": "application/javascript; charset=utf-8",
    "/game_fx.js": "application/javascript; charset=utf-8",
    "/cards_ui.js": "application/javascript; charset=utf-8",
    "/coin_dice_ui.js": "application/javascript; charset=utf-8",
    "/kdm_ingame.css": "text/css; charset=utf-8",
    "/kdm_ingame.js": "application/javascript; charset=utf-8",
    "/kdm_aviator.js": "application/javascript; charset=utf-8",
    "/kdm_highflyer_live.js": "application/javascript; charset=utf-8",
    "/kdm_skymasters_live.js": "application/javascript; charset=utf-8",
    "/kdm_mines.js": "application/javascript; charset=utf-8",
    "/kdm_plinko.js": "application/javascript; charset=utf-8",
    "/kdm_keno.js": "application/javascript; charset=utf-8",
    "/kdm_triplegold.js": "application/javascript; charset=utf-8",
    "/kdm_flame.js": "application/javascript; charset=utf-8",
    "/kdm_aztec.js": "application/javascript; charset=utf-8",
    "/kdm_buffalo.js": "application/javascript; charset=utf-8",
    "/kdm_rabbit.js": "application/javascript; charset=utf-8",
    "/kdm_penalty.js": "application/javascript; charset=utf-8",
    "/kdm_chicken.js": "application/javascript; charset=utf-8",
    "/kdm_blackjack.js": "application/javascript; charset=utf-8",
    "/kdm_baccarat.js": "application/javascript; charset=utf-8",
    "/kdm_roulette.js": "application/javascript; charset=utf-8",
    "/kdm_wheel.js": "application/javascript; charset=utf-8",
    "/kdm_fish.js": "application/javascript; charset=utf-8",
    "/kdm_bingo.js": "application/javascript; charset=utf-8",
    "/kdm_fastkeno.js": "application/javascript; charset=utf-8",
    "/kdm_superkeno_live.js": "application/javascript; charset=utf-8",
    "/kdm_slot.js": "application/javascript; charset=utf-8",
    "/kdm_number.js": "application/javascript; charset=utf-8",
    "/kdm_number.css": "text/css; charset=utf-8",
    "/kdm_keno_live.js": "application/javascript; charset=utf-8",
    "/kdm_live_crash.js": "application/javascript; charset=utf-8",
    "/kdm_roast.js": "application/javascript; charset=utf-8",
    "/kdm_chicken2.js": "application/javascript; charset=utf-8",
    "/kdm_boom.js": "application/javascript; charset=utf-8",
    "/kdm_jet.js": "application/javascript; charset=utf-8",
    "/kdm_rocket.js": "application/javascript; charset=utf-8",
    "/kdm_sports.js": "application/javascript; charset=utf-8",
    "/kdm_slot.css": "text/css; charset=utf-8",
    "/kdm_bingo.css": "text/css; charset=utf-8",
    "/kdm_fastkeno.css": "text/css; charset=utf-8",
    "/kdm_boom.css": "text/css; charset=utf-8",
    "/kdm_jet.css": "text/css; charset=utf-8",
    "/kdm_rocket.css": "text/css; charset=utf-8",
    "/kdm_triplegold.css": "text/css; charset=utf-8",
    "/kdm_flame.css": "text/css; charset=utf-8",
    "/kdm_aztec.css": "text/css; charset=utf-8",
}


@web.middleware
async def mini_auth_middleware(request, handler):
    if request.path in ("/health", "/", "/index.html") or request.path in MINI_PUBLIC_ASSETS:
        return await handler(request)
    if request.path.startswith("/assets/"):
        return await handler(request)
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    tg_user = validate_mini_app_init_data(init_data)
    request["tg_user"] = tg_user
    register_mini_user(tg_user)
    return await handler(request)


def register_mini_user(tg_user):
    conn = db()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO users (user_id, first_name, username, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name=excluded.first_name,
            username=excluded.username,
            last_seen=excluded.last_seen
    """, (
        int(tg_user["id"]),
        tg_user.get("first_name", ""),
        tg_user.get("username", ""),
        now,
    ))
    conn.commit()
    conn.close()


def mini_user_id(request):
    return int(request["tg_user"]["id"])


def mini_user_is_staff(request):
    return is_staff(mini_user_id(request))


def mini_auction_dict(row):
    participants, bids = get_auction_participant_stats(row["id"])
    simulated = get_auction_simulation_count(row["id"])
    return {
        "id": row["id"],
        "prize": float(row["prize_amount"]),
        "ticket_price": float(row["ticket_price"]),
        "ends_at": row["ends_at"],
        "participants": participants + simulated,
        "real_participants": participants,
        "bids": bids,
        "status": row["status"],
        "tier_level": int(row["tier_level"] or 0),
    }


async def mini_index(request):
    path = os.path.join(MINI_APP_DIR, "index.html")
    if not os.path.exists(path):
        raise web.HTTPNotFound(text="miniapp/index.html not found")
    return web.FileResponse(path, headers={"Cache-Control": "no-cache"})


async def mini_health(request):
    return _mini_json({"ok": True, "service": "King Bet"})


async def mini_me(request):
    uid = mini_user_id(request)
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT user_id, first_name, username, balance, manager FROM users WHERE user_id=?", (uid,))
    user = cur.fetchone()
    conn.close()
    return _mini_json({
        "user": dict(user) if user else {"user_id": uid},
        "is_admin": is_admin(uid),
        "is_staff": is_staff(uid),
    })


async def mini_auctions(request):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM auctions WHERE status='ACTIVE' ORDER BY id DESC")
    rows = cur.fetchall(); conn.close()
    return _mini_json({"auctions": [mini_auction_dict(r) for r in rows]})


async def mini_bid(request):
    try:
        payload = await request.json()
        auction_id = int(payload.get("auction_id"))
        bid_amount = float(payload.get("bid_amount"))
    except Exception:
        return _mini_json({"ok": False, "error": "Invalid bid data"}, 400)

    uid = mini_user_id(request)
    if bid_amount < 1 or round(bid_amount, 2) != bid_amount:
        return _mini_json({"ok": False, "error": "Bid ቢያንስ 1 ብር እና እስከ 2 decimal ብቻ ነው።"}, 400)

    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM auctions WHERE id=? AND status='ACTIVE'", (auction_id,))
        auction = cur.fetchone()
        if not auction:
            return _mini_json({"ok": False, "error": "ጨረታው ተዘግቷል።"}, 404)
        ticket = float(auction["ticket_price"])
        cur.execute("BEGIN")
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (ticket, uid, ticket))
        if cur.rowcount != 1:
            conn.rollback()
            return _mini_json({"ok": False, "error": "Wallet በቂ አይደለም።", "ticket_price": ticket}, 400)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO bids(auction_id,user_id,bid_amount,created_at) VALUES(?,?,?,?)", (auction_id, uid, bid_amount, now))
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (uid, -ticket, "auction_ticket", now))
        conn.commit()
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        balance = float(cur.fetchone()["balance"])
    except Exception as e:
        conn.rollback()
        logging.exception("Mini App bid error")
        return _mini_json({"ok": False, "error": "Bid ሲመዘገብ ችግኝ ተፈጥሯል።"}, 500)
    finally:
        conn.close()

    # Keep the existing public Telegram auction post updated.
    try:
        conn2 = db(); cur2 = conn2.cursor(); cur2.execute("SELECT * FROM auctions WHERE id=?", (auction_id,)); updated = cur2.fetchone(); conn2.close()
        if updated and updated["post_chat_id"] and updated["post_message_id"]:
            await request.app["ptb_app"].bot.edit_message_text(
                chat_id=updated["post_chat_id"],
                message_id=updated["post_message_id"],
                text=build_auction_post(updated),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ተሳተፍ", callback_data=f"select_auc:{auction_id}")]]),
            )
    except Exception as e:
        logging.warning(f"Mini bid auction post refresh failed: {e}")

    return _mini_json({"ok": True, "balance": balance, "message": "Bid ተመዝግቧል።"})


async def mini_history(request):
    uid = mini_user_id(request)
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT amount, transaction_type, created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,))
    rows = [dict(r) for r in cur.fetchall()]; conn.close()
    return _mini_json({"history": rows})


async def mini_deposit(request):
    try:
        reader = await request.multipart()
        amount = None
        photo_bytes = None
        filename = "payment.jpg"
        async for part in reader:
            if part.name == "amount":
                amount = float((await part.text()).strip())
            elif part.name == "screenshot":
                filename = part.filename or filename
                photo_bytes = await part.read()
        if amount is None or amount <= 0 or not photo_bytes:
            return _mini_json({"ok": False, "error": "Amount እና Screenshot ያስገቡ።"}, 400)
    except Exception:
        return _mini_json({"ok": False, "error": "Invalid deposit request"}, 400)

    uid = mini_user_id(request)
    tg_user = request["tg_user"]
    app = request.app["ptb_app"]
    conn = db(); cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO payments(user_id,first_name,amount,status,photo_file_id,created_at) VALUES(?,?,?,'pending',?,?)", (uid, tg_user.get("first_name", ""), amount, "", now))
    payment_id = cur.lastrowid
    conn.commit(); conn.close()

    try:
        sent = await app.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=BytesIO(photo_bytes),
            caption=(f"📥 **Payment Request — Mini App**\n\n👤 {tg_user.get('first_name','N/A')}\n🆔 `{uid}`\n💰 `{amount:.2f}` ብር\n🆔 Payment: `{payment_id}`"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{payment_id}")],
                [InlineKeyboardButton("❌ REJECT", callback_data=f"reject:{payment_id}")],
            ]),
        )
        file_id = sent.photo[-1].file_id if sent.photo else ""
        conn = db(); cur = conn.cursor(); cur.execute("UPDATE payments SET photo_file_id=? WHERE id=?", (file_id, payment_id)); conn.commit(); conn.close()
    except Exception as e:
        logging.exception("Mini App deposit admin delivery error")
        conn = db(); cur = conn.cursor(); cur.execute("DELETE FROM payments WHERE id=?", (payment_id,)); conn.commit(); conn.close()
        return _mini_json({"ok": False, "error": "Screenshot ወደ Admin መላክ አልተቻለም።"}, 500)

    return _mini_json({"ok": True, "payment_id": payment_id, "message": "Screenshot ተልኳል። Admin ካረጋገጠው Wallet ይጨምራል።"})


async def mini_withdraw(request):
    try:
        payload = await request.json()
        amount = float(payload.get("amount"))
        acc_name = str(payload.get("acc_name", "")).strip()
        acc_number = str(payload.get("acc_number", "")).strip()
    except Exception:
        return _mini_json({"ok": False, "error": "Invalid withdrawal data"}, 400)
    if amount <= 0 or not acc_name or not acc_number:
        return _mini_json({"ok": False, "error": "Amount, Account Name እና Account Number ያስገቡ።"}, 400)

    uid = mini_user_id(request)
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        _b, _lk, _can = _withdrawable(cur, uid)
        if _lk > 0 and amount > _can + 0.001:
            conn.rollback(); return _mini_json({"ok": False, "error": f"🎁 Bonus ({_lk:.2f} ብር) ለመጫወት ብቻ ነው -- ማውጣት የሚችሉት {_can:.2f} ብር ነው"}, 400)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (amount, uid, amount))
        if cur.rowcount != 1:
            conn.rollback(); return _mini_json({"ok": False, "error": "Wallet በቂ አይደለም።"}, 400)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO withdrawals(user_id,amount,acc_name,acc_number,status,created_at) VALUES(?,?,?,?,'pending',?)", (uid, amount, acc_name, acc_number, now))
        withdrawal_id = cur.lastrowid
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (uid, -amount, "withdraw", now))
        conn.commit()
    except Exception:
        conn.rollback(); logging.exception("Mini withdrawal error")
        return _mini_json({"ok": False, "error": "Withdrawal ሲመዘገብ ችግኝ ተፈጥሯል።"}, 500)
    finally:
        conn.close()

    await request.app["ptb_app"].bot.send_message(
        chat_id=ADMIN_ID,
        text=(f"💸 <b>Withdrawal Request — Mini App</b>\n\n🆔 User: <code>{uid}</code>\n💰 <code>{amount:.2f}</code> ብር\n👤 Account: <code>{html.escape(acc_name)}</code>\n📱/🏦 Number: <code>{html.escape(acc_number)}</code>\n🆔 Withdrawal: <code>{withdrawal_id}</code>"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ APPROVE", callback_data=f"w_approve:{withdrawal_id}")],
            [InlineKeyboardButton("❌ REJECT", callback_data=f"w_reject:{withdrawal_id}")],
        ]),
    )
    return _mini_json({"ok": True, "withdrawal_id": withdrawal_id, "message": "Withdrawal Request ተልኳል።"})


async def mini_support(request):
    try:
        reader = await request.multipart()
        text = ""
        photo_bytes = None
        filename = "support.jpg"
        async for part in reader:
            if part.name == "text":
                text = (await part.text()).strip()
            elif part.name == "photo":
                filename = part.filename or filename
                photo_bytes = await part.read()
    except Exception:
        return _mini_json({"ok": False, "error": "Invalid support request"}, 400)

    if not text and not photo_bytes:
        return _mini_json({"ok": False, "error": "Message ወይም Photo ያስገቡ።"}, 400)

    uid = mini_user_id(request); tg_user = request["tg_user"]; app = request.app["ptb_app"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"📩 **Player Support — Mini App**\n\n👤 {tg_user.get('first_name','N/A')}\n🆔 `{uid}`\n🔗 @{tg_user.get('username','N/A')}\n🕒 `{now}`\n\n"
    try:
        if photo_bytes:
            msg = await app.bot.send_photo(chat_id=ADMIN_ID, photo=BytesIO(photo_bytes), caption=prefix + (text or "📸 Photo ተልኳል።"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Reply to Player", callback_data=f"support_reply:{uid}")]]))
            content_type = "photo"
        else:
            msg = await app.bot.send_message(chat_id=ADMIN_ID, text=prefix + text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Reply to Player", callback_data=f"support_reply:{uid}")]]))
            content_type = "text"
        conn=db(); cur=conn.cursor(); cur.execute("INSERT OR REPLACE INTO support_messages(admin_message_id,user_id,created_at,direction,content_type) VALUES(?,?,?,?,?)", (msg.message_id, uid, now, "user_to_admin", content_type)); conn.commit(); conn.close()
    except Exception:
        logging.exception("Mini support delivery error")
        return _mini_json({"ok": False, "error": "Support መልዕክቱን መላክ አልተቻለም።"}, 500)
    return _mini_json({"ok": True, "message": "መልዕክትዎ Admin ጋር ደርሷል።"})


async def mini_aviator_state(request):
    uid = mini_user_id(request)
    rid = AVIATOR_STATE.get("round_id")
    b = AVIATOR_STATE.get("player_bets", {}).get(uid)
    return _mini_json({
        "round_id": rid,
        "phase": AVIATOR_STATE.get("phase"),
        "multiplier": aviator_current_multiplier() if AVIATOR_STATE.get("phase") == "flying" else (float(AVIATOR_STATE.get("crash", 1.0)) if AVIATOR_STATE.get("phase") == "crashed" else 1.0),
        "crash": float(AVIATOR_STATE.get("crash", 1.0)),
        "players": int(AVIATOR_STATE.get("total_players", 0)),
        "total_bets": float(AVIATOR_STATE.get("total_bets", 0)),
        "total_payout": float(AVIATOR_STATE.get("total_payout", 0)),
        "cashed_out": int(AVIATOR_STATE.get("cashed_out_count", 0)),
        "my_bet": b,
        "balance": get_balance(uid),
    })


async def mini_aviator_bet(request):
    try:
        amount = float((await request.json()).get("amount"))
    except Exception:
        return _mini_json({"ok": False, "error": "Invalid amount"}, 400)
    uid = mini_user_id(request); rid = AVIATOR_STATE.get("round_id")
    if AVIATOR_STATE.get("phase") != "betting" or not rid:
        return _mini_json({"ok": False, "error": "አሁን Bet መጫን አይቻልም።"}, 400)
    if amount <= 0:
        return _mini_json({"ok": False, "error": "Bet ከ0 በላይ ይሁን።"}, 400)

    conn=db(); cur=conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)); row=cur.fetchone(); balance=float(row["balance"] or 0) if row else 0
        if balance < amount:
            conn.rollback(); return _mini_json({"ok": False, "error": "Wallet በቂ አይደለም።", "balance": balance}, 400)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (amount, uid, amount))
        if cur.rowcount != 1:
            conn.rollback(); return _mini_json({"ok": False, "error": "Wallet በቂ አይደለም።"}, 400)
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO aviator_bets(round_id,user_id,bet_amount,status,created_at) VALUES(?,?,?,'placed',?)", (rid,uid,amount,now))
        bet_id=cur.lastrowid
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (uid,-amount,"aviator_bet",now))
        conn.commit()
    except Exception:
        conn.rollback(); logging.exception("Mini Aviator bet error")
        return _mini_json({"ok": False, "error": "Aviator Bet ሲመዘገብ ችግኝ ተፈጥሯል።"}, 500)
    finally: conn.close()

    AVIATOR_STATE.setdefault("player_bets", {})[uid] = {"bet_id": int(bet_id), "bet_amount": float(amount), "status": "placed", "cashout_multiplier": None, "payout": 0.0, "name": request["tg_user"].get("first_name") or str(uid)}
    AVIATOR_STATE["total_players"] = len(AVIATOR_STATE["player_bets"])
    AVIATOR_STATE["total_bets"] = float(AVIATOR_STATE.get("total_bets",0)) + amount
    return _mini_json({"ok": True, "bet_id": int(bet_id), "balance": get_balance(uid)})


async def mini_aviator_cashout(request):
    try:
        payload = await request.json(); rid=int(payload.get("round_id")); bet_id=int(payload.get("bet_id"))
    except Exception:
        return _mini_json({"ok": False, "error": "Invalid cashout data"}, 400)
    uid=mini_user_id(request)
    if AVIATOR_STATE.get("round_id") != rid or AVIATOR_STATE.get("phase") != "flying":
        return _mini_json({"ok": False, "error": "ይህ round አልነቃም።"}, 400)
    multiplier=aviator_current_multiplier()
    if multiplier >= float(AVIATOR_STATE.get("crash", 1.0)):
        return _mini_json({"ok": False, "error": "💥 Crash ሆኗል።"}, 400)
    conn=db(); cur=conn.cursor()
    try:
        cur.execute("SELECT * FROM aviator_bets WHERE bet_id=? AND round_id=? AND user_id=? AND status='placed'", (bet_id,rid,uid)); bet=cur.fetchone()
        if not bet:
            return _mini_json({"ok": False, "error": "ንቁ Bet የለዎትም።"}, 404)
        payout=round(float(bet["bet_amount"])*multiplier,2); now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE aviator_bets SET status='cashed_out',cashout_multiplier=?,payout=? WHERE bet_id=? AND status='placed'", (multiplier,payout,bet_id))
        if cur.rowcount != 1:
            conn.rollback(); return _mini_json({"ok": False, "error": "Bet ቀድሞ ተሰርቷል።"}, 409)
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (payout,uid))
        cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (uid,payout,"aviator_win",now))
        conn.commit()
    except Exception:
        conn.rollback(); logging.exception("Mini Aviator cashout error")
        return _mini_json({"ok": False, "error": "Cash Out አልተሳካም።"}, 500)
    finally: conn.close()
    cached=AVIATOR_STATE.setdefault("player_bets",{}).get(uid)
    if cached:
        cached.update({"status":"cashed_out","cashout_multiplier":float(multiplier),"payout":float(payout)})
    AVIATOR_STATE["total_payout"]=float(AVIATOR_STATE.get("total_payout",0))+payout
    AVIATOR_STATE["cashed_out_count"]=int(AVIATOR_STATE.get("cashed_out_count",0))+1
    return _mini_json({"ok": True, "payout": payout, "multiplier": multiplier, "balance": get_balance(uid)})


async def mini_admin_summary(request):
    if not mini_user_is_staff(request):
        raise web.HTTPForbidden(text="Staff only")
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT COUNT(*) cnt, COALESCE(SUM(balance),0) wallet FROM users"); users=cur.fetchone()
    cur.execute("SELECT COUNT(*) cnt FROM auctions WHERE status='ACTIVE'"); active=cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) cnt FROM aviator_rounds WHERE status='crashed'"); rounds=cur.fetchone()["cnt"]
    cur.execute("SELECT COALESCE(SUM(bet_amount),0) bets, COALESCE(SUM(payout),0) payouts FROM aviator_bets"); av=cur.fetchone()
    conn.close()
    return _mini_json({"users":users["cnt"],"wallet":float(users["wallet"]),"active_auctions":active,"aviator_rounds":rounds,"aviator_bets":float(av["bets"]),"aviator_payouts":float(av["payouts"]),"settings":EXTRA_GAME_SETTINGS})


async def mini_app_server_start(application):
    if not os.path.isdir(MINI_APP_DIR):
        logging.warning("Mini App directory missing: %s", MINI_APP_DIR)
        return
    app = web.Application(middlewares=[mini_auth_middleware])
    app["ptb_app"] = application
    app.router.add_get("/", mini_index)
    app.router.add_get("/index.html", mini_index)
    app.router.add_get("/health", mini_health)

    async def _mini_root_asset(request):
        content_type = MINI_PUBLIC_ASSETS.get(request.path)
        if not content_type:
            raise web.HTTPNotFound()
        filename = request.path.lstrip("/")
        path = os.path.join(MINI_APP_DIR, filename)
        if not os.path.isfile(path):
            raise web.HTTPNotFound(text=f"Mini App asset not found: {filename}")
        return web.FileResponse(path, headers={"Content-Type": content_type, "Cache-Control": "no-cache"})

    # Never expose MINI_APP_DIR as a directory. Only the known frontend files in
    # MINI_PUBLIC_ASSETS are public.
    for _asset_path in MINI_PUBLIC_ASSETS:
        app.router.add_get(_asset_path, _mini_root_asset)
    # No legacy /api/* handlers here. webapp_api.py is the single HTTP API owner.

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()
    application.bot_data["mini_runner"] = runner
    logging.info("Telegram Mini App server listening on %s:%s", WEBAPP_HOST, WEBAPP_PORT)


async def mini_app_server_stop(application):
    runner = application.bot_data.pop("mini_runner", None)
    if runner:
        await runner.cleanup()


# ============================================================
# MAIN MENU — TELEGRAM MINI APP
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Deep-link payload: /start ref_<inviter id>  (invite link)  or  /start g_<game>  (post / channel link)
    start_arg = (context.args[0] if getattr(context, "args", None) else "").strip()
    _conn = db(); _cur = _conn.cursor()
    _cur.execute("SELECT 1 FROM users WHERE user_id=?", (user.id,)); _is_new = _cur.fetchone() is None
    _conn.close()
    register_user(user)
    if _is_new and start_arg.startswith("ref_") and start_arg[4:].isdigit():
        inviter = int(start_arg[4:])
        if inviter != user.id:
            try:
                _conn = db(); _cur = _conn.cursor()
                if record_invite(_cur, inviter, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
                    _conn.commit()
                    try:   # tell the inviter
                        _c2 = db(); _k2 = _c2.cursor(); _def = invite_requires_deposit(_k2); _c2.close()
                        await context.bot.send_message(inviter, (f"🎉 አዲስ ጓደኛ ተቀላቅሏል! 🎁 +{INVITE_BONUS_ETB:g} ብር ቦነስ ጓደኛዎ የመጀመሪያ ገንዘብ ሲያስገባ ይከፈላል።" if _def
                                                                 else f"🎉 አዲስ ጓደኛ ተቀላቅሏል! 🎁 +{INVITE_BONUS_ETB:g} ብር ቦነስ (ለመጫወት)"))
                    except Exception:
                        pass
                _conn.close()
            except Exception as e:
                logging.warning(f"referral save failed: {e}")
    start_game = start_arg[2:] if start_arg.startswith("g_") and PROMO_KEY_RE.match(start_arg[2:] or "-") else ""

    # Reset temporary conversation state without discarding a valid Admin PIN
    # session. /start and the "main" callback both call this handler; clearing
    # all user_data here previously erased admin_pin_verified_until and forced
    # staff back to the ordinary user flow after PIN verification.
    pin_verified_until = float(
        context.user_data.get("admin_pin_verified_until", 0) or 0
    )
    context.user_data.clear()
    if pin_verified_until > time.time():
        context.user_data["admin_pin_verified_until"] = pin_verified_until

    # Reply keyboard Web App button: the old chat menu is no longer shown.
    web_button = KeyboardButton(
        "King Bet 🥳",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )
    markup = ReplyKeyboardMarkup(
        [[web_button]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )

    balance = get_balance(user.id)
    text = (
        f"ሰላም {user.first_name or 'ተጠቃሚ'}! 👋\n\n"
        "King Bet 🥳 ወደ Telegram Mini App ተቀይሯል።\n\n"
        f"💰 Wallet: {balance:.2f} ብር\n\n"
        "ከታች ያለውን «King Bet 🥳» ይጫኑ።"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)
        if start_arg:
            # Invite / post link: one tap opens the Mini App (on the chosen game when the link names one).
            game_url = WEBAPP_URL + ((("&" if "?" in WEBAPP_URL else "?") + "game=" + start_game) if start_game and start_game != "lobby" else "")
            if WEBAPP_URL.startswith("https://"):
                await update.message.reply_text(
                    "👇 ለመጫወት ይጫኑ",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("King Bet 🥳", web_app=WebAppInfo(url=game_url))]]),
                )

# ============================================================
# PLAYER <-> ADMIN SUPPORT
# ============================================================

async def support_start(update, context):
    q = update.callback_query
    await q.answer()
    if is_staff(q.from_user.id):
        return
    context.user_data.clear()
    context.user_data["waiting_support_message"] = True
    await q.edit_message_text(
        "📩 **Admin / Support**\n\n"
        "ለAdmin መልዕክት ይላኩ።\n"
        "✍️ Text ወይም 📸 Photo መላክ ይችላሉ።\n\n"
        "❌ ለመሰረዝ /cancel ይጻፉ።",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ዋና ማውጫ", callback_data="main")]])
    )

async def send_support_to_admin(update, context, photo_id=None, text=None):
    user = update.effective_user
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = text or (update.message.caption or "")
    prefix = (
        "📩 **Player Support**\n\n"
        f"👤 {user.first_name or 'N/A'}\n"
        f"🆔 `{user.id}`\n"
        f"🔗 @{user.username if user.username else 'N/A'}\n"
        f"🕒 `{now}`\n\n"
    )
    try:
        if photo_id:
            msg = await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo_id,
                caption=prefix + (body if body else "📸 Photo ተልኳል።"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Reply to Player", callback_data=f"support_reply:{user.id}")]])
            )
            content_type = "photo"
        else:
            msg = await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=prefix + (body or ""),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Reply to Player", callback_data=f"support_reply:{user.id}")]])
            )
            content_type = "text"
        conn = db(); cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO support_messages(admin_message_id,user_id,created_at,direction,content_type) VALUES(?,?,?,?,?)", (msg.message_id, user.id, now, "user_to_admin", content_type))
        conn.commit(); conn.close()
        context.user_data.clear()
        await update.message.reply_text("✅ መልዕክትዎ Admin ጋር ደርሷል። ምላሽ ሲመጣ በዚህ Telegram ይደርስዎታል።")
    except Exception as e:
        logging.error(f"Support delivery error: {e}")
        await update.message.reply_text("❌ መልዕክቱን Admin ጋር መላክ አልተቻለም።")

async def support_reply_start(update, context, user_id):
    q = update.callback_query
    await q.answer()
    if not is_staff(q.from_user.id):
        return
    context.user_data.clear()
    context.user_data["support_reply_user_id"] = int(user_id)
    await q.message.reply_text(
        f"↩️ User `{user_id}` ላይ ምላሽ ለመላክ Text ወይም Photo ይላኩ።\n\n❌ /cancel",
        parse_mode="Markdown"
    )

async def send_admin_support_reply(update, context, photo_id=None, text=None):
    if not is_staff(update.effective_user.id):
        return False
    user_id = int(context.user_data.get("support_reply_user_id"))
    try:
        if photo_id:
            await context.bot.send_photo(chat_id=user_id, photo=photo_id, caption=text or "📩 Admin ምላሽ", parse_mode="Markdown")
            content_type = "photo"
        else:
            await context.bot.send_message(chat_id=user_id, text="📩 **Admin ምላሽ**\n\n" + (text or ""), parse_mode="Markdown")
            content_type = "text"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn=db(); cur=conn.cursor()
        cur.execute("INSERT INTO support_messages(admin_message_id,user_id,created_at,direction,content_type) VALUES(?,?,?,?,?)", (-int(datetime.now().timestamp()*1000000), user_id, now, "admin_to_user", content_type))
        conn.commit(); conn.close()
        context.user_data.pop("support_reply_user_id", None)
        await update.message.reply_text(f"✅ ምላሽ ለUser `{user_id}` ተልኳል።", parse_mode="Markdown")
        return True
    except Exception as e:
        logging.error(f"Admin support reply error: {e}")
        await update.message.reply_text("❌ ምላሽ መላክ አልተቻለም።")
        return True

# ============================================================
# ADMIN PANEL
# ============================================================

async def admin_panel_handler(update, context):

    query = update.callback_query

    await query.answer()

    if not is_staff(query.from_user.id):
        return

    text = (
        "👑 **አድሚን / Manager ፓነል**\n\n"
        "የሚፈልጉትን ይምረጡ።"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "➕ አዲስ ጨረታ መፍጠር",
                callback_data="admin_create_auction"
            )
        ],

        [
            InlineKeyboardButton(
                "🎯 ንቁ ጨረታዎች",
                callback_data="admin_manage_auctions"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 የተጠናቀቁ ጨረታዎች",
                callback_data="admin_results"
            )
        ],
        [InlineKeyboardButton("👥 Users / Bot ተጠቃሚዎች", callback_data="admin_users:0")],

        [
            InlineKeyboardButton(
                "🏃‍♂️ ንቁ ተጫዋቾች እና ዋጋዎች",
                callback_data="admin_active_players"
            )
        ],

        [InlineKeyboardButton("📊 ጠቅላላ Users / Wallet", callback_data="admin_total_wallets")],

        [InlineKeyboardButton("🎮 Game Settings", callback_data="admin_game_settings")],

        [InlineKeyboardButton("✈️ Aviator Statistics", callback_data="aviator_admin_stats")],

        [InlineKeyboardButton("📢 ማስታወቂያ Post ላክ", callback_data="admin_announcement")],

        [InlineKeyboardButton("📩 Support Messages", callback_data="support_inbox")],

        *([[InlineKeyboardButton("👥 Manager አስተዳደር", callback_data="admin_managers")]] if is_admin(query.from_user.id) else []),

        [
            InlineKeyboardButton(
                "🔙 ዋና ማውጫ",
                callback_data="main"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# ADMIN ANNOUNCEMENT / POST
# ============================================================

MAX_HOME_BANNERS = 5

async def save_announcement_as_banner(context, photo_id, link_page=""):
    """A PHOTO announcement is also shown in the Mini App home carousel (newest 5 kept). Shares the
    `banners` table + banners/ folder (same data volume) with the API's engagement_v8.py."""
    try:
        tg_file = await context.bot.get_file(photo_id)
        data = bytes(await tg_file.download_as_bytearray())
        ext = "png" if data.startswith(b"\x89PNG") else ("webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else "jpg")
        folder = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)) or ".", "banners")
        os.makedirs(folder, exist_ok=True)
        name = f"{secrets.token_hex(16)}.{ext}"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
        conn = db(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, link_page TEXT,
            seconds INTEGER NOT NULL DEFAULT 4, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)""")
        cur.execute("INSERT INTO banners(filename,link_page,seconds,active,created_at) VALUES (?,?,?,1,?)",
                    (name, (link_page or "")[:30], 4, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cur.execute("SELECT id, filename FROM banners WHERE active=1 ORDER BY id DESC")
        for r in cur.fetchall()[MAX_HOME_BANNERS:]:
            cur.execute("UPDATE banners SET active=0 WHERE id=?", (r["id"],))
            try: os.remove(os.path.join(folder, os.path.basename(r["filename"])))
            except OSError: pass
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logging.warning(f"Could not save announcement photo as home banner: {e}")
        return False

async def send_admin_announcement(update, context, message_text=None, photo_id=None, video_id=None, animation_id=None, caption=None):
    """Broadcast text/photo/GIF/video with a Play Now URL button to users and optional channel."""
    banner_saved = await save_announcement_as_banner(context, photo_id) if photo_id else False
    conn=db(); cur=conn.cursor(); cur.execute("SELECT user_id FROM users WHERE banned=0"); users=cur.fetchall(); conn.close()
    delivered=failed=0; caption=(caption or "").strip()
    body = caption or (message_text or "").strip() or "🎮 ወደ ጨዋታዎቻችን ይግቡ!"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Now", url=WEBAPP_URL)]]) if WEBAPP_URL.startswith("https://") else None

    async def send_one(chat_id):
        prefix = "📢 ማስታወቂያ\n\n"
        if animation_id:
            return await context.bot.send_animation(chat_id=chat_id, animation=animation_id, caption=prefix+body, reply_markup=keyboard)
        if photo_id:
            return await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=prefix+body, reply_markup=keyboard)
        if video_id:
            return await context.bot.send_video(chat_id=chat_id, video=video_id, caption=prefix+body, reply_markup=keyboard)
        return await context.bot.send_message(chat_id=chat_id, text=prefix+body, reply_markup=keyboard)

    # Publish to configured announcement channel as well as the user list.
    if ANNOUNCEMENT_CHANNEL_ID:
        try:
            await send_one(ANNOUNCEMENT_CHANNEL_ID)
        except Exception as e:
            failed += 1
            logging.warning(f"Announcement channel delivery failed: {e}")
    for u in users:
        try:
            await send_one(u["user_id"])
            delivered += 1
        except Exception as e:
            failed += 1
            logging.warning(f"Announcement delivery failed for {u['user_id']}: {e}")
    await update.message.reply_text(
        f"📢 ማስታወቂያ ተልኳል\n\n👥 ተጠቃሚዎች: {len(users)}\n✅ Delivered: {delivered}\n❌ Failed: {failed}"
        + ("\n🖼 App ላይ banner ሆኖ ተለጥፏል" if banner_saved else "")
        + ("\n🎮 Play Now ቁልፍ ተጨምሯል።" if keyboard else "\n⚠️ MINI_APP_URL/WEBAPP_URL HTTPS አልተዋቀረም።"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 አድሚን ፓነል",callback_data="admin_panel")]])
    )




# ============================================================
# PROMO POST BUILDER
#   Admin/Manager: 1) picks the game the post opens  2) sends text / photo / video / GIF (Telegram formatting is kept:
#   bold, quote, emoji ...)  3) sees an exact PREVIEW  4) optionally adds extra buttons / vote buttons  5) publishes to
#   the channel and/or every user. Voting buttons (e.g. Liverpool / Arsenal) count one vote per person and show the totals.
# ============================================================
import re as _re
from telegram.error import RetryAfter, Forbidden, BadRequest, TelegramError

PROMO_SPECIAL = [("lobby", "🏠 ሎቢ (ሁሉም ጨዋታዎች)"), ("sports", "⚽ Sports"), ("marketplace", "🛍 Marketplace"), ("wheel", "🎡 Lucky Spin")]
PROMO_GAMES = [
    ("aviator", "✈️ Aviator"), ("crash", "📈 Crash"), ("rocket", "🚀 Rocket"), ("highflyer", "🛩️ High Flyer"),
    ("skymasters", "🛫 Sky Masters"), ("jet", "🚀 Jet"), ("keno", "🎯 Keno"), ("fastkeno", "⚡ Fast Keno"),
    ("keno_power", "🎱 Power Keno"), ("keno_super", "🟢 Super Keno"), ("keno_insta", "💎 Insta Keno"), ("mines", "💣 Mines"),
    ("boom", "💣 Boom"), ("number", "🔢 Number"), ("dice2", "🎲 Dice"), ("plinko", "🟣 Plinko"),
    ("roulette", "🎡 Roulette"), ("bingo", "🎱 Bingo"), ("slot", "🎰 777 Slot"), ("triplegold", "🔔 Triple Gold"),
    ("triplegold_deluxe", "🔔 Triple Gold Deluxe"), ("flame", "🔥 Flame Classics"), ("aztec", "🗿 Aztec Gold"),
    ("buffalo", "🦬 Buffalo Plains"), ("chicken", "🐔 Chicken Road"), ("chicken2", "🐔 Chicken Road 2"),
    ("rabbit", "🐇 Rabbit Road"), ("roast", "🔥 Chicken Roast"), ("tower", "🏗 Tower"), ("fish", "🐟 Fish"),
    ("penalty", "⚽ Penalty Shootout"), ("penaltystreak", "⚽ Penalty Streak"), ("coinstreak", "🪙 Coin Flip"),
    ("blackjack", "🃏 Blackjack"), ("baccarat", "🎴 Baccarat"), ("dragontiger", "🐉 Dragon Tiger"),
    ("andarbahar", "🃏 Andar Bahar"), ("card", "🃏 Card Table"),
]
PROMO_LABELS = dict(PROMO_SPECIAL + PROMO_GAMES)
PROMO_PAGE_SIZE = 12
PROMO_CAPTION_MAX = 1024
PROMO_TEXT_MAX = 4096
PROMO_MAX_EXTRA = 8
PROMO_KEY_RE = _re.compile(r"^[a-z0-9_]{1,40}$")


def promo_init_tables():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS promo_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_by INTEGER, created_at TEXT, game TEXT, buttons_json TEXT, audience TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promo_votes (
        post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, choice INTEGER NOT NULL, created_at TEXT,
        PRIMARY KEY (post_id, user_id))""")
    conn.commit(); conn.close()


def promo_bot_username(context=None):
    name = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
    if not name and context is not None:
        try: name = (context.bot.username or "").lstrip("@")
        except Exception: name = ""
    return name


def promo_open_button(text, key, private, bot_username):
    """Button that opens the Mini App on a given game. In a private chat it is a real Mini App button (so the player is
    logged in); in a channel Telegram only allows link buttons, so it is a t.me ?startapp= link."""
    key = (key or "").strip()
    if key in ("", "none"):
        return None
    if key == "lobby":
        key = ""
    if private and WEBAPP_URL.startswith("https://"):
        url = WEBAPP_URL + ((("&" if "?" in WEBAPP_URL else "?") + "game=" + key) if key else "")
        return InlineKeyboardButton(text, web_app=WebAppInfo(url=url))
    if bot_username:
        short = os.getenv("MINI_APP_SHORT_NAME", "").strip().strip("/")
        base = f"https://t.me/{bot_username}" + (f"/{short}" if short else "")
        return InlineKeyboardButton(text, url=f"{base}?startapp=g_{key or 'lobby'}")
    if WEBAPP_URL.startswith("https://"):
        return InlineKeyboardButton(text, url=WEBAPP_URL + ((("&" if "?" in WEBAPP_URL else "?") + "game=" + key) if key else ""))
    return None


def promo_keyboard(promo, post_id, private, bot_username, counts=None):
    """Main game button on top, vote buttons (2 per row, with totals once counts is a dict), then extra buttons."""
    rows = []
    main = promo_open_button(promo.get("btn_text") or "▶️ አሁን ይጫወቱ", promo.get("game"), private, bot_username)
    if main: rows.append([main])
    votes, others, vi = [], [], 0
    for e in promo.get("extra") or []:
        if e.get("t") == "vote":
            label = e["text"] + (f" ({int((counts or {}).get(vi, 0))})" if counts is not None else "")
            votes.append(InlineKeyboardButton(label, callback_data=f"pv:{int(post_id)}:{vi}")); vi += 1
        elif e.get("t") == "game":
            b = promo_open_button(e["text"], e.get("v"), private, bot_username)
            if b: others.append([b])
        elif e.get("t") == "url":
            others.append([InlineKeyboardButton(e["text"], url=e["v"])])
    for i in range(0, len(votes), 2): rows.append(votes[i:i + 2])
    rows += others
    return InlineKeyboardMarkup(rows) if rows else None


def promo_parse_buttons(text):
    """One button per line:  Text | vote   or   Text | game:keno   or   Text | https://link"""
    out, errors = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line: continue
        if "|" not in line:
            errors.append(f"«{line[:30]}» -- `ጽሑፍ | vote` ወይም `ጽሑፍ | game:keno` ወይም `ጽሑፍ | https://...` ይጠቀሙ"); continue
        label, target = [x.strip() for x in line.split("|", 1)]
        if not label or len(label) > 32:
            errors.append(f"«{label[:30]}» -- የቁልፍ ጽሑፍ 1-32 ፊደል መሆን አለበት"); continue
        low = target.lower()
        if low == "vote": out.append({"t": "vote", "text": label})
        elif low.startswith("game:"):
            key = low[5:].strip()
            if key in PROMO_LABELS or PROMO_KEY_RE.match(key): out.append({"t": "game", "text": label, "v": key})
            else: errors.append(f"«{label}» -- የጨዋታ ስም ትክክል አይደለም")
        elif low.startswith("https://"): out.append({"t": "url", "text": label, "v": target})
        else: errors.append(f"«{label}» -- ከ vote / game:ስም / https://... አንዱን ብቻ ይጠቀሙ")
    if len(out) > PROMO_MAX_EXTRA:
        errors.append(f"ከ{PROMO_MAX_EXTRA} በላይ ቁልፍ አይፈቀድም"); out = out[:PROMO_MAX_EXTRA]
    return out, errors


def promo_picker_markup(page=0):
    items = PROMO_SPECIAL + PROMO_GAMES
    pages = max(1, (len(items) + PROMO_PAGE_SIZE - 1) // PROMO_PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    chunk = items[page * PROMO_PAGE_SIZE:(page + 1) * PROMO_PAGE_SIZE]
    rows = []
    for i in range(0, len(chunk), 2):
        rows.append([InlineKeyboardButton(l, callback_data=f"ap_g:{k}") for k, l in chunk[i:i + 2]])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"ap_pg:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="ap_noop"))
    if page < pages - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"ap_pg:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🚫 ቁልፍ አይኑር (ጽሑፍ/ፎቶ ብቻ)", callback_data="ap_g:none")])
    rows.append([InlineKeyboardButton("❌ ሰርዝ", callback_data="ap_cancel")])
    return InlineKeyboardMarkup(rows)


PROMO_PICK_TEXT = ("📢 Post ማስታወቂያ\n\n1️⃣ ይህ Post የሚከፍተውን ጨዋታ ይምረጡ።\n"
                   "ተጫዋቹ የ «አሁን ይጫወቱ» ቁልፉን ሲነካ Mini App በቀጥታ በዚያ ጨዋታ ላይ ይከፈታል።")


async def admin_announcement(update, context):
    q = update.callback_query; await q.answer()
    if not is_staff(q.from_user.id): return
    context.user_data.clear()
    await q.edit_message_text(PROMO_PICK_TEXT, reply_markup=promo_picker_markup(0))


async def promo_send_one(bot, chat_id, promo, kb):
    kind = promo.get("kind", "text"); h = promo.get("html") or ""
    if kind == "photo":
        return await bot.send_photo(chat_id=chat_id, photo=promo["file_id"], caption=h or None, parse_mode="HTML", reply_markup=kb)
    if kind == "video":
        return await bot.send_video(chat_id=chat_id, video=promo["file_id"], caption=h or None, parse_mode="HTML", reply_markup=kb)
    if kind == "animation":
        return await bot.send_animation(chat_id=chat_id, animation=promo["file_id"], caption=h or None, parse_mode="HTML", reply_markup=kb)
    return await bot.send_message(chat_id=chat_id, text=h or "🎮", parse_mode="HTML", reply_markup=kb)


async def promo_show_preview(message, context):
    promo = context.user_data.get("promo") or {}
    bu = promo_bot_username(context)
    try:
        await promo_send_one(context.bot, message.chat_id, promo, promo_keyboard(promo, 0, True, bu))
    except Exception as e:
        await message.reply_text(f"❌ ቅድመ እይታ አልተሳካም: {e}\nጽሑፉን እንደገና ይላኩ።"); return
    conn = db(); cur = conn.cursor(); cur.execute("SELECT COUNT(*) c FROM users WHERE banned=0"); n_users = cur.fetchone()["c"]; conn.close()
    game = promo.get("game") or "none"
    label = "ቁልፍ የለም" if game == "none" else PROMO_LABELS.get(game, game)
    extra = promo.get("extra") or []
    lines = ["👆 ይህ ነው የሚላከው (ቅድመ እይታ)።", "", f"🎮 የሚከፈት ጨዋታ: {label}",
             f"🔘 ተጨማሪ ቁልፎች: {len(extra)}" + (f" (ድምጽ: {sum(1 for e in extra if e['t'] == 'vote')})" if extra else ""),
             f"👥 Users: {n_users}", "📣 Channel: " + (f"✅ {ANNOUNCEMENT_CHANNEL_ID}" if ANNOUNCEMENT_CHANNEL_ID else "⚠️ ANNOUNCEMENT_CHANNEL_ID አልተዋቀረም"),
             "", "ሌላ ጽሑፍ/ፎቶ ቢልኩ ይህን ይተካል።"]
    rows = []
    if ANNOUNCEMENT_CHANNEL_ID:
        rows.append([InlineKeyboardButton("✅ ለሁሉም ላክ (Users + Channel)", callback_data="ap_send:all")])
        rows.append([InlineKeyboardButton("📣 Channel ብቻ", callback_data="ap_send:ch"), InlineKeyboardButton("👥 Users ብቻ", callback_data="ap_send:us")])
    else:
        rows.append([InlineKeyboardButton("✅ ለሁሉም Users ላክ", callback_data="ap_send:us")])
    rows.append([InlineKeyboardButton("➕ ተጨማሪ ቁልፎች / ድምጽ", callback_data="ap_btns"), InlineKeyboardButton("🎮 ጨዋታ ቀይር", callback_data="ap_game")])
    rows.append([InlineKeyboardButton("❌ ሰርዝ", callback_data="ap_cancel")])
    await message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


async def promo_content_received(update, context, kind, file_id=None):
    """Called from the text / photo / video / GIF handlers while an admin is building a post."""
    msg = update.message
    promo = context.user_data.setdefault("promo", {"game": "lobby", "extra": []})
    plain = (msg.text if kind == "text" else msg.caption) or ""
    html_text = (msg.text_html if kind == "text" else msg.caption_html) or ""
    limit = PROMO_TEXT_MAX if kind == "text" else PROMO_CAPTION_MAX
    if len(plain) > limit:
        await msg.reply_text(f"❌ ጽሑፉ በጣም ረጅም ነው ({len(plain)}). ከፍተኛው {limit} ፊደል ነው -- አሳጥረው ይላኩ።"); return
    if kind == "text" and not plain.strip():
        await msg.reply_text("❌ ባዶ ጽሑፍ ነው።"); return
    promo.update({"kind": kind, "file_id": file_id, "html": html_text, "wait_buttons": False})
    await promo_show_preview(msg, context)


async def promo_buttons_received(update, context):
    promo = context.user_data.get("promo") or {}
    out, errors = promo_parse_buttons(update.message.text or "")
    if errors:
        await update.message.reply_text("⚠️ እነዚህ መስመሮች አልተቀበሉም:\n" + "\n".join("• " + x for x in errors) + "\n\nእንደገና ይላኩ ወይም /cancel።"); return
    promo["extra"] = out; promo["wait_buttons"] = False
    await promo_show_preview(update.message, context)


def promo_counts(post_id):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT choice, COUNT(*) c FROM promo_votes WHERE post_id=? GROUP BY choice", (int(post_id),))
    d = {int(r["choice"]): int(r["c"]) for r in cur.fetchall()}; conn.close()
    return d


async def promo_vote(update, context):
    q = update.callback_query
    try:
        _, pid, idx = (q.data or "").split(":"); pid = int(pid); idx = int(idx)
    except Exception:
        await q.answer(); return
    if pid == 0:
        await q.answer("👀 ይህ ቅድመ እይታ ነው -- ድምጽ አይቆጠርም", show_alert=False); return
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT game, buttons_json FROM promo_posts WHERE id=?", (pid,)); row = cur.fetchone()
    if not row:
        conn.close(); await q.answer("Post አልተገኘም", show_alert=True); return
    extra = json.loads(row["buttons_json"] or "[]")
    n_votes = sum(1 for e in extra if e.get("t") == "vote")
    if idx < 0 or idx >= n_votes:
        conn.close(); await q.answer(); return
    cur.execute("""INSERT INTO promo_votes(post_id,user_id,choice,created_at) VALUES(?,?,?,?)
                   ON CONFLICT(post_id,user_id) DO UPDATE SET choice=excluded.choice, created_at=excluded.created_at""",
                (pid, q.from_user.id, idx, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()
    names = [e["text"] for e in extra if e.get("t") == "vote"]
    await q.answer(f"✅ ድምጽዎ ተመዝግቧል: {names[idx]}")
    try:
        private = (q.message.chat.type == "private") if q.message else True
        await q.edit_message_reply_markup(reply_markup=promo_keyboard({"game": row["game"], "extra": extra}, pid, private, promo_bot_username(context), promo_counts(pid)))
    except BadRequest:
        pass   # "message is not modified" (same totals) -- harmless
    except Exception as e:
        logging.warning(f"promo vote markup update failed: {e}")


async def promo_broadcast(application, admin_chat_id, promo, audience, post_id):
    bot = application.bot; bu = os.getenv("BOT_USERNAME", "").strip().lstrip("@") or (bot.username or "")
    sent = blocked = failed = 0; ch_status = "—"
    banner_saved = False
    if audience in ("all", "ch") and ANNOUNCEMENT_CHANNEL_ID:
        try:
            await promo_send_one(bot, ANNOUNCEMENT_CHANNEL_ID, promo, promo_keyboard(promo, post_id, False, bu))
            ch_status = "✅ ተልኳል"
        except Exception as e:
            ch_status = f"❌ {e}"; logging.warning(f"promo channel delivery failed: {e}")
    if audience in ("all", "us"):
        conn = db(); cur = conn.cursor(); cur.execute("SELECT user_id FROM users WHERE banned=0"); users = [r["user_id"] for r in cur.fetchall()]; conn.close()
        kb = promo_keyboard(promo, post_id, True, bu)
        for uid in users:
            for attempt in (1, 2):
                try:
                    await promo_send_one(bot, uid, promo, kb); sent += 1; break
                except RetryAfter as e:
                    await asyncio.sleep(float(e.retry_after) + 1)
                except Forbidden:
                    blocked += 1; break
                except Exception as e:
                    failed += 1; logging.warning(f"promo delivery failed for {uid}: {e}"); break
            await asyncio.sleep(0.05)     # stay far below Telegram's 30 messages / second limit
    if promo.get("kind") == "photo" and promo.get("file_id"):
        link = promo.get("game") if promo.get("game") not in (None, "none") else ""
        class _Ctx: pass
        _c = _Ctx(); _c.bot = bot
        banner_saved = await save_announcement_as_banner(_c, promo["file_id"], link_page=(link or "")[:30])
    summary = ["📢 Post ተጠናቀቀ", ""]
    if audience in ("all", "ch"): summary.append(f"📣 Channel: {ch_status}")
    if audience in ("all", "us"): summary.append(f"👥 ተልኳል: {sent}   🚫 Bot ያገዱ: {blocked}   ❌ አልተሳካም: {failed}")
    if banner_saved: summary.append("🖼 App ላይ banner ሆኖ ተለጥፏል")
    if any(e.get("t") == "vote" for e in promo.get("extra") or []): summary.append("🗳 ድምጽ ቁልፎች ንቁ ናቸው -- ጠቅላላ ድምጽ በቁልፉ ላይ ይታያል")
    try:
        await bot.send_message(admin_chat_id, "\n".join(summary), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 አድሚን ፓነል", callback_data="admin_panel")]]))
    except Exception:
        pass


async def promo_callback(update, context):
    q = update.callback_query; data = q.data or ""
    if data.startswith("pv:"):
        await promo_vote(update, context); return
    if not is_staff(q.from_user.id):
        await q.answer("⛔ ለAdmin / Manager ብቻ", show_alert=True); return
    if data == "ap_noop":
        await q.answer(); return
    if data.startswith("ap_pg:"):
        await q.answer()
        try: await q.edit_message_reply_markup(reply_markup=promo_picker_markup(int(data.split(":")[1])))
        except Exception: pass
        return
    if data == "ap_cancel":
        context.user_data.clear(); await q.answer("ተሰርዟል")
        try: await q.edit_message_text("❌ ማስታወቂያው ተሰርዟል።", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 አድሚን ፓነል", callback_data="admin_panel")]]))
        except Exception: pass
        return
    if data.startswith("ap_g:"):
        key = data.split(":", 1)[1]
        if key != "none" and key not in PROMO_LABELS:
            await q.answer("ያልታወቀ ጨዋታ", show_alert=True); return
        promo = context.user_data.setdefault("promo", {"game": "lobby", "extra": []})
        promo["game"] = key; context.user_data["waiting_admin_announcement"] = True
        label = "ቁልፍ አይኖርም" if key == "none" else PROMO_LABELS.get(key, key)
        await q.answer()
        if promo.get("kind"):
            await promo_show_preview(q.message, context); return
        try:
            await q.edit_message_text(
                f"✅ ጨዋታ: {label}\n\n2️⃣ አሁን Post ይላኩ:\n• ✍️ ጽሑፍ  • 📸 ፎቶ  • 🎥 ቪዲዮ  • GIF\n"
                "ፎቶ/ቪዲዮ ከሆነ ጽሑፉን Caption ላይ ይጻፉ። Bold፣ Quote፣ Emoji ሁሉ እንዳለ ይቀራል።\n\n"
                "ከመላክዎ በፊት ቅድመ እይታ ያያሉ። ለመሰረዝ /cancel",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 ጨዋታ ቀይር", callback_data="ap_game"), InlineKeyboardButton("❌ ሰርዝ", callback_data="ap_cancel")]]))
        except Exception:
            pass
        return
    if data == "ap_game":
        await q.answer()
        context.user_data.setdefault("promo", {"game": "lobby", "extra": []})["wait_buttons"] = False
        await q.message.reply_text(PROMO_PICK_TEXT, reply_markup=promo_picker_markup(0)); return
    if data == "ap_btns":
        promo = context.user_data.get("promo")
        if not promo or not promo.get("kind"):
            await q.answer("መጀመሪያ Post ይላኩ", show_alert=True); return
        promo["wait_buttons"] = True; context.user_data["waiting_admin_announcement"] = True
        await q.answer()
        await q.message.reply_text(
            "➕ ተጨማሪ ቁልፎች -- አንድ መስመር = አንድ ቁልፍ:\n\n"
            "🗳 ድምጽ ቁልፍ:\n  ሊቨርፑል | vote\n  አርሰናል | vote\n\n"
            "🎮 ሌላ ጨዋታ የሚከፍት:\n  Keno ተጫወት | game:keno\n\n"
            "🔗 ሊንክ:\n  Channel | https://t.me/yourchannel\n\n"
            f"(ከፍተኛ {PROMO_MAX_EXTRA} ቁልፍ።) ሁሉንም ቁልፎች ለማጥፋት clear ብለው ይጻፉ።  ለመሰረዝ /cancel")
        return
    if data.startswith("ap_send:"):
        promo = context.user_data.get("promo")
        if not promo or not promo.get("kind"):
            await q.answer("Post የለም ወይም ተልኳል", show_alert=True); return
        audience = data.split(":", 1)[1]
        if audience not in ("all", "ch", "us"): await q.answer(); return
        snap = {k: promo.get(k) for k in ("kind", "file_id", "html", "game", "extra", "btn_text")}
        snap["extra"] = list(snap.get("extra") or [])
        promo_init_tables()
        conn = db(); cur = conn.cursor()
        cur.execute("INSERT INTO promo_posts(created_by,created_at,game,buttons_json,audience) VALUES (?,?,?,?,?)",
                    (q.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), snap.get("game") or "none", json.dumps(snap["extra"], ensure_ascii=False), audience))
        post_id = cur.lastrowid; conn.commit(); conn.close()
        context.user_data.clear()
        await q.answer("⏳ እየተላከ ነው...")
        try: await q.edit_message_text("⏳ Post እየተላከ ነው... ሲጨርስ ሪፖርት ይደርስዎታል (ብዙ users ካሉ ጥቂት ደቂቃ ሊወስድ ይችላል)።")
        except Exception: pass
        context.application.create_task(promo_broadcast(context.application, q.message.chat_id, snap, audience, post_id))
        return
    await q.answer()




# ============================================================
# ADMIN CREATE AUCTION - STEP 1
# ============================================================

async def admin_create_auction(update, context):

    query = update.callback_query

    await query.answer()

    if not is_staff(query.from_user.id):
        return

    context.user_data.clear()

    context.user_data[
        "admin_create_auction"
    ] = True

    context.user_data[
        "waiting_admin_prize"
    ] = True

    await query.edit_message_text(
        "➕ **አዲስ ጨረታ መፍጠር**\n\n"
        "ደረጃ 1/4\n\n"
        "💰 የሽልማት ብር ያስገቡ።\n"
        "ለምሳሌ፦ `5000`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ ሰርዝ",
                    callback_data="admin_panel"
                )
            ]
        ])
    )


# ============================================================
# ADMIN ACTIVE PLAYERS
# ============================================================

async def admin_active_players(update, context):

    query = update.callback_query

    await query.answer()

    if not is_staff(query.from_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            b.user_id,
            u.first_name,
            b.auction_id,
            b.bid_amount,
            b.created_at
        FROM bids b
        JOIN users u
            ON b.user_id = u.user_id
        JOIN auctions a
            ON b.auction_id = a.id
        WHERE a.status = 'ACTIVE'
        ORDER BY b.created_at DESC
    """)

    rows = cur.fetchall()

    conn.close()

    text = (
        "🏃‍♂️ **ንቁ ተጫዋቾች እና Bid**\n\n"
    )

    if not rows:

        text += "አሁን በንቁ ጨረታ ላይ ተሳታፊ የለም።"

    else:

        for r in rows:

            text += (
                f"👤 {r['first_name']}\n"
                f"🆔 `{r['user_id']}`\n"
                f"🎯 Auction #{r['auction_id']}\n"
                f"💰 `{r['bid_amount']}` ብር\n"
                f"📅 {r['created_at']}\n"
                f"────────────\n"
            )

    keyboard = [[
        InlineKeyboardButton(
            "🔙 አድሚን ፓነል",
            callback_data="admin_panel"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# ADMIN -> MANAGER MANAGEMENT
# ============================================================

async def admin_managers(update, context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT user_id,first_name,username FROM users WHERE manager=1 ORDER BY first_name")
    rows=cur.fetchall(); conn.close()
    text="👥 **Manager አስተዳደር**\n\n"
    if rows:
        for r in rows:
            text += f"🛡 {r['first_name'] or 'N/A'}  |  `{r['user_id']}`  |  @{r['username'] if r['username'] else 'N/A'}\n"
    else:
        text += "ምንም Manager የለም።\n"
    text += "\n📌 Manager ለመመደብ Users ውስጥ ይግቡ።"
    kb=[[InlineKeyboardButton("👥 Users ክፈት",callback_data="admin_users:0")],[InlineKeyboardButton("🔙 አድሚን ፓነል",callback_data="admin_panel")]]
    await q.edit_message_text(text,parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(kb))

async def set_manager(update, context, user_id, enabled):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    if int(user_id)==ADMIN_ID:
        await q.answer("❌ ዋና Admin ሊቀየር አይችልም።",show_alert=True); return
    conn=db(); cur=conn.cursor(); cur.execute("SELECT first_name FROM users WHERE user_id=?",(int(user_id),)); row=cur.fetchone()
    if not row:
        conn.close(); await q.answer("❌ User አልተገኘም።",show_alert=True); return
    cur.execute("UPDATE users SET manager=? WHERE user_id=?",(1 if enabled else 0,int(user_id))); conn.commit(); conn.close()
    await q.answer("✅ Manager ሆኗል።" if enabled else "✅ Manager ተወግዷል፣")
    await admin_users(update, context)

# ============================================================
# ADMIN USERS
# ============================================================

async def admin_users(update, context):
    q=update.callback_query; await q.answer()
    if not is_staff(q.from_user.id): return
    try: page=max(0,int(q.data.split(':')[1]))
    except: page=0
    per=15
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT COUNT(*) cnt FROM users")
    total=int(cur.fetchone()['cnt'] or 0)
    cur.execute("SELECT user_id,first_name,username,balance,last_seen,manager FROM users ORDER BY last_seen DESC,user_id DESC LIMIT ? OFFSET ?",(per,page*per))
    rows=cur.fetchall(); conn.close()
    text=f"👥 **የBot Users**\n\n📊 ጠቅላላ Users: `{total}`\n\n"
    kb=[]
    for r in rows:
        un=f"@{r['username']}" if r['username'] else "የለም"
        role="👑 ADMIN" if int(r['user_id'])==ADMIN_ID else ("🛡 MANAGER" if r['manager'] else "👤 USER")
        text+=f"{role}\n👤 {r['first_name'] or 'N/A'}\n🆔 `{r['user_id']}`\n🔗 {un}\n💰 Wallet: `{float(r['balance'] or 0):.2f}` ብር\n🕒 Last seen: `{r['last_seen'] or 'N/A'}`\n────────────\n"
        kb.append([InlineKeyboardButton(f"📜 Activity: {r['first_name'] or r['user_id']}", callback_data=f"admin_user_activity:{r['user_id']}")])
        if is_admin(q.from_user.id) and int(r['user_id']) != ADMIN_ID:
            if r['manager']:
                kb.append([InlineKeyboardButton(f"⬇️ Manager አስወግድ: {r['first_name'] or r['user_id']}", callback_data=f"manager_remove:{r['user_id']}")])
            else:
                kb.append([InlineKeyboardButton(f"🛡 Manager አድርግ: {r['first_name'] or r['user_id']}", callback_data=f"manager_add:{r['user_id']}")])
    if page>0: kb.append([InlineKeyboardButton("⬅️ ቀዳሚ",callback_data=f"admin_users:{page-1}")])
    if (page+1)*per<total: kb.append([InlineKeyboardButton("ቀጣይ ➡️",callback_data=f"admin_users:{page+1}")])
    kb.append([InlineKeyboardButton("🔙 አድሚን / Manager ፓነል",callback_data="admin_panel")])
    await q.edit_message_text(text,parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(kb))


async def admin_user_activity(update, context, user_id):
    q=update.callback_query; await q.answer()
    if not is_staff(q.from_user.id): return
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT first_name,username,balance,last_seen FROM users WHERE user_id=?", (int(user_id),)); u=cur.fetchone()
    if not u:
        conn.close(); await q.answer("User አልተገኘም።", show_alert=True); return
    cur.execute("SELECT amount,transaction_type,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 30", (int(user_id),)); tx=cur.fetchall()
    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(bet_amount),0) total FROM aviator_bets WHERE user_id=?", (int(user_id),)); bets=cur.fetchone()
    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(payout),0) payout FROM aviator_bets WHERE user_id=? AND status='cashed_out'", (int(user_id),)); wins=cur.fetchone()
    cur.execute("SELECT COUNT(*) c, COALESCE(SUM(bet_amount),0) amount FROM aviator_bets WHERE user_id=? AND status='lost'", (int(user_id),)); losses=cur.fetchone()
    conn.close()
    lines=[f"📊 **Player Activity**",f"👤 {u['first_name'] or 'N/A'}",f"🆔 `{user_id}`",f"💰 Wallet: `{float(u['balance'] or 0):.2f}` ብር",f"🕒 Last seen: `{u['last_seen'] or 'N/A'}`","",f"✈️ Bets: `{bets['c']}` | Amount: `{float(bets['total'] or 0):.2f}`",f"🏆 Wins: `{wins['c']}` | Payout: `{float(wins['payout'] or 0):.2f}`",f"❌ Losses: `{losses['c']}` | Amount: `{float(losses['amount'] or 0):.2f}`","","📜 **Transactions**"]
    names={"deposit":"💳 Deposit","withdraw":"💸 Withdraw","aviator_bet":"✈️ Aviator Bet","aviator_win":"🏆 Aviator Win","auction_ticket":"🎟 Auction Ticket","auction_win":"🏆 Auction Win"}
    for r in tx:
        lines.append(f"{names.get(r['transaction_type'],r['transaction_type'])}: `{float(r['amount'] or 0):.2f}` ብር — `{r['created_at']}`")
    await q.edit_message_text("\n".join(lines),parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Users",callback_data="admin_users:0")],[InlineKeyboardButton("📩 Reply to Player",callback_data=f"support_reply:{user_id}")]]))

# ============================================================
# ADMIN TOTAL WALLETS
# ============================================================

async def admin_total_wallets(update, context):

    query = update.callback_query

    await query.answer()

    if not is_staff(query.from_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            SUM(balance) AS total,
            COUNT(*) AS cnt
        FROM users
    """)

    res = cur.fetchone()

    conn.close()

    total = res["total"] or 0.0

    text = (
        f"📊 **Wallet አጠቃላይ መረጃ**\n\n"
        f"👥 Users: `{res['cnt']}`\n"
        f"💰 Total Wallet: `{total:.2f}` ብር"
    )

    keyboard = [[
        InlineKeyboardButton(
            "🔙 አድሚን ፓነል",
            callback_data="admin_panel"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# ADMIN RESULTS HISTORY
# ============================================================

async def admin_results(update, context):

    query = update.callback_query

    await query.answer()

    if not is_staff(query.from_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE status = 'CLOSED'
        ORDER BY id DESC
        LIMIT 10
    """)

    auctions = cur.fetchall()

    conn.close()

    if not auctions:

        text = "📊 እስካሁን የተጠናቀቀ ጨረታ የለም።"

    else:

        text = "📊 **የተጠናቀቁ ጨረታዎች**\n\n"

        for auc in auctions:

            collected = float(
                auc["total_collected"] or 0
            )

            prize = float(
                auc["prize_amount"]
            )

            profit = collected - prize

            if auc["winner_user_id"]:

                winner_name = get_winner_name(
                    auc["winner_user_id"]
                )

                winner_line = (
                    f"🏆 {winner_name}\n"
                    f"🎯 Unique: "
                    f"`{auc['winning_bid']}` ብር"
                )

            else:

                winner_line = (
                    "🏆 አሸናፊ: የለም\n"
                    "🎯 Unique: የለም"
                )

            participants, bid_count = get_auction_participant_stats(auc["id"])
            text += (
                f"📌 **Auction #{auc['id']}**\n"
                f"{winner_line}\n"
                f"👥 Participants: `{participants}`\n"
                f"🎟 Total Bids: `{bid_count}`\n"
                f"💰 Prize: `{prize:.2f}` ብር\n"
                f"💵 Collected: `{collected:.2f}` ብር\n"
                f"📊 ልዩነት: `{profit:.2f}` ብር\n"
                f"📅 {auc['closed_at']}\n"
                f"════════════\n"
            )

    keyboard = [[
        InlineKeyboardButton(
            "🔙 አድሚን ፓነል",
            callback_data="admin_panel"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# ADMIN AUCTION MANAGEMENT
# ============================================================

async def admin_manage_auctions_from_message(update, context):
    if not is_staff(update.effective_user.id):
        return
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM auctions WHERE status = 'ACTIVE' ORDER BY id DESC")
    auctions = cur.fetchall()
    conn.close()
    text = "🎯 **ንቁ ጨረታዎች**\n\n"
    keyboard = []
    for auc in auctions:
        real_participants, _ = get_auction_participant_stats(auc["id"])
        sim_count = get_auction_simulation_count(auc["id"])
        text += f"# {auc['id']} — Real: {real_participants} | Simulation: {sim_count}\n"
        keyboard.append([InlineKeyboardButton(f"🧪 Simulation + | {sim_count}", callback_data=f"admin_sim_add:{auc['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 አድሚን ፓነል", callback_data="admin_panel")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_manage_auctions(update, context):

    query = update.callback_query

    await query.answer()

    if not is_staff(query.from_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE status = 'ACTIVE'
        ORDER BY id DESC
    """)

    auctions = cur.fetchall()

    conn.close()

    text = "🎯 **ንቁ ጨረታዎች**\n\n"

    keyboard = []

    if not auctions:

        text += "አሁን ንቁ ጨረታ የለም።"

    else:

        for auc in auctions:

            keyboard.append([
                InlineKeyboardButton(
                    f"🎯 #{auc['id']} | "
                    f"Prize {auc['prize_amount']} ብር",
                    callback_data="none"
                )
            ])

            keyboard.append([
                InlineKeyboardButton(
                    "❌ ዝጋ",
                    callback_data=f"admin_close:{auc['id']}"
                ),
                InlineKeyboardButton(
                    "⏳ +1 ሰዓት",
                    callback_data=f"admin_extend:{auc['id']}"
                ),
                InlineKeyboardButton(
                    "🗑 ሰርዝ",
                    callback_data=f"admin_delete:{auc['id']}"
                )
            ])
            real_participants, real_bids = get_auction_participant_stats(auc["id"])
            sim_count = get_auction_simulation_count(auc["id"])
            keyboard.append([
                InlineKeyboardButton(
                    f"🧪 Simulation + | {sim_count}",
                    callback_data=f"admin_sim_add:{auc['id']}"
                )
            ])
            if auc["post_message_id"]:
                keyboard.append([InlineKeyboardButton("✏️ Post አስተካክል",callback_data=f"admin_post_edit:{auc['id']}"),InlineKeyboardButton("🗑 Post ሰርዝ",callback_data=f"admin_post_delete:{auc['id']}")])
            else:
                keyboard.append([InlineKeyboardButton("📢 Post አድርግ",callback_data=f"admin_post:{auc['id']}")])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 አድሚን ፓነል",
            callback_data="admin_panel"
        )
    ])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# ADMIN AUCTION ACTION
# ============================================================

async def admin_auction_action_callback(
    update,
    context
):

    query = update.callback_query

    if not is_staff(query.from_user.id):
        await query.answer()
        return

    data = query.data

    action, auc_id = data.split(":")
    auc_id = int(auc_id)

    if action == "admin_close":

        # ----------------------------------------------------
        # Close + calculate winner
        # ----------------------------------------------------

        final_auction = close_auction(
            auc_id
        )

        if not final_auction:

            await query.answer(
                "❌ ጨረታው አልተገኘም።",
                show_alert=True
            )

            return

        send_auction_result(
            context.application,
            final_auction
        )

        await query.answer(
            f"✅ Auction #{auc_id} ተዘግቷል።",
            show_alert=True
        )

        # Create next only if none active
        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM auctions
            WHERE status = 'ACTIVE'
        """)

        active_count = cur.fetchone()["cnt"]

        # No automatic next auction. Admin creates the next one manually.

        conn.close()

    elif action == "admin_delete":

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM auctions WHERE id=? AND status='ACTIVE'", (auc_id,))
        auc = cur.fetchone()

        if not auc:
            conn.close()
            await query.answer("❌ ጨረታው አልተገኘም።", show_alert=True)
            return

        # Refund every ticket already paid before deleting the auction.
        cur.execute("SELECT user_id, COUNT(*) AS cnt FROM bids WHERE auction_id=? GROUP BY user_id", (auc_id,))
        bid_users = cur.fetchall()
        for row in bid_users:
            refund = float(row["cnt"] or 0) * float(auc["ticket_price"] or 0)
            if refund > 0:
                cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (refund, row["user_id"]))

        # Delete the channel post first when one exists.
        post_chat = auc["post_chat_id"] if "post_chat_id" in auc.keys() else None
        post_msg = auc["post_message_id"] if "post_message_id" in auc.keys() else None
        if post_chat and post_msg:
            try:
                await context.bot.delete_message(chat_id=post_chat, message_id=post_msg)
            except Exception as e:
                logging.warning(f"Auction post delete while auction deleting: {e}")

        cur.execute("DELETE FROM bids WHERE auction_id=?", (auc_id,))
        cur.execute("DELETE FROM auctions WHERE id=?", (auc_id,))
        conn.commit()
        conn.close()

        await query.answer(f"🗑 Auction #{auc_id} ተሰርዟል። የተከፈለ Ticket ተመልሷል።", show_alert=True)

    elif action == "admin_extend":

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            UPDATE auctions
            SET ends_at = datetime(ends_at, '+1 hour')
            WHERE id = ?
            AND status = 'ACTIVE'
        """, (auc_id,))

        conn.commit()
        conn.close()

        # If this auction already has a channel post, refresh its end time immediately.
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM auctions WHERE id=?", (auc_id,))
        updated_auc = cur.fetchone()
        conn.close()
        if updated_auc and updated_auc["post_chat_id"] and updated_auc["post_message_id"]:
            try:
                await context.bot.edit_message_text(
                    chat_id=updated_auc["post_chat_id"],
                    message_id=updated_auc["post_message_id"],
                    text=build_auction_post(updated_auc),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ተሳተፍ", callback_data=f"select_auc:{auc_id}")]])
                )
            except Exception as e:
                logging.warning(f"Auction post refresh error: {e}")

        await query.answer(
            f"⏳ #{auc_id} በ1 ሰዓት ተራዝሟል።",
            show_alert=True
        )

    await admin_manage_auctions(
        update,
        context
    )


# ============================================================
# DEPOSIT
# ============================================================

async def show_deposit(update, context):

    query = update.callback_query

    await query.answer()

    text = (
        "💳 **የክፍያ መረጃ**\n\n"
        f"👤 `{ACCOUNT_NAME}`\n\n"
        f"🏦 CBE: `{CBE_ACCOUNT}`\n"
        f"🏦 BOA: `{BOA_ACCOUNT}`\n"
        f"📱 Telebirr: `{TELEBIRR_NUMBER}`\n\n"
        "ገንዘብ ካስተላለፉ በኋላ "
        "መጠኑን ያስገቡ እና Screenshot ይላኩ።"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "✍️ የከፈሉትን መጠን",
                callback_data="deposit_ask"
            )
        ],

        [
            InlineKeyboardButton(
                "🔙 ዋና ማውጫ",
                callback_data="main"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def ask_amount(update, context):

    query = update.callback_query

    await query.answer()

    context.user_data.clear()

    context.user_data[
        "waiting_amount"
    ] = True

    await query.edit_message_text(
        "💰 **የከፈሉትን መጠን በቁጥር ያስገቡ፦**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )
            ]
        ])
    )


# ============================================================
# WITHDRAW
# ============================================================

async def show_withdraw(update, context):

    query = update.callback_query

    await query.answer()

    balance = get_balance(
        query.from_user.id
    )

    context.user_data.clear()

    context.user_data[
        "waiting_withdraw_amount"
    ] = True

    text = (
        f"💸 **ገንዘብ ማውጣት**\n\n"
        f"Wallet: `{balance:.2f}` ብር\n\n"
        f"ደረጃ 1/3\n"
        f"የሚያወጡትን መጠን ያስገቡ።"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )
            ]
        ])
    )


# ============================================================
# BALANCE
# ============================================================

async def show_balance(update, context):

    query = update.callback_query

    await query.answer()

    balance = get_balance(
        query.from_user.id
    )

    text = (
        f"💰 **Wallet**\n\n"
        f"`{balance:.2f}` ብር"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💳 ሂሳብ ሙላ",
                    callback_data="deposit"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )
            ]
        ])
    )


# ============================================================
# HISTORY
# ============================================================

async def show_history(update, context):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    conn = db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT amount, transaction_type, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
        """, (user_id,))
        rows = cur.fetchall()
    except sqlite3.Error as e:
        logging.error(f"History database error for user {user_id}: {e}")
        rows = []
    finally:
        conn.close()

    if not rows:
        text = (
            "📜 **የክፍያ ታሪክ**\n\n"
            "እስካሁን የተመዘገበ የክፍያ/Wallet ግብይት የለም።"
        )
    else:
        lines = ["📜 **የክፍያ ታሪክ — የመጨረሻ 10**", ""]
        type_names = {
            "deposit": "💳 ሂሳብ መሙያ",
            "withdraw": "💸 ገንዘብ ማውጣት",
            "auction_ticket": "🎟 የጨረታ ቲኬት",
            "auction_win": "🏆 የጨረታ ሽልማት",
        }

        for row in rows:
            tx_type = type_names.get(
                row["transaction_type"],
                str(row["transaction_type"] or "ግብይት")
            )
            amount = float(row["amount"] or 0)
            sign = "+" if amount > 0 else ""
            lines.append(
                f"{tx_type}\n"
                f"💰 {sign}{amount:.2f} ብር\n"
                f"📅 {row['created_at']}\n"
                f"────────────"
            )
        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 ዋና ማውጫ", callback_data="main")]
        ])
    )


# ============================================================
# WINNERS HISTORY
# ============================================================

async def show_winners_history(update, context):

    query = update.callback_query

    await query.answer()

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            t.user_id,
            u.first_name,
            t.amount,
            t.created_at
        FROM transactions t
        JOIN users u
            ON t.user_id = u.user_id
        WHERE t.transaction_type = 'auction_win'
        ORDER BY t.id DESC
        LIMIT 10
    """)

    rows = cur.fetchall()

    conn.close()

    text = "🏆 **ያለፉ አሸናፊዎች**\n\n"

    if not rows:

        text += "እስካሁን አሸናፊ የለም።"

    else:

        for r in rows:

            text += (
                f"👤 {r['first_name']}\n"
                f"💰 `{r['amount']}` ብር\n"
                f"📅 {r['created_at']}\n"
                f"────────────\n"
            )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )
            ]
        ])
    )


# ============================================================
# AUCTIONS
# ============================================================

async def show_auctions(update, context):

    query = update.callback_query

    await query.answer()

    balance = get_balance(
        query.from_user.id
    )

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE status = 'ACTIVE'
        ORDER BY id DESC
    """)

    auctions = cur.fetchall()

    conn.close()

    if not auctions:

        text = (
            "❌ አሁን ንቁ ጨረታ የለም።\n\n"
            f"Wallet: `{balance:.2f}` ብር"
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 ዋና ማውጫ",
                callback_data="main"
            )
        ]]

    else:

        text = (
            f"🔥 **ንቁ ጨረታዎች**\n"
            f"Wallet: `{balance:.2f}` ብር\n\n"
            f"ጨረታ ይምረጡ፦"
        )

        keyboard = []

        for auc in auctions:

            try:

                ends_dt = datetime.strptime(
                    auc["ends_at"],
                    "%Y-%m-%d %H:%M:%S"
                )

                seconds = int(
                    (
                        ends_dt
                        - datetime.now()
                    ).total_seconds()
                )

                if seconds <= 0:

                    time_str = "ሊጠናቀቅ ነው"

                else:

                    days, rem = divmod(
                        seconds,
                        86400
                    )

                    hours, rem = divmod(
                        rem,
                        3600
                    )

                    minutes, _ = divmod(
                        rem,
                        60
                    )

                    time_str = (
                        f"{days}ቀን "
                        f"{hours}ሰ "
                        f"{minutes}ደ"
                    )

            except Exception:

                time_str = "N/A"

            real_participants, _ = get_auction_participant_stats(auc["id"])
            simulated_participants = get_auction_simulation_count(auc["id"])
            total_participants = real_participants + simulated_participants

            keyboard.append([
                InlineKeyboardButton(
                    f"🎯 {auc['prize_amount']} ብር | "
                    f"🎟 {auc['ticket_price']} | "
                    f"👥 {total_participants} ተሳታፊ | "
                    f"⏳ {time_str}",
                    callback_data=f"select_auc:{auc['id']}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔙 ዋና ማውጫ",
                callback_data="main"
            )
        ])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# SELECT AUCTION
# ============================================================

async def select_auction_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    auction_id = int(
        query.data.split(":")[1]
    )

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE id = ?
        AND status = 'ACTIVE'
    """, (auction_id,))

    auction = cur.fetchone()

    conn.close()

    if not auction:

        await query.edit_message_text(
            "❌ ይህ ጨረታ ተዘግቷል።",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 ዋና ማውጫ",
                        callback_data="main"
                    )
                ]
            ])
        )

        return

    context.user_data.clear()

    context.user_data[
        "selected_auction_id"
    ] = auction_id

    try:

        ends_dt = datetime.strptime(
            auction["ends_at"],
            "%Y-%m-%d %H:%M:%S"
        )

        seconds = int(
            (
                ends_dt
                - datetime.now()
            ).total_seconds()
        )

        if seconds > 0:

            days, rem = divmod(
                seconds,
                86400
            )

            hours, rem = divmod(
                rem,
                3600
            )

            minutes, _ = divmod(
                rem,
                60
            )

            time_str = (
                f"{days} ቀን "
                f"{hours} ሰዓት "
                f"{minutes} ደቂቃ"
            )

        else:

            time_str = "ሊጠናቀቅ ነው"

    except Exception:

        time_str = "N/A"

    text = (
        f"🎯 **ጨረታ #{auction_id}**\n\n"
        f"🏆 ሽልማት: "
        f"`{auction['prize_amount']}` ብር\n"
        f"🎟 Ticket: "
        f"`{auction['ticket_price']}` ብር\n"
        f"⏳ የሚቀረው: `{time_str}`\n"
        f"👥 ተሳታፊዎች: `{get_auction_participant_stats(auction_id)[0] + get_auction_simulation_count(auction_id)}` ሰዎች\n\n"
        f"Bid ዋጋዎን በቁጥር ብቻ ያስገቡ።"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ ተመለስ",
                    callback_data="auctions"
                )
            ]
        ])
    )


# ============================================================
# PROCESS BID
# ============================================================

async def process_bid(
    update,
    context,
    auction_id,
    bid_amount
):

    user = update.effective_user

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM auctions
        WHERE id = ?
        AND status = 'ACTIVE'
    """, (auction_id,))

    auction = cur.fetchone()

    if not auction:

        conn.close()

        await update.message.reply_text(
            "❌ ጨረታው ተዘግቷል።"
        )

        return

    ticket_price = float(
        auction["ticket_price"]
    )

    if bid_amount < 1:
        conn.close()
        await update.message.reply_text("❌ Bid ቢያንስ 1 ብር መሆን አለበት።")
        return

    if round(bid_amount, 2) != bid_amount:
        conn.close()
        await update.message.reply_text("❌ ከነጥብ በኋላ 2 ቁጥር ብቻ ይፈቀዳል።")
        return

    cur.execute("""
        SELECT balance
        FROM users
        WHERE user_id = ?
    """, (user.id,))

    user_row = cur.fetchone()

    balance = (
        float(user_row["balance"])
        if user_row
        else 0.0
    )

    if balance < ticket_price:

        conn.close()

        await update.message.reply_text(
            (
                f"🚫 **Wallet በቂ አይደለም።**\n\n"
                f"🎟 Ticket: `{ticket_price}` ብር\n"
                f"💰 Wallet: `{balance:.2f}` ብር"
            ),
            parse_mode="Markdown"
        )

        return

    try:

        cur.execute("BEGIN")

        cur.execute("""
            UPDATE users
            SET balance = balance - ?
            WHERE user_id = ?
            AND balance >= ?
        """, (
            ticket_price,
            user.id,
            ticket_price
        ))

        if cur.rowcount != 1:

            conn.rollback()
            conn.close()

            await update.message.reply_text(
                "🚫 Wallet በቂ አይደለም።"
            )

            return

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cur.execute("""
            INSERT INTO bids (
                auction_id,
                user_id,
                bid_amount,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            auction_id,
            user.id,
            bid_amount,
            now
        ))

        cur.execute("""
            INSERT INTO transactions (
                user_id,
                amount,
                transaction_type,
                created_at
            )
            VALUES (?, ?, 'auction_ticket', ?)
        """, (
            user.id,
            -ticket_price,
            now
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        conn.close()

        logging.error(
            f"Bid transaction error: {e}"
        )

        await update.message.reply_text(
            "❌ Bid ሲመዘገብ ችግኝ ተፈጥሯል።"
        )

        return

    conn.close()

    # Refresh the public auction post so users see the updated TOTAL
    # participant count. It intentionally does not reveal Real/Simulation.
    try:
        conn2 = db(); cur2 = conn2.cursor()
        cur2.execute("SELECT * FROM auctions WHERE id = ?", (auction_id,))
        updated_auction = cur2.fetchone()
        conn2.close()
        if updated_auction and updated_auction["post_chat_id"] and updated_auction["post_message_id"]:
            await update.get_bot().edit_message_text(
                chat_id=updated_auction["post_chat_id"],
                message_id=updated_auction["post_message_id"],
                text=build_auction_post(updated_auction),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎯 ተሳተፍ", callback_data=f"select_auc:{auction_id}")
                ]])
            )
    except Exception as e:
        logging.warning(f"Could not refresh auction post #{auction_id}: {e}")

    new_balance = get_balance(
        user.id
    )

    await update.message.reply_text(
        (
            f"✅ **Bid ተመዝግቧል።**\n\n"
            f"🎯 Auction: `#{auction_id}`\n"
            f"💰 Bid: `{bid_amount}` ብር\n"
            f"🎟 Ticket: `{ticket_price}` ብር\n"
            f"💳 Wallet: `{new_balance:.2f}` ብር"
        ),
        parse_mode="Markdown"
    )

    # --------------------------------------------------------
    # Return to Main Menu
    # --------------------------------------------------------

    await start(
        update,
        context
    )


# ============================================================
# MY BIDS
# ============================================================

async def my_bids_command(update, context):

    user_id = update.effective_user.id

    balance = get_balance(user_id)

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            b.auction_id,
            b.bid_amount,
            b.created_at,
            a.prize_amount,
            a.status,
            a.ends_at
        FROM bids b
        JOIN auctions a
            ON b.auction_id = a.id
        WHERE b.user_id = ?
        ORDER BY b.created_at DESC
        LIMIT 10
    """, (user_id,))

    bids = cur.fetchall()

    conn.close()

    if not bids:

        text = (
            f"📭 የጨረታ ተሳትፎ የለም።\n\n"
            f"Wallet: `{balance:.2f}` ብር"
        )

    else:

        text = (
            f"📋 **የኔ ተሳትፎዎች**\n"
            f"Wallet: `{balance:.2f}` ብር\n\n"
        )

        for b in bids:

            status = (
                "🟢 Active"
                if b["status"] == "ACTIVE"
                else "🔴 Closed"
            )

            text += (
                f"🎯 Auction #{b['auction_id']} "
                f"({status})\n"
                f"🏆 Prize: `{b['prize_amount']}` ብር\n"
                f"💰 Bid: `{b['bid_amount']}` ብር\n"
                f"📅 {b['created_at']}\n"
                f"────────────\n"
            )

    keyboard = [[
        InlineKeyboardButton(
            "🔙 ዋና ማውጫ",
            callback_data="main"
        )
    ]]

    if update.callback_query:

        await update.callback_query.answer()

        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ============================================================
# PHOTO HANDLER
# ============================================================

async def handle_photo(update, context):

    user = update.effective_user

    register_user(user)

    if is_staff(user.id) and context.user_data.get("support_reply_user_id"):
        await send_admin_support_reply(update, context, photo_id=update.message.photo[-1].file_id, text=update.message.caption or "")
        return

    if context.user_data.get("waiting_support_message") and not is_staff(user.id):
        await send_support_to_admin(update, context, photo_id=update.message.photo[-1].file_id, text=update.message.caption or "")
        return

    if is_staff(user.id) and context.user_data.get("waiting_admin_announcement"):
        await promo_content_received(update, context, "photo", update.message.photo[-1].file_id); return

    # ========================================================
    # ADMIN -> WITHDRAWAL PAYMENT SCREENSHOT
    # User NEVER sends a withdrawal screenshot.
    # Admin sends the real payment proof here, and the bot
    # forwards it to the withdrawal owner.
    # ========================================================
    if is_staff(user.id) and context.user_data.get("admin_withdraw_proof_id"):
        withdraw_id = context.user_data.get("admin_withdraw_proof_id")
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM withdrawals WHERE id=?", (withdraw_id,))
        w = cur.fetchone()
        if not w or w["status"] != "pending":
            conn.close()
            context.user_data.pop("admin_withdraw_proof_id", None)
            await update.message.reply_text("⚠️ ይህ Withdrawal ቀድሞ ተጠናቋል ወይም አልተገኘም።")
            return

        photo_id = update.message.photo[-1].file_id

        # First deliver the real payment proof to the withdrawal owner.
        # The withdrawal is marked completed ONLY after Telegram confirms delivery.
        try:
            await context.bot.send_photo(
                chat_id=w["user_id"],
                photo=photo_id,
                caption=(
                    f"✅ **የWithdrawal ክፍያ ተፈጽሟል።**\n\n"
                    f"💰 መጠን: `{w['amount']:.2f}` ብር\n"
                    f"👤 ስም: `{w['acc_name']}`\n"
                    f"📱 አካውንት: `{w['acc_number']}`\n"
                    f"🆔 Withdrawal: `{withdraw_id}`\n\n"
                    "📸 የክፍያ ማስረጃ ከAdmin ተልኳል።"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            conn.close()
            logging.error(f"Withdrawal proof delivery error: {e}")
            await update.message.reply_text(
                "❌ Screenshot ለUser መላክ አልተቻለም። Withdrawal አልተጠናቀቀም። እንደገና 📸 Payment Screenshot ላክ ይጫኑ።"
            )
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            UPDATE withdrawals
            SET screenshot_file_id=?, status='approved'
            WHERE id=? AND status='pending'
        """, (photo_id, withdraw_id))

        if cur.rowcount != 1:
            conn.rollback()
            conn.close()
            await update.message.reply_text("⚠️ Withdrawal ቀድሞ ተጠናቋል ወይም ተቀይሯል።")
            return

        conn.commit()
        conn.close()
        context.user_data.pop("admin_withdraw_proof_id", None)

        await update.message.reply_text(
            f"✅ Screenshot ለUser `{w['user_id']}` ተልኳል።\n💰 `{w['amount']:.2f}` ብር\n🟢 Withdrawal #{withdraw_id} Paid/Completed ሆኗል።",
            parse_mode="Markdown"
        )
        return

    pending_amount = context.user_data.get(
        "payment_amount"
    )

    if not pending_amount:

        await update.message.reply_text(
            "❌ መጀመሪያ የከፈሉትን መጠን ያስገቡ።"
        )

        return

    photo_id = (
        update.message.photo[-1].file_id
    )

    payment_id = create_payment(
        user.id,
        user.first_name or "",
        pending_amount,
        photo_id
    )

    context.user_data.clear()

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ APPROVE",
                callback_data=f"approve:{payment_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ REJECT",
                callback_data=f"reject:{payment_id}"
            )
        ]
    ]

    await send_staff_photo(
        context,
        photo_id,
        (
            f"📥 **Payment Request**\n\n"
            f"🆔 User: `{user.id}`\n"
            f"👤 {user.first_name}\n"
            f"💰 `{pending_amount:.2f}` ብር\n"
            f"🆔 Payment: `{payment_id}`"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text(
        "✅ Screenshot ተልኳል። Admin ካረጋገጠው Wallet ይጨምራል።"
    )


# ============================================================
# GIF / ANIMATION HANDLER
# ============================================================

async def handle_animation(update, context):
    user = update.effective_user
    register_user(user)
    if is_staff(user.id) and context.user_data.get("waiting_admin_announcement"):
        await promo_content_received(update, context, "animation", update.message.animation.file_id)
        return
    await update.message.reply_text("❌ GIF ለመላክ መጀመሪያ Admin / Manager የማስታወቂያ ቁልፉን ይጫኑ።")


# ============================================================
# VIDEO HANDLER
# ============================================================

async def handle_video(update, context):
    user=update.effective_user; register_user(user)
    if is_staff(user.id) and context.user_data.get("waiting_admin_announcement"):
        await promo_content_received(update, context, "video", update.message.video.file_id); return
    await update.message.reply_text("❌ Video ለመላክ 📩 Admin / Manager ቁልፉን መጀመሪያ ይጫኑ።")


# ============================================================
# TEXT HANDLER
# ============================================================

async def handle_text(update, context):

    user = update.effective_user

    register_user(user)

    text = update.message.text.strip()

    if context.user_data.get("waiting_admin_pin"):
        if not is_staff(user.id):
            context.user_data.pop("waiting_admin_pin", None)
            return
        if not hmac.compare_digest(text.encode("utf-8"), ADMIN_PANEL_PIN.encode("utf-8")):
            await update.message.reply_text("❌ የAdmin PIN ስህተት ነው።")
            return
        context.user_data.pop("waiting_admin_pin", None)
        context.user_data["admin_pin_verified_until"] = time.time() + BOT_ADMIN_PIN_TTL
        try:
            await update.message.delete()
        except Exception:
            pass
        await update.message.reply_text("✅ Admin PIN ተረጋግጧል። ለ15 ደቂቃ የAdmin/Manager actions ክፍት ናቸው።")
        return

    if is_staff(user.id) and context.user_data.get("support_reply_user_id"):
        await send_admin_support_reply(update, context, text=text)
        return

    if context.user_data.get("waiting_support_message") and not is_staff(user.id):
        await send_support_to_admin(update, context, text=text)
        return

    # ========================================================
    # KDM AVIATOR BET
    # ========================================================
    if context.user_data.get("aviator_waiting_bet"):
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ ትክክለኛ የBet መጠን ያስገቡ።")
            return
        await process_aviator_bet(update, context, amount)
        return

    # ========================================================
    # ADMIN CREATE AUCTION
    # ========================================================

    if is_staff(user.id):

        # ----------------------------------------------------
        # Admin announcement
        # ----------------------------------------------------
        if context.user_data.get("waiting_admin_announcement"):
            if text.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text("❌ ማስታወቂያው ተሰርዟል።")
                await admin_panel_handler_from_message(update, context)
                return

            _pr = context.user_data.get("promo") or {}
            if _pr.get("wait_buttons"):
                if text.strip().lower() == "clear":
                    _pr["extra"] = []; _pr["wait_buttons"] = False
                    await promo_show_preview(update.message, context)
                else:
                    await promo_buttons_received(update, context)
                return
            await promo_content_received(update, context, "text")
            return

        # ----------------------------------------------------
        # Admin-only simulation participants
        # ----------------------------------------------------
        if context.user_data.get("waiting_admin_sim_count"):
            try:
                count = int(text)
                if count <= 0 or count > 10000:
                    raise ValueError
            except ValueError:
                await update.message.reply_text(
                    "❌ 1-10000 መካከል ያለ ቁጥር ያስገቡ።"
                )
                return

            auction_id = context.user_data.get("admin_sim_auction_id")
            context.user_data.pop("waiting_admin_sim_count", None)
            context.user_data.pop("admin_sim_auction_id", None)

            if not auction_id:
                await update.message.reply_text("❌ ጨረታው አልተገኘም።")
                return

            conn = db(); cur = conn.cursor()
            cur.execute(
                "SELECT id, status FROM auctions WHERE id = ?",
                (auction_id,)
            )
            auc = cur.fetchone()
            conn.close()

            if not auc or auc["status"] != "ACTIVE":
                await update.message.reply_text("❌ ይህ ጨረታ ACTIVE አይደለም።")
                return

            add_auction_simulations(auction_id, count, user.id)
            total_sim = get_auction_simulation_count(auction_id)
            real_participants, _ = get_auction_participant_stats(auction_id)

            # Public post shows only the combined participant total.
            try:
                conn2 = db(); cur2 = conn2.cursor()
                cur2.execute("SELECT * FROM auctions WHERE id = ?", (auction_id,))
                updated_auction = cur2.fetchone()
                conn2.close()
                if updated_auction and updated_auction["post_chat_id"] and updated_auction["post_message_id"]:
                    await context.bot.edit_message_text(
                        chat_id=updated_auction["post_chat_id"],
                        message_id=updated_auction["post_message_id"],
                        text=build_auction_post(updated_auction),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🎯 ተሳተፍ", callback_data=f"select_auc:{auction_id}")
                        ]])
                    )
            except Exception as e:
                logging.warning(f"Could not refresh simulation auction post #{auction_id}: {e}")

            await update.message.reply_text(
                f"✅ Simulation ተጨምሯል።\n\n"
                f"🎯 Auction: #{auction_id}\n"
                f"👥 Real: {real_participants}\n"
                f"🧪 Simulation: {total_sim}\n"
                f"📊 Admin Total: {real_participants + total_sim}"
            )
            await admin_manage_auctions_from_message(update, context)
            return

        # ----------------------------------------------------
        # Prize
        # ----------------------------------------------------

        if context.user_data.get(
            "waiting_admin_prize"
        ):

            try:

                prize = float(text)

                if prize <= 0:
                    raise ValueError

            except ValueError:

                await update.message.reply_text(
                    "❌ ትክክለኛ የሽልማት ብር ያስገቡ።"
                )

                return

            context.user_data.pop(
                "waiting_admin_prize"
            )

            context.user_data[
                "admin_prize"
            ] = prize

            context.user_data[
                "waiting_admin_ticket"
            ] = True

            await update.message.reply_text(
                (
                    f"✅ Prize: `{prize:.2f}` ብር\n\n"
                    f"ደረጃ 2/4\n"
                    f"🎟 የTicket ዋጋ ያስገቡ።"
                ),
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # Ticket
        # ----------------------------------------------------

        if context.user_data.get(
            "waiting_admin_ticket"
        ):

            try:

                ticket = float(text)

                if ticket <= 0:
                    raise ValueError

            except ValueError:

                await update.message.reply_text(
                    "❌ ትክክለኛ የTicket ዋጋ ያስገቡ።"
                )

                return

            context.user_data.pop(
                "waiting_admin_ticket"
            )

            context.user_data[
                "admin_ticket"
            ] = ticket

            context.user_data[
                "waiting_admin_hours"
            ] = True

            await update.message.reply_text(
                (
                    f"✅ Ticket: `{ticket:.2f}` ብር\n\n"
                    f"ደረጃ 3/4\n"
                    f"⏱ ለስንት **ሰዓት** እንዲቆይ "
                    f"ይፈልጋሉ?\n\n"
                    f"ለምሳሌ፦ `23`"
                ),
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # Hours
        # ----------------------------------------------------

        if context.user_data.get(
            "waiting_admin_hours"
        ):

            try:

                hours = int(text)

                if hours < 0:
                    raise ValueError

            except ValueError:

                await update.message.reply_text(
                    "❌ ሰዓቱን በቁጥር ያስገቡ።"
                )

                return

            context.user_data.pop(
                "waiting_admin_hours"
            )

            context.user_data[
                "admin_hours"
            ] = hours

            context.user_data[
                "waiting_admin_minutes"
            ] = True

            await update.message.reply_text(
                (
                    f"✅ Hours: `{hours}`\n\n"
                    f"ደረጃ 4/4\n"
                    f"⏱ ስንት **ደቂቃ** እንዲቆይ?\n\n"
                    f"ለምሳሌ፦ `30`\n"
                    f"ከሌለ `0` ያስገቡ።"
                ),
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # Minutes
        # ----------------------------------------------------

        if context.user_data.get(
            "waiting_admin_minutes"
        ):

            try:

                minutes = int(text)

                if minutes < 0 or minutes > 59:
                    raise ValueError

            except ValueError:

                await update.message.reply_text(
                    "❌ ደቂቃው 0-59 መሆን አለበት።"
                )

                return

            prize = context.user_data.get(
                "admin_prize"
            )

            ticket = context.user_data.get(
                "admin_ticket"
            )

            hours = context.user_data.get(
                "admin_hours"
            )

            auction_id = create_custom_auction(
                prize,
                ticket,
                hours,
                minutes
            )

            context.user_data.clear()

            await update.message.reply_text(
                (
                    f"✅ **አዲስ ጨረታ ተፈጥሯል!**\n\n"
                    f"🎯 Auction: `#{auction_id}`\n"
                    f"💰 Prize: `{prize:.2f}` ብር\n"
                    f"🎟 Ticket: `{ticket:.2f}` ብር\n"
                    f"⏱ Duration: `{hours}` ሰዓት "
                    f"እና `{minutes}` ደቂቃ\n\n"
                    f"ጨረታው አሁን ACTIVE ነው።"
                ),
                parse_mode="Markdown"
            )

            await admin_panel_handler_from_message(
                update,
                context
            )

            return

    # ========================================================
    # DEPOSIT AMOUNT
    # ========================================================

    if context.user_data.get(
        "waiting_amount"
    ):

        try:

            amount = float(text)

            if amount <= 0:
                raise ValueError

        except ValueError:

            await update.message.reply_text(
                "❌ ትክክለኛ የገንዘብ መጠን ያስገቡ።"
            )

            return

        context.user_data.pop(
            "waiting_amount"
        )

        context.user_data[
            "payment_amount"
        ] = amount

        await update.message.reply_text(
            (
                f"✅ `{amount:.2f}` ብር ተመዝግቧል።\n\n"
                f"አሁን Screenshot ይላኩ።"
            ),
            parse_mode="Markdown"
        )

        return

    # ========================================================
    # WITHDRAW AMOUNT
    # ========================================================

    if context.user_data.get(
        "waiting_withdraw_amount"
    ):

        try:

            amount = float(text)

            if amount <= 0:
                raise ValueError

        except ValueError:

            await update.message.reply_text(
                "❌ ትክክለኛ የብር መጠን ያስገቡ።"
            )

            return

        balance = get_balance(user.id)

        if balance < amount:

            await update.message.reply_text(
                (
                    f"🚫 በቂ Wallet የለዎትም።\n"
                    f"Wallet: `{balance:.2f}` ብር"
                ),
                parse_mode="Markdown"
            )

            return

        context.user_data.pop(
            "waiting_withdraw_amount"
        )

        context.user_data[
            "withdraw_amount"
        ] = amount

        context.user_data[
            "waiting_withdraw_name"
        ] = True

        await update.message.reply_text(
            (
                f"ደረጃ 2/3\n\n"
                f"👤 Account Holder Name ያስገቡ።"
            )
        )

        return

    # ========================================================
    # WITHDRAW NAME
    # ========================================================

    if context.user_data.get(
        "waiting_withdraw_name"
    ):

        context.user_data.pop(
            "waiting_withdraw_name"
        )

        context.user_data[
            "withdraw_name"
        ] = text

        context.user_data[
            "waiting_withdraw_number"
        ] = True

        await update.message.reply_text(
            (
                f"ደረጃ 3/3\n\n"
                f"📱 Bank Account Number "
                f"ወይም Telebirr Number ያስገቡ።"
            )
        )

        return

    # ========================================================
    # WITHDRAW ACCOUNT NUMBER
    # ========================================================

    if context.user_data.get(
        "waiting_withdraw_number"
    ):

        context.user_data.pop(
            "waiting_withdraw_number"
        )

        acc_number = text

        amount = context.user_data.pop(
            "withdraw_amount",
            0
        )

        acc_name = context.user_data.pop(
            "withdraw_name",
            ""
        )

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("BEGIN IMMEDIATE")

            _b, _lk, _can = _withdrawable(cur, user.id)
            if _lk > 0 and amount > _can + 0.001:
                conn.rollback()
                conn.close()
                await update.message.reply_text(f"🎁 Bonus ({_lk:.2f} ብር) ለመጫወት ብቻ ነው -- ማውጣት የሚችሉት {_can:.2f} ብር ነው")
                return

            cur.execute("""
                UPDATE users
                SET balance = balance - ?
                WHERE user_id = ?
                AND balance >= ?
            """, (
                amount,
                user.id,
                amount
            ))

            if cur.rowcount != 1:

                conn.rollback()
                conn.close()

                await update.message.reply_text(
                    "🚫 Wallet በቂ አይደለም።"
                )

                return

            now = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            cur.execute("""
                INSERT INTO withdrawals (
                    user_id,
                    amount,
                    acc_name,
                    acc_number,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'pending', ?)
            """, (
                user.id,
                amount,
                acc_name,
                acc_number,
                now
            ))

            w_id = cur.lastrowid

            conn.commit()

        except Exception as e:

            conn.rollback()
            conn.close()

            logging.error(
                f"Withdrawal error: {e}"
            )

            await update.message.reply_text(
                "❌ Withdrawal ሲመዘገብ ችግኝ ተፈጥሯል።"
            )

            return

        conn.close()

        context.user_data.clear()

        await send_staff_message(
            context,
            (f"💸 <b>Withdrawal Request</b>\n\n🆔 User: <code>{user.id}</code>\n👤 {html.escape(user.first_name or '')}\n💰 <code>{amount:.2f}</code> ብር\n👤 Name: <code>{html.escape(acc_name)}</code>\n📱 Account: <code>{html.escape(acc_number)}</code>\n🆔 Withdrawal: <code>{w_id}</code>\n\n"
             "💳 ክፍያውን ካስተላለፉ በኋላ Payment Screenshot ላክ ይጫኑ።\n"
             "⚠️ Screenshot የሚላከው Admin/Manager ብቻ ነው።"),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📸 Payment Screenshot ላክ", callback_data=f"w_proof:{w_id}")
            ],[
                InlineKeyboardButton("❌ Reject", callback_data=f"w_reject:{w_id}")
            ]]),
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ Withdrawal ጥያቄዎ ለAdmin ተልኳል። ክፍያው ሲፈጸም Admin የክፍያ Screenshot ይልክልዎታል።")
        return

    # ========================================================
    # BID
    # ========================================================

    selected_auction_id = context.user_data.get(
        "selected_auction_id"
    )

    if selected_auction_id:

        try:

            bid_amount = float(text)

            if bid_amount < 1:
                raise ValueError
            if round(bid_amount, 2) != bid_amount:
                raise ValueError

        except ValueError:

            await update.message.reply_text(
                "❌ Bid ቢያንስ 1 ብር እና ከነጥብ በኋላ 2 ቁጥር ብቻ ይሁን።"
            )

            return

        context.user_data.pop(
            "selected_auction_id",
            None
        )

        await process_bid(
            update,
            context,
            selected_auction_id,
            bid_amount
        )

        return

    await update.message.reply_text(
        "ቦቱን ለመጠቀም /start ይጫኑ።"
    )



# ============================================================
# KDM AVIATOR
# Added to the existing Auction Wallet without replacing it.
# Uses the SAME users.balance wallet.
# ============================================================

AVIATOR_STATE = {
    "round_id": None,
    "phase": "waiting",       # waiting / betting / flying / crashed
    "crash": 1.00,
    "flight_started": None,
    "multiplier": 1.00,
    "live_messages": {},  # user_id -> (chat_id, message_id)
    "live_last_text": {},  # user_id -> last rendered text
    # Per-round cache: avoids opening SQLite once for every player every second.
    "player_bets": {},     # user_id -> {bet_id, bet_amount, status, cashout_multiplier, payout}
    "total_players": 0,
    "total_bets": 0.0,
    "total_payout": 0.0,
    "cashed_out_count": 0,
}


def _aviator_house_edge():
    """Admin's live house edge for Aviator: the per-game value, overridden by the global house edge when the admin
    enabled it (same rule as webapp_api._cabinet_limits). Falls back to the old 30% only if the DB can't be read."""
    try:
        conn = db(); cur = conn.cursor()
        r = cur.execute("SELECT house_edge FROM cabinet_game_settings WHERE game_key='aviator'").fetchone()
        edge = float(r["house_edge"]) if r and r["house_edge"] is not None else 0.15
        try:
            import platform_controls as _pc
            c = _pc.get_controls(cur)
            if c["global_house_edge_enabled"]:
                edge = float(c["global_house_edge"])
        except Exception:
            pass
        conn.close()
        return min(0.95, max(0.0, edge))
    except Exception:
        return 0.15


def generate_aviator_crash_point():
    """Crash point with theoretical RTP = 1 - the admin's house edge (read fresh every round)."""
    rtp = 1.0 - _aviator_house_edge()
    u = random.random()

    # Probability mass at 1.00x so that P(crash >= x) = RTP / x for x >= 1.
    if u >= rtp or u <= 0:
        return 1.00
    multiplier = rtp / u
    return round(max(1.01, multiplier), 2)


def aviator_current_multiplier():
    if AVIATOR_STATE["phase"] != "flying" or not AVIATOR_STATE["flight_started"]:
        return 1.00

    elapsed = asyncio.get_running_loop().time() - AVIATOR_STATE["flight_started"]

    # IMPORTANT:
    # Do NOT cap the live multiplier at 10.00x.
    # The crash generator can produce values above 10x. If the live
    # multiplier is capped at 10x, a round whose crash point is >10x
    # can get stuck forever at 10.00x.
    #
    # Keep the same smooth growth rate, but let it continue past 10x.
    return round(1.00 + elapsed * 0.25, 2)


async def update_aviator_live_messages(application, final=False):
    """Update active Aviator boards with minimal DB work.

    IMPORTANT:
    - One aggregate state is kept in memory for the current round.
    - There is NO SQLite query per player per second.
    - Only the Telegram edit calls scale with the number of active boards.
    """
    messages = list(AVIATOR_STATE.get("live_messages", {}).items())
    rid = AVIATOR_STATE.get("round_id")
    phase = AVIATOR_STATE.get("phase")
    if not messages or not rid:
        return

    total_players = int(AVIATOR_STATE.get("total_players", 0))
    total_bets = float(AVIATOR_STATE.get("total_bets", 0.0))
    total_payout = float(AVIATOR_STATE.get("total_payout", 0.0))
    cashed_out_count = int(AVIATOR_STATE.get("cashed_out_count", 0))
    player_bets = AVIATOR_STATE.get("player_bets", {})

    if phase == "flying":
        current_m = aviator_current_multiplier()
    elif phase == "crashed":
        current_m = float(AVIATOR_STATE.get("crash") or 1.00)
    else:
        current_m = 1.00

    def money(v):
        return f"{float(v or 0):.2f}"

    # Only a small recent sample is shown; never build a million-line message.
    recent = list(player_bets.items())[-LIVE_MAX_RECENT_PLAYERS:]
    sample_lines = []
    for uid, b in recent:
        name = str(b.get("name") or uid)[:18]
        if b.get("status") == "cashed_out":
            sample_lines.append(
                f"✅ {name}: {money(b['bet_amount'])} → "
                f"{float(b['cashout_multiplier']):.2f}x = +{money(b['payout'])} ብር"
            )
        elif b.get("status") == "lost":
            sample_lines.append(f"💥 {name}: {money(b['bet_amount'])} → LOST")
        else:
            sample_lines.append(f"🎮 {name}: {money(b['bet_amount'])} ብር → LIVE")

    sample_text = "\n".join(sample_lines) or "👥 እስካሁን ምንም Bet የለም።"
    if total_players > LIVE_MAX_RECENT_PLAYERS:
        sample_text += f"\n\n… +{total_players - LIVE_MAX_RECENT_PLAYERS:,} ሌሎች players"

    if phase == "betting":
        phase_text = "🟢 **BETTING OPEN**"
    elif phase == "flying":
        phase_text = f"🚀 **{current_m:.2f}x**"
    elif phase == "crashed":
        phase_text = f"💥 **CRASH {float(AVIATOR_STATE['crash']):.2f}x**"
    else:
        phase_text = "⏳ ቀጣዩ round እየተዘጋጀ ነው"

    async def edit_one(user_id, chat_id, message_id):
        b = player_bets.get(user_id)

        text = (
            "✈️ **KDM Aviator LIVE**\n\n"
            f"{phase_text}\n"
            f"🎯 Round: `#{rid}`\n"
            f"👥 Players: `{total_players:,}`\n"
            f"💰 Total Bets: `{money(total_bets)}` ብር\n"
            f"💸 Total Paid: `{money(total_payout)}` ብር\n"
            f"🏆 Cashed Out: `{cashed_out_count:,}`\n\n"
            "📋 **Recent Players**\n"
            f"{sample_text}\n"
        )

        if b:
            text += f"\n👤 **የእኔ Bet:** `{money(b['bet_amount'])}` ብር"
            if b["status"] == "cashed_out":
                text += (
                    f"\n🎉 **ያሸነፉት:** `{money(b['payout'])}` ብር"
                    f"\n🚀 Cash Out: `{float(b['cashout_multiplier']):.2f}x`"
                )
            elif b["status"] == "placed" and phase == "flying":
                text += "\n⚠️ Crash ከመሆኑ በፊት CASH OUT ያድርጉ።"

        if phase == "betting":
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 BET", callback_data="aviator_bet")],
                [InlineKeyboardButton("🔙 ዋና ማውጫ", callback_data="main")]
            ])
        elif phase == "flying" and b and b["status"] == "placed":
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "💸 CASH OUT",
                    callback_data=f"aviator_cashout:{rid}:{int(b['bet_id'])}"
                )
            ]])
        elif phase == "flying":
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏳ LIVE", callback_data="aviator")]
            ])
        elif phase == "crashed":
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏳ ቀጣዩን round ይጠብቁ", callback_data="aviator")]
            ])
        else:
            markup = InlineKeyboardMarkup([])

        state_key = (
            phase, round(current_m, 2),
            total_players, round(total_bets, 2),
            round(total_payout, 2), cashed_out_count,
            b.get("bet_id") if b else None,
            b.get("status") if b else None,
            round(float(b.get("payout", 0) or 0), 2) if b else 0,
            repr(markup.inline_keyboard)
        )
        last = AVIATOR_STATE.setdefault("live_last_state", {}).get(user_id)
        if last == state_key and not final:
            return

        try:
            async with LIVE_EDIT_SEMAPHORE:
                await asyncio.wait_for(
                    application.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode="Markdown",
                        reply_markup=markup,
                    ),
                    timeout=LIVE_EDIT_TIMEOUT,
                )
            AVIATOR_STATE.setdefault("live_last_state", {})[user_id] = state_key
        except Exception as e:
            err_text = str(e).lower()
            logging.warning(
                f"Aviator live edit failed for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )

            # If the Telegram message/chat was deleted or is no longer
            # editable, stop retrying it every second.
            dead_markers = (
                "message to edit not found",
                "chat not found",
                "message can't be edited",
                "message is too old",
                "have no rights",
                "bot was blocked",
            )
            if any(marker in err_text for marker in dead_markers):
                AVIATOR_STATE.get("live_messages", {}).pop(user_id, None)
                AVIATOR_STATE.get("live_last_state", {}).pop(user_id, None)

    # IMPORTANT for high traffic:
    # Never create one asyncio task per user at once. With hundreds of
    # thousands/millions of live boards that would exhaust RAM and the event
    # loop. Process bounded batches instead.
    batch_size = max(1, int(LIVE_EDIT_BATCH_SIZE))
    for start in range(0, len(messages), batch_size):
        batch = messages[start:start + batch_size]
        results = await asyncio.gather(
            *(edit_one(uid, chat_id, msg_id) for uid, (chat_id, msg_id) in batch),
            return_exceptions=True,
        )

        # Yield to Telegram polling and other bot work between batches.
        await asyncio.sleep(0)

    if final:
        AVIATOR_STATE.setdefault("live_last_state", {}).clear()

def aviator_status_text(user_id):
    conn = db()
    cur = conn.cursor()
    rid = AVIATOR_STATE.get("round_id")
    my_bet = None
    if rid:
        cur.execute("""
            SELECT * FROM aviator_bets
            WHERE round_id=? AND user_id=? AND status='placed'
            ORDER BY bet_id DESC LIMIT 1
        """, (rid, user_id))
        my_bet = cur.fetchone()
    conn.close()

    balance = get_balance(user_id)
    phase = AVIATOR_STATE.get("phase")
    if phase == "betting":
        status = "🟢 ውርርድ መቀበል ላይ ነው"
    elif phase == "flying":
        status = f"🚀 በረራ: **{aviator_current_multiplier():.2f}x**"
    elif phase == "crashed":
        status = f"💥 Crash: **{AVIATOR_STATE['crash']:.2f}x**"
    else:
        status = "⏳ ቀጣዩ ራውንድ እየተዘጋጀ ነው"

    text = (
        "✈️ **KDM Aviator**\n\n"
        f"{status}\n"
        f"💰 Wallet: `{balance:.2f}` ብር\n"
        f"🎯 Round: `#{rid or '---'}`\n"
    )
    if my_bet:
        text += f"\n💵 ያስገቡት Bet: `{float(my_bet['bet_amount']):.2f}` ብር"
    if phase == "betting":
        text += "\n\nBet ለማስገባት ከታች ያለውን ቁልፍ ይጫኑ።"
    elif phase == "flying" and my_bet:
        text += "\n\n⚠️ Crash ከመሆኑ በፊት Cash Out ያድርጉ።"
    return text


async def show_aviator(update, context):
    q = update.callback_query
    if q:
        await q.answer()
    else:
        await update.message.reply_text("✈️ Aviator ለመክፈት /start ይጫኑ።")
        return

    kb = []
    if AVIATOR_STATE["phase"] == "betting":
        kb.append([InlineKeyboardButton("💰 Bet አስገባ", callback_data="aviator_bet")])
    if AVIATOR_STATE["phase"] == "flying":
        rid = AVIATOR_STATE.get("round_id")
        # Only show CASH OUT when this user has an active bet.
        conn = db(); cur = conn.cursor()
        cur.execute("""
            SELECT bet_id FROM aviator_bets
            WHERE round_id=? AND user_id=? AND status='placed'
            ORDER BY bet_id DESC LIMIT 1
        """, (rid, q.from_user.id))
        current_bet = cur.fetchone()
        conn.close()
        if current_bet:
            kb.append([InlineKeyboardButton(
                "💸 CASH OUT",
                callback_data=f"aviator_cashout:{rid}:{int(current_bet['bet_id'])}"
            )])
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="aviator")])
    kb.append([InlineKeyboardButton("🔙 ዋና ማውጫ", callback_data="main")])

    await q.edit_message_text(
        aviator_status_text(q.from_user.id),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    # Register this message for live multiplier updates during flight.
    if AVIATOR_STATE.get("phase") == "flying" and q.message:
        AVIATOR_STATE.setdefault("live_messages", {})[q.from_user.id] = (q.message.chat_id, q.message.message_id)
        AVIATOR_STATE.setdefault("live_last_state", {}).pop(q.from_user.id, None)


async def aviator_ask_bet(update, context):
    q = update.callback_query
    await q.answer()
    if AVIATOR_STATE["phase"] != "betting":
        await q.answer("❌ አሁን Bet መጫን አይቻልም።", show_alert=True)
        return
    context.user_data.clear()
    context.user_data["aviator_waiting_bet"] = True
    await q.edit_message_text(
        "✈️ **KDM Aviator**\n\n💰 የሚወርዱትን Bet ብር ያስገቡ።\n\nለመሰረዝ /cancel ይጻፉ።",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Aviator", callback_data="aviator")]])
    )


async def process_aviator_bet(update, context, amount):
    user = update.effective_user
    rid = AVIATOR_STATE.get("round_id")
    if AVIATOR_STATE["phase"] != "betting" or not rid:
        await update.message.reply_text("❌ የBet ጊዜው አልፏል።")
        return
    if amount <= 0:
        await update.message.reply_text("❌ ከ0 በላይ የሆነ Bet ያስገቡ።")
        return

    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
        row = cur.fetchone()
        balance = float(row["balance"] or 0) if row else 0.0
        if balance < amount:
            conn.rollback(); conn.close()
            await update.message.reply_text(f"❌ Wallet በቂ አይደለም።\n💰 Wallet: `{balance:.2f}` ብር", parse_mode="Markdown")
            return

        cur.execute("""
            UPDATE users SET balance=balance-?
            WHERE user_id=? AND balance>=?
        """, (amount, user.id, amount))
        if cur.rowcount != 1:
            conn.rollback(); conn.close()
            await update.message.reply_text("❌ Wallet በቂ አይደለም።")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO aviator_bets(round_id,user_id,bet_amount,status,created_at)
            VALUES(?,?,?,'placed',?)
        """, (rid, user.id, amount, now))
        bet_id = cur.lastrowid
        cur.execute("""
            INSERT INTO transactions(user_id,amount,transaction_type,created_at)
            VALUES(?,?,?,?)
        """, (user.id, -amount, "aviator_bet", now))
        conn.commit()

        # Update in-memory live cache: no DB read is needed for the next
        # 1-second live tick.
        AVIATOR_STATE.setdefault("player_bets", {})[user.id] = {
            "bet_id": int(bet_id),
            "bet_amount": float(amount),
            "status": "placed",
            "cashout_multiplier": None,
            "payout": 0.0,
            "name": user.first_name or user.username or str(user.id),
        }
        AVIATOR_STATE["total_players"] = len(AVIATOR_STATE["player_bets"])
        AVIATOR_STATE["total_bets"] = float(AVIATOR_STATE.get("total_bets", 0.0)) + float(amount)
        AVIATOR_STATE.setdefault("live_last_state", {}).clear()

    except Exception as e:
        conn.rollback(); logging.error(f"Aviator bet error: {e}")
        await update.message.reply_text("❌ Aviator Bet ሲመዘገብ ችግኝ ተፈጥሯል።")
        return
    finally:
        try: conn.close()
        except Exception: pass

    context.user_data.clear()
    await update.message.reply_text(
        f"✅ **Bet ተመዝግቧል!**\n\n🎯 Round: `#{rid}`\n💰 Bet: `{amount:.2f}` ብር\n💳 Wallet: `{get_balance(user.id):.2f}` ብር",
        parse_mode="Markdown"
    )
    # Immediately open a live Aviator board for this bettor.
    live_msg = await update.message.reply_text(
        aviator_status_text(user.id),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💸 CASH OUT", callback_data=f"aviator_cashout:{rid}:{int(bet_id)}")]])
    )
    AVIATOR_STATE.setdefault("live_messages", {})[user.id] = (live_msg.chat_id, live_msg.message_id)
    AVIATOR_STATE.setdefault("live_last_state", {}).pop(user.id, None)
    # Render the complete round board immediately for this bettor.
    try:
        await update_aviator_live_messages(context.application)
    except Exception as e:
        logging.warning(f"Immediate Aviator bet live refresh failed: {e}")
    # Keep the live Aviator board visible; do not replace it with the main menu.


async def aviator_cashout(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    rid = int(parts[1])
    requested_bet_id = int(parts[2]) if len(parts) > 2 else None
    if AVIATOR_STATE.get("round_id") != rid or AVIATOR_STATE.get("phase") != "flying":
        await q.answer("❌ ይህ round አልነቃም።", show_alert=True)
        return

    multiplier = aviator_current_multiplier()
    if multiplier >= float(AVIATOR_STATE["crash"]):
        await q.answer("💥 Crash ሆኗል።", show_alert=True)
        return

    user_id = q.from_user.id
    conn = db(); cur = conn.cursor()
    if requested_bet_id is not None:
        cur.execute("""
            SELECT * FROM aviator_bets
            WHERE bet_id=? AND round_id=? AND user_id=? AND status='placed'
        """, (requested_bet_id, rid, user_id))
    else:
        cur.execute("""
            SELECT * FROM aviator_bets
            WHERE round_id=? AND user_id=? AND status='placed'
            ORDER BY bet_id DESC LIMIT 1
        """, (rid, user_id))
    bet = cur.fetchone()
    if not bet:
        conn.close()
        await q.answer("❌ ንቁ Bet የለዎትም።", show_alert=True)
        return

    payout = round(float(bet["bet_amount"]) * multiplier, 2)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cur.execute("""
            UPDATE aviator_bets
            SET status='cashed_out', cashout_multiplier=?, payout=?
            WHERE bet_id=? AND status='placed'
        """, (multiplier, payout, bet["bet_id"]))
        if cur.rowcount != 1:
            conn.rollback(); conn.close()
            await q.answer("❌ Bet ቀድሞ ተሰርቷል።", show_alert=True)
            return
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (payout, user_id))
        cur.execute("""
            INSERT INTO transactions(user_id,amount,transaction_type,created_at)
            VALUES(?,?,?,?)
        """, (user_id, payout, "aviator_win", now))
        conn.commit()
    except Exception as e:
        conn.rollback(); logging.error(f"Aviator cashout error: {e}")
        conn.close()
        await q.answer("❌ Cash Out አልተሳካም።", show_alert=True)
        return
    conn.close()

    # Update in-memory state immediately so every live board sees the
    # cash-out on the next edit without a per-user DB query.
    cached = AVIATOR_STATE.setdefault("player_bets", {}).get(user_id)
    if cached and int(cached.get("bet_id", 0)) == int(bet["bet_id"]):
        cached["status"] = "cashed_out"
        cached["cashout_multiplier"] = float(multiplier)
        cached["payout"] = float(payout)
    else:
        # Fallback if the process restarted or cache was missing.
        AVIATOR_STATE.setdefault("player_bets", {})[user_id] = {
            "bet_id": int(bet["bet_id"]),
            "bet_amount": float(bet["bet_amount"]),
            "status": "cashed_out",
            "cashout_multiplier": float(multiplier),
            "payout": float(payout),
            "name": q.from_user.first_name or q.from_user.username or str(user_id),
        }
    AVIATOR_STATE["total_payout"] = float(AVIATOR_STATE.get("total_payout", 0.0)) + float(payout)
    AVIATOR_STATE["cashed_out_count"] = int(AVIATOR_STATE.get("cashed_out_count", 0)) + 1

    # Immediately refresh EVERY active player's board. The same Telegram
    # messages are edited, so the winner and new totals appear without Refresh.
    AVIATOR_STATE.setdefault("live_last_state", {}).clear()
    try:
        await update_aviator_live_messages(context.application)
    except Exception as e:
        logging.warning(f"Immediate Aviator cashout live refresh failed: {e}")

    await q.answer(
        f"🎉 Cash Out {payout:.2f} ብር ተከፍሏል።",
        show_alert=True
    )



async def aviator_admin_stats(update, context):
    q = update.callback_query
    await q.answer()
    if not is_staff(q.from_user.id):
        return
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) cnt, AVG(crash_multiplier) avg_crash FROM aviator_rounds WHERE status='crashed'")
    r = cur.fetchone()
    cur.execute("SELECT COALESCE(SUM(bet_amount),0) total_bets, COALESCE(SUM(payout),0) total_payout FROM aviator_bets")
    f = cur.fetchone()
    conn.close()
    await q.edit_message_text(
        f"✈️ **Aviator Statistics**\n\n"
        f"📊 Rounds: `{r['cnt'] or 0}`\n"
        f"📈 Average Crash: `{float(r['avg_crash'] or 0):.2f}x`\n"
        f"💰 Total Bets: `{float(f['total_bets'] or 0):.2f}` ብር\n"
        f"💸 Total Payout: `{float(f['total_payout'] or 0):.2f}` ብር",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]])
    )


async def run_aviator_loop(application):
    """Continuous Aviator engine. Existing player boards follow every phase automatically."""
    while True:
        try:
            conn = db()
            cur = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            crash = generate_aviator_crash_point()
            cur.execute("""
                INSERT INTO aviator_rounds(crash_multiplier,status,created_at)
                VALUES(0,'betting',?)
            """, (now,))
            rid = cur.lastrowid
            conn.commit()
            conn.close()

            AVIATOR_STATE.update({
                "round_id": rid,
                "phase": "betting",
                "crash": crash,
                "flight_started": None,
                "multiplier": 1.00,
                "live_last_state": {},
                "player_bets": {},
                "total_players": 0,
                "total_bets": 0.0,
                "total_payout": 0.0,
                "cashed_out_count": 0,
            })

            # Immediately show BETTING on every existing live board.
            await update_aviator_live_messages(application)
            betting_end = asyncio.get_running_loop().time() + 10.0

            # During betting, keep the same Telegram board alive.
            while asyncio.get_running_loop().time() < betting_end:
                await update_aviator_live_messages(application)
                await asyncio.sleep(1.0)

            if AVIATOR_STATE.get("round_id") != rid:
                continue

            AVIATOR_STATE["phase"] = "flying"
            AVIATOR_STATE["flight_started"] = asyncio.get_running_loop().time()

            # First LIVE edit happens immediately when flight starts.
            while AVIATOR_STATE["phase"] == "flying":
                m = aviator_current_multiplier()
                AVIATOR_STATE["multiplier"] = m

                if m >= crash:
                    break

                await update_aviator_live_messages(application)
                await asyncio.sleep(1.0)

            AVIATOR_STATE["multiplier"] = crash
            AVIATOR_STATE["phase"] = "crashed"

            conn = db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE aviator_rounds
                SET crash_multiplier=?, status='crashed', crashed_at=?
                WHERE round_id=?
            """, (
                crash,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                rid
            ))
            cur.execute("""
                UPDATE aviator_bets SET status='lost'
                WHERE round_id=? AND status='placed'
            """, (rid,))
            conn.commit()
            conn.close()

            # Update in-memory cache after crash; no DB reads are needed for
            # the final crash screen.
            for cached in AVIATOR_STATE.setdefault("player_bets", {}).values():
                if cached.get("status") == "placed":
                    cached["status"] = "lost"

            # Show CRASH immediately; do not delete the player's live board.
            await update_aviator_live_messages(application, final=True)

            # Short crash display, then the SAME message changes to the next
            # round's BETTING screen. No user Refresh is required.
            await asyncio.sleep(3)
            # The next loop iteration reuses the SAME Telegram messages.
            AVIATOR_STATE.setdefault("live_last_state", {}).clear()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Aviator loop error: {e}")
            await asyncio.sleep(3)


# ============================================================
# ADMIN PANEL FROM MESSAGE
# ============================================================

BOT_ADMIN_PIN_TTL = 15 * 60

# Deposit/withdraw approve+reject buttons are exempt from the PIN prompt by default (staff check still
# applies). Set BOT_PAYMENT_ACTIONS_REQUIRE_PIN=1 in .env to require /adminpin for them again.
BOT_PAYMENT_ACTIONS_REQUIRE_PIN = os.getenv("BOT_PAYMENT_ACTIONS_REQUIRE_PIN", "1") == "1"

def bot_admin_pin_ok(context):
    # No PIN configured -> same behaviour as the Mini App API (staff check only). Previously this returned
    # False, so EVERY admin button said "Admin PIN needed" and /adminpin could never succeed.
    if not ADMIN_PANEL_PIN:
        return True
    return float(context.user_data.get("admin_pin_verified_until", 0) or 0) > time.time()

async def admin_pin_command(update, context):
    if not is_staff(update.effective_user.id):
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("🔐 /adminpin በprivate chat ብቻ ይጠቀሙ።")
        return
    pin = " ".join(context.args).strip()
    if not pin:
        context.user_data["waiting_admin_pin"] = True
        await update.message.reply_text("🔐 Admin PIN ያስገቡ። PIN ከመረጃ ማስታወሻ ጋር አትላኩ፤ ከተቻለ የTelegram message ን ያጥፉ።")
        return
    if not hmac.compare_digest(pin.encode("utf-8"), ADMIN_PANEL_PIN.encode("utf-8")):
        await update.message.reply_text("❌ የAdmin PIN ስህተት ነው።")
        return
    context.user_data["admin_pin_verified_until"] = time.time() + BOT_ADMIN_PIN_TTL
    context.user_data.pop("waiting_admin_pin", None)
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.message.reply_text("✅ Admin PIN ተረጋግጧል። ለ15 ደቂቃ የAdmin/Manager actions ክፍት ናቸው።")

def bot_admin_sensitive_ok(user_id, context):
    return is_staff(user_id) and bot_admin_pin_ok(context)

async def admin_panel_handler_from_message(
    update,
    context
):

    if not bot_admin_sensitive_ok(update.effective_user.id, context):
        await update.message.reply_text("🔐 Admin PIN አስገብተው /adminpin ይጠቀሙ።")
        return

    keyboard = [

        [
            InlineKeyboardButton(
                "➕ አዲስ ጨረታ መፍጠር",
                callback_data="admin_create_auction"
            )
        ],

        [
            InlineKeyboardButton(
                "🎯 ንቁ ጨረታዎች",
                callback_data="admin_manage_auctions"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 የተጠናቀቁ ጨረታዎች",
                callback_data="admin_results"
            )
        ],
        [InlineKeyboardButton("👥 Users / Bot ተጠቃሚዎች", callback_data="admin_users:0")],
        [InlineKeyboardButton("📢 ማስታወቂያ Post ላክ", callback_data="admin_announcement")],
        *([[InlineKeyboardButton("👥 Manager አስተዳደር", callback_data="admin_managers")]] if is_admin(update.effective_user.id) else []),

        [
            InlineKeyboardButton(
                "🔙 ዋና ማውጫ",
                callback_data="main"
            )
        ]
    ]

    await update.message.reply_text(
        "👑 **አድሚን ፓነል**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# SUPPORT INBOX
# ============================================================

async def support_inbox(update, context):
    q=update.callback_query; await q.answer()
    if not is_staff(q.from_user.id): return
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT sm.user_id, sm.created_at, sm.content_type, u.first_name, u.username FROM support_messages sm LEFT JOIN users u ON u.user_id=sm.user_id WHERE sm.direction='user_to_admin' ORDER BY sm.admin_message_id DESC LIMIT 20")
    rows=cur.fetchall(); conn.close()
    lines=["📩 **Support Messages — የተጫዋቾች መልዕክት**",""]
    kb=[]
    seen=set()
    for r in rows:
        uid=int(r["user_id"])
        if uid in seen: continue
        seen.add(uid)
        lines.append(f"👤 {r['first_name'] or 'N/A'} | `{uid}` | 🕒 `{r['created_at']}`")
        kb.append([InlineKeyboardButton(f"↩️ Reply: {r['first_name'] or uid}", callback_data=f"support_reply:{uid}")])
    if not rows: lines.append("📭 አዲስ Support Message የለም።")
    kb.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ============================================================
# ADMIN CALLBACKS
# ============================================================

async def admin_callback(update, context):

    query = update.callback_query

    if not is_staff(query.from_user.id):
        await query.answer()
        return

    data = query.data

    # --------------------------------------------------------
    # APPROVE PAYMENT
    # --------------------------------------------------------

    if data.startswith("approve:"):

        payment_id = int(
            data.split(":")[1]
        )

        payment, result = approve_payment(
            payment_id
        )

        if result == "approved":

            await query.answer(
                "✅ Payment approved"
            )

            await context.bot.send_message(
                chat_id=payment["user_id"],
                text=(
                    f"✅ ክፍያዎ ተረጋግጧል።\n\n"
                    f"💰 `{payment['amount']:.2f}` ብር "
                    f"ወደ Wallet ገብቷል።"
                ),
                parse_mode="Markdown"
            )

            await query.edit_message_caption(
                caption=(
                    f"✅ APPROVED\n"
                    f"User: {payment['user_id']}\n"
                    f"Amount: {payment['amount']} ብር"
                )
            )

        elif result == "provider_verification_required":
            await query.answer("⚠️ Chapa ክፍያ በChapa verify ብቻ ይጸድቃል።", show_alert=True)

        else:
            await query.answer("⚠️ ቀድሞ ተሰርቷል።", show_alert=True)

    # --------------------------------------------------------
    # REJECT PAYMENT
    # --------------------------------------------------------

    elif data.startswith("reject:"):

        payment_id = int(
            data.split(":")[1]
        )

        payment, result = reject_payment(
            payment_id
        )

        if result == "rejected":

            await query.answer(
                "❌ Payment rejected"
            )

            await context.bot.send_message(
                chat_id=payment["user_id"],
                text=(
                    "❌ የላኩት የክፍያ Screenshot "
                    "ውድቅ ተደርጓል።"
                )
            )

            await query.edit_message_caption(
                caption=(
                    f"❌ REJECTED\n"
                    f"User: {payment['user_id']}"
                )
            )

        else:

            await query.answer(
                "⚠️ ቀድሞ ተሰርቷል።",
                show_alert=True
            )

    # --------------------------------------------------------
    # ADMIN SENDS WITHDRAWAL PAYMENT PROOF
    # --------------------------------------------------------

    elif data.startswith("w_proof:"):
        w_id = int(data.split(":")[1])
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM withdrawals WHERE id=?", (w_id,))
        w = cur.fetchone()
        conn.close()
        if not w or w["status"] != "pending":
            await query.answer("⚠️ Withdrawal ቀድሞ ተጠናቋል።", show_alert=True)
            return
        context.user_data["admin_withdraw_proof_id"] = w_id
        await query.answer("📸 አሁን የክፍያ Screenshot ይላኩ።")
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=(f"📸 Withdrawal #{w_id}\n\n"
                  f"👤 User: `{w['user_id']}`\n"
                  f"💰 Amount: `{w['amount']:.2f}` ብር\n"
                  f"👤 Name: `{w['acc_name']}`\n"
                  f"📱 Account: `{w['acc_number']}`\n\n"
                  "➡️ አሁን የተፈጸመውን የክፍያ Screenshot እዚህ ይላኩ።"),
            parse_mode="Markdown"
        )
        return

    # --------------------------------------------------------
    # APPROVE WITHDRAW
    # Withdrawal requests already reserve/debit the wallet and add one
    # negative `withdraw` ledger row at creation. Approval only changes
    # the pending status; it must never debit the balance a second time.
    # --------------------------------------------------------

    elif data.startswith("w_approve:"):
        try:
            w_id = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            await query.answer("❌ Withdrawal ID ትክክል አይደለም።", show_alert=True)
            return

        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            cur.execute("SELECT * FROM withdrawals WHERE id=?", (w_id,))
            w = cur.fetchone()
            if not w or w["status"] != "pending":
                conn.rollback()
                await query.answer("⚠️ ቀድሞ ተሰርቷል ወይም አልተገኘም።", show_alert=True)
                return

            cur.execute("UPDATE withdrawals SET status='approved' WHERE id=? AND status='pending'", (w_id,))
            if cur.rowcount != 1:
                conn.rollback()
                await query.answer("⚠️ ቀድሞ ተሰርቷል።", show_alert=True)
                return
            conn.commit()
        except Exception:
            conn.rollback()
            logging.exception("Withdrawal approval failed for id=%s", w_id)
            await query.answer("❌ Withdrawal ማጽደቅ አልተቻለም።", show_alert=True)
            return
        finally:
            conn.close()

        await query.answer("✅ Withdrawal approved")
        try:
            await context.bot.send_message(
                chat_id=w["user_id"],
                text=(f"✅ Withdrawal ተጠናቋል / Approved.\n\n"
                      f"🆔 Withdrawal: `{w_id}`\n"
                      f"💰 `{w['amount']:.2f}` ብር\n\n"
                      "ℹ️ የWithdrawal መጠኑ ከWallet ቀድሞ ተቀንሷል።"),
                parse_mode="Markdown"
            )
        except Exception:
            logging.exception("Could not notify user about approved withdrawal id=%s", w_id)

        try:
            await query.edit_message_text(
                f"✅ WITHDRAW APPROVED\nUser: {w['user_id']}\nAmount: {w['amount']:.2f} ብር"
            )
        except Exception:
            pass

    # --------------------------------------------------------
    # REJECT WITHDRAW
    # --------------------------------------------------------

    elif data.startswith("w_reject:"):

        w_id = int(
            data.split(":")[1]
        )

        conn = db()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM withdrawals WHERE id = ?",
            (w_id,)
        )

        w = cur.fetchone()

        if w and w["status"] == "pending":

            cur.execute("BEGIN IMMEDIATE")
            cur.execute("""
                UPDATE withdrawals
                SET status = 'rejected'
                WHERE id = ? AND status = 'pending'
            """, (w_id,))
            if cur.rowcount != 1:
                conn.rollback(); conn.close()
                await query.answer("⚠️ Withdrawal ቀድሞ ተሰርቷል።", show_alert=True)
                return
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (w["amount"], w["user_id"]))
            if cur.rowcount != 1:
                conn.rollback(); conn.close()
                await query.answer("❌ User wallet አልተገኘም።", show_alert=True)
                return
            cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (w["user_id"], w["amount"], "withdraw_refund", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

            await query.answer(
                "❌ Withdrawal rejected"
            )

            await context.bot.send_message(
                chat_id=w["user_id"],
                text=(
                    f"❌ Withdrawal ውድቅ ተደርጓል።\n\n"
                    f"💰 `{w['amount']}` ብር "
                    f"ወደ Wallet ተመልሷል።"
                ),
                parse_mode="Markdown"
            )

            await query.edit_message_text(
                (
                    f"❌ WITHDRAW REJECTED\n"
                    f"User: {w['user_id']}\n"
                    f"Amount: {w['amount']} ብር"
                )
            )

        else:

            conn.close()

            await query.answer(
                "⚠️ ቀድሞ ተሰርቷል።",
                show_alert=True
            )


# ============================================================
# CALLBACK ROUTER
# ============================================================


# ============================================================
# EXTRA GROUP GAMES (PTB INTEGRATION)
# Converted from the supplied telebot version so the project
# keeps ONE Telegram framework (python-telegram-bot).
# ============================================================

EXTRA_BET_AMOUNT = 10.0
EXTRA_GROUP_GAMES = {}
EXTRA_NUMBER_GAMES = {}

# Real-player-only mode. Demo/fake players are not used in these games.
EXTRA_BOTS_ENABLED = False
EXTRA_BOT_COUNT = 0

# Admin-controlled game presentation/settings.
# reward_points are points only; they are NOT connected to cash payouts.
EXTRA_GAME_SETTINGS = {
    "nku": {"name": "🎯 Nku Game", "enabled": True, "reward_points": 25},
    "avatar": {"name": "🧑 Avatar Game", "enabled": True, "reward_points": 25},
    "bomb": {"name": "💣 Bomb Game", "enabled": True, "reward_points": 25},
    "number": {"name": "🔢 Number Game", "enabled": True, "reward_points": 50},
}

def game_setting_enabled(key):
    return bool(EXTRA_GAME_SETTINGS.get(key, {}).get("enabled", False))

def game_reward_points(key):
    return int(EXTRA_GAME_SETTINGS.get(key, {}).get("reward_points", 0))

async def admin_bots_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ ይህ ትዕዛዝ Admin ብቻ ነው።")
        return
    await update.message.reply_text("🤖 Fake/Demo Players በዚህ version ጠፍተዋል።\n👥 Real Players ብቻ ይታያሉ።")

async def admin_game_settings(update, context):
    q = update.callback_query
    await q.answer()
    if not is_staff(q.from_user.id):
        return

    lines = ["⚙️ **Game Settings**", ""]
    for key in ("nku", "avatar", "bomb", "number"):
        item = EXTRA_GAME_SETTINGS[key]
        state = "✅ ON" if item["enabled"] else "❌ OFF"
        lines.append(f"{item['name']}: {state} | Points: `{item['reward_points']}`")
    lines.append("")
    lines.append("Points የgame points ብቻ ናቸው፤ cash payout አያደርጉም።")

    kb = []
    for key in ("nku", "avatar", "bomb", "number"):
        item = EXTRA_GAME_SETTINGS[key]
        kb.append([
            InlineKeyboardButton(
                f"{item['name']} {'OFF' if item['enabled'] else 'ON'}",
                callback_data=f"admin_game_toggle:{key}"
            ),
            InlineKeyboardButton("➖", callback_data=f"admin_game_points:{key}:-5"),
            InlineKeyboardButton("➕", callback_data=f"admin_game_points:{key}:5"),
        ])
    kb.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def admin_game_toggle(update, context, key):
    q=update.callback_query
    await q.answer()
    if not is_staff(q.from_user.id):
        return
    if key in EXTRA_GAME_SETTINGS:
        EXTRA_GAME_SETTINGS[key]["enabled"] = not EXTRA_GAME_SETTINGS[key]["enabled"]
    await admin_game_settings(update, context)

async def admin_game_points(update, context, key, delta):
    q=update.callback_query
    await q.answer()
    if not is_staff(q.from_user.id):
        return
    if key in EXTRA_GAME_SETTINGS:
        EXTRA_GAME_SETTINGS[key]["reward_points"] = max(0, EXTRA_GAME_SETTINGS[key]["reward_points"] + delta)
    await admin_game_settings(update, context)

async def extra_games_menu(update, context):
    q = update.callback_query
    await q.answer()

    rows = []
    if game_setting_enabled("bomb"):
        rows.append([InlineKeyboardButton("👥 የግሩፕ ቦምብ", callback_data="game_gmines")])
    if game_setting_enabled("number"):
        rows.append([InlineKeyboardButton("🔢 የቁጥር ግምት", callback_data="game_numguess")])
    rows.append([InlineKeyboardButton("🔙 ዋና ማውጫ", callback_data="main")])
    kb = InlineKeyboardMarkup(rows)

    await q.edit_message_text(
        "🎮 **ተጨማሪ ጨዋታዎች**\n\n"
        f"👥 Real Players ብቻ\n"
        f"💰 እያንዳንዱ ጨዋታ: `{EXTRA_BET_AMOUNT:.0f}` ብር\n\n"
        "ከታች የሚፈልጉትን ይምረጡ።",
        parse_mode="Markdown",
        reply_markup=kb
    )


def _extra_balance(user_id):
    return get_balance(user_id)


async def start_group_mines(update, context):
    q = update.callback_query
    if not game_setting_enabled("bomb"):
        await q.answer("❌ Bomb Game በAdmin ተዘግቷል።", show_alert=True)
        return
    uid = q.from_user.id
    chat_id = q.message.chat_id

    if _extra_balance(uid) < EXTRA_BET_AMOUNT:
        await q.answer("❌ Wallet በቂ አይደለም።", show_alert=True)
        return

    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
            (EXTRA_BET_AMOUNT, uid, EXTRA_BET_AMOUNT)
        )
        if cur.rowcount != 1:
            conn.rollback()
            await q.answer("❌ Wallet በቂ አይደለም።", show_alert=True)
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """INSERT INTO transactions(user_id,amount,transaction_type,created_at)
               VALUES(?,?,?,?)""",
            (uid, -EXTRA_BET_AMOUNT, "group_mines_bet", now)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Group Mines start error")
        await q.answer("❌ ጨዋታው ሲጀመር ችግኝ ተፈጥሯል።", show_alert=True)
        return
    finally:
        conn.close()

    bombs = random.sample(range(1, 10), 3)

    EXTRA_GROUP_GAMES[chat_id] = {
        "bombs": bombs,
        "opened": [],
        "game_over": False,
        "players": {
            uid: {
                "name": q.from_user.first_name or "User",
                "bet": EXTRA_BET_AMOUNT,
                "status": "playing"
            }
        },
        "message_id": q.message.message_id,
        "started_at": time.time()
    }

    await _render_group_mines(context.bot, chat_id, q.message.message_id)


async def _render_group_mines(telegram_bot, chat_id, message_id):
    game = EXTRA_GROUP_GAMES.get(chat_id)
    if not game:
        return

    buttons = []
    for i in range(1, 10):
        if i in game["opened"]:
            buttons.append(
                InlineKeyboardButton("🎁", callback_data="extra_noop")
            )
        else:
            buttons.append(
                InlineKeyboardButton(str(i), callback_data=f"gmine_{i}")
            )

    rows = [buttons[i:i + 3] for i in range(0, 9, 3)]
    rows.append([
        InlineKeyboardButton(
            "🔙 ተጨማሪ ጨዋታዎች",
            callback_data="extra_games"
        )
    ])

    real_names = ", ".join(
        v.get("name", "User") for v in game["players"].values()
    ) or "—"

    status_lines = []
    for p in game["players"].values():
        status_lines.append(
            f"👤 {p.get('name', 'User')} — "
            f"{p.get('bet', EXTRA_BET_AMOUNT):.2f} ብር — "
            f"{p.get('status', 'playing')}"
        )

    elapsed = int(time.time() - game.get("started_at", time.time()))
    text = (
        "👥 **የግሩፕ ቦምብ — LIVE**\n\n"
        f"⏱ Live: `{elapsed}s`\n"
        f"💰 Bet: `{EXTRA_BET_AMOUNT:.2f}` ብር\n"
        f"👥 **Real Players: `{len(game['players'])}`**\n"
        f"⭐ Points: `{game_reward_points('bomb')}`\n"
        f"📝 {real_names}\n\n"
        "📋 **Players**\n"
        + ("\n".join(status_lines) or "—")
        + "\n\n"
        "⚠️ 9 ሳጥኖች ውስጥ 3 ቦምቦች አሉ።\n"
        "👇 ሳጥን ይምረጡ።"
    )

    try:
        await telegram_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )
    except Exception as e:
        logging.warning(f"Group Mines live render failed: {e}")


async def handle_group_mine(update, context):
    q = update.callback_query

    uid = q.from_user.id
    chat_id = q.message.chat_id
    game = EXTRA_GROUP_GAMES.get(chat_id)

    if not game or game["game_over"]:
        await q.answer(
            "❌ ጨዋታው አልቋል ወይም አይገኝም።",
            show_alert=True
        )
        return

    # A real user joins the shared round by paying the entry amount.
    if uid not in game["players"]:
        if _extra_balance(uid) < EXTRA_BET_AMOUNT:
            await q.answer(
                "❌ ለመግባት 10 ብር ያስፈልጋል።",
                show_alert=True
            )
            return

        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                "UPDATE users SET balance=balance-? "
                "WHERE user_id=? AND balance>=?",
                (EXTRA_BET_AMOUNT, uid, EXTRA_BET_AMOUNT)
            )
            if cur.rowcount != 1:
                conn.rollback()
                await q.answer(
                    "❌ Wallet በቂ አይደለም።",
                    show_alert=True
                )
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                """INSERT INTO transactions
                   (user_id,amount,transaction_type,created_at)
                   VALUES(?,?,?,?)""",
                (uid, -EXTRA_BET_AMOUNT, "group_mines_bet", now)
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logging.exception("Group Mines join error")
            await q.answer(
                "❌ ጨዋታው ላይ ሲገቡ ችግኝ ተፈጥሯል።",
                show_alert=True
            )
            return
        finally:
            conn.close()

        game["players"][uid] = {
            "name": q.from_user.first_name or "User",
            "bet": EXTRA_BET_AMOUNT,
            "status": "playing"
        }
        await q.answer("✅ ጨዋታው ላይ ገብተዋል።")

    try:
        box = int(q.data.split("_")[1])
    except Exception:
        return

    if box in game["opened"]:
        await q.answer("ይህ ሳጥን ተከፍቷል።", show_alert=True)
        return

    if box in game["bombs"]:
        game["game_over"] = True
        game["players"][uid]["status"] = "LOST"

        # All other real players who were still active also lose this round.
        for player_id, player in game["players"].items():
            if player_id != uid and player.get("status") == "playing":
                player["status"] = "LOST"

        await q.answer("💥 BOOM!", show_alert=True)

        names = "\n".join(
            f"👤 {p.get('name', 'User')} — {p.get('status', 'LOST')}"
            for p in game["players"].values()
        )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=q.message.message_id,
            text=(
                "💥 **BOOM! — Round ተጠናቀቀ**\n\n"
                f"👤 {q.from_user.first_name or 'User'} ቦምብ መታ።\n\n"
                "📋 **Real Players**\n"
                f"{names}\n\n"
                "❌ የዚህ round ያልተከፈቱ bets አልተመለሱም።"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🎮 ተጨማሪ ጨዋታዎች",
                    callback_data="extra_games"
                )],
                [InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )]
            ])
        )
        EXTRA_GROUP_GAMES.pop(chat_id, None)
        return

    game["opened"].append(box)
    await q.answer("🎁 ደህና ነው!")

    if len(game["opened"]) >= 6:
        winners = list(game["players"].keys())
        reward_per = EXTRA_BET_AMOUNT * 2.5

        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for winner_id in winners:
                game["players"][winner_id]["status"] = "WIN"
                cur.execute(
                    "UPDATE users SET balance=balance+? WHERE user_id=?",
                    (reward_per, winner_id)
                )
                cur.execute(
                    """INSERT INTO transactions
                       (user_id,amount,transaction_type,created_at)
                       VALUES(?,?,?,?)""",
                    (winner_id, reward_per, "group_mines_win", now)
                )

            conn.commit()
        except Exception:
            conn.rollback()
            logging.exception("Group Mines reward error")
            await q.answer(
                "❌ ክፍያው ሲፈጸም ችግኝ ተፈጥሯል።",
                show_alert=True
            )
            return
        finally:
            conn.close()

        names = "\n".join(
            f"👤 {p.get('name', 'User')} — {p.get('status', 'WIN')}"
            for p in game["players"].values()
        )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=q.message.message_id,
            text=(
                "🎉 **Round ተጠናቀቀ!**\n\n"
                "📋 **Real Players**\n"
                f"{names}\n\n"
                f"💰 እያንዳንዱ `{reward_per:.2f}` ብር ተከፍሏል።"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🎮 ተጨማሪ ጨዋታዎች",
                    callback_data="extra_games"
                )],
                [InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )]
            ])
        )
        EXTRA_GROUP_GAMES.pop(chat_id, None)
        return

    await _render_group_mines(
        context.bot,
        chat_id,
        q.message.message_id
    )


async def start_number_guess(update, context):
    q = update.callback_query
    if not game_setting_enabled("number"):
        await q.answer("❌ Number Game በAdmin ተዘግቷል።", show_alert=True)
        return
    uid = q.from_user.id

    if _extra_balance(uid) < EXTRA_BET_AMOUNT:
        await q.answer("❌ Wallet በቂ አይደለም።", show_alert=True)
        return

    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute(
            "UPDATE users SET balance=balance-? "
            "WHERE user_id=? AND balance>=?",
            (EXTRA_BET_AMOUNT, uid, EXTRA_BET_AMOUNT)
        )
        if cur.rowcount != 1:
            conn.rollback()
            await q.answer("❌ Wallet በቂ አይደለም።", show_alert=True)
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """INSERT INTO transactions
               (user_id,amount,transaction_type,created_at)
               VALUES(?,?,?,?)""",
            (uid, -EXTRA_BET_AMOUNT, "number_guess_bet", now)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Number Guess start error")
        await q.answer(
            "❌ ጨዋታው ሲጀመር ችግኝ ተፈጥሯል።",
            show_alert=True
        )
        return
    finally:
        conn.close()

    EXTRA_NUMBER_GAMES[q.message.chat_id] = {
        "secret": secrets.randbelow(15) + 1,
        "active": True,
        "players": {
            uid: {
                "name": q.from_user.first_name or "User",
                "bet": EXTRA_BET_AMOUNT,
                "status": "playing"
            }
        },
        "message_id": q.message.message_id,
        "started_at": time.time()
    }

    await _render_number_guess(
        context.bot,
        q.message.chat_id,
        q.message.message_id
    )


async def _render_number_guess(telegram_bot, chat_id, message_id):
    game = EXTRA_NUMBER_GAMES.get(chat_id)
    if not game:
        return

    buttons = [
        InlineKeyboardButton(
            str(i),
            callback_data=f"guess_{i}"
        )
        for i in range(1, 16)
    ]
    rows = [buttons[i:i + 5] for i in range(0, 15, 5)]
    rows.append([
        InlineKeyboardButton(
            "🔙 ተጨማሪ ጨዋታዎች",
            callback_data="extra_games"
        )
    ])

    players_text = "\n".join(
        f"👤 {p.get('name', 'User')} — "
        f"{p.get('bet', EXTRA_BET_AMOUNT):.2f} ብር — "
        f"{p.get('status', 'playing')}"
        for p in game["players"].values()
    ) or "—"

    elapsed = int(time.time() - game.get("started_at", time.time()))
    text = (
        "🔢 **የቁጥር ግምት — LIVE**\n\n"
        f"⏱ Live: `{elapsed}s`\n"
        "1–15 ውስጥ ያለውን ቁጥር ገምቱ።\n\n"
        f"👥 **Real Players: `{len(game['players'])}`\n"
        f"⭐ Points: `{game_reward_points('number')}`\n"
        f"{players_text}\n\n"
        "👇 ቁጥር ይምረጡ።"
    )

    try:
        await telegram_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )
    except Exception as e:
        logging.warning(f"Number Guess live render failed: {e}")


async def handle_number_guess(update, context):
    q = update.callback_query

    chat_id = q.message.chat_id
    uid = q.from_user.id
    game = EXTRA_NUMBER_GAMES.get(chat_id)

    if not game or not game["active"]:
        await q.answer("❌ ንቁ round የለም።", show_alert=True)
        return

    # New real players can join this round by paying the entry.
    if uid not in game["players"]:
        if _extra_balance(uid) < EXTRA_BET_AMOUNT:
            await q.answer(
                "❌ ለመግባት 10 ብር ያስፈልጋል።",
                show_alert=True
            )
            return

        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                "UPDATE users SET balance=balance-? "
                "WHERE user_id=? AND balance>=?",
                (EXTRA_BET_AMOUNT, uid, EXTRA_BET_AMOUNT)
            )
            if cur.rowcount != 1:
                conn.rollback()
                await q.answer(
                    "❌ Wallet በቂ አይደለም。",
                    show_alert=True
                )
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                """INSERT INTO transactions
                   (user_id,amount,transaction_type,created_at)
                   VALUES(?,?,?,?)""",
                (uid, -EXTRA_BET_AMOUNT, "number_guess_bet", now)
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logging.exception("Number Guess join error")
            await q.answer(
                "❌ ጨዋታው ላይ ሲገቡ ችግኝ ተፈጥሯል።",
                show_alert=True
            )
            return
        finally:
            conn.close()

        game["players"][uid] = {
            "name": q.from_user.first_name or "User",
            "bet": EXTRA_BET_AMOUNT,
            "status": "playing"
        }

    try:
        guess = int(q.data.split("_")[1])
    except Exception:
        return

    if guess == game["secret"]:
        game["active"] = False
        game["players"][uid]["status"] = "WIN"

        reward = 50.0
        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "UPDATE users SET balance=balance+? WHERE user_id=?",
                (reward, uid)
            )
            cur.execute(
                """INSERT INTO transactions
                   (user_id,amount,transaction_type,created_at)
                   VALUES(?,?,?,?)""",
                (uid, reward, "number_guess_win", now)
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logging.exception("Number Guess reward error")
            await q.answer(
                "❌ ክፍያው ሲፈጸም ችግኝ ተፈጥሯል።",
                show_alert=True
            )
            return
        finally:
            conn.close()

        await q.answer("🎉 ትክክል!", show_alert=True)

        players_text = "\n".join(
            f"👤 {p.get('name', 'User')} — {p.get('status', 'playing')}"
            for p in game["players"].values()
        )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=q.message.message_id,
            text=(
                "🎯 **ትክክለኛ ግምት!**\n\n"
                f"👤 አሸናፊ: {q.from_user.first_name or 'User'}\n"
                f"🔢 ቁጥሩ: `{game['secret']}`\n"
                f"🏆 Prize: `{reward:.2f}` ብር\n\n"
                "📋 **Real Players**\n"
                f"{players_text}"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔢 እንደገና",
                    callback_data="game_numguess"
                )],
                [InlineKeyboardButton(
                    "🔙 ዋና ማውጫ",
                    callback_data="main"
                )]
            ])
        )
        EXTRA_NUMBER_GAMES.pop(chat_id, None)
    else:
        hint = "▲ ከፍ ያድርጉ" if guess < game["secret"] else "▼ ዝቅ ያድርጉ"
        await q.answer(f"❌ {hint}", show_alert=True)

async def extra_games_live_tick(application):
    """Refresh active extra-game boards once per second using elapsed live time."""
    while True:
        try:
            for chat_id, game in list(EXTRA_GROUP_GAMES.items()):
                if not game.get("game_over"):
                    await _render_group_mines(application.bot, chat_id, game.get("message_id"))
            for chat_id, game in list(EXTRA_NUMBER_GAMES.items()):
                if game.get("active"):
                    await _render_number_guess(application.bot, chat_id, game.get("message_id"))
        except Exception as e:
            logging.warning(f"Extra games 1-second live tick failed: {e}")
        await asyncio.sleep(1)

async def callback_router(update, context):

    query = update.callback_query

    data = query.data
    payment_btn = data.startswith("approve:") or data.startswith("reject:") or data.startswith("w_approve:") or data.startswith("w_reject:")
    sensitive_admin = (data.startswith("admin_") or data.startswith("approve:") or data.startswith("reject:") or data.startswith("w_"))
    if payment_btn and not BOT_PAYMENT_ACTIONS_REQUIRE_PIN:
        sensitive_admin = False  # is_staff is still enforced inside the handlers
    if sensitive_admin and not bot_admin_sensitive_ok(query.from_user.id, context):
        await query.answer("🔐 Admin PIN አስፈላጊ ነው። /adminpin ይጠቀሙ።", show_alert=True)
        return

    if data == "extra_games":
        await extra_games_menu(update, context)
    elif data == "game_gmines":
        await start_group_mines(update, context)
    elif data.startswith("gmine_"):
        await handle_group_mine(update, context)
    elif data == "game_numguess":
        await start_number_guess(update, context)
    elif data.startswith("guess_"):
        await handle_number_guess(update, context)
    elif data == "extra_noop":
        await query.answer("🎁 ይህ ሳጥን ተከፍቷል።")
    elif data == "aviator":
        await show_aviator(update, context)
    elif data == "aviator_bet":
        await aviator_ask_bet(update, context)
    elif data.startswith("aviator_cashout:"):
        await aviator_cashout(update, context)
    elif data == "aviator_admin_stats":
        await aviator_admin_stats(update, context)
    elif data == "main":

        await query.answer()

        await start(
            update,
            context
        )

    elif data == "deposit":

        await show_deposit(
            update,
            context
        )

    elif data == "deposit_ask":

        await ask_amount(
            update,
            context
        )

    elif data == "withdraw":

        await show_withdraw(
            update,
            context
        )

    elif data == "balance":

        await show_balance(
            update,
            context
        )

    elif data == "history":

        await show_history(
            update,
            context
        )

    elif data == "auctions":

        await show_auctions(
            update,
            context
        )

    elif data == "mybids":

        await my_bids_command(
            update,
            context
        )

    elif data == "winners_history":

        await show_winners_history(
            update,
            context
        )


    # ========================================================
    # ADMIN
    # ========================================================

    elif data == "admin_panel":

        await admin_panel_handler(
            update,
            context
        )

    elif data == "admin_game_settings":
        await admin_game_settings(update, context)

    elif data.startswith("admin_game_toggle:"):
        await admin_game_toggle(update, context, data.split(":", 1)[1])

    elif data.startswith("admin_game_points:"):
        _, key, delta = data.split(":")
        await admin_game_points(update, context, key, int(delta))

    elif data == "admin_create_auction":

        await admin_create_auction(
            update,
            context
        )

    elif data == "admin_results":

        await admin_results(
            update,
            context
        )

    elif data == "admin_active_players":

        await admin_active_players(
            update,
            context
        )

    elif data == "admin_total_wallets":

        await admin_total_wallets(
            update,
            context
        )

    elif data == "admin_announcement":

        await admin_announcement(update, context)

    elif data == "support_start":
        await support_start(update, context)

    elif data == "support_inbox":
        await support_inbox(update, context)

    elif data.startswith("support_reply:"):
        await support_reply_start(update, context, int(data.split(":")[1]))

    elif data.startswith("admin_user_activity:"):
        await admin_user_activity(update, context, int(data.split(":")[1]))
    elif data.startswith("admin_users:"):
        await admin_users(update, context)
    elif data == "admin_managers":
        await admin_managers(update, context)
    elif data.startswith("manager_add:"):
        await set_manager(update, context, int(data.split(":")[1]), True)
    elif data.startswith("manager_remove:"):
        await set_manager(update, context, int(data.split(":")[1]), False)

    elif data.startswith("admin_post:"):
        await admin_post_auction(update, context)

    elif data.startswith("admin_post_edit:"):
        await admin_edit_auction_post(update, context)

    elif data.startswith("admin_post_delete:"):
        await admin_delete_auction_post(update, context)

    elif data.startswith("admin_sim_add:"):
        if not is_staff(query.from_user.id):
            await query.answer()
            return
        auction_id = int(data.split(":")[1])
        context.user_data.clear()
        context.user_data["waiting_admin_sim_count"] = True
        context.user_data["admin_sim_auction_id"] = auction_id
        await query.answer()
        await query.edit_message_text(
            f"🧪 **Auction #{auction_id} Simulation**\n\n"
            "ለAdmin ሙከራ የሚጨመሩትን የSimulation ተሳታፊዎች ብዛት ያስገቡ።\n\n"
            "⚠️ እነዚህ ከReal Users እና Real Bids ተለይተው ይቀመጣሉ፤ winner/wallet አይነኩም።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 አድሚን ፓነል", callback_data="admin_panel")]])
        )

    elif data == "admin_manage_auctions":

        await admin_manage_auctions(
            update,
            context
        )

    elif (
        data.startswith("admin_close:")
        or data.startswith("admin_extend:")
        or data.startswith("admin_delete:")
    ):

        await admin_auction_action_callback(
            update,
            context
        )

    elif data.startswith("select_auc:"):

        await select_auction_callback(
            update,
            context
        )

    elif (
        data.startswith("approve:")
        or data.startswith("reject:")
        or data.startswith("w_approve:")
        or data.startswith("w_reject:")
        or data.startswith("w_proof:")
    ):

        await admin_callback(
            update,
            context
        )

    elif data == "none":

        await query.answer()


# ============================================================
# CANCEL CURRENT PROCESS
# ============================================================

async def cancel_command(update, context):
    if context.user_data.get("waiting_admin_announcement"):
        context.user_data.clear(); await update.message.reply_text("❌ ማስታወቂያው ተሰርዟል።"); await admin_panel_handler_from_message(update, context); return
        context.user_data.clear(); await update.message.reply_text("❌ የAdmin / Manager መልዕክት ተሰርዟል።"); return
    context.user_data.clear(); await update.message.reply_text("❌ የአሁኑ ሂደት ተሰርዟል።")


# ============================================================
# MAIN
# ============================================================

async def post_init(application):
    application.bot_data["event_loop"] = asyncio.get_running_loop()
    await mini_app_server_start(application)
    # Put the Mini App in Telegram's chat-menu button as well as /start.
    try:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="King Bet 🥳",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        )
    except Exception as e:
        logging.warning(f"Could not set Telegram Mini App menu button: {e}")
    application.bot_data["aviator_task"] = asyncio.create_task(run_aviator_loop(application))
    application.bot_data["extra_games_live_task"] = asyncio.create_task(extra_games_live_tick(application))


async def post_shutdown(application):
    for key in ("aviator_task", "extra_games_live_task"):
        task = application.bot_data.pop(key, None)
        if task:
            task.cancel()
    await mini_app_server_stop(application)


def send_pending_withdrawal_reminders(application):
    """Remind staff about old pending withdrawals, at most every 30 minutes per request."""
    loop = application.bot_data.get("event_loop")
    if not loop or loop.is_closed():
        return
    now = datetime.now()
    stale_before = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    reminder_before = stale_before
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT id,user_id,amount,created_at FROM withdrawals WHERE status='pending' AND created_at<=? AND (staff_reminded_at IS NULL OR staff_reminded_at<=?) ORDER BY created_at LIMIT 50", (stale_before, reminder_before))
        rows = cur.fetchall()
    finally:
        conn.close()
    for row in rows:
        sent = False
        msg = (f"⏰ Withdrawal reminder\nRequest: {row['id']}\nUser: {row['user_id']}\n"
               f"Amount: {float(row['amount']):.2f} ብር\nCreated: {row['created_at']}\nStatus: still pending")
        for staff_id in get_manager_ids():
            try:
                future = asyncio.run_coroutine_threadsafe(application.bot.send_message(chat_id=staff_id, text=msg), loop)
                future.result(timeout=10)
                sent = True
            except Exception:
                logging.exception("pending withdrawal reminder failed for staff_id=%s withdrawal_id=%s", staff_id, row["id"])
        if sent:
            conn = db(); cur = conn.cursor()
            cur.execute("UPDATE withdrawals SET staff_reminded_at=? WHERE id=? AND status='pending'", (now.strftime("%Y-%m-%d %H:%M:%S"), row["id"]))
            conn.commit(); conn.close()


def main():

    init_db()

    required_runtime = {
        "BOT_TOKEN": BOT_TOKEN,
        "ADMIN_ID": str(ADMIN_ID or ""),
        "MINI_APP_URL": WEBAPP_URL,
        "ACCOUNT_NAME": ACCOUNT_NAME,
        "CBE_ACCOUNT": CBE_ACCOUNT,
        "BOA_ACCOUNT": BOA_ACCOUNT,
        "TELEBIRR_NUMBER": TELEBIRR_NUMBER,
        "ADMIN_PANEL_PIN": ADMIN_PANEL_PIN,
    }
    missing = [name for name, value in required_runtime.items() if not str(value).strip()]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    if ADMIN_ID <= 0:
        raise RuntimeError("ADMIN_ID must be a positive Telegram user id")
    if not WEBAPP_URL.startswith("https://"):
        raise RuntimeError("MINI_APP_URL must start with https:// in production")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        check_and_close_auctions,
        "interval",
        seconds=60,
        args=[app]
    )

    scheduler.add_job(
        send_hourly_admin_report,
        "interval",
        hours=1,
        args=[app]
    )

    scheduler.add_job(
        send_pending_withdrawal_reminders,
        "interval",
        minutes=15,
        args=[app],
        id="pending_withdrawal_reminders",
        replace_existing=True
    )

    scheduler.start()

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )
    app.add_handler(
        CommandHandler(
            "bots",
            admin_bots_command
        )
    )
    app.add_handler(
        CommandHandler(
            "adminpin",
            admin_pin_command
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
        )
    )

    app.add_handler(
        CommandHandler(
            "mybids",
            my_bids_command
        )
    )

    promo_init_tables()
    app.add_handler(CallbackQueryHandler(promo_callback, pattern=r"^(ap_|pv:)"))
    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    app.add_handler(MessageHandler(filters.ANIMATION, handle_animation))
    app.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video
        )
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print(
        "✅ Enhanced Auction Wallet Bot is running..."
    )

    app.run_polling()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()