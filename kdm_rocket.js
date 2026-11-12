/* ROCKET (new look + mechanics). Same server-authoritative crash engine as Jet (catalog skin "rocket" on the jet page): the server
   holds the hidden crash point, runs the curve and settles; this file only draws state and sends bet / cash out.
   BET 1 and BET 2 are two stake slots. The engine allows ONE live round per player, so: a slot's button launches a round when
   none is flying, and while a round is flying the OTHER slot's button queues its stake for the next launch (auto-starts after
   the countdown). Nothing here decides a result or a payout.
   SELF-REGISTERING: wraps window.setupJet (load after kdm_jet.js). Needs kdm_rocket.css. */
(function () {
  "use strict";
  var KEY = "jet", SKIN = "rocket", GAP = 6;       // GAP = seconds between rounds when a bet is queued
  var S = { min: 1, max: 10000, loaded: false, busy: false, stopped: true, mult: 1, crashed: false, flying: -1, queued: -1,
            stake: [25, 100], hist: [], round: "", raf: 0, cd: 0, cdTimer: 0, stars: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var esc = function (v) { return String(v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var isRocket = function () { return typeof window.kdmSkinKey === "function" && window.kdmSkinKey() === SKIN; };

  var prev = window.setupJet;
  window.setupJet = function () {
    var root = document.getElementById(KEY + "-controls");
    if (isRocket()) return setup(root);
    if (root && root.dataset.built === "rocket") { stopAll(); delete root.dataset.built; root.innerHTML = ""; }   // back to plain Jet: let kdm_jet.js rebuild
    return prev ? prev.apply(this, arguments) : undefined;
  };

  function stopAll() { S.cd = 0; clearInterval(S.cdTimer); S.queued = -1; S.stopped = true; if (S.raf) cancelAnimationFrame(S.raf); S.raf = 0; }
  function alive(root) { return document.body.contains(root) && root.dataset.built === "rocket" && isRocket(); }
  function stepFor(v) { return v >= 1000 ? 100 : v >= 100 ? 10 : v >= 20 ? 5 : 1; }
  function clamp(v) { return Math.max(S.min, Math.min(S.max, Math.round(v * 100) / 100)); }

  function limits() {
    if (S.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) { S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.loaded = true; }).catch(function () { S.loaded = true; });
  }

  function slotHtml(i) {
    return '<div class="rk-bet" id="rk-bet' + i + '"><div class="rk-bt">BET ' + (i + 1) + '</div>' +
      '<div class="rk-step"><button type="button" data-s="' + i + '" data-d="-1" aria-label="Decrease bet ' + (i + 1) + '">−</button>' +
      '<input id="rk-s' + i + '" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake[i] + '" aria-label="Bet ' + (i + 1) + ' amount">' +
      '<button type="button" data-s="' + i + '" data-d="1" aria-label="Increase bet ' + (i + 1) + '">+</button></div>' +
      '<button type="button" class="rk-go" id="rk-go' + i + '"></button></div>';
  }

  async function setup(root) {
    if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page", "rk-page");
    if (root.dataset.built !== "rocket") {
      stopAll(); S.busy = false; S.flying = -1; S.crashed = false; S.mult = 1; S.hist = [];
      root.dataset.built = "rocket";
      root.innerHTML = '<div class="rk-wrap"><div class="rk-sky" id="rk-sky"><canvas id="rk-cv" width="640" height="660"></canvas>' +
        '<div class="rk-alt"><small>ALTITUDE</small><b id="rk-mult">1.00x</b></div>' +
        '<span class="rk-pill rk-l" id="rk-next">Place a bet to launch</span><span class="rk-pill rk-r" id="rk-round">Round —</span></div>' +
        '<div class="rk-hist" id="rk-hist"></div>' +
        '<div class="rk-bets">' + slotHtml(0) + slotHtml(1) + '</div>' +
        '<div class="kx-msg" id="rk-msg" aria-live="polite"></div><div class="kx-proof" id="rk-proof"></div>' +
        '<div class="rk-wins"><div class="rk-wt">Top winners</div><div id="rk-wl"><span class="rk-none">—</span></div></div>' +
        '<small class="kx-note">ሰርቨሩ የመከስከሻ ነጥቡን ከበፊት ይደብቃል፤ ከመከስከሱ በፊት Cash Out ሲጫኑ ብቻ ያሸንፋሉ። ሌላኛውን BET ሲጫኑ (ዙር በሚበርበት ጊዜ) ለሚቀጥለው ዙር ይሰለፋል።</small></div>';
      root.querySelectorAll(".rk-step button").forEach(function (b) {
        b.addEventListener("click", function () {
          var i = Number(b.dataset.s); if (S.busy && S.flying === i) return;
          var inp = $(root, "#rk-s" + i), v = Number(inp.value) || 0;
          inp.value = clamp(v + Number(b.dataset.d) * stepFor(v)).toFixed(2); S.stake[i] = Number(inp.value); hap("light"); paint(root);
        });
      });
      [0, 1].forEach(function (i) {
        $(root, "#rk-s" + i).addEventListener("input", function () { S.stake[i] = Number(this.value) || 0; paint(root); });
        $(root, "#rk-go" + i).addEventListener("click", function () { press(root, i); });
      });
      try {
        var h = await apiFetch("/games/" + KEY + "/history?limit=20"); S.hist = [];
        (h.items || []).forEach(function (it) { var c = Number((it.outcome || {}).crash); if (c >= 1) S.hist.push(Math.round(c * 100) / 100); });
      } catch (_) {}
      loop(root); winners(root);
    }
    await limits(); paint(root);
  }

  function histHtml() {
    return S.hist.slice(0, 7).map(function (m) { return '<span class="' + (m < 1.5 ? "lo" : m >= 10 ? "hi" : "") + '">' + m.toFixed(2) + "x</span>"; }).join("") || '<span class="none">—</span>';
  }
  function paint(root) {
    if (!alive(root)) return;
    $(root, "#rk-hist").innerHTML = histHtml();
    [0, 1].forEach(function (i) {
      var inp = $(root, "#rk-s" + i), go = $(root, "#rk-go" + i), v = Number(inp.value) || 0;
      inp.disabled = S.busy && S.flying === i; root.querySelectorAll('.rk-step button[data-s="' + i + '"]').forEach(function (b) { b.disabled = S.busy && S.flying === i; });
      go.className = "rk-go";
      if (S.busy && S.flying === i) { go.className = "rk-go cash"; go.disabled = !!go.dataset.cashing; go.innerHTML = "<span>Cash Out</span><em>" + money(v * S.mult) + "</em>"; }
      else if (S.busy || S.cd > 0) { var q = S.queued === i; go.className = "rk-go" + (q ? " queued" : ""); go.disabled = false; go.innerHTML = "<span>" + (q ? "Queued ✓" : "Next round") + "</span><em>" + money(v) + "</em>"; }
      else { go.disabled = false; go.innerHTML = "<span>Launch</span><em>" + money(v) + "</em>"; }
    });
  }

  // ---- sky: stars, climbing flame trail, rocket, explosion (drawn from S.mult / S.crashed only)
  function loop(root) {
    var cv = $(root, "#rk-cv"); if (!cv) return;
    (function frame() {
      if (!alive(root)) return;
      draw(cv); S.raf = requestAnimationFrame(frame);
    })();
  }
  function draw(cv) {
    var ctx = cv.getContext("2d"), w = cv.width, h = cv.height, t = Date.now() / 1000;
    if (!S.stars) { S.stars = []; for (var i = 0; i < 46; i++) S.stars.push([Math.random() * w, Math.random() * h, 1 + Math.random() * 2, Math.random()]); }
    ctx.clearRect(0, 0, w, h);
    var frac = Math.min(1, Math.log(Math.max(1, S.mult)) / Math.log(50)), flying = S.busy && !S.stopped;
    S.stars.forEach(function (s) {
      var y = (s[1] + (flying ? t * 40 * (0.4 + s[3]) : 0)) % h;
      ctx.fillStyle = "rgba(255,255,255," + (0.25 + 0.6 * Math.abs(Math.sin(t * 1.5 + s[3] * 6))) + ")"; ctx.beginPath(); ctx.arc(s[0], y, s[2], 0, 6.283); ctx.fill();
    });
    var sx = w * 0.12, sy = h * 0.92, ex = w * (0.2 + 0.62 * frac), ey = h * (0.9 - 0.62 * frac);
    ctx.strokeStyle = S.crashed ? "rgba(140,140,170,.5)" : "rgba(255,170,60,.85)"; ctx.lineWidth = 6; ctx.setLineDash([3, 14]); ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(sx + (ex - sx) * 0.15, sy - (sy - ey) * 0.7, ex, ey); ctx.stroke(); ctx.setLineDash([]);
    var ang = Math.atan2(ey - (sy - (sy - ey) * 0.7), ex - (sx + (ex - sx) * 0.15));
    ctx.save(); ctx.translate(ex, ey); ctx.rotate(ang);
    if (S.crashed) {
      var r = 22 + ((t * 40) % 16); ctx.fillStyle = "rgba(239,68,68,.85)"; ctx.beginPath(); ctx.arc(0, 0, r, 0, 6.283); ctx.fill();
      ctx.fillStyle = "rgba(253,186,116,.9)"; ctx.beginPath(); ctx.arc(0, 0, r * 0.55, 0, 6.283); ctx.fill();
    } else {
      if (flying) { ctx.fillStyle = "rgba(251,146,60,.9)"; ctx.beginPath(); ctx.moveTo(-26, 0); ctx.lineTo(-52 - Math.random() * 14, -6); ctx.lineTo(-52 - Math.random() * 14, 6); ctx.closePath(); ctx.fill(); }
      ctx.fillStyle = "#f4f7ff"; ctx.beginPath(); ctx.moveTo(34, 0); ctx.quadraticCurveTo(10, -16, -26, -12); ctx.lineTo(-26, 12); ctx.quadraticCurveTo(10, 16, 34, 0); ctx.fill();
      ctx.fillStyle = "#8b5cf6"; ctx.beginPath(); ctx.moveTo(-8, -10); ctx.lineTo(-26, -26); ctx.lineTo(-26, -8); ctx.fill(); ctx.beginPath(); ctx.moveTo(-8, 10); ctx.lineTo(-26, 26); ctx.lineTo(-26, 8); ctx.fill();
      ctx.fillStyle = "#38bdf8"; ctx.beginPath(); ctx.arc(8, 0, 6, 0, 6.283); ctx.fill();
    }
    ctx.restore();
  }

  // ---- real data: other players' recent crash-family wins (masked names), never invented
  async function winners(root) {
    try {
      var d = await apiFetch("/wins/recent"), fam = { rocket: 1, jet: 1, aviator: 1, crash: 1, highflyer: 1, skymasters: 1 };
      var rows = (d.wins || []).filter(function (x) { return fam[x.game]; }).slice(0, 3);
      if (!alive(root)) return;
      $(root, "#rk-wl").innerHTML = rows.length ? rows.map(function (x) {
        var m = Number(x.multiplier) || 0, amt = Number(x.amount) || 0;
        return '<div class="rk-wr"><span class="n">' + esc(x.name || "Player") + '</span><span class="s">' + (m ? money(amt / m) : "—") + '</span><span class="m">' + (m ? m.toFixed(2) + "x" : "—") + '</span><span class="w">' + money(amt) + "</span></div>";
      }).join("") : '<span class="rk-none">ገና አሸናፊ የለም</span>';
    } catch (_) {}
  }

  function say(root, cls, t) { var m = $(root, "#rk-msg"); if (m) { m.className = "kx-msg " + cls; m.textContent = t; } }

  // ---- button logic
  function press(root, i) {
    var stake = Number($(root, "#rk-s" + i).value);
    if (S.busy && S.flying === i) return cashOut(root);
    if (S.busy || S.cd > 0) {             // another round is flying / counting down: queue (or un-queue) this slot
      if (S.queued === i) S.queued = -1;
      else { if (!(stake >= S.min && stake <= S.max)) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"); S.queued = i; hap("light"); }
      return paint(root);
    }
    launch(root, i);
  }

  var cashFn = null;
  function cashOut(root) { if (cashFn) cashFn(); }

  async function launch(root, i) {
    if (S.busy) return;
    var stake = Number($(root, "#rk-s" + i).value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.stopped = false; S.crashed = false; S.mult = 1; S.flying = i; S.cd = 0; clearInterval(S.cdTimer);
    [0, 1].forEach(function (k) { delete $(root, "#rk-go" + k).dataset.cashing; });
    var sky = $(root, "#rk-sky"), multEl = $(root, "#rk-mult"), nextEl = $(root, "#rk-next"), proof = $(root, "#rk-proof");
    sky.classList.remove("crashed", "won"); say(root, "", ""); proof.textContent = ""; nextEl.textContent = "Launching…"; paint(root);
    var r;
    try { r = await startRealtimeRound(KEY, { stake: stake }); }
    catch (e) { S.busy = false; S.stopped = true; S.flying = -1; S.queued = -1; nextEl.textContent = "Place a bet to launch"; paint(root); return say(root, "bad", "❌ " + e.message); }
    var rc = String(r.round_code || ""); $(root, "#rk-round").textContent = "Round #" + (rc.split("-").pop() || rc);
    proof.textContent = "ROUND " + rc + " · COMMIT " + String(r.seed_commit || r.commitment || "").slice(0, 16) + "…"; nextEl.textContent = "In flight";
    var result = null, cashing = false;
    cashFn = async function () {
      if (cashing || S.stopped) return; cashing = true; $(root, "#rk-go" + i).dataset.cashing = "1"; hap("medium"); paint(root);
      try { result = await realtimeAction(KEY, "cashout"); }
      catch (e) { say(root, "bad", "❌ " + e.message); result = null; cashing = false; delete $(root, "#rk-go" + i).dataset.cashing; paint(root); }
    };
    while (!result && !S.stopped) {
      if (!alive(root)) { S.stopped = true; break; }
      try {
        var st = await realtimeState(KEY); S.mult = Number(st.live_multiplier || 1); multEl.textContent = S.mult.toFixed(2) + "x";
        if (!cashing) paint(root);
        if (st.phase === "CRASHED" || st.status === "WON" || st.status === "LOST") { S.stopped = true; try { result = await realtimeAction(KEY, "cashout"); } catch (_) { result = null; } break; }
      } catch (_) {}
      await new Promise(function (res) { setTimeout(res, 220); });
    }
    while (!result && cashing) await new Promise(function (res) { setTimeout(res, 80); });
    S.stopped = true; cashFn = null;
    [0, 1].forEach(function (k) { var g = $(root, "#rk-go" + k); if (g) delete g.dataset.cashing; });
    var o = (result && result.outcome) || {}, crash = Number(o.crash || (result && result.crash) || 0), pay = Number((result && result.payout) || 0), won = !!(result && result.won);
    if (crash >= 1) { S.hist.unshift(Math.round(crash * 100) / 100); S.hist = S.hist.slice(0, 20); }
    if (won) { sky.classList.add("won"); multEl.textContent = (pay / stake).toFixed(2) + "x"; nextEl.textContent = "Cashed out"; say(root, "win", "🎉 አሸንፈዋል +" + money(pay - stake) + " ብር"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
    else { S.crashed = true; sky.classList.add("crashed"); if (crash >= 1) { multEl.textContent = crash.toFixed(2) + "x"; S.mult = crash; } nextEl.textContent = "Crashed"; say(root, "lose", "💥 ተከስክሷል -" + money(stake) + " ብር"); hap("error"); }
    if (result && result.server_seed) proof.textContent = "ROUND " + (result.round_code || rc) + " · SERVER SEED " + String(result.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    S.busy = false; S.flying = -1; paint(root); winners(root);
    if (S.queued >= 0 && alive(root)) countdown(root);
    else if (alive(root)) nextEl.textContent = "Place a bet to launch";
  }

  // the queued slot launches by itself after GAP seconds (cancel by tapping its button again)
  function countdown(root) {
    S.cd = GAP; var nextEl = $(root, "#rk-next");
    clearInterval(S.cdTimer);
    S.cdTimer = setInterval(function () {
      if (!alive(root)) { stopAll(); return; }
      if (S.queued < 0) { S.cd = 0; clearInterval(S.cdTimer); nextEl.textContent = "Place a bet to launch"; paint(root); return; }
      S.cd = Math.max(0, Math.round((S.cd - 0.1) * 10) / 10); nextEl.textContent = "Next launch in " + S.cd.toFixed(1) + "s";
      if (S.cd <= 0) { clearInterval(S.cdTimer); var i = S.queued; S.queued = -1; S.cd = 0; launch(root, i); }
    }, 100);
    paint(root);
  }
})();
