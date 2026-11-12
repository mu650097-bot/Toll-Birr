/* BOOM LADDER (PDF "Boom Game"): 8 levels, pick one of 3 boxes per level, avoid the bomb, cash out after any safe level.
   Runs on the existing single-player TOWER engine (key "tower"): every level is a server-side roll and the multiplier after n safe
   levels = RTP / p^n, so every number shown is exactly what is paid. SELF-REGISTERING (wraps window.setupAddedGameControls for the
   page key "tower"); the server and the separate multiplayer Boom pool game are NOT touched. Load after app.js. Needs kdm_boom.css. */
(function () {
  "use strict";
  var KEY = "tower", MAX = 8, P = { easy: 0.82, medium: 0.70, hard: 0.58 };   // MUST match TOWER_* in realtime_engine_v3.py
  var LV = [["easy", "Easy"], ["medium", "Medium"], ["hard", "Hard"]];
  var S = { level: "medium", rtp: 0.92, min: 1, max: 10000, loaded: false, busy: false, round: null, over: null, picked: -1, state: "", fuseLeft: 10, fuseFor: "", fuseT: 0 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var fx = function (m) { return "x" + (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2)); };
  var mult = function (lv, n) { return S.rtp / Math.pow(P[lv], n); };
  var BOMB = '<svg viewBox="0 0 64 64" width="100%" height="100%"><circle cx="30" cy="38" r="20" fill="#1f2937" stroke="#6b7280" stroke-width="3"/><ellipse cx="22" cy="30" rx="7" ry="4" fill="#9ca3af" opacity=".6"/><rect x="24" y="12" width="12" height="9" rx="2" fill="#374151"/><path d="M38 14c5-6 9-7 12-8" stroke="#d6b27a" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M52 3l3 6 6 1-5 4 1 6-5-3-5 3 1-6-4-4 6-1z" fill="#f97316"/></svg>';
  var BOX = '<svg viewBox="0 0 48 48" width="46" height="46"><path d="M6 16l18-8 18 8v22l-18 8-18-8z" fill="#b45309" stroke="#78350f" stroke-width="2" stroke-linejoin="round"/><path d="M6 16l18 8 18-8M24 24v22" stroke="#78350f" stroke-width="2" fill="none"/><rect x="20" y="26" width="8" height="8" rx="2" fill="#fde047"/></svg>';
  var SAFE = '<svg viewBox="0 0 48 48" width="46" height="46"><path d="M6 16l18-8 18 8v22l-18 8-18-8z" fill="#16a34a" stroke="#14532d" stroke-width="2" stroke-linejoin="round"/><path d="M14 27l7 7 14-15" stroke="#fff" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  var prev = window.setupAddedGameControls;
  window.setupAddedGameControls = function (key) { if (key === KEY) return window.setupBoomLadder(); return prev ? prev.apply(this, arguments) : undefined; };

  window.setupBoomLadder = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("cr-page"); pg.classList.add("kx-page", "bm-page"); }
    if (!root.dataset.bm) {
      root.dataset.bm = "1";
      var seg = LV.map(function (l) { return '<button type="button" data-l="' + l[0] + '">' + l[1] + "</button>"; }).join("");
      root.innerHTML = '<div class="bm-wrap"><div class="bm-top"><span class="bm-lvl" id="bm-lvl">Level 1 of ' + MAX + '</span><span class="bm-fuse" id="bm-fuse" hidden>Fuse 00:10</span></div>' +
        '<div class="bm-stage" id="bm-stage"><div class="bm-bomb" id="bm-bomb">' + BOMB + '</div><b class="bm-x" id="bm-x">x1.00</b></div>' +
        '<p class="bm-hint" id="bm-hint">Pick one box. Avoid the bomb to move to the next level.</p>' +
        '<div class="bm-boxes" id="bm-boxes"><button type="button" class="bm-box" data-i="0"></button><button type="button" class="bm-box" data-i="1"></button><button type="button" class="bm-box" data-i="2"></button></div>' +
        '<div class="bm-ladder" id="bm-ladder"></div>' +
        '<div class="bm-card"><div class="bm-cols"><div class="bm-col"><label for="tower-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="tower-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="bm-col"><label>Take now</label><b class="bm-take" id="bm-take">0.00</b></div></div>' +
        '<div class="bm-seg" id="bm-seg">' + seg + '</div><div class="bm-chance" id="bm-chance"></div>' +
        '<div class="bm-acts"><button type="button" id="bm-start" class="bm-btn bm-go">Bet</button><button type="button" id="bm-next" class="bm-btn bm-next" hidden>Next level</button><button type="button" id="bm-cash" class="bm-btn bm-cash" hidden>Cash Out</button></div>' +
        '<div class="kx-msg" id="bm-msg" aria-live="polite"></div><div class="kx-proof" id="bm-proof"></div></div>' +
        '<small class="kx-note">በእያንዳንዱ ደረጃ አንድ ሳጥን ይምረጡ፤ ሰርቨሩ ደህንነቱን ይወስናል። የሳጥን ምርጫዎ የደህንነት ዕድሉን አይቀይርም (ዕድሉ በታች ተጽፏል)። ደህና ሳጥን ሲያገኙ ማባዣው ይጨምራል፤ ከማንኛውም ደህና ደረጃ በኋላ Cash Out ይችላሉ። ማባዣ = RTP ÷ (የደህንነት ዕድል)<sup>ደረጃ</sup>።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || S.round) return; var i = $(root, "#tower-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#tower-stake").addEventListener("input", function () { paint(root); });
      root.querySelectorAll("#bm-seg button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || S.round) return; S.level = b.dataset.l; S.over = null; hap("light"); paint(root); }); });
      root.querySelectorAll(".bm-box").forEach(function (b) { b.addEventListener("click", function () { pick(root, Number(b.dataset.i)); }); });
      $(root, "#bm-start").addEventListener("click", function () { start(root); });
      $(root, "#bm-next").addEventListener("click", function () { pick(root, Math.floor(Math.random() * 3)); });
      $(root, "#bm-cash").addEventListener("click", function () { cash(root); });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.rtp = Number(s.rtp) || (1 - Number(s.house_edge || 0.05)); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.loaded = true; } catch (_) { S.loaded = true; } }
    if (!S.round) { try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); } catch (_) {} }
    paint(root);
  };
  function lvMult(lv) { var a = []; for (var i = 1; i <= MAX; i++) a.push(mult(lv, i)); return a; }
  function adopt(d) {
    var st = d.state || {}, inp = st.input || {}; S.level = inp.difficulty || S.level; S.over = null; S.picked = -1; S.state = "";
    S.round = { id: d.round_id, stake: Number(d.stake), level: S.level, progress: Number(st.progress || 0), mult: st.multipliers || lvMult(S.level) };
  }

  function paint(root) {
    var r = S.round, o = S.over, lv = r ? r.level : (o ? o.level : S.level), ms = r ? r.mult : (o ? o.mult : lvMult(lv)), prog = r ? r.progress : (o ? o.progress : 0);
    var stake = r ? r.stake : (o ? o.stake : (Number($(root, "#tower-stake").value) || 0)), live = !!r;
    root.querySelectorAll("#bm-seg button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === lv); b.disabled = live || S.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = live || S.busy; }); $(root, "#tower-stake").disabled = live || S.busy;
    $(root, "#bm-chance").textContent = "Safe chance each level: " + Math.round(P[lv] * 100) + "%";
    $(root, "#bm-lvl").textContent = "Level " + Math.min(MAX, prog + (live ? 1 : (o && !o.won ? 1 : 0)) || 1) + " of " + MAX;
    var cur = prog ? ms[prog - 1] : 1, nxt = prog < MAX ? ms[prog] : ms[MAX - 1];
    $(root, "#bm-x").textContent = fx(live ? nxt : cur); $(root, "#bm-bomb").classList.toggle("boom", S.state === "lost");
    $(root, "#bm-take").textContent = money(live ? (prog ? stake * cur : 0) : (o && o.won ? o.payout : 0));
    $(root, "#bm-hint").textContent = live ? "Pick one box. Avoid the bomb to move to the next level." : (o ? (o.won ? "Cashed out!" : "Boom! The bomb was in your box.") : "Choose a level of risk and place your bet.");
    var boxes = root.querySelectorAll(".bm-box");
    boxes.forEach(function (b, i) {
      var cls = "bm-box", html = BOX, label = "Pick";
      if (S.state === "safe" && i === S.picked) { cls += " safe"; html = SAFE; label = "SAFE"; }
      else if (S.state === "lost" && i === S.picked) { cls += " bomb"; html = '<span class="bm-bsvg">' + BOMB + "</span>"; label = "BOOM"; }
      else if (!live) { cls += " idle"; }
      b.className = cls; b.innerHTML = html + "<span>" + label + "</span>"; b.disabled = !live || S.busy;
    });
    $(root, "#bm-ladder").innerHTML = ms.map(function (m, i) { var n = i + 1; return '<span class="' + (n <= prog ? "done" : n === prog + 1 && live ? "cur" : "") + '">' + fx(m).replace(/\.00$/, "") + "</span>"; }).join("");
    fuse(root);
    $(root, "#bm-start").hidden = live; $(root, "#bm-next").hidden = !live; $(root, "#bm-cash").hidden = !live;
    $(root, "#bm-start").disabled = S.busy; $(root, "#bm-start").textContent = "Bet " + money(Number($(root, "#tower-stake").value) || 0) + " ETB";
    $(root, "#bm-next").disabled = S.busy; $(root, "#bm-cash").disabled = S.busy || !r || r.progress < 1;
    $(root, "#bm-cash").innerHTML = r && r.progress >= 1 ? "Cash Out<small>" + money(stake * cur) + " ETB</small>" : "Cash Out";
  }
  // FUSE: 10 s per level (UI only; the server roll never depends on the box or on the timer). When the fuse burns out the
  // player is protected: with >= 1 safe level it CASHES OUT; with none yet it opens a random box (same as "Next level").
  var FUSE_SEC = 10;
  function fuseTxt(n) { return "Fuse 00:" + (n < 10 ? "0" : "") + n; }
  function fuseStop() { if (S.fuseT) { clearInterval(S.fuseT); S.fuseT = 0; } }
  function fuse(root) {
    var el = $(root, "#bm-fuse"), r = S.round; if (!el) return;
    if (!r) { fuseStop(); S.fuseFor = ""; el.hidden = true; return; }
    el.hidden = false;
    var key = r.id + ":" + r.progress;
    if (S.fuseFor !== key) { S.fuseFor = key; S.fuseLeft = FUSE_SEC; }
    el.textContent = fuseTxt(S.fuseLeft); el.classList.toggle("hot", S.fuseLeft <= 3);
    if (S.busy) { fuseStop(); return; }
    if (S.fuseT) return;
    S.fuseT = setInterval(function () {
      if (!document.body.contains(root) || !S.round) { fuseStop(); return; }
      if (S.busy) return;
      S.fuseLeft = Math.max(0, S.fuseLeft - 1); el.textContent = fuseTxt(S.fuseLeft); el.classList.toggle("hot", S.fuseLeft <= 3);
      if (S.fuseLeft > 0) return;
      fuseStop();
      if (S.round.progress >= 1) { say(root, "", "⏱ Fuse አለቀ — ራስ-ሰር Cash Out"); cash(root); } else pick(root, Math.floor(Math.random() * 3));
    }, 1000);
  }
  function say(root, cls, t) { var e = $(root, "#bm-msg"); e.className = "kx-msg " + cls; e.textContent = t; }

  async function start(root) {
    if (S.busy || S.round) return; var stake = Number($(root, "#tower-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.over = null; S.picked = -1; S.state = ""; say(root, "", ""); $(root, "#bm-proof").textContent = ""; paint(root);
    try {
      var r = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, difficulty: S.level, client_seed: makeClientSeed() } });
      var st = r.state || {}; S.round = { id: r.round_id, stake: stake, level: S.level, progress: 0, mult: st.multipliers || lvMult(S.level) };
      $(root, "#bm-proof").textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || "").slice(0, 16) + "…";
      hap("light"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }
  function end(root, a) {
    var r = S.round, o = a.outcome || {}, won = a.status === "WON", pay = Number(a.payout || 0);
    S.over = { level: r.level, mult: r.mult, progress: Number(o.steps_cleared != null ? o.steps_cleared : r.progress), won: won, payout: pay, stake: r.stake }; S.round = null;
    if (won) { say(root, "win", "🎉 +" + money(pay - r.stake) + " ብር (" + fx(Number(o.multiplier || 0)) + ")"); hap("success"); }
    else { say(root, "lose", "💥 ቦምብ! -" + money(r.stake) + " ብር"); hap("error"); }
    if (o.server_seed) $(root, "#bm-proof").textContent = "ROUND " + (a.round_code || "") + " · SERVER SEED " + String(o.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
  }
  async function resync() { try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); else S.round = null; } catch (_) {} }
  async function pick(root, i) {
    var r = S.round; if (!r || S.busy) return; S.busy = true; S.picked = i; S.state = ""; paint(root); hap("light");
    try {
      var a = await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "step" } });
      if (a.status === "ACTIVE") { S.state = "safe"; r.progress = a.progress; hap("medium"); paint(root); await sleep(750); S.state = ""; S.picked = -1; }
      else if (a.status === "LOST") { S.state = "lost"; end(root, a); }
      else if (a.status === "WON") { S.state = "safe"; r.progress = a.progress || MAX; end(root, a); }
    } catch (e) { say(root, "bad", "❌ " + e.message); S.state = ""; S.picked = -1; await resync(); }
    S.busy = false; paint(root);
  }
  async function cash(root) {
    var r = S.round; if (!r || S.busy || r.progress < 1) return; S.busy = true; S.state = ""; S.picked = -1; paint(root); hap("medium");
    try { end(root, await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "cashout" } })); }
    catch (e) { say(root, "bad", "❌ " + e.message); await resync(); }
    S.busy = false; paint(root);
  }
})();
