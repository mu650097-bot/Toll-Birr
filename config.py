# ============================================================
# SHARED CONFIG
# Both kdm_bot.py (the Telegram bot) and webapp_api.py (the Mini App
# backend) import from this single file so they always agree on the
# bot token and the database file. Do not hardcode these values
# separately in either file -- edit them here only.
#
# SECURITY: secrets (bot token, admin id, bank/telebirr numbers) are
# now read from environment variables instead of being hardcoded, so
# they never end up in git history or get shared accidentally when
# this file is shown to anyone (support, a contractor, an AI tool,
# etc). Set them before running either process, e.g. in a .env file
# loaded by your process manager, or directly:
#
#   export BOT_TOKEN="<YOUR_NEW_BOT_TOKEN>"
#   export ADMIN_ID="<YOUR_TELEGRAM_ADMIN_ID>"
#   export ACCOUNT_NAME="Your Name"
#   export CBE_ACCOUNT="..."
#   export BOA_ACCOUNT="..."
#   export TELEBIRR_NUMBER="..."
#
# IMPORTANT: if a real bot token was ever exposed in source, chat, logs,
# or a shared package, revoke/regenerate it in @BotFather and use only
# the new token through the environment. Never place a token in comments.
# ============================================================

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it before starting the bot or the Mini App API."
        )
    return value


BOT_TOKEN = _require("BOT_TOKEN")
ANNOUNCEMENT_CHANNEL_ID = os.environ.get("ANNOUNCEMENT_CHANNEL_ID", "")

ADMIN_ID = int(_require("ADMIN_ID"))

ACCOUNT_NAME = _require("ACCOUNT_NAME")
CBE_ACCOUNT = _require("CBE_ACCOUNT")
BOA_ACCOUNT = _require("BOA_ACCOUNT")
TELEBIRR_NUMBER = _require("TELEBIRR_NUMBER")

DB_FILE = os.environ.get("DB_FILE", "auction_wallet.db")

# Public HTTPS URL where the Mini App frontend (index.html/app.js) is
# hosted. Telegram REQUIRES this to be a real https:// URL -- it will
# refuse to open a WebApp button pointing at http:// or localhost.
# Set this once you've deployed the frontend (see the Mini App
# deployment notes). Also env-configurable now because it's no longer
# just documentation -- webapp_api.py uses it to restrict CORS to
# this exact origin, so deploying to a different domain WITHOUT
# setting this would silently keep CORS locked to the old domain and
# every request from your real frontend would fail.
MINI_APP_URL = _require("MINI_APP_URL")
if not MINI_APP_URL.startswith("https://"):
    raise RuntimeError("MINI_APP_URL must start with https:// in production")
# Telegram only allows web_app buttons in PRIVATE chats. Fill this in
# with your bot's @username (no @) so group chats get a working
# deep-link fallback instead of a button Telegram would reject.
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip().lstrip("@").strip("/")  # "@Kingbirrbot" -> t.me/@Kingbirrbot = "Username not found"
# Direct-link Mini App short name (BotFather /newapp). Optional. Set MINI_APP_MAIN=1 instead if the Main Mini App is configured.
MINI_APP_SHORT_NAME = os.environ.get("MINI_APP_SHORT_NAME", "").strip().strip("/")
MINI_APP_MAIN = os.environ.get("MINI_APP_MAIN", "").strip().lower() in ("1", "true", "yes")

# Base URL where webapp_api.py itself is reachable, used by the
# frontend's app.js to know where to call the API from. Usually the
MINI_APP_API_URL = _require("MINI_APP_API_URL")
if not MINI_APP_API_URL.startswith("https://"):
    raise RuntimeError("MINI_APP_API_URL must start with https:// in production")
if not MINI_APP_API_URL.rstrip("/").endswith("/api"):
    raise RuntimeError("MINI_APP_API_URL must end with /api")

# ------------------------------------------------------------
# ADMIN PANEL SECURITY
# ------------------------------------------------------------
# A second secret, separate from the Telegram account itself, required
# to actually USE the Admin Panel (not just to see the button). If a
# staff member's Telegram account is ever compromised, this PIN is the
# thing that still stands between an attacker and House Edge/balance
# controls. This production build requires the PIN.
ADMIN_PANEL_PIN = _require("ADMIN_PANEL_PIN").strip()
if ADMIN_PANEL_PIN and len(ADMIN_PANEL_PIN) < 4:
    # A 1-2 digit PIN defeats the whole point of this second factor --
    # fail loudly at startup (same style as _require()) rather than
    # silently running with a PIN an attacker could guess in a handful
    # of tries even with the lockout in webapp_api.py.
    raise RuntimeError(
        "ADMIN_PANEL_PIN is set but too short (must be at least 4 characters) -- "
        "a short PIN defeats the purpose of this security layer."
    )

# Who gets a heads-up DM whenever another admin makes a large balance
# adjustment or changes a game's house edge -- lets a second person
# (e.g. the owner) notice quickly if a staff account is compromised or
# misused, instead of only finding out from the audit log later.
# Defaults to ADMIN_ID itself if not set separately (still useful: it
# means the FIRST staff member always gets pinged even if the action
# was taken by a DIFFERENT staff member).
OWNER_ID = int(os.environ.get("OWNER_ID", ADMIN_ID))

# Shown to users on the Terms page, the self-exclusion panel, and the
# responsible-gaming note -- a real, checkable way to reach a human,
# not just a self-exclusion button.
SUPPORT_CONTACT = _require("SUPPORT_CONTACT").strip()

# Optional live payment gateway (Chapa). Keep disabled until the merchant
# account/compliance is approved and the correct TEST/LIVE key is installed.
CHAPA_SECRET_KEY = os.environ.get("CHAPA_SECRET_KEY", "").strip()
CHAPA_MODE = os.environ.get("CHAPA_MODE", "test").strip().lower()
CHAPA_CALLBACK_URL = os.environ.get("CHAPA_CALLBACK_URL", "").strip()
CHAPA_RETURN_URL = os.environ.get("CHAPA_RETURN_URL", MINI_APP_URL).strip()
# Secret used to verify Chapa webhook HMAC-SHA256 signatures before processing.
CHAPA_WEBHOOK_SECRET = os.environ.get("CHAPA_WEBHOOK_SECRET", "").strip()
