/* LUCKY WHEEL (new look): a 10-sector wheel, a pointer, chips, Spin. Same server engine as before: the server picks the sector (1..10) and pays its
   multiplier; the prize list comes from the server (admin-configurable), so every label on the wheel is the real payout. The spin animation only lands
   on the server's sector. Self-contained: injects its own CSS. Needs app.js to route the wheel page to window.setupWheel (see README). */
(function () {
  "use strict";
  var KEY = "wheel", DEFAULT = [0, 0, 0.5, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0], CHIPS = [10, 50, 100, 500];
  var PAL = { 0: "#1d6bff", 0.5: "#0891b2", 1: "#16a34a", 1.2: "#f59e0b", 1.5: "#f59e0b", 2: "#dc2626", 3: "#16a34a", 5: "#7c3aed", 10: "#7c3aed" };
  var ALT = ["#1d6bff", "#dc2626", "#16a34a", "#f59e0b", "#7c3aed", "#0891b2", "#dc2626", "#111827", "#f59e0b", "#7c3aed"];
  var S = { prizes: DEFAULT.slice(), min: 1, max: 10000, loaded: false, busy: false, rot: 0, last: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var fmtX = function (m) { m = Number(m); return "x" + (Math.abs(m - Math.round(m)) < 0.005 ? String(Math.round(m)) : m.toFixed(m < 10 ? 2 : 1).replace(/0$/, "")); };

  var css = ".wl-wrap{display:flex;flex-direction:column;gap:12px}.wl-stage{position:relative;border-radius:22px;border:1px solid #23407f;background:radial-gradient(100% 80% at 50% 40%,#10235a,#0a1330);padding:26px 12px 14px;display:flex;justify-content:center}" +
    ".wl-last{position:absolute;right:10px;top:10px;padding:5px 12px;border-radius:999px;background:#13361f;color:#86efac;font-weight:800;font-size:12px}.wl-ptr{position:absolute;left:50%;top:12px;transform:translateX(-50%);z-index:2;width:0;height:0;border-left:13px solid transparent;border-right:13px solid transparent;border-top:24px solid #fbbf24;filter:drop-shadow(0 2px 3px rgba(0,0,0,.5))}" +
    ".wl-wheel{width:min(100%,330px);aspect-ratio:1}.wl-wheel svg{width:100%;height:100%;display:block}.wl-legend{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.wl-legend div{border-radius:12px;border:1px solid #23407f;background:#0d1b45;text-align:center;padding:8px 2px}.wl-legend small{display:block;font-size:11px;opacity:.7}.wl-legend b{font-size:15px}.wl-legend .j b{color:#fbbf24}" +
    ".wl-chips{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.wl-chips button{min-height:42px;border-radius:12px;border:1px solid #23407f;background:#0d1b45;color:#fff;font-weight:800}.wl-chips button.on{background:#1d6bff;border-color:#1d6bff}.wl-bet{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:end}";
  function style() { if (document.getElementById("kdm-wheel-css")) return; var s = document.createElement("style"); s.id = "kdm-wheel-css"; s.textContent = css; document.head.appendChild(s); }

  function wheelSvg() {
    var N = S.prizes.length, h = "";
    for (var i = 0; i < N; i++) {
      var a0 = i * 2 * Math.PI / N - Math.PI / 2, a1 = (i + 1) * 2 * Math.PI / N - Math.PI / 2, am = (a0 + a1) / 2, R = 96, p = function (rad, a) { return (100 + rad * Math.cos(a)).toFixed(2) + " " + (100 + rad * Math.sin(a)).toFixed(2); };
      var c = PAL[S.prizes[i]] || ALT[i % ALT.length]; if (i > 0 && c === (PAL[S.prizes[i - 1]] || ALT[(i - 1) % ALT.length])) c = ALT[(i + 3) % ALT.length];
      h += '<path d="M100 100L' + p(R, a0) + " A" + R + " " + R + " 0 0 1 " + p(R, a1) + 'z" fill="' + c + '" stroke="#fff" stroke-width=".8"/>';
      var tx = 100 + 66 * Math.cos(am), ty = 100 + 66 * Math.sin(am);
      h += '<text x="' + tx.toFixed(1) + '" y="' + ty.toFixed(1) + '" fill="#fff" font-size="13" font-weight="900" text-anchor="middle" dominant-baseline="middle" transform="rotate(' + (am * 180 / Math.PI + 90).toFixed(1) + " " + tx.toFixed(1) + " " + ty.toFixed(1) + ')">' + fmtX(S.prizes[i]) + "</text>";
    }
    return '<svg viewBox="0 0 200 200" aria-hidden="true"><circle cx="100" cy="100" r="99" fill="#f59e0b"/><g id="wl-rot" style="transform-origin:100px 100px">' + h + '</g><circle cx="100" cy="100" r="20" fill="#d4a017" stroke="#fff" stroke-width="3"/><text x="100" y="101" fill="#3b2a12" font-size="9" font-weight="900" text-anchor="middle" dominant-baseline="middle">KDM</text></svg>';
  }
  window.setupWheel = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return; style();
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!S.loaded) {
      try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000;
        var wp = s.wheel_prizes || (s.settings && s.settings.wheel_prizes); if (Array.isArray(wp) && wp.length >= 2) S.prizes = wp.map(Number); } catch (_) {}
      S.loaded = true; delete root.dataset.wl2;
    }
    if (!root.dataset.wl2) {
      root.dataset.wl2 = "1";
      root.innerHTML = '<div class="wl-wrap"><div class="wl-stage"><span class="wl-last" id="wl-last" hidden></span><i class="wl-ptr"></i><div class="wl-wheel" id="wl-wheel">' + wheelSvg() + "</div></div>" +
        '<div class="wl-legend" id="wl-leg"></div>' +
        '<div class="av-card"><div class="wl-chips" id="wl-chips">' + CHIPS.map(function (c) { return '<button type="button" data-c="' + c + '">' + c + "</button>"; }).join("") + "</div>" +
        '<div class="wl-bet"><div class="av-bet-col"><label for="wheel-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button><input id="wheel-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<button type="button" id="wl-spin" class="av-go">Spin</button></div><div class="kx-msg" id="wl-msg" aria-live="polite"></div><div class="kx-proof" id="wl-proof"></div></div>' +
        '<small class="kx-note">ሰርቨሩ ዘርፉን ይመርጣል፤ ጎማው የሰርቨሩን ውጤት ብቻ ያሳያል። በጎማው ላይ የሚታየው ማባዣ እውነተኛው ክፍያ ነው (ዘርፎቹ እኩል ዕድል አላቸው፣ አንዳንዶቹ x0 ናቸው)።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () { if (S.busy) return; var i = $(root, "#wheel-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root); });
      });
      $(root, "#wl-chips").addEventListener("click", function (e) { var b = e.target.closest("button[data-c]"); if (!b || S.busy) return; $(root, "#wheel-stake").value = b.dataset.c; hap("light"); paint(root); });
      $(root, "#wheel-stake").addEventListener("input", function () { paint(root); });
      $(root, "#wl-spin").addEventListener("click", function () { spin(root); });
      S.rot = 0;
    }
    paint(root);
  };
  function paint(root) {
    var v = Number($(root, "#wheel-stake").value) || 0, pos = S.prizes.filter(function (x) { return x > 0; }).sort(function (a, b) { return a - b; });
    var low = pos[0], top = pos[pos.length - 1], big = pos.length > 2 ? pos[pos.length - 2] : top;
    $(root, "#wl-leg").innerHTML = '<div><small>Lose</small><b>x0</b></div><div><small>Low</small><b>' + fmtX(low) + '</b></div><div><small>Big</small><b>' + fmtX(big) + '</b></div><div class="j"><small>Top</small><b>' + fmtX(top) + "</b></div>";
    root.querySelectorAll("#wl-chips button").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.c) === v); b.disabled = S.busy; });
    $(root, "#wheel-stake").disabled = S.busy; root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = S.busy; });
    $(root, "#wl-spin").disabled = S.busy; $(root, "#wl-spin").textContent = "Spin";
    if (S.last !== null) { var l = $(root, "#wl-last"); l.hidden = false; l.textContent = "Last: " + fmtX(S.last); }
  }
  function say(root, cls, t) { var e = $(root, "#wl-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function spin(root) {
    if (S.busy) return; var stake = Number($(root, "#wheel-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; paint(root); say(root, "", ""); $(root, "#wl-proof").textContent = "";
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome || {}, N = S.prizes.length, idx = Math.max(0, Math.min(N - 1, Number(o.sector || 1) - 1)), seg = 360 / N;
      var target = -(idx * seg + seg / 2), cur = ((S.rot % 360) + 360) % 360;
      S.rot += 360 * 5 + ((target - cur) % 360 + 360) % 360; S.rot = Math.round(S.rot * 100) / 100;
      var rot = $(root, "#wl-rot"); rot.style.transition = "transform 3.2s cubic-bezier(.12,.7,.15,1)"; rot.style.transform = "rotate(" + S.rot + "deg)"; hap("light");
      await sleep(3300);
      var m = Number(o.multiplier || 0), p = Number(act.payout || 0), net = Math.round((p - stake) * 100) / 100; S.last = m;
      if (p > stake) { say(root, "win", "🎉 " + fmtX(m) + " · +" + money(net) + " ብር"); hap("success"); }
      else if (p > 0) { say(root, "bad", "↩️ " + fmtX(m) + " · " + money(p) + " ብር ተመለሰ (ከBet በታች)"); hap("light"); }
      else { say(root, "lose", "😕 x0 · -" + money(stake) + " ብር"); hap("error"); }
      if (act.server_seed) $(root, "#wl-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + (e.message || e)); }
    S.busy = false; paint(root);
  }
})();
