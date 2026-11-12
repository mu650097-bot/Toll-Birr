# Step 18 — Jet (new radar look, self-registering)

Only TWO new files; no existing file is replaced, so it cannot conflict with steps 10-17.

1. Copy `kdm_jet.js` and `kdm_jet.css` next to `index.html`.
2. In `index.html` add the stylesheet BEFORE `new_games.css` (or anywhere in <head>):
       <link rel="stylesheet" href="kdm_jet.css?v=20261110">
3. In `index.html` add the script as the VERY LAST script (after every other game script, so it is the outermost wrapper):
       <script src="kdm_jet.js?v=20261110"></script>

How it works: `kdm_jet.js` wraps `window.setupAddedGameControls`; for the page key `jet` it builds the new page, for every other key it
calls the previous handler unchanged. The server (`jet` = the same crash engine as Aviator) is NOT modified.
Needs these globals from app.js (already there): apiFetch, startRealtimeRound, realtimeState, realtimeAction, refreshBalance, haptic.
