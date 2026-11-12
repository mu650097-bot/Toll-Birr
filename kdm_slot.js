/* SLOTS (new look + new maths): 5 reels x 3 rows, 10 paylines, Wild, Scatter + 8 Free Spins (wins x2).
   ONE engine behind all 36 themed slot games: game_catalog.js supplies the theme (symbols/colours) through kdmSlotSkin();
   the server (slot_math.py) stops the reels, evaluates the lines and pays. This file only draws what the server returned. Replaces window.setupSlot. */
(function () {
  "use strict";
  var KEY = "slot", FALLBACK = ["🍒", "🍋", "🔔", "💎", "7️⃣"];
  var LINES = [[1,1,1,1,1],[0,0,0,0,0],[2,2,2,2,2],[0,1,2,1,0],[2,1,0,1,2],[0,0,1,2,2],[2,2,1,0,0],[1,0,0,0,1],[1,2,2,2,1],[0,1,1,1,0]];
  var S = { min: 1, max: 10000, busy: false, loaded: false, stake: 10, auto: false, table: null, grid: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var IDX = { a: 0, b: 1, c: 2, d: 3, e: 4 };
  function skin() { try { return (typeof window.kdmSlotSkin === "function" && window.kdmSlotSkin()) || null; } catch (_) { return null; } }
  function glyph(s) {
    if (s === "W") return '<span class="sl-w">WILD</span>';
    if (s === "S") return '<span class="sl-s">★</span>';
    var sk = skin(), base = FALLBACK[IDX[s]]; return sk && sk.map ? sk.map(base) : base;
  }
  function paintTheme(root) {
    var sk = skin(), box = $(root, ".sl-frame"); if (!box) return;
    box.style.setProperty("--sl-c1", (sk && sk.frame) || "#f59e0b"); box.style.setProperty("--sl-c2", (sk && sk.c2) || "#3b1d05");
  }
  function cell(s) { return '<div class="sl-c">' + glyph(s) + "</div>"; }
  function drawGrid(root, g, hl) {
    var cells = root.querySelectorAll(".sl-c"); if (!cells.length) return;
    for (var r = 0; r < 3; r++) for (var k = 0; k < 5; k++) { var el = cells[r * 5 + k]; el.innerHTML = glyph(g[r][k]); el.classList.remove("win", "spin"); }
    (hl || []).forEach(function (w) { LINES[w.line].forEach(function (row, k) { if (k < w.count) cells[row * 5 + k].classList.add("win"); }); });
    if (hl) g.forEach(function (row, r) { row.forEach(function (s, k) { if (s === "S" && hl.sc) cells[r * 5 + k].classList.add("win"); }); });
  }
  var ALL = ["a", "b", "c", "d", "e", "a", "b", "c", "W", "S"];
  async function spinAnim(root, g, ms) {
    var cells = root.querySelectorAll(".sl-c"); var t0 = Date.now(), stopAt = [0, 1, 2, 3, 4].map(function (k) { return ms + k * 170; });
    var done = [false, false, false, false, false];
    while (done.indexOf(false) >= 0) {
      var t = Date.now() - t0;
      for (var k = 0; k < 5; k++) {
        if (t >= stopAt[k]) { if (!done[k]) { done[k] = true; for (var r = 0; r < 3; r++) { cells[r * 5 + k].innerHTML = glyph(g[r][k]); cells[r * 5 + k].classList.remove("spin"); } hap("light"); } }
        else for (var r2 = 0; r2 < 3; r2++) { cells[r2 * 5 + k].innerHTML = glyph(ALL[Math.floor(Math.random() * ALL.length)]); cells[r2 * 5 + k].classList.add("spin"); }
      }
      await sleep(70);
    }
  }
  window.setupSlot = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.table = s.slot_table || null; if (s.slot_lines) LINES = s.slot_lines; } catch (_) {} S.loaded = true; }
    if (!root.dataset.sl) {
      root.dataset.sl = "1";
      var cells = ""; for (var i = 0; i < 15; i++) cells += cell("a");
      root.innerHTML = '<div class="kx-wrap"><div class="sl-frame"><div class="sl-grid" id="sl-grid">' + cells + '</div><div class="sl-win" id="sl-win">WIN <b>0.00</b> ETB</div></div>' +
        '<div class="sl-info"><div><small>Scatter bonus</small><div class="sl-bar"><i id="sl-bar"></i></div></div><div><small>Free spins</small><b id="sl-fs">8</b></div></div>' +
        '<div class="sl-pay" id="sl-pay"></div>' +
        '<div class="kx-card"><div class="kx-bet"><label for="sl-stake">Bet Amount</label><div class="kx-row"><div class="kx-step"><button type="button" data-d="-1" aria-label="minus">−</button><input id="sl-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1" aria-label="plus">+</button></div></div></div>' +
        '<div class="kx-row" style="margin-top:10px"><button type="button" id="sl-auto" class="sl-ghost gold">Auto</button><button type="button" id="sl-go" class="kx-go" style="flex:2.4">Spin</button></div></div>' +
        '<div class="kx-msg" id="sl-msg" aria-live="polite"></div><div class="kx-proof" id="sl-proof"></div></div>';
      var inp = $(root, "#sl-stake");
      root.querySelectorAll(".kx-step button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; var v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; inp.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); }); });
      $(root, "#sl-go").addEventListener("click", function () { spin(root, inp); });
      $(root, "#sl-auto").addEventListener("click", async function () {
        if (S.auto) { S.auto = false; this.classList.remove("on"); return; }
        S.auto = true; this.classList.add("on");
        for (var n = 0; n < 10 && S.auto; n++) { var ok = await spin(root, inp); if (!ok) break; await sleep(500); }
        S.auto = false; this.classList.remove("on");
      });
    }
    paintTheme(root); drawGrid(root, [["a", "b", "c", "d", "e"], ["e", "d", "W", "b", "a"], ["b", "S", "a", "c", "d"]], null);
    var t = S.table;
    if (t) $(root, "#sl-pay").innerHTML = ["e", "d", "c", "b", "a"].map(function (s) { var p = t.pay[s]; return '<div><span>' + glyph(s) + "</span><small>3·4·5</small><b>x" + [p["3"], p["4"], p["5"]].map(function (x) { return +Number(x).toFixed(1); }).join(" · ") + "</b></div>"; }).join("") +
      '<div class="sc"><span>' + glyph("S") + "</span><small>3·4·5 +" + t.free_spins + " FS</small><b>x" + [t.scatter["3"], t.scatter["4"], t.scatter["5"]].map(function (x) { return +Number(x).toFixed(1); }).join(" · ") + "</b></div>";
  };
  function say(root, cls, t) { var e = $(root, "#sl-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  function setWin(root, v) { $(root, "#sl-win").innerHTML = "WIN <b>" + money(v) + "</b> ETB"; }
  async function spin(root, inp) {
    if (S.busy) return false;
    var stake = Number(inp.value);
    if (!(stake >= S.min && stake <= S.max)) { say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"); return false; }
    S.busy = true; var go = $(root, "#sl-go"); go.disabled = true; say(root, "", ""); setWin(root, 0); $(root, "#sl-proof").textContent = ""; $(root, "#sl-fs").textContent = "8"; $(root, "#sl-bar").style.width = "0";
    var ok = true;
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome, sc = Number(o.payout_scale || 1), shown = 0, total = Number(act.payout || 0);
      await spinAnim(root, o.grid, 900);
      var hl = o.wins.slice(); if (o.scatters >= 3) hl.sc = true; drawGrid(root, o.grid, hl);
      var baseWin = stake * (Number(o.base_mult) + Number(o.scatter_mult)) * sc; shown = baseWin; setWin(root, shown);
      if (o.wins.length || baseWin > 0) hap("light");
      if (o.free_spins && o.free_spins.length) {
        say(root, "win", "⭐ " + o.scatters + " scatters · " + o.free_spins.length + " FREE SPINS (wins ×2)!"); hap("success"); await sleep(1300);
        for (var i = 0; i < o.free_spins.length; i++) {
          var f = o.free_spins[i]; $(root, "#sl-fs").textContent = String(o.free_spins.length - i - 1); $(root, "#sl-bar").style.width = ((i + 1) / o.free_spins.length * 100) + "%";
          await spinAnim(root, f.grid, 600); drawGrid(root, f.grid, f.wins);
          shown += stake * Number(f.mult) * sc; setWin(root, shown); await sleep(f.wins.length ? 700 : 250);
        }
      }
      setWin(root, total);
      if (total > stake) { say(root, "win", "🎉 +" + money(total - stake) + " ብር"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else if (total > 0) say(root, "bad", "↩️ " + money(total) + " ብር ተመልሷል");
      else { say(root, "lose", "😕 -" + money(stake) + " ብር"); }
      if (act.server_seed) $(root, "#sl-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + (e.message || e)); ok = false; }
    S.busy = false; go.disabled = false; return ok;
  }
})();
