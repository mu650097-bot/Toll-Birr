/* BUFFALO PLAINS: 5x3 slot, 243 ways, coin scatters start the Stampede Bonus (free spins, wins x2). The SERVER stops every
   reel (base spin and each free spin), evaluates the ways, applies the disclosed edge and pays in one round; this file only
   replays the spins the server returned. Loaded after app.js. */
(function () {
  "use strict";
  var KEY = "buffalo", SYMS = ["J", "Q", "K", "A", "cactus", "wolf", "eagle", "buffalo", "coin"];
  var B = { min: 1, max: 10000, table: null, fs: { 3: 8, 4: 12, 5: 20 }, mult: 2, loaded: false, busy: false, auto: 0, skip: false, win: 0, last: 0, free: 0, coins: 0, grid: null, hl: {} };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, B.skip ? 15 : ms); }); };
  function xf(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : String(+m.toFixed(2)); }
  function letter(t, c) { return '<svg viewBox="0 0 64 64" width="100%" height="100%"><text x="32" y="50" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" font-size="54" fill="' + c + '">' + t + "</text></svg>"; }
  function sym(n) {
    var h = '<svg viewBox="0 0 64 64" width="100%" height="100%">';
    if (n === "J") return letter("J", "#60a5fa"); if (n === "Q") return letter("Q", "#c084fc"); if (n === "K") return letter("K", "#fbbf24"); if (n === "A") return letter("A", "#fb7185");
    if (n === "cactus") return h + '<path d="M28 58V16a5 5 0 0 1 10 0v42z" fill="#16a34a" stroke="#14532d" stroke-width="2"/><path d="M28 36h-8a4 4 0 0 1-4-4V24a3 3 0 0 1 6 0v6h6M38 30h8a4 4 0 0 0 4-4v-6a3 3 0 0 0-6 0v4h-6" fill="none" stroke="#16a34a" stroke-width="6" stroke-linejoin="round"/><circle cx="33" cy="7" r="3.5" fill="#f472b6"/></svg>';
    if (n === "wolf") return h + '<path d="M8 10l14 10h20l14-10-4 24-10 20H22L12 34z" fill="#94a3b8" stroke="#334155" stroke-width="2.5" stroke-linejoin="round"/><path d="M26 54l6-10 6 10z" fill="#e2e8f0"/><circle cx="24" cy="32" r="3" fill="#fde047"/><circle cx="40" cy="32" r="3" fill="#fde047"/><path d="M28 44h8" stroke="#1e293b" stroke-width="2.5" stroke-linecap="round"/></svg>';
    if (n === "eagle") return h + '<path d="M2 26c10-4 20-2 30 6 10-8 20-10 30-6-6 12-16 18-30 16C18 44 8 38 2 26z" fill="#92400e" stroke="#451a03" stroke-width="2.5"/><circle cx="32" cy="22" r="8" fill="#f8fafc" stroke="#451a03" stroke-width="2"/><path d="M36 22l8 3-8 3z" fill="#f59e0b"/><circle cx="30" cy="20" r="1.8" fill="#111"/></svg>';
    if (n === "buffalo") return h + '<path d="M4 20c4 6 10 6 14 2M60 20c-4 6-10 6-14 2" stroke="#f1f5f9" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M14 22c0-8 8-12 18-12s18 4 18 12v18c0 10-6 18-18 18s-18-8-18-18z" fill="#7c2d12" stroke="#2a0e05" stroke-width="2.5"/><ellipse cx="32" cy="46" rx="10" ry="8" fill="#a16207"/><circle cx="23" cy="33" r="2.6" fill="#fff"/><circle cx="41" cy="33" r="2.6" fill="#fff"/><circle cx="28" cy="46" r="1.8" fill="#2a0e05"/><circle cx="36" cy="46" r="1.8" fill="#2a0e05"/></svg>';
    return h + '<circle cx="32" cy="32" r="26" fill="#fbbf24" stroke="#b45309" stroke-width="4"/><circle cx="32" cy="32" r="19" fill="none" stroke="#b45309" stroke-width="2.5"/><text x="32" y="43" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" font-size="30" fill="#92400e">B</text></svg>';
  }
  function rnd() { return SYMS[Math.floor(Math.random() * SYMS.length)]; }
  function randGrid() { return [0, 1, 2].map(function () { return [rnd(), rnd(), rnd(), rnd(), rnd()]; }); }
  function load() {
    if (B.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      B.min = Number(s.min_stake) || 1; B.max = Number(s.max_stake) || 10000; if (s.buffalo_table) B.table = s.buffalo_table;
      if (s.buffalo_free_spins) B.fs = s.buffalo_free_spins; if (s.buffalo_fs_mult) B.mult = Number(s.buffalo_fs_mult); B.loaded = true;
    }).catch(function () { B.loaded = true; });
  }

  window.setupBuffalo = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var cs = ""; for (var r = 0; r < 3; r++) for (var c = 0; c < 5; c++) cs += '<div class="bf-cell" data-r="' + r + '" data-c="' + c + '"></div>';
      root.innerHTML = '<div class="bf-wrap"><div class="bf-banner"><b>BUFFALO PLAINS</b><span>243 WAYS</span></div><div class="bf-board"><div class="bf-grid" id="bf-grid">' + cs + '</div><div class="bf-flash" id="bf-flash"></div></div>' +
        '<div class="bf-stats"><div class="kx-tile"><small>Win</small><b id="bf-win" class="g">0.00</b></div><div class="kx-tile"><small>Stampede Bonus</small><div class="fl-bar"><i id="bf-bar"></i></div><em id="bf-coins">🪙 0 / 3</em></div><div class="kx-tile"><small>Free spins</small><b id="bf-free" class="y">0</b></div></div>' +
        '<div class="av-card"><div class="av-bet-col"><label for="buffalo-stake">Bet Amount</label><div class="kn-row"><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="buffalo-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="20"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="kn-sm" id="bf-max" style="grid-column:3">Max Bet</button></div></div>' +
        '<div class="tg-btns"><button type="button" class="kn-sm tg-auto" id="bf-auto">Auto</button><button type="button" id="bf-go" class="av-go">Spin</button></div>' +
        '<div class="kx-msg" id="bf-msg" aria-live="polite"></div><div class="kx-proof" id="bf-proof"></div></div>' +
        '<div class="av-card"><div class="av-h">ክፍያዎች (ለአንድ way፣ ከጠቅላላ ውርርድ ስንት እጥፍ)</div><div class="bf-table" id="bf-table"></div></div>' +
        '<small class="kx-note">243 ways፦ ተመሳሳይ ምልክት ከግራ በኩል ተከታታይ ሪሎች ላይ (ቢያንስ 3) ሲታይ ይከፍላል፤ ብዛታቸው በሪሎቹ ላይ ያሉት ቁጥሮች ብዜት ነው። 3 / 4 / 5 🪙 በየትኛውም ቦታ ሲወጣ Stampede Bonus (8 / 12 / 20 ነጻ ዙሮች) ይጀምራል፤ በነጻ ዙሮች ውስጥ ሁሉም ክፍያ x2 ነው። ክፍያዎቹ house edge ተቀንሶ የሚታዩ ናቸው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (B.busy) return; var i = $(root, "#buffalo-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(B.min, Math.min(B.max, v + Number(b.dataset.d) * st)); hap("light");
        });
      });
      $(root, "#bf-max").addEventListener("click", function () { if (!B.busy) { $(root, "#buffalo-stake").value = B.max; hap("light"); } });
      $(root, "#bf-go").addEventListener("click", function () { if (B.busy) { B.skip = true; } else spin(root); });
      $(root, "#bf-auto").addEventListener("click", function () { if (B.auto > 0) { B.auto = 0; paint(root); } else if (!B.busy) { B.auto = 10; paint(root); spin(root); } });
      B.grid = randGrid();
    }
    await load(); paint(root);
  };

  function drawGrid(root) {
    root.querySelectorAll(".bf-cell").forEach(function (c) { var r = +c.dataset.r, k = +c.dataset.c; c.innerHTML = sym(B.grid[r][k]); c.classList.toggle("win", !!B.hl[r + "," + k]); });
  }
  function paint(root) {
    if (B.table) $(root, "#bf-table").innerHTML = '<div class="bf-tr bf-th"><span></span><span>3</span><span>4</span><span>5</span></div>' + B.table.slice().reverse().map(function (x) {
      return '<div class="bf-tr"><span class="ic">' + sym(x.symbol) + "</span><span>x" + xf(x.x3) + "</span><span>x" + xf(x.x4) + "</span><span>x" + xf(x.x5) + "</span></div>";
    }).join("");
    $(root, "#bf-win").textContent = money(B.win); $(root, "#bf-free").textContent = B.free;
    $(root, "#bf-bar").style.width = Math.min(100, B.coins / 3 * 100) + "%"; $(root, "#bf-coins").textContent = "🪙 " + Math.min(B.coins, 5) + " / 3";
    root.querySelectorAll(".kx-step button,#bf-max").forEach(function (b) { b.disabled = B.busy; }); $(root, "#buffalo-stake").disabled = B.busy;
    var g = $(root, "#bf-go"); g.disabled = false; g.textContent = B.busy ? (B.free > 0 ? "Skip ›" : "…") : "Spin"; g.classList.toggle("dim", B.busy && B.free === 0);
    var a = $(root, "#bf-auto"); a.textContent = B.auto > 0 ? "Stop (" + B.auto + ")" : "Auto"; a.classList.toggle("on", B.auto > 0);
    drawGrid(root);
  }
  function highlight(sp) {
    var hl = {}; (sp.wins || []).forEach(function (w) {
      for (var k = 0; k < w.reels; k++) for (var r = 0; r < 3; r++) if (sp.grid[r][k] === w.symbol) hl[r + "," + k] = 1;
    }); return hl;
  }
  async function show(root, sp, spinMs) {   // one spin: reels stop left to right, then winning symbols light up
    var on = [true, true, true, true, true], cells = root.querySelectorAll(".bf-cell"); B.hl = {};
    var t = setInterval(function () { for (var k = 0; k < 5; k++) if (on[k]) for (var r = 0; r < 3; r++) B.grid[r][k] = rnd(); drawGrid(root); cells.forEach(function (c) { c.classList.toggle("spin", on[+c.dataset.c]); }); }, 70);
    for (var k = 0; k < 5; k++) { await sleep(k === 0 ? spinMs : spinMs / 3); on[k] = false; for (var r = 0; r < 3; r++) B.grid[r][k] = sp.grid[r][k]; }
    clearInterval(t); cells.forEach(function (c) { c.classList.remove("spin"); }); B.hl = highlight(sp); drawGrid(root);
  }

  async function spin(root) {
    if (B.busy) return;
    var msg = $(root, "#bf-msg"), proof = $(root, "#bf-proof"), flash = $(root, "#bf-flash"), stake = Number($(root, "#buffalo-stake").value);
    if (!(stake > 0)) { B.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; paint(root); return; }
    if (stake < B.min || stake > B.max) { B.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + B.min + " እስከ " + B.max + " ብር መሆን አለበት"; paint(root); return; }
    B.busy = true; B.skip = false; B.win = 0; B.free = 0; B.coins = 0; B.hl = {}; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; flash.textContent = ""; paint(root); hap("light");
    var ok = true;
    try {
      var r0 = await startRealtimeRound(KEY, { stake: stake });
      proof.textContent = "ROUND " + (r0.round_code || "") + " · COMMIT " + String(r0.seed_commit || r0.commitment || "").slice(0, 16) + "…";
      var rr = await realtimeAction(KEY, "play"), o = rr.outcome || {};
      if (!o.grid || o.grid.length !== 3) throw new Error("bad server grid");
      var tot = Number(o.base_multiple || 0) + Number(o.feature_multiple || 0), unit = tot > 0 ? Number(rr.payout || 0) / tot : 0;   // money per nominal multiple (stake x edge scale)
      var base = { grid: o.grid, wins: o.wins || [] }; B.coins = Number(o.scatters || 0);
      await show(root, base, 700); B.win = Number(o.base_multiple || 0) * unit; paint(root);
      if (o.free_spins > 0) {
        B.free = o.free_spins; flash.innerHTML = "🦬 <b>STAMPEDE BONUS</b> — " + o.free_spins + " ነጻ ዙሮች · ክፍያ x" + B.mult; hap("success"); paint(root); await sleep(1200);
        for (var i = 0; i < o.free_spin_rounds.length; i++) {
          var fs = o.free_spin_rounds[i]; await show(root, fs, 520); B.free = o.free_spins - i - 1; B.win += Number(fs.multiple || 0) * unit; B.coins = 0; paint(root); await sleep(260);
        }
        flash.innerHTML = "🦬 STAMPEDE BONUS ተጠናቋል";
      }
      var pay = Number(rr.payout || 0); B.win = pay; B.last = pay; B.free = 0;
      if (pay > stake) { msg.className = "kx-msg win"; msg.textContent = "🎉 +" + money(pay - stake) + " ብር"; hap("success"); }
      else if (pay > 0) { msg.className = "kx-msg lose"; msg.textContent = "ከውርርድዎ ክፍል " + money(pay) + " ብር ተመልሷል"; }
      else { msg.className = "kx-msg lose"; msg.textContent = "-" + money(stake) + " ብር"; hap("error"); }
      if (rr.server_seed) proof.textContent = "ROUND " + (rr.round_code || "") + " · SERVER SEED " + String(rr.server_seed).slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { ok = false; B.auto = 0; B.free = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; }
    B.busy = false; B.skip = false; if (B.auto > 0) B.auto--; paint(root);
    if (ok && B.auto > 0) setTimeout(function () { if (B.auto > 0 && !B.busy) spin(root); }, 1000);
  }
})();
