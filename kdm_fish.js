/* FISH (new look): a fish tank with a cannon. Every shot is one server round (same engine as before): the server draws a result from a fixed
   table and pays it; the cannon animation just flies the bullet to the fish whose multiplier matches the server's draw, or into open water on a miss.
   Where you "aim" never changes the odds. The multiplier on each fish is the real payout (base table x the house-edge scale), not a decoration.
   Loaded after app.js; replaces window.setupFish (app.js routes the fish page to it). Presentation only. */
(function () {
  "use strict";
  var KEY = "fish", BASE = [0.5, 0.8, 1.2, 1.5, 2, 3, 5], BASE_RTP = 14 / 9;   // MUST match the fish table in realtime_engine_v3.py (two 0 outcomes + these 7)
  var COL = ["#fb923c", "#4ade80", "#facc15", "#f87171", "#2dd4bf", "#f472b6", "#a78bfa"];
  var POS = [[6, 12], [38, 30], [58, 8], [4, 50], [60, 44], [30, 62], [66, 70]];   // % positions in the tank
  var S = { stake: 2, min: 1, max: 10000, edge: 0.08, scale: null, loaded: false, busy: false, auto: 0, caught: 0, shots: 0 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var fmtX = function (m) { return "x" + (m >= 10 ? m.toFixed(1) : m.toFixed(2)); };
  var scale = function () { return S.scale != null ? S.scale : (1 - S.edge) / BASE_RTP; };
  function fishSvg(c) { return '<svg viewBox="0 0 80 44" width="64" height="36" aria-hidden="true"><path d="M60 22l18-14v28z" fill="' + c + '"/><ellipse cx="34" cy="22" rx="30" ry="17" fill="' + c + '"/><circle cx="18" cy="17" r="4" fill="#fff"/><circle cx="17" cy="17" r="2" fill="#111"/><path d="M36 8q8 14 0 28" fill="none" stroke="rgba(0,0,0,.18)" stroke-width="3"/></svg>'; }

  window.setupFish = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.fs2) {
      root.dataset.fs2 = "1";
      root.innerHTML = '<div class="fs-wrap"><div class="fs-tank" id="fs-tank"><div class="fs-caught" id="fs-caught">Returned: 0.00</div><div id="fs-fish"></div>' +
        '<div class="fs-bullet" id="fs-bullet" hidden></div><div class="fs-pop" id="fs-pop" hidden></div><div class="fs-cannon" id="fs-cannon"><i></i></div></div>' +
        '<div class="av-card"><label for="fish-stake">Bet per shot</label><div class="fs-bet"><div class="kx-step"><button type="button" data-d="-1">−</button><input id="fish-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="2"><button type="button" data-d="1">+</button></div>' +
        '<button type="button" id="fs-auto" class="fs-auto">Auto ×10</button></div><button type="button" id="fs-fire" class="av-go">Fire</button>' +
        '<div class="kx-msg" id="fs-msg" aria-live="polite"></div><div class="kx-proof" id="fs-proof"></div></div>' +
        '<small class="kx-note">እያንዳንዱ ተኩስ በሰርቨሩ የሚወሰን ራሱን የቻለ ዙር ነው፤ ኢላማው ዕድሉን አይቀይርም። በዓሣው ላይ የሚታየው ማባዣ እውነተኛው ክፍያ ነው (ከቤቱ ድርሻ ጋር የተሰላ)። ብዙ ተኩሶች ከውርርድ በታች ይመልሳሉ ወይም ባዶ ናቸው። Auto ቢበዛ 10 ተኩስ ይተኩሳል እና በ Stop ይቆማል።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy) return; var i = $(root, "#fish-stake"), v = Number(i.value) || 0, st = v < 10 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#fs-fire").addEventListener("click", function () { if (!S.busy) fire(root); });
      $(root, "#fs-auto").addEventListener("click", function () { if (S.auto) { S.auto = 0; paint(root); } else if (!S.busy) { S.auto = 10; paint(root); runAuto(root); } });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; if (s.house_edge != null) S.edge = Number(s.house_edge); } catch (_) {} S.loaded = true; }
    paint(root);
  };
  function paint(root) {
    var h = ""; BASE.forEach(function (b, i) {
      h += '<div class="fs-fish f' + (i % 3) + '" data-i="' + i + '" style="left:' + POS[i][0] + "%;top:" + POS[i][1] + '%;animation-delay:-' + (i * 1.3) + 's">' + fishSvg(COL[i]) + "<b>" + fmtX(b * scale()) + "</b></div>";
    });
    var fl = $(root, "#fs-fish"); if (!fl.dataset.done || fl.dataset.sc !== String(scale())) { fl.innerHTML = h; fl.dataset.done = "1"; fl.dataset.sc = String(scale()); }
    $(root, "#fs-caught").textContent = "Returned: " + money(S.caught);
    $(root, "#fish-stake").disabled = S.busy; root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = S.busy; });
    $(root, "#fs-fire").disabled = S.busy || !!S.auto; $(root, "#fs-fire").textContent = "Fire · " + money(Number($(root, "#fish-stake").value) || 0) + " ETB";
    var a = $(root, "#fs-auto"); a.textContent = S.auto ? "Stop (" + S.auto + ")" : "Auto ×10"; a.classList.toggle("on", !!S.auto); a.disabled = S.busy && !S.auto;
  }
  function say(root, cls, t) { var e = $(root, "#fs-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function runAuto(root) { while (S.auto > 0) { var ok = await fire(root); if (!ok) { S.auto = 0; break; } S.auto--; paint(root); if (S.auto > 0) await sleep(700); } S.auto = 0; paint(root); }

  async function fire(root) {
    var stake = Number($(root, "#fish-stake").value);
    if (!(stake > 0)) { say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ"); return false; }
    if (stake < S.min || stake > S.max) { say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"); return false; }
    S.busy = true; paint(root); say(root, "", ""); var ok = true;
    try {
      S.shots++;
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, shot: 1 + (S.shots % 5), client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome || {}, base = Number(o.base_multiplier != null ? o.base_multiplier : 0), p = Number(act.payout || 0);
      if (o.payout_scale) { S.scale = Number(o.payout_scale); }
      var idx = base > 0 ? BASE.reduce(function (best, b, i) { return Math.abs(b - base) < Math.abs(BASE[best] - base) ? i : best; }, 0) : -1;
      await animate(root, idx); paint(root);
      S.caught += p;
      if (p > stake) { say(root, "win", "🎯 " + fmtX(p / stake) + " · +" + money(p - stake) + " ብር"); hap("success"); }
      else if (p > 0) { say(root, "bad", "🎯 " + fmtX(p / stake) + " · " + money(p) + " ብር ተመለሰ (ከBet በታች)"); hap("light"); }
      else { say(root, "lose", "💨 ሳተ · -" + money(stake) + " ብር"); hap("error"); }
      if (act.server_seed) $(root, "#fs-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + (e.message || e)); ok = false; }
    S.busy = false; paint(root); return ok;
  }
  async function animate(root, idx) {
    var tank = $(root, "#fs-tank"), tr = tank.getBoundingClientRect(), cn = $(root, "#fs-cannon"), bl = $(root, "#fs-bullet"), pop = $(root, "#fs-pop");
    var fx, fy; if (idx >= 0) { var fe = root.querySelector('.fs-fish[data-i="' + idx + '"]').getBoundingClientRect(); fx = fe.left + fe.width / 2 - tr.left; fy = fe.top + fe.height / 2 - tr.top; } else { fx = tr.width * (0.15 + Math.random() * 0.7); fy = tr.height * 0.12; }
    var sx = tr.width / 2, sy = tr.height - 48, ang = Math.atan2(fx - sx, sy - fy) * 180 / Math.PI;
    cn.style.transform = "translateX(-50%) rotate(" + ang + "deg)"; await sleep(180);
    bl.hidden = false; bl.style.transition = "none"; bl.style.transform = "translate(" + sx + "px," + sy + "px)"; void bl.offsetWidth;
    bl.style.transition = "transform .45s ease-in"; bl.style.transform = "translate(" + fx + "px," + fy + "px)"; await sleep(470); bl.hidden = true;
    pop.hidden = false; pop.textContent = idx >= 0 ? "💥" : "💨"; pop.style.left = fx + "px"; pop.style.top = fy + "px"; await sleep(450); pop.hidden = true;
    cn.style.transform = "translateX(-50%)";
  }
})();
