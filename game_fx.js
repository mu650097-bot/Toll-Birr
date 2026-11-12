/* KDM GAME FX -- presentation only.
   1) Win celebration: gold-coin rain + confetti + "+X ብር" banner, shown ONLY when the server reports a real win
      (won === true and payout > 0). Nothing here decides or changes a result.
   2) Per-game visual theme: each game page gets its own colours + emblem so the games do not all look alike. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------------ win celebration */
  var cvs, ctx, parts = [], raf = 0, lastFx = 0;
  function ensureCanvas() {
    if (cvs) return;
    cvs = document.createElement("canvas"); cvs.id = "kdm-fx-canvas";
    document.body.appendChild(cvs); ctx = cvs.getContext("2d");
    window.addEventListener("resize", size); size();
  }
  function size() { if (!cvs) return; var d = Math.min(window.devicePixelRatio || 1, 2); cvs.width = innerWidth * d; cvs.height = innerHeight * d; ctx.setTransform(d, 0, 0, d, 0, 0); }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function spawn(n, coinShare) {
    for (var i = 0; i < n; i++) {
      var coin = Math.random() < coinShare;
      parts.push({ coin: coin, x: rnd(0, innerWidth), y: rnd(-innerHeight * 0.6, -10), vx: rnd(-0.6, 0.6), vy: rnd(2.2, 5.2),
        r: coin ? rnd(8, 14) : rnd(4, 7), rot: rnd(0, 6.28), vr: rnd(-0.2, 0.2), ph: rnd(0, 6.28),
        col: ["#f43f5e", "#22c55e", "#3b82f6", "#f59e0b", "#a855f7", "#fde047"][(Math.random() * 6) | 0] });
    }
  }
  function drawCoin(p) {
    var w = Math.abs(Math.cos(p.ph)) * p.r + 1.5;
    ctx.save(); ctx.translate(p.x, p.y);
    var g = ctx.createLinearGradient(-p.r, -p.r, p.r, p.r); g.addColorStop(0, "#fff3b0"); g.addColorStop(0.5, "#fbbf24"); g.addColorStop(1, "#b45309");
    ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(0, 0, w, p.r, 0, 0, 6.283); ctx.fill();
    ctx.strokeStyle = "#92400e"; ctx.lineWidth = 1.2; ctx.stroke();
    if (w > p.r * 0.5) { ctx.beginPath(); ctx.ellipse(0, 0, w * 0.6, p.r * 0.6, 0, 0, 6.283); ctx.stroke(); }
    ctx.restore();
  }
  function tick() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (var i = parts.length - 1; i >= 0; i--) {
      var p = parts[i]; p.x += p.vx; p.y += p.vy; p.vy += 0.035; p.rot += p.vr; p.ph += 0.18;
      if (p.y > innerHeight + 30) { parts.splice(i, 1); continue; }
      if (p.coin) drawCoin(p);
      else { ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.fillStyle = p.col; ctx.fillRect(-p.r, -p.r / 2, p.r * 2, p.r); ctx.restore(); }
    }
    if (parts.length) raf = requestAnimationFrame(tick); else { raf = 0; ctx.clearRect(0, 0, innerWidth, innerHeight); }
  }
  function banner(text, big) {
    var b = document.createElement("div"); b.className = "kdm-win-banner" + (big ? " big" : "");
    b.innerHTML = '<div class="kw-t"></div><div class="kw-a"></div>';
    b.querySelector(".kw-t").textContent = big ? "🏆 ትልቅ ድል!" : "🎉 አሸንፈዋል!";
    b.querySelector(".kw-a").textContent = text;
    document.body.appendChild(b); setTimeout(function () { b.classList.add("out"); }, big ? 3200 : 2200); setTimeout(function () { b.remove(); }, big ? 3700 : 2700);
  }
  function celebrate(payout, mult) {
    var now = Date.now(); if (now - lastFx < 1500) return; lastFx = now;
    var big = mult >= 10, mid = mult >= 2;
    banner("+" + Number(payout).toFixed(2) + " ብር", big);
    try { var h = window.Telegram && Telegram.WebApp && Telegram.WebApp.HapticFeedback; if (h) h.notificationOccurred("success"); } catch (_) {}
    if (reduce) return;
    ensureCanvas(); spawn(big ? 170 : mid ? 90 : 45, big ? 0.6 : 0.7);
    if (big) setTimeout(function () { spawn(90, 0.6); }, 700);
    if (!raf) raf = requestAnimationFrame(tick);
  }

  var _fetch = window.fetch;
  if (_fetch) window.fetch = function (input, init) {
    var p = _fetch.apply(this, arguments);
    try {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      if (url.indexOf("/games/") !== -1 || url.indexOf("/blackjack/") !== -1) p.then(function (res) {
        if (!res.ok) return;
        res.clone().json().then(function (d) {
          if (d && d.won === true && Number(d.payout) > 0) {
            var m = Number(d.effective_multiplier || (d.outcome && d.outcome.effective_multiplier) || 0);
            if (!m && Number(d.stake) > 0) m = Number(d.payout) / Number(d.stake);
            celebrate(d.payout, m);
          }
        }).catch(function () {});
      }).catch(function () {});
    } catch (_) {}
    return p;
  };
  window.kdmCelebrate = celebrate;

  /* ------------------------------------------------------------------ per-game themes */
  // key: [colourA, colourB, glow, emblem]
  var T = {
    dice: ["#1d4ed8", "#0b1b44", "#60a5fa", "🎲"], slot: ["#be123c", "#2b0710", "#fb7185", "🎰"], wheel: ["#f59e0b", "#3b2204", "#fde047", "🎡"],
    keno: ["#0d9488", "#04201f", "#5eead4", "🎯"], fastkeno: ["#16a34a", "#04210f", "#86efac", "⚡"], roulette: ["#15803d", "#052e16", "#f87171", "🎡"],
    bingo: ["#7c3aed", "#1e0f3d", "#c4b5fd", "🎱"], aviator: ["#0284c7", "#03162a", "#7dd3fc", "✈️"], jet: ["#ea580c", "#2a0f03", "#fdba74", "🚀"],
    penaltystreak: ["#16a34a", "#04190b", "#bef264", "⚽"], tower: ["#7c3aed", "#14102e", "#c4b5fd", "🏗"],
    dragontiger: ["#dc2626", "#2a0505", "#fca5a5", "🐉"], andarbahar: ["#0d9488", "#03201e", "#5eead4", "🃏"],
    buffalo: ["#ea580c", "#2a1105", "#fdba74", "🦬"], aztec: ["#0f766e", "#0a1f1c", "#fcd34d", "🗿"], flame: ["#c2410c", "#2a0a03", "#fdba74", "🔥"], triplegold: ["#b45309", "#2a1203", "#fcd34d", "🔔"], dice2: ["#1d4ed8", "#0b1b44", "#60a5fa", "🎲"], coinstreak: ["#ca8a04", "#2a1d02", "#fde68a", "🪙"],
    chicken: ["#dc2626", "#2a0707", "#fca5a5", "🐔"], rabbit: ["#db2777", "#2d0a1c", "#f9a8d4", "🐇"], roast: ["#f97316", "#2d1204", "#fdba74", "🔥"],
    mines: ["#6d28d9", "#12082a", "#ddd6fe", "💣"], plinko: ["#a21caf", "#240a2b", "#f0abfc", "🟣"], fish: ["#0891b2", "#031a24", "#67e8f9", "🐟"],
    card: ["#166534", "#04170b", "#bbf7d0", "🃏"], coinflip: ["#ca8a04", "#2a1d02", "#fde68a", "🪙"], penalty: ["#16a34a", "#04190b", "#bef264", "⚽"],
    blackjack: ["#15803d", "#031a0c", "#86efac", "🃏"], baccarat: ["#be123c", "#2a0710", "#fda4af", "🎴"],
    boom: ["#b91c1c", "#240606", "#fecaca", "💥"], number: ["#2563eb", "#071536", "#bfdbfe", "🔢"]
  };
  function theme() {
    var p = document.querySelector(".page.active"); if (!p || p.id.indexOf("page-") !== 0) return;
    var k = p.id.slice(5), t = T[k]; if (!t || p.dataset.gt === k) return;
    p.dataset.gt = k; p.classList.add("gt-themed");
    p.style.setProperty("--gt-a", t[0]); p.style.setProperty("--gt-b", t[1]); p.style.setProperty("--gt-glow", t[2]); p.style.setProperty("--gt-emblem", '"' + t[3] + '"');
  }
  function init() {
    var pages = document.getElementById("pages") || document.body;
    new MutationObserver(theme).observe(pages, { attributes: true, attributeFilter: ["class"], subtree: true, childList: true });
    theme();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
