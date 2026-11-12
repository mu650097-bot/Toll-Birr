/* FLAME CLASSICS: 3-reel, one-row slot with a memoryless Hot Respin (1 in 8 on every paid spin). The SERVER stops the reels,
   draws the respin, applies the disclosed edge and pays; this file only draws what the server returns. Loaded after app.js. */
(function () {
  "use strict";
  var KEY = "flame", SYMS = ["cherry", "coal", "bell", "flame", "seven"];
  var F = { min: 1, max: 10000, table: null, hot: 8, loaded: false, busy: false, auto: 0, last: 0, row: ["flame", "flame", "flame"], win: false, heat: 0 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  function xf(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : String(+m.toFixed(2)); }
  function sym(n, s) {
    s = s || 84;
    if (n === "flame") return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><path d="M32 4c2 10 14 16 14 32a14 14 0 0 1-28 0c0-8 4-12 8-16 0 6 3 8 5 8 0-8-1-14 1-24z" fill="#ff5a0a"/><path d="M32 22c1 7 9 11 9 21a9 9 0 0 1-18 0c0-6 3-9 6-12 0 4 2 5 3 5 0-5-1-9 0-14z" fill="#ffb21e"/><path d="M32 40c1 4 5 5 5 10a5 5 0 0 1-10 0c0-4 3-6 5-10z" fill="#fff3c4"/></svg>';
    if (n === "coal") return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><path d="M12 44l6-18 14-8 16 6 6 18-12 12H24z" fill="#374151" stroke="#111827" stroke-width="2.5" stroke-linejoin="round"/><path d="M24 32l8-4 8 6" stroke="#6b7280" stroke-width="2.5" fill="none" stroke-linecap="round"/><circle cx="38" cy="44" r="3" fill="#f97316" opacity=".85"/></svg>';
    if (n === "bell") return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><path d="M32 6c-3 0-5 2-5 4-8 3-13 10-13 20 0 10-4 12-6 16h48c-2-4-6-6-6-16 0-10-5-17-13-20 0-2-2-4-5-4z" fill="#fbbf24" stroke="#b45309" stroke-width="2.5" stroke-linejoin="round"/><path d="M22 20c-3 4-4 9-4 14" stroke="#fef3c7" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="32" cy="54" r="5" fill="#d97706" stroke="#92400e" stroke-width="2"/></svg>';
    if (n === "cherry") return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><path d="M22 40C24 24 34 14 46 10M42 42C42 28 44 18 46 10" stroke="#15803d" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M46 10c6-4 12-2 14 2-6 2-11 1-14-2z" fill="#22c55e"/><circle cx="20" cy="44" r="12" fill="#dc2626" stroke="#7f1d1d" stroke-width="2"/><circle cx="42" cy="46" r="12" fill="#ef4444" stroke="#7f1d1d" stroke-width="2"/><circle cx="16" cy="40" r="3.2" fill="#fecaca"/><circle cx="38" cy="42" r="3.2" fill="#fecaca"/></svg>';
    return '<svg viewBox="0 0 64 64" width="' + s + '" height="' + s + '"><text x="32" y="54" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" font-size="64" fill="#e11d48" stroke="#7f1d1d" stroke-width="1.5">7</text></svg>';
  }
  function rnd() { return SYMS[Math.floor(Math.random() * SYMS.length)]; }
  function load() {
    if (F.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      F.min = Number(s.min_stake) || 1; F.max = Number(s.max_stake) || 10000; if (s.flame_table) F.table = s.flame_table; if (s.flame_hot_one_in) F.hot = Number(s.flame_hot_one_in); F.loaded = true;
    }).catch(function () { F.loaded = true; });
  }

  window.setupFlame = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="fl-wrap"><div class="fl-frame"><div class="fl-title">★ FLAME CLASSICS ★</div><div class="fl-reels" id="fl-reels"><div class="fl-cell"></div><div class="fl-cell"></div><div class="fl-cell"></div><i class="fl-line"></i></div><div class="fl-res" id="fl-res"></div></div>' +
        '<div class="fl-stats"><div class="fl-tile fl-heat"><small>Heat meter</small><div class="fl-bar"><i id="fl-fill"></i></div><em id="fl-hint">Hot Respin: 1 in ' + F.hot + ' every spin</em></div><div class="fl-tile"><small>Last win</small><b id="fl-last" class="g">0.00</b></div></div>' +
        '<div class="tg-pay" id="fl-pay"></div>' +
        '<div class="av-card"><div class="av-bet-col"><label for="flame-stake">Bet Amount</label><div class="kn-row"><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="flame-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="100"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="kn-sm" id="fl-max" style="grid-column:3">Max Bet</button></div></div>' +
        '<div class="tg-btns"><button type="button" class="kn-sm tg-auto" id="fl-auto">Auto</button><button type="button" id="fl-go" class="av-go fl-spin">Spin</button></div>' +
        '<div class="kx-msg" id="fl-msg" aria-live="polite"></div><div class="kx-proof" id="fl-proof"></div></div>' +
        '<small class="kx-note">መስመሩ ሦስት ተመሳሳይ ምልክት ወይም ሁለት 🍒 ሲይዝ ይከፍላል። በእያንዳንዱ ዙር 1 ከ ' + F.hot + ' ዕድል Hot Respin (በነጻ ተጨማሪ ዙር) ይኖራል፤ ይህ ቆጣሪ የሌለው ስለሆነ አወራረድዎን በማስተካከል ማሸነፍ አይቻልም። ክፍያዎቹ house edge ተቀንሶ የሚታዩ ናቸው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (F.busy) return; var i = $(root, "#flame-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(F.min, Math.min(F.max, v + Number(b.dataset.d) * st)); hap("light");
        });
      });
      $(root, "#fl-max").addEventListener("click", function () { if (!F.busy) { $(root, "#flame-stake").value = F.max; hap("light"); } });
      $(root, "#fl-go").addEventListener("click", function () { if (!F.busy) spin(root); });
      $(root, "#fl-auto").addEventListener("click", function () { if (F.auto > 0) { F.auto = 0; paint(root); } else if (!F.busy) { F.auto = 10; paint(root); spin(root); } });
    }
    await load(); paint(root);
  };

  function cells(root) { var c = root.querySelectorAll(".fl-cell"); c.forEach(function (x, i) { x.innerHTML = sym(F.row[i], 84); }); $(root, "#fl-reels").classList.toggle("win", F.win); }
  function paint(root) {
    if (F.table) $(root, "#fl-pay").innerHTML = F.table.map(function (x) {
      return '<div class="tg-chip"><span class="ic">' + sym(x.symbol, 22) + '</span><small>' + (x.kind === "two" ? 2 : 3) + '×</small><b>x' + xf(x.multiplier) + "</b></div>";
    }).join("");
    $(root, "#fl-last").textContent = money(F.last); $(root, "#fl-fill").style.width = F.heat + "%";
    root.querySelectorAll(".kx-step button,#fl-max").forEach(function (b) { b.disabled = F.busy; }); $(root, "#flame-stake").disabled = F.busy;
    var g = $(root, "#fl-go"); g.disabled = F.busy || F.auto > 0; g.textContent = F.busy ? "…" : "Spin";
    var a = $(root, "#fl-auto"); a.textContent = F.auto > 0 ? "Stop (" + F.auto + ")" : "Auto"; a.classList.toggle("on", F.auto > 0);
    cells(root);
  }
  async function reelsTo(root, line) {
    var cs = root.querySelectorAll(".fl-cell"), on = [true, true, true];
    var t = setInterval(function () { for (var k = 0; k < 3; k++) if (on[k]) F.row[k] = rnd(); cells(root); cs.forEach(function (c, k) { c.classList.toggle("spin", on[k]); }); }, 80);
    for (var k = 0; k < 3; k++) { await sleep(k === 0 ? 650 : 330); on[k] = false; F.row[k] = line[k]; hap("light"); }
    clearInterval(t); cs.forEach(function (c) { c.classList.remove("spin"); }); cells(root);
  }

  async function spin(root) {
    if (F.busy) return;
    var msg = $(root, "#fl-msg"), proof = $(root, "#fl-proof"), res = $(root, "#fl-res"), stake = Number($(root, "#flame-stake").value);
    if (!(stake > 0)) { F.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; paint(root); return; }
    if (stake < F.min || stake > F.max) { F.auto = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + F.min + " እስከ " + F.max + " ብር መሆን አለበት"; paint(root); return; }
    F.busy = true; F.win = false; F.heat = 0; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; res.textContent = ""; paint(root); hap("light");
    var ok = true;
    try {
      var r0 = await startRealtimeRound(KEY, { stake: stake });
      proof.textContent = "ROUND " + (r0.round_code || "") + " · COMMIT " + String(r0.seed_commit || r0.commitment || "").slice(0, 16) + "…";
      var rr = await realtimeAction(KEY, "play"), o = rr.outcome || {}, sp = o.spins;
      if (!Array.isArray(sp) || !sp.length) throw new Error("bad server result");
      F.heat = 25; paint(root); await reelsTo(root, sp[0].line);
      if (sp.length > 1) {
        F.heat = 100; $(root, "#fl-hint").textContent = "🔥 HOT RESPIN!"; res.innerHTML = "🔥 <b>HOT RESPIN</b> — ነጻ ተጨማሪ ዙር"; hap("success"); paint(root);
        await sleep(900); await reelsTo(root, sp[1].line);
      }
      var pay = Number(rr.payout || 0); F.last = pay; F.win = pay > 0; $(root, "#fl-hint").textContent = "Hot Respin: 1 in " + F.hot + " every spin"; F.heat = 0;
      if (pay > stake) { msg.className = "kx-msg win"; res.innerHTML = "WIN <b>+" + money(pay) + "</b>"; msg.textContent = "🎉 +" + money(pay - stake) + " ብር"; hap("success"); }
      else if (pay > 0) { msg.className = "kx-msg lose"; res.innerHTML = "WIN <b>+" + money(pay) + "</b>"; msg.textContent = "ከውርርድዎ ክፍል " + money(pay) + " ብር ተመልሷል"; }
      else { msg.className = "kx-msg lose"; msg.textContent = "-" + money(stake) + " ብር"; hap("error"); }
      if (rr.server_seed) proof.textContent = "ROUND " + (rr.round_code || "") + " · SERVER SEED " + String(rr.server_seed).slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { ok = false; F.auto = 0; F.heat = 0; msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; }
    F.busy = false; if (F.auto > 0) F.auto--; paint(root);
    if (ok && F.auto > 0) setTimeout(function () { if (F.auto > 0 && !F.busy) spin(root); }, 900);
  }
})();
