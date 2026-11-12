/* KENO (classic): pick 1-10 of 80, the SERVER draws 20 (hypergeometric), applies the disclosed edge and pays.
   This file only draws the board and animates the server's draw. Loaded after app.js. */
(function () {
  "use strict";
  var KEY = "keno", MAXP = 10;
  var K = { min: 1, max: 10000, tables: null, loaded: false, busy: false, picks: [], draw: [], hits: null, win: 0, shown: 0, over: false };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  function xf(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : String(+m.toFixed(2)); }

  function load() {
    if (K.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      K.min = Number(s.min_stake) || 1; K.max = Number(s.max_stake) || 10000; if (s.keno_tables) K.tables = s.keno_tables; K.loaded = true;
    }).catch(function () { K.loaded = true; });
  }

  window.setupKeno = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var cells = ""; for (var i = 1; i <= 80; i++) cells += '<button type="button" class="kn-num" data-n="' + i + '">' + i + "</button>";
      root.innerHTML = '<div class="kn-wrap"><div class="kn-stats"><div class="kx-tile"><small>Picked</small><b id="kn-picked">0 / 10</b></div><div class="kx-tile"><small>Hits</small><b id="kn-hits" class="g">0</b></div><div class="kx-tile"><small>Your win</small><b id="kn-win" class="g">0.00</b></div></div>' +
        '<div class="kn-board"><div class="kn-grid" id="kn-grid">' + cells + '</div>' +
        '<div class="kn-legend"><span><i class="h"></i>Hit</span><span><i class="p"></i>Picked</span><span><i class="d"></i>Drawn</span></div></div>' +
        '<div class="kn-pay" id="kn-pay"></div>' +
        '<div class="av-card"><div class="av-bet-col"><label for="keno-stake">Bet Amount</label><div class="kn-row"><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="keno-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="kn-sm" id="kn-auto">Auto pick</button><button type="button" class="kn-sm" id="kn-clear">Clear</button></div></div>' +
        '<button type="button" id="kn-go" class="av-go">Play</button><div class="kx-msg" id="kn-msg" aria-live="polite"></div><div class="kx-proof" id="kn-proof"></div></div>' +
        '<small class="kx-note">1 እስከ 10 ቁጥሮች ከ80 ይምረጡ፤ ሰርቨሩ 20 ቁጥሮች ይመዝናል። ብዙ ቁጥር ባገኙ መጠን ክፍያው ይጨምራል። ሰንጠረዡ ቀድሞ house edge ተቀንሶ የሚታይ ነው።</small></div>';
      root.querySelectorAll(".kn-num").forEach(function (c) { c.addEventListener("click", function () { toggle(root, Number(c.dataset.n)); }); });
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (K.busy) return; var i = $(root, "#keno-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(K.min, Math.min(K.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#keno-stake").addEventListener("input", function () { paint(root); });
      $(root, "#kn-clear").addEventListener("click", function () { if (K.busy) return; K.picks = []; reset(); paint(root); });
      $(root, "#kn-auto").addEventListener("click", function () {
        if (K.busy) return; var n = K.picks.length || 5, pool = []; for (var i = 1; i <= 80; i++) pool.push(i);
        for (var j = pool.length - 1; j > 0; j--) { var k = Math.floor(Math.random() * (j + 1)), t = pool[j]; pool[j] = pool[k]; pool[k] = t; }
        K.picks = pool.slice(0, n).sort(function (a, b) { return a - b; }); reset(); hap("light"); paint(root);
      });
      $(root, "#kn-go").addEventListener("click", function () { play(root); });
    }
    await load(); paint(root);
  };
  function reset() { K.draw = []; K.hits = null; K.win = 0; K.shown = 0; K.over = false; }
  function toggle(root, n) {
    if (K.busy) return; if (K.over) reset();
    var i = K.picks.indexOf(n);
    if (i >= 0) K.picks.splice(i, 1); else if (K.picks.length < MAXP) K.picks.push(n); else return hap("error");
    hap("light"); paint(root);
  }
  function paint(root) {
    var drawn = K.draw.slice(0, K.shown), n = K.picks.length;
    $(root, "#kn-picked").textContent = n + " / " + MAXP;
    $(root, "#kn-hits").textContent = K.hits == null ? "0" : K.hits;
    $(root, "#kn-win").textContent = money(K.win);
    root.querySelectorAll(".kn-num").forEach(function (c) {
      var x = Number(c.dataset.n), p = K.picks.indexOf(x) >= 0, d = drawn.indexOf(x) >= 0;
      c.className = "kn-num" + (p && d ? " hit" : p ? " pick" : d ? " drawn" : ""); c.disabled = K.busy;
    });
    var tb = K.tables && K.tables[String(n)], pay = $(root, "#kn-pay"), html = "";
    if (tb) for (var h = 1; h < tb.length; h++) if (tb[h] > 0) html += '<div class="kn-chip' + (K.over && K.hits === h ? " on" : "") + '"><small>' + h + ' hits</small><b>x' + xf(tb[h]) + "</b></div>";
    pay.innerHTML = html || '<div class="kn-hint">ቁጥሮችን ይምረጡ</div>';
    root.querySelectorAll(".kx-step button,#kn-auto,#kn-clear").forEach(function (b) { b.disabled = K.busy; });
    var g = $(root, "#kn-go"); g.disabled = K.busy || n < 1; g.textContent = K.busy ? "…" : "Play";
  }
  async function play(root) {
    if (K.busy) return; var msg = $(root, "#kn-msg"), proof = $(root, "#kn-proof"), stake = Number($(root, "#keno-stake").value);
    if (K.picks.length < 1) { msg.className = "kx-msg bad"; msg.textContent = "❌ ቢያንስ 1 ቁጥር ይምረጡ"; return; }
    if (!(stake > 0)) { msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; return; }
    if (stake < K.min || stake > K.max) { msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + K.min + " እስከ " + K.max + " ብር መሆን አለበት"; return; }
    reset(); K.busy = true; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; paint(root); hap("light");
    try {
      var r = await startRealtimeRound(KEY, { stake: stake, numbers: K.picks.slice(), grid: 80 });
      proof.textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || r.commitment || "").slice(0, 16) + "…";
      var rr = await realtimeAction(KEY, "play"), o = rr.outcome || {};
      K.draw = (o.draw || []).map(Number);
      for (var i = 1; i <= K.draw.length; i++) { K.shown = i; paint(root); await new Promise(function (res) { setTimeout(res, 70); }); }
      K.hits = Number(o.hits || 0); K.win = Number(rr.payout || 0); K.over = true;
      if (K.win > stake) { msg.className = "kx-msg win"; msg.textContent = "🎉 " + K.hits + " hits · x" + xf(Number(o.multiplier || 0)) + " · +" + money(K.win - stake) + " ብር"; hap("success"); }
      else if (K.win > 0) { msg.className = "kx-msg lose"; msg.textContent = K.hits + " hits · " + money(K.win) + " ብር ተመልሷል"; hap("light"); }
      else { msg.className = "kx-msg lose"; msg.textContent = K.hits + " hits · -" + money(stake) + " ብር"; hap("error"); }
      if (rr.server_seed) proof.textContent = "ROUND " + (rr.round_code || "") + " · SERVER SEED " + String(rr.server_seed).slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; }
    K.busy = false; paint(root);
  }
})();
