/* GAME STAGE: original vector scenes for Aviator, Jet, Chicken Road, Rabbit Road, Keno, Fish, Dice, 777 Slot, Lucky Wheel, Plinko, Mines and Card Table.
   Replaces the old primitive WebGL shapes. VISUAL ONLY -- every number shown comes from the server
   outcome that app.js already passes in; nothing here decides or fabricates a result. */
(function () {
  "use strict";
  var KEYS = { aviator: 1, jet: 1, chicken: 1, rabbit: 1, keno: 1, fish: 1, dice: 1, slot: 1, wheel: 1, plinko: 1, mines: 1, card: 1, coinflip: 1, penalty: 1 };
  var stages = {};
  var TAU = Math.PI * 2;

  function rng(seed) { return function () { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; var t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function easeOut(t) { return 1 - Math.pow(1 - clamp(t, 0, 1), 3); }
  function num(v, d) { v = Number(v); return isFinite(v) ? v : d; }
  function rr(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.min(r, w / 2, h / 2)); }
  function text(ctx, s, x, y, size, color, glow, align) {
    ctx.save(); ctx.font = "900 " + size + "px system-ui,sans-serif"; ctx.textAlign = align || "center"; ctx.textBaseline = "middle";
    if (glow) { ctx.shadowColor = glow; ctx.shadowBlur = 18; }
    ctx.fillStyle = color; ctx.fillText(s, x, y); ctx.restore();
  }

  /* ------------------------------------------------------------------ crash games */
  var STARS = (function () { var r = rng(7), a = []; for (var i = 0; i < 70; i++) a.push({ x: r(), y: r(), z: .3 + r() * .9, s: .6 + r() * 1.6 }); return a; })();

  function crashMult(st, o, phase, dt) {
    var live = num(o.live_multiplier, 0);
    var crash = num(o.crash != null ? o.crash : (o.crash_point != null ? o.crash_point : (o.outcome && o.outcome.crash)), 0);
    var cash = num(o.cashout != null ? o.cashout : (o.outcome && o.outcome.cashout), 0);
    var won = phase === "win";
    var target = 1;
    if (phase === "playing") target = live || 1;
    else if (phase === "win") target = cash || live || 1;
    else if (phase === "lose") target = crash || live || 1;
    st.mShown = st.mShown == null ? 1 : st.mShown;
    var rate = phase === "playing" ? 10 : 3.2;                       // per second smoothing
    st.mShown += (target - st.mShown) * Math.min(1, dt * rate);
    if (Math.abs(target - st.mShown) < 0.015) st.mShown = target;
    st.crashed = phase === "lose" && st.mShown === target;
    st.won = won;
    return st.mShown;
  }

  function drawPlane(ctx, x, y, ang, s, alpha) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.scale(s, s); ctx.globalAlpha = alpha;
    var g = ctx.createLinearGradient(-60, 0, -34, 0); g.addColorStop(0, "rgba(255,170,60,0)"); g.addColorStop(1, "rgba(255,200,90,.9)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(-34, -3); ctx.lineTo(-70, 0); ctx.lineTo(-34, 3); ctx.fill();
    ctx.fillStyle = "#7f93b8"; ctx.beginPath(); ctx.moveTo(6, 3); ctx.lineTo(-14, 22); ctx.lineTo(-21, 22); ctx.lineTo(-9, 3); ctx.fill();   // far wing
    ctx.fillStyle = "#ffb13b"; ctx.beginPath(); ctx.moveTo(-26, -4); ctx.lineTo(-36, -19); ctx.lineTo(-41, -19); ctx.lineTo(-33, -3); ctx.fill(); // tail fin
    var b = ctx.createLinearGradient(0, -8, 0, 8); b.addColorStop(0, "#ffffff"); b.addColorStop(1, "#9cc4f2");
    ctx.fillStyle = b; ctx.beginPath(); ctx.moveTo(36, 0); ctx.bezierCurveTo(22, -8, -10, -8, -33, -3); ctx.lineTo(-33, 3); ctx.bezierCurveTo(-10, 8, 22, 8, 36, 0); ctx.fill();
    ctx.fillStyle = "#e9eef7"; ctx.beginPath(); ctx.moveTo(6, -3); ctx.lineTo(-14, -26); ctx.lineTo(-21, -26); ctx.lineTo(-9, -3); ctx.fill();  // near wing
    ctx.fillStyle = "#ff7a2f"; ctx.fillRect(-14, -26, 3, 2);
    ctx.fillStyle = "#1c3350"; ctx.beginPath(); ctx.ellipse(17, -2.5, 7, 3, -.1, 0, TAU); ctx.fill();
    ctx.restore();
  }

  function drawRocket(ctx, x, y, ang, s, T, alpha) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.scale(s, s); ctx.globalAlpha = alpha;
    var fl = 24 + Math.sin(T * 40) * 5 + Math.sin(T * 23) * 4;
    var g = ctx.createLinearGradient(-26, 0, -26 - fl, 0); g.addColorStop(0, "#fff6b0"); g.addColorStop(.4, "#ffa826"); g.addColorStop(1, "rgba(255,80,20,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(-26, -7); ctx.quadraticCurveTo(-26 - fl, 0, -26, 7); ctx.fill();
    ctx.fillStyle = "#c93a4a";                                                                                                  // fins
    ctx.beginPath(); ctx.moveTo(-8, -9); ctx.lineTo(-26, -23); ctx.lineTo(-28, -8); ctx.fill();
    ctx.beginPath(); ctx.moveTo(-8, 9); ctx.lineTo(-26, 23); ctx.lineTo(-28, 8); ctx.fill();
    var b = ctx.createLinearGradient(0, -11, 0, 11); b.addColorStop(0, "#ffffff"); b.addColorStop(1, "#aab6c8");
    ctx.fillStyle = b; ctx.beginPath(); ctx.moveTo(40, 0); ctx.bezierCurveTo(24, -11, -6, -11, -26, -8); ctx.lineTo(-26, 8); ctx.bezierCurveTo(-6, 11, 24, 11, 40, 0); ctx.fill();
    ctx.fillStyle = "#e0394a"; ctx.beginPath(); ctx.moveTo(40, 0); ctx.bezierCurveTo(31, -7, 23, -10, 14, -10.5); ctx.lineTo(14, 10.5); ctx.bezierCurveTo(23, 10, 31, 7, 40, 0); ctx.fill();
    ctx.fillStyle = "#6fd3ff"; ctx.beginPath(); ctx.arc(0, 0, 5.2, 0, TAU); ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.6; ctx.stroke();
    ctx.restore();
  }

  function drawCrash(ctx, w, h, T, dt, st, o, phase, space) {
    var m = crashMult(st, o, phase, dt);
    // background
    var bg = ctx.createLinearGradient(0, 0, 0, h);
    if (space) { bg.addColorStop(0, "#050816"); bg.addColorStop(1, "#150a2e"); } else { bg.addColorStop(0, "#071526"); bg.addColorStop(1, "#0d2d4d"); }
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    var f = 1 - Math.exp(-(m - 1) * 0.30);
    if (space) {
      var neb = ctx.createRadialGradient(w * .75, h * .3, 5, w * .75, h * .3, w * .6); neb.addColorStop(0, "rgba(120,70,220,.28)"); neb.addColorStop(1, "rgba(120,70,220,0)");
      ctx.fillStyle = neb; ctx.fillRect(0, 0, w, h);
      var speed = 14 + f * 160;
      for (var i = 0; i < STARS.length; i++) {
        var s = STARS[i], x = (((s.x * w - T * speed * s.z) % w) + w) % w;
        ctx.fillStyle = "rgba(255,255,255," + (.35 + s.z * .5) + ")"; ctx.fillRect(x, s.y * h, s.s * s.z * (1 + f * 3), s.s * s.z);
      }
      [[.18, .25, 26, "#c98b5a"], [.82, .72, 18, "#4f86c6"]].forEach(function (p, k) {
        var px = (((p[0] * w - T * (6 + f * 40) * (k + 1)) % (w + 120)) + w + 120) % (w + 120) - 60, py = p[1] * h;
        var pg = ctx.createRadialGradient(px - p[2] * .3, py - p[2] * .3, 2, px, py, p[2]); pg.addColorStop(0, "#fff3"); pg.addColorStop(.25, p[3]); pg.addColorStop(1, "#0b0b18");
        ctx.fillStyle = pg; ctx.beginPath(); ctx.arc(px, py, p[2], 0, TAU); ctx.fill();
      });
    } else {
      ctx.save(); ctx.translate(w * .06, h); var rot = Math.sin(T * .25) * .04;
      for (var r = 0; r < 18; r++) {
        var a0 = -Math.PI / 2 + (r / 18) * (Math.PI / 2) + rot, a1 = a0 + (Math.PI / 2) / 36 * 1.6;
        ctx.fillStyle = r % 2 ? "rgba(120,190,255,.07)" : "rgba(120,190,255,.02)";
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, w * 1.6, a0, a1); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
    }
    // axis dots (scroll as the multiplier grows)
    var gap = h * .075, sh = (f * h * .5 + T * 6) % gap;
    ctx.fillStyle = space ? "rgba(190,160,255,.55)" : "rgba(110,200,255,.6)";
    for (var yy = h * .12 + sh; yy < h * .82; yy += gap) { ctx.beginPath(); ctx.arc(w * .05, yy, 2, 0, TAU); ctx.fill(); }
    var gx = w * .09, sx = (f * w * .3 + T * 6) % gx;
    for (var xx = w * .08 + sx; xx < w * .96; xx += gx) { ctx.beginPath(); ctx.arc(xx, h * .9, 2, 0, TAU); ctx.fill(); }
    // curve
    var x0 = w * .10, y0 = h * .80, x1 = x0 + w * .72 * f, y1 = y0 - h * .52 * f, p = 1.9;
    var curve = function (u) { return [x0 + (x1 - x0) * u, y0 - (y0 - y1) * Math.pow(u, p)]; };
    var col = st.crashed ? "#ff5a5a" : (space ? "#ffb347" : "#ffd23f");
    var fly = st.crashed ? clamp((T - (st.crashT || (st.crashT = T))) / 0.9, 0, 1) : 0;
    if (!st.crashed) st.crashT = null;
    if (x1 - x0 > 2) {
      ctx.beginPath(); ctx.moveTo(x0, y0); for (var u = .02; u <= 1.001; u += .02) { var c = curve(u); ctx.lineTo(c[0], c[1]); }
      ctx.lineTo(x1, y0); ctx.closePath();
      var fg = ctx.createLinearGradient(0, y1, 0, y0); fg.addColorStop(0, space ? "rgba(255,140,60,.28)" : "rgba(255,210,63,.24)"); fg.addColorStop(1, "rgba(255,210,63,0)");
      ctx.fillStyle = fg; ctx.fill();
      ctx.beginPath(); ctx.moveTo(x0, y0); for (u = .02; u <= 1.001; u += .02) { c = curve(u); ctx.lineTo(c[0], c[1]); }
      ctx.strokeStyle = col; ctx.lineWidth = 4; ctx.lineCap = "round"; ctx.shadowColor = col; ctx.shadowBlur = 14; ctx.stroke(); ctx.shadowBlur = 0;
    }
    var ang = x1 - x0 > 2 ? -Math.atan2(p * (y0 - y1), (x1 - x0)) : -.12;
    var sc = Math.min(w, h) / 250 * 1.15, bob = Math.sin(T * 3) * 2.5;
    var px = x1 + fly * w * .5, py = y1 + bob - fly * h * .25;
    if (space) drawRocket(ctx, px, py, ang - fly * .3, sc, T, 1 - fly); else drawPlane(ctx, px, py, ang - fly * .3, sc, 1 - fly);
    // multiplier
    var big = Math.min(w * .17, 66);
    var mc = st.crashed ? "#ff6b6b" : (st.won ? "#6dff9e" : (m >= 2 ? "#ffe066" : "#ffffff"));
    text(ctx, m.toFixed(2) + "×", w / 2, h * .30, big, mc, mc);
    var sub = st.crashed ? (space ? "ROCKET LOST" : "FLEW AWAY!") : st.won ? "CASHED OUT" : phase === "playing" ? "" : "";
    if (sub) text(ctx, sub, w / 2, h * .30 + big * .75, 15, mc, null);
    return st.crashed ? "CRASHED" : st.won ? "WIN" : null;
  }

  /* ------------------------------------------------------------------ chicken / rabbit road */
  function drawAnimal(ctx, rabbit, x, y, s, T, squash) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s * (squash ? .35 : 1)); if (squash) ctx.translate(0, 0);
    ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.beginPath(); ctx.ellipse(0, 2, 28, 7, 0, 0, TAU); ctx.fill();
    ctx.strokeStyle = rabbit ? "#e9b7c9" : "#f3a43a"; ctx.lineWidth = 4; ctx.lineCap = "round";
    var lg = Math.sin(T * 14) * 4;
    ctx.beginPath(); ctx.moveTo(-6, -12); ctx.lineTo(-6 + lg, 0); ctx.moveTo(8, -12); ctx.lineTo(8 - lg, 0); ctx.stroke();
    var g = ctx.createRadialGradient(-6, -40, 4, 0, -30, 34); g.addColorStop(0, "#ffffff"); g.addColorStop(1, rabbit ? "#e8dfe6" : "#dfe6ee");
    ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(0, -30, 29, 24, 0, 0, TAU); ctx.fill();
    if (rabbit) {
      ctx.beginPath(); ctx.arc(-29, -30, 8, 0, TAU); ctx.fill();                          // tail
      ctx.beginPath(); ctx.arc(22, -50, 14, 0, TAU); ctx.fill();                          // head
      ctx.save(); ctx.translate(16, -60); ctx.rotate(-.25); ctx.beginPath(); ctx.ellipse(0, -14, 5, 17, 0, 0, TAU); ctx.fill(); ctx.fillStyle = "#f7b9cf"; ctx.beginPath(); ctx.ellipse(0, -14, 2.4, 12, 0, 0, TAU); ctx.fill(); ctx.restore();
      ctx.fillStyle = "#fff"; ctx.save(); ctx.translate(26, -60); ctx.rotate(.1); ctx.beginPath(); ctx.ellipse(0, -14, 5, 17, 0, 0, TAU); ctx.fill(); ctx.restore();
      ctx.fillStyle = "#f08ab0"; ctx.beginPath(); ctx.arc(34, -48, 2.6, 0, TAU); ctx.fill();
    } else {
      ctx.fillStyle = "#eef2f7"; for (var k = 0; k < 3; k++) { ctx.beginPath(); ctx.ellipse(-30 + k * 3, -44 + k * 9, 9, 6, -.5 + k * .3, 0, TAU); ctx.fill(); }  // tail
      ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(22, -52, 14, 0, TAU); ctx.fill();   // head
      ctx.fillStyle = "#e5392f"; [14, 21, 28].forEach(function (cx, i) { ctx.beginPath(); ctx.arc(cx, -67 - (i === 1 ? 3 : 0), 5, 0, TAU); ctx.fill(); });  // comb
      ctx.fillStyle = "#f6a21e"; ctx.beginPath(); ctx.moveTo(34, -55); ctx.lineTo(46, -51); ctx.lineTo(34, -47); ctx.fill();   // beak
      ctx.fillStyle = "#e5392f"; ctx.beginPath(); ctx.arc(32, -42, 4, 0, TAU); ctx.fill();   // wattle
    }
    ctx.fillStyle = "#c9d3df"; ctx.beginPath(); ctx.ellipse(-6, -28, 14, 10, -.3, 0, TAU); ctx.fill();   // wing
    ctx.fillStyle = "#111"; ctx.beginPath(); ctx.arc(27, -55, 2.6, 0, TAU); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(28, -56, .9, 0, TAU); ctx.fill();
    ctx.restore();
  }

  function drawCar(ctx, x, y, s, color) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.fillStyle = "rgba(0,0,0,.35)"; rr(ctx, -20, -34, 46, 74, 10); ctx.fill();
    ctx.fillStyle = color; rr(ctx, -24, -40, 46, 76, 10); ctx.fill();
    ctx.fillStyle = "rgba(20,30,50,.85)"; rr(ctx, -19, -20, 36, 14, 4); ctx.fill(); rr(ctx, -19, 8, 36, 12, 4); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.35)"; rr(ctx, -20, -38, 8, 5, 2); ctx.fill(); rr(ctx, 6, -38, 8, 5, 2); ctx.fill();
    ctx.restore();
  }

  function drawRoad(ctx, w, h, T, dt, st, o, phase, key) {
    var rabbit = key === "rabbit", steps = clamp(Math.round(num(o.steps, 3)), 1, 12);
    var domSteps = document.getElementById(key + "-steps"); if (!o.steps && domSteps) steps = clamp(Math.round(num(domSteps.value, 3)), 1, 12);
    var gap = w * .30, startX = w * .16, X0 = startX + gap * .45, cy = h * .52;
    if (st.phaseKey !== phase + "|" + st.pt0) { st.phaseKey = phase + "|" + st.pt0; }
    var pt = (performance.now() - st.pt0) / 1000, hop = .34;
    var pos = (phase === "win" || phase === "lose") ? Math.min(steps, pt / hop) : (phase === "playing" ? Math.min(steps, pt / hop * .8) : 0);
    var arrived = (phase === "win" || phase === "lose") && pos >= steps, ta = steps * hop;
    var wx = startX + pos * gap, cam = Math.max(0, wx - w * .30);
    // ground
    ctx.fillStyle = "#3f4046"; ctx.fillRect(0, 0, w, h);
    var rg = ctx.createLinearGradient(0, 0, 0, h); rg.addColorStop(0, "rgba(255,255,255,.05)"); rg.addColorStop(.5, "rgba(0,0,0,0)"); rg.addColorStop(1, "rgba(0,0,0,.25)");
    ctx.fillStyle = rg; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.lineWidth = 3; ctx.setLineDash([22, 18]); ctx.lineDashOffset = cam; ctx.beginPath(); ctx.moveTo(0, cy + h * .20); ctx.lineTo(w, cy + h * .20); ctx.moveTo(0, cy - h * .20); ctx.lineTo(w, cy - h * .20); ctx.stroke(); ctx.setLineDash([]);
    // sidewalk
    var swx = X0 - cam;
    if (swx > 0) {
      ctx.fillStyle = "#b9b4aa"; ctx.fillRect(0, 0, swx, h);
      ctx.strokeStyle = "rgba(0,0,0,.14)"; ctx.lineWidth = 1;
      for (var by = 0; by < h; by += 26) { ctx.beginPath(); ctx.moveTo(0, by); ctx.lineTo(swx, by); ctx.stroke(); for (var bx = (by / 26 % 2) * 22 - cam % 44; bx < swx; bx += 44) { ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx, by + 26); ctx.stroke(); } }
      ctx.fillStyle = "#8c877e"; ctx.fillRect(swx - 8, 0, 8, h);
      ctx.fillStyle = "#2f7d3a"; ctx.beginPath(); ctx.arc(-cam + w * .06, h * .12, 44, 0, TAU); ctx.fill(); ctx.fillStyle = "#3e9b4a"; ctx.beginPath(); ctx.arc(-cam + w * .06 - 8, h * .12 - 8, 30, 0, TAU); ctx.fill();
      ctx.fillStyle = "#2f7d3a"; rr(ctx, -cam + 4, h * .78, 60, 40, 14); ctx.fill();
    }
    // manholes
    var nShow = 12;
    for (var i = 1; i <= nShow; i++) {
      var mx = startX + i * gap - cam; if (mx < -50 || mx > w + 50) continue;
      var passed = i <= Math.floor(pos + .001), target = i === steps;
      var rad = Math.min(w, h) * .11;
      var gg = ctx.createRadialGradient(mx - rad * .3, cy - rad * .3, 2, mx, cy, rad); gg.addColorStop(0, passed ? "#5fe08c" : "#8b8d94"); gg.addColorStop(1, passed ? "#1c7a45" : "#4a4c53");
      ctx.fillStyle = gg; ctx.beginPath(); ctx.arc(mx, cy, rad, 0, TAU); ctx.fill();
      ctx.lineWidth = 4; ctx.strokeStyle = target && phase !== "idle" ? "rgba(255,216,74," + (.6 + .4 * Math.sin(T * 6)) + ")" : "rgba(0,0,0,.45)"; ctx.stroke();
      ctx.strokeStyle = "rgba(0,0,0,.25)"; ctx.lineWidth = 2; for (var k = -2; k <= 2; k++) { ctx.beginPath(); ctx.moveTo(mx - rad * .6, cy + k * rad * .22); ctx.lineTo(mx + rad * .6, cy + k * rad * .22); ctx.stroke(); }
      text(ctx, passed ? "✓" : String(i), mx, cy, rad * .85, passed ? "#eafff1" : "#e7e9ee", null);
    }
    // chicken position
    var hopY = 0, moving = pos < steps && (phase === "win" || phase === "lose" || phase === "playing");
    if (moving) hopY = -Math.abs(Math.sin(Math.PI * (pos % 1))) * h * .10;
    var idleBob = phase === "idle" ? Math.sin(T * 3) * 2 : 0;
    var charX = wx - cam, hit = phase === "lose" && arrived && (pt - ta) > .05;
    var sc = Math.min(w, h) / 300 * 1.25;
    drawAnimal(ctx, rabbit, charX, cy + h * .06 + hopY + idleBob, sc, T, hit && (pt - ta) > .30);
    // car hit
    if (hit) {
      var ct = clamp((pt - ta - .05) / .30, 0, 1), carY = lerp(-90, cy + h * .06, easeOut(ct));
      drawCar(ctx, charX + 4, carY, sc * 1.1, "#d83b3b");
      if (ct >= 1) { var bt = clamp((pt - ta - .35) / .4, 0, 1); ctx.save(); ctx.globalAlpha = 1 - bt; ctx.fillStyle = "#ffd84a"; ctx.beginPath(); for (var q = 0; q < 16; q++) { var a = q / 16 * TAU, r = (q % 2 ? 26 : 52) * (.6 + bt); ctx.lineTo(charX + Math.cos(a) * r, cy - h * .02 + Math.sin(a) * r); } ctx.closePath(); ctx.fill(); ctx.restore(); }
    }
    if (phase === "win" && arrived) {
      var wt = pt - ta;
      for (var c = 0; c < 10; c++) { var an = c / 10 * TAU, rad2 = easeOut(wt * 1.6) * 60; ctx.fillStyle = "rgba(255,216,74," + clamp(1 - wt * .8, 0, 1) + ")"; ctx.beginPath(); ctx.arc(charX + Math.cos(an) * rad2, cy - 30 + Math.sin(an) * rad2, 4, 0, TAU); ctx.fill(); }
    }
    // labels
    var mult = num(o.multiplier != null ? o.multiplier : o.effective_multiplier, null);
    var label = phase === "win" && arrived ? (mult != null ? mult.toFixed(2) + "× · " : "") + "SAFE!" : (phase === "lose" && hit ? "CRASH!" : steps + (steps === 1 ? " STEP" : " STEPS"));
    var lc = phase === "win" ? "#6dff9e" : (phase === "lose" && hit ? "#ff6b6b" : "#ffd84a");
    text(ctx, label, w / 2, h * .92, 20, lc, "rgba(0,0,0,.9)");
    return phase === "win" && arrived ? "WIN" : (phase === "lose" && hit ? "CRASHED" : null);
  }

  /* ------------------------------------------------------------------ keno */
  /* Classic Keno (1-10 of 80). Multipliers come from the server (/games/keno/settings -> keno_tables, edge applied). */
  var KN = window.__keno = window.__keno || { tables: null, loading: false };
  function knLoad() {
    if (KN.tables || KN.loading || typeof apiFetch !== "function") return;
    KN.loading = true;
    apiFetch("/games/keno/settings").then(function (r) { if (r && r.keno_tables) KN.tables = r.keno_tables; KN.loading = false; knRefresh(); }, function () { KN.loading = false; });
  }
  function knSel() { return Array.prototype.slice.call(document.querySelectorAll("#keno-controls .choice-btn.selected")); }
  function knFmt(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1) : m.toFixed(2); }
  function knRefresh() {
    var cnt = document.getElementById("kn-count"), pay = document.getElementById("kn-pay"); if (!cnt || !pay) return;
    var n = knSel().length; cnt.textContent = "Picked " + n + " / 10";
    if (!n) { pay.innerHTML = "<small>Pick 1–10 numbers · 20 balls are drawn from 80</small>"; return; }
    var t = KN.tables && KN.tables[String(n)]; if (!t) { pay.innerHTML = "<small>…</small>"; knLoad(); return; }
    var h = ""; for (var k = 0; k < t.length; k++) if (t[k] > 0) h += "<span class=\"kn-cell\"><b>" + k + " hits</b><i>×" + knFmt(t[k]) + "</i></span>";
    pay.innerHTML = h;
  }
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest && e.target.closest("#keno-controls .choice-btn, #kn-auto, #kn-clear"); if (!t) return;
    if (t.id === "kn-clear") knSel().forEach(function (b) { b.classList.remove("selected"); });
    else if (t.id === "kn-auto") {
      var want = Math.min(10, Math.max(1, knSel().length || 5)), all = Array.prototype.slice.call(document.querySelectorAll("#keno-controls .choice-btn"));
      all.forEach(function (b) { b.classList.remove("selected"); });
      for (var i = all.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), x = all[i]; all[i] = all[j]; all[j] = x; }
      all.slice(0, want).forEach(function (b) { b.classList.add("selected"); });
    }
    setTimeout(knRefresh, 0);
  });
  function drawKeno(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createRadialGradient(w / 2, h * .45, 10, w / 2, h * .5, h * .9); bg.addColorStop(0, "#0e4f52"); bg.addColorStop(1, "#04161a");
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(120,255,230,.10)"; ctx.lineWidth = 2; for (var ring = 0; ring < 3; ring++) { ctx.beginPath(); ctx.arc(w / 2, h * .5, h * (.30 + ring * .12) + Math.sin(T + ring) * 3, 0, TAU); ctx.stroke(); }
    var chosen = Array.isArray(o.chosen) ? o.chosen : Array.isArray(o.selected) ? o.selected : null;
    if (!chosen) { chosen = []; document.querySelectorAll("#keno-controls .choice-btn.selected").forEach(function (b) { chosen.push(Number(b.dataset.value)); }); }
    var draw = Array.isArray(o.draw) ? o.draw : [];
    var pt = (performance.now() - st.pt0) / 1000, resulting = phase === "win" || phase === "lose";
    var big = o.grid === 80 || !!document.querySelector("#keno-controls .kn80");   // classic 80-ball board
    var POOL = big ? 80 : 20, STEP = big ? .11 : .25, cols = big ? 10 : 5, rows = big ? 8 : 4, cell = Math.min((w * (big ? .96 : .90)) / cols, (h * (big ? .70 : .66)) / rows), r = cell * (big ? .42 : .40);
    var sx = w / 2 - (cols - 1) * cell / 2, sy = h * .47 - (rows - 1) * cell / 2, hits = 0, revealed = 0;
    for (var n = 1; n <= POOL; n++) {
      var i = n - 1, bx = sx + (i % cols) * cell, by = sy + Math.floor(i / cols) * cell;
      var di = draw.indexOf(n), isDrawn = di >= 0, isChosen = chosen.indexOf(n) >= 0;
      var show = resulting && isDrawn && pt > STEP * di + .15;
      if (show) { revealed++; if (isChosen) hits++; }
      var shake = phase === "playing" || (resulting && pt < .15 + STEP * draw.length && !show) ? (big ? 1.5 : 3) : 0;
      bx += Math.sin(T * 25 + n * 3) * shake; by += Math.cos(T * 21 + n * 5) * shake;
      var pop = show ? 1 + .30 * Math.max(0, 1 - (pt - (STEP * di + .15)) / .3) : 1;
      var rad = r * pop, base1, base2;
      if (show) { base1 = "#8bffb8"; base2 = "#0f9d55"; } else { base1 = "#4a86d9"; base2 = "#0d2550"; }
      var g = ctx.createRadialGradient(bx - rad * .35, by - rad * .4, rad * .1, bx, by, rad); g.addColorStop(0, base1); g.addColorStop(1, base2);
      if (show) { ctx.shadowColor = "#5dffa5"; ctx.shadowBlur = 16; }
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(bx, by, rad, 0, TAU); ctx.fill(); ctx.shadowBlur = 0;
      if (isChosen) { ctx.lineWidth = 3.5; ctx.strokeStyle = "#ffd23f"; ctx.shadowColor = "#ffd23f"; ctx.shadowBlur = 8; ctx.beginPath(); ctx.arc(bx, by, rad + 2, 0, TAU); ctx.stroke(); ctx.shadowBlur = 0; }
      ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.beginPath(); ctx.ellipse(bx - rad * .3, by - rad * .5, rad * .35, rad * .18, -.5, 0, TAU); ctx.fill();
      text(ctx, String(n), bx, by + 1, rad * (big ? .85 : .95), show ? "#073d22" : (isChosen ? "#ffe27a" : "#e8f1ff"), null);
    }
    var cnt = Number.isFinite(Number(o.hits)) ? Number(o.hits) : hits;
    var done = resulting && revealed >= draw.length;
    text(ctx, done ? "HITS " + cnt + (num(o.multiplier, 0) > 0 ? " · " + Number(o.multiplier).toFixed(2) + "×" : "") : (phase === "playing" ? "DRAWING…" : (big ? "PICK 1–10 NUMBERS" : "PICK 5 NUMBERS")), w / 2, h * .92, 19, done && cnt > 0 ? "#6dff9e" : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  /* ------------------------------------------------------------------ fish */
  var BUBBLES = (function () { var r = rng(3), a = []; for (var i = 0; i < 26; i++) a.push({ x: r(), y: r(), s: 1 + r() * 3, v: 10 + r() * 26 }); return a; })();
  var FISHCOL = ["#4fc3f7", "#ffb74d", "#81c784", "#ba68c8", "#ff8a65"];

  function drawFishShape(ctx, x, y, s, col, T, flip) {
    ctx.save(); ctx.translate(x, y); ctx.scale(flip ? -s : s, s);
    var wag = Math.sin(T * 9 + x * .05) * 6;
    ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(-22, 0); ctx.lineTo(-40, -12 + wag); ctx.lineTo(-40, 12 + wag); ctx.closePath(); ctx.fill();
    var g = ctx.createLinearGradient(0, -16, 0, 16); g.addColorStop(0, "#fff9"); g.addColorStop(.35, col); g.addColorStop(1, "#0006");
    ctx.fillStyle = col; ctx.beginPath(); ctx.ellipse(0, 0, 28, 15, 0, 0, TAU); ctx.fill();
    ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(0, 0, 28, 15, 0, 0, TAU); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.beginPath(); ctx.moveTo(-4, -14); ctx.quadraticCurveTo(6, -28, 16, -12); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(17, -3, 4.2, 0, TAU); ctx.fill(); ctx.fillStyle = "#101820"; ctx.beginPath(); ctx.arc(18, -3, 2.2, 0, TAU); ctx.fill();
    ctx.restore();
  }

  function drawFish(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createLinearGradient(0, 0, 0, h); bg.addColorStop(0, "#0b5c86"); bg.addColorStop(1, "#021622"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    for (var k = 0; k < 4; k++) { var lx = w * (.1 + k * .27) + Math.sin(T * .4 + k) * 20; ctx.fillStyle = "rgba(160,230,255,.06)"; ctx.beginPath(); ctx.moveTo(lx, 0); ctx.lineTo(lx + 50, 0); ctx.lineTo(lx + 140, h); ctx.lineTo(lx + 60, h); ctx.fill(); }
    ctx.fillStyle = "#1a3b3a"; ctx.beginPath(); ctx.moveTo(0, h); for (var sx = 0; sx <= w; sx += 20) ctx.lineTo(sx, h * .90 + Math.sin(sx * .03) * 6); ctx.lineTo(w, h); ctx.fill();
    ctx.strokeStyle = "#2f9a62"; ctx.lineWidth = 5; ctx.lineCap = "round";
    [.12, .3, .62, .88].forEach(function (px, i) { ctx.beginPath(); ctx.moveTo(w * px, h * .93); ctx.quadraticCurveTo(w * px + Math.sin(T * 1.5 + i) * 14, h * .84, w * px + Math.sin(T * 1.5 + i + 1) * 10, h * .74); ctx.stroke(); });
    ctx.fillStyle = "rgba(210,245,255,.45)";
    BUBBLES.forEach(function (b) { var yy = (((b.y * h - T * b.v) % h) + h) % h; ctx.beginPath(); ctx.arc(b.x * w + Math.sin(T + b.y * 9) * 5, yy, b.s, 0, TAU); ctx.fill(); });
    var shotDom = document.getElementById("fish-shot"), shot = clamp(Math.round(num(o.shot, shotDom ? num(shotDom.value, 1) : 1)), 1, 5);
    var pt = (performance.now() - st.pt0) / 1000, resulting = phase === "win" || phase === "lose", mult = num(o.multiplier, 0);
    var sc = Math.min(w, h) / 310 * 1.15, label = null;
    for (var i = 1; i <= 5; i++) {
      var sp = 28 + i * 7, off = i * 97, cycle = w + 160, fx = (((off + T * sp) % cycle) + cycle) % cycle - 80, fy = h * (.20 + (i - 1) * .13) + Math.sin(T * 1.7 + i) * 6;
      var isT = i === shot, caught = isT && resulting && mult > 0 && pt > .45, missed = isT && resulting && mult <= 0 && pt > .45;
      if (missed) fx += (pt - .45) * 260;
      var alpha = caught ? clamp(1 - (pt - .9) * 2, 0, 1) : 1;
      if (alpha > 0) { ctx.save(); ctx.globalAlpha = alpha; if (caught) { ctx.shadowColor = "#ffd84a"; ctx.shadowBlur = 24; } drawFishShape(ctx, fx, fy, sc * (isT ? 1.12 : 1), FISHCOL[i - 1], T, false); ctx.restore(); }
      if (isT) {
        var rad = (24 + Math.sin(T * 6) * 3) * sc * 1.1 + (resulting ? Math.max(0, 1 - pt) * 16 : 0);
        ctx.lineWidth = 3; ctx.strokeStyle = resulting ? (mult > 0 ? "#6dff9e" : "#ff8080") : "#ffe066";
        if (alpha > .2) { ctx.beginPath(); ctx.arc(fx, fy, rad, 0, TAU); ctx.moveTo(fx - rad - 8, fy); ctx.lineTo(fx - rad + 8, fy); ctx.moveTo(fx + rad - 8, fy); ctx.lineTo(fx + rad + 8, fy); ctx.moveTo(fx, fy - rad - 8); ctx.lineTo(fx, fy - rad + 8); ctx.moveTo(fx, fy + rad - 8); ctx.lineTo(fx, fy + rad + 8); ctx.stroke(); }
        if (caught) {
          for (var b = 0; b < 12; b++) { var a = b / 12 * TAU, rr2 = (pt - .45) * 120; ctx.fillStyle = "rgba(255,255,255," + clamp(1 - (pt - .45), 0, 1) + ")"; ctx.beginPath(); ctx.arc(fx + Math.cos(a) * rr2, fy + Math.sin(a) * rr2, 3, 0, TAU); ctx.fill(); }
          text(ctx, "+" + mult.toFixed(2) + "×", clamp(fx, 50, w - 50), Math.max(34, fy - 36 - Math.min(24, (pt - .45) * 40)), 26, "#ffe066", "#000");
        }
      }
    }
    if (resulting && pt > .6) label = mult > 0 ? mult.toFixed(2) + "× · CAUGHT!" : "MISSED";
    text(ctx, label || (resulting ? "…" : "TARGET " + shot), w / 2, h * .94, 19, resulting && mult > 0 ? "#6dff9e" : (resulting && label ? "#ff9a9a" : "#ffd84a"), "rgba(0,0,0,.8)");
    return resulting && label ? (mult > 0 ? "WIN" : "RESULT") : null;
  }

  /* ------------------------------------------------------------------ dice / slot / wheel / plinko / mines / card
     Same original vector style as the six scenes above. VISUAL ONLY: all values come from the server outcome `o`. */
  function pips(ctx, n, cx, cy, s) {
    var P = { 1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]], 4: [[-1, -1], [1, -1], [-1, 1], [1, 1]], 5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]], 6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]] }[n] || [];
    ctx.fillStyle = "#1b2433"; P.forEach(function (p) { ctx.beginPath(); ctx.arc(cx + p[0] * s * .26, cy + p[1] * s * .26, s * .075, 0, TAU); ctx.fill(); });
  }
  function drawDie(ctx, x, y, s, face, rot, glow) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot);
    ctx.fillStyle = "rgba(0,0,0,.35)"; rr(ctx, -s / 2 + 5, -s / 2 + 9, s, s, s * .2); ctx.fill();
    var g = ctx.createLinearGradient(-s / 2, -s / 2, s / 2, s / 2); g.addColorStop(0, "#ffffff"); g.addColorStop(1, "#c9d3e3");
    if (glow) { ctx.shadowColor = glow; ctx.shadowBlur = 26; }
    ctx.fillStyle = g; rr(ctx, -s / 2, -s / 2, s, s, s * .2); ctx.fill(); ctx.shadowBlur = 0;
    pips(ctx, face, 0, 0, s); ctx.restore();
  }
  function drawDice(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createRadialGradient(w / 2, h * .5, 10, w / 2, h * .5, h); bg.addColorStop(0, "#1f6b4a"); bg.addColorStop(1, "#06241a"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(255,255,255,.08)"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(w / 2, h * .5, h * .38, 0, TAU); ctx.stroke();
    var pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose", roll = clamp(Math.round(num(o.roll, 0)), 0, 6);
    var guessDom = document.getElementById("dice-value"), guess = clamp(Math.round(num(o.guess, guessDom ? num(guessDom.value, 0) : 0)), 0, 6);
    var s = Math.min(w, h) * .32, tumbling = phase === "playing" || (res && pt < .9), face = roll || 1, x = w / 2, y = h * .46, rot = 0;
    if (tumbling) { face = 1 + Math.floor(T * 14) % 6; rot = Math.sin(T * 17) * .6; x += Math.sin(T * 11) * w * .08; y += -Math.abs(Math.sin(T * 9)) * h * .14; }
    else if (res) { var b = Math.max(0, 1 - (pt - .9) * 3); y -= Math.abs(Math.sin((pt - .9) * 14)) * b * h * .10; }
    else { face = guess || 1; y += Math.sin(T * 2) * 3; }
    var done = res && pt >= .9;
    drawDie(ctx, x, y, s, face, rot, done && phase === "win" ? "#6dff9e" : null);
    var mult = num(o.multiplier, 0), lbl = done ? (phase === "win" ? "ROLLED " + roll + (mult ? " · " + mult.toFixed(2) + "×" : "") + " · WIN!" : "ROLLED " + roll + " · MISS") : (phase === "playing" ? "ROLLING…" : (guess ? "YOUR PICK: " + guess : "PICK 1–6"));
    text(ctx, lbl, w / 2, h * .90, 19, done ? (phase === "win" ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  var SLOTSYM = ["🍒", "🍋", "🔔", "⭐", "7️⃣"];
  function drawSlot(ctx, w, h, T, dt, st, o, phase) {
    var sk = (window.kdmSlotSkin && window.kdmSlotSkin()) || null, sm = sk ? sk.map : function (s) { return s; };
    var bg = ctx.createLinearGradient(0, 0, 0, h); bg.addColorStop(0, sk ? sk.c1 : "#2a0a3d"); bg.addColorStop(1, sk ? sk.c2 : "#0d0318"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    if (sk) { ctx.save(); ctx.globalAlpha = .13; ctx.font = Math.floor(h * .8) + "px system-ui,sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(sk.icon, w / 2, h * .5); ctx.restore(); }
    for (var k = 0; k < 14; k++) { ctx.fillStyle = (Math.floor(T * 3) + k) % 2 ? "#ffd23f" : "#6b4a10"; ctx.beginPath(); ctx.arc(w * (.06 + k * .0723), h * .07, 3, 0, TAU); ctx.fill(); ctx.beginPath(); ctx.arc(w * (.06 + k * .0723), h * .80, 3, 0, TAU); ctx.fill(); }
    var pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose", reels = Array.isArray(o.reels) ? o.reels : [];
    var rw = Math.min(w * .26, 110), rh = h * .56, gap = rw * .14, x0 = w / 2 - (3 * rw + 2 * gap) / 2, y0 = h * .16, cell = rh / 1.6, stopped = 0;
    for (var r = 0; r < 3; r++) {
      var x = x0 + r * (rw + gap), stopAt = .6 + r * .45, spinning = phase === "playing" || (res && pt < stopAt) || (res && !reels.length);
      if (res && pt >= stopAt) stopped++;
      ctx.save(); rr(ctx, x, y0, rw, rh, 12); ctx.clip();
      var rg = ctx.createLinearGradient(0, y0, 0, y0 + rh); rg.addColorStop(0, "#9a9fb0"); rg.addColorStop(.5, "#ffffff"); rg.addColorStop(1, "#9a9fb0"); ctx.fillStyle = rg; ctx.fillRect(x, y0, rw, rh);
      ctx.font = Math.floor(cell * .62) + "px system-ui,sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      if (spinning) { var off = (T * (9 + r) * cell * .9) % cell; for (var j = -1; j < 3; j++) { ctx.globalAlpha = .75; ctx.fillStyle = "#222"; ctx.fillText(sm(SLOTSYM[((Math.floor(T * 9 + r * 2) + j) % 5 + 5) % 5]), x + rw / 2, y0 + rh / 2 + (j - .5) * cell + off); } }
      else { var bounce = res ? Math.max(0, 1 - (pt - stopAt) * 4) * Math.sin((pt - stopAt) * 30) * 6 : 0; ctx.fillStyle = "#222"; ctx.fillText(sm(reels[r] || SLOTSYM[[4, 3, 0][r]]), x + rw / 2, y0 + rh / 2 + bounce); }
      var sh = ctx.createLinearGradient(0, y0, 0, y0 + rh); sh.addColorStop(0, "rgba(0,0,0,.45)"); sh.addColorStop(.3, "rgba(0,0,0,0)"); sh.addColorStop(.7, "rgba(0,0,0,0)"); sh.addColorStop(1, "rgba(0,0,0,.45)"); ctx.fillStyle = sh; ctx.fillRect(x, y0, rw, rh);
      ctx.restore();
      ctx.strokeStyle = sk ? sk.frame : "#ffd23f"; ctx.lineWidth = 4; rr(ctx, x, y0, rw, rh, 12); ctx.stroke();
    }
    var done = res && stopped === 3, mult = num(o.multiplier, 0);
    if (done && phase === "win") { ctx.strokeStyle = "rgba(109,255,158," + (.5 + .5 * Math.sin(T * 10)) + ")"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(x0 - 8, y0 + rh / 2); ctx.lineTo(x0 + 3 * rw + 2 * gap + 8, y0 + rh / 2); ctx.stroke(); }
    var lbl = done ? (phase === "win" ? mult.toFixed(2) + "× · " + (mult >= 12 ? "JACKPOT!" : "WIN!") : "NO MATCH") : (phase === "playing" || res ? "SPINNING…" : "SPIN TO PLAY");
    text(ctx, lbl, w / 2, h * .90, 20, done ? (phase === "win" ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  var WHEELCOL = ["#e5392f", "#f6a21e", "#2f9e6b", "#3b82f6", "#a855f7"];
  function drawWheel(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createRadialGradient(w / 2, h * .5, 10, w / 2, h * .5, h); bg.addColorStop(0, "#3b1d6e"); bg.addColorStop(1, "#0c0620"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    var prizes = Array.isArray(o.prizes) && o.prizes.length ? o.prizes : null, n = prizes ? prizes.length : 10, sector = clamp(Math.round(num(o.sector, 0)), 0, n);
    var pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose", R = Math.min(w * .42, h * .40), cx = w / 2, cy = h * .48, seg = TAU / n;
    var target = -(sector - .5) * seg, rot;                                   // sector centre under the top pointer
    if (res && sector) { var k = easeOut(pt / 3); rot = lerp(T * 6 % TAU, target - TAU * 4, k) ; if (pt >= 3) rot = target; }
    else if (phase === "playing") rot = T * 7; else rot = Math.sin(T * .5) * .08;
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot - Math.PI / 2 + Math.PI / 2);
    for (var i = 0; i < n; i++) {
      var a0 = -Math.PI / 2 + i * seg, a1 = a0 + seg, win = res && pt >= 3 && i === sector - 1;
      ctx.fillStyle = win ? "#6dff9e" : WHEELCOL[i % WHEELCOL.length]; ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, R, a0, a1); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,.7)"; ctx.lineWidth = 2; ctx.stroke();
      if (prizes) { ctx.save(); ctx.rotate((a0 + a1) / 2); text(ctx, prizes[i] > 0 ? prizes[i] + "×" : "✕", R * .66, 0, R * .13, "#fff", null); ctx.restore(); }
    }
    ctx.restore();
    var hub = ctx.createRadialGradient(cx - 4, cy - 4, 2, cx, cy, R * .16); hub.addColorStop(0, "#fff3b0"); hub.addColorStop(1, "#c8901a"); ctx.fillStyle = hub; ctx.beginPath(); ctx.arc(cx, cy, R * .16, 0, TAU); ctx.fill();
    ctx.lineWidth = 6; ctx.strokeStyle = "#ffd23f"; ctx.beginPath(); ctx.arc(cx, cy, R + 3, 0, TAU); ctx.stroke();
    ctx.fillStyle = "#fff"; ctx.shadowColor = "#000"; ctx.shadowBlur = 8; ctx.beginPath(); ctx.moveTo(cx - 12, cy - R - 14); ctx.lineTo(cx + 12, cy - R - 14); ctx.lineTo(cx, cy - R + 8); ctx.fill(); ctx.shadowBlur = 0;
    var done = res && pt >= 3, mult = num(o.multiplier, 0);
    text(ctx, done ? (mult > 0 ? mult.toFixed(2) + "× · WIN!" : "NO PRIZE") : (phase === "playing" || res ? "SPINNING…" : "SPIN THE WHEEL"), w / 2, h * .92, 20, done ? (mult > 0 ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  var PLINKO_M = [0, .5, .8, 1, 1.2, 1.5, 2, 3, 5];
  /* Plinko: Risk (low/med/high) x Rows (8/12/16). The multipliers on the board come from the server
     (/games/plinko/settings -> plinko_tables, disclosed edge already applied); the legacy 8-row board is the fallback. */
  var PL = window.__plinko = window.__plinko || { risk: "med", rows: 12, tables: null, loading: false };
  function plinkoLoad() {
    if (PL.tables || PL.loading || typeof apiFetch !== "function") return;
    PL.loading = true;
    apiFetch("/games/plinko/settings").then(function (r) { if (r && r.plinko_tables) PL.tables = r.plinko_tables; PL.loading = false; }, function () { PL.loading = false; });
  }
  document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest && e.target.closest(".pl-opt"); if (!b) return;
    var grp = b.parentNode;
    if (b.dataset.risk) PL.risk = b.dataset.risk; if (b.dataset.rows) PL.rows = parseInt(b.dataset.rows, 10) || 12;
    Array.prototype.forEach.call(grp.querySelectorAll(".pl-opt"), function (x) { x.classList.toggle("on", x === b); });
  });
  function plFmt(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(0) : m >= 1 ? m.toFixed(1) : (m.toFixed(2)).replace(/^0/, ""); }
  function drawPlinko(ctx, w, h, T, dt, st, o, phase) {
    plinkoLoad();
    var bg = ctx.createLinearGradient(0, 0, 0, h); bg.addColorStop(0, "#1b0f3a"); bg.addColorStop(1, "#08041a"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    var res = phase === "win" || phase === "lose";
    var newMode = !!(o && o.risk) || !!PL.tables;
    var rows = (o && o.rows) ? o.rows : (newMode ? PL.rows : 8), risk = (o && o.risk) ? o.risk : PL.risk;
    var tbl = (PL.tables && PL.tables[risk] && PL.tables[risk][String(rows)]) || null;
    if (!tbl) { rows = 8; tbl = PLINKO_M; }
    var dx = Math.min(w / (rows + 2.4), 46), dy = (h * .62) / rows, top = h * .10, cx = w / 2;
    ctx.fillStyle = "rgba(255,255,255,.75)";
    for (var r = 0; r < rows; r++) for (var j = 0; j <= r; j++) { ctx.beginPath(); ctx.arc(cx + (j - r / 2) * dx, top + r * dy + dy, rows > 12 ? 2.4 : 3.2, 0, TAU); ctx.fill(); }
    var path = Array.isArray(o.path) ? o.path : [], pt = (performance.now() - st.pt0) / 1000, land = path.reduce(function (a, b) { return a + (b ? 1 : 0); }, 0);
    var per = Math.min(.24, 2.6 / rows), prog = res && path.length ? Math.min(rows, pt / per) : 0, k = Math.floor(prog), f = prog - k, sum = 0;
    for (var q = 0; q < k && q < path.length; q++) sum += path[q] ? 1 : 0;
    var bx = cx + (sum - k / 2) * dx, by = top + k * dy + dy * .2;
    if (k < rows && path.length && res) { var d = path[k] ? 1 : -1; bx += d * dx * .5 * f; by += dy * f - Math.sin(Math.PI * f) * dy * .45; }
    else if (!res) { bx = cx + Math.sin(T * 1.3) * dx * .6; by = top - 4 + (phase === "playing" ? (T * 90) % (dy * Math.max(1, rows - 1)) : 0); }
    else { bx = cx + (land - rows / 2) * dx; by = top + rows * dy + dy * .6; }
    var sw = dx * .92, sy = top + rows * dy + dy * 1.1, done = res && prog >= rows;
    for (var s = 0; s <= rows; s++) {
      var sx = cx + (s - rows / 2) * dx, hit = done && s === land, m = tbl[s];
      ctx.fillStyle = hit ? "#6dff9e" : (m >= 2 ? "#a855f7" : m >= 1 ? "#3b82f6" : "#4b5563"); rr(ctx, sx - sw / 2, sy, sw, h * .075, 6); ctx.fill();
      text(ctx, plFmt(m) + (rows > 12 ? "" : "×"), sx, sy + h * .037, Math.max(7, Math.min(13, dx * .34)), hit ? "#06301a" : "#fff", null);
    }
    var bg2 = ctx.createRadialGradient(bx - 3, by - 3, 1, bx, by, 11); bg2.addColorStop(0, "#fff"); bg2.addColorStop(1, "#d946ef");
    ctx.shadowColor = "#e78bff"; ctx.shadowBlur = 18; ctx.fillStyle = bg2; ctx.beginPath(); ctx.arc(bx, by, rows > 12 ? 7 : 10, 0, TAU); ctx.fill(); ctx.shadowBlur = 0;
    var mult = num(o.multiplier, 0);
    text(ctx, done ? (mult > 0 ? mult.toFixed(2) + "× · WIN!" : "0× · NO WIN") : (phase === "playing" || res ? "DROPPING…" : "DROP THE BALL"), w / 2, h * .94, 19, done ? (mult > 0 ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  function drawMines(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createRadialGradient(w / 2, h * .5, 10, w / 2, h * .5, h); bg.addColorStop(0, "#2b1d5c"); bg.addColorStop(1, "#0a0720"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    var pickDom = document.getElementById("mines-pick"), cntDom = document.getElementById("mines-count");
    var pick = clamp(Math.round(num(o.pick, pickDom ? num(pickDom.value, 0) : 0)), 0, 25), mc = clamp(Math.round(num(o.mine_count, cntDom ? num(cntDom.value, 3) : 3)), 1, 8);
    var mines = Array.isArray(o.mine_positions) ? o.mine_positions : [], pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose";
    var cell = Math.min((w * .86) / 5, (h * .74) / 5), sx = w / 2 - 2 * cell, sy = h * .06 + cell * .5 + 0, mult = num(o.multiplier, 0), revealedAll = false;
    for (var n = 1; n <= 25; n++) {
      var i = n - 1, x = sx + (i % 5) * cell, y = sy + Math.floor(i / 5) * cell, isP = n === pick, isM = mines.indexOf(n) >= 0;
      var open = res && (isP ? pt > .25 : (isM && pt > .8 + (mines.indexOf(n)) * .12)); if (res && pt > .8 + mines.length * .12) revealedAll = true;
      var r = cell * .42, g = ctx.createLinearGradient(x - r, y - r, x + r, y + r);
      if (open) { g.addColorStop(0, isM ? "#ff7b7b" : "#8bffb8"); g.addColorStop(1, isM ? "#9c1c1c" : "#0f9d55"); } else { g.addColorStop(0, "#5d6ad6"); g.addColorStop(1, "#262a63"); }
      var sq = open && isP ? 1 + .18 * Math.max(0, 1 - (pt - .25) * 4) : 1;
      ctx.fillStyle = g; rr(ctx, x - r * sq, y - r * sq, 2 * r * sq, 2 * r * sq, 9); ctx.fill();
      if (isP) { ctx.lineWidth = 3.5; ctx.strokeStyle = "#ffd23f"; ctx.shadowColor = "#ffd23f"; ctx.shadowBlur = 8; rr(ctx, x - r - 2, y - r - 2, 2 * r + 4, 2 * r + 4, 10); ctx.stroke(); ctx.shadowBlur = 0; }
      if (open) text(ctx, isM ? "💣" : "💎", x, y + 1, r * 1.1, "#fff", null); else text(ctx, "?", x, y + 1, r * .9, "rgba(255,255,255,.55)", null);
    }
    var done = res && pt > .45, safe = phase === "win";
    text(ctx, done ? (safe ? "SAFE" + (mult ? " · " + mult.toFixed(2) + "×" : "") + "!" : "BOOM!") : (phase === "playing" ? "REVEALING…" : mc + " MINES · PICK A TILE"), w / 2, h * .95, 18, done ? (safe ? "#6dff9e" : "#ff6b6b") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (safe ? "WIN" : "CRASHED") : null;
  }

  var SUITS = ["♠", "♥", "♦", "♣"], RANKS = ["", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
  function drawCard(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createRadialGradient(w / 2, h * .5, 10, w / 2, h * .5, h); bg.addColorStop(0, "#1c5d3b"); bg.addColorStop(1, "#06190f"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    var card = clamp(Math.round(num(o.card, 0)), 0, 13), choice = o.choice || ((document.querySelector("#card-controls .choice-btn.selected") || {}).dataset || {}).value || "";
    var pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose", cw = Math.min(w * .3, 130), ch = cw * 1.42, cx = w / 2, cy = h * .46;
    var flip = res && card ? clamp((pt - .3) / .5, 0, 1) : 0, sx = Math.abs(Math.cos(flip * Math.PI)), front = flip >= .5;
    var lift = phase === "playing" ? Math.sin(T * 8) * 5 : 0;
    ctx.save(); ctx.translate(cx, cy + lift); ctx.scale(sx || .02, 1);
    ctx.shadowColor = "rgba(0,0,0,.6)"; ctx.shadowBlur = 22; ctx.fillStyle = front ? "#fafaf6" : "#b32a3d"; rr(ctx, -cw / 2, -ch / 2, cw, ch, 12); ctx.fill(); ctx.shadowBlur = 0;
    if (front) { var sIdx = card % 4, suit = SUITS[sIdx], col = (sIdx === 1 || sIdx === 2) ? "#d62839" : "#1b2433";
      text(ctx, RANKS[card], -cw * .30, -ch * .36, cw * .26, col, null); text(ctx, suit, -cw * .30, -ch * .20, cw * .22, col, null); text(ctx, suit, 0, 0, cw * .62, col, null); }
    else { ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.lineWidth = 2; rr(ctx, -cw / 2 + 8, -ch / 2 + 8, cw - 16, ch - 16, 8); ctx.stroke(); text(ctx, "♦", 0, 0, cw * .5, "rgba(255,255,255,.55)", null); }
    ctx.restore();
    var hi = choice === "high", lo = choice === "low";
    text(ctx, "⬆ HIGH 8–K", w * .17, h * .46, 13, hi ? "#ffd84a" : "rgba(255,255,255,.4)", hi ? "#ffd84a" : null);
    text(ctx, "⬇ LOW A–6", w * .83, h * .46, 13, lo ? "#ffd84a" : "rgba(255,255,255,.4)", lo ? "#ffd84a" : null);
    var done = res && pt > .85, mult = num(o.multiplier, 0);
    text(ctx, done ? (phase === "win" ? (card ? RANKS[card] + " · " : "") + (mult ? mult.toFixed(2) + "× · " : "") + "WIN!" : (card === 7 ? "7 · HOUSE WINS" : RANKS[card] + " · MISS")) : (phase === "playing" ? "DEALING…" : "HIGH OR LOW?"), w / 2, h * .91, 20, done ? (phase === "win" ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  /* ------------------------------------------------------------------ coin flip */
  function drawCoinFlip(ctx, w, h, T, dt, st, o, phase) {
    var bg = ctx.createRadialGradient(w / 2, h * .45, 10, w / 2, h * .5, h); bg.addColorStop(0, "#5a3d06"); bg.addColorStop(1, "#140d02"); ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    var pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose", flip = o.flip || "", choice = o.choice || ((document.querySelector("#coinflip-controls .choice-btn.selected") || {}).dataset || {}).value || "";
    var R = Math.min(w, h) * .22, cx = w / 2, cy = h * .46, rise = 0, sx = 1;
    if (phase === "playing") { rise = Math.abs(Math.sin(T * 5)) * h * .12; sx = Math.cos(T * 22); }
    else if (res && flip) { var k = clamp(pt / 1.1, 0, 1); rise = Math.sin(k * Math.PI) * h * .2; var turns = 6 + (flip === "tails" ? 1 : 0); sx = k < 1 ? Math.cos(k * turns * Math.PI) : (flip === "heads" ? 1 : -1); }
    else { rise = Math.sin(T * 2) * 5; }
    var face = sx >= 0 ? "heads" : "tails", ax = Math.max(.04, Math.abs(sx));
    ctx.save(); ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.beginPath(); ctx.ellipse(cx, cy + R + 26, R * (1 - rise / (h * .6)), 9, 0, 0, TAU); ctx.fill(); ctx.restore();
    ctx.save(); ctx.translate(cx, cy - rise); ctx.scale(ax, 1);
    var g = ctx.createLinearGradient(-R, -R, R, R); g.addColorStop(0, "#fff0a8"); g.addColorStop(.5, "#f5b82e"); g.addColorStop(1, "#9a5a06");
    ctx.shadowColor = "rgba(255,200,60,.55)"; ctx.shadowBlur = 24; ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, R, 0, TAU); ctx.fill(); ctx.shadowBlur = 0;
    ctx.strokeStyle = "#8a4f05"; ctx.lineWidth = 4; ctx.stroke(); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(0, 0, R * .78, 0, TAU); ctx.stroke();
    text(ctx, face === "heads" ? "H" : "T", 0, 2, R * 1.05, "#7a4604", null);
    ctx.restore();
    text(ctx, "HEADS", w * .17, h * .46, 13, choice === "heads" ? "#ffd84a" : "rgba(255,255,255,.4)", choice === "heads" ? "#ffd84a" : null);
    text(ctx, "TAILS", w * .83, h * .46, 13, choice === "tails" ? "#ffd84a" : "rgba(255,255,255,.4)", choice === "tails" ? "#ffd84a" : null);
    var done = res && pt > 1.15, mult = num(o.multiplier, 0);
    text(ctx, done ? (flip.toUpperCase() + " · " + (phase === "win" ? (mult ? mult.toFixed(2) + "× · " : "") + "WIN!" : "MISS")) : (phase === "playing" || res ? "FLIPPING…" : "PICK A SIDE"), w / 2, h * .9, 19, done ? (phase === "win" ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  /* ------------------------------------------------------------------ penalty shootout */
  function drawPenalty(ctx, w, h, T, dt, st, o, phase) {
    var sky = ctx.createLinearGradient(0, 0, 0, h); sky.addColorStop(0, "#0b2a4a"); sky.addColorStop(.38, "#1a5a8a"); sky.addColorStop(.39, "#1e7a3a"); sky.addColorStop(1, "#0b3a1a"); ctx.fillStyle = sky; ctx.fillRect(0, 0, w, h);
    for (var s = 0; s < 6; s++) { ctx.fillStyle = s % 2 ? "rgba(255,255,255,.05)" : "rgba(0,0,0,.06)"; ctx.fillRect(0, h * .39 + s * h * .1, w, h * .1); }
    var gx = w * .14, gw = w * .72, gy = h * .12, gh = h * .34;
    ctx.save(); ctx.strokeStyle = "rgba(255,255,255,.22)"; ctx.lineWidth = 1;
    for (var n = 1; n < 14; n++) { ctx.beginPath(); ctx.moveTo(gx + gw * n / 14, gy); ctx.lineTo(gx + gw * n / 14, gy + gh); ctx.stroke(); }
    for (var m = 1; m < 6; m++) { ctx.beginPath(); ctx.moveTo(gx, gy + gh * m / 6); ctx.lineTo(gx + gw, gy + gh * m / 6); ctx.stroke(); }
    ctx.restore();
    ctx.strokeStyle = "#f4f4f4"; ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(gx, gy + gh); ctx.lineTo(gx, gy); ctx.lineTo(gx + gw, gy); ctx.lineTo(gx + gw, gy + gh); ctx.stroke();
    var zx = { left: gx + gw * .17, center: gx + gw * .5, right: gx + gw * .83 };
    var pt = (performance.now() - st.pt0) / 1000, res = phase === "win" || phase === "lose";
    var choice = o.choice || ((document.querySelector("#penalty-controls .choice-btn.selected") || {}).dataset || {}).value || "", keeper = o.keeper || "";
    ["left", "center", "right"].forEach(function (z) {
      var on = z === choice; ctx.fillStyle = on ? "rgba(255,216,74,.22)" : "rgba(255,255,255,.04)"; ctx.fillRect(zx[z] - gw * .15, gy + 4, gw * .3, gh - 4);
      if (on) { ctx.strokeStyle = "#ffd84a"; ctx.lineWidth = 2; ctx.setLineDash([6, 5]); ctx.strokeRect(zx[z] - gw * .15, gy + 4, gw * .3, gh - 4); ctx.setLineDash([]); }
    });
    // keeper
    var kx = zx.center, kdive = 0, kang = 0;
    if (phase === "playing") kx = zx.center + Math.sin(T * 7) * gw * .1;
    else if (res && keeper) { var kk = easeOut(pt / .45); kx = lerp(zx.center, zx[keeper] || zx.center, kk); kang = (keeper === "left" ? -1 : keeper === "right" ? 1 : 0) * kk * .9; kdive = keeper === "center" ? -kk * 8 : 0; }
    else kx = zx.center + Math.sin(T * 1.6) * gw * .05;
    var ky = gy + gh * .72;
    ctx.save(); ctx.translate(kx, ky + kdive); ctx.rotate(kang);
    ctx.fillStyle = "#ff8a1f"; rr(ctx, -13, -26, 26, 34, 6); ctx.fill();
    ctx.fillStyle = "#f2c9a0"; ctx.beginPath(); ctx.arc(0, -34, 9, 0, TAU); ctx.fill();
    ctx.strokeStyle = "#ff8a1f"; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-12, -20); ctx.lineTo(-30, -34); ctx.moveTo(12, -20); ctx.lineTo(30, -34); ctx.stroke();
    ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(-31, -35, 6, 0, TAU); ctx.arc(31, -35, 6, 0, TAU); ctx.fill();
    ctx.strokeStyle = "#1b2433"; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-6, 8); ctx.lineTo(-9, 30); ctx.moveTo(6, 8); ctx.lineTo(9, 30); ctx.stroke();
    ctx.restore();
    // ball
    var bx = w / 2, by = h * .84, br = 13;
    if (res && choice) { var bk = easeOut(clamp((pt - .05) / .5, 0, 1)); bx = lerp(w / 2, zx[choice] || w / 2, bk); by = lerp(h * .84, gy + gh * .45, bk); br = lerp(13, 8, bk); }
    else if (phase === "playing") { by = h * .84 - Math.abs(Math.sin(T * 9)) * 8; }
    ctx.fillStyle = "rgba(0,0,0,.3)"; ctx.beginPath(); ctx.ellipse(bx, h * .9, br * 1.1, 4, 0, 0, TAU); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU); ctx.fill(); ctx.strokeStyle = "#222"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = "#222"; ctx.beginPath(); ctx.arc(bx, by, br * .38, 0, TAU); ctx.fill();
    var done = res && pt > .7, mult = num(o.multiplier, 0);
    text(ctx, done ? (phase === "win" ? "⚽ GOAL! " + (mult ? mult.toFixed(2) + "×" : "") : "🧤 SAVED!") : (phase === "playing" || res ? "SHOOTING…" : "PICK YOUR CORNER"), w / 2, h * .96, 18, done ? (phase === "win" ? "#6dff9e" : "#ff9a9a") : "#ffd84a", "rgba(0,0,0,.8)");
    return done ? (phase === "win" ? "WIN" : "RESULT") : null;
  }

  /* ------------------------------------------------------------------ loop */
  function hud(key, status, mult) {
    var host = document.getElementById(key + "-scene"); if (!host) return;
    var s = host.querySelector(".scene-status"), m = host.querySelector(".scene-multiplier");
    if (s && status) s.textContent = status; if (m) m.textContent = mult || "";
  }

  function frame(key, st, tok, now) {
    if (st.tok !== tok) return;
    var host = document.getElementById(key + "-scene");
    if (!host || !host.offsetParent || document.hidden) { setTimeout(function () { requestAnimationFrame(function (n) { frame(key, st, tok, n); }); }, 400); return; }
    var sc = sceneCanvas(key); if (!sc) return;
    var T = (now - st.t0) / 1000, dt = Math.min(.1, (now - (st.last || now)) / 1000); st.last = now;
    var ctx = sc.ctx, w = sc.w, h = sc.h, o = st.o || {}, status = null;
    ctx.save();
    if (key === "aviator") status = drawCrash(ctx, w, h, T, dt, st, o, st.phase, false);
    else if (key === "jet") status = drawCrash(ctx, w, h, T, dt, st, o, st.phase, true);
    else if (key === "chicken" || key === "rabbit") status = drawRoad(ctx, w, h, T, dt, st, o, st.phase, key);
    else if (key === "keno") status = drawKeno(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "fish") status = drawFish(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "dice") status = drawDice(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "slot") status = drawSlot(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "wheel") status = drawWheel(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "plinko") status = drawPlinko(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "mines") status = drawMines(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "card") status = drawCard(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "coinflip") status = drawCoinFlip(ctx, w, h, T, dt, st, o, st.phase);
    else if (key === "penalty") status = drawPenalty(ctx, w, h, T, dt, st, o, st.phase);
    ctx.restore();
    hud(key, status || (st.phase === "playing" ? "LIVE" : "READY"), (key === "aviator" || key === "jet") && st.mShown ? st.mShown.toFixed(2) + "×" : "");
    requestAnimationFrame(function (n) { frame(key, st, tok, n); });
  }

  function stageRender(key, outcome, phase) {
    var host = document.getElementById(key + "-scene"); if (!host) return;
    host.classList.add("stage");
    var st = stages[key];
    if (!st) { st = stages[key] = { tok: 0, t0: performance.now(), pt0: performance.now() }; }
    var prev = st.phase;
    st.o = outcome || {}; st.phase = phase || "idle";
    if (prev !== st.phase || phase === "playing" && !st.o.live_multiplier) st.pt0 = performance.now();
    if (st.phase === "idle" || (st.phase === "playing" && prev !== "playing")) { st.mShown = 1; st.crashed = false; st.won = false; st.crashT = null; }
    if (!st.running) { st.running = true; var tok = ++st.tok; requestAnimationFrame(function (n) { frame(key, st, tok, n); }); }
  }

  var origRender3D = render3DScene, origRenderThree = renderThreeGameScene;
  render3DScene = function (key, o, p) { if (KEYS[key]) return stageRender(key, o, p); return origRender3D(key, o, p); };
  renderThreeGameScene = function (key, o, p) { if (KEYS[key]) return Promise.resolve(stageRender(key, o, p)); return origRenderThree(key, o, p); };

  // Pages are created lazily; draw the idle scene as soon as a stage game page is opened.
  var origGo = goToPage;
  goToPage = function (page) { origGo(page); if (KEYS[page]) setTimeout(function () { var st = stages[page]; if (!st || !st.running) stageRender(page, {}, "idle"); }, 30); };
})();
