/* PLINKO (new look): Risk (Low/Med/High) x Rows (8/12/16). The SERVER drops the ball (fair 50/50 pegs), picks the bucket,
   applies the disclosed house edge and pays; this file only animates the server's path. Loaded after app.js and game_stage.js. */
(function () {
  "use strict";
  var KEY = "plinko", RISKS = [["low", "Low"], ["med", "Med"], ["high", "High"]], ROWS = [8, 12, 16];
  var P = { min: 1, max: 10000, tables: null, loaded: false, risk: "med", rows: 8, busy: false, last: null, anim: 0 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  function fmt(m) { return m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : m >= 1 ? m.toFixed(1) : m.toFixed(1); }
  function color(m) { return m >= 8 ? "#a21caf" : m >= 3 ? "#c2410c" : m >= 1.2 ? "#a16207" : m >= 1 ? "#92400e" : "#7f1d3a"; }
  function table() { var t = P.tables && P.tables[P.risk] && P.tables[P.risk][String(P.rows)]; return t || null; }

  function load() {
    if (P.loaded) return Promise.resolve();
    return apiFetch("/games/" + KEY + "/settings").then(function (s) {
      P.min = Number(s.min_stake) || 1; P.max = Number(s.max_stake) || 10000; if (s.plinko_tables) P.tables = s.plinko_tables; P.loaded = true;
    }).catch(function () { P.loaded = true; });
  }

  window.setupPlinko = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var rk = RISKS.map(function (r) { return '<button type="button" data-r="' + r[0] + '">' + r[1] + "</button>"; }).join("");
      var rw = ROWS.map(function (r) { return '<button type="button" data-w="' + r + '">' + r + "</button>"; }).join("");
      root.innerHTML = '<div class="pk-wrap"><div class="pk-top"><span class="pk-last" id="pk-last">Last: —</span></div>' +
        '<div class="pk-stage"><canvas id="pk-cv" width="640" height="620"></canvas></div>' +
        '<div class="av-card"><div class="av-cols"><div class="av-bet-col"><label>Risk</label><div class="pk-seg" id="pk-risk">' + rk + '</div></div>' +
        '<div class="av-bet-col"><label>Rows</label><div class="pk-seg" id="pk-rows">' + rw + '</div></div></div>' +
        '<div class="av-bet-col"><label for="plinko-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="plinko-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="20"><button type="button" data-d="1">+</button></div></div>' +
        '<button type="button" id="pk-go" class="av-go">Drop Ball</button><div class="kx-msg" id="pk-msg" aria-live="polite"></div><div class="kx-proof" id="pk-proof"></div></div>' +
        '<small class="kx-note">ኳሱ የሚወድቅበትን ቦታ ሰርቨሩ ይወስናል (እያንዳንዱ ችንካር 50/50)። ማባዣዎቹ የሚታዩት ቀድሞ የተከፈለው house edge ተቀንሶ ነው።</small></div>';
      root.querySelectorAll("#pk-risk button").forEach(function (b) { b.addEventListener("click", function () { if (P.busy) return; P.risk = b.dataset.r; hap("light"); paint(root); }); });
      root.querySelectorAll("#pk-rows button").forEach(function (b) { b.addEventListener("click", function () { if (P.busy) return; P.rows = Number(b.dataset.w); hap("light"); paint(root); }); });
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (P.busy) return;
          var i = $(root, "#plinko-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(P.min, Math.min(P.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#plinko-stake").addEventListener("input", function () { paint(root); });
      $(root, "#pk-go").addEventListener("click", function () { drop(root); });
    }
    await load(); paint(root);
  };

  function paint(root) {
    root.querySelectorAll("#pk-risk button").forEach(function (b) { b.classList.toggle("on", b.dataset.r === P.risk); b.disabled = P.busy; });
    root.querySelectorAll("#pk-rows button").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.w) === P.rows); b.disabled = P.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = P.busy; });
    var g = $(root, "#pk-go"); g.disabled = P.busy; g.textContent = P.busy ? "…" : "Drop Ball";
    $(root, "#pk-last").textContent = "Last: " + (P.last != null ? "x" + fmt(P.last) : "—");
    $(root, "#pk-last").className = "pk-last" + (P.last != null ? (P.last >= 1 ? " up" : " down") : "");
    draw(root, P.keep && P.keep.rows === P.rows ? P.keep : null);
  }

  /* ball: {rows, path, t0, dur, bucket}  – drawn from the server's path */
  function draw(root, ball) {
    var cv = $(root, "#pk-cv"); if (!cv) return;
    var ctx = cv.getContext("2d"), W = cv.width, H = cv.height, rows = ball ? ball.rows : P.rows, tbl = table();
    ctx.clearRect(0, 0, W, H);
    var dx = Math.min(W / (rows + 2.2), 56), top = 30, dy = (H - 150) / (rows + 0.4), cx = W / 2;
    ctx.fillStyle = "rgba(190,170,255,.9)";
    for (var r = 0; r < rows; r++) for (var j = 0; j <= r; j++) { ctx.beginPath(); ctx.arc(cx + (j - r / 2) * dx, top + (r + 1) * dy, rows > 12 ? 3 : 4.2, 0, 6.283); ctx.fill(); }
    var by0 = top + (rows + 1) * dy + 10, bw = dx * 0.9, bh = 46;
    for (var s = 0; s <= rows; s++) {
      var m = tbl ? tbl[s] : null, x = cx + (s - rows / 2) * dx, hit = ball && ball.done && ball.bucket === s;
      ctx.fillStyle = m == null ? "#334155" : color(m);
      ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x - bw / 2, by0, bw, bh, 8) : ctx.rect(x - bw / 2, by0, bw, bh); ctx.fill();
      if (hit) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 3; ctx.stroke(); }
      if (m != null) { ctx.fillStyle = "#fff"; ctx.font = "800 " + Math.max(10, Math.min(17, dx * 0.4)) + "px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText((rows > 12 ? "" : "x") + fmt(m), x, by0 + bh / 2); }
    }
    if (ball) {
      var k, f, p = ball.path || [];
      var prog = ball.done ? rows : Math.min(rows, Math.max(0, (performance.now() - ball.t0) / ball.dur * rows));
      k = Math.min(rows, Math.floor(prog)); f = prog - k;
      var sum = 0; for (var q = 0; q < k; q++) sum += p[q] ? 1 : 0;
      var bx = cx + (sum - k / 2) * dx, by = top + (k + 0.2) * dy;
      if (k < rows) { var dir = p[k] ? 1 : -1; bx += dir * dx * 0.5 * f; by += dy * f - Math.sin(Math.PI * f) * dy * 0.35; }
      else { bx = cx + (ball.bucket - rows / 2) * dx; by = by0 - 8; }
      var gr = ctx.createRadialGradient(bx - 3, by - 3, 1, bx, by, 12); gr.addColorStop(0, "#fff"); gr.addColorStop(1, "#e879f9");
      ctx.shadowColor = "#f0abfc"; ctx.shadowBlur = 16; ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(bx, by, rows > 12 ? 8 : 11, 0, 6.283); ctx.fill(); ctx.shadowBlur = 0;
    }
  }

  function animate(root, ball) {
    return new Promise(function (res) {
      var id = ++P.anim;
      (function step() {
        if (id !== P.anim) return res();
        draw(root, ball);
        if (performance.now() - ball.t0 >= ball.dur) { ball.done = true; draw(root, ball); return res(); }
        requestAnimationFrame(step);
      })();
    });
  }

  async function drop(root) {
    if (P.busy) return;
    var msg = $(root, "#pk-msg"), proof = $(root, "#pk-proof"), stake = Number($(root, "#plinko-stake").value);
    if (!(stake > 0)) { msg.className = "kx-msg bad"; msg.textContent = "❌ የBet መጠን ትክክል ያስገቡ"; return; }
    if (stake < P.min || stake > P.max) { msg.className = "kx-msg bad"; msg.textContent = "❌ Bet ከ " + P.min + " እስከ " + P.max + " ብር መሆን አለበት"; return; }
    P.keep = null; P.busy = true; msg.className = "kx-msg"; msg.textContent = ""; proof.textContent = ""; paint(root); hap("light");
    var risk = P.risk, rows = P.rows;
    try {
      var r = await startRealtimeRound(KEY, { stake: stake, risk: risk, rows: rows });
      proof.textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || r.commitment || "").slice(0, 16) + "…";
      var rr = await realtimeAction(KEY, "play"), o = rr.outcome || {}, path = Array.isArray(o.path) ? o.path : [];
      var bucket = path.reduce(function (a, b) { return a + (b ? 1 : 0); }, 0);
      var ball = { rows: Number(o.rows) || rows, path: path, bucket: bucket, t0: performance.now(), dur: Math.max(1400, rows * 150), done: false };
      await animate(root, ball); P.keep = ball;
      var mult = Number(o.multiplier != null ? o.multiplier : (rr.payout || 0) / stake), pay = Number(rr.payout || 0);
      P.last = mult;
      if (pay > stake) { msg.className = "kx-msg win"; msg.textContent = "🎉 x" + fmt(mult) + " · +" + money(pay - stake) + " ብር"; hap("success"); }
      else if (pay > 0) { msg.className = "kx-msg lose"; msg.textContent = "x" + fmt(mult) + " · ከውርርድዎ ክፍል " + money(pay) + " ብር ተመልሷል"; hap("light"); }
      else { msg.className = "kx-msg lose"; msg.textContent = "x0 · -" + money(stake) + " ብር"; hap("error"); }
      if (rr.server_seed) proof.textContent = "ROUND " + (rr.round_code || "") + " · SERVER SEED " + String(rr.server_seed).slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { msg.className = "kx-msg bad"; msg.textContent = "❌ " + e.message; }
    P.busy = false; paint(root);
  }
})();
