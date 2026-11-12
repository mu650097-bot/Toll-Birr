# KDM Mini App — Launch runbook (things only you can run)

## 1. Secrets
1. BotFather -> /revoke -> new token. Put it ONLY in `.env` (`BOT_TOKEN=`). Never in code/zip/screenshots.
2. `cp .env.example .env` and fill every REPLACE_WITH_* value. Keep `.env` out of the zip/git.

## 2. Risk settings (set to YOUR real numbers)
- `PLATFORM_BANKROLL_ETB` = money actually available to pay winners (0 = guard off). `BANKROLL_EXPOSURE_PCT` default 0.5.
- `MAX_ROUND_PAYOUT_ETB` = most one round may ever pay (default 100,000; keep it ~2-5% of your real bankroll). Default max bet per game is now 500 ETB (Admin Panel -> Game Economics).
- `WITHDRAW_TURNOVER_MULTIPLIER` = times a real deposit must be wagered before withdrawal (default 0 = off, withdraw allowed without playing; was 3; the 10% deposit bonus has no wagering of its own, so 1x would lose money; 0 = off). Deposit bonus max default is 1,000 ETB (Admin Panel -> Deposit Bonus)..
- `MAX_HOUSE_EDGE` (default 0.30), `SPORTS_MIN_OVERROUND` (default 1.02).

## 3. Build and start
    docker compose build && docker compose up -d
    docker compose ps            # api, bot, proxy must be "healthy"
    curl -s https://$DOMAIN/api/health   # {"ok": true, "db_integrity": "ok"}

## 4. Offline gates (inside the repo, with env vars set)
    python release_self_check.py && python rtp_regression_test.py && python realtime_path_regression_test.py \
    && python launch_blocker_regression_test.py && python crash_refund_regression_test.py \
    && python table_games_rtp_test.py && python risk_controls_regression_test.py && python api_path_audit.py

## 5. Live checks (use small amounts / test accounts)
- Open the Mini App from Telegram on the real domain.
- Manual deposit: approve once -> exactly one wallet credit. Withdrawal: request -> reject refunds once; approve debits nothing extra.
- Chapa: CHAPA_MODE=test small payment -> credited once; then live key.
- Play each game once; Aviator/Jet: do NOT cash out and wait for the crash -> round must end LOST.
- Boom with two accounts: second player joins after boxes are open -> smaller prize shown.
- Sports: create a match with a near-future closes_at; confirm betting is refused after it.
- WebRTC: two real phones on different networks, TURN configured.
- `docker compose exec backup python backup_db.py` creates a verified backup.

## 6. Sports operation rule
Always give a kickoff time (`closes_at`). Use "Betting ዝጋ" in Admin to close early. Old matches without `closes_at` are treated as closed.

## Admin/Owner announcements
- Set `OWNER_ID` to the trusted owner Telegram numeric user ID. Both `ADMIN_ID` and `OWNER_ID` are accepted for protected admin actions; manager users remain controlled through the database.
- Optional: set `ANNOUNCEMENT_CHANNEL_ID` to the Telegram channel ID (often a negative number such as `-100...`) and add the bot as a channel administrator with permission to post.
- In the Mini App Admin panel, use **Announcements** to publish text or a photo/video/voice file (maximum 8 MB) to registered unbanned users. When the channel ID is configured, the same announcement is also posted to that channel. Verify the channel post and delivery counts with a small test audience before a production broadcast.
- Telegram Bot API rate limits can cause some messages to fail during large broadcasts; inspect the returned sent/failed counts and announcement history.
