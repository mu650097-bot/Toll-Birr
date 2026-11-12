/* AVIATOR LIVE: ONE plane for ALL players, a new round every 60 s (15 s betting, then the shared flight). Server: live_engine_v1.py (game key "aviator").
   Used by the plain Aviator tile and the "Crash" tile. Replaces window.setupAviator for those skins only. */
(function () {
  "use strict";
  var GK = "aviator", orig = window.setupAviator;
  var S = { st: null, off: 0, at: 0, timer: null, raf: 0, root: null, busy: {}, queue: { A: false, B: false }, stake: { A: 50, B: 20 }, autoOn: true, auto: 10, trail: [], seenDraw: 0, shown: {} };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var $ = function (s) { return S.root && S.root.querySelector(s); };

  function css() {
    if (document.getElementById("avl-css")) return;
    var s = document.createElement("style"); s.id = "avl-css";
    s.textContent = ".avl{display:flex;flex-direction:column;gap:12px;color:#fff}.avl-top{display:flex;justify-content:space-between;color:#c4b5fd;font-size:13px}.avl-top b{color:#facc15}" +
      ".avl-stage{position:relative;height:300px;border-radius:24px;overflow:hidden;border:1.5px solid #5b3fd1;background:linear-gradient(#4c2fb3,#8b46c9 45%,#fb9d6b)}" +
      ".avl-stage.crashed{background:linear-gradient(#3b1d5a,#6b2d5c 55%,#b45a4a)}" +
      ".avl-mult{position:absolute;left:16px;top:10px;font-size:62px;font-weight:900;line-height:1;text-shadow:0 4px 18px #0006}" +
      ".avl-sub{position:absolute;left:18px;top:84px;letter-spacing:.3em;font-weight:800;font-size:13px;color:#e9d5ff}" +
      ".avl-chips{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:6px;align-items:flex-end}.avl-chips span{background:#2a1670;border-radius:14px;padding:3px 12px;font-weight:800;font-size:14px}.avl-chips span.b{color:#f9a8d4}.avl-chips span.v{color:#c4b5fd}" +
      ".avl-svg{position:absolute;inset:0;width:100%;height:100%}.avl-plane{position:absolute;width:74px;height:34px;transform:translate(-50%,-50%) rotate(-22deg);transition:left .12s linear,bottom .12s linear;font-size:40px;line-height:34px;text-align:center}" +
      ".avl-cd{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;background:#1a0f4a66;text-align:center}" +
      ".avl-bets{display:flex;gap:10px}.avl-b{flex:1;background:#1b1448;border:1.5px solid #5b3fd1;border-radius:20px;padding:10px}.avl-bh{display:flex;justify-content:space-between;font-size:13px;color:#c4b5fd}.avl-bh em{font-style:normal;color:#4ade80}" +
      ".avl-in{display:flex;align-items:center;background:#0f0a33;border:1px solid #5b3fd1;border-radius:14px;margin:8px 0;padding:3px}.avl-in button{width:36px;height:40px;border:0;border-radius:10px;background:#2a1670;color:#fff;font-size:20px}.avl-in input{flex:1;min-width:0;text-align:center;background:transparent;border:0;color:#fff;font-size:19px;font-weight:800}" +
      ".avl-go{width:100%;height:50px;border:0;border-radius:15px;font-weight:900;font-size:16px;background:linear-gradient(#4ade80,#22c55e);color:#04200f}.avl-go.cash{background:linear-gradient(#fde047,#f59e0b);color:#3a2a00}.avl-go.wait{background:#2a1670;color:#c4b5fd}.avl-go:disabled{opacity:.55}" +
      ".avl-card{background:#1b1448;border:1.5px solid #5b3fd1;border-radius:20px;padding:12px}.avl-ac{display:flex;justify-content:space-between;align-items:center}.avl-ac small{color:#c4b5fd}.avl-ac .in{display:flex;align-items:center;gap:6px}.avl-ac input[type=text]{width:90px;background:#0f0a33;border:1px solid #5b3fd1;border-radius:12px;color:#fff;font-size:20px;font-weight:900;text-align:center;padding:6px}" +
      ".avl-sw{width:56px;height:30px;border-radius:16px;background:#3b3566;border:0;position:relative}.avl-sw.on{background:#2563eb}.avl-sw i{position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;background:#fff;transition:left .15s}.avl-sw.on i{left:29px}" +
      ".avl-tw{display:flex;justify-content:space-between;padding:5px 0;font-weight:700}.avl-tw .m{color:#facc15}.avl-tw .p{color:#4ade80}.avl-msg{min-height:20px;text-align:center;font-weight:800}.avl-msg.win{color:#facc15}.avl-msg.lose{color:#fca5a5}.avl-msg.bad{color:#fdba74}.avl-note{color:#a78bfa;font-size:11px}";
    document.head.appendChild(s);
  }

  window.setupAviator = async function () {
    var skin = typeof window.kdmSkinKey === "function" ? window.kdmSkinKey() : null;
    if (!(skin === null || skin === "crash" || skin === "aviator")) { stop(); return orig && orig.apply(this, arguments); }
    var root = document.getElementById("aviator-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById("aviator" + s); if (e) e.style.display = "none"; });
    css(); S.root = root;
    if ((root.dataset.avl !== "1" || root.dataset.lk !== GK)) {
      root.dataset.avl = "1"; root.dataset.built = "1"; root.dataset.lk = GK;
      var slot = function (k) { return '<div class="avl-b" id="avl-b' + k + '"><div class="avl-bh"><span>Bet ' + k + '</span><em id="avl-s' + k + '">waiting</em></div><div class="avl-in"><button type="button" data-k="' + k + '" data-d="-1">−</button><input id="avl-i' + k + '" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake[k] + '"><button type="button" data-k="' + k + '" data-d="1">+</button></div><button type="button" class="avl-go" id="avl-g' + k + '" data-k="' + k + '">Bet</button></div>'; };
      root.innerHTML = '<div class="avl"><div class="avl-top"><span id="avl-pl">LIVE · Round #—</span><span>Best today <b id="avl-best">—</b></span></div>' +
        '<div class="avl-stage" id="avl-stage"><svg class="avl-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline id="avl-trail" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.2" stroke-dasharray="1.2 2.4" stroke-linecap="round" vector-effect="non-scaling-stroke" points=""/></svg>' +
        '<div class="avl-mult" id="avl-mult">1.00x</div><div class="avl-sub" id="avl-sub">CONNECTING</div><div class="avl-chips" id="avl-chips"></div><div class="avl-plane" id="avl-plane">✈️</div><div class="avl-cd" id="avl-cd" hidden></div></div>' +
        '<div class="avl-bets">' + slot("A") + slot("B") + '</div>' +
        '<div class="avl-card avl-ac"><div><small>Auto cash-out</small><div class="in"><input id="avl-auto" type="text" inputmode="decimal" value="x' + S.auto.toFixed(2) + '"></div></div><button type="button" class="avl-sw on" id="avl-sw"><i></i></button></div>' +
        '<div class="avl-msg" id="avl-msg" aria-live="polite"></div>' +
        '<div class="avl-card"><div class="avl-bh"><b style="color:#c4b5fd">Top wins</b><small id="avl-pc"></small></div><div id="avl-top"><div class="avl-note">…</div></div></div>' +
        '<small class="avl-note">ሁሉም ተጫዋች አንድ አይሮፕላን ነው የሚያየው። ሰርቨሩ የመከስከሻውን ነጥብ ከመከስከሱ በፊት ይደብቃል፤ ከመከስከሱ በፊት Cash ሲጫኑ ብቻ ያሸንፋሉ።</small></div>';
      root.querySelectorAll(".avl-in button").forEach(function (b) { b.addEventListener("click", function () { var k = b.dataset.k, i = $("#avl-i" + k), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000; i.value = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); hap("light"); }); });
      root.querySelectorAll(".avl-go").forEach(function (b) { b.addEventListener("click", function () { press(b.dataset.k); }); });
      $("#avl-sw").addEventListener("click", function () { S.autoOn = !S.autoOn; this.classList.toggle("on", S.autoOn); hap("light"); });
      $("#avl-auto").addEventListener("change", function () { var v = parseFloat(String(this.value).replace(/[^0-9.]/g, "")); S.auto = isFinite(v) ? Math.max(1.01, Math.min(100, v)) : 2; this.value = "x" + S.auto.toFixed(2); });
    }
    start();
  };

  function say(c, t) { var e = $("#avl-msg"); if (e) { e.className = "avl-msg " + c; e.textContent = t; } }
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
      var stake = Number($("#avl-i" + k).value);
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
    catch (e) { var sb = $("#avl-sub"); if (sb) sb.textContent = "RECONNECTING"; }
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
    var st = S.st, m = curMult(), stage = $("#avl-stage"); if (!stage) return;
    $("#avl-mult").textContent = m.toFixed(2) + "x";
    var prog = Math.min(1, Math.log(Math.max(1, m)) / Math.log(30)), x = 10 + 76 * prog, y = 10 + 62 * Math.pow(prog, 0.8);
    var pl = $("#avl-plane"); pl.style.left = x + "%"; pl.style.bottom = y + "%"; pl.style.top = "auto"; pl.style.transform = "translate(-50%,50%) rotate(" + (st.phase === "CRASHED" ? 40 : -22) + "deg)"; pl.style.opacity = st.phase === "CRASHED" ? 0.5 : 1;
    if (st.phase === "FLYING") { S.trail.push(x.toFixed(1) + "," + (100 - y).toFixed(1)); if (S.trail.length > 400) S.trail.shift(); $("#avl-trail").setAttribute("points", S.trail.join(" ")); }
    else if (st.phase === "BETTING") { $("#avl-trail").setAttribute("points", ""); }
    var left = Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000), cd = $("#avl-cd");
    cd.hidden = st.phase !== "BETTING"; if (!cd.hidden) cd.innerHTML = "BETTING OPEN<br><span style='font-size:44px'>" + Math.ceil(left) + "</span>";
    // my cash buttons follow the live multiplier
    ["A", "B"].forEach(function (k) { var my = st.my[k]; if (st.phase === "FLYING" && my && my.round_no === st.draw_no && my.status === "PENDING") { var b = $("#avl-g" + k); b.textContent = "Cash " + money(my.stake * m); } });
  }

  function render() {
    var st = S.st; if (!st) return;
    var stage = $("#avl-stage"); stage.classList.toggle("crashed", st.phase === "CRASHED");
    $("#avl-sub").textContent = st.phase === "BETTING" ? "WAITING" : st.phase === "FLYING" ? "CRUISING" : "FLEW AWAY";
    $("#avl-pl").textContent = "LIVE · Round #" + st.draw_no + " · " + st.players + " players";
    $("#avl-best").textContent = "x" + Number(st.best_today).toFixed(2);
    $("#avl-chips").innerHTML = (st.last || []).slice(0, 3).map(function (v) { return '<span class="' + (v >= 10 ? "b" : v >= 2 ? "v" : "") + '">' + v.toFixed(2) + "x</span>"; }).join("");
    $("#avl-pc").textContent = money(st.total_staked) + " ETB in this round";
    $("#avl-top").innerHTML = (st.top || []).length ? st.top.map(function (r) { return '<div class="avl-tw"><span>' + r.name + '</span><span class="m">x' + Number(r.mult).toFixed(2) + '</span><span class="p">' + Number(r.payout).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "</span></div>"; }).join("") : '<div class="avl-note">ገና አሸናፊ የለም</div>';
    ["A", "B"].forEach(function (k) {
      var my = st.my[k], cur = my && my.round_no === st.draw_no, b = $("#avl-g" + k), s = $("#avl-s" + k);
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
