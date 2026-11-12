/* CHICKEN ROAD -- interactive client (replaces the old one-shot Chicken Road + Rabbit Road).
   The player picks a difficulty and a stake, then taps GO to hop one lane at a time. Every lane is a
   server-side roll; CASH OUT is available after any safe hop. Multiplier after n safe hops = RTP / p^n,
   so the shown multipliers are exactly what is paid (no hidden scaling). This file is presentation only:
   the server decides every hop and every payout. Loaded after app.js (uses its global helpers). */
(function () {
  "use strict";
  // Two games share this client; the numbers MUST match ROAD_CFG in realtime_engine_v3.py (the server is authoritative).
  var GAMES = {
    chicken: { max: 15, icon: "🐔", p: { easy: 0.90, medium: 0.82, hard: 0.75 }, hazards: ["🚗", "🚕", "🚚"],
               lose: "🚗 መኪና ገጨችዎ!", start: "🐔 ጀምር" },
    roast:   { max: 12, icon: "🐔", p: { easy: 0.88, medium: 0.78, hard: 0.70 }, hazards: ["🔥", "🍳", "🌋"],
               lose: "🔥 ተጠበሱ!", start: "🔥 ጀምር" },
    penaltystreak: { max: 10, icon: "⚽", p: { easy: 0.88, medium: 0.78, hard: 0.68 }, hazards: ["🧤", "🧤", "🧤"],
               lose: "🧤 ጎል ጠባቂው አዳነው!", start: "⚽ ምታ" },
    tower:   { max: 8, icon: "🧗", p: { easy: 0.82, medium: 0.70, hard: 0.58 }, hazards: ["🕳️", "💣", "⚡"],
               lose: "💥 ወጥመድ ነካችሁ!", start: "🏗 ውጣ" },
    rabbit:  { max: 10, icon: "🐇", p: { easy: 0.86, medium: 0.76, hard: 0.66 }, hazards: ["🦊", "🐺", "🦅"],
               lose: "🦊 አዳኝ ያዘችዎ!", start: "🐇 ጀምር" }
  };
  function create(KEY) {
  var CFG = GAMES[KEY], MAX = CFG.max;
  var LEVELS = {
    easy:   { label: "Easy",   am: "ቀላል",  p: CFG.p.easy,   dot: "🟢" },
    medium: { label: "Medium", am: "መካከለኛ", p: CFG.p.medium, dot: "🟡" },
    hard:   { label: "Hard",   am: "ከባድ",  p: CFG.p.hard,   dot: "🔴" }
  };
  var TILE = 78;                                   // px per lane (keep in sync with road_game.css --cr-tile)
  var S = { built: false, level: "easy", rtp: 0.95, min: 1, max: 10000, enabled: true, round: null, busy: false, settingsLoaded: false };
  var rootEl = function () { return document.getElementById(KEY + "-controls"); };
  var $ = function (id) { var r = rootEl(); return r ? r.querySelector("#" + id) : null; };
  var esc = function (v) { return (typeof escapeHtml === "function") ? escapeHtml(String(v)) : String(v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var mult = function (level, n) { return S.rtp / Math.pow(LEVELS[level].p, n); };
  var fmtX = function (m) { return (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2)) + "×"; };

  /* ---------------------------------------------------------------- DOM */
  function build() {
    var el = rootEl();
    if (!el || S.built) return !!el;
    S.built = true;
    // This game has its own scene/buttons: hide the generic cabinet scene, Play button and legacy note.
    var scene = document.getElementById(KEY + "-scene"); if (scene) scene.style.display = "none";
    var play = document.getElementById(KEY + "-play"); if (play) play.style.display = "none";
    var res = document.getElementById(KEY + "-result"); if (res) res.style.display = "none";
    var page = document.getElementById("page-" + KEY); if (page) page.classList.add("cr-page", "cr-page-" + KEY);

    el.innerHTML =
      '<div class="cr-wrap">' +
        '<div class="cr-levels" id="cr-levels">' +
          Object.keys(LEVELS).map(function (k) {
            return '<button type="button" class="cr-level" data-level="' + k + '"><b>' + LEVELS[k].dot + " " + LEVELS[k].label +
                   '</b><small id="cr-lv-' + k + '"></small></button>';
          }).join("") +
        "</div>" +
        '<div class="cr-hud"><div><small>ደረጃ</small><b id="cr-hud-step">0 / ' + MAX + '</b></div>' +
          '<div><small>Multiplier</small><b id="cr-hud-mult">—</b></div>' +
          '<div><small>ክፍያ (Cash Out)</small><b id="cr-hud-pay">—</b></div></div>' +
        '<div class="cr-viewport" id="cr-viewport"><div class="cr-road" id="cr-road"></div></div>' +
        '<div class="cr-status" id="cr-status"></div>' +
        '<div class="cr-stake" id="cr-stake-row">' +
          '<label for="' + KEY + '-stake">Bet (ብር)</label>' +
          '<input id="' + KEY + '-stake" class="game-stake" type="number" min="0.01" step="0.01" value="10" inputmode="decimal">' +
          '<div class="cr-chips">' + [10, 20, 50, 100].map(function (v) { return '<button type="button" data-chip="' + v + '">' + v + "</button>"; }).join("") + "</div>" +
        "</div>" +
        '<div class="cr-actions">' +
          '<button type="button" id="cr-start" class="primary-game-btn cr-btn-start">' + CFG.start + '</button>' +
          '<button type="button" id="cr-go" class="primary-game-btn cr-btn-go" hidden>➡ ሂድ (GO)</button>' +
          '<button type="button" id="cr-cash" class="cr-btn-cash" hidden>💰 Cash Out</button>' +
        "</div>" +
        '<div class="cr-result" id="cr-result" aria-live="polite"></div>' +
        '<small class="cr-note">እያንዳንዱ ሌን አንድ ጊዜ በServer ይወሰናል። Multiplier = RTP ÷ (የማለፍ ዕድል)<sup>ደረጃ</sup> -- የሚታየው ልክ የሚከፈለው ነው። በማንኛውም ደህንነቱ የተጠበቀ ሌን Cash Out ማድረግ ይችላሉ።</small>';

    el.querySelectorAll(".cr-level").forEach(function (b) {
      b.addEventListener("click", function () {
        if (S.round) return;                                      // can't change difficulty mid-round
        S.level = b.dataset.level; if (typeof haptic === "function") haptic("light");
        renderIdle();
      });
    });
    el.querySelectorAll("[data-chip]").forEach(function (b) {
      b.addEventListener("click", function () { if (!S.round) { $(KEY + "-stake").value = b.dataset.chip; if (typeof haptic === "function") haptic("light"); } });
    });
    $("cr-start").addEventListener("click", start);
    $("cr-go").addEventListener("click", go);
    $("cr-cash").addEventListener("click", cash);
    return true;
  }

  function buildRoad(multipliers, hitTile) {
    var road = $("cr-road"); if (!road) return;
    road.style.width = (TILE * (MAX + 1)) + "px";
    var html = '<div class="cr-tile cr-start-tile"><span class="cr-flag">🏁</span></div>';
    for (var i = 1; i <= MAX; i++) {
      html += '<div class="cr-tile" data-n="' + i + '"><span class="cr-mult">' + fmtX(multipliers[i - 1]) + "</span>" +
              '<span class="cr-car" style="animation-delay:-' + ((i * 0.37) % 2.4).toFixed(2) + 's">' + CFG.hazards[i % 3] + "</span></div>";
    }
    html += '<div class="cr-chicken" id="cr-chicken">' + CFG.icon + '</div>';
    road.innerHTML = html;
    placeChicken(0, false);
  }

  function placeChicken(n, smooth) {
    var ch = $("cr-chicken"), vp = $("cr-viewport"); if (!ch) return;
    ch.style.transform = "translateX(" + (n * TILE + TILE / 2 - 18) + "px)";
    if (vp) vp.scrollTo({ left: Math.max(0, n * TILE - 110), behavior: smooth ? "smooth" : "auto" });
  }

  function paintRoad(progress, hitTile) {
    rootEl().querySelectorAll("#cr-road .cr-tile[data-n]").forEach(function (t) {
      var n = Number(t.dataset.n);
      t.classList.toggle("done", n <= progress);
      t.classList.toggle("current", n === progress);
      t.classList.toggle("next", !hitTile && n === progress + 1);
      t.classList.toggle("hit", hitTile === n);
    });
  }

  /* ---------------------------------------------------------------- views */
  function multsFor(level) { var a = []; for (var i = 1; i <= MAX; i++) a.push(mult(level, i)); return a; }

  function levelChips() {
    Object.keys(LEVELS).forEach(function (k) {
      var b = rootEl().querySelector('.cr-level[data-level="' + k + '"]'); if (!b) return;
      b.classList.toggle("active", k === (S.round ? S.round.level : S.level));
      b.disabled = !!S.round;
      var sm = $("cr-lv-" + k);
      if (sm) sm.textContent = Math.round(LEVELS[k].p * 100) + "% / ሌን · max " + fmtX(mult(k, MAX));
    });
  }

  function setButtons() {
    var r = S.round, live = !!r;
    $("cr-start").hidden = live; $("cr-stake-row").hidden = live;
    $("cr-go").hidden = !live; $("cr-cash").hidden = !live;
    $("cr-go").disabled = S.busy;
    $("cr-cash").disabled = S.busy || !r || r.progress < 1;
    $("cr-start").disabled = S.busy || !S.enabled;
    if (r) {
      var pay = r.progress >= 1 ? r.stake * r.mult[r.progress - 1] : 0;
      $("cr-cash").textContent = r.progress >= 1 ? "💰 Cash Out  " + money(pay) + " ብር" : "💰 Cash Out (አንድ ሌን ይለፉ)";
    }
  }

  function renderIdle() {
    levelChips();
    buildRoad(multsFor(S.level));
    paintRoad(0, 0);
    $("cr-hud-step").textContent = "0 / " + MAX;
    $("cr-hud-mult").textContent = "—"; $("cr-hud-pay").textContent = "—";
    $("cr-status").textContent = S.enabled ? "ደረጃ ይምረጡ፣ Bet ያስገቡ እና ይጀምሩ። 1ኛ ሌን: " + fmtX(mult(S.level, 1)) : "⛔ ጨዋታው ለጊዜው ጠፍቷል";
    setButtons();
  }

  function renderRound() {
    var r = S.round; if (!r) return renderIdle();
    levelChips();
    if (!rootEl().querySelector("#cr-road .cr-tile[data-n]") || r.rebuild) { buildRoad(r.mult); r.rebuild = false; }
    paintRoad(r.progress, 0);
    placeChicken(r.progress, true);
    var m = r.progress ? r.mult[r.progress - 1] : 0;
    $("cr-hud-step").textContent = r.progress + " / " + MAX;
    $("cr-hud-mult").textContent = r.progress ? fmtX(m) : "—";
    $("cr-hud-pay").textContent = r.progress ? money(r.stake * m) + " ብር" : "—";
    $("cr-status").innerHTML = "ቀጣይ ሌን: <b>" + fmtX(r.mult[Math.min(r.progress, MAX - 1)]) + "</b> · ዕድል " + Math.round(LEVELS[r.level].p * 100) + "% · Bet " + money(r.stake) + " ብር";
    setButtons();
  }

  /* ---------------------------------------------------------------- fairness proof */
  function safeStepsJS(seed, clientSeed, level) {
    return sha256Hex(seed + ":" + clientSeed + ":" + level).then(function (h) {
      var u = (parseInt(h.slice(0, 13), 16) + 1) / Math.pow(16, 13);
      return Math.max(0, Math.min(MAX, Math.floor(Math.log(u) / Math.log(LEVELS[level].p))));
    });
  }
  function proofHtml(o, commit) {
    return '<div class="cr-proof" id="cr-proof"><small>🔒 Provably fair</small>' +
      '<div>Commit: <code>' + esc((commit || "").slice(0, 16)) + '…</code></div>' +
      '<div>Server seed: <code>' + esc((o.server_seed || "").slice(0, 16)) + '…</code> · ደህንነታቸው የተጠበቁ ሌኖች: <b>' + esc(o.safe_steps) + '</b></div>' +
      '<div id="cr-proof-check">⏳ በማረጋገጥ ላይ…</div></div>';
  }
  function verify(o, commit) {
    if (!(typeof sha256Hex === "function") || !o || !o.server_seed) return;
    Promise.all([sha256Hex(o.server_seed), safeStepsJS(o.server_seed, o.client_seed || "", o.difficulty)]).then(function (v) {
      var ok = (!commit || v[0] === commit) && v[1] === o.safe_steps;
      var el = $("cr-proof-check"); if (el) el.textContent = ok ? "✅ ተረጋግጧል: SHA-256(seed) == commit እና ውጤቱ ከ seed ጋር ይመሳሰላል" : "❌ አልተመሳሰለም -- Support ያነጋግሩ";
    }).catch(function () { var el = $("cr-proof-check"); if (el) el.textContent = ""; });
  }

  /* ---------------------------------------------------------------- end of round */
  function finish(res, hitTile) {
    var r = S.round, o = res.outcome || {}, won = res.status === "WON";
    var stake = r ? r.stake : Number(res.stake || 0), commit = r && r.commit;
    if (r) { if (hitTile) { r.progress = o.steps_cleared || r.progress; } }
    var prog = r ? r.progress : (o.steps_cleared || 0);
    paintRoad(prog, hitTile || 0);
    if (hitTile) {
      placeChicken(hitTile, true);
      var ch = $("cr-chicken"); if (ch) { setTimeout(function () { ch.textContent = "💥"; ch.classList.add("cr-crash"); }, 420); }
    }
    var payout = Number(res.payout || 0), net = Math.round((payout - stake) * 100) / 100;
    $("cr-result").innerHTML = (won
      ? '<div class="cr-banner win">🎉 <b>አሸነፉ!</b> +' + money(net) + ' ብር <small>(ክፍያ ' + money(payout) + ' ብር · ' + fmtX(Number(o.multiplier || 0)) + (o.reason === "max_steps" ? " · MAX 🏆" : "") + ')</small></div>'
      : '<div class="cr-banner lose">💥 <b>' + CFG.lose + '</b> -' + money(stake) + ' ብር <small>(ሌን ' + esc(o.hit_step) + ')</small></div>') + proofHtml(o, commit);
    verify(o, commit);
    if (won) { if (typeof gameSound === "function") gameSound("win"); if (typeof haptic === "function") haptic("success"); if (typeof celebrateWin === "function") celebrateWin(); if (typeof celebrateWin3D === "function") celebrateWin3D(); }
    else { if (typeof gameSound === "function") gameSound("lose"); if (typeof haptic === "function") haptic("error"); }
    S.round = null; S.busy = false;
    $("cr-hud-mult").textContent = won ? fmtX(Number(o.multiplier || 0)) : "💥";
    $("cr-hud-pay").textContent = won ? money(payout) + " ብር" : "0.00 ብር";
    $("cr-status").textContent = won ? "✅ ገንዘቡ ወደ ሂሳብዎ ገብቷል" : "እንደገና ይሞክሩ!";
    // keep the finished road on screen; offer a fresh round
    $("cr-start").textContent = "🔁 እንደገና ተጫወት";
    setButtons(); levelChips();
    if (typeof refreshBalance === "function") refreshBalance();
  }

  /* ---------------------------------------------------------------- actions */
  function err(e) {
    var box = $("cr-result"); if (typeof renderActionError === "function") renderActionError(box, e && e.message || String(e)); else box.textContent = "❌ " + (e && e.message);
    if (typeof haptic === "function") haptic("error");
  }

  async function start() {
    if (S.busy || S.round) return;
    var stake = Number($(KEY + "-stake").value);
    if (!(stake > 0)) return err(new Error("የBet መጠን ትክክል ያስገቡ"));
    if (stake < S.min || stake > S.max) return err(new Error("Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"));
    S.busy = true; setButtons(); $("cr-result").innerHTML = "";
    try {
      var r = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, difficulty: S.level, client_seed: makeClientSeed() } });
      var st = r.state || {};
      S.round = { id: r.round_id, stake: stake, level: S.level, progress: 0, mult: st.multipliers || multsFor(S.level), commit: r.seed_commit || "", rebuild: true };
      $("cr-proof") && $("cr-proof").remove();
      if (typeof gameSound === "function") gameSound("round");
      if (typeof haptic === "function") haptic("light");
      if (typeof refreshBalance === "function") refreshBalance();
    } catch (e) { err(e); }
    S.busy = false; renderRound();
  }

  async function go() {
    var r = S.round; if (!r || S.busy) return;
    S.busy = true; setButtons();
    try {
      var a = await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "step" } });
      if (a.status === "ACTIVE") {
        r.progress = a.progress; S.busy = false;
        if (typeof gameSound === "function") gameSound("tap"); if (typeof haptic === "function") haptic("light");
        renderRound();
      } else if (a.status === "LOST") {
        finish(a, a.outcome && a.outcome.hit_step);
      } else if (a.status === "WON") {                                  // reached the last lane: auto cash-out
        r.progress = a.progress || MAX; placeChicken(r.progress, true); finish(a, 0);
      } else { S.busy = false; renderRound(); }
    } catch (e) { S.busy = false; err(e); await resync(); }
  }

  async function cash() {
    var r = S.round; if (!r || S.busy || r.progress < 1) return;
    S.busy = true; setButtons();
    try {
      var a = await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "cashout" } });
      finish(a, 0);
    } catch (e) { S.busy = false; err(e); await resync(); }
  }

  // After a failed request our local view may be stale: ask the server what the live round looks like.
  async function resync() {
    try {
      var d = await apiFetch("/games/" + KEY + "/active");
      if (d && d.round_id && d.status === "ACTIVE") { adopt(d); renderRound(); }
      else { S.round = null; S.busy = false; renderIdle(); }
    } catch (_) { S.busy = false; setButtons(); }
  }

  function adopt(d) {
    var st = d.state || {}, inp = st.input || {};
    S.level = inp.difficulty || S.level;
    S.round = { id: d.round_id, stake: Number(d.stake), level: S.level, progress: Number(st.progress || 0), mult: st.multipliers || multsFor(S.level), commit: d.seed_commit || "", rebuild: true };
  }

  async function loadSettings() {
    if (S.settingsLoaded) return;
    try {
      var s = await apiFetch("/games/" + KEY + "/settings");
      S.rtp = Number(s.rtp) || S.rtp; S.min = Number(s.min_stake) || S.min; S.max = Number(s.max_stake) || S.max; S.enabled = s.enabled !== false;
      var inp = $(KEY + "-stake"); if (inp) { inp.min = S.min; inp.max = S.max; }
      S.settingsLoaded = true;
    } catch (_) { /* defaults are fine; the server enforces the real limits */ }
  }

  /* ---------------------------------------------------------------- entry point (called every time the page opens) */
  return async function () {
    if (!build()) return;
    await loadSettings();
    if (S.round) { renderRound(); return; }
    try {
      var d = await apiFetch("/games/" + KEY + "/active");
      if (d && d.round_id && d.status === "ACTIVE") { adopt(d); renderRound(); return; }
    } catch (_) { /* fall through to idle */ }
    if (!$("cr-result").innerHTML) renderIdle(); else { levelChips(); setButtons(); }
  };
  }
  window.setupChickenRoad = create("chicken");
  window.setupRabbitRoad = create("rabbit");
  window.setupRoastRoad = create("roast");
  window.setupPenaltyStreak = create("penaltystreak");
  window.setupTower = create("tower");
})();
