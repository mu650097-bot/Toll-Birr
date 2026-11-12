/* DICE (two dice: Under / Exact / Over) + COIN FLIP (streak with Cash Out). Presentation only: the server rolls, flips,
   decides every step and pays. Loaded after app.js (uses apiFetch, refreshBalance, haptic, makeClientSeed, sha256Hex, escapeHtml). */
(function () {
  "use strict";
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var esc = function (v) { return (typeof escapeHtml === "function") ? escapeHtml(String(v)) : String(v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };

  function hideGeneric(key) {
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(key + s); if (e) e.style.display = "none"; });
    var page = document.getElementById("page-" + key); if (page) page.classList.add("kx-page");
    return document.getElementById(key + "-controls");
  }
  function stepper(key, val) {
    return '<div class="kx-bet"><label for="' + key + '-stake">Bet Amount</label><div class="kx-step">' +
      '<button type="button" data-d="-1" aria-label="minus">−</button>' +
      '<input id="' + key + '-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + val + '">' +
      '<button type="button" data-d="1" aria-label="plus">+</button></div></div>';
  }
  function wireStepper(root, key, lim) {
    var inp = $(root, "#" + key + "-stake");
    root.querySelectorAll(".kx-step button").forEach(function (b) {
      b.addEventListener("click", function () {
        if (inp.disabled) return;
        var v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
        v = Math.max(lim().min, Math.min(lim().max, v + Number(b.dataset.d) * st)); inp.value = v; hap("light");
        inp.dispatchEvent(new Event("input"));
      });
    });
  }
  function readLimits(key, st) {
    if (st.loaded) return Promise.resolve();
    return apiFetch("/games/" + key + "/settings").then(function (s) {
      st.min = Number(s.min_stake) || 1; st.max = Number(s.max_stake) || 10000; st.edge = s.house_edge != null ? Number(s.house_edge) : 0.05; st.loaded = true;
    }).catch(function () { st.min = 1; st.max = 10000; st.edge = 0.05; });
  }
  function readStake(root, key, st) {
    var v = Number($(root, "#" + key + "-stake").value);
    if (!(v > 0)) throw new Error("የBet መጠን ትክክል ያስገቡ");
    if (v < st.min || v > st.max) throw new Error("Bet ከ " + st.min + " እስከ " + st.max + " ብር መሆን አለበት");
    return v;
  }

  /* ========================================================================= DICE (2 dice) */
  var DS = { mode: "over", target: 7, busy: false, min: 1, max: 10000, edge: 0.05, loaded: false, hist: [], last: null };
  var PIPS = { 1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8] };
  function die(n) { var h = ""; for (var i = 0; i < 9; i++) h += "<i" + ((PIPS[n] || []).indexOf(i) >= 0 ? ' class="on"' : "") + "></i>"; return '<div class="kx-die">' + h + "</div>"; }
  function cnt(k) { return (k >= 2 && k <= 12) ? 6 - Math.abs(k - 7) : 0; }
  function chance(mode, t) {
    var n = 0, k;
    if (mode === "under") for (k = 2; k < t; k++) n += cnt(k);
    else if (mode === "over") for (k = t + 1; k <= 12; k++) n += cnt(k);
    else n = cnt(t);
    return n / 36;
  }
  function dvalid(mode, t) { var p = chance(mode, t); return p > 0 && p <= 0.9; }
  window.setupDice2 = async function () {
    var root = hideGeneric("dice2"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      var nums = ""; for (var n = 2; n <= 12; n++) nums += '<button type="button" class="kx-num" data-n="' + n + '">' + n + "</button>";
      root.innerHTML = '<div class="kx-wrap">' +
        '<div class="kx-top"><div class="kx-stage" id="dx-stage">' + die(4) + die(3) + '</div>' +
        '<div class="kx-side"><div class="kx-tile"><small>Last Roll</small><b id="dx-last">—</b><em id="dx-sum"></em></div>' +
        '<div class="kx-tile"><small>Your Win</small><b id="dx-win" class="g">0.00</b><em>ETB</em></div></div></div>' +
        '<div class="kx-hist"><span>History</span><div id="dx-hist"></div></div>' +
        '<div class="kx-card"><div class="kx-h">Select Number</div><div class="kx-nums" id="dx-nums">' + nums + '</div>' +
        '<div class="kx-seg" id="dx-mode"><button type="button" data-m="under">Under</button><button type="button" data-m="exact">Exact</button><button type="button" data-m="over">Over</button></div>' +
        '<div class="kx-two"><div class="kx-tile"><small>Win chance</small><b id="dx-ch">—</b></div><div class="kx-tile"><small>Payout</small><b id="dx-pay" class="b">—</b></div></div></div>' +
        '<div class="kx-row">' + stepper("dice2", 10) + '<button type="button" id="dx-go" class="kx-go">🎲 Roll</button></div>' +
        '<div class="kx-msg" id="dx-msg" aria-live="polite"></div><div class="kx-proof" id="dx-proof"></div>' +
        '<small class="kx-note">ሁለት ዳይስ ይጣላሉ፣ ድምሩ 2–12 ነው። ክፍያ = (1 − edge) ÷ የማሸነፍ ዕድል፣ ስለዚህ ሁሉም ምርጫ ተመሳሳይ RTP አለው።</small></div>';
      root.querySelectorAll(".kx-num").forEach(function (b) { b.addEventListener("click", function () { if (DS.busy) return; DS.target = Number(b.dataset.n); hap("light"); dpaint(root); }); });
      root.querySelectorAll("#dx-mode button").forEach(function (b) { b.addEventListener("click", function () { if (DS.busy) return; DS.mode = b.dataset.m; hap("light"); dpaint(root); }); });
      $(root, "#dx-go").addEventListener("click", function () { droll(root); });
      wireStepper(root, "dice2", function () { return DS; });
    }
    await readLimits("dice2", DS); dpaint(root);
  };
  function dpaint(root) {
    root.querySelectorAll(".kx-num").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.n) === DS.target); });
    root.querySelectorAll("#dx-mode button").forEach(function (b) { b.classList.toggle("on", b.dataset.m === DS.mode); });
    var p = chance(DS.mode, DS.target), ok = dvalid(DS.mode, DS.target);
    $(root, "#dx-ch").textContent = p > 0 ? (p * 100).toFixed(2) + "%" : "—";
    $(root, "#dx-pay").textContent = ok ? "x" + ((1 - DS.edge) / p).toFixed(2) : "—";
    $(root, "#dx-go").disabled = DS.busy || !ok;
    $(root, "#dx-msg").className = "kx-msg" + (ok ? "" : " bad");
    if (!ok && !DS.busy) $(root, "#dx-msg").textContent = p <= 0 ? "ይህ ምርጫ ፈጽሞ አያሸንፍም -- ሌላ ቁጥር ወይም ሁነታ ይምረጡ" : "ይህ ምርጫ በጣም ብዙ ጊዜ ያሸንፋል (ከ 90% በላይ) -- አይፈቀድም";
    else if (ok && !DS.busy && /አይፈቀድም|አያሸንፍም/.test($(root, "#dx-msg").textContent)) $(root, "#dx-msg").textContent = "";
  }
  async function droll(root) {
    if (DS.busy || !dvalid(DS.mode, DS.target)) return;
    var stake; try { stake = readStake(root, "dice2", DS); } catch (e) { $(root, "#dx-msg").className = "kx-msg bad"; $(root, "#dx-msg").textContent = "❌ " + e.message; return; }
    DS.busy = true; dpaint(root); $(root, "#dx-msg").textContent = ""; $(root, "#dx-proof").textContent = "";
    var stage = $(root, "#dx-stage"); stage.classList.add("roll");
    var t = setInterval(function () { stage.innerHTML = die(1 + Math.floor(Math.random() * 6)) + die(1 + Math.floor(Math.random() * 6)); }, 90);
    try {
      var start = await apiFetch("/games/dice2/round/start", { method: "POST", json: { stake: stake, mode: DS.mode, target: DS.target, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/dice2/round/" + start.round_id + "/action", { method: "POST", json: { action: "play" } });
      await sleep(650); clearInterval(t); stage.classList.remove("roll");
      var o = act.outcome, pay = Number(act.payout || 0);
      stage.innerHTML = die(o.dice[0]) + die(o.dice[1]);
      $(root, "#dx-last").textContent = o.total; $(root, "#dx-sum").textContent = o.dice[0] + " + " + o.dice[1];
      $(root, "#dx-win").textContent = money(pay); $(root, "#dx-win").className = act.won ? "g" : "r";
      DS.hist.unshift({ t: o.total, w: !!act.won }); DS.hist = DS.hist.slice(0, 7);
      $(root, "#dx-hist").innerHTML = DS.hist.map(function (h) { return '<span class="' + (h.w ? "w" : "l") + '">' + h.t + "</span>"; }).join("");
      var m = $(root, "#dx-msg"); m.className = "kx-msg " + (act.won ? "win" : "lose");
      m.textContent = act.won ? "🎉 አሸንፈዋል +" + money(pay - stake) + " ብር" : "😕 አልተሳካም -" + money(stake) + " ብር";
      $(root, "#dx-proof").innerHTML = "🔒 Provably fair · commit <code>" + esc((start.seed_commit || "").slice(0, 12)) + "…</code>" + (act.server_seed ? " · seed <code>" + esc(act.server_seed.slice(0, 12)) + "…</code>" : "");
      if (typeof refreshBalance === "function") refreshBalance();
    } catch (e) {
      clearInterval(t); stage.classList.remove("roll");
      var m2 = $(root, "#dx-msg"); m2.className = "kx-msg bad"; m2.textContent = "❌ " + (e.message || e);
    }
    DS.busy = false; dpaint(root);
  }

  /* ========================================================================= COIN FLIP (streak) */
  var CS = { round: null, busy: false, side: "heads", min: 1, max: 10000, edge: 0.05, loaded: false, hist: [], face: "heads", MAX: 6 };
  function coin(face) { return '<div class="kx-coin ' + (face === "tails" ? "t" : "h") + '"><b>' + (face === "tails" ? "T" : "H") + "</b></div>"; }
  function mults() { return (CS.round && CS.round.mult) || (function () { var a = [], i; for (i = 1; i <= CS.MAX; i++) a.push((1 - CS.edge) / Math.pow(0.5, i)); return a; })(); }
  window.setupCoinStreak = async function () {
    var root = hideGeneric("coinstreak"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="kx-wrap">' +
        '<div class="kx-top1"><span class="kx-pill" id="cf-streak">Streak 0</span></div>' +
        '<div class="kx-stage big" id="cf-stage">' + coin("heads") + '<div class="kx-coin-lab" id="cf-lab"></div></div>' +
        '<div class="kx-chips" id="cf-hist"></div>' +
        '<div class="kx-card"><div class="kx-seg two" id="cf-side"><button type="button" data-s="heads">Heads</button><button type="button" data-s="tails">Tails</button></div>' +
        '<div class="kx-row">' + stepper("coinstreak", 10) + '<div class="kx-tile"><small id="cf-ptl">Potential win</small><b id="cf-pot" class="g">—</b></div></div>' +
        '<div class="kx-row"><button type="button" id="cf-flip" class="kx-go">🪙 Flip</button><button type="button" id="cf-cash" class="kx-cash" hidden>💰 Cash Out</button></div></div>' +
        '<div class="kx-msg" id="cf-msg" aria-live="polite"></div><div class="kx-proof" id="cf-proof"></div>' +
        '<small class="kx-note">እያንዳንዱ Flip 50/50 ነው፣ የሚመርጡት ጎን ዕድሉን አይቀይርም። ከፍ ባለ ተከታታይ ድል ሽልማቱ ይጨምራል፤ ሲሸነፉ ሁሉም ይጠፋል፣ በፈለጉት ጊዜ 💰 Cash Out ያድርጉ። ከፍተኛው 6 ተከታታይ ነው።</small></div>';
      root.querySelectorAll("#cf-side button").forEach(function (b) { b.addEventListener("click", function () { if (CS.busy) return; CS.side = b.dataset.s; hap("light"); cpaint(root); }); });
      $(root, "#cf-flip").addEventListener("click", function () { cflip(root); });
      $(root, "#cf-cash").addEventListener("click", function () { ccash(root); });
      wireStepper(root, "coinstreak", function () { return CS; });
    }
    await readLimits("coinstreak", CS);
    if (!CS.round) { try { var d = await apiFetch("/games/coinstreak/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); } catch (_) {} }
    cpaint(root);
  };
  function adopt(d) { var st = d.state || {}; CS.round = { id: d.round_id, stake: Number(d.stake), progress: Number(st.progress || 0), mult: st.multipliers || null, commit: d.seed_commit || "" }; }
  function cpaint(root) {
    var r = CS.round, p = r ? r.progress : 0, m = mults(), live = !!r;
    root.querySelectorAll("#cf-side button").forEach(function (b) { b.classList.toggle("on", b.dataset.s === CS.side); });
    $(root, "#cf-streak").textContent = "Streak " + p;
    var stake = r ? r.stake : (Number($(root, "#coinstreak-stake").value) || 0), nextM = p < CS.MAX ? m[p] : null;
    $(root, "#cf-pot").textContent = nextM ? money(stake * nextM) : "—"; $(root, "#cf-ptl").textContent = "Next flip → x" + (nextM ? nextM.toFixed(2) : "—");
    $(root, "#cf-lab").innerHTML = CS.side.charAt(0).toUpperCase() + CS.side.slice(1) + ' <b class="g">x' + (nextM ? nextM.toFixed(2) : "—") + "</b>";
    $(root, "#cf-flip").disabled = CS.busy || (p >= CS.MAX); $(root, "#cf-cash").hidden = !(live && p >= 1); $(root, "#cf-cash").disabled = CS.busy;
    $(root, "#coinstreak-stake").disabled = live || CS.busy;
    $(root, "#cf-hist").innerHTML = (function () { var h = CS.hist.slice(0, 5), s = ""; for (var i = 0; i < 5; i++) { var x = h[i]; s += '<span class="' + (x ? (x.ok ? "w" : "l") : "") + '">' + (x ? (x.f === "tails" ? "T" : "H") : "?") + "</span>"; } return s; })();
  }
  async function cflip(root) {
    if (CS.busy) return; var msg = $(root, "#cf-msg"), stage = $(root, "#cf-stage");
    try {
      CS.busy = true; cpaint(root); msg.className = "kx-msg"; msg.textContent = ""; $(root, "#cf-proof").textContent = "";
      if (!CS.round) {
        var stake = readStake(root, "coinstreak", CS);
        var r = await apiFetch("/games/coinstreak/round/start", { method: "POST", json: { stake: stake, difficulty: "easy", client_seed: makeClientSeed() } });
        CS.round = { id: r.round_id, stake: stake, progress: 0, mult: (r.state && r.state.multipliers) || null, commit: r.seed_commit || "" };
        if (typeof refreshBalance === "function") refreshBalance();
      }
      stage.classList.add("spin");
      var a = await apiFetch("/games/coinstreak/round/" + CS.round.id + "/action", { method: "POST", json: { action: "step" } });
      await sleep(700); stage.classList.remove("spin");
      var ok = a.status !== "LOST", face = ok ? CS.side : (CS.side === "heads" ? "tails" : "heads");
      stage.querySelector(".kx-coin").outerHTML = coin(face); CS.hist.unshift({ f: face, ok: ok }); CS.hist = CS.hist.slice(0, 5); hap(ok ? "light" : "error");
      if (a.status === "ACTIVE") { CS.round.progress = a.progress; }
      else { await cfinish(root, a, ok); }
    } catch (e) { stage.classList.remove("spin"); msg.className = "kx-msg bad"; msg.textContent = "❌ " + (e.message || e); }
    CS.busy = false; cpaint(root);
  }
  async function ccash(root) {
    if (CS.busy || !CS.round || CS.round.progress < 1) return; CS.busy = true; cpaint(root);
    try { var a = await apiFetch("/games/coinstreak/round/" + CS.round.id + "/action", { method: "POST", json: { action: "cashout" } }); await cfinish(root, a, true); }
    catch (e) { var m = $(root, "#cf-msg"); m.className = "kx-msg bad"; m.textContent = "❌ " + (e.message || e); }
    CS.busy = false; cpaint(root);
  }
  async function cfinish(root, a, won) {
    var r = CS.round, pay = Number(a.payout || 0), msg = $(root, "#cf-msg"), o = a.outcome || {};
    msg.className = "kx-msg " + (pay > r.stake ? "win" : "lose");
    msg.textContent = pay > r.stake ? "🎉 አሸንፈዋል +" + money(pay - r.stake) + " ብር (" + money(pay) + ")" : "😕 ተሸንፈዋል -" + money(r.stake) + " ብር";
    var seed = o.server_seed || a.server_seed;
    $(root, "#cf-proof").innerHTML = "🔒 Provably fair · commit <code>" + esc((r.commit || "").slice(0, 12)) + "…</code>" + (seed ? " · seed <code>" + esc(String(seed).slice(0, 12)) + "…</code>" : "");
    CS.round = null; if (typeof refreshBalance === "function") refreshBalance();
  }
})();
