/* CHICKEN ROAD (new look): the chicken crosses lane after lane, cash out after any safe lane. Same server engine as before:
   every step is a server-side roll and multiplier after n safe lanes = RTP / p^n, so the numbers shown are exactly what is paid.
   Loaded after road_game.js; replaces window.setupChickenRoad. Presentation only. */
(function () {
  "use strict";
  var KEY = "chicken", MAX = 15, P = { easy: 0.90, medium: 0.82, hard: 0.75, hardcore: 0.735 };   // MUST match CHICKEN_* in realtime_engine_v3.py
  var LV = [["easy", "Easy"], ["medium", "Medium"], ["hard", "Hard"], ["hardcore", "Hardcore"]];
  var S = { level: "medium", rtp: 0.95, min: 1, max: 10000, loaded: false, busy: false, round: null, over: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var fmtX = function (m) { return "x" + (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2)); };
  var mult = function (lv, n) { return S.rtp / Math.pow(P[lv], n); };
  var HEN = '<svg viewBox="0 0 48 52" width="46" height="50" aria-hidden="true"><path d="M20 8c0-4 3-6 5-4 2-3 6-1 5 3" fill="#ef4444"/><ellipse cx="24" cy="28" rx="15" ry="13" fill="#fff" stroke="#e5e7eb"/><circle cx="24" cy="14" r="8" fill="#fff" stroke="#e5e7eb"/><path d="M30 14l6 2-6 3z" fill="#f59e0b"/><circle cx="26" cy="12" r="1.5" fill="#111"/><path d="M12 28c-4 0-5 5-2 7 4 2 9-3 7-7z" fill="#f3f4f6" stroke="#e5e7eb"/><path d="M20 40v8M28 40v8M16 48h8M24 48h8" stroke="#f59e0b" stroke-width="2.4" stroke-linecap="round"/></svg>';
  var OK = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#4ade80" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var LOCK = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2" fill="#9fb0da"/><path d="M8 11V8a4 4 0 018 0v3" fill="none" stroke="#9fb0da" stroke-width="2"/></svg>';
  var CAR = '<svg viewBox="0 0 40 28" width="36" height="26" aria-hidden="true"><rect x="3" y="10" width="34" height="13" rx="4" fill="#ef4444"/><path d="M10 10l4-7h12l4 7z" fill="#fca5a5"/><circle cx="12" cy="24" r="4" fill="#111"/><circle cx="29" cy="24" r="4" fill="#111"/></svg>';

  window.setupChickenRoad = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("cr-page", "cr-page-chicken"); pg.classList.add("kx-page"); }
    if (!root.dataset.ck) {
      root.dataset.ck = "1";
      var seg = LV.map(function (l) { return '<button type="button" data-l="' + l[0] + '">' + l[1] + "</button>"; }).join("");
      root.innerHTML = '<div class="ck-wrap"><div class="ck-board"><div class="ck-head"><b>START</b><b id="ck-fin">FINISH</b></div><div class="ck-lanes" id="ck-lanes"></div></div>' +
        '<div class="rb-stats"><div class="kx-tile"><small>Current multiplier</small><b id="ck-mult" class="b">x1.00</b></div><div class="kx-tile"><small>Cash out now</small><b id="ck-win" class="g">—</b></div></div>' +
        '<div class="av-card"><div class="pk-seg" id="ck-seg">' + seg + '</div><div class="av-bet-col"><label for="chicken-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="chicken-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="rb-acts"><button type="button" id="ck-start" class="av-go">Go</button><button type="button" id="ck-go" class="av-go" hidden>Go</button><button type="button" id="ck-cash" class="av-go rb-cash" hidden>Cash Out</button></div>' +
        '<div class="kx-msg" id="ck-msg" aria-live="polite"></div><div class="kx-proof" id="ck-proof"></div></div>' +
        '<small class="kx-note">በእያንዳንዱ እርምጃ ሰርቨሩ ይወስናል። ደህና እርምጃ ሲያደርጉ ማባዣው ይጨምራል፤ ከማንኛውም ደህና እርምጃ በኋላ Cash Out ይችላሉ። ማባዣ = RTP ÷ (የደህንነት ዕድል)<sup>እርምጃ</sup>፤ የሚታየው ሁሉ እውነተኛ ክፍያ ነው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || S.round) return; var i = $(root, "#chicken-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#chicken-stake").addEventListener("input", function () { paint(root); });
      root.querySelectorAll("#ck-seg button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || S.round) return; S.level = b.dataset.l; S.over = null; hap("light"); paint(root); }); });
      $(root, "#ck-start").addEventListener("click", function () { start(root); });
      $(root, "#ck-go").addEventListener("click", function () { step(root); });
      $(root, "#ck-cash").addEventListener("click", function () { cash(root); });
    }
    // Skins (e.g. "Chicken Road 2") share this page and route /games/chicken/* to their own game key: forget the previous skin's round and re-read
    // the limits / RTP every time the page opens, so another skin never shows stale limits, multipliers or a round that belongs to a different game key.
    var hd = pg && pg.querySelector("h2"), skin = hd ? hd.textContent : "";
    if (S.skin !== undefined && S.skin !== skin) { S.round = null; S.over = null; }
    S.skin = skin;
    try { var s = await apiFetch("/games/" + KEY + "/settings"); S.rtp = Number(s.rtp) || (1 - Number(s.house_edge || 0.05)); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; } catch (_) {}
    S.loaded = true;
    if (!S.round) { try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); } catch (_) {} }
    paint(root);
  };
  function adopt(d) {
    var st = d.state || {}, inp = st.input || {}; S.level = inp.difficulty || S.level; S.over = null;
    S.round = { id: d.round_id, stake: Number(d.stake), level: S.level, progress: Number(st.progress || 0), mult: st.multipliers || lvMult(S.level) };
  }
  function lvMult(lv) { var a = []; for (var i = 1; i <= MAX; i++) a.push(mult(lv, i)); return a; }

  function paint(root) {
    var r = S.round, o = S.over, lv = r ? r.level : (o ? o.level : S.level), ms = r ? r.mult : (o ? o.mult : lvMult(lv)), prog = r ? r.progress : (o ? o.progress : 0);
    var stake = r ? r.stake : (o ? o.stake : (Number($(root, "#chicken-stake").value) || 0)), hit = o && o.hit ? o.hit : 0;
    root.querySelectorAll("#ck-seg button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === lv); b.disabled = !!r || S.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = !!r || S.busy; }); $(root, "#chicken-stake").disabled = !!r || S.busy;
    $(root, "#ck-fin").textContent = "FINISH " + fmtX(ms[MAX - 1]);
    var m = prog ? ms[prog - 1] : 1; $(root, "#ck-mult").textContent = fmtX(m);
    var win = r ? (prog ? stake * m : 0) : (o && o.won ? o.payout : 0); $(root, "#ck-win").textContent = win > 0 ? money(win) : "—";
    // 6 lanes (columns); lane 0 = START
    var first = Math.max(0, Math.min(MAX - 5, prog - 2)), html = "";
    for (var n = first; n < first + 6; n++) {
      var cls = "ck-lane", ic = "", tag = n === 0 ? "START" : fmtX(ms[n - 1]);
      if (hit && n === hit) { cls += " hit"; ic = CAR; }
      else if (n === prog && !hit) { cls += " cur"; ic = HEN; }
      else if (n < prog) { cls += " done"; ic = OK; }
      else if (r && n === prog + 1) { cls += " next"; ic = "<em>?</em>"; }
      else ic = LOCK;
      html += '<div class="' + cls + '"><span class="tag">' + tag + '</span><span class="ic">' + ic + "</span></div>";
    }
    $(root, "#ck-lanes").innerHTML = html;
    var live = !!r; $(root, "#ck-start").hidden = live; $(root, "#ck-go").hidden = !live; $(root, "#ck-cash").hidden = !live;
    $(root, "#ck-start").disabled = S.busy; $(root, "#ck-go").disabled = S.busy; $(root, "#ck-cash").disabled = S.busy || !r || r.progress < 1;
    $(root, "#ck-cash").textContent = "Cash Out";
  }
  function say(root, cls, t) { var e = $(root, "#ck-msg"); e.className = "kx-msg " + cls; e.textContent = t; }

  async function start(root) {
    if (S.busy || S.round) return; var stake = Number($(root, "#chicken-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.over = null; say(root, "", ""); $(root, "#ck-proof").textContent = ""; paint(root);
    try {
      var r = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, difficulty: S.level, client_seed: makeClientSeed() } });
      var st = r.state || {}; S.round = { id: r.round_id, stake: stake, level: S.level, progress: 0, mult: st.multipliers || lvMult(S.level) };
      $(root, "#ck-proof").textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || "").slice(0, 16) + "…";
      hap("light"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }
  function end(root, a, hit) {
    var r = S.round, o = a.outcome || {}, won = a.status === "WON", pay = Number(a.payout || 0);
    S.over = { level: r.level, mult: r.mult, progress: Number(o.steps_cleared != null ? o.steps_cleared : r.progress), hit: hit || 0, won: won, payout: pay, stake: r.stake };
    S.round = null;
    if (won) { say(root, "win", "🎉 +" + money(pay - r.stake) + " ብር (" + fmtX(Number(o.multiplier || 0)) + ")"); hap("success"); }
    else { say(root, "lose", "💥 መኪና ገጭቷል -" + money(r.stake) + " ብር"); hap("error"); }
    if (o.server_seed) $(root, "#ck-proof").textContent = "ROUND " + (a.round_code || "") + " · SERVER SEED " + String(o.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
  }
  async function resync(root) {
    try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); else S.round = null; } catch (_) {}
  }
  async function step(root) {
    var r = S.round; if (!r || S.busy) return; S.busy = true; paint(root);
    try {
      var a = await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "step" } });
      if (a.status === "ACTIVE") { r.progress = a.progress; hap("light"); }
      else if (a.status === "LOST") end(root, a, a.outcome && a.outcome.hit_step);
      else if (a.status === "WON") { r.progress = a.progress || MAX; end(root, a, 0); }
    } catch (e) { say(root, "bad", "❌ " + e.message); await resync(root); }
    S.busy = false; paint(root);
  }
  async function cash(root) {
    var r = S.round; if (!r || S.busy || r.progress < 1) return; S.busy = true; paint(root); hap("medium");
    try { end(root, await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "cashout" } }), 0); }
    catch (e) { say(root, "bad", "❌ " + e.message); await resync(root); }
    S.busy = false; paint(root);
  }
})();
