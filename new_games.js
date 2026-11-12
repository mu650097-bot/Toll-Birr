/* ROULETTE, BINGO, FAST KENO -- client UIs. Presentation only: the server draws every number, scores every
   card and pays every bet (POST /games/<key>/round/start then /action {"action":"play"}). The animations
   below just replay the server's returned outcome. Loaded after app.js (uses its global helpers). */
(function () {
  "use strict";
  var $ = function (root, sel) { return root.querySelector(sel); };
  var esc = function (v) { return (typeof escapeHtml === "function") ? escapeHtml(String(v)) : String(v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var xfmt = function (m) { m = Number(m || 0); return (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2).replace(/\.?0+$/, "")) + "×"; };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var snd = function (n) { if (typeof gameSound === "function") try { gameSound(n); } catch (_) {} };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };

  // Generic page prep: these games draw their own UI, so hide the placeholder scene / Play button / result box.
  function prepare(key) {
    var root = document.getElementById(key + "-controls"); if (!root) return null;
    if (root.dataset.ng === "1") return root;
    root.dataset.ng = "1";
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(key + s); if (e) e.style.display = "none"; });
    var page = document.getElementById("page-" + key); if (page) page.classList.add("ng-page", "ng-page-" + key);
    return root;
  }

  function stakeBlock(key) {
    return '<div class="ng-stake"><label for="' + key + '-stake">Bet (ብር)</label>' +
      '<input id="' + key + '-stake" class="game-stake" type="number" min="0.01" step="0.01" value="10" inputmode="decimal">' +
      '<div class="ng-chips">' + [10, 20, 50, 100].map(function (v) { return '<button type="button" data-chip="' + v + '">' + v + "</button>"; }).join("") + "</div></div>";
  }
  function wireChips(root, key) {
    root.querySelectorAll("[data-chip]").forEach(function (b) { b.addEventListener("click", function () { $(root, "#" + key + "-stake").value = b.dataset.chip; hap("light"); }); });
  }
  function readStake(root, key, settings) {
    var v = Number($(root, "#" + key + "-stake").value);
    if (!(v > 0)) throw new Error("የBet መጠን ትክክል ያስገቡ");
    if (settings && (v < settings.min || v > settings.max)) throw new Error("Bet ከ " + settings.min + " እስከ " + settings.max + " ብር መሆን አለበት");
    return v;
  }
  async function loadLimits(key, state) {
    if (state.limits) return state.limits;
    try { var s = await apiFetch("/games/" + key + "/settings"); state.limits = { min: Number(s.min_stake) || 1, max: Number(s.max_stake) || 10000, enabled: s.enabled !== false }; }
    catch (_) { state.limits = { min: 1, max: 10000, enabled: true }; }
    return state.limits;
  }
  // start + play in one go; returns { start, action }
  async function runRound(key, body) {
    var start = await apiFetch("/games/" + key + "/round/start", { method: "POST", json: Object.assign({}, body, { client_seed: makeClientSeed() }) });
    var action = await apiFetch("/games/" + key + "/round/" + start.round_id + "/action", { method: "POST", json: { action: "play" } });
    return { start: start, action: action };
  }
  function proof(root, start, action) {
    var box = $(root, ".ng-proof"); if (!box) return;
    box.innerHTML = "🔒 Provably fair · commit <code>" + esc((start.seed_commit || "").slice(0, 12)) + "…</code> · seed <code>" + esc((action.server_seed || "").slice(0, 12)) + '…</code> <span class="ng-ok">⏳</span>';
    if (typeof sha256Hex !== "function" || !action.server_seed) return;
    sha256Hex(action.server_seed).then(function (h) {
      var ok = !start.seed_commit || h === start.seed_commit; var s = $(box, ".ng-ok"); if (s) s.textContent = ok ? "✅ ተረጋግጧል" : "❌ አልተመሳሰለም";
    }).catch(function () {});
  }
  function banner(root, won, payout, stake, extra) {
    var net = Math.round((payout - stake) * 100) / 100;
    won = payout > stake;                                   // a payout below the stake is a partial return, not a win
    if (!won && payout > 0) {
      $(root, ".ng-result").innerHTML = '<div class="ng-banner part">↩️ <b>ክፍል ተመልሷል</b> ' + money(payout) + " ብር <small>(" + money(net) + " ብር" + (extra ? " · " + extra : "") + ")</small></div>";
      snd("lose"); hap("light"); if (typeof refreshBalance === "function") refreshBalance(); return;
    }
    $(root, ".ng-result").innerHTML = won
      ? '<div class="ng-banner win">🎉 <b>አሸነፉ!</b> +' + money(net) + " ብር <small>(ክፍያ " + money(payout) + " ብር" + (extra ? " · " + extra : "") + ")</small></div>"
      : '<div class="ng-banner lose">😕 <b>አልተሳካም</b> -' + money(stake) + " ብር" + (extra ? " <small>" + extra + "</small>" : "") + "</div>";
    if (won) { snd("win"); hap("success"); if (typeof celebrateWin === "function") celebrateWin(); if (typeof celebrateWin3D === "function") celebrateWin3D(); } else { snd("lose"); hap("error"); }
    if (typeof refreshBalance === "function") refreshBalance();
  }
  function fail(root, e) { var box = $(root, ".ng-result"); if (typeof renderActionError === "function") renderActionError(box, e && e.message || String(e)); else box.textContent = "❌ " + (e && e.message); hap("error"); }

  /* =================================================================== ROULETTE */
  var RED = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36];
  var rcolor = function (n) { return (n === 0 || n === 37) ? "green" : (RED.indexOf(n) >= 0 ? "red" : "black"); };
  var rlabel = function (n) { return n === 37 ? "00" : String(n); };
  var OUTSIDE = [
    { id: "red", label: "🔴 Red", bet: "red", pay: 2 }, { id: "black", label: "⚫ Black", bet: "black", pay: 2 },
    { id: "odd", label: "Odd", bet: "odd", pay: 2 }, { id: "even", label: "Even", bet: "even", pay: 2 },
    { id: "low", label: "1–18", bet: "low", pay: 2 }, { id: "high", label: "19–36", bet: "high", pay: 2 },
    { id: "d1", label: "1st 12", bet: "dozen", value: 1, pay: 3 }, { id: "d2", label: "2nd 12", bet: "dozen", value: 2, pay: 3 }, { id: "d3", label: "3rd 12", bet: "dozen", value: 3, pay: 3 },
    { id: "c1", label: "Col 1", bet: "column", value: 1, pay: 3 }, { id: "c2", label: "Col 2", bet: "column", value: 2, pay: 3 }, { id: "c3", label: "Col 3", bet: "column", value: 3, pay: 3 }
  ];
  var R = { sel: null, busy: false, limits: null, history: [] };

  window.setupRoulette = async function () {
    var root = prepare("roulette"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var nums = '<button type="button" class="ng-num green" data-n="0">0</button><button type="button" class="ng-num green" data-n="37">00</button>';
      for (var n = 1; n <= 36; n++) nums += '<button type="button" class="ng-num ' + rcolor(n) + '" data-n="' + n + '">' + n + "</button>";
      root.innerHTML =
        '<div class="ng-wrap">' +
          '<div class="ng-wheel"><div class="ng-ball" id="rl-ball">?</div></div>' +
          '<div class="ng-hist" id="rl-hist"></div>' +
          '<div class="ng-sub">ውርርድ ይምረጡ (አንድ ውርርድ በአንድ ዙር)</div>' +
          '<div class="ng-outside">' + OUTSIDE.map(function (o) { return '<button type="button" class="ng-bet" data-id="' + o.id + '">' + o.label + "<small>" + o.pay + "×</small></button>"; }).join("") + "</div>" +
          '<div class="ng-sub">ወይም ቁጥር ይምረጡ <small>(36×)</small></div>' +
          '<div class="ng-numgrid">' + nums + "</div>" +
          '<div class="ng-sel" id="rl-sel">ምንም አልተመረጠም</div>' +
          stakeBlock("roulette") +
          '<button type="button" class="primary-game-btn ng-go" id="rl-go">🎡 ያሽክርክሩ</button>' +
          '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
          '<small class="ng-note">American roulette (0 እና 00)። ሁሉም ውርርድ RTP 94.74%። 0/00 ሲመጣ የውጭ ውርርዶች ይጠፋሉ።</small>' +
        "</div>";
      wireChips(root, "roulette");
      root.querySelectorAll(".ng-bet").forEach(function (b) { b.addEventListener("click", function () { var o = OUTSIDE.filter(function (x) { return x.id === b.dataset.id; })[0]; pick(root, { bet: o.bet, value: o.value, label: o.label.replace(/^[^\wА-я1]+/, ""), pay: o.pay, key: o.id }); }); });
      root.querySelectorAll(".ng-num").forEach(function (b) { b.addEventListener("click", function () { var n = Number(b.dataset.n); pick(root, { bet: "number", value: n, label: "ቁጥር " + rlabel(n), pay: 36, key: "n" + n }); }); });
      $(root, "#rl-go").addEventListener("click", function () { spin(root); });
    }
    await loadLimits("roulette", R); renderHist(root);
  };
  function pick(root, s) {
    if (R.busy) return; R.sel = s; hap("light");
    root.querySelectorAll(".ng-bet,.ng-num").forEach(function (b) { b.classList.remove("on"); });
    var el = s.bet === "number" ? root.querySelector('.ng-num[data-n="' + s.value + '"]') : root.querySelector('.ng-bet[data-id="' + s.key + '"]'); if (el) el.classList.add("on");
    $(root, "#rl-sel").innerHTML = "ውርርድ: <b>" + esc(s.label) + "</b> · ይከፍላል <b>" + s.pay + "×</b>";
  }
  function renderHist(root) { var h = $(root, "#rl-hist"); if (h) h.innerHTML = R.history.map(function (n) { return '<span class="ng-dot ' + rcolor(n) + '">' + rlabel(n) + "</span>"; }).join(""); }
  async function spin(root) {
    if (R.busy) return;
    var ball = $(root, "#rl-ball");
    try {
      if (!R.sel) throw new Error("መጀመሪያ ውርርድ ይምረጡ");
      var stake = readStake(root, "roulette", R.limits);
      R.busy = true; $(root, "#rl-go").disabled = true; $(root, ".ng-result").innerHTML = ""; $(root, ".ng-proof").innerHTML = "";
      ball.className = "ng-ball spinning"; snd("round");
      var shuffle = setInterval(function () { var n = Math.floor(Math.random() * 38); ball.textContent = rlabel(n); ball.className = "ng-ball spinning " + rcolor(n); }, 70);
      var body = { stake: stake, bet: R.sel.bet }; if (R.sel.value !== undefined) body.value = R.sel.value;
      var res; try { res = await runRound("roulette", body); } finally { await sleep(900); clearInterval(shuffle); }
      var o = res.action.outcome;
      ball.textContent = o.label; ball.className = "ng-ball landed " + o.color; hap("light");
      R.history.unshift(o.spin); R.history = R.history.slice(0, 12); renderHist(root);
      banner(root, !!res.action.won && res.action.payout > 0, res.action.payout, stake, "ወጣ: " + o.label + " " + (o.color === "red" ? "🔴" : o.color === "black" ? "⚫" : "🟢"));
      proof(root, res.start, res.action);
    } catch (e) { ball.className = "ng-ball"; fail(root, e); }
    R.busy = false; $(root, "#rl-go").disabled = false;
  }

  /* =================================================================== FAST KENO */
  var FK = { POOL: 40, PICK: 4, sel: [], busy: false, limits: null, last: null,
             table: [[0, 0], [1, 0.35], [2, 1.6], [3, 7], [4, 80]] };  // must match FASTKENO_PAYTABLE (server is authoritative)
  window.setupFastKeno = async function () {
    var root = prepare("fastkeno"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var cells = ""; for (var n = 1; n <= FK.POOL; n++) cells += '<button type="button" class="ng-cell" data-n="' + n + '">' + n + "</button>";
      root.innerHTML =
        '<div class="ng-wrap">' +
          '<div class="ng-sub">⚡ <b>4 ቁጥሮች</b> ይምረጡ (1–40) · 10 ኳሶች ይወጣሉ</div>' +
          '<div class="ng-fkgrid" id="fk-grid">' + cells + "</div>" +
          '<div class="ng-paytable" id="fk-pay">' + FK.table.slice(1).map(function (r) { return '<div data-h="' + r[0] + '"><small>' + r[0] + ' hit</small><b>' + xfmt(r[1]) + "</b></div>"; }).join("") + "</div>" +
          '<div class="ng-row"><button type="button" class="ng-ghost" id="fk-quick">🎲 Quick Pick</button><button type="button" class="ng-ghost" id="fk-clear">✖ አጽዳ</button></div>' +
          stakeBlock("fastkeno") +
          '<button type="button" class="primary-game-btn ng-go" id="fk-go">⚡ ጀምር</button>' +
          '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
          '<small class="ng-note">እያንዳንዱ ጨዋታ በሰከንዶች ውስጥ ያልቃል። ኳሶቹ በServer ይመረጣሉ።</small>' +
        "</div>";
      wireChips(root, "fastkeno");
      root.querySelectorAll(".ng-cell").forEach(function (b) { b.addEventListener("click", function () { toggle(root, Number(b.dataset.n)); }); });
      $(root, "#fk-quick").addEventListener("click", function () { if (FK.busy) return; var s = []; while (s.length < FK.PICK) { var n = 1 + Math.floor(Math.random() * FK.POOL); if (s.indexOf(n) < 0) s.push(n); } FK.sel = s; FK.last = null; paint(root, null); hap("light"); });
      $(root, "#fk-clear").addEventListener("click", function () { if (!FK.busy) { FK.sel = []; FK.last = null; paint(root, null); } });
      $(root, "#fk-go").addEventListener("click", function () { playFK(root); });
    }
    await loadLimits("fastkeno", FK); paint(root);
  };
  function toggle(root, n) {
    if (FK.busy) return; var i = FK.sel.indexOf(n);
    if (i >= 0) FK.sel.splice(i, 1); else if (FK.sel.length < FK.PICK) FK.sel.push(n); else { hap("error"); return; }
    hap("light"); FK.last = null; paint(root, null);
  }
  function paint(root, draw) {
    root.querySelectorAll(".ng-cell").forEach(function (b) {
      var n = Number(b.dataset.n), picked = FK.sel.indexOf(n) >= 0, drawn = draw && draw.indexOf(n) >= 0;
      b.className = "ng-cell" + (picked ? " picked" : "") + (drawn ? " drawn" : "") + (picked && drawn ? " hit" : "");
    });
    $(root, "#fk-go").disabled = FK.busy || FK.sel.length !== FK.PICK;
    $(root, "#fk-go").textContent = FK.sel.length === FK.PICK ? "⚡ ጀምር" : "⚡ " + (FK.PICK - FK.sel.length) + " ተጨማሪ ቁጥር ይምረጡ";
  }
  async function playFK(root) {
    if (FK.busy || FK.sel.length !== FK.PICK) return;
    try {
      var stake = readStake(root, "fastkeno", FK.limits);
      FK.busy = true; FK.last = null; paint(root, null); $(root, ".ng-result").innerHTML = ""; $(root, ".ng-proof").innerHTML = ""; snd("round");
      root.querySelectorAll("#fk-pay > div").forEach(function (d) { d.classList.remove("on"); });
      var res = await runRound("fastkeno", { stake: stake, numbers: FK.sel.slice() }); var o = res.action.outcome, shown = [];
      for (var i = 0; i < o.draw.length; i++) { shown.push(o.draw[i]); paint(root, shown); if (FK.sel.indexOf(o.draw[i]) >= 0) hap("light"); await sleep(170); }
      FK.last = shown;
      var h = root.querySelector('#fk-pay [data-h="' + o.hits + '"]'); if (h) h.classList.add("on");
      banner(root, res.action.payout > 0, res.action.payout, stake, o.hits + " hit" + (o.hits === 1 ? "" : "s"));
      proof(root, res.start, res.action);
    } catch (e) { fail(root, e); }
    FK.busy = false; paint(root, FK.last);
  }

  /* =================================================================== BINGO */
  var BG = { busy: false, limits: null,
             table: [[1, 0.8], [2, 2.5], [3, 8.5], [4, 30], [5, 105], [6, 300], [7, 1000]],   // must match BINGO_PAYTABLE
             lines: [[0,1,2,3,4],[5,6,7,8,9],[10,11,12,13,14],[15,16,17,18,19],[20,21,22,23,24],[0,5,10,15,20],[1,6,11,16,21],[2,7,12,17,22],[3,8,13,18,23],[4,9,14,19,24],[0,6,12,18,24],[4,8,12,16,20]] };
  window.setupBingo = async function () {
    var root = prepare("bingo"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var head = "BINGO".split("").map(function (c) { return "<b>" + c + "</b>"; }).join(""), cells = "";
      for (var i = 0; i < 25; i++) cells += '<div class="ng-bcell" data-i="' + i + '">' + (i === 12 ? "★" : "") + "</div>";
      root.innerHTML =
        '<div class="ng-wrap">' +
          '<div class="ng-bcard"><div class="ng-bhead">' + head + '</div><div class="ng-bgrid" id="bg-grid">' + cells + "</div></div>" +
          '<div class="ng-balls" id="bg-balls"><span class="ng-sub">ካርድዎ ሲጀመር ይታደላል · 40 ኳሶች ይወጣሉ</span></div>' +
          '<div class="ng-paytable ng-pt-bingo" id="bg-pay">' + BG.table.map(function (r) { return '<div data-l="' + r[0] + '"><small>' + r[0] + (r[0] === 7 ? "+" : "") + ' line</small><b>' + xfmt(r[1]) + "</b></div>"; }).join("") + "</div>" +
          stakeBlock("bingo") +
          '<button type="button" class="primary-game-btn ng-go" id="bg-go">🎱 ካርድ ግዛ እና ጀምር</button>' +
          '<button type="button" class="ng-ghost" id="bg-skip" hidden>⏩ በፍጥነት አሳይ</button>' +
          '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
          '<small class="ng-note">መስመር = ረድፍ፣ ዓምድ ወይም ሰያፍ (12 መስመሮች)። መሃል ★ ነጻ ነው። ብዙ መስመር = ትልቅ ሽልማት።</small>' +
        "</div>";
      wireChips(root, "bingo");
      $(root, "#bg-go").addEventListener("click", function () { playBingo(root); });
      $(root, "#bg-skip").addEventListener("click", function () { BG.skip = true; });
    }
    await loadLimits("bingo", BG);
  };
  async function playBingo(root) {
    if (BG.busy) return; var grid = $(root, "#bg-grid"), balls = $(root, "#bg-balls");
    try {
      var stake = readStake(root, "bingo", BG.limits);
      BG.busy = true; BG.skip = false; $(root, "#bg-go").disabled = true; $(root, ".ng-result").innerHTML = ""; $(root, ".ng-proof").innerHTML = "";
      grid.querySelectorAll(".ng-bcell").forEach(function (c, i) { c.className = "ng-bcell"; c.textContent = i === 12 ? "★" : ""; });
      root.querySelectorAll("#bg-pay > div").forEach(function (d) { d.classList.remove("on"); });
      balls.innerHTML = ""; snd("round");
      var res = await runRound("bingo", { stake: stake }); var o = res.action.outcome, cells = grid.querySelectorAll(".ng-bcell");
      o.card.forEach(function (n, i) { if (i !== 12) cells[i].textContent = n; });
      cells[12].classList.add("mark");
      $(root, "#bg-skip").hidden = false;
      var hit = {}; o.card.forEach(function (n, i) { if (n) hit[n] = i; });
      for (var k = 0; k < o.draws.length; k++) {
        var n = o.draws[k]; var b = document.createElement("span"); b.className = "ng-ball2" + (hit[n] !== undefined ? " m" : ""); b.textContent = n; balls.appendChild(b); balls.scrollLeft = balls.scrollWidth;
        if (hit[n] !== undefined) { cells[hit[n]].classList.add("mark"); hap("light"); }
        if (!BG.skip) await sleep(95);
      }
      $(root, "#bg-skip").hidden = true;
      o.line_ids.forEach(function (li) { BG.lines[li].forEach(function (ci) { cells[ci].classList.add("line"); }); });
      var row = root.querySelector('#bg-pay [data-l="' + Math.min(o.lines, 7) + '"]'); if (row && o.lines > 0) row.classList.add("on");
      banner(root, res.action.payout > 0, res.action.payout, stake, o.lines + " መስመር");
      proof(root, res.start, res.action);
    } catch (e) { fail(root, e); }
    BG.busy = false; $(root, "#bg-go").disabled = false; $(root, "#bg-skip").hidden = true;
  }
})();
