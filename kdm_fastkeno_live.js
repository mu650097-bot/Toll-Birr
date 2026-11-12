/* FAST KENO FAMILY LIVE (Fast / Power / Insta Keno): one global draw every 60 s per game for ALL players. 40 numbers, 10 balls, pick 1-8.
   Server (live_engine_v1.py) owns the clock, the draw and the payout. This file only shows what /api/live40/<game>/state says.
   Replaces window.setupFastKeno for fastkeno / keno_power / keno_insta; Super Keno has its own live file. */
(function () {
  "use strict";
  var KEYS = ["fastkeno", "keno_power", "keno_insta"], GK = "fastkeno", orig = window.setupFastKeno;
  var BALLC = ["#facc15", "#3b82f6", "#ef4444", "#a855f7", "#f97316", "#14b8a6", "#ec4899", "#84cc16"];
  var S = { sel: [], stake: 50, st: null, off: 0, timer: null, root: null, busy: false, lastNo: 0, sound: null };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var $ = function (s) { return S.root && S.root.querySelector(s); };

  function css() {
    if (document.getElementById("fkl-css")) return;
    var s = document.createElement("style"); s.id = "fkl-css";
    s.textContent = ".fkl{display:flex;flex-direction:column;gap:12px}.fkl-m{background:#0b2a17;border:1.5px solid #1f6b3c;border-radius:22px;padding:12px}" +
      ".fkl-h{display:flex;justify-content:space-between;align-items:center;color:#9fd9b4;font-size:13px}.fkl-h b{color:#fff;font-size:15px}" +
      ".fkl-pill{background:#06180d;border-radius:14px;padding:4px 10px;color:#e8fff0;font-weight:700}" +
      ".fkl-cd{text-align:center;margin:10px 0 6px}.fkl-cd b{font-size:42px;color:#4ade80;line-height:1}.fkl-cd small{display:block;color:#9fd9b4;letter-spacing:.12em;font-size:11px;margin-top:2px}" +
      ".fkl-meter{height:12px;border-radius:8px;background:#06180d;overflow:hidden;margin-top:8px;border:1px solid #1f6b3c}.fkl-meter i{display:block;height:100%;width:0;background:linear-gradient(90deg,#facc15,#f97316);transition:width .4s}" +
      ".fkl-bar{height:6px;border-radius:6px;background:#06180d;overflow:hidden}.fkl-bar i{display:block;height:100%;width:0;background:#4ade80;transition:width .4s linear}" +
      ".fkl-tray{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;min-height:36px;margin-top:10px}" +
      ".fkl-ball{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;color:#111;animation:fklpop .3s ease}" +
      ".fkl-ball.h{box-shadow:0 0 0 3px #fff}@keyframes fklpop{from{transform:scale(.2);opacity:0}to{transform:scale(1);opacity:1}}" +
      ".fkl-g{display:grid;grid-template-columns:repeat(8,1fr);gap:5px;background:#0b2a17;border:1.5px solid #1f6b3c;border-radius:20px;padding:10px}" +
      ".fkl-c{aspect-ratio:1;border-radius:9px;border:1px solid #1f6b3c;background:#0a2514;color:#d6f5e0;font-weight:700;font-size:13px;padding:0}" +
      ".fkl-c.pick{background:#16a34a;color:#04200f;border-color:#86efac}.fkl-c.drawn{background:#1f6b3c;border-color:#4ade80}.fkl-c.hit{background:#facc15;color:#111;border-color:#fff}" +
      ".fkl-pay{display:flex;gap:8px}.fkl-pay div{flex:1;background:#0b2a17;border:1px solid #1f6b3c;border-radius:14px;padding:8px 4px;text-align:center;color:#d6f5e0}.fkl-pay div.on{border-color:#4ade80;background:#14532d}" +
      ".fkl-pay small{display:block;font-size:11px;color:#9fd9b4}.fkl-pay b{font-size:16px}" +
      ".fkl-bet{background:#0b2a17;border:1.5px solid #1f6b3c;border-radius:20px;padding:12px}.fkl-row{display:flex;gap:10px;align-items:center;margin-top:8px}" +
      ".fkl-step{display:flex;flex:1;align-items:center;background:#06180d;border:1px solid #1f6b3c;border-radius:16px;padding:4px}.fkl-step button{width:42px;height:42px;border:0;border-radius:12px;background:#14532d;color:#fff;font-size:22px}" +
      ".fkl-step input{flex:1;min-width:0;text-align:center;background:transparent;border:0;color:#fff;font-size:20px;font-weight:800}" +
      ".fkl-go{flex:1.3;height:52px;border:0;border-radius:16px;background:linear-gradient(#4ade80,#22c55e);color:#04200f;font-weight:900;font-size:17px}.fkl-go:disabled{opacity:.45}" +
      ".fkl-ghost{height:42px;border-radius:14px;border:1px solid #1f6b3c;background:#0a2514;color:#d6f5e0;padding:0 12px;font-weight:700}" +
      ".fkl-msg{min-height:20px;text-align:center;font-weight:700;color:#d6f5e0}.fkl-msg.win{color:#facc15}.fkl-msg.lose{color:#fca5a5}.fkl-msg.bad{color:#fdba74}" +
      ".fkl-info{display:flex;justify-content:space-between;color:#9fd9b4;font-size:12px;margin-top:8px}.fkl-last{color:#9fd9b4;font-size:12px;word-break:break-all}";
    document.head.appendChild(s);
  }

  window.setupFastKeno = async function () {
    var vkey = (typeof window.kdmVariantKey === "function" && window.kdmVariantKey()) || "fastkeno";
    if (KEYS.indexOf(vkey) < 0) { stop(); return orig && orig.apply(this, arguments); }
    GK = vkey;
    var root = document.getElementById("fastkeno-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById("fastkeno" + s); if (e) e.style.display = "none"; });
    css(); S.root = root;
    if (root.dataset.fkl !== GK) {
      root.dataset.fkl = GK; root.dataset.fkl = ""; root.dataset.fk = GK; S.sel = []; S.st = null; S.lastNo = 0;
      var cells = ""; for (var n = 1; n <= 40; n++) cells += '<button type="button" class="fkl-c" data-n="' + n + '">' + n + "</button>";
      root.innerHTML = '<div class="fkl"><div class="fkl-m"><div class="fkl-h"><span>LIVE · Draw #<b id="fkl-no">—</b></span><span class="fkl-pill" id="fkl-balls">Balls 0 / 20</span></div>' +
        '<div class="fkl-cd"><b id="fkl-sec">—</b><small id="fkl-ph">CONNECTING…</small></div><div class="fkl-bar"><i id="fkl-bar"></i></div><div class="fkl-meter" id="fkl-mwrap" hidden><i id="fkl-meter"></i></div><div class="fkl-tray" id="fkl-tray"></div>' +
        '<div class="fkl-info"><span id="fkl-pl">—</span><span id="fkl-cnt">0 / 8 picked</span></div></div>' +
        '<div class="fkl-g" id="fkl-g">' + cells + "</div><div class=\"fkl-pay\" id=\"fkl-pay\"></div>" +
        '<div class="fkl-bet"><small style="color:#9fd9b4">Bet Amount</small><div class="fkl-row"><div class="fkl-step"><button type="button" data-d="-1">−</button><input id="fkl-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="fkl-ghost" id="fkl-quick">Quick pick</button></div><div class="fkl-row"><button type="button" class="fkl-go" id="fkl-go">Bet on this draw</button></div></div>' +
        '<div class="fkl-msg" id="fkl-msg" aria-live="polite"></div><div class="fkl-last" id="fkl-last"></div></div>';
      root.querySelectorAll(".fkl-c").forEach(function (b) { b.addEventListener("click", function () { toggle(Number(b.dataset.n)); }); });
      root.querySelectorAll(".fkl-step button").forEach(function (b) { b.addEventListener("click", function () { var i = $("#fkl-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000; i.value = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); hap("light"); }); });
      $("#fkl-quick").addEventListener("click", function () { var k = S.sel.length || 4, s = []; while (s.length < k) { var n = 1 + Math.floor(Math.random() * 40); if (s.indexOf(n) < 0) s.push(n); } S.sel = s; hap("light"); render(); });
      $("#fkl-go").addEventListener("click", bet);
    }
    start();
  };

  function toggle(n) {
    var my = S.st && S.st.my_bet; if (my && my.status === "PENDING") return;   // bet placed: picks locked
    var i = S.sel.indexOf(n);
    if (i >= 0) S.sel.splice(i, 1); else if (S.sel.length < 8) S.sel.push(n); else { hap("error"); return; }
    hap("light"); render();
  }
  function say(c, t) { var e = $("#fkl-msg"); if (e) { e.className = "fkl-msg " + c; e.textContent = t; } }

  async function bet() {
    if (S.busy || !S.sel.length) return; S.busy = true; var btn = $("#fkl-go"); btn.disabled = true;
    try {
      var stake = Number($("#fkl-stake").value);
      await apiFetch("/live40/" + GK + "/bet", { method: "POST", json: { stake: stake, numbers: S.sel.slice() } });
      S.stake = stake; hap("success"); say("", "✅ ውርርድዎ ተቀምጧል — ዕጣውን ይጠብቁ"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); }
    S.busy = false; await poll();
  }

  function start() { stop(); poll(); S.timer = setInterval(poll, 800); }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }
  async function poll() {
    if (!S.root || !S.root.isConnected || S.root.offsetParent === null || document.hidden) return;   // not on screen
    try {
      var st = await apiFetch("/live40/" + GK + "/state"); S.off = st.server_time * 1000 - Date.now(); S.st = st; S.at = Date.now(); render();
    } catch (e) { var ph = $("#fkl-ph"); if (ph) ph.textContent = "RECONNECTING…"; }
  }

  function render() {
    var st = S.st; if (!st || !S.root) return;
    var my = st.my_bet, mine = my && my.status === "PENDING", cur = my && my.round_no === st.draw_no;
    var drawn = st.balls || [], pickSet = mine || (my && cur) ? my.picks : S.sel;
    $("#fkl-no").textContent = st.draw_no;
    $("#fkl-balls").textContent = "Balls " + drawn.length + " / " + st.balls_total;
    var left = Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000);
    $("#fkl-sec").textContent = st.phase === "BETTING" ? Math.ceil(left) + "s" : st.phase === "DRAWING" ? "🎱" : "✓";
    $("#fkl-ph").textContent = st.phase === "BETTING" ? "BETTING OPEN" : st.phase === "DRAWING" ? "DRAWING…" : "NEXT DRAW IN " + Math.ceil(left) + "s";
    $("#fkl-bar").style.width = Math.min(100, st.elapsed / st.round_sec * 100) + "%";
    $("#fkl-pl").textContent = st.players + " players · " + money(st.total_staked) + " ETB in this draw";
    var tray = $("#fkl-tray"); if (tray.childElementCount !== drawn.length || tray.dataset.no !== String(st.draw_no)) {
      tray.dataset.no = st.draw_no; tray.innerHTML = "";
      drawn.forEach(function (n) { var b = document.createElement("span"); b.className = "fkl-ball" + (pickSet.indexOf(n) >= 0 && (mine || cur) ? " h" : ""); b.style.background = BALLC[n % BALLC.length]; b.textContent = n; tray.appendChild(b); if (pickSet.indexOf(n) >= 0 && (mine || cur)) hap("light"); });
    }
    var sel = (mine || cur) ? my.picks : S.sel;
    S.root.querySelectorAll(".fkl-c").forEach(function (b) { var n = Number(b.dataset.n), p = sel.indexOf(n) >= 0, d = drawn.indexOf(n) >= 0; b.className = "fkl-c" + (p && d ? " hit" : p ? " pick" : d ? " drawn" : ""); });
    $("#fkl-cnt").textContent = sel.length + " / 8 picked";
    var t = st.tables[String(sel.length)], hits = drawn.filter(function (n) { return sel.indexOf(n) >= 0; }).length, pay = "";
    if (t) { for (var h = 1; h < t.length; h++) if (t[h] > 0) pay += '<div class="' + (drawn.length && h === hits ? "on" : "") + '"><small>' + h + ' hits</small><b>x' + (t[h] >= 100 ? Math.round(t[h]) : Number(t[h].toFixed(2))) + "</b></div>"; }
    $("#fkl-pay").innerHTML = pay || '<div><small>1–8 ቁጥሮች ይምረጡ</small></div>';
    var mw = $("#fkl-mwrap"); if (mw) { mw.hidden = GK !== "keno_power"; $("#fkl-meter").style.width = (sel.length ? Math.min(100, hits / sel.length * 100) : 0) + "%"; }
    var go = $("#fkl-go");
    if (mine && cur) { go.textContent = "Bet placed ✓"; go.disabled = true; }
    else if (st.phase === "BETTING" && left >= 1.5) { go.textContent = "Bet on this draw"; go.disabled = !t || S.busy; }
    else { go.textContent = "Betting closed — next draw"; go.disabled = true; }
    if (my && my.status !== "PENDING" && my.round_no !== S.lastNo) {   // settled result of my last draw
      S.lastNo = my.round_no; var p = Number(my.payout || 0), s = Number(my.stake);
      if (p > s) { say("win", "🎉 Draw #" + my.round_no + " · " + my.hits + " hits · +" + money(p - s) + " ETB"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else if (p > 0) say("bad", "↩️ Draw #" + my.round_no + " · " + my.hits + " hits · " + money(p) + " ETB returned");
      else say("lose", "😕 Draw #" + my.round_no + " · " + my.hits + " hits · -" + money(s) + " ETB");
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    }
    var lastEl = $("#fkl-last"); if (st.last && st.last[0]) lastEl.textContent = "Draw #" + st.last[0].draw_no + ": " + st.last[0].balls.join(" ");
  }
  window.addEventListener("pagehide", stop);
})();
