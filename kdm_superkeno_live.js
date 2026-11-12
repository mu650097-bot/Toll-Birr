/* SUPER KENO LIVE: one global draw every 60 s for ALL players. 80 numbers, 20 balls, pick 1-10.
   Server (live_engine_v1.py) owns the clock, the draw and the payout. This file only shows what /api/live/keno_super/state says.
   Replaces window.setupFastKeno ONLY for the keno_super skin; Fast / Power / Insta keep the old file. */
(function () {
  "use strict";
  var GK = "keno_super", orig = window.setupFastKeno;
  var BALLC = ["#facc15", "#3b82f6", "#ef4444", "#a855f7", "#f97316", "#14b8a6", "#ec4899", "#84cc16"];
  var S = { sel: [], stake: 50, st: null, off: 0, timer: null, root: null, busy: false, lastNo: 0, sound: null };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var $ = function (s) { return S.root && S.root.querySelector(s); };

  function css() {
    if (document.getElementById("skl-css")) return;
    var s = document.createElement("style"); s.id = "skl-css";
    s.textContent = ".skl{display:flex;flex-direction:column;gap:12px}.skl-m{background:#0b2a17;border:1.5px solid #1f6b3c;border-radius:22px;padding:12px}" +
      ".skl-h{display:flex;justify-content:space-between;align-items:center;color:#9fd9b4;font-size:13px}.skl-h b{color:#fff;font-size:15px}" +
      ".skl-pill{background:#06180d;border-radius:14px;padding:4px 10px;color:#e8fff0;font-weight:700}" +
      ".skl-cd{text-align:center;margin:10px 0 6px}.skl-cd b{font-size:42px;color:#4ade80;line-height:1}.skl-cd small{display:block;color:#9fd9b4;letter-spacing:.12em;font-size:11px;margin-top:2px}" +
      ".skl-bar{height:6px;border-radius:6px;background:#06180d;overflow:hidden}.skl-bar i{display:block;height:100%;width:0;background:#4ade80;transition:width .4s linear}" +
      ".skl-tray{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;min-height:36px;margin-top:10px}" +
      ".skl-ball{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;color:#111;animation:sklpop .3s ease}" +
      ".skl-ball.h{box-shadow:0 0 0 3px #fff}@keyframes sklpop{from{transform:scale(.2);opacity:0}to{transform:scale(1);opacity:1}}" +
      ".skl-g{display:grid;grid-template-columns:repeat(10,minmax(0,1fr));gap:4px;background:#0b2a17;border:1.5px solid #1f6b3c;border-radius:20px;padding:8px}" +
      ".skl-c{min-width:0;width:100%;aspect-ratio:1;border-radius:9px;border:1px solid #1f6b3c;background:#0a2514;color:#d6f5e0;font-weight:700;font-size:13px;padding:0}" +
      ".skl-c.pick{background:#16a34a;color:#04200f;border-color:#86efac}.skl-c.drawn{background:#1f6b3c;border-color:#4ade80}.skl-c.hit{background:#facc15;color:#111;border-color:#fff}" +
      ".skl-pay{display:flex;gap:8px}.skl-pay div{flex:1;background:#0b2a17;border:1px solid #1f6b3c;border-radius:14px;padding:8px 4px;text-align:center;color:#d6f5e0}.skl-pay div.on{border-color:#4ade80;background:#14532d}" +
      ".skl-pay small{display:block;font-size:11px;color:#9fd9b4}.skl-pay b{font-size:16px}" +
      ".skl-bet{background:#0b2a17;border:1.5px solid #1f6b3c;border-radius:20px;padding:12px}.skl-row{display:flex;gap:10px;align-items:center;margin-top:8px}" +
      ".skl-step{display:flex;flex:1;align-items:center;background:#06180d;border:1px solid #1f6b3c;border-radius:16px;padding:4px}.skl-step button{width:42px;height:42px;border:0;border-radius:12px;background:#14532d;color:#fff;font-size:22px}" +
      ".skl-step input{flex:1;min-width:0;text-align:center;background:transparent;border:0;color:#fff;font-size:20px;font-weight:800}" +
      ".skl-go{flex:1.3;height:52px;border:0;border-radius:16px;background:linear-gradient(#4ade80,#22c55e);color:#04200f;font-weight:900;font-size:17px}.skl-go:disabled{opacity:.45}" +
      ".skl-ghost{height:42px;border-radius:14px;border:1px solid #1f6b3c;background:#0a2514;color:#d6f5e0;padding:0 12px;font-weight:700}" +
      ".skl-msg{min-height:20px;text-align:center;font-weight:700;color:#d6f5e0}.skl-msg.win{color:#facc15}.skl-msg.lose{color:#fca5a5}.skl-msg.bad{color:#fdba74}" +
      ".skl-info{display:flex;justify-content:space-between;color:#9fd9b4;font-size:12px;margin-top:8px}.skl-last{color:#9fd9b4;font-size:12px;word-break:break-all}";
    document.head.appendChild(s);
  }

  window.setupFastKeno = async function () {
    var vkey = (typeof window.kdmVariantKey === "function" && window.kdmVariantKey()) || "fastkeno";
    if (vkey !== GK) { stop(); return orig && orig.apply(this, arguments); }
    var root = document.getElementById("fastkeno-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById("fastkeno" + s); if (e) e.style.display = "none"; });
    css(); S.root = root;
    if (root.dataset.skl !== "1") {
      root.dataset.skl = "1"; root.dataset.fk = GK; S.sel = [];
      var cells = ""; for (var n = 1; n <= 80; n++) cells += '<button type="button" class="skl-c" data-n="' + n + '">' + n + "</button>";
      root.innerHTML = '<div class="skl"><div class="skl-m"><div class="skl-h"><span>LIVE · Draw #<b id="skl-no">—</b></span><span class="skl-pill" id="skl-balls">Balls 0 / 20</span></div>' +
        '<div class="skl-cd"><b id="skl-sec">—</b><small id="skl-ph">CONNECTING…</small></div><div class="skl-bar"><i id="skl-bar"></i></div><div class="skl-tray" id="skl-tray"></div>' +
        '<div class="skl-info"><span id="skl-pl">—</span><span id="skl-cnt">0 / 10 picked</span></div></div>' +
        '<div class="skl-g" id="skl-g">' + cells + "</div><div class=\"skl-pay\" id=\"skl-pay\"></div>" +
        '<div class="skl-bet"><small style="color:#9fd9b4">Bet Amount</small><div class="skl-row"><div class="skl-step"><button type="button" data-d="-1">−</button><input id="skl-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" class="skl-ghost" id="skl-quick">Quick pick</button></div><div class="skl-row"><button type="button" class="skl-go" id="skl-go">Bet on this draw</button></div></div>' +
        '<div class="skl-msg" id="skl-msg" aria-live="polite"></div><div class="skl-last" id="skl-last"></div></div>';
      root.querySelectorAll(".skl-c").forEach(function (b) { b.addEventListener("click", function () { toggle(Number(b.dataset.n)); }); });
      root.querySelectorAll(".skl-step button").forEach(function (b) { b.addEventListener("click", function () { var i = $("#skl-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000; i.value = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); hap("light"); }); });
      $("#skl-quick").addEventListener("click", function () { var k = S.sel.length || 6, s = []; while (s.length < k) { var n = 1 + Math.floor(Math.random() * 80); if (s.indexOf(n) < 0) s.push(n); } S.sel = s; hap("light"); render(); });
      $("#skl-go").addEventListener("click", bet);
    }
    start();
  };

  function toggle(n) {
    var my = S.st && S.st.my_bet; if (my && my.status === "PENDING") return;   // bet placed: picks locked
    var i = S.sel.indexOf(n);
    if (i >= 0) S.sel.splice(i, 1); else if (S.sel.length < 10) S.sel.push(n); else { hap("error"); return; }
    hap("light"); render();
  }
  function say(c, t) { var e = $("#skl-msg"); if (e) { e.className = "skl-msg " + c; e.textContent = t; } }

  async function bet() {
    if (S.busy || !S.sel.length) return; S.busy = true; var btn = $("#skl-go"); btn.disabled = true;
    try {
      var stake = Number($("#skl-stake").value);
      await apiFetch("/live/" + GK + "/bet", { method: "POST", json: { stake: stake, numbers: S.sel.slice() } });
      S.stake = stake; hap("success"); say("", "✅ ውርርድዎ ተቀምጧል — ዕጣውን ይጠብቁ"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); }
    S.busy = false; await poll();
  }

  function start() { stop(); poll(); S.timer = setInterval(poll, 800); }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }
  async function poll() {
    if (!S.root || S.root.dataset.skl !== "1" || !S.root.isConnected || S.root.offsetParent === null || document.hidden) return;   // not on screen
    try {
      var st = await apiFetch("/live/" + GK + "/state"); S.off = st.server_time * 1000 - Date.now(); S.st = st; S.at = Date.now(); render();
    } catch (e) { var ph = $("#skl-ph"); if (ph) ph.textContent = "RECONNECTING…"; }
  }

  function render() {
    var st = S.st; if (!st || !S.root) return;
    var my = st.my_bet, mine = my && my.status === "PENDING", cur = my && my.round_no === st.draw_no;
    var drawn = st.balls || [], pickSet = mine || (my && cur) ? my.picks : S.sel;
    $("#skl-no").textContent = st.draw_no;
    $("#skl-balls").textContent = "Balls " + drawn.length + " / " + st.balls_total;
    var left = Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000);
    $("#skl-sec").textContent = st.phase === "BETTING" ? Math.ceil(left) + "s" : st.phase === "DRAWING" ? "🎱" : "✓";
    $("#skl-ph").textContent = st.phase === "BETTING" ? "BETTING OPEN" : st.phase === "DRAWING" ? "DRAWING…" : "NEXT DRAW IN " + Math.ceil(left) + "s";
    $("#skl-bar").style.width = Math.min(100, st.elapsed / st.round_sec * 100) + "%";
    $("#skl-pl").textContent = st.players + " players · " + money(st.total_staked) + " ETB in this draw";
    var tray = $("#skl-tray"); if (tray.childElementCount !== drawn.length || tray.dataset.no !== String(st.draw_no)) {
      tray.dataset.no = st.draw_no; tray.innerHTML = "";
      drawn.forEach(function (n) { var b = document.createElement("span"); b.className = "skl-ball" + (pickSet.indexOf(n) >= 0 && (mine || cur) ? " h" : ""); b.style.background = BALLC[n % BALLC.length]; b.textContent = n; tray.appendChild(b); if (pickSet.indexOf(n) >= 0 && (mine || cur)) hap("light"); });
    }
    var sel = (mine || cur) ? my.picks : S.sel;
    S.root.querySelectorAll(".skl-c").forEach(function (b) { var n = Number(b.dataset.n), p = sel.indexOf(n) >= 0, d = drawn.indexOf(n) >= 0; b.className = "skl-c" + (p && d ? " hit" : p ? " pick" : d ? " drawn" : ""); });
    $("#skl-cnt").textContent = sel.length + " / 10 picked";
    var t = st.tables[String(sel.length)], hits = drawn.filter(function (n) { return sel.indexOf(n) >= 0; }).length, pay = "";
    if (t) { for (var h = 1; h < t.length; h++) if (t[h] > 0) pay += '<div class="' + (drawn.length && h === hits ? "on" : "") + '"><small>' + h + ' hits</small><b>x' + (t[h] >= 100 ? Math.round(t[h]) : Number(t[h].toFixed(2))) + "</b></div>"; }
    $("#skl-pay").innerHTML = pay || '<div><small>1–10 ቁጥሮች ይምረጡ</small></div>';
    var go = $("#skl-go");
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
    var lastEl = $("#skl-last"); if (st.last && st.last[0]) lastEl.textContent = "Draw #" + st.last[0].draw_no + ": " + st.last[0].balls.join(" ");
  }
  window.addEventListener("pagehide", stop);
})();
