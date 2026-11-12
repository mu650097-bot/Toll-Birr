# Production Launch Checklist — KDM Mini App

## Source gate
- [ ] `release_self_check.py` returns `SELF_CHECK=PASS`.
- [ ] `rtp_regression_test.py` returns `RTP_REGRESSION=PASS`.
- [ ] No `__pycache__`, `.env`, database, backup or secret files are packaged.

## Secrets
- [ ] Revoke the old exposed BotFather token and generate a new one.
- [ ] Set `BOT_TOKEN`, `ADMIN_ID`, bank/Telebirr values, `ADMIN_PANEL_PIN`, Mini App URLs.
- [ ] Set Chapa secret/webhook secret only through environment.
- [ ] Configure TURN credentials for production WebRTC if calls are required.

## Runtime
- [ ] Build and start Compose on the target host.
- [ ] `/api/health` returns DB integrity `ok`.
- [ ] API is healthy before bot/proxy starts.
- [ ] HTTPS certificate is valid and Telegram opens the Mini App.

## Money E2E
- [ ] Manual deposit approve once; verify one wallet credit and one transaction row.
- [ ] Concurrent approve/reject test: only one terminal state is accepted.
- [ ] Withdrawal request creates one negative ledger row.
- [ ] Withdrawal reject creates one positive refund row.
- [ ] Withdrawal approval does not create a second debit.
- [ ] Admin reconciliation reports zero mismatches for test users.
- [ ] Chapa small test payment verifies provider amount/currency and credits once.

## Games
- [ ] Run all 12 cabinet games and verify server-authoritative result/history.
- [ ] Run realtime Aviator/Jet/Mines/Keno flows.
- [ ] Confirm configured RTP values against the actual settings shown to Admin.

## Marketplace / WebRTC
- [ ] Post moderation, price/media review, escrow, refund and commission flows.
- [ ] Two real devices complete audio/video call through TURN-capable networks.

## Backup
- [ ] Confirm the 6-hour backup service creates an integrity-checked SQLite backup.
- [ ] Confirm persistent backup volume and retention.


## 2026-10-09 — Launch blocker fixes (source-level checks)
- All 12 cabinet games use the realtime `/round/start` + `/action` path in the UI; legacy stream/play frontend code was removed.
- Realtime start validates stake and game-specific input before `BEGIN IMMEDIATE` and before reserving the stake. Old malformed active rounds are defensively cancelled/refunded.
- RTP regression now checks both configured expected return and effective `payout / stake` multipliers for Wheel, Slot, Plinko, Chicken/Rabbit, Mines and Keno. Results show the multiplier users actually receive; raw/base multiplier is kept separately.
- Withdrawal staff notification uses Telegram HTML with escaped names/account values, checks Telegram's `ok` response, and daily limits are checked under `BEGIN IMMEDIATE`.
- JSON request bodies are capped at 1 MiB; multipart media retains the 60 MiB hard cap. `/round/start`, `/action`, and `/payments/intent` are rate-limited. Unexpected error DMs are rate-limited while local logs retain errors.
- `BOT_USERNAME` now comes from the environment; `.env` is excluded from Docker build context and the API remains one Gunicorn worker because rate limits are in-memory.
- Static API-path audit currently discovers 79 unique frontend path templates; all 79 match a backend route template. This is not a live deployment HTTP test.
- Still required before public launch: run the release tests against the actual configured DB/API; test live Telegram withdrawal notifications and duplicate actions; verify production HTTPS/payment provider; run Docker build/start and two-client WebRTC/TURN checks. These external checks were not performed in this environment.

- Follow-up test improvement: `realtime_path_regression_test.py` executes the production `rt_action` function against an isolated SQLite database for all 12 games and asserts the returned effective multiplier equals actual `payout / stake`; it also validates malformed input before debit. This is source-level/isolated-DB testing, not a deployed HTTPS/Telegram integration test.
