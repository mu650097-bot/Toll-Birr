# KDM Mini App — FINAL FULL SOURCE AUDIT
Date: 2026-10-08

## 1. Final status

The earlier audit list was correct about several important defects. They have now been fixed in the source package and covered by a stricter release gate.

**Source/package gate: PASS**

- Python syntax: PASS
- JavaScript syntax: PASS
- Flask route uniqueness across API + realtime engine: 104 unique routes / 104 registrations
- Shared schema migration smoke: PASS
- Production-source RTP regression: PASS for all 12 cabinet games
- SQLite backup integrity smoke: PASS
- Release self-check: PASS
- Offline production contract check: PASS

## 2. Blockers fixed

### `webapp_api.py`
`webapp_api.py` is included in the final package and is the Flask API entry point used by `Dockerfile.api` (`webapp_api:app`). It contains Telegram auth, wallet, Chapa, game settlement, marketplace, admin, audit and realtime integration.

### Withdrawals schema conflict
There is now one canonical schema:

```text
withdrawals.id INTEGER PRIMARY KEY AUTOINCREMENT
```

Older databases that used `withdrawal_id` are migrated by `extended_schema.py` while preserving existing IDs/data. Both API-first and bot-first startup use the shared schema migration.

### `transactions.payment_id`
`transactions.payment_id` is now part of the canonical schema and is added to older installations if missing. Manual deposit approval records the payment ID in the transaction ledger.

### Manual deposit approval
`approve_payment()` now uses `BEGIN IMMEDIATE`, updates only `status='pending'`, checks `rowcount`, checks that the user exists, and inserts exactly one deposit ledger row. A second approval returns `already_processed` and cannot credit twice.

### Auction result delivery
`get_user_auction_bids()` is implemented. Auction results are sent only to users who actually bid in that auction, not to every user in the database. Delivery is paced (`0.05s` between messages) to avoid creating an uncontrolled Telegram API burst.

### Withdrawal accounting
Canonical ledger convention is now:

- deposit / win / refund = positive
- bet / stake / withdrawal = negative

Withdrawal request creates the negative `withdraw` ledger row in the same transaction as the balance reservation. Reject creates one positive `withdraw_refund` row. Approval does not debit the wallet a second time.

Old positive `withdraw` ledger rows are migrated to negative values once by the shared schema migration.

### Realtime payment webhook
`realtime_engine_v3.py` now has:

- connection rollback (`c.rollback()`), never cursor rollback
- UTF-8 JSON decoding with malformed-JSON rejection
- bytes-safe HMAC comparison
- object-type validation
- amount/status validation

### Realtime Mines / house edge
Realtime Mines is aligned with the Mini App UI and main API at **1–8 mines, pick 1–25**. The raw multiplier is no longer pre-scaled by `.92`; the common house-edge scaler applies the configured edge once.

### Realtime timestamps
Realtime cleanup/call-session timestamps now use the same local-time convention as the application's `_now()` values, avoiding UTC/local timestamp comparison drift.

## 3. Admin security

`ADMIN_PANEL_PIN` is mandatory in `config.py` and is also used by the Telegram bot.

Bot admin/manager sensitive callbacks (`admin_*`, payment approve/reject, withdrawal actions) require a short-lived PIN session. The PIN can be entered with `/adminpin <PIN>` or after `/adminpin` prompt; the PIN message is deleted when possible.

The Mini App API separately keeps its authenticated admin PIN session/lockout mechanism.

## 4. Telegram Markdown / user-input safety

Withdrawal staff notifications now use HTML escaping for account name/number instead of inserting raw user input into Markdown backticks. Mini App deposit staff captions also escape the Telegram user's first name.

## 5. Legacy API surface

The bot's old `/api/*` aiohttp handlers are no longer registered. `webapp_api.py` is the single HTTP API owner. This removes the legacy paths that lacked the production API's full validation/rate-limit/security model.

## 6. Deployment hardening

- `.dockerignore` is correctly named and excludes `.env`, databases, backups, caches and archives.
- `.env.example` is correctly named.
- API and bot Dockerfiles run as non-root `appuser`.
- API and bot have container healthchecks.
- Compose makes bot/proxy wait for healthy API/bot services.
- Caddy adds HSTS, CSP, X-Content-Type-Options, Referrer-Policy and Permissions-Policy.
- Three.js r128 is pinned with the published SHA-384 SRI hash and `crossorigin="anonymous"`.
- Dedicated backup service remains every 6 hours with a persistent `kdm-backups` volume.
- The old bot-side backup scheduler is not used.

## 7. RTP verification

The RTP regression test was upgraded so it executes the production `_run_cabinet`, `_cabinet_base_rtp`, and `_apply_cabinet_house_edge` functions extracted directly from `webapp_api.py` instead of maintaining a completely separate payout implementation.

Current targets:

- Dice 95%
- Slot 92%
- Wheel 93%
- Keno 90%
- Chicken 95%
- Aviator 95%
- Plinko 92%
- Mines 95%
- Jet 95%
- Fish 92%
- Rabbit 95%
- Card 95%

**RTP_REGRESSION=PASS**

The previous Slot mathematical-base defect that produced roughly 210% RTP is not present. Slot base RTP is 115.2%, then scaled to the configured 92% target.

## 8. Package / release checks

`release_self_check.py` now checks source contracts rather than only looking for reassuring text. It covers schema ownership/migration, atomic payment approval, withdrawal ledger behavior, auction-result delivery, webhook rollback/JSON handling, Mines range/scaling, backup architecture, Admin PIN, Docker hardening, Caddy headers, SRI, legacy API removal and required files.

`production_e2e_smoke.py` additionally checks route uniqueness and required release files.

`production_smoke_test.py` now fails closed when `SMOKE_API_URL` is missing; it no longer returns an artificial green result for an untested deployment.

## 9. Remaining live-only verification

These are not source-code defects that can honestly be certified from this offline environment:

1. Docker image build/start on the actual server.
2. Real HTTPS Telegram Mini App launch with the production domain.
3. Real Chapa transaction using the merchant's actual credentials.
4. Two real devices/networks completing WebRTC audio/video.
5. Production TURN connectivity using real TURN credentials.

## 10. Credential warning

If the Telegram bot token was previously exposed, it must be revoked/regenerated in **@BotFather** before production. The replacement token must be supplied only through environment variables and must not be placed in source code, comments, screenshots, logs or the release ZIP.
