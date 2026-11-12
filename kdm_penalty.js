/* PENALTY KICK (new look + mechanics): tap a corner to aim, shoot, every goal raises the multiplier, cash out after any goal.
   Same server engine "penaltystreak": every shot is a server-side roll; multiplier after n goals = RTP / p^n, so the numbers shown are
   exactly what is paid. The aimed corner is for the animation only -- it never changes the chance (the note on the page says so).
   Loaded after road_game.js; replaces window.setupPenaltyStreak. Presentation only. */
(function () {
  "use strict";
  var KEY = "penaltystreak", MAX = 10, P = { easy: 0.88, medium: 0.78, hard: 0.68 };   // MUST match PENALTYSTREAK_* in realtime_engine_v3.py
  var LV = [["easy", "Easy"], [ "medium", "Mid"], ["hard", "Hard"]];
  var S = { level: "easy", rtp: 0.95, min: 1, max: 10000, loaded: false, busy: false, round: null, over: null, aim: 1, anim: "" };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var fmtX = function (m) { return "x" + (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2)); };
  var mult = function (lv, n) { return S.rtp / Math.pow(P[lv], n); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var KEEPER = '<svg viewBox="0 0 60 70" width="54" height="64" aria-hidden="true"><circle cx="30" cy="12" r="9" fill="#f5c9a0"/><path d="M21 6c2-6 16-6 18 0-4-2-14-2-18 0z" fill="#3b2a1a"/><path d="M12 24l10-4h16l10 4 4 20-8 2-3-12v26H19V34l-3 12-8-2z" fill="#facc15" stroke="#a16207" stroke-width="1.5" stroke-linejoin="round"/><rect x="19" y="46" width="22" height="22" rx="3" fill="#1e3a8a"/><circle cx="8" cy="46" r="6" fill="#fff" stroke="#9ca3af"/><circle cx="52" cy="46" r="6" fill="#fff" stroke="#9ca3af"/></svg>';
  var BALL = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="12" cy="12" r="10.5" fill="#fff" stroke="#111827" stroke-width="1.5"/><path d="M12 6l4 3-1.5 5h-5L8 9z" fill="#111827"/></svg>';

  window.setupPenaltyStreak = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("cr-page"); pg.classList.add("kx-page"); }
    if (!root.dataset.pk2) {
      root.dataset.pk2 = "1";
      var cells = ""; for (var i = 0; i < 6; i++) cells += '<button type="button" class="pn-cell" data-c="' + i + '"><span></span></button>';
      var seg = LV.map(function (l) { return '<button type="button" data-l="' + l[0] + '">' + l[1] + "</button>"; }).join("");
      root.innerHTML = '<div class="pn-wrap"><div class="pn-top"><span class="pn-goals" id="pn-goals">Goals 0</span></div>' +
        '<div class="pn-pitch" id="pn-pitch"><div class="pn-goal"><div class="pn-grid" id="pn-grid">' + cells + '</div><div class="pn-keeper" id="pn-keeper">' + KEEPER + '</div></div>' +
        '<div class="pn-ball" id="pn-ball">' + BALL + '</div><div class="pn-tip" id="pn-tip">Tap a corner to aim, then shoot</div></div>' +
        '<div class="pn-chips" id="pn-chips"></div>' +
        '<div class="av-card"><div class="av-cols"><div class="av-bet-col"><label for="penaltystreak-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="penaltystreak-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="av-bet-col"><label id="pn-cl">Cash out now</label><b class="pn-cash-val" id="pn-cv">—</b></div></div>' +
        '<div class="pk-seg" id="pn-seg">' + seg + '</div>' +
        '<div class="pn-acts"><button type="button" id="pn-start" class="av-go">Bet</button><button type="button" id="pn-shoot" class="av-go" hidden>Shoot</button><button type="button" id="pn-cash" class="av-go rb-cash" hidden>Cash Out</button></div>' +
        '<div class="kx-msg" id="pn-msg" aria-live="polite"></div><div class="kx-proof" id="pn-proof"></div></div>' +
        '<small class="kx-note">ሰርቨሩ እያንዳንዱን ምት ይወስናል፤ የሚመርጡት ጥግ ዕድሉን አይቀይርም (ለእይታ ብቻ ነው)። ግብ ሲያስቆጥሩ ማባዣው ይጨምራል፣ ከማንኛውም ግብ በኋላ Cash Out ይችላሉ። ማባዣ = RTP ÷ (የግብ ዕድል)<sup>ግቦች</sup>፤ የሚታየው ሁሉ እውነተኛ ክፍያ ነው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || S.round) return; var i = $(root, "#penaltystreak-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#penaltystreak-stake").addEventListener("input", function () { paint(root); });
      root.querySelectorAll("#pn-seg button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || S.round) return; S.level = b.dataset.l; S.over = null; hap("light"); paint(root); }); });
      root.querySelectorAll(".pn-cell").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; S.aim = Number(b.dataset.c); hap("light"); paint(root); }); });
      $(root, "#pn-start").addEventListener("click", function () { start(root); });
      $(root, "#pn-shoot").addEventListener("click", function () { shoot(root); });
      $(root, "#pn-cash").addEventListener("click", function () { cash(root); });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.rtp = Number(s.rtp) || (1 - Number(s.house_edge || 0.05)); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.loaded = true; } catch (_) { S.loaded = true; } }
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
    var stake = r ? r.stake : (o ? o.stake : (Number($(root, "#penaltystreak-stake").value) || 0));
    root.querySelectorAll("#pn-seg button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === lv); b.disabled = !!r || S.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = !!r || S.busy; }); $(root, "#penaltystreak-stake").disabled = !!r || S.busy;
    root.querySelectorAll(".pn-cell").forEach(function (b) { b.classList.toggle("aim", Number(b.dataset.c) === S.aim); b.querySelector("span").textContent = fmtX(prog < MAX ? ms[prog] : ms[MAX - 1]); });
    $(root, "#pn-goals").textContent = "Goals " + prog;
    // chips: window of 5 goals
    var first = Math.max(0, Math.min(MAX - 5, prog - 1)), h = "";
    for (var n = first + 1; n <= first + 5; n++) h += '<div class="' + (n <= prog ? "done" : r && n === prog + 1 ? "next" : "") + '"><small>Goal ' + n + "</small><b>" + fmtX(ms[n - 1]) + "</b></div>";
    $(root, "#pn-chips").innerHTML = h;
    var m = prog ? ms[prog - 1] : 1, live = !!r;
    $(root, "#pn-cv").textContent = live && prog ? money(stake * m) : (o && o.won ? money(o.payout) : "—");
    $(root, "#pn-cl").textContent = o && !live ? (o.won ? "You won" : "Round lost") : "Cash out now";
    $(root, "#pn-start").hidden = live; $(root, "#pn-shoot").hidden = !live; $(root, "#pn-cash").hidden = !live;
    $(root, "#pn-start").disabled = S.busy; $(root, "#pn-start").textContent = "Bet " + money(Number($(root, "#penaltystreak-stake").value) || 0) + " ETB";
    $(root, "#pn-shoot").disabled = S.busy; $(root, "#pn-cash").disabled = S.busy || !live || prog < 1;
    $(root, "#pn-cash").innerHTML = live && prog >= 1 ? "Cash Out<small>" + money(stake * m) + " ETB</small>" : "Cash Out";
    $(root, "#pn-pitch").className = "pn-pitch " + S.anim;
  }
  function say(root, cls, t) { var e = $(root, "#pn-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  function place(root, cell, saved) {
    // ball flies to the aimed cell; keeper dives to the same cell if saved, otherwise to a different one
    var grid = $(root, "#pn-grid"), cs = grid.querySelectorAll(".pn-cell"), pr = $(root, "#pn-pitch").getBoundingClientRect(), a = cs[S.aim].getBoundingClientRect();
    var ball = $(root, "#pn-ball"), kp = $(root, "#pn-keeper"), tc = cell;
    var t = cs[tc].getBoundingClientRect();
    ball.style.transform = "translate(" + (a.left + a.width / 2 - pr.left - pr.width / 2) + "px," + (a.top + a.height / 2 - pr.top - (pr.height - 40)) + "px) scale(.8)";
    kp.style.transform = "translate(" + (t.left + t.width / 2 - pr.left - pr.width / 2) + "px," + (t.top + t.height / 2 - pr.top - 60) + "px) rotate(" + (tc % 3 === 0 ? -35 : tc % 3 === 2 ? 35 : 0) + "deg)";
  }
  function reset(root) { var b = $(root, "#pn-ball"), k = $(root, "#pn-keeper"); b.style.transform = ""; k.style.transform = ""; S.anim = ""; }

  async function start(root) {
    if (S.busy || S.round) return; var stake = Number($(root, "#penaltystreak-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.over = null; reset(root); say(root, "", ""); $(root, "#pn-proof").textContent = ""; paint(root);
    try {
      var r = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, difficulty: S.level, client_seed: makeClientSeed() } });
      var st = r.state || {}; S.round = { id: r.round_id, stake: stake, level: S.level, progress: 0, mult: st.multipliers || lvMult(S.level) };
      $(root, "#pn-proof").textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || "").slice(0, 16) + "…";
      hap("light"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }
  function end(root, a) {
    var r = S.round, o = a.outcome || {}, won = a.status === "WON", pay = Number(a.payout || 0);
    S.over = { level: r.level, mult: r.mult, progress: Number(o.steps_cleared != null ? o.steps_cleared : r.progress), won: won, payout: pay, stake: r.stake };
    S.round = null;
    if (won) { say(root, "win", "🎉 +" + money(pay - r.stake) + " ብር (" + fmtX(Number(o.multiplier || 0)) + ")"); hap("success"); }
    else { say(root, "lose", "🧤 ጠባቂው አዳነው -" + money(r.stake) + " ብር"); hap("error"); }
    if (o.server_seed) $(root, "#pn-proof").textContent = "ROUND " + (a.round_code || "") + " · SERVER SEED " + String(o.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
  }
  async function resync(root) {
    try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); else S.round = null; } catch (_) {}
  }
  async function shoot(root) {
    var r = S.round; if (!r || S.busy) return; S.busy = true; paint(root);
    try {
      var a = await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "step" } });
      var saved = a.status === "LOST", other = (S.aim + 1 + Math.floor(Math.random() * 5)) % 6;
      S.anim = "shot"; place(root, saved ? S.aim : other, saved); await sleep(700);
      if (a.status === "ACTIVE") { r.progress = a.progress; say(root, "win", "⚽ GOAL! " + fmtX(r.mult[r.progress - 1])); hap("light"); }
      else if (a.status === "LOST") end(root, a);
      else if (a.status === "WON") { r.progress = a.progress || MAX; end(root, a); }
      await sleep(350); reset(root);
    } catch (e) { say(root, "bad", "❌ " + e.message); reset(root); await resync(root); }
    S.busy = false; paint(root);
  }
  async function cash(root) {
    var r = S.round; if (!r || S.busy || r.progress < 1) return; S.busy = true; paint(root); hap("medium");
    try { end(root, await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "cashout" } })); }
    catch (e) { say(root, "bad", "❌ " + e.message); await resync(root); }
    S.busy = false; paint(root);
  }
})();
