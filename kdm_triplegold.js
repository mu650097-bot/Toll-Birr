/* TRIPLE GOLD: classic 3-reel, 3-row slot with one payline (the middle row). The SERVER stops the reels, evaluates the
   payline, applies the disclosed house edge and pays. This file only draws the grid the server returns. Loaded after app.js. */
(function () {
  "use strict";
  var KEY = "triplegold", SYMS = ["bell", "cherry", "bar", "seven"];
  var T = { min: 1, max: 10000, table: null, loaded: false, busy: false, auto: 0, last: 0, grid: null, win: null, keep: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  function xf(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : String(+m.toFixed(2)); }
  function sym(n, s) {
    s = s || 52;
    if (n === "bell") return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><path d="M32 6c-3 0-5 2-5 4-8 3-13 10-13 20 0 10-4 12-6 16h48c-2-4-6-6-6-16 0-10-5-17-13-20 0-2-2-4-5-4z" fill="#fbbf24" stroke="#b45309" stroke-width="2.5" stroke-linejoin="round"/><path d="M22 20c-3 4-4 9-4 14" stroke="#fef3c7" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="32" cy="54" r="5" fill="#d97706" stroke="#92400e" stroke-width="2"/></svg>';
    if (n === "cherry") return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><path d="M22 40C24 24 34 14 46 10M42 42C42 28 44 18 46 10" stroke="#15803d" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M46 10c6-4 12-2 14 2-6 2-11 1-14-2z" fill="#22c55e"/><circle cx="20" cy="44" r="12" fill="#dc2626" stroke="#7f1d1d" stroke-width="2"/><circle cx="42" cy="46" r="12" fill="#ef4444" stroke="#7f1d1d" stroke-width="2"/><circle cx="16" cy="40" r="3.2" fill="#fecaca"/><circle cx="38" cy="42" r="3.2" fill="#fecaca"/></svg>';
    if (n === "bar") return '<svg viewBox="0 0 96 64" width="' + (s * 1.5) + '" height="' + s + '"><rect x="4" y="16" width="88" height="32" rx="6" fill="#111827" stroke="#fbbf24" stroke-width="3"/><text x="48" y="40" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" font-size="24" letter-spacing="3" fill="#fbbf24">BAR</text></svg>';
    return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><text x="32" y="54" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" font-size="64" fill="#e11d48" stroke="#7f1d1d" stroke-width="1.5">7</text></svg>';
  }
  function rnd() { return SYMS[Math.floor(Math.random() * SYMS.length)]; }
  function load() {
    var sk = (typeof window.kdmSkinKey === "function" && window.kdmSkinKey()) || KEY;   // plain Triple Gold or the Deluxe skin: each has its own limits / edge
    if (T.loaded && T.loadedFor === sk) return Promise.resolve();
    T.loadedFor = sk;
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      T.min = Number(s.min_stake) || 1; T.max = Number(s.max_stake) || 10000; if (s.triplegold_table) T.table = s.triplegold_table; T.loaded = true;
    }).catch(function () { T.loaded = true; });
  }

  window.setupTripleGold = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var cells = ""; for (var r = 0; r < 3; r++) for (var c = 0; c < 3; c++) cells += '<div class="tg-cell' + (r === 1 ? " mid" : "") + '" data-r="' + r + '" data-c="' + c + '"></div>';
      root.innerHTML = '<div class="tg-wrap"><div class="tg-frame"><div class="tg-ribbon">TRIPLE GOLD</div><div class="tg-grid" id="tg-grid">' + cells + '</div><div class="tg-win" id="tg-win"></div></div>' +
        '<div class="tg-stats"><div class="kx-tile"><small>Last Win</small><b id="tg-last" class="g">0.00</b></div><div class="kx-tile"><small>Top prize</small><b id="tg-top" class="y">—</b></div></div>' +
        '<div class="tg-pay" id="tg-pay"></div>' +
        '<div class="av-card"><div class="av-bet-col"><label for="triplegold-stake">Bet Amount</label><div class="kn-row"><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="triplegold-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="10"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="kn-sm" id="tg-max" style="grid-column:3">Max Bet</button></div></div>' +
        '<div class="tg-btns"><button type="button" class="kn-sm tg-auto" id="tg-auto">Auto</button><button type="button" id="tg-go" class="av-go tg-spin">Spin</button></div>' +
        '<div class="kx-msg" id="tg-msg" aria-live="polite"></div><div class="kx-proof" id="tg-proof"></div></div>' +
        '<small class="kx-note">ሦስቱ ሪሎች ሲቆሙ መካከለኛው ረድፍ ብቻ ይከፍላል፤ ሦስት ተመሳሳይ ወይም ሁለት 🍒 ሲሆን። ክፍያዎቹ house edge ተቀንሶ የሚታዩ ናቸው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (T.busy) return; var i = $(root, "#triplegold-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(T.min, Math.min(T.max, v + Number(b.dataset.d) * st)); hap("light");
        });
      });
      $(root, "#tg-max").addEventListener("click", function () { if (!T.busy) { $(root, "#triplegold-stake").value = T.max; hap("light"); } });
      $(root, "#tg-go").addEventListener("click", function () { if (!T.busy) spin(root); });
      $(root, "#tg-auto").addEventListener("click", function () { if (T.auto > 0) { T.auto = 0; paint(root); } else if (!T.busy) { T.auto = 10; paint(root); spin(root); } });
      T.grid = [[rnd(), rnd(), rnd()], [rnd(), rnd(), rnd()], [rnd(), rnd(), rnd()]];
    }
    await load(); paint(root);
  };

  function cellHtml(root) {
    root.querySelectorAll(".tg-cell").forEach(function (c) { var r = +c.dataset.r, k = +c.dataset.c; c.innerHTML = sym(T.grid[r][k], 52); c.classList.toggle("win", !!T.win && r === 1); });
  }
  function paint(root) {
    if (T.table) {
      var tp = T.table.filter(function (x) { return x.kind === "three"; }).reduce(function (a, x) { return Math.max(a, x.multiplier); }, 0);
      $(root, "#tg-top").textContent = "x" + xf(tp);
      $(root, "#tg-pay").innerHTML = T.table.map(function (x) {
        var n = x.kind === "two" ? 2 : 3;
        return '<div class="tg-chip"><span class="ic">' + sym(x.symbol, 22).replace(/(width|height)="[\d.]+"/g, function (m) { return m; }) + '</span><small>' + n + '×</small><b>x' + xf(x.multiplier) + "</b></div>";
      }).join("");
    }
    $(root, "#tg-last").textContent = money(T.last);
    root.querySelectorAll(".kx-step button,#tg-max").forEach(function (b) { b.disabled = T.busy; });
    $(root, "#triplegold-stake").disabled = T.busy;
    var g = $(root, "#tg-go"); g.disabled = T.busy || T.auto > 0; g.textContent = T.busy ? "…" : "Spin";
    var a = $(root, "#tg-auto"); a.textContent = T.auto > 0 ? "Stop (" + T.auto + ")" : "Auto"; a.classList.toggle("on", T.auto > 0);
    cellHtml(root);
  }

  async function spin(root) {
    if (T.busy) return;
    var msg = $(root, "#tg-msg"), proof = $(root, "#tg-proof"), win = $(root, "#tg-win"), stake = Number($(root, "#triplegold-stake").value);
    if (!(stake > 0)) { T.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; paint(root); return; }
    if (stake < T.min || stake > T.max) { T.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + T.min + " እስከ " + T.max + " ብር መሆን አለበት"; paint(root); return; }
    T.busy = true; T.win = null; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; win.textContent = ""; paint(root); hap("light");
    var cells = root.querySelectorAll(".tg-cell"), spinning = [true, true, true];
    var timer = setInterval(function () {
      for (var k = 0; k < 3; k++) if (spinning[k]) for (var r = 0; r < 3; r++) T.grid[r][k] = rnd();
      cellHtml(root); cells.forEach(function (c) { c.classList.add("spin"); });
    }, 80);
    var ok = true;
    try {
      var r0 = await startRealtimeRound(KEY, { stake: stake });
      proof.textContent = "ROUND " + (r0.round_code || "") + " · COMMIT " + String(r0.seed_commit || r0.commitment || "").slice(0, 16) + "…";
      var rr = await realtimeAction(KEY, "play"), o = rr.outcome || {}, g = o.grid;
      if (!g || g.length !== 3) throw new Error("bad server grid");
      for (var k = 0; k < 3; k++) {
        await new Promise(function (res) { setTimeout(res, k === 0 ? 700 : 350); });
        spinning[k] = false; for (var r = 0; r < 3; r++) T.grid[r][k] = g[r][k]; hap("light");
        cells.forEach(function (c) { if (+c.dataset.c === k) c.classList.remove("spin"); }); cellHtml(root);
      }
      var pay = Number(rr.payout || 0); T.last = pay; T.win = pay > 0 ? true : null;
      if (pay > stake) { msg.className = "kx-msg win"; win.innerHTML = 'WIN <b>' + money(pay) + "</b> ETB"; msg.textContent = "🎉 +" + money(pay - stake) + " ብር"; hap("success"); }
      else if (pay > 0) { msg.className = "kx-msg lose"; win.innerHTML = 'WIN <b>' + money(pay) + "</b> ETB"; msg.textContent = "ከውርርድዎ ክፍል " + money(pay) + " ብር ተመልሷል"; }
      else { msg.className = "kx-msg lose"; msg.textContent = "-" + money(stake) + " ብር"; hap("error"); }
      if (rr.server_seed) proof.textContent = "ROUND " + (rr.round_code || "") + " · SERVER SEED " + String(rr.server_seed).slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { ok = false; T.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; }
    clearInterval(timer); cells.forEach(function (c) { c.classList.remove("spin"); });
    T.busy = false;
    if (T.auto > 0) T.auto--;
    paint(root);
    if (ok && T.auto > 0) setTimeout(function () { if (T.auto > 0 && !T.busy) spin(root); }, 900);
  }
})();
