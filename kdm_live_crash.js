/* LIVE CRASH (Aviator / Crash / Jet / Rocket): ONE shared flight for ALL players, a new round every 60 s (15 s betting, then the flight).
   Same server engine as High Flyer live (live_engine_v1.py -> /api/live/<game>/crash-state | crash-bet | cashout).
   The server owns the clock, the hidden crash point, cash-out and settlement; this file only draws state and sends bet / cash-out.
   Wraps window.setupAviator (Aviator + Crash tiles) and window.setupJet (Jet + Rocket tiles). Load AFTER kdm_rocket.js. */
(function () {
  "use strict";
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var skin = function () { return typeof window.kdmSkinKey === "function" ? window.kdmSkinKey() : null; };

  function css() {
    if (document.getElementById("klc-css")) return;
    var s = document.createElement("style"); s.id = "klc-css";
    s.textContent =
      ".klc{--bg1:#0b2a5b;--bg2:#1d4ed8;--bd:#2f6bdc;--card:#0d1f4a;--acc:#facc15;--mut:#9ec0ff;--ink:#07142f;display:flex;flex-direction:column;gap:10px;color:#fff}" +
      ".klc.rk{--bg1:#0a0220;--bg2:#3b1a7a;--bd:#5b3fd1;--card:#160c3d;--acc:#c4b5fd;--mut:#b9a8f5;--ink:#0f0a33}" +
      ".klc-top{display:flex;justify-content:space-between;align-items:center;color:var(--mut);font-size:12px}.klc-top b{color:var(--acc)}" +
      ".klc-live{display:inline-flex;align-items:center;gap:6px;font-weight:800;color:#fff}.klc-live i{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 0 #22c55e99;animation:klcp 1.4s infinite}" +
      "@keyframes klcp{70%{box-shadow:0 0 0 7px #22c55e00}100%{box-shadow:0 0 0 0 #22c55e00}}" +
      ".klc-stage{position:relative;height:250px;border-radius:22px;overflow:hidden;border:1.5px solid var(--bd);background:linear-gradient(var(--bg1),var(--bg2))}" +
      ".klc.rk .klc-stage{background:radial-gradient(1px 1px at 12% 18%,#fff9,#0000),radial-gradient(1.5px 1.5px at 38% 62%,#fffa,#0000),radial-gradient(1px 1px at 70% 30%,#fff8,#0000),radial-gradient(1.5px 1.5px at 86% 74%,#fff9,#0000),radial-gradient(1px 1px at 55% 12%,#fff7,#0000),linear-gradient(var(--bg1),var(--bg2))}" +
      ".klc-stage.crashed{filter:saturate(.55) brightness(.85)}" +
      ".klc-alt{position:absolute;left:16px;top:10px;z-index:2}.klc-alt small{display:block;letter-spacing:.3em;font-weight:800;font-size:11px;color:var(--mut)}" +
      ".klc-mult{font-size:58px;font-weight:900;line-height:1.05;text-shadow:0 4px 18px #0007}" +
      ".klc-chips{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:5px;align-items:flex-end;z-index:2}.klc-chips span{background:#0006;border:1px solid var(--bd);border-radius:12px;padding:2px 10px;font-weight:800;font-size:13px}.klc-chips .v{color:#86efac}.klc-chips .b{color:#f9a8d4}" +
      ".klc-svg{position:absolute;inset:0;width:100%;height:100%}.klc-plane{position:absolute;font-size:38px;line-height:1;transform:translate(-50%,50%)}" +
      ".klc-cd{position:absolute;inset:0;z-index:3;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#050a1cb0;text-align:center;font-weight:800;letter-spacing:.08em;font-size:14px;color:var(--mut)}.klc-cd b{font-size:56px;color:#fff;line-height:1;letter-spacing:0}" +
      ".klc-pills{position:absolute;left:10px;right:10px;bottom:8px;display:flex;justify-content:space-between;z-index:2;font-size:12px}.klc-pills span{background:#0007;border:1px solid var(--bd);border-radius:14px;padding:4px 12px;font-weight:700}" +
      ".klc-bets{display:flex;gap:8px}.klc-b{flex:1;min-width:0;background:var(--card);border:1.5px solid var(--bd);border-radius:18px;padding:8px}" +
      ".klc-bh{display:flex;justify-content:space-between;font-size:12px;color:var(--mut)}.klc-bh em{font-style:normal;color:#4ade80}" +
      ".klc-in{display:flex;align-items:center;background:var(--ink);border:1px solid var(--bd);border-radius:12px;margin:6px 0;padding:2px}.klc-in button{width:32px;height:36px;border:0;border-radius:9px;background:var(--bg2);color:#fff;font-size:19px;font-weight:800}.klc-in input{flex:1;min-width:0;text-align:center;background:transparent;border:0;color:#fff;font-size:17px;font-weight:800}" +
      ".klc-go{width:100%;height:44px;border:0;border-radius:13px;font-weight:900;font-size:15px;background:linear-gradient(#4ade80,#22c55e);color:#04200f}.klc-go.cash{background:linear-gradient(#fde047,#f59e0b);color:#3a2a00}.klc-go.wait{background:var(--bg2);color:#fff}.klc-go:disabled{opacity:.55}" +
      ".klc-card{background:var(--card);border:1.5px solid var(--bd);border-radius:18px;padding:10px 12px}.klc-ac{display:flex;justify-content:space-between;align-items:center}.klc-ac small{color:var(--mut)}" +
      ".klc-ac input[type=text]{width:84px;background:var(--ink);border:1px solid var(--bd);border-radius:10px;color:#fff;font-size:18px;font-weight:900;text-align:center;padding:5px;margin-top:3px}" +
      ".klc-sw{width:52px;height:28px;border-radius:16px;background:#3b3566;border:0;position:relative}.klc-sw.on{background:#2563eb}.klc-sw i{position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;transition:left .15s}.klc-sw.on i{left:27px}" +
      ".klc-tw{display:flex;justify-content:space-between;padding:4px 0;font-weight:700;font-size:13px}.klc-tw .m{color:var(--acc)}.klc-tw .p{color:#4ade80}" +
      ".klc-msg{min-height:18px;text-align:center;font-weight:800;font-size:14px}.klc-msg.win{color:#facc15}.klc-msg.lose{color:#fca5a5}.klc-msg.bad{color:#fdba74}.klc-note{color:var(--mut);font-size:11px;line-height:1.4}";
    document.head.appendChild(s);
  }

  function make(cfg) {
    var GK = cfg.gk, ROOT = cfg.root, orig = window[cfg.hook], P = "klc";
    var S = { st: null, off: 0, at: 0, timer: null, raf: 0, root: null, busy: {}, queue: { A: false, B: false }, stake: { A: 50, B: 20 }, autoOn: true, auto: 2, trail: [], seenDraw: 0, shown: {} };
    var $ = function (s) { return S.root && S.root.querySelector(s); };
    var mine = function () { return S.root && S.root.dataset.klcGk === GK && S.root.querySelector(".klc[data-gk=\"" + GK + "\"]"); };

    window[cfg.hook] = async function () {
      var root = document.getElementById(ROOT + "-controls");
      if (!cfg.match(skin())) {
        if (root && root.dataset.klcGk === GK) {         // leaving this live skin: hand the page back to whoever owns the next one
          stop(); root.innerHTML = ""; delete root.dataset.klcGk; delete root.dataset.built;
          ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(ROOT + s); if (e) e.style.display = ""; });
        }
        return orig && orig.apply(this, arguments);
      }
      if (!root) return;
      ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(ROOT + s); if (e) e.style.display = "none"; });
      var pg = document.getElementById("page-" + ROOT); if (pg) pg.classList.add("kx-page");
      css(); S.root = root;
      if (!(root.dataset.klcGk === GK && root.querySelector(".klc[data-gk=\"" + GK + "\"]"))) {
        stop(); delete root.dataset.hfl; delete root.dataset.sml; delete root.dataset.skl;   // other live skins on this page must rebuild when they come back
        root.dataset.klcGk = GK; root.dataset.built = "klc"; S.trail = []; S.seenDraw = 0; S.shown = {}; S.st = null;
        var slot = function (k) {
          return '<div class="klc-b"><div class="klc-bh"><span>Bet ' + k + '</span><em data-s="' + k + '">waiting</em></div><div class="klc-in"><button type="button" data-k="' + k + '" data-d="-1" aria-label="Decrease">−</button>' +
            '<input data-i="' + k + '" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake[k] + '"><button type="button" data-k="' + k + '" data-d="1" aria-label="Increase">+</button></div>' +
            '<button type="button" class="klc-go" data-g="' + k + '">Bet</button></div>';
        };
        root.innerHTML = '<div class="klc ' + (cfg.rocket ? "rk" : "") + '" data-gk="' + GK + '">' +
          '<div class="klc-top"><span class="klc-live"><i></i>LIVE · Round #<span data-r>—</span></span><span>Best today <b data-best>—</b></span></div>' +
          '<div class="klc-stage" data-stage><svg class="klc-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline data-trail fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.2" stroke-dasharray="1.2 2.4" stroke-linecap="round" vector-effect="non-scaling-stroke" points=""/></svg>' +
          '<div class="klc-alt"><small>' + cfg.altLabel + '</small><div class="klc-mult" data-mult>1.00x</div></div><div class="klc-chips" data-chips></div>' +
          '<div class="klc-plane" data-plane>' + cfg.emoji + '</div><div class="klc-pills"><span data-ph>CONNECTING</span><span data-pl>—</span></div><div class="klc-cd" data-cd hidden></div></div>' +
          '<div class="klc-bets">' + slot("A") + slot("B") + '</div>' +
          '<div class="klc-card klc-ac"><div><small>Auto cash-out</small><br><input data-auto type="text" inputmode="decimal" value="x' + S.auto.toFixed(2) + '"></div><button type="button" class="klc-sw on" data-sw aria-label="Auto cash-out"><i></i></button></div>' +
          '<div class="klc-msg" data-msg aria-live="polite"></div>' +
          '<div class="klc-card"><div class="klc-bh"><b style="color:var(--mut)">Top wins</b><small data-pc></small></div><div data-top><div class="klc-note">…</div></div></div>' +
          '<small class="klc-note">ሁሉም ተጫዋች አንድ በረራ ነው የሚያየው፤ ዙሩ በየ1 ደቂቃ ይጀምራል። ሰርቨሩ የመከስከሻውን ነጥብ ከመከስከሱ በፊት ይደብቃል፤ ከመከስከሱ በፊት Cash ሲጫኑ ወይም Auto ሲደርስ ብቻ ያሸንፋሉ።</small></div>';
        root.querySelectorAll(".klc-in button").forEach(function (b) { b.addEventListener("click", function () { var k = b.dataset.k, i = $('[data-i="' + k + '"]'), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000; i.value = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); hap("light"); }); });
        root.querySelectorAll(".klc-go").forEach(function (b) { b.addEventListener("click", function () { press(b.dataset.g); }); });
        $("[data-sw]").addEventListener("click", function () { S.autoOn = !S.autoOn; this.classList.toggle("on", S.autoOn); hap("light"); });
        $("[data-auto]").addEventListener("change", function () { var v = parseFloat(String(this.value).replace(/[^0-9.]/g, "")); S.auto = isFinite(v) ? Math.max(1.01, Math.min(100, v)) : 2; this.value = "x" + S.auto.toFixed(2); });
      }
      start();
    };

    function say(c, t) { var e = $("[data-msg]"); if (e) { e.className = "klc-msg " + c; e.textContent = t; } }
    function autoVal() { return S.autoOn ? Math.round(S.auto * 100) / 100 : null; }
    function curMult() {
      var st = S.st; if (!st) return 1;
      if (st.phase === "CRASHED") return st.crash || 1;
      if (st.phase !== "FLYING") return 1;
      var t = (Date.now() + S.off) / 1000 - st.flight_start; return Math.max(1, Math.floor(Math.exp(st.k * Math.max(0, t)) * 100) / 100);
    }
    function refresh() { try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {} }

    async function place(k) {
      if (S.busy[k]) return false; S.busy[k] = true;
      try {
        var stake = Number($('[data-i="' + k + '"]').value), body = { slot: k, stake: stake }, a = autoVal(); if (a) body.auto = a;
        await apiFetch("/live/" + GK + "/crash-bet", { method: "POST", json: body });
        S.stake[k] = stake; hap("success"); refresh(); S.busy[k] = false; poll(); return true;
      } catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); S.busy[k] = false; return false; }
    }
    async function press(k) {
      var st = S.st; if (!st) return; var my = st.my[k], cur = my && my.round_no === st.draw_no && my.status === "PENDING";
      if (cur && st.phase === "FLYING") {
        if (S.busy[k]) return; S.busy[k] = true;
        try { var r = await apiFetch("/live/" + GK + "/cashout", { method: "POST", json: { slot: k } }); hap("success"); say("win", "💰 Bet " + k + " · x" + r.multiplier.toFixed(2) + " · +" + money(r.payout) + " ETB"); refresh(); }
        catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); }
        S.busy[k] = false; poll(); return;
      }
      if (st.phase === "BETTING" && !(my && my.round_no === st.draw_no)) { await place(k); return; }
      if (!(my && my.round_no === st.draw_no)) { S.queue[k] = !S.queue[k]; hap("light"); render(); }   // "Bet next": queue for the next round
    }

    function start() { stop(); poll(); S.timer = setInterval(poll, 450); S.raf = requestAnimationFrame(frame); }
    function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0; } }
    function visible() { return mine() && S.root.isConnected && S.root.offsetParent !== null && !document.hidden; }
    async function poll() {
      if (!visible()) return;
      try { var st = await apiFetch("/live/" + GK + "/crash-state"); if (!mine()) return; S.off = st.server_time * 1000 - Date.now(); S.st = st; S.at = Date.now(); onState(); }
      catch (e) { var sb = $("[data-ph]"); if (sb) sb.textContent = "RECONNECTING"; }
    }
    function onState() {
      var st = S.st;
      if (st.draw_no !== S.seenDraw) { S.seenDraw = st.draw_no; S.trail = []; }
      if (st.phase === "BETTING") ["A", "B"].forEach(function (k) {   // a queued "Bet next" fires as soon as betting opens
        var my = st.my[k]; if (S.queue[k] && !(my && my.round_no === st.draw_no) && st.seconds_left > 2) { S.queue[k] = false; place(k); }
      });
      ["A", "B"].forEach(function (k) {   // settled result of my bet, once
        var my = st.my[k]; if (!my || my.status === "PENDING") return; var id = k + ":" + my.round_no; if (S.shown[id]) return; S.shown[id] = 1;
        if (Number(my.payout) > 0) { say("win", "🎉 Bet " + k + " · x" + Number(my.mult).toFixed(2) + " · +" + money(my.payout - my.stake) + " ETB"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
        else say("lose", "😕 Bet " + k + " · crashed · -" + money(my.stake) + " ETB");
        refresh();
      });
      render();
    }

    function frame() {
      S.raf = requestAnimationFrame(frame);
      if (!visible() || !S.st) return;
      var st = S.st, m = curMult(), stage = $("[data-stage]"); if (!stage) return;
      $("[data-mult]").textContent = m.toFixed(2) + "x";
      var prog = Math.min(1, Math.log(Math.max(1, m)) / Math.log(30)), x = 10 + 76 * prog, y = 10 + 62 * Math.pow(prog, 0.8);
      var pl = $("[data-plane]"); pl.style.left = x + "%"; pl.style.bottom = y + "%"; pl.style.top = "auto";
      pl.style.transform = "translate(-50%,50%) rotate(" + (st.phase === "CRASHED" ? cfg.rot + 60 : cfg.rot) + "deg)"; pl.style.opacity = st.phase === "CRASHED" ? 0.45 : 1;
      if (st.phase === "FLYING") { S.trail.push(x.toFixed(1) + "," + (100 - y).toFixed(1)); if (S.trail.length > 400) S.trail.shift(); $("[data-trail]").setAttribute("points", S.trail.join(" ")); }
      else if (st.phase === "BETTING") { $("[data-trail]").setAttribute("points", ""); }
      var left = Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000), cd = $("[data-cd]");
      cd.hidden = st.phase !== "BETTING"; if (!cd.hidden) cd.innerHTML = "BETTING OPEN<b>" + Math.ceil(left) + "</b>";
      var pill = $("[data-ph]");
      pill.textContent = st.phase === "BETTING" ? "BETS OPEN" : st.phase === "FLYING" ? "IN FLIGHT" : "FLEW AWAY · NEXT ROUND IN " + Math.ceil(left) + "s";
      ["A", "B"].forEach(function (k) { var my = st.my[k]; if (st.phase === "FLYING" && my && my.round_no === st.draw_no && my.status === "PENDING") { var b = $('[data-g="' + k + '"]'); if (b) b.textContent = "Cash " + money(my.stake * m); } });
    }

    function render() {
      var st = S.st; if (!st || !mine()) return;
      $("[data-stage]").classList.toggle("crashed", st.phase === "CRASHED");
      $("[data-r]").textContent = st.draw_no;
      $("[data-pl]").textContent = st.players + " players · " + money(st.total_staked) + " ETB";
      $("[data-best]").textContent = "x" + Number(st.best_today).toFixed(2);
      $("[data-chips]").innerHTML = (st.last || []).slice(0, 3).map(function (v) { return '<span class="' + (v >= 10 ? "b" : v >= 2 ? "v" : "") + '">' + v.toFixed(2) + "x</span>"; }).join("");
      $("[data-pc]").textContent = money(st.total_staked) + " ETB in this round";
      $("[data-top]").innerHTML = (st.top || []).length ? st.top.map(function (r) { return '<div class="klc-tw"><span>' + r.name + '</span><span class="m">x' + Number(r.mult).toFixed(2) + '</span><span class="p">' + Number(r.payout).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "</span></div>"; }).join("") : '<div class="klc-note">ገና አሸናፊ የለም</div>';
      ["A", "B"].forEach(function (k) {
        var my = st.my[k], cur = my && my.round_no === st.draw_no, b = $('[data-g="' + k + '"]'), s = $('[data-s="' + k + '"]');
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
  }

  // Aviator page (engine "aviator"): plain Aviator tile + the "Crash" catalog skin
  make({ gk: "aviator", hook: "setupAviator", root: "aviator", emoji: "✈️", altLabel: "MULTIPLIER", rot: -22, rocket: false, match: function (s) { return !s || s === "aviator"; } });
  make({ gk: "crash", hook: "setupAviator", root: "aviator", emoji: "✈️", altLabel: "MULTIPLIER", rot: -22, rocket: false, match: function (s) { return s === "crash"; } });
  // Jet page (engine "jet"): plain Jet tile + the "Rocket" catalog skin
  make({ gk: "jet", hook: "setupJet", root: "jet", emoji: "🚀", altLabel: "ALTITUDE", rot: 0, rocket: true, match: function (s) { return !s || s === "jet"; } });
  make({ gk: "rocket", hook: "setupJet", root: "jet", emoji: "🚀", altLabel: "ALTITUDE", rot: 0, rocket: true, match: function (s) { return s === "rocket"; } });
})();
