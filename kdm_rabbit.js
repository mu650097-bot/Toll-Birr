/* RABBIT ROAD (new look): hop lane by lane up the meadow, cash out after any safe hop. Same server engine as before: every hop is a
   server-side roll and multiplier after n safe hops = RTP / p^n, so the shown numbers are exactly what is paid.
   Loaded after road_game.js; it replaces window.setupRabbitRoad. Presentation only. */
(function () {
  "use strict";
  var KEY = "rabbit", MAX = 10, P = { easy: 0.86, medium: 0.76, hard: 0.66 };   // MUST match RABBIT_* in realtime_engine_v3.py
  var LV = [["easy", "Easy"], ["medium", "Mid"], ["hard", "Hard"]];
  var S = { built: false, level: "easy", rtp: 0.92, min: 1, max: 10000, loaded: false, busy: false, round: null, over: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var fmtX = function (m) { return "x" + (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2)); };
  var mult = function (lv, n) { return S.rtp / Math.pow(P[lv], n); };
  var RABBIT = '<svg viewBox="0 0 48 48" width="40" height="40"><ellipse cx="17" cy="12" rx="4" ry="11" fill="#fff" stroke="#e5e7eb"/><ellipse cx="31" cy="12" rx="4" ry="11" fill="#fff" stroke="#e5e7eb"/><ellipse cx="17" cy="13" rx="1.8" ry="7" fill="#fbcfe8"/><ellipse cx="31" cy="13" rx="1.8" ry="7" fill="#fbcfe8"/><circle cx="24" cy="30" r="14" fill="#fff" stroke="#e5e7eb"/><circle cx="19" cy="28" r="1.8" fill="#111"/><circle cx="29" cy="28" r="1.8" fill="#111"/><ellipse cx="24" cy="34" rx="2.4" ry="1.6" fill="#f472b6"/></svg>';
  var CARROT = '<svg viewBox="0 0 32 32" width="28" height="28"><path d="M20 10c4 2 6 5 3 9l-9 11c-2 2-4 0-4-2L12 14c1-4 5-6 8-4z" fill="#f97316" stroke="#c2410c" stroke-width="1.5"/><path d="M19 9c0-4 2-6 5-6M19 9c-2-3-5-3-7-1M19 9c3-1 6 0 7 2" stroke="#16a34a" stroke-width="2.4" fill="none" stroke-linecap="round"/></svg>';
  var SPIKES = '<svg viewBox="0 0 40 28" width="36" height="26"><path d="M2 26l5-20 5 20 5-20 5 20 5-20 5 20 5-20" fill="#cbd5e1" stroke="#64748b" stroke-width="1.5" stroke-linejoin="round"/><rect x="2" y="23" width="36" height="4" fill="#64748b"/></svg>';

  window.setupRabbitRoad = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("cr-page", "cr-page-rabbit"); pg.classList.add("kx-page"); }
    if (!root.dataset.rb) {
      root.dataset.rb = "1";
      var seg = LV.map(function (l) { return '<button type="button" data-l="' + l[0] + '">' + l[1] + "</button>"; }).join("");
      root.innerHTML = '<div class="rb-wrap"><div class="rb-top"><span class="rb-hops" id="rb-hops">Hops 0</span></div>' +
        '<div class="rb-board"><div class="rb-head"><b id="rb-fin">FINISH</b><b id="rb-lane">Lane 0 of ' + MAX + '</b></div><div class="rb-lanes" id="rb-lanes"></div></div>' +
        '<div class="rb-stats"><div class="kx-tile"><small>Multiplier</small><b id="rb-mult" class="b">x1.00</b></div><div class="kx-tile"><small>Carrots won</small><b id="rb-win" class="o">0.00</b></div></div>' +
        '<div class="av-card"><div class="av-cols"><div class="av-bet-col"><label for="rabbit-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="rabbit-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="av-bet-col"><label>&nbsp;</label><div class="pk-seg" id="rb-seg">' + seg + '</div></div></div>' +
        '<div class="rb-acts"><button type="button" id="rb-start" class="av-go">Bet</button><button type="button" id="rb-hop" class="av-go" hidden>Hop</button><button type="button" id="rb-cash" class="av-go rb-cash" hidden>Cash Out</button></div>' +
        '<div class="kx-msg" id="rb-msg" aria-live="polite"></div><div class="kx-proof" id="rb-proof"></div></div>' +
        '<small class="kx-note">በእያንዳንዱ ዝላይ ሰርቨሩ ይወስናል። ደህና ዝላይ ሲያደርጉ ማባዣው ይጨምራል፤ ከማንኛውም ደህና ዝላይ በኋላ Cash Out ይችላሉ። ማባዣ = RTP ÷ (የደህንነት ዕድል)<sup>ዝላይ</sup>፤ የሚታየው ሁሉ እውነተኛ ክፍያ ነው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || S.round) return; var i = $(root, "#rabbit-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#rabbit-stake").addEventListener("input", function () { paint(root); });
      root.querySelectorAll("#rb-seg button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || S.round) return; S.level = b.dataset.l; S.over = null; hap("light"); paint(root); }); });
      $(root, "#rb-start").addEventListener("click", function () { start(root); });
      $(root, "#rb-hop").addEventListener("click", function () { hop(root); });
      $(root, "#rb-cash").addEventListener("click", function () { cash(root); });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.rtp = Number(s.rtp) || (1 - Number(s.house_edge || 0.08)); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.loaded = true; } catch (_) { S.loaded = true; } }
    if (!S.round) { try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); } catch (_) {} }
    paint(root);
  };
  function adopt(d) {
    var st = d.state || {}, inp = st.input || {}; S.level = inp.difficulty || S.level; S.over = null;
    S.round = { id: d.round_id, stake: Number(d.stake), level: S.level, progress: Number(st.progress || 0), mult: st.multipliers || lvMult(S.level), commit: d.seed_commit || "" };
  }
  function lvMult(lv) { var a = []; for (var i = 1; i <= MAX; i++) a.push(mult(lv, i)); return a; }
  function cur() { return S.round || S.over || null; }

  function paint(root) {
    var r = S.round, o = S.over, lv = r ? r.level : (o ? o.level : S.level), ms = r ? r.mult : (o ? o.mult : lvMult(lv)), prog = r ? r.progress : (o ? o.progress : 0), stake = r ? r.stake : (o ? o.stake : (Number($(root, "#rabbit-stake").value) || 0));
    var hit = o && o.hit ? o.hit : 0;
    root.querySelectorAll("#rb-seg button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === lv); b.disabled = !!r || S.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = !!r || S.busy; }); $(root, "#rabbit-stake").disabled = !!r || S.busy;
    $(root, "#rb-hops").textContent = "Hops " + prog; $(root, "#rb-fin").textContent = "FINISH " + fmtX(ms[MAX - 1]); $(root, "#rb-lane").textContent = "Lane " + Math.min(MAX, prog + (hit ? 0 : 0)) + " of " + MAX;
    var m = prog ? ms[prog - 1] : 1; $(root, "#rb-mult").textContent = fmtX(m);
    var win = r ? (prog ? stake * m : 0) : (o && o.won ? o.payout : 0); $(root, "#rb-win").textContent = money(win);
    // lanes: window of 6 (top = further), lane 0 = START
    var top = Math.max(5, Math.min(MAX, prog + 3)), html = "";
    for (var n = top; n > top - 6; n--) {
      var cls = "rb-lane", inner = '<span class="x">' + (n === 0 ? "START" : fmtX(ms[n - 1])) + '</span><span class="ic">';
      if (hit && n === hit) { cls += " hit"; inner += SPIKES; }
      else if (n === prog && !hit) { cls += " cur"; inner += RABBIT; }
      else if (n < prog) { cls += " done"; inner += CARROT; }
      else if (r && n === prog + 1) { cls += " next"; inner += '<em>?</em>'; }
      html += '<div class="' + cls + '">' + inner + "</span></div>";
    }
    $(root, "#rb-lanes").innerHTML = html;
    var live = !!r; $(root, "#rb-start").hidden = live; $(root, "#rb-hop").hidden = !live; $(root, "#rb-cash").hidden = !live;
    $(root, "#rb-start").disabled = S.busy; $(root, "#rb-start").textContent = "Bet " + money(Number($(root, "#rabbit-stake").value) || 0) + " ETB";
    $(root, "#rb-hop").disabled = S.busy; $(root, "#rb-cash").disabled = S.busy || !r || r.progress < 1;
    $(root, "#rb-cash").innerHTML = r && r.progress >= 1 ? "Cash Out<small>" + money(stake * m) + " ETB</small>" : "Cash Out";
  }
  function say(root, cls, t) { var e = $(root, "#rb-msg"); e.className = "kx-msg " + cls; e.textContent = t; }

  async function start(root) {
    if (S.busy || S.round) return; var stake = Number($(root, "#rabbit-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.over = null; say(root, "", ""); $(root, "#rb-proof").textContent = ""; paint(root);
    try {
      var r = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, difficulty: S.level, client_seed: makeClientSeed() } });
      var st = r.state || {}; S.round = { id: r.round_id, stake: stake, level: S.level, progress: 0, mult: st.multipliers || lvMult(S.level), commit: r.seed_commit || "" };
      $(root, "#rb-proof").textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || "").slice(0, 16) + "…";
      hap("light"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }
  function end(root, a, hit) {
    var r = S.round, o = a.outcome || {}, won = a.status === "WON", pay = Number(a.payout || 0);
    S.over = { level: r.level, mult: r.mult, progress: Number(o.steps_cleared != null ? o.steps_cleared : r.progress), hit: hit || 0, won: won, payout: pay, stake: r.stake };
    S.round = null;
    if (won) { say(root, "win", "🎉 +" + money(pay - r.stake) + " ብር (" + fmtX(Number(o.multiplier || 0)) + ")"); hap("success"); }
    else { say(root, "lose", "💥 ወጥመድ ነክቷል -" + money(r.stake) + " ብር"); hap("error"); }
    if (o.server_seed) $(root, "#rb-proof").textContent = "ROUND " + (a.round_code || "") + " · SERVER SEED " + String(o.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
  }
  async function resync(root) {
    try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); else S.round = null; } catch (_) {}
  }
  async function hop(root) {
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
