# KDM Mini App — Game Visual Refresh

- Added distinct original game-inspired cabinet tile treatments for Aviator, Keno, Chicken Road, Fish Road and JetX.
- Updated native canvas scenes for Aviator/JetX crash-flight visuals, Chicken Road street/steps, and Fish Road underwater layers.
- Updated palette colors for all game scenes and renamed Jet/Fish display labels to JetX/Fish Road.
- Kept all game outcome decisions on the server; animations only visualize server outcomes.
- Did not change Keno's number range or wager rules because the existing backend contract and payout tests are configured for the current 1–20 / five-pick flow. Matching the screenshot's 1–80 rules requires a coordinated backend payout and validation change, not a front-end-only edit.

## Checks
- `node --check app.js`: PASS
- `python -m py_compile *.py`: PASS
- `blocker_regression_test.py`: PASS
- `rtp_regression_test.py`: PASS
- `crash_refund_regression_test.py`: PASS
- `risk_controls_regression_test.py`: PASS
- `launch_blocker_regression_test.py`: PASS
- `table_games_rtp_test.py`: PASS
- `pool_games_regression_test.py`: NOT RUN successfully in this environment; Flask dependency is not installed.
- `realtime_path_regression_test.py`: timed out in the available test window; not counted as passed.
