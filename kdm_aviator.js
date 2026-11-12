/* AVIATOR (new look + mechanics). The server decides everything: it holds the hidden crash point, runs the time-based
   curve, auto cash-out and settlement. This file only draws the state it gets back and sends bet / cash-out.
   Loaded after app.js (uses apiFetch, startRealtimeRound, realtimeState, realtimeAction, refreshBalance, haptic, escapeHtml). */
(function () {
  "use strict";
  var KEY = "aviator";
  var S = { min: 1, max: 10000, loaded: false, busy: false, stopped: true, auto: 2.0, hist: [], bets: [], samples: [], stake: 50, items: [], bStake: 20, queued: false, rtp: 0.95, plane: 0, live: 1 };
  var isSM = function () { return typeof window.kdmSkinKey === "function" && window.kdmSkinKey() === "skymasters"; };
  var PLANES = [["falcon", "Falcon", "steady", 2.0], ["viper", "Viper", "risky", 5.0], ["phoenix", "Phoenix", "jackpot", 20.0]], STUNTS = [["Loop", 1.5], ["Roll", 2], ["Dive", 3]];
  var isHF = function () { return typeof window.kdmSkinKey === "function" && window.kdmSkinKey() === "highflyer"; };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var CHIPS = [10, 50, 100, 500];

  function limits() {
    if (S.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.rtp = Number(s.rtp) || (1 - Number(s.house_edge || 0.05)); S.loaded = true;
    }).catch(function () { S.loaded = true; });
  }
  function tone(m) { return m >= 10 ? "pink" : m >= 2 ? "violet" : "blue"; }
  function stripHtml() {
    if (!S.hist.length) return '<span class="av-empty">—</span>';
    return S.hist.slice(0, 8).map(function (m) { return '<span class="av-chip ' + tone(m) + '">' + m.toFixed(2) + "x</span>"; }).join("");
  }
  function betsHtml() {
    if (!S.bets.length) return '<div class="av-none">ገና ውርርድ የለም</div>';
    return S.bets.slice(0, 5).map(function (b) {
      var won = b.payout > 0;
      return '<div class="av-bet"><span>' + money(b.stake) + '</span><span class="' + (won ? "b" : "d") + '">' + (b.mult ? b.mult.toFixed(2) + "x" : "—") +
        '</span><span class="' + (won ? "g" : "d") + '">' + (won ? money(b.payout) : "—") + "</span></div>";
    }).join("");
  }
  function fromHistory(items) {
    S.hist = []; S.bets = []; S.items = (items || []).map(function (it) { return { created_at: String(it.created_at || ""), stake: Number(it.stake || 0), payout: Number(it.payout || 0) }; });
    (items || []).forEach(function (it) {
      var o = it.outcome || {}, crash = Number(o.crash);
      if (crash >= 1) S.hist.push(Math.round(crash * 100) / 100);
      var pay = Number(it.payout || 0), st = Number(it.stake || 0);
      S.bets.push({ stake: st, payout: pay, mult: pay > 0 && st > 0 ? pay / st : 0 });
    });
  }

  window.setupAviator = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var page = document.getElementById("page-" + KEY); if (page) page.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="av-wrap">' +
        '<div class="av-strip" id="av-strip"></div>' +
        '<div class="av-stage" id="av-stage"><canvas id="av-cv" width="640" height="360"></canvas>' +
        '<div class="av-mid"><b id="av-mult">1.00x</b><small id="av-state">READY</small></div>' +
        '<div class="av-bar"><i id="av-barfill"></i></div></div>' +
        '<div class="av-card"><div class="av-cols">' +
        '<div class="av-bet-col"><label for="aviator-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="aviator-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="av-bet-col"><label>Auto Cashout</label><div class="kx-step"><button type="button" data-a="-1">−</button>' +
        '<input id="aviator-cashout" type="text" inputmode="decimal" readonly value="2.00x"><button type="button" data-a="1">+</button></div></div></div>' +
        '<div class="av-quick" id="av-quick"></div>' +
        '<button type="button" id="av-go" class="av-go">Bet</button>' +
        '<div class="kx-msg" id="av-msg" aria-live="polite"></div><div class="kx-proof" id="av-proof"></div></div>' +
        '<div class="av-card sm-only" id="sm-panel" hidden><div class="av-h">Choose your plane</div><div class="sm-planes" id="sm-planes"></div><small class="hf-hint" id="sm-chance"></small>' +
        '<div class="sm-stunts" id="sm-stunts"></div></div>' +
        '<div class="av-card hf-only" id="hf-panel" hidden><div class="av-h"><span>Bet B</span> <span class="hf-st" id="hf-bstate">not set</span></div>' +
        '<div class="av-bet-col"><label for="hf-bstake">Next-round bet</label><div class="kx-step"><button type="button" data-b="-1">−</button><input id="hf-bstake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="20"><button type="button" data-b="1">+</button></div></div>' +
        '<button type="button" id="hf-queue" class="hf-queue">Bet next</button><small class="hf-hint" id="hf-hint"></small></div>' +
        '<div class="av-card av-list hf-only" id="hf-stats" hidden><div class="av-h">My best today <b id="hf-best">—</b></div><div class="av-h">My top wins</div><div id="hf-top"></div></div>' +
        '<div class="av-card av-list" id="av-live"><div class="av-h">Live wins <small>(real players)</small></div><div id="av-live-list"><div class="av-none">…</div></div></div>' +
        '<div class="av-card av-list"><div class="av-h">My bets</div><div id="av-bets"></div></div>' +
        '<small class="kx-note">ሰርቨሩ የመከስከሻውን ነጥብ ከበፊት ይደብቃል፤ ከመከስከሱ በፊት Cash Out ሲጫኑ ብቻ ያሸንፋሉ። Auto Cashout ከደረሰ ሰርቨሩ ራሱ ይከፍላል።</small></div>';
      var q = $(root, "#av-quick");
      CHIPS.forEach(function (c) {
        var b = document.createElement("button"); b.type = "button"; b.dataset.v = c; b.textContent = c; q.appendChild(b);
        b.addEventListener("click", function () { if (S.busy) return; $(root, "#aviator-stake").value = c; hap("light"); paint(root); });
      });
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy) return;
          var inp = $(root, "#aviator-stake"), v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          inp.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      root.querySelectorAll("[data-a]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy) return;
          var a = S.auto == null ? 1.1 - 0.1 : S.auto, d = Number(b.dataset.a), step = a < 2 ? 0.1 : a < 10 ? 0.5 : 5;
          var n = Math.round((a + d * step) * 100) / 100;
          S.auto = n < 1.1 ? null : Math.min(100, n); hap("light"); paint(root);
        });
      });
      $(root, "#aviator-stake").addEventListener("input", function () { paint(root); });
      $(root, "#av-go").addEventListener("click", function () { go(root); });
      css();
      $(root, "#sm-planes").innerHTML = PLANES.map(function (p, i) { return '<button type="button" data-p="' + i + '"><b>' + p[1] + "</b><small>" + p[2] + "</small></button>"; }).join("");
      $(root, "#sm-stunts").innerHTML = STUNTS.map(function (t) { return '<span data-t="' + t[1] + '">' + t[0] + " x" + t[1] + "</span>"; }).join("");
      root.querySelectorAll("[data-p]").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; S.plane = Number(b.dataset.p); S.auto = PLANES[S.plane][3]; hap("light"); paint(root); }); });
      root.querySelectorAll("[data-b]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.queued) return; var i = $(root, "#hf-bstake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.b) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#hf-bstake").addEventListener("input", function () { if (!S.queued) paint(root); });
      $(root, "#hf-queue").addEventListener("click", function () {
        if (S.queued) { S.queued = false; hap("light"); paint(root); return; }
        var v = Number($(root, "#hf-bstake").value) || 0, msg = $(root, "#av-msg");
        if (!(v > 0) || v < S.min || v > S.max) { msg.className = "kx-msg bad"; msg.textContent = "❌ Bet B ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"; return; }
        S.bStake = v; S.queued = true; hap("medium"); paint(root);
      });
      try { var h = await apiFetch("/games/" + KEY + "/history?limit=20"); fromHistory(h.items); } catch (_) {}
      liveWins(root); if (S._lw) clearInterval(S._lw); S._lw = setInterval(function () { if (!document.body.contains(root)) { clearInterval(S._lw); return; } liveWins(root); }, 20000);
    }
    await limits(); paint(root); draw(root, 1, false);
  };

  function liveWins(root) {
    var box = root && root.querySelector("#av-live-list"); if (!box) return;
    apiFetch("/games/" + (window.kdmEngineKey ? window.kdmEngineKey() : KEY) + "/live-wins").then(function (r) {
      var it = (r && r.items) || [];
      box.innerHTML = it.length ? it.map(function (x) { return '<div class="hf-tw"><span>' + escapeHtml(x.name) + "</span><span>" + money(x.stake) + "</span><span>x" + Number(x.multiplier).toFixed(2) + "</span><b>" + money(x.payout) + "</b></div>"; }).join("") : '<div class="av-none">ገና የሌሎች አሸናፊ ዙር የለም</div>';
    }).catch(function () {});
  }
  function paint(root) {
    $(root, "#av-strip").innerHTML = stripHtml();
    $(root, "#av-bets").innerHTML = betsHtml();
    var v = Number($(root, "#aviator-stake").value) || 0;
    $(root, "#aviator-cashout").value = S.auto == null ? "Off" : S.auto.toFixed(2) + "x";
    $(root, "#av-quick").querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.v) === v); });
    if (!S.busy) { var g = $(root, "#av-go"); g.className = "av-go"; g.disabled = false; g.textContent = "Bet " + money(v) + " ETB"; }
    root.querySelectorAll(".kx-step button,.av-quick button").forEach(function (b) { b.disabled = S.busy; });
    paintHF(root); paintSM(root);
  }
  function paintSM(root) {
    var on = isSM(), p = $(root, "#sm-panel"); if (!p) return; p.hidden = !on;
    var ac = root.querySelector("[data-a]"); ac = ac && ac.closest(".av-bet-col"); if (ac) ac.style.display = on ? "none" : "";
    if (!on) return;
    if (!S.busy) S.auto = PLANES[S.plane][3];
    root.querySelectorAll("[data-p]").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.p) === S.plane); b.disabled = S.busy; });
    var t = PLANES[S.plane][3], wc = Math.min(100, S.rtp / t * 100);
    $(root, "#sm-chance").textContent = PLANES[S.plane][1] + ": auto land at x" + t.toFixed(2) + " · win chance ≈ " + wc.toFixed(wc < 10 ? 1 : 0) + "% (ሰርቨሩ ራሱ ይከፍላል)";
    root.querySelectorAll("#sm-stunts span").forEach(function (e) { e.classList.toggle("on", S.live >= Number(e.dataset.t)); });
  }
  function css() {
    if (document.getElementById("hf-css")) return; var st = document.createElement("style"); st.id = "hf-css";
    st.textContent = ".hf-only[hidden],.sm-only[hidden]{display:none}.sm-planes{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.sm-planes button{min-height:56px;border:0;border-radius:12px;background:#12204d;color:#c3d0ee;display:flex;flex-direction:column;align-items:center;justify-content:center}.sm-planes button b{font-size:15px}.sm-planes button small{font-size:11px;opacity:.75}.sm-planes button.on{background:#1e6bff;color:#fff}.sm-stunts{display:flex;gap:8px;margin-top:10px}.sm-stunts span{flex:1;text-align:center;padding:6px 0;border-radius:10px;background:#0f1a3d;color:#8ea0c9;font-size:12px;font-weight:800}.sm-stunts span.on{background:#14532d;color:#bbf7d0}.hf-st{float:right;font-size:12px;font-weight:800;color:#9fb0da}.hf-st.on{color:#ffd84a}.hf-queue{min-height:46px;border:0;border-radius:14px;font-weight:800;font-size:15px;background:#1e6bff;color:#fff}.hf-queue.on{background:#7c2d12}.hf-queue:disabled{opacity:.5}.hf-hint{display:block;color:#8ea0c9;font-size:11px;margin-top:6px}.hf-tw{display:flex;justify-content:space-between;font-size:13px;padding:4px 0}.hf-tw b{color:#4ade80}";
    document.head.appendChild(st);
  }
  function paintHF(root) {
    var on = isHF(), p = $(root, "#hf-panel"), s2 = $(root, "#hf-stats"); if (!p) return;
    p.hidden = !on; s2.hidden = !on;
    var lbl = root.querySelector("[data-a]"); lbl = lbl && lbl.closest(".av-bet-col") && lbl.closest(".av-bet-col").querySelector("label"); if (lbl) lbl.textContent = on ? "Auto cash-out" : "Auto Cashout";
    if (!on) { S.queued = false; return; }
    var live = S.busy && !S.stopped, st = $(root, "#hf-bstate"), q = $(root, "#hf-queue");
    st.textContent = S.queued ? "waiting" : "not set"; st.classList.toggle("on", S.queued);
    $(root, "#hf-bstake").disabled = S.queued; root.querySelectorAll("[data-b]").forEach(function (b) { b.disabled = S.queued; });
    q.textContent = S.queued ? "Cancel Bet B" : "Bet next"; q.classList.toggle("on", S.queued); q.disabled = !S.queued && !live;
    $(root, "#hf-hint").textContent = S.queued ? "Bet B " + money(S.bStake) + " ETB በቀጣዩ ዙር ይጀምራል (አንድ ጊዜ ብቻ)።" : (live ? "Bet A እየበረረ ነው፤ Bet B ለቀጣዩ ዙር ያዘጋጁ።" : "Bet A ሲጀምር Bet B ለቀጣዩ ዙር ማዘጋጀት ይችላሉ።");
    var today = new Date().toISOString().slice(0, 10), best = 0;
    S.items.forEach(function (it) { if (it.created_at.slice(0, 10) === today && it.stake > 0 && it.payout > 0) best = Math.max(best, it.payout / it.stake); });
    $(root, "#hf-best").textContent = best > 0 ? "x" + best.toFixed(2) : "—";
    var top = S.items.filter(function (it) { return it.payout > 0; }).sort(function (a, b) { return b.payout - a.payout; }).slice(0, 3);
    $(root, "#hf-top").innerHTML = top.length ? top.map(function (it) { return '<div class="hf-tw"><span>x' + (it.payout / it.stake).toFixed(2) + "</span><span>" + money(it.stake) + "</span><b>" + money(it.payout) + "</b></div>"; }).join("") : '<div class="av-none">ገና አሸናፊ ውርርድ የለም</div>';
  }

  function draw(root, mult, crashed) {
    var cv = $(root, "#av-cv"); if (!cv) return;
    var ctx = cv.getContext("2d"), w = cv.width, h = cv.height;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(120,150,220,.12)"; ctx.lineWidth = 1;
    for (var i = 1; i < 5; i++) { ctx.beginPath(); ctx.moveTo(0, h * i / 5); ctx.lineTo(w, h * i / 5); ctx.stroke(); }
    var frac = Math.min(1, Math.log(Math.max(1, mult)) / Math.log(100));
    var pts = 40, x0 = 6, y0 = h - 14, ex = x0 + (w - 90) * (0.12 + 0.88 * Math.sqrt(frac)), ey = y0 - (h - 80) * frac;
    var px = [], py = [];
    for (var k = 0; k <= pts; k++) { var t = k / pts; px.push(x0 + (ex - x0) * t); py.push(y0 - (y0 - ey) * Math.pow(t, 2.2)); }
    var grad = ctx.createLinearGradient(0, ey, 0, y0); grad.addColorStop(0, "rgba(255,59,92,.30)"); grad.addColorStop(1, "rgba(255,59,92,0)");
    ctx.beginPath(); ctx.moveTo(px[0], py[0]); for (k = 1; k <= pts; k++) ctx.lineTo(px[k], py[k]); ctx.lineTo(ex, y0); ctx.lineTo(x0, y0); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath(); ctx.moveTo(px[0], py[0]); for (k = 1; k <= pts; k++) ctx.lineTo(px[k], py[k]);
    ctx.strokeStyle = crashed ? "#8a93b8" : "#ff3b5c"; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.stroke();
    var ang = Math.atan2(py[pts] - py[pts - 2], px[pts] - px[pts - 2]);
    ctx.save(); ctx.translate(ex, ey); ctx.rotate(crashed ? 0.9 : ang);
    ctx.fillStyle = crashed ? "#6b7391" : "#ff4d6d"; ctx.beginPath(); ctx.moveTo(22, 0); ctx.lineTo(-14, -9); ctx.lineTo(-8, 0); ctx.lineTo(-14, 9); ctx.closePath(); ctx.fill();
    ctx.fillStyle = crashed ? "#555c78" : "#d9304f"; ctx.beginPath(); ctx.moveTo(-2, 0); ctx.lineTo(-16, -17); ctx.lineTo(-10, 0); ctx.closePath(); ctx.fill();
    ctx.restore();
    $(root, "#av-barfill").style.width = Math.round(frac * 100) + "%";
  }

  function cashLabel() { return isSM() ? "Land & Cash Out" : "Cash Out"; }
  function runBet(root) { return go(root); }   // go() shadows its own name with a local button variable, so Bet B starts through this alias

  async function go(root) {
    if (S.busy) return;
    var msg = $(root, "#av-msg"), proof = $(root, "#av-proof");
    var stake = Number($(root, "#aviator-stake").value);
    if (!(stake > 0)) { msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; return; }
    if (stake < S.min || stake > S.max) { msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"; return; }
    S.busy = true; S.stopped = false; msg.textContent = ""; proof.textContent = "";
    var body = { stake: stake }; if (S.auto != null) body.auto_cashout = S.auto;
    var go = $(root, "#av-go"), stage = $(root, "#av-stage"), multEl = $(root, "#av-mult"), stEl = $(root, "#av-state");
    paint(root); go.disabled = true; go.textContent = "…";
    var r;
    try { r = await startRealtimeRound(KEY, body); }
    catch (e) { S.busy = false; S.stopped = true; paint(root); msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; return; }
    proof.textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || r.commitment || "").slice(0, 16) + "…";
    stage.classList.remove("crashed", "won"); stage.classList.add("fly"); stEl.textContent = "FLYING";
    go.className = "av-go cash"; go.disabled = false; go.innerHTML = cashLabel() + "<small>" + money(stake) + " ETB</small>"; S.live = 1;
    var result = null, cashing = false, curMult = 1;
    var finish = function (rr) { result = rr; };
    go.onclick = async function () {
      if (cashing || S.stopped) return; cashing = true; go.disabled = true; hap("medium");
      try { finish(await realtimeAction(KEY, "cashout")); } catch (e) { msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; finish(null); }
    };
    while (!result && !S.stopped) {
      try {
        var st = await realtimeState(KEY);
        curMult = Number(st.live_multiplier || 1);
        multEl.textContent = curMult.toFixed(2) + "x"; draw(root, curMult, false);
        S.live = curMult; paintSM(root);
        if (!cashing) go.innerHTML = cashLabel() + "<small>" + money(stake * curMult) + " ETB</small>";
        if (st.phase === "CRASHED" || st.status === "WON" || st.status === "LOST") {
          S.stopped = true;
          try { result = await realtimeAction(KEY, "cashout"); } catch (_) { result = null; }
          break;
        }
      } catch (_) {}
      await new Promise(function (res) { setTimeout(res, 220); });
    }
    while (!result && cashing) await new Promise(function (res) { setTimeout(res, 80); });
    S.stopped = true; go.onclick = null; stage.classList.remove("fly");
    var o = (result && result.outcome) || {}, crash = Number(o.crash || (result && result.crash) || 0), pay = Number((result && result.payout) || 0);
    var won = !!(result && result.won);
    if (crash >= 1) { S.hist.unshift(Math.round(crash * 100) / 100); S.hist = S.hist.slice(0, 20); }
    S.bets.unshift({ stake: stake, payout: pay, mult: won ? pay / stake : 0 }); S.bets = S.bets.slice(0, 20);
    S.items.unshift({ created_at: new Date().toISOString().replace("T", " ").slice(0, 19), stake: stake, payout: pay }); S.items = S.items.slice(0, 100);
    if (won) {
      stage.classList.add("won"); stEl.textContent = "CASHED OUT"; multEl.textContent = (pay / stake).toFixed(2) + "x";
      msg.className = "kx-msg win"; msg.textContent = "🎉 አሸንፈዋል +" + money(pay - stake) + " ብር"; hap("success");
    } else {
      stage.classList.add("crashed"); stEl.textContent = "CRASHED"; if (crash >= 1) multEl.textContent = crash.toFixed(2) + "x"; draw(root, crash >= 1 ? crash : curMult, true);
      msg.className = "kx-msg lose"; msg.textContent = "💥 ተከስክሷል -" + money(stake) + " ብር"; hap("error");
    }
    if (result && result.server_seed) proof.textContent = "ROUND " + (result.round_code || r.round_code || "") + " · SERVER SEED " + String(result.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    S.busy = false; paint(root);
    if (S.queued) {   // Bet B was queued by the player for the next round: start it once, with the stake they set
      S.queued = false; paint(root);
      if (isHF() && document.body.contains(root)) setTimeout(function () {
        if (S.busy || !isHF() || !document.body.contains(root)) return;
        if (S.restoreStake == null) S.restoreStake = Number($(root, "#aviator-stake").value) || S.stake;
        $(root, "#aviator-stake").value = S.bStake; paint(root); runBet(root);
      }, 1800);
    } else if (S.restoreStake != null) { $(root, "#aviator-stake").value = S.restoreStake; S.restoreStake = null; paint(root); }   // Bet A's own stake comes back after Bet B has run
  }
})();
