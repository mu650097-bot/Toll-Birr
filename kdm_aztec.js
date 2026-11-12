/* AZTEC GOLD: 3x3 slot, 5 fixed paylines (3 rows + 2 diagonals), total bet split over the lines. The SERVER stops the reels,
   evaluates every line, applies the disclosed edge and pays; this file only draws the grid and the winning lines it returns. */
(function () {
  "use strict";
  var KEY = "aztec", SYMS = ["gem", "snake", "corn", "mask", "sun"], LINES = [[0, 0, 0], [1, 1, 1], [2, 2, 2], [0, 1, 2], [2, 1, 0]];
  var Z = { min: 1, max: 10000, table: null, lines: LINES, loaded: false, busy: false, auto: 0, last: 0, wins: [], grid: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  function xf(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : String(+m.toFixed(2)); }
  function sym(n, s) {
    s = s || 60;
    var h = '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '">';
    if (n === "gem") return h + '<path d="M32 6l20 22-20 30L12 28z" fill="#10b981" stroke="#d1fae5" stroke-width="2.5" stroke-linejoin="round"/><path d="M12 28h40M32 6l-8 22 8 30 8-30z" fill="none" stroke="#d1fae5" stroke-width="1.8" opacity=".85"/></svg>';
    if (n === "snake") return h + '<path d="M12 50c10 6 22 2 22-8s-18-8-18-18 12-14 28-8" stroke="#84cc16" stroke-width="9" fill="none" stroke-linecap="round"/><path d="M12 50c10 6 22 2 22-8s-18-8-18-18 12-14 28-8" stroke="#3f6212" stroke-width="2" stroke-dasharray="3 7" fill="none" stroke-linecap="round"/><circle cx="46" cy="14" r="2.4" fill="#111"/><path d="M52 14l7-2-5 5" fill="#ef4444"/></svg>';
    if (n === "corn") return h + '<path d="M32 6c9 7 13 17 13 28 0 8-5 15-13 15s-13-7-13-15c0-11 4-21 13-28z" fill="#facc15" stroke="#a16207" stroke-width="2.5"/><path d="M32 10v38M24 22h16M22 32h20M24 42h16" stroke="#a16207" stroke-width="1.8" opacity=".7"/><path d="M32 60c-12-2-18-10-18-18 8 2 14 6 18 12 4-6 10-10 18-12 0 8-6 16-18 18z" fill="#22c55e"/></svg>';
    if (n === "mask") return h + '<rect x="12" y="6" width="40" height="52" rx="10" fill="#78716c" stroke="#292524" stroke-width="3"/><rect x="18" y="12" width="28" height="7" fill="#fbbf24"/><rect x="18" y="24" width="10" height="8" fill="#14b8a6"/><rect x="36" y="24" width="10" height="8" fill="#14b8a6"/><path d="M22 42h20M22 49h20" stroke="#292524" stroke-width="3.2" stroke-linecap="round"/></svg>';
    return h + '<g stroke="#f97316" stroke-width="4" stroke-linecap="round"><path d="M32 3v9M32 52v9M3 32h9M52 32h9M11 11l6 6M47 47l6 6M53 11l-6 6M17 47l-6 6"/></g><circle cx="32" cy="32" r="15" fill="#fbbf24" stroke="#c2410c" stroke-width="3"/><circle cx="27" cy="29" r="2" fill="#7c2d12"/><circle cx="37" cy="29" r="2" fill="#7c2d12"/><path d="M26 37c4 4 8 4 12 0" stroke="#7c2d12" stroke-width="2.5" fill="none" stroke-linecap="round"/></svg>';
  }
  function rnd() { return SYMS[Math.floor(Math.random() * SYMS.length)]; }
  function randGrid() { return [0, 1, 2].map(function () { return [rnd(), rnd(), rnd()]; }); }
  function load() {
    if (Z.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      Z.min = Number(s.min_stake) || 1; Z.max = Number(s.max_stake) || 10000; if (s.aztec_table) Z.table = s.aztec_table; if (s.aztec_lines) Z.lines = s.aztec_lines; Z.loaded = true;
    }).catch(function () { Z.loaded = true; });
  }

  window.setupAztec = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var cs = ""; for (var r = 0; r < 3; r++) for (var c = 0; c < 3; c++) cs += '<div class="az-cell" data-r="' + r + '" data-c="' + c + '"></div>';
      root.innerHTML = '<div class="az-wrap"><div class="az-frame"><div class="az-title">AZTEC GOLD</div><div class="az-grid" id="az-grid">' + cs + '<svg class="az-lines" id="az-lines" viewBox="0 0 300 300" preserveAspectRatio="none"></svg></div></div>' +
        '<div class="az-stats"><div class="kx-tile"><small>Win lines</small><b id="az-wl">0 / 5</b></div><div class="kx-tile"><small>Last Win</small><b id="az-last" class="g">0.00</b></div><div class="kx-tile"><small>Top line</small><b id="az-top" class="y">—</b></div></div>' +
        '<div class="tg-pay" id="az-pay"></div>' +
        '<div class="av-card"><div class="av-bet-col"><label for="aztec-stake">Bet Amount (5 መስመሮች)</label><div class="kn-row"><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="aztec-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="10"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="kn-sm" id="az-max" style="grid-column:3">Max Bet</button></div></div>' +
        '<div class="tg-btns"><button type="button" class="kn-sm tg-auto" id="az-auto">Auto</button><button type="button" id="az-go" class="av-go">Spin</button></div>' +
        '<div class="kx-msg" id="az-msg" aria-live="polite"></div><div class="kx-proof" id="az-proof"></div></div>' +
        '<small class="kx-note">ጠቅላላ ውርርድዎ በ5 መስመሮች እኩል ይከፈላል (3 ረድፎች + 2 ሰያፎች)። መስመር ሦስት ተመሳሳይ ምልክት ሲይዝ ይከፍላል፤ የመስመሮች ድምር ይከፈላል። በሰንጠረዡ ያለው ማባዣ አንድ አሸናፊ መስመር ከጠቅላላ ውርርድዎ ስንት እጥፍ እንደሚከፍል ያሳያል (house edge ተቀንሶ)።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (Z.busy) return; var i = $(root, "#aztec-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(Z.min, Math.min(Z.max, v + Number(b.dataset.d) * st)); hap("light");
        });
      });
      $(root, "#az-max").addEventListener("click", function () { if (!Z.busy) { $(root, "#aztec-stake").value = Z.max; hap("light"); } });
      $(root, "#az-go").addEventListener("click", function () { if (!Z.busy) spin(root); });
      $(root, "#az-auto").addEventListener("click", function () { if (Z.auto > 0) { Z.auto = 0; paint(root); } else if (!Z.busy) { Z.auto = 10; paint(root); spin(root); } });
      Z.grid = randGrid();
    }
    await load(); paint(root);
  };

  function drawGrid(root) {
    var won = {}; Z.wins.forEach(function (w) { Z.lines[w.line].forEach(function (row, k) { won[row + "," + k] = 1; }); });
    root.querySelectorAll(".az-cell").forEach(function (c) { var r = +c.dataset.r, k = +c.dataset.c; c.innerHTML = sym(Z.grid[r][k], 60); c.classList.toggle("win", !!won[r + "," + k]); });
    var sv = $(root, "#az-lines"), h = "";
    Z.wins.forEach(function (w) { var pts = Z.lines[w.line].map(function (row, k) { return (50 + k * 100) + "," + (50 + row * 100); }).join(" "); h += '<polyline points="' + pts + '" fill="none" stroke="#fcd34d" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" opacity=".9"/>'; });
    sv.innerHTML = h;
  }
  function paint(root) {
    if (Z.table) {
      $(root, "#az-top").textContent = "x" + xf(Z.table.reduce(function (a, x) { return Math.max(a, x.multiplier); }, 0));
      $(root, "#az-pay").innerHTML = Z.table.map(function (x) { return '<div class="tg-chip"><span class="ic">' + sym(x.symbol, 22) + "</span><small>3× / መስመር</small><b>x" + xf(x.multiplier) + "</b></div>"; }).join("");
    }
    $(root, "#az-wl").textContent = Z.wins.length + " / 5"; $(root, "#az-last").textContent = money(Z.last);
    root.querySelectorAll(".kx-step button,#az-max").forEach(function (b) { b.disabled = Z.busy; }); $(root, "#aztec-stake").disabled = Z.busy;
    var g = $(root, "#az-go"); g.disabled = Z.busy || Z.auto > 0; g.textContent = Z.busy ? "…" : "Spin";
    var a = $(root, "#az-auto"); a.textContent = Z.auto > 0 ? "Stop (" + Z.auto + ")" : "Auto"; a.classList.toggle("on", Z.auto > 0);
    drawGrid(root);
  }

  async function spin(root) {
    if (Z.busy) return;
    var msg = $(root, "#az-msg"), proof = $(root, "#az-proof"), stake = Number($(root, "#aztec-stake").value);
    if (!(stake > 0)) { Z.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; paint(root); return; }
    if (stake < Z.min || stake > Z.max) { Z.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + Z.min + " እስከ " + Z.max + " ብር መሆን አለበት"; paint(root); return; }
    Z.busy = true; Z.wins = []; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; paint(root); hap("light");
    var cells = root.querySelectorAll(".az-cell"), on = [true, true, true], ok = true;
    var t = setInterval(function () { for (var k = 0; k < 3; k++) if (on[k]) for (var r = 0; r < 3; r++) Z.grid[r][k] = rnd(); drawGrid(root); cells.forEach(function (c) { c.classList.toggle("spin", on[+c.dataset.c]); }); }, 80);
    try {
      var r0 = await startRealtimeRound(KEY, { stake: stake });
      proof.textContent = "ROUND " + (r0.round_code || "") + " · COMMIT " + String(r0.seed_commit || r0.commitment || "").slice(0, 16) + "…";
      var rr = await realtimeAction(KEY, "play"), o = rr.outcome || {}, g = o.grid;
      if (!g || g.length !== 3) throw new Error("bad server grid");
      for (var k = 0; k < 3; k++) { await sleep(k === 0 ? 650 : 330); on[k] = false; for (var r = 0; r < 3; r++) Z.grid[r][k] = g[r][k]; hap("light"); }
      clearInterval(t); cells.forEach(function (c) { c.classList.remove("spin"); });
      var pay = Number(rr.payout || 0); Z.last = pay; Z.wins = (o.wins || []).map(function (w) { return { line: Number(w.line) }; });
      if (pay > stake) { msg.className = "kx-msg win"; msg.textContent = "🎉 " + Z.wins.length + " መስመር · +" + money(pay - stake) + " ብር"; hap("success"); }
      else if (pay > 0) { msg.className = "kx-msg lose"; msg.textContent = Z.wins.length + " መስመር · ከውርርድዎ ክፍል " + money(pay) + " ብር ተመልሷል"; }
      else { msg.className = "kx-msg lose"; msg.textContent = "-" + money(stake) + " ብር"; hap("error"); }
      if (rr.server_seed) proof.textContent = "ROUND " + (rr.round_code || "") + " · SERVER SEED " + String(rr.server_seed).slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { ok = false; Z.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; }
    clearInterval(t); cells.forEach(function (c) { c.classList.remove("spin"); });
    Z.busy = false; if (Z.auto > 0) Z.auto--; paint(root);
    if (ok && Z.auto > 0) setTimeout(function () { if (Z.auto > 0 && !Z.busy) spin(root); }, 900);
  }
})();
