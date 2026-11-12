/* JET (new look + mechanics, radar theme). Same server-authoritative crash engine as Aviator (key "jet"): the server holds the hidden
   crash point, runs the time-based curve, auto-eject and settlement; this file only draws state and sends bet / eject.
   SELF-REGISTERING: wraps window.setupAddedGameControls, so no edit to app.js is needed. Load after app.js. Needs kdm_jet.css. */
(function () {
  "use strict";
  var KEY = "jet", CHIPS = [20, 50, 100, "MAX"];
  var S = { min: 1, max: 10000, loaded: false, busy: false, stopped: true, auto: 2.5, hist: [], round: "", sweep: 0, raf: 0, mult: 1, crashed: false };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };

  var prev = window.setupAddedGameControls;
  window.setupAddedGameControls = function (key) { if (key === KEY) return window.setupJet(); return prev ? prev.apply(this, arguments) : undefined; };

  function limits() {
    if (S.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) { S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.loaded = true; }).catch(function () { S.loaded = true; });
  }
  function recentHtml() {
    return S.hist.slice(0, 3).map(function (m, i) { return '<span class="jt-pill' + (i === 2 ? " hot" : "") + '">' + m.toFixed(2) + "</span>"; }).join("") || '<span class="jt-pill">—</span>';
  }

  window.setupJet = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page", "jt-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var chips = CHIPS.map(function (c) { return '<button type="button" data-v="' + c + '">' + c + "</button>"; }).join("");
      root.innerHTML = '<div class="jt-wrap"><div class="jt-top"><span class="jt-hot">HOT</span><span class="jt-round" id="jt-round">Round —</span></div>' +
        '<div class="jt-radar" id="jt-radar"><div class="jt-tag">RADAR · LIVE</div><div class="jt-recent" id="jt-recent"></div><canvas id="jt-cv" width="640" height="520"></canvas>' +
        '<div class="jt-mid"><b id="jt-mult">1.00x</b><small id="jt-state">READY</small></div></div>' +
        '<div class="jt-stats"><div class="jt-tile"><small>Climb</small><div class="jt-bar"><i id="jt-bar"></i></div></div><div class="jt-tile"><small>My last rounds</small><b id="jt-n">0</b></div></div>' +
        '<div class="jt-card"><div class="jt-chips" id="jt-chips">' + chips + '</div>' +
        '<div class="jt-row"><div class="jt-auto"><span>Auto eject at</span><div class="jt-step"><button type="button" data-a="-1">−</button><b id="jt-autov">x2.50</b><button type="button" data-a="1">+</button></div></div>' +
        '<input id="jet-stake" class="game-stake jt-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50" aria-label="Bet amount"></div>' +
        '<button type="button" id="jt-go" class="jt-eject">Bet</button><div class="kx-msg" id="jt-msg" aria-live="polite"></div><div class="kx-proof" id="jt-proof"></div></div>' +
        '<small class="kx-note">ሰርቨሩ የመከስከሻ ነጥቡን ከበፊት ይደብቃል፤ ከመከስከሱ በፊት EJECT ሲጫኑ ብቻ ያሸንፋሉ። Auto eject ከደረሰ ሰርቨሩ ራሱ ይከፍላል። በቅርብ ጊዜ የተከሰከሱባቸው ነጥቦች የራስዎ እውነተኛ ዙሮች ናቸው።</small></div>';
      root.querySelectorAll("#jt-chips button").forEach(function (b) {
        b.addEventListener("click", function () { if (S.busy) return; $(root, "#jet-stake").value = b.dataset.v === "MAX" ? S.max : Number(b.dataset.v); hap("light"); paint(root); });
      });
      root.querySelectorAll("[data-a]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy) return; var a = S.auto == null ? 1.0 : S.auto, d = Number(b.dataset.a), st = a < 2 ? 0.1 : a < 10 ? 0.5 : 5, n = Math.round((a + d * st) * 100) / 100;
          S.auto = n < 1.1 ? null : Math.min(100, n); hap("light"); paint(root);
        });
      });
      $(root, "#jet-stake").addEventListener("input", function () { paint(root); });
      $(root, "#jt-go").addEventListener("click", function () { go(root); });
      try { var h = await apiFetch("/games/" + KEY + "/history?limit=20"); S.hist = []; (h.items || []).forEach(function (it) { var c = Number((it.outcome || {}).crash); if (c >= 1) S.hist.push(Math.round(c * 100) / 100); }); S.n = (h.items || []).length; } catch (_) {}
      loop(root);
    }
    await limits(); paint(root);
  };

  function paint(root) {
    $(root, "#jt-recent").innerHTML = recentHtml(); $(root, "#jt-n").textContent = S.n || 0;
    $(root, "#jt-autov").textContent = S.auto == null ? "Off" : "x" + S.auto.toFixed(2);
    var v = Number($(root, "#jet-stake").value) || 0;
    $(root, "#jt-chips").querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", (b.dataset.v === "MAX" ? S.max : Number(b.dataset.v)) === v); b.disabled = S.busy; });
    root.querySelectorAll(".jt-step button").forEach(function (b) { b.disabled = S.busy; }); $(root, "#jet-stake").disabled = S.busy;
    if (!S.busy) { var g = $(root, "#jt-go"); g.className = "jt-eject"; g.disabled = false; g.textContent = "Bet " + money(v) + " ETB"; }
  }

  function loop(root) {   // radar sweep + jet, redrawn every frame from S.mult / S.crashed
    var cv = $(root, "#jt-cv"); if (!cv) return;
    (function frame() {
      if (!document.body.contains(cv)) return;
      draw(cv, S.mult, S.crashed, S.busy && !S.stopped); S.raf = requestAnimationFrame(frame);
    })();
  }
  function draw(cv, mult, crashed, flying) {
    var ctx = cv.getContext("2d"), w = cv.width, h = cv.height, cx = w / 2, cy = h / 2 + 10, R = Math.min(w, h) * 0.46;
    ctx.clearRect(0, 0, w, h); ctx.strokeStyle = "rgba(255,140,50,.28)"; ctx.lineWidth = 2;
    for (var i = 1; i <= 4; i++) { ctx.beginPath(); ctx.arc(cx, cy, R * i / 4, 0, 6.283); ctx.stroke(); }
    for (var a = 0; a < 4; a++) { ctx.beginPath(); ctx.moveTo(cx + R * Math.cos(a * 0.785), cy + R * Math.sin(a * 0.785)); ctx.lineTo(cx - R * Math.cos(a * 0.785), cy - R * Math.sin(a * 0.785)); ctx.stroke(); }
    S.sweep = (S.sweep + 0.03) % 6.283; var g = ctx.createConicGradient ? ctx.createConicGradient(S.sweep, cx, cy) : null;
    if (g) { g.addColorStop(0, "rgba(255,150,60,.0)"); g.addColorStop(0.9, "rgba(255,150,60,.0)"); g.addColorStop(1, "rgba(255,150,60,.35)"); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.283); ctx.fill(); }
    var frac = Math.min(1, Math.log(Math.max(1, mult)) / Math.log(100)), ang = -0.785, dist = R * (0.1 + 0.88 * Math.sqrt(frac));
    var ex = cx + Math.cos(ang) * dist, ey = cy + Math.sin(ang) * dist, sx = cx - R * 0.55, sy = cy + R * 0.55;
    ctx.setLineDash([6, 10]); ctx.strokeStyle = crashed ? "#8a93b8" : "#fb923c"; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(cx - R * 0.1, cy + R * 0.2, ex, ey); ctx.stroke(); ctx.setLineDash([]);
    ctx.save(); ctx.translate(ex, ey); ctx.rotate(crashed ? 0.8 : ang);
    ctx.fillStyle = crashed ? "#6b7391" : "#fdba74"; ctx.beginPath(); ctx.moveTo(30, 0); ctx.lineTo(-18, -7); ctx.lineTo(-10, 0); ctx.lineTo(-18, 7); ctx.closePath(); ctx.fill();
    ctx.fillStyle = crashed ? "#555c78" : "#f97316"; ctx.beginPath(); ctx.moveTo(4, 0); ctx.lineTo(-14, -24); ctx.lineTo(-8, 0); ctx.lineTo(-14, 24); ctx.closePath(); ctx.fill(); ctx.restore();
    if (crashed) { ctx.fillStyle = "rgba(239,68,68,.85)"; ctx.beginPath(); ctx.arc(ex, ey, 14 + (S.sweep * 6) % 10, 0, 6.283); ctx.fill(); }
    if (flying || mult > 1) { var bar = document.getElementById("jt-bar"); if (bar) bar.style.width = Math.round(frac * 100) + "%"; }
  }

  async function go(root) {
    if (S.busy) return;
    var msg = $(root, "#jt-msg"), proof = $(root, "#jt-proof"), stake = Number($(root, "#jet-stake").value);
    if (!(stake > 0)) { msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; return; }
    if (stake < S.min || stake > S.max) { msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"; return; }
    S.busy = true; S.stopped = false; S.crashed = false; S.mult = 1; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; paint(root);
    var body = { stake: stake }; if (S.auto != null) body.auto_cashout = S.auto;
    var btn = $(root, "#jt-go"), multEl = $(root, "#jt-mult"), stEl = $(root, "#jt-state"), radar = $(root, "#jt-radar"); btn.disabled = true; btn.textContent = "…";
    var r;
    try { r = await startRealtimeRound(KEY, body); } catch (e) { S.busy = false; S.stopped = true; paint(root); msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; return; }
    var rc = String(r.round_code || ""); $(root, "#jt-round").textContent = "Round #" + (rc.split("-").pop() || rc);
    proof.textContent = "ROUND " + rc + " · COMMIT " + String(r.seed_commit || r.commitment || "").slice(0, 16) + "…";
    radar.classList.remove("crashed", "won"); stEl.textContent = "IN FLIGHT";
    btn.className = "jt-eject live"; btn.disabled = false; btn.innerHTML = "EJECT<small>" + money(stake) + " ETB</small>";
    var result = null, cashing = false;
    btn.onclick = async function () {
      if (cashing || S.stopped) return; cashing = true; btn.disabled = true; hap("medium");
      try { result = await realtimeAction(KEY, "cashout"); } catch (e) { msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; result = null; cashing = false; btn.disabled = false; }
    };
    while (!result && !S.stopped) {
      try {
        var st = await realtimeState(KEY); S.mult = Number(st.live_multiplier || 1); multEl.textContent = S.mult.toFixed(2) + "x";
        if (!cashing) btn.innerHTML = "EJECT<small>" + money(stake * S.mult) + " ETB</small>";
        if (st.phase === "CRASHED" || st.status === "WON" || st.status === "LOST") { S.stopped = true; try { result = await realtimeAction(KEY, "cashout"); } catch (_) { result = null; } break; }
      } catch (_) {}
      await new Promise(function (res) { setTimeout(res, 220); });
    }
    while (!result && cashing) await new Promise(function (res) { setTimeout(res, 80); });
    S.stopped = true; btn.onclick = null;
    var o = (result && result.outcome) || {}, crash = Number(o.crash || (result && result.crash) || 0), pay = Number((result && result.payout) || 0), won = !!(result && result.won);
    if (crash >= 1) { S.hist.unshift(Math.round(crash * 100) / 100); S.hist = S.hist.slice(0, 20); } S.n = (S.n || 0) + 1;
    if (won) { radar.classList.add("won"); stEl.textContent = "EJECTED"; multEl.textContent = (pay / stake).toFixed(2) + "x"; msg.className = "kx-msg win"; msg.textContent = "🎉 አሸንፈዋል +" + money(pay - stake) + " ብር"; hap("success"); }
    else { S.crashed = true; radar.classList.add("crashed"); stEl.textContent = "CRASHED"; if (crash >= 1) { multEl.textContent = crash.toFixed(2) + "x"; S.mult = crash; } msg.className = "kx-msg lose"; msg.textContent = "💥 ተከስክሷል -" + money(stake) + " ብር"; hap("error"); }
    if (result && result.server_seed) proof.textContent = "ROUND " + (result.round_code || rc) + " · SERVER SEED " + String(result.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    S.busy = false; paint(root);
  }
})();
