/* FAST KENO (new look + new rule): pick 1-8 of 40, the server draws 10, pay table depends on how many you pick.
   Design: draw ring, 1-40 grid (picked / hit / drawn), "n / 8 picked", last draw chips, Quick pick, Auto x10, Bet next round.
   TABLES must match FASTKENO_PAYTABLES in new_games_math.py (the server is authoritative and pays). Replaces window.setupFastKeno. */
(function () {
  "use strict";
  var KEY = "fastkeno", POOL = 40, MAXP = 8;
  var TABLES = { 1: { 1: 3.8 }, 2: { 2: 16.46 }, 3: { 2: 4.63, 3: 26.07 }, 4: { 2: 2.21, 3: 8.03, 4: 68.9 }, 5: { 3: 5.98, 4: 33.07, 5: 413.43 },
    6: { 3: 3.31, 4: 11.97, 5: 96.46, 6: 1000 }, 7: { 4: 10.24, 5: 48.47, 6: 562.26, 7: 1000 }, 8: { 4: 6.13, 5: 19.04, 6: 159.95, 7: 1000, 8: 1000 } };
  var BALLC = ["#facc15", "#3b82f6", "#ef4444", "#a855f7", "#f97316", "#14b8a6", "#ec4899", "#84cc16"];   // Super Keno ball colours
  var S = { min: 1, max: 10000, busy: false, loaded: false, sel: [], stake: 20, round: 128, auto: false, last: [] };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  window.setupFastKeno = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    var vkey = (typeof window.kdmVariantKey === "function" && window.kdmVariantKey()) || "fastkeno";
    if (S.vkey !== vkey) { S.vkey = vkey; S.loaded = false; }   // each game has its own min / max bet
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; } catch (_) {} S.loaded = true; }
    if (root.dataset.fk === vkey) return;   // already built for THIS game (Fast / Power / Super / Insta share one page, so rebuild when it changes)
    root.dataset.fk = vkey; S.sel = []; S.last = []; S.auto = false;
    var cells = ""; for (var n = 1; n <= POOL; n++) cells += '<button type="button" class="fk-c" data-n="' + n + '">' + n + "</button>";
    var power = (vkey === "keno_power");   // Power Keno = same engine + a hit meter
    root.dataset.power = power ? "1" : "";
    var sup = (vkey === "keno_super");   // Super Keno = same engine + ball-machine look (coloured balls roll into a tray)
    root.dataset.sup = sup ? "1" : "";
    root.innerHTML = '<div class="kx-wrap' + (sup ? ' fk-super' : '') + '">' + (power ? '<div class="fk-power"><div class="fk-8">8</div><div style="flex:1"><small>Power meter (fills on each hit)</small><div class="fk-meter"><i id="fk-meter"></i></div><div class="fk-ticks" id="fk-ticks"></div></div></div>' : '') + (sup ? '<div class="fk-machine"><div class="fk-mt"><span>Draw #<span id="fk-round">' + S.round + '</span></span><span id="fk-balls">Balls 0 / 10</span></div><div class="fk-tray" id="fk-last"></div><b id="fk-sec" hidden>—</b></div>' : '<div class="fk-top"><div class="fk-ring" id="fk-ring"><b id="fk-sec">—</b></div><div><small>NEXT DRAW IN</small><h4>Round <span id="fk-round">' + S.round + '</span></h4><em>Pick 1–8 numbers</em></div></div>') +
      '<div class="fk-board"><div class="fk-grid" id="fk-grid">' + cells + '</div><div class="fk-leg"><span><i style="background:#facc15"></i>Picked</span><span><i style="background:#16a34a"></i>Hit</span><span><i style="background:#5b3fd1"></i>Drawn</span><b id="fk-cnt">0 / 8 picked</b></div></div>' +
      '<div class="fk-pay" id="fk-pay"></div>' + (sup ? '' : '<div class="fk-lastrow"><small>Last draw</small><div id="fk-last"></div></div>') +
      '<div class="kx-card"><div class="kx-bet"><label for="fk-stake">Bet Amount</label><div class="kx-row"><div class="kx-step"><button type="button" data-d="-1" aria-label="minus">−</button><input id="fk-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1" aria-label="plus">+</button></div><button type="button" id="fk-quick" class="fk-ghost">Quick pick</button></div></div>' +
      '<div class="kx-row" style="margin-top:10px"><button type="button" id="fk-auto" class="fk-ghost gold">Auto ×10</button><button type="button" id="fk-go" class="fk-bet" style="flex:2.4">' + (sup ? 'Start draw' : 'Bet next round') + '</button></div></div>' +
      '<div class="kx-msg" id="fk-msg" aria-live="polite"></div><div class="kx-proof" id="fk-proof"></div></div>';
    var inp = $(root, "#fk-stake");
    root.querySelectorAll(".fk-c").forEach(function (b) { b.addEventListener("click", function () { toggle(root, Number(b.dataset.n)); }); });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; var v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; inp.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); }); });
    $(root, "#fk-quick").addEventListener("click", function () { if (S.busy) return; var k = S.sel.length >= 1 ? S.sel.length : 5, s = []; while (s.length < k) { var n = 1 + Math.floor(Math.random() * POOL); if (s.indexOf(n) < 0) s.push(n); } S.sel = s; S.last = []; hap("light"); paint(root, []); });
    $(root, "#fk-go").addEventListener("click", function () { play(root, inp); });
    $(root, "#fk-auto").addEventListener("click", async function () {
      if (S.auto) { S.auto = false; this.classList.remove("on"); return; }
      if (S.busy || !S.sel.length) return say(root, "bad", "መጀመሪያ ቁጥሮች ይምረጡ");
      S.auto = true; this.classList.add("on");
      for (var i = 0; i < 10 && S.auto; i++) { var ok = await play(root, inp); if (!ok) break; await sleep(500); }
      S.auto = false; this.classList.remove("on");
    });
    S.sel = [3, 8, 14, 21, 33]; paint(root, []);
  };
  function toggle(root, n) {
    if (S.busy) return; var i = S.sel.indexOf(n);
    if (i >= 0) S.sel.splice(i, 1); else if (S.sel.length < MAXP) S.sel.push(n); else { hap("error"); return; }
    hap("light"); S.last = []; paint(root, []);
  }
  function paint(root, draw) {
    root.querySelectorAll(".fk-c").forEach(function (b) {
      var n = Number(b.dataset.n), pk = S.sel.indexOf(n) >= 0, dr = draw.indexOf(n) >= 0;
      b.className = "fk-c" + (pk && dr ? " hit" : pk ? " pick" : dr ? " drawn" : "");
    });
    $(root, "#fk-cnt").textContent = S.sel.length + " / " + MAXP + " picked";
    var t = TABLES[S.sel.length], hits = draw.filter(function (n) { return S.sel.indexOf(n) >= 0; }).length;
    $(root, "#fk-pay").innerHTML = t ? Object.keys(t).map(function (h) { return '<div class="' + (draw.length && Number(h) === hits ? "on" : "") + '"><small>' + h + " hits</small><b>x" + t[h] + "</b></div>"; }).join("") : '<div><small>1–8 ቁጥሮች ይምረጡ</small></div>';
    $(root, "#fk-go").disabled = S.busy || !t;
    var mt = $(root, "#fk-meter");
    if (mt) {   // Power meter: one tick per paying hit count of the CURRENT pick count, showing that real table multiplier
      var hs = t ? Object.keys(t) : [], lit = hs.filter(function (h) { return draw.length && Number(h) <= hits; }).length;
      mt.style.width = (hs.length ? lit / hs.length * 100 : 0) + "%";
      $(root, "#fk-ticks").innerHTML = hs.map(function (h) { return "<span" + (draw.length && Number(h) <= hits ? ' class="on"' : "") + ">x" + t[h] + "</span>"; }).join("");
    }
  }
  function say(root, cls, t) { var e = $(root, "#fk-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function play(root, inp) {
    if (S.busy || !S.sel.length) return false;
    var stake = Number(inp.value);
    if (!(stake >= S.min && stake <= S.max)) { say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"); return false; }
    S.busy = true; S.last = []; paint(root, []); say(root, "", ""); $(root, "#fk-proof").textContent = ""; $(root, "#fk-last").innerHTML = ""; var bl0 = $(root, "#fk-balls"); if (bl0) bl0.textContent = "Balls 0 / 10";
    var ok = true;
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, numbers: S.sel.slice(), client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      for (var c = 3; c >= 1; c--) { $(root, "#fk-sec").textContent = c + "s"; await sleep(450); }
      $(root, "#fk-sec").textContent = "•";
      var o = act.outcome, shown = [];
      for (var i = 0; i < o.draw.length; i++) {
        var n = o.draw[i]; shown.push(n); paint(root, shown);
        var chip = document.createElement("span"); chip.textContent = n; chip.className = S.sel.indexOf(n) >= 0 ? "h" : ""; if (root.dataset.sup) chip.style.background = BALLC[n % BALLC.length]; $(root, "#fk-last").appendChild(chip); var bl = $(root, "#fk-balls"); if (bl) bl.textContent = "Balls " + shown.length + " / " + o.draw.length;
        if (S.sel.indexOf(n) >= 0) hap("light"); await sleep(170);
      }
      S.last = shown; S.round++; $(root, "#fk-round").textContent = S.round; $(root, "#fk-sec").textContent = "—";
      var p = Number(act.payout || 0);
      if (p > stake) { say(root, "win", "🎉 " + o.hits + " hits · +" + money(p - stake) + " ብር"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else if (p > 0) say(root, "bad", "↩️ " + o.hits + " hits · " + money(p) + " ብር ተመልሷል");
      else say(root, "lose", "😕 " + o.hits + " hits · -" + money(stake) + " ብር");
      if (act.server_seed) $(root, "#fk-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + (e.message || e)); ok = false; $(root, "#fk-sec").textContent = "—"; }
    S.busy = false; paint(root, S.last); return ok;
  }
})();
