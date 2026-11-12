# KDM Mini App — Blocker Fix Notes

## 1. Flask global error handler

- `HTTPException` (including 404, 405, and 413) now returns JSON with its original HTTP status code.
- These expected client/request errors are not sent to the Admin Telegram DM.
- Unexpected exceptions are still logged and sent to the Admin, then return HTTP 500.

## 2. Telegram withdrawal approve/reject

- The Mini App withdrawal request reserves the amount from the wallet and writes one negative `withdraw` ledger entry when the request is created.
- Admin approval now atomically changes `pending` to `approved`; it does not debit the wallet again or create another ledger row.
- Admin rejection atomically changes `pending` to `rejected`, refunds the reserved amount once, and writes one positive `withdraw_refund` ledger entry.
- Duplicate/stale button clicks are rejected because the withdrawal must still be `pending`.

## Verification

- Python syntax check: PASS.
- Release self-check: PASS.
- Production contract/route smoke check: PASS.
- A live Flask test-client run and live Telegram callback test still need to be run in an environment with project dependencies and real bot/database configuration. Do not treat offline source checks as proof of a live production deployment.


## Follow-up launch audit — 2026-10-09
- Realtime path: all 12 games are wired to `/round/start` and `/action`; validation runs before stake debit. Malformed old ACTIVE records are refunded/cancelled defensively.
- RTP: regression checks configured RTP and effective payout multiplier (`payout/stake`). UI now labels the effective multiplier and configured RTP; the base multiplier is separate.
- Wallet/withdrawal: staff message is HTML escaped and Telegram send response is checked; daily limits and balance reservation share one immediate transaction.
- API abuse controls: start/action/payment-intent limits, 1 MiB JSON body cap, rate-limited admin error DMs, environment-only bot username, and single-worker deployment for in-memory limits.
- Path audit: 80 unique frontend API templates detected and all 80 matched to backend route templates. Live HTTPS, payment-provider, Docker daemon and WebRTC checks remain external launch gates.

- Follow-up test improvement: `realtime_path_regression_test.py` executes the production `rt_action` function against an isolated SQLite database for all 12 games and asserts the returned effective multiplier equals actual `payout / stake`; it also validates malformed input before debit. This is source-level/isolated-DB testing, not a deployed HTTPS/Telegram integration test.
