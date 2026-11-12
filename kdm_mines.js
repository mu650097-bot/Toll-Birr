/* MINES (new look + mechanics): 5x5 board, open tiles one at a time, cash out whenever you like.
   The SERVER holds the mine layout (never sent while the round is active), decides every pick and pays.
   This file only draws what the server returns. Uses the engine key "minesx". Loaded after app.js. */
(function () {
  "use strict";
  var GK = "minesx", PAGE = "mines", OPTIONS = [1, 3, 5, 10];
  var S = { min: 1, max: 10000, edge: 0.05, loaded: false, busy: false, mines: 3, round: null, st: null, stake: 0, over: false, out: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var GEM = '<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path d="M6 3h12l4 6-10 12L2 9z" fill="#38bdf8" stroke="#e0f7ff" stroke-width="1.2" stroke-linejoin="round"/><path d="M2 9h20M9 3l-2 6 5 12 5-12-2-6" fill="none" stroke="#e0f7ff" stroke-width="1" opacity=".8"/></svg>';
  var BOMB = '<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><circle cx="11" cy="14" r="7" fill="#1f2937" stroke="#9ca3af" stroke-width="1.2"/><path d="M15 7l3-3" stroke="#fbbf24" stroke-width="2" stroke-linecap="round"/><circle cx="19" cy="3.5" r="1.6" fill="#f97316"/><circle cx="8.5" cy="12" r="1.6" fill="#e5e7eb" opacity=".7"/></svg>';

  function comb(n, k) { var r = 1; for (var i = 1; i <= k; i++) r = r * (n - k + i) / i; return r; }
  function mult(m, k, rtp) { return k < 1 ? 1 : rtp * comb(25, k) / comb(25 - m, k); }
  function progress() { return S.st ? Number(S.st.progress || 0) : 0; }
  function minesNow() { return S.st ? Number(S.st.mines) : S.mines; }
  function revealed() { return S.st && S.st.revealed ? S.st.revealed.map(Number) : []; }
  function active() { return !!S.round && !S.over; }

  function limits() {
    if (S.loaded) return Promise.resolve();
    return apiFetch("/games/" + GK + "/settings").then(function (s) {
      S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.edge = s.house_edge != null ? Number(s.house_edge) : 0.05; S.loaded = true;
    }).catch(function () { S.loaded = true; });
  }

  window.setupMines = async function () {
    var root = document.getElementById(PAGE + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(PAGE + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + PAGE); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var cells = ""; for (var i = 1; i <= 25; i++) cells += '<button type="button" class="mx-cell" data-t="' + i + '" aria-label="tile ' + i + '"></button>';
      var opts = OPTIONS.map(function (o) { return '<button type="button" data-m="' + o + '">' + o + "</button>"; }).join("");
      root.innerHTML = '<div class="mx-wrap">' +
        '<div class="mx-stats"><div class="kx-tile"><small>Mines</small><b id="mx-mines">3</b></div><div class="kx-tile"><small>Gems found</small><b id="mx-gems" class="b">0 / 22</b></div><div class="kx-tile"><small>Total win</small><b id="mx-win" class="g">0.00</b></div></div>' +
        '<div class="mx-board" id="mx-board">' + cells + '</div>' +
        '<div class="mx-info"><span>Next gem <b id="mx-next" class="b">—</b></span><span>Profit if cashed out <b id="mx-profit" class="g">—</b></span></div>' +
        '<div class="av-card"><div class="av-cols"><div class="av-bet-col"><label for="mines-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="mines-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="av-bet-col"><label>Mines</label><div class="mx-opts" id="mx-opts">' + opts + '</div></div></div>' +
        '<button type="button" id="mx-go" class="av-go">Bet</button><div class="kx-msg" id="mx-msg" aria-live="polite"></div><div class="kx-proof" id="mx-proof"></div></div>' +
        '<small class="kx-note">ሳጥኖቹን አንድ በአንድ ይክፈቱ፤ 💎 ባገኙ ቁጥር ማባዣው ይጨምራል። 💣 ከነኩ ያጣሉ። Cash Out ሲጫኑ እስካሁን ያገኙትን ይወስዳሉ። ፈንጂዎቹ የሚገኙበት ቦታ ሰርቨሩ ላይ ብቻ ነው፤ ዙሩ ሲያበቃ ይገለጣል።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || active()) return;
          var inp = $(root, "#mines-stake"), v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          inp.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#mines-stake").addEventListener("input", function () { paint(root); });
      root.querySelectorAll("#mx-opts button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || active()) return; S.mines = Number(b.dataset.m); hap("light"); paint(root); }); });
      root.querySelectorAll(".mx-cell").forEach(function (c) { c.addEventListener("click", function () { pick(root, Number(c.dataset.t)); }); });
      $(root, "#mx-go").addEventListener("click", function () { active() ? cash(root) : start(root); });
    }
    await limits();
    if (!S.round || S.over) {   // resume an unfinished round after the app was closed
      try { var a = await apiFetch("/games/" + GK + "/active"); if (a && a.round_id && a.status === "ACTIVE") { S.round = a; S.st = a.state; S.stake = Number(a.stake); S.over = false; S.out = null; S.mines = Number(a.state.mines); } } catch (_) {}
    }
    paint(root);
  };

  function paint(root) {
    var m = minesNow(), k = progress(), rev = revealed(), act = active(), rtp = 1 - S.edge, safeTotal = 25 - m;
    var stake = act || S.over ? S.stake : (Number($(root, "#mines-stake").value) || 0);
    $(root, "#mx-mines").textContent = m;
    $(root, "#mx-gems").textContent = k + " / " + safeTotal;
    var cur = S.over && S.out ? Number(S.out.payout || 0) : (k > 0 ? stake * (S.st && S.st.multipliers ? S.st.multipliers[k - 1] : mult(m, k, rtp)) : 0);
    $(root, "#mx-win").textContent = money(cur);
    var next = k < safeTotal ? (S.st && S.st.multipliers && act ? S.st.multipliers[k] : mult(m, k + 1, rtp)) : null;
    $(root, "#mx-next").textContent = act || !S.over ? (next ? "x" + next.toFixed(2) : "—") : "—";
    $(root, "#mx-profit").textContent = act && k > 0 ? (cur - stake >= 0 ? "+" : "−") + money(Math.abs(cur - stake)) : "—";
    root.querySelectorAll(".mx-cell").forEach(function (c) {
      var t = Number(c.dataset.t), isRev = rev.indexOf(t) >= 0, mine = S.over && S.out && (S.out.mine_positions || []).indexOf(t) >= 0, hit = S.over && S.out && Number(S.out.hit_tile) === t;
      c.className = "mx-cell" + (isRev ? " gem" : "") + (mine ? " mine" : "") + (hit ? " hit" : "");
      c.innerHTML = isRev ? GEM : mine ? BOMB : "";
      c.disabled = !act || S.busy || isRev;
    });
    root.querySelectorAll("#mx-opts button").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.m) === m); b.disabled = act || S.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = act || S.busy; });
    $(root, "#mines-stake").disabled = act || S.busy;
    var g = $(root, "#mx-go");
    if (act) { g.className = "av-go cash"; g.disabled = S.busy || k < 1; g.innerHTML = "Cash Out<small>" + money(cur) + " ETB</small>"; }
    else { g.className = "av-go"; g.disabled = S.busy; g.textContent = "Bet " + money(Number($(root, "#mines-stake").value) || 0) + " ETB"; }
  }
  function say(root, cls, text) { var e = $(root, "#mx-msg"); e.className = "kx-msg " + cls; e.textContent = text; }

  async function start(root) {
    if (S.busy || active()) return;
    var stake = Number($(root, "#mines-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; say(root, "", ""); $(root, "#mx-proof").textContent = ""; paint(root);
    try {
      var r = await apiFetch("/games/" + GK + "/round/start", { method: "POST", json: { stake: stake, mines: S.mines, client_seed: makeClientSeed() } });
      S.round = r; S.st = r.state; S.stake = stake; S.over = false; S.out = null; S.mines = Number(r.state.mines);
      $(root, "#mx-proof").textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || "").slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }

  async function pick(root, tile) {
    if (S.busy || !active() || revealed().indexOf(tile) >= 0) return;
    S.busy = true; paint(root); hap("light");
    try {
      var r = await apiFetch("/games/" + GK + "/round/" + S.round.round_id + "/action", { method: "POST", json: { action: "pick", tile: tile } });
      if (r.status === "ACTIVE") { S.st.progress = r.progress; S.st.revealed = r.revealed; hap("medium"); }
      else finish(root, r, tile);
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }

  async function cash(root) {
    if (S.busy || !active() || progress() < 1) return;
    S.busy = true; paint(root); hap("medium");
    try { finish(root, await apiFetch("/games/" + GK + "/round/" + S.round.round_id + "/action", { method: "POST", json: { action: "cashout" } })); }
    catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }

  function finish(root, r, tile) {
    var o = r.outcome || {}; S.over = true; S.out = o; S.st.revealed = o.revealed || S.st.revealed; S.st.progress = o.gems != null ? o.gems : S.st.progress;
    var pay = Number(r.payout || 0);
    if (r.won) { say(root, "win", "🎉 አሸንፈዋል +" + money(pay - S.stake) + " ብር"); hap("success"); }
    else { say(root, "lose", "💥 ፈንጂ ነክተዋል -" + money(S.stake) + " ብር"); hap("error"); }
    if (r.server_seed) $(root, "#mx-proof").textContent = "ROUND " + (r.round_code || "") + " · SERVER SEED " + String(r.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
  }
})();
