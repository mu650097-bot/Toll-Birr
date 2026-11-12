/* CHICKEN ROAST (new look + new maths): 3 reels x 3 rows, 5 fixed paylines (3 rows + 2 diagonals); the stake is split over the 5 lines.
   Symbols: egg, pepper, coin, drumstick, flame ("full roast"). The server (roast_math.py) stops the reels, evaluates the lines and pays;
   this file only draws the result. Replaces window.setupRoast (the old road-style Chicken Roast was removed). */
(function () {
  "use strict";
  var KEY = "roast", ICON = { egg: "🥚", pepper: "🌶️", coin: "🪙", leg: "🍗", flame: "🔥" }, ORDER = ["egg", "pepper", "coin", "leg", "flame"];
  var LINES = [[0,0,0],[1,1,1],[2,2,2],[0,1,2],[2,1,0]];
  var S = { min: 1, max: 10000, busy: false, loaded: false, stake: 20, auto: false, table: null, heat: 0 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  function drawGrid(root, g, wins) {
    var cells = root.querySelectorAll(".rs-c");
    for (var r = 0; r < 3; r++) for (var k = 0; k < 3; k++) { var el = cells[r * 3 + k]; el.textContent = ICON[g[r][k]] || "?"; el.classList.remove("win", "spin"); }
    (wins || []).forEach(function (w) { LINES[w.line].forEach(function (row, k) { cells[row * 3 + k].classList.add("win"); }); });
  }
  async function spinAnim(root, g) {
    var cells = root.querySelectorAll(".rs-c"), t0 = Date.now(), stop = [700, 1000, 1300], done = [false, false, false];
    while (done.indexOf(false) >= 0) {
      var t = Date.now() - t0;
      for (var k = 0; k < 3; k++) {
        if (t >= stop[k]) { if (!done[k]) { done[k] = true; for (var r = 0; r < 3; r++) { cells[r * 3 + k].textContent = ICON[g[r][k]]; cells[r * 3 + k].classList.remove("spin"); } hap("light"); } }
        else for (var r2 = 0; r2 < 3; r2++) { cells[r2 * 3 + k].textContent = ICON[ORDER[Math.floor(Math.random() * 5)]]; cells[r2 * 3 + k].classList.add("spin"); }
      }
      await sleep(70);
    }
  }
  window.setupRoast = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result", "-road", "-board"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.table = s.roast_table || null; if (s.roast_lines) LINES = s.roast_lines; } catch (_) {} S.loaded = true; }
    if (root.dataset.rs) return; root.dataset.rs = "1";
    var cells = ""; for (var i = 0; i < 9; i++) cells += '<div class="rs-c">🥚</div>';
    root.innerHTML = '<div class="kx-wrap"><div class="rs-head"><span>5 lines</span><div class="rs-heat"><small>Grill heat (win streak)</small><div class="rs-bar"><i id="rs-heat"></i></div></div></div>' +
      '<div class="rs-frame"><div class="rs-grid" id="rs-grid">' + cells + '</div><div class="rs-win" id="rs-win">WIN <b>0.00</b> ETB</div></div>' +
      '<div class="rs-pay" id="rs-pay"></div>' +
      '<div class="kx-card"><div class="kx-bet"><label for="rs-stake">Bet Amount</label><div class="kx-row"><div class="kx-step"><button type="button" data-d="-1" aria-label="minus">−</button><input id="rs-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1" aria-label="plus">+</button></div><button type="button" id="rs-max" class="rs-ghost">Max</button></div></div>' +
      '<div class="kx-row" style="margin-top:10px"><button type="button" id="rs-auto" class="rs-ghost gold">Auto</button><button type="button" id="rs-go" class="rs-spin" style="flex:2.4">Spin</button></div></div>' +
      '<div class="kx-msg" id="rs-msg" aria-live="polite"></div><div class="kx-proof" id="rs-proof"></div></div>';
    drawGrid(root, [["egg", "pepper", "coin"], ["leg", "leg", "leg"], ["flame", "coin", "pepper"]], null);
    var t = S.table;
    if (t) $(root, "#rs-pay").innerHTML = t.slice().reverse().map(function (r) { return '<div><span>3 × ' + (ICON[r.symbol] || r.symbol) + "</span><b>x" + r.multiplier + "</b></div>"; }).join("");
    var inp = $(root, "#rs-stake");
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; var v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; inp.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); }); });
    $(root, "#rs-max").addEventListener("click", function () { if (!S.busy) inp.value = Math.min(S.max, 500); });
    $(root, "#rs-go").addEventListener("click", function () { spin(root, inp); });
    $(root, "#rs-auto").addEventListener("click", async function () {
      if (S.auto) { S.auto = false; this.classList.remove("on"); return; }
      S.auto = true; this.classList.add("on");
      for (var n = 0; n < 10 && S.auto; n++) { var ok = await spin(root, inp); if (!ok) break; await sleep(500); }
      S.auto = false; this.classList.remove("on");
    });
  };
  function say(root, cls, t) { var e = $(root, "#rs-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function spin(root, inp) {
    if (S.busy) return false;
    var stake = Number(inp.value);
    if (!(stake >= S.min && stake <= S.max)) { say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"); return false; }
    S.busy = true; var go = $(root, "#rs-go"); go.disabled = true; say(root, "", ""); $(root, "#rs-win").innerHTML = "WIN <b>0.00</b> ETB"; $(root, "#rs-proof").textContent = "";
    var ok = true;
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome, p = Number(act.payout || 0);
      await spinAnim(root, o.grid); drawGrid(root, o.grid, o.wins);
      $(root, "#rs-win").innerHTML = "WIN <b>" + money(p) + "</b> ETB";
      S.heat = p > 0 ? Math.min(5, S.heat + 1) : 0; $(root, "#rs-heat").style.width = (S.heat / 5 * 100) + "%";
      if (p > stake) { say(root, "win", "🎉 " + o.wins.length + " line · +" + money(p - stake) + " ብር"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else if (p > 0) say(root, "bad", "↩️ " + money(p) + " ብር ተመልሷል");
      else say(root, "lose", "😕 -" + money(stake) + " ብር");
      if (act.server_seed) $(root, "#rs-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + (e.message || e)); ok = false; }
    S.busy = false; go.disabled = false; return ok;
  }
})();
