/* JET LIVE: ONE plane for ALL players, a new round every 60 s (15 s betting, then the shared flight).
   Server (live_engine_v1.py) owns the clock, the hidden crash point, cash-out and settlement.
   This file only draws /api/live/higjtlyer/crash-state and sends bet / cash-out. Wraps window.setupJet ONLY for the jet game. */
(function () {
  "use strict";
  var GK = "jet", orig = window.setupJet;
  var S = { st: null, off: 0, at: 0, timer: null, raf: 0, root: null, busy: {}, queue: { A: false, B: false }, stake: { A: 50, B: 20 }, autoOn: true, auto: 10, trail: [], seenDraw: 0, shown: {} };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var $ = function (s) { return S.root && S.root.querySelector(s); };

  function css() {
    if (document.getElementById("jtl-css")) return;
    var s = document.createElement("style"); s.id = "jtl-css";
    s.textContent = ".jtl{display:flex;flex-direction:column;gap:12px;color:#fff}.jtl-top{display:flex;justify-content:space-between;color:#a7f3d0;font-size:13px}.jtl-top b{color:#facc15}" +
      ".jtl-stage{position:relative;height:300px;border-radius:24px;overflow:hidden;border:1.5px solid #1f8a5b;background:linear-gradient(#052e1c,#0b5d3b 45%,#16a34a)}" +
      ".jtl-stage.crashed{background:linear-gradient(#2b1620,#5b1f2c 55%,#9f3a3a)}" +
      ".jtl-mult{position:absolute;left:16px;top:10px;font-size:62px;font-weight:900;line-height:1;text-shadow:0 4px 18px #0006}" +
      ".jtl-sub{position:absolute;left:18px;top:84px;letter-spacing:.3em;font-weight:800;font-size:13px;color:#d1fae5}" +
      ".jtl-chips{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:6px;align-items:flex-end}.jtl-chips span{background:#14532d;border-radius:14px;padding:3px 12px;font-weight:800;font-size:14px}.jtl-chips span.b{color:#fda4af}.jtl-chips span.v{color:#a7f3d0}" +
      ".jtl-svg{position:absolute;inset:0;width:100%;height:100%}.jtl-plane{position:absolute;width:74px;height:34px;transform:translate(-50%,-50%) rotate(-22deg);transition:left .12s linear,bottom .12s linear;font-size:40px;line-height:34px;text-align:center}" +
      ".jtl-cd{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;background:#02140d66;text-align:center}" +
      ".jtl-bets{display:flex;gap:10px}.jtl-b{flex:1;background:#0f2a20;border:1.5px solid #1f8a5b;border-radius:20px;padding:10px}.jtl-bh{display:flex;justify-content:space-between;font-size:13px;color:#a7f3d0}.jtl-bh em{font-style:normal;color:#4ade80}" +
      ".jtl-in{display:flex;align-items:center;background:#06150f;border:1px solid #1f8a5b;border-radius:14px;margin:8px 0;padding:3px}.jtl-in button{width:36px;height:40px;border:0;border-radius:10px;background:#14532d;color:#fff;font-size:20px}.jtl-in input{flex:1;min-width:0;text-align:center;background:transparent;border:0;color:#fff;font-size:19px;font-weight:800}" +
      ".jtl-go{width:100%;height:50px;border:0;border-radius:15px;font-weight:900;font-size:16px;background:linear-gradient(#4ade80,#22c55e);color:#04200f}.jtl-go.cash{background:linear-gradient(#fde047,#f59e0b);color:#3a2a00}.jtl-go.wait{background:#14532d;color:#a7f3d0}.jtl-go:disabled{opacity:.55}" +
      ".jtl-card{background:#0f2a20;border:1.5px solid #1f8a5b;border-radius:20px;padding:12px}.jtl-ac{display:flex;justify-content:space-between;align-items:center}.jtl-ac small{color:#a7f3d0}.jtl-ac .in{display:flex;align-items:center;gap:6px}.jtl-ac input[type=text]{width:90px;background:#06150f;border:1px solid #1f8a5b;border-radius:12px;color:#fff;font-size:20px;font-weight:900;text-align:center;padding:6px}" +
      ".jtl-sw{width:56px;height:30px;border-radius:16px;background:#2f4a3d;border:0;position:relative}.jtl-sw.on{background:#2563eb}.jtl-sw i{position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;background:#fff;transition:left .15s}.jtl-sw.on i{left:29px}" +
      ".jtl-tw{display:flex;justify-content:space-between;padding:5px 0;font-weight:700}.jtl-tw .m{color:#facc15}.jtl-tw .p{color:#4ade80}.jtl-msg{min-height:20px;text-align:center;font-weight:800}.jtl-msg.win{color:#facc15}.jtl-msg.lose{color:#fca5a5}.jtl-msg.bad{color:#fdba74}.jtl-note{color:#6ee7b7;font-size:11px}";
    document.head.appendChild(s);
  }

  window.setupJet = async function () {
    var skin = typeof window.kdmSkinKey === "function" ? window.kdmSkinKey() : null;
    if (!(skin === null || skin === "jet")) { stop(); return orig && orig.apply(this, arguments); }
    var root = document.getElementById("jet-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById("jet" + s); if (e) e.style.display = "none"; });
    css(); S.root = root;
    if (root.dataset.jtl !== "1") {
      root.dataset.jtl = "1"; root.dataset.built = "1";
      var slot = function (k) { return '<div class="jtl-b" id="jtl-b' + k + '"><div class="jtl-bh"><span>Bet ' + k + '</span><em id="jtl-s' + k + '">waiting</em></div><div class="jtl-in"><button type="button" data-k="' + k + '" data-d="-1">−</button><input id="jtl-i' + k + '" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake[k] + '"><button type="button" data-k="' + k + '" data-d="1">+</button></div><button type="button" class="jtl-go" id="jtl-g' + k + '" data-k="' + k + '">Bet</button></div>'; };
      root.innerHTML = '<div class="jtl"><div class="jtl-top"><span id="jtl-pl">LIVE · Round #—</span><span>Best today <b id="jtl-best">—</b></span></div>' +
        '<div class="jtl-stage" id="jtl-stage"><svg class="jtl-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline id="jtl-trail" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.2" stroke-dasharray="1.2 2.4" stroke-linecap="round" vector-effect="non-scaling-stroke" points=""/></svg>' +
        '<div class="jtl-mult" id="jtl-mult">1.00x</div><div class="jtl-sub" id="jtl-sub">CONNECTING</div><div class="jtl-chips" id="jtl-chips"></div><div class="jtl-plane" id="jtl-plane">🚀</div><div class="jtl-cd" id="jtl-cd" hidden></div></div>' +
        '<div class="jtl-bets">' + slot("A") + slot("B") + '</div>' +
        '<div class="jtl-card jtl-ac"><div><small>Auto cash-out</small><div class="in"><input id="jtl-auto" type="text" inputmode="decimal" value="x' + S.auto.toFixed(2) + '"></div></div><button type="button" class="jtl-sw on" id="jtl-sw"><i></i></button></div>' +
        '<div class="jtl-msg" id="jtl-msg" aria-live="polite"></div>' +
        '<div class="jtl-card"><div class="jtl-bh"><b style="color:#a7f3d0">Top wins</b><small id="jtl-pc"></small></div><div id="jtl-top"><div class="jtl-note">…</div></div></div>' +
        '<small class="jtl-note">ሁሉም ተጫዋች አንድ Jet ነው የሚያየው። ሰርቨሩ የመከስከሻውን ነጥብ ከመከስከሱ በፊት ይደብቃል፤ ከመከስከሱ በፊት Cash ሲጫኑ ብቻ ያሸንፋሉ።</small></div>';
      root.querySelectorAll(".jtl-in button").forEach(function (b) { b.addEventListener("click", function () { var k = b.dataset.k, i = $("#jtl-i" + k), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000; i.value = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); hap("light"); }); });
      root.querySelectorAll(".jtl-go").forEach(function (b) { b.addEventListener("click", function () { press(b.dataset.k); }); });
      $("#jtl-sw").addEventListener("click", function () { S.autoOn = !S.autoOn; this.classList.toggle("on", S.autoOn); hap("light"); });
      $("#jtl-auto").addEventListener("change", function () { var v = parseFloat(String(this.value).replace(/[^0-9.]/g, "")); S.auto = isFinite(v) ? Math.max(1.01, Math.min(100, v)) : 2; this.value = "x" + S.auto.toFixed(2); });
    }
    start();
  };

  function say(c, t) { var e = $("#jtl-msg"); if (e) { e.className = "jtl-msg " + c; e.textContent = t; } }
  function autoVal() { return S.autoOn ? Math.round(S.auto * 100) / 100 : null; }
  function curMult() {
    var st = S.st; if (!st) return 1;
    if (st.phase === "CRASHED") return st.crash || 1;
    if (st.phase !== "FLYING") return 1;
    var t = (Date.now() + S.off) / 1000 - st.flight_start; return Math.max(1, Math.floor(Math.exp(st.k * Math.max(0, t)) * 100) / 100);
  }

  async function place(k) {
    if (S.busy[k]) return false; S.busy[k] = true;
    try {
      var stake = Number($("#jtl-i" + k).value);
      var body = { slot: k, stake: stake }; var a = autoVal(); if (a) body.auto = a;
      await apiFetch("/live/" + GK + "/crash-bet", { method: "POST", json: body });
      S.stake[k] = stake; hap("success"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
      S.busy[k] = false; poll(); return true;
    } catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); S.busy[k] = false; return false; }
  }
  async function press(k) {
    var st = S.st; if (!st) return; var my = st.my[k], mine = my && my.round_no === st.draw_no && my.status === "PENDING";
    if (mine && st.phase === "FLYING") {
      if (S.busy[k]) return; S.busy[k] = true;
      try { var r = await apiFetch("/live/" + GK + "/cashout", { method: "POST", json: { slot: k } }); hap("success"); say("win", "💰 Bet " + k + " · x" + r.multiplier.toFixed(2) + " · +" + money(r.payout - 0) + " ETB"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {} }
      catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); }
      S.busy[k] = false; poll(); return;
    }
    if (st.phase === "BETTING" && !(my && my.round_no === st.draw_no)) { await place(k); return; }
    if (!(my && my.round_no === st.draw_no)) { S.queue[k] = !S.queue[k]; hap("light"); render(); }   // "Bet next": queue for the next round
  }

  function start() { stop(); poll(); S.timer = setInterval(poll, 450); S.raf = requestAnimationFrame(frame); }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0; } }
  function visible() { return S.root && S.root.isConnected && S.root.offsetParent !== null && !document.hidden; }
  async function poll() {
    if (!visible()) return;
    try { var st = await apiFetch("/live/" + GK + "/crash-state"); S.off = st.server_time * 1000 - Date.now(); S.st = st; S.at = Date.now(); onState(); }
    catch (e) { var sb = $("#jtl-sub"); if (sb) sb.textContent = "RECONNECTING"; }
  }
  function onState() {
    var st = S.st;
    if (st.draw_no !== S.seenDraw) { S.seenDraw = st.draw_no; S.trail = []; }
    if (st.phase === "BETTING") ["A", "B"].forEach(function (k) {   // queued "Bet next" fires as soon as betting opens
      var my = st.my[k]; if (S.queue[k] && !(my && my.round_no === st.draw_no) && st.seconds_left > 2) { S.queue[k] = false; place(k); }
    });
    ["A", "B"].forEach(function (k) {   // settled result of my bet, once
      var my = st.my[k]; if (!my || my.status === "PENDING") return; var id = k + ":" + my.round_no; if (S.shown[id]) return; S.shown[id] = 1;
      if (Number(my.payout) > 0) { say("win", "🎉 Bet " + k + " · x" + Number(my.mult).toFixed(2) + " · +" + money(my.payout - my.stake) + " ETB"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else say("lose", "😕 Bet " + k + " · crashed · -" + money(my.stake) + " ETB");
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    });
    render();
  }

  function frame() {
    S.raf = requestAnimationFrame(frame);
    if (!visible() || !S.st) return;
    var st = S.st, m = curMult(), stage = $("#jtl-stage"); if (!stage) return;
    $("#jtl-mult").textContent = m.toFixed(2) + "x";
    var prog = Math.min(1, Math.log(Math.max(1, m)) / Math.log(30)), x = 10 + 76 * prog, y = 10 + 62 * Math.pow(prog, 0.8);
    var pl = $("#jtl-plane"); pl.style.left = x + "%"; pl.style.bottom = y + "%"; pl.style.top = "auto"; pl.style.transform = "translate(-50%,50%) rotate(" + (st.phase === "CRASHED" ? 40 : -22) + "deg)"; pl.style.opacity = st.phase === "CRASHED" ? 0.5 : 1;
    if (st.phase === "FLYING") { S.trail.push(x.toFixed(1) + "," + (100 - y).toFixed(1)); if (S.trail.length > 400) S.trail.shift(); $("#jtl-trail").setAttribute("points", S.trail.join(" ")); }
    else if (st.phase === "BETTING") { $("#jtl-trail").setAttribute("points", ""); }
    var left = Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000), cd = $("#jtl-cd");
    cd.hidden = st.phase !== "BETTING"; if (!cd.hidden) cd.innerHTML = "BETTING OPEN<br><span style='font-size:44px'>" + Math.ceil(left) + "</span>";
    // my cash buttons follow the live multiplier
    ["A", "B"].forEach(function (k) { var my = st.my[k]; if (st.phase === "FLYING" && my && my.round_no === st.draw_no && my.status === "PENDING") { var b = $("#jtl-g" + k); b.textContent = "Cash " + money(my.stake * m); } });
  }

  function render() {
    var st = S.st; if (!st) return;
    var stage = $("#jtl-stage"); stage.classList.toggle("crashed", st.phase === "CRASHED");
    $("#jtl-sub").textContent = st.phase === "BETTING" ? "WAITING" : st.phase === "FLYING" ? "CRUISING" : "FLEW AWAY";
    $("#jtl-pl").textContent = "LIVE · Round #" + st.draw_no + " · " + st.players + " players";
    $("#jtl-best").textContent = "x" + Number(st.best_today).toFixed(2);
    $("#jtl-chips").innerHTML = (st.last || []).slice(0, 3).map(function (v) { return '<span class="' + (v >= 10 ? "b" : v >= 2 ? "v" : "") + '">' + v.toFixed(2) + "x</span>"; }).join("");
    $("#jtl-pc").textContent = money(st.total_staked) + " ETB in this round";
    $("#jtl-top").innerHTML = (st.top || []).length ? st.top.map(function (r) { return '<div class="jtl-tw"><span>' + r.name + '</span><span class="m">x' + Number(r.mult).toFixed(2) + '</span><span class="p">' + Number(r.payout).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "</span></div>"; }).join("") : '<div class="jtl-note">ገና አሸናፊ የለም</div>';
    ["A", "B"].forEach(function (k) {
      var my = st.my[k], cur = my && my.round_no === st.draw_no, b = $("#jtl-g" + k), s = $("#jtl-s" + k);
      b.classList.remove("cash", "wait");
      if (cur && my.status === "PENDING") {
        s.textContent = st.phase === "FLYING" ? "in flight" : "bet placed";
        if (st.phase === "FLYING") { b.classList.add("cash"); b.disabled = false; } else { b.textContent = "Bet placed ✓"; b.disabled = true; }
      } else if (cur) { s.textContent = my.status === "WON" ? "won x" + Number(my.mult).toFixed(2) : "lost"; b.textContent = my.status === "WON" ? "+" + money(my.payout) : "Crashed"; b.disabled = true; }
      else if (st.phase === "BETTING" && st.seconds_left > 1.5) { s.textContent = S.queue[k] ? "queued" : "waiting"; b.textContent = "Bet"; b.disabled = false; }
      else { s.textContent = S.queue[k] ? "queued" : "waiting"; b.classList.add("wait"); b.textContent = S.queue[k] ? "Queued ✓ (tap to cancel)" : "Bet next"; b.disabled = false; }
    });
  }
  window.addEventListener("pagehide", stop);
})();
