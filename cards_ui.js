/* BACCARAT + BLACKJACK client UIs. Presentation only: the server shuffles, deals, draws and pays everything.
   Loaded after app.js (uses its helpers: apiFetch, refreshBalance, haptic, makeClientSeed, sha256Hex). */
(function () {
  "use strict";
  var $ = function (r, s) { return r.querySelector(s); };
  var esc = function (v) { return (typeof escapeHtml === "function") ? escapeHtml(String(v)) : String(v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var snd = function (n) { if (typeof gameSound === "function") try { gameSound(n); } catch (_) {} };
  var SUITS = ["♠", "♥", "♦", "♣"], RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];

  function card(c, opts) {
    opts = opts || {};
    if (c === null || c === undefined) return '<div class="pc back' + (opts.fresh ? " deal" : "") + '"></div>';
    var s = Math.floor(c / 13) % 4, r = RANKS[c % 13], red = (s === 1 || s === 2);
    return '<div class="pc ' + (red ? "red" : "blk") + (opts.fresh ? " deal" : "") + '"><b>' + r + '</b><i>' + SUITS[s] + '</i><span>' + SUITS[s] + "</span></div>";
  }
  function prepare(key) {
    var root = document.getElementById(key + "-controls"); if (!root) return null;
    if (root.dataset.cu === "1") return root;
    root.dataset.cu = "1";
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(key + s); if (e) e.style.display = "none"; });
    var page = document.getElementById("page-" + key); if (page) page.classList.add("ng-page", "cu-page", "cu-page-" + key);
    return root;
  }
  function stakeBlock(key) {
    return '<div class="ng-stake"><label for="' + key + '-stake">Bet (ብር)</label><input id="' + key + '-stake" class="game-stake" type="number" min="0.01" step="0.01" value="10" inputmode="decimal">' +
      '<div class="ng-chips">' + [10, 20, 50, 100].map(function (v) { return '<button type="button" data-chip="' + v + '">' + v + "</button>"; }).join("") + "</div></div>";
  }
  function wireChips(root, key) {
    root.querySelectorAll("[data-chip]").forEach(function (b) { b.addEventListener("click", function () { var i = $(root, "#" + key + "-stake"); if (i && !i.disabled) { i.value = b.dataset.chip; hap("light"); } }); });
  }
  async function limits(key, st) {
    if (st.limits) return st.limits;
    try { var s = await apiFetch("/games/" + key + "/settings"); st.limits = { min: Number(s.min_stake) || 1, max: Number(s.max_stake) || 10000, edge: (s.house_edge != null ? Number(s.house_edge) : 0.05), enabled: s.enabled !== false }; }
    catch (_) { st.limits = { min: 1, max: 10000, edge: 0.05, enabled: true }; }
    return st.limits;
  }
  function readStake(root, key, lim) {
    var v = Number($(root, "#" + key + "-stake").value);
    if (!(v > 0)) throw new Error("የBet መጠን ትክክል ያስገቡ");
    if (v < lim.min || v > lim.max) throw new Error("Bet ከ " + lim.min + " እስከ " + lim.max + " ብር መሆን አለበት");
    return v;
  }
  function say(root, html, cls) { var b = $(root, ".ng-result"); if (b) { b.className = "ng-result " + (cls || ""); b.innerHTML = html; } }
  function proof(root, commit, seed) {
    var box = $(root, ".ng-proof"); if (!box) return;
    if (!seed) { box.innerHTML = ""; return; }
    box.innerHTML = '🔒 Provably fair · commit <code>' + esc((commit || "").slice(0, 12)) + '…</code> · seed <code>' + esc(seed.slice(0, 12)) + '…</code> <span class="ng-ok">⏳</span>';
    if (typeof sha256Hex !== "function") return;
    sha256Hex(seed).then(function (h) { var s = $(box, ".ng-ok"); if (s) s.textContent = (!commit || h === commit) ? "✅ ተረጋግጧል" : "❌ አልተመሳሰለም"; }).catch(function () {});
  }

  /* ======================================================================= BACCARAT */
  var BW = { player: 0.4462466093, banker: 0.4585974226, tie: 0.0951559680 }, BM = { player: 2.0, banker: 1.95, tie: 9.0 };
  var B = { sel: "player", busy: false, limits: null, hist: [] };
  function bscale(choice, target) { var t = choice === "tie" ? 0 : BW.tie; return Math.max(0, (target - t) / (BW[choice] * BM[choice])); }
  function bpay(choice, edge) { return BM[choice] * bscale(choice, 1 - edge); }
  window.setupBaccarat = async function () {
    var root = prepare("baccarat"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="ng-wrap">' +
        '<div class="bc-table"><div class="bc-hand" id="bc-p"><div class="bc-lab">PLAYER <b id="bc-pt"></b></div><div class="bc-cards"></div></div>' +
        '<div class="bc-hand" id="bc-b"><div class="bc-lab">BANKER <b id="bc-bt"></b></div><div class="bc-cards"></div></div></div>' +
        '<div class="bc-hist" id="bc-hist"></div>' +
        '<div class="ng-sub">ማን ያሸንፋል? ይምረጡ</div>' +
        '<div class="bc-bets" id="bc-bets"></div>' +
        stakeBlock("baccarat") +
        '<button type="button" class="primary-game-btn ng-go" id="bc-go">🎴 ካርድ ስጥ</button>' +
        '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
        '<small class="ng-note">8 ዴክ። ካርድ ማውጣት በ Punto Banco ህግ ነው። Player/Banker ላይ ከተወራረዱ እና Tie ከወጣ ገንዘብዎ ይመለሳል (Push)።</small></div>';
      wireChips(root, "baccarat");
      $(root, "#bc-go").addEventListener("click", function () { bdeal(root); });
    }
    var lim = await limits("baccarat", B); bbets(root, lim.edge);
  };
  function bbets(root, edge) {
    var el = $(root, "#bc-bets"); if (!el) return;
    el.innerHTML = [["player", "👤 Player"], ["banker", "🏦 Banker"], ["tie", "🤝 Tie"]].map(function (x) {
      return '<button type="button" class="bc-bet' + (B.sel === x[0] ? " on" : "") + '" data-c="' + x[0] + '">' + x[1] + "<small>ይከፍላል " + bpay(x[0], edge).toFixed(2) + "×</small></button>";
    }).join("");
    el.querySelectorAll(".bc-bet").forEach(function (b) { b.addEventListener("click", function () { if (B.busy) return; B.sel = b.dataset.c; hap("light"); bbets(root, edge); }); });
  }
  async function bdeal(root) {
    if (B.busy) return;
    try {
      var lim = await limits("baccarat", B), stake = readStake(root, "baccarat", lim);
      B.busy = true; $(root, "#bc-go").disabled = true; say(root, ""); proof(root, "", "");
      ["#bc-p", "#bc-b"].forEach(function (s) { $(root, s + " .bc-cards").innerHTML = ""; });
      $(root, "#bc-pt").textContent = ""; $(root, "#bc-bt").textContent = "";
      snd("round");
      var start = await apiFetch("/games/baccarat/round/start", { method: "POST", json: { stake: stake, choice: B.sel, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/baccarat/round/" + start.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome, order = [["p", 0], ["b", 0], ["p", 1], ["b", 1], ["p", 2], ["b", 2]];
      var shown = { p: [], b: [] };
      for (var i = 0; i < order.length; i++) {
        var side = order[i][0], idx = order[i][1], hand = side === "p" ? o.player : o.banker;
        if (idx >= hand.length) continue;
        await sleep(i < 4 ? 450 : 700); shown[side].push(hand[idx]); hap("light");
        $(root, "#bc-" + side + " .bc-cards").innerHTML = shown[side].map(function (c) { return card(c, { fresh: true }); }).join("");
        var tot = shown[side].reduce(function (a, c) { var r = (c % 13) + 1; return a + (r < 10 ? r : 0); }, 0) % 10;
        $(root, "#bc-" + side + "t").textContent = tot;
      }
      await sleep(450);
      var wl = { player: "👤 Player ያሸንፋል", banker: "🏦 Banker ያሸንፋል", tie: "🤝 Tie" }[o.winner];
      B.hist.unshift(o.winner); B.hist = B.hist.slice(0, 14);
      $(root, "#bc-hist").innerHTML = B.hist.map(function (w) { return '<span class="bc-dot ' + w + '">' + (w === "player" ? "P" : w === "banker" ? "B" : "T") + "</span>"; }).join("");
      var pay = Number(act.payout || 0), net = Math.round((pay - stake) * 100) / 100;
      if (o.push) say(root, "<b>" + wl + "</b><br>↩️ Push -- " + money(pay) + " ብር ተመለሰ", "ng-push");
      else if (act.won) say(root, "<b>" + wl + "</b><br>🎉 አሸንፈዋል +" + money(net) + " ብር (" + money(pay) + ")", "ng-win");
      else say(root, "<b>" + wl + "</b><br>😕 አልተሳካም -" + money(stake) + " ብር", "ng-lose");
      proof(root, start.seed_commit, act.server_seed);
      if (typeof refreshBalance === "function") refreshBalance();
    } catch (e) { say(root, "❌ " + esc(e.message || e), "ng-lose"); }
    B.busy = false; $(root, "#bc-go").disabled = false;
  }

  /* ======================================================================= BLACKJACK */
  var J = { busy: false, limits: null, round: null, last: 10 };
  window.setupBlackjack = async function () {
    var root = prepare("blackjack"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="ng-wrap">' +
        '<div class="bj-table">' +
          '<div class="bj-hand"><div class="bj-lab">DEALER <b id="bj-dt"></b></div><div class="bj-cards" id="bj-d"></div></div>' +
          '<div class="bj-mid" id="bj-mid">ካርድ ለመጀመር Bet ያስገቡ</div>' +
          '<div class="bj-hand"><div class="bj-lab">YOU <b id="bj-pt"></b></div><div class="bj-cards" id="bj-p"></div></div>' +
        "</div>" +
        '<div id="bj-bet">' + stakeBlock("blackjack") + '<button type="button" class="primary-game-btn ng-go" id="bj-deal">🃏 ካርድ ስጥ</button></div>' +
        '<div class="bj-actions" id="bj-act" hidden><button type="button" data-a="hit" class="bj-a hit">➕ Hit</button><button type="button" data-a="stand" class="bj-a stand">✋ Stand</button><button type="button" data-a="double" class="bj-a dbl">✖️2 Double</button></div>' +
        '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
        '<small class="ng-note" id="bj-note"></small></div>';
      wireChips(root, "blackjack");
      $(root, "#bj-deal").addEventListener("click", function () { jdeal(root); });
      $(root, "#bj-act").addEventListener("click", function (e) { var b = e.target.closest("button[data-a]"); if (b) jact(root, b.dataset.a); });
    }
    var lim = await limits("blackjack", J);
    var win = (2 * (1 - lim.edge)).toFixed(2), bj = (2.5 * (1 - lim.edge)).toFixed(2);
    $(root, "#bj-note").textContent = "6 ዴክ · Dealer በ17 ሁሉ ይቆማል · Win " + win + "× · Blackjack " + bj + "× · Push = ገንዘብ ይመለሳል · Split/Insurance የለም።";
    try { var a = await apiFetch("/blackjack/active"); if (a && a.round_id) { J.round = a; jrender(root, a, false); } else if (!J.round || J.round.status !== "ACTIVE") jidle(root); }
    catch (_) { if (!J.round) jidle(root); }
  };
  function jidle(root) { $(root, "#bj-bet").hidden = false; $(root, "#bj-act").hidden = true; }
  function jrender(root, r, animate) {
    J.round = r; var active = r.status === "ACTIVE";
    $(root, "#bj-p").innerHTML = r.player.map(function (c) { return card(c, { fresh: animate }); }).join("");
    var d = r.dealer.map(function (c) { return card(c, { fresh: animate }); }).join(""); if (active && r.dealer_hidden) d += card(null, { fresh: animate });
    $(root, "#bj-d").innerHTML = d;
    $(root, "#bj-pt").textContent = r.player_total; $(root, "#bj-dt").textContent = active ? r.dealer_total + "+?" : r.dealer_total;
    $(root, "#bj-bet").hidden = active; $(root, "#bj-act").hidden = !active;
    if (active) {
      $(root, '[data-a="double"]').hidden = (r.actions || []).indexOf("double") < 0;
      $(root, "#bj-mid").innerHTML = "Bet <b>" + money(r.total_stake) + "</b> ብር";
      say(root, ""); proof(root, r.seed_commit, "");
    }
  }
  async function jdeal(root) {
    if (J.busy) return; J.busy = true; $(root, "#bj-deal").disabled = true;
    try {
      var lim = await limits("blackjack", J), stake = readStake(root, "blackjack", lim); J.last = stake;
      snd("round"); say(root, ""); proof(root, "", "");
      var r = await apiFetch("/blackjack/start", { method: "POST", json: { stake: stake, client_seed: makeClientSeed() } });
      hap("light"); jrender(root, r, true); if (typeof refreshBalance === "function") refreshBalance();
      if (r.status !== "ACTIVE") await jfinish(root, r);
    } catch (e) { say(root, "❌ " + esc(e.message || e), "ng-lose"); }
    J.busy = false; $(root, "#bj-deal").disabled = false;
  }
  async function jact(root, a) {
    if (J.busy || !J.round || J.round.status !== "ACTIVE") return; J.busy = true;
    root.querySelectorAll(".bj-a").forEach(function (b) { b.disabled = true; });
    try {
      var r = await apiFetch("/blackjack/" + J.round.round_id + "/action", { method: "POST", json: { action: a, seq: J.round.player.length } });
      hap("light");
      if (r.status === "ACTIVE") jrender(root, r, true);
      else { jrender(root, r, true); await jfinish(root, r); }
      if (typeof refreshBalance === "function") refreshBalance();
    } catch (e) {
      say(root, "❌ " + esc(e.message || e), "ng-lose");
      try { var s = await apiFetch("/blackjack/active"); if (s && s.round_id) jrender(root, s, false); else jidle(root); } catch (_) {}
    }
    root.querySelectorAll(".bj-a").forEach(function (b) { b.disabled = false; }); J.busy = false;
  }
  async function jfinish(root, r) {
    await sleep(350);
    var o = r.outcome || {}, pay = Number(r.payout || 0), tot = Number(r.total_stake), net = Math.round((pay - tot) * 100) / 100;
    var title = { blackjack: "🂡 BLACKJACK!", win: "🎉 አሸንፈዋል!", push: "↩️ Push", lose: (o.player_total > 21 ? "💥 Bust" : "😕 ተሸንፈዋል") }[o.result] || "";
    var cls = (o.result === "win" || o.result === "blackjack") && pay > tot ? "ng-win" : o.result === "push" ? "ng-push" : "ng-lose";
    say(root, "<b>" + title + "</b><br>" + (cls === "ng-win" ? "+" + money(net) + " ብር (" + money(pay) + ")" : o.result === "push" ? money(pay) + " ብር ተመለሰ" : "-" + money(tot) + " ብር") + (o.doubled ? " · Double" : ""), cls);
    $(root, "#bj-mid").textContent = "ዙሩ አልቋል";
    proof(root, r.seed_commit, r.server_seed); $(root, "#bj-deal").textContent = "🃏 ድጋሚ ስጥ";
  }

  /* ======================================================================= DRAGON TIGER */
  var DW = { dragon: 0.46265060240963857, tiger: 0.46265060240963857, tie: 0.0746987951807229 }, DMU = { dragon: 2.0, tiger: 2.0, tie: 9.0 };
  var D = { sel: "dragon", busy: false, limits: null, hist: [] };
  function dpay(choice, edge) { var t = choice === "tie" ? 0 : DW.tie; return DMU[choice] * Math.max(0, ((1 - edge) - t) / (DW[choice] * DMU[choice])); }
  window.setupDragonTiger = async function () {
    var root = prepare("dragontiger"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="ng-wrap">' +
        '<div class="dt-table"><div class="dt-side" id="dt-d"><div class="dt-lab">🐉 DRAGON</div><div class="dt-slot"></div></div><div class="dt-vs">VS</div>' +
        '<div class="dt-side" id="dt-t"><div class="dt-lab">🐯 TIGER</div><div class="dt-slot"></div></div></div>' +
        '<div class="bc-hist" id="dt-hist"></div><div class="ng-sub">ትልቁ ካርድ የትኛው ነው? (A ትንሹ፣ K ትልቁ)</div>' +
        '<div class="bc-bets" id="dt-bets"></div>' + stakeBlock("dragontiger") +
        '<button type="button" class="primary-game-btn ng-go" id="dt-go">🐉 ካርድ ስጥ</button>' +
        '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
        '<small class="ng-note">8 ዴክ፣ ለእያንዳንዱ አንድ ካርድ። Dragon/Tiger ላይ ከተወራረዱ እና እኩል ከወጣ ገንዘብዎ ይመለሳል (Push)።</small></div>';
      wireChips(root, "dragontiger");
      $(root, "#dt-go").addEventListener("click", function () { ddeal(root); });
    }
    var lim = await limits("dragontiger", D); dbets(root, lim.edge);
  };
  function dbets(root, edge) {
    var el = $(root, "#dt-bets"); if (!el) return;
    el.innerHTML = [["dragon", "🐉 Dragon"], ["tiger", "🐯 Tiger"], ["tie", "🤝 Tie"]].map(function (x) {
      return '<button type="button" class="bc-bet' + (D.sel === x[0] ? " on" : "") + '" data-c="' + x[0] + '">' + x[1] + "<small>ይከፍላል " + dpay(x[0], edge).toFixed(2) + "×</small></button>";
    }).join("");
    el.querySelectorAll(".bc-bet").forEach(function (b) { b.addEventListener("click", function () { if (D.busy) return; D.sel = b.dataset.c; hap("light"); dbets(root, edge); }); });
  }
  async function ddeal(root) {
    if (D.busy) return;
    try {
      var lim = await limits("dragontiger", D), stake = readStake(root, "dragontiger", lim);
      D.busy = true; $(root, "#dt-go").disabled = true; say(root, ""); proof(root, "", "");
      ["#dt-d", "#dt-t"].forEach(function (s) { $(root, s + " .dt-slot").innerHTML = card(null); });
      snd("round");
      var start = await apiFetch("/games/dragontiger/round/start", { method: "POST", json: { stake: stake, choice: D.sel, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/dragontiger/round/" + start.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome;
      await sleep(500); $(root, "#dt-d .dt-slot").innerHTML = card(o.dragon, { fresh: true }); hap("light");
      await sleep(650); $(root, "#dt-t .dt-slot").innerHTML = card(o.tiger, { fresh: true }); hap("light");
      await sleep(450);
      var wl = { dragon: "🐉 Dragon ያሸንፋል", tiger: "🐯 Tiger ያሸንፋል", tie: "🤝 እኩል (Tie)" }[o.winner];
      D.hist.unshift(o.winner); D.hist = D.hist.slice(0, 14);
      $(root, "#dt-hist").innerHTML = D.hist.map(function (w) { return '<span class="bc-dot ' + (w === "dragon" ? "player" : w === "tiger" ? "banker" : "tie") + '">' + (w === "dragon" ? "D" : w === "tiger" ? "T" : "=") + "</span>"; }).join("");
      var pay = Number(act.payout || 0), net = Math.round((pay - stake) * 100) / 100;
      if (o.push) say(root, "<b>" + wl + "</b><br>↩️ Push -- " + money(pay) + " ብር ተመለሰ", "ng-push");
      else if (act.won) say(root, "<b>" + wl + "</b><br>🎉 አሸንፈዋል +" + money(net) + " ብር (" + money(pay) + ")", "ng-win");
      else say(root, "<b>" + wl + "</b><br>😕 አልተሳካም -" + money(stake) + " ብር", "ng-lose");
      proof(root, start.seed_commit, act.server_seed);
      if (typeof refreshBalance === "function") refreshBalance();
    } catch (e) { say(root, "❌ " + esc(e.message || e), "ng-lose"); }
    D.busy = false; $(root, "#dt-go").disabled = false;
  }

  /* ======================================================================= ANDAR BAHAR */
  var AW = { andar: 0.5150060024009604, bahar: 0.4849939975990396 };
  var A = { sel: "andar", busy: false, limits: null, hist: [] };
  function apay(choice, edge) { return (1 - edge) / AW[choice]; }
  window.setupAndarBahar = async function () {
    var root = prepare("andarbahar"); if (!root) return;
    if (!root.dataset.built) {
      root.dataset.built = "1";
      root.innerHTML = '<div class="ng-wrap">' +
        '<div class="ab-table"><div class="ab-joker"><div class="ab-lab">🃏 JOKER</div><div id="ab-j">' + card(null) + '</div></div>' +
        '<div class="ab-row"><div class="ab-lab">አንደር <b id="ab-an"></b></div><div class="ab-cards" id="ab-a"></div></div>' +
        '<div class="ab-row"><div class="ab-lab">ባሃር <b id="ab-bn"></b></div><div class="ab-cards" id="ab-b"></div></div></div>' +
        '<div class="bc-hist" id="ab-hist"></div><div class="ng-sub">ጆከሩን ቁጥር መጀመሪያ የሚያገኘው ወገን ያሸንፋል</div>' +
        '<div class="ab-bets" id="ab-bets"></div>' + stakeBlock("andarbahar") +
        '<button type="button" class="primary-game-btn ng-go" id="ab-go">🃏 ካርድ ስጥ</button>' +
        '<div class="ng-result" aria-live="polite"></div><div class="ng-proof"></div>' +
        '<small class="ng-note">አንድ ዴክ። ካርዶች አንደር፣ ባሃር በተራ ይሰጣሉ (አንደር መጀመሪያ)። አንደር ትንሽ የበለጠ ዕድል ስላለው ክፍያው ዝቅ ይላል።</small></div>';
      wireChips(root, "andarbahar");
      $(root, "#ab-go").addEventListener("click", function () { adeal(root); });
    }
    var lim = await limits("andarbahar", A); abets(root, lim.edge);
  };
  function abets(root, edge) {
    var el = $(root, "#ab-bets"); if (!el) return;
    el.innerHTML = [["andar", "⬅️ አንደር"], ["bahar", "➡️ ባሃር"]].map(function (x) {
      return '<button type="button" class="bc-bet' + (A.sel === x[0] ? " on" : "") + '" data-c="' + x[0] + '">' + x[1] + "<small>ይከፍላል " + apay(x[0], edge).toFixed(2) + "×</small></button>";
    }).join("");
    el.querySelectorAll(".bc-bet").forEach(function (b) { b.addEventListener("click", function () { if (A.busy) return; A.sel = b.dataset.c; hap("light"); abets(root, edge); }); });
  }
  async function adeal(root) {
    if (A.busy) return;
    try {
      var lim = await limits("andarbahar", A), stake = readStake(root, "andarbahar", lim);
      A.busy = true; $(root, "#ab-go").disabled = true; say(root, ""); proof(root, "", "");
      $(root, "#ab-j").innerHTML = card(null); $(root, "#ab-a").innerHTML = ""; $(root, "#ab-b").innerHTML = ""; $(root, "#ab-an").textContent = ""; $(root, "#ab-bn").textContent = "";
      snd("round");
      var start = await apiFetch("/games/andarbahar/round/start", { method: "POST", json: { stake: stake, choice: A.sel, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/andarbahar/round/" + start.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome;
      await sleep(450); $(root, "#ab-j").innerHTML = card(o.joker, { fresh: true }); hap("light");
      var seq = [], n = Math.max(o.andar.length, o.bahar.length);
      for (var i = 0; i < n; i++) { if (i < o.andar.length) seq.push(["a", o.andar[i]]); if (i < o.bahar.length) seq.push(["b", o.bahar[i]]); }
      var gap = Math.max(60, Math.min(420, 3200 / seq.length)), cnt = { a: 0, b: 0 };
      for (var k = 0; k < seq.length; k++) {
        await sleep(gap); var row = $(root, seq[k][0] === "a" ? "#ab-a" : "#ab-b");
        row.insertAdjacentHTML("beforeend", card(seq[k][1], { fresh: true })); row.scrollLeft = row.scrollWidth; cnt[seq[k][0]]++;
        $(root, seq[k][0] === "a" ? "#ab-an" : "#ab-bn").textContent = cnt[seq[k][0]]; if (k % 3 === 0) hap("light");
      }
      await sleep(450);
      var wl = { andar: "⬅️ አንደር ያሸንፋል", bahar: "➡️ ባሃር ያሸንፋል" }[o.winner];
      A.hist.unshift(o.winner); A.hist = A.hist.slice(0, 14);
      $(root, "#ab-hist").innerHTML = A.hist.map(function (w) { return '<span class="bc-dot ' + (w === "andar" ? "player" : "banker") + '">' + (w === "andar" ? "A" : "B") + "</span>"; }).join("");
      var pay = Number(act.payout || 0), net = Math.round((pay - stake) * 100) / 100;
      if (act.won) say(root, "<b>" + wl + "</b><br>🎉 አሸንፈዋል +" + money(net) + " ብር (" + money(pay) + ")", "ng-win");
      else say(root, "<b>" + wl + "</b><br>😕 አልተሳካም -" + money(stake) + " ብር", "ng-lose");
      proof(root, start.seed_commit, act.server_seed);
      if (typeof refreshBalance === "function") refreshBalance();
    } catch (e) { say(root, "❌ " + esc(e.message || e), "ng-lose"); }
    A.busy = false; $(root, "#ab-go").disabled = false;
  }
})();
