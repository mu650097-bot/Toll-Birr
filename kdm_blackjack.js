/* BLACKJACK (new look): green felt table, Hit / Stand / Double. Same server engine as before: the server shuffles, deals, draws for the
   dealer (stands on 17) and pays. This file only draws what the server returns. Split is not offered by the engine, so the button is shown disabled.
   Loaded after cards_ui.js; replaces window.setupBlackjack. Presentation only. */
(function () {
  "use strict";
  var KEY = "blackjack";
  var S = { busy: false, min: 1, max: 10000, edge: 0.05, loaded: false, round: null, last: 50, over: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var esc = function (v) { return String(v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var SUITS = ["♠", "♥", "♦", "♣"], RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
  function card(c, fresh) {
    if (c === null || c === undefined) return '<div class="bjc back' + (fresh ? " fresh" : "") + '"></div>';
    var s = Math.floor(c / 13) % 4, red = s === 1 || s === 2;
    return '<div class="bjc ' + (red ? "red" : "") + (fresh ? " fresh" : "") + '"><b>' + RANKS[c % 13] + "</b><i>" + SUITS[s] + "</i></div>";
  }
  function payX() { return 2 * (1 - S.edge); }
  function bjX() { return 2.5 * (1 - S.edge); }

  window.setupBlackjack = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("ng-page", "cu-page", "cu-page-blackjack"); pg.classList.add("kx-page"); }
    if (!root.dataset.bj2) {
      root.dataset.bj2 = "1";
      root.innerHTML = '<div class="bk-wrap"><div class="bk-table">' +
        '<div class="bk-lab" id="bk-dl">Dealer</div><div class="bk-cards" id="bk-d"></div>' +
        '<div class="bk-mid"><div class="bk-pay" id="bk-pay"></div><small id="bk-rule">Dealer stands on 17</small><div class="bk-chip" id="bk-chip" hidden></div></div>' +
        '<div class="bk-cards" id="bk-p"></div><div class="bk-lab" id="bk-pl">You</div></div>' +
        '<div class="bk-acts" id="bk-acts"><button type="button" data-a="hit" class="bk-a hit">Hit</button><button type="button" data-a="stand" class="bk-a stand">Stand</button>' +
        '<button type="button" data-a="double" class="bk-a dbl">Double</button><button type="button" class="bk-a split" disabled title="Split is not available">Split</button></div>' +
        '<div class="bk-bet"><div class="av-bet-col"><label for="blackjack-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button>' +
        '<input id="blackjack-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="av-bet-col"><label id="bk-wl">Win if you stand</label><b class="bk-win" id="bk-win">—</b></div></div>' +
        '<button type="button" id="bk-deal" class="av-go">Deal</button>' +
        '<div class="kx-msg" id="bk-msg" aria-live="polite"></div><div class="kx-proof" id="bk-proof"></div>' +
        '<small class="kx-note" id="bk-note"></small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || active()) return; var i = $(root, "#blackjack-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      $(root, "#blackjack-stake").addEventListener("input", function () { paint(root); });
      $(root, "#bk-deal").addEventListener("click", function () { deal(root); });
      $(root, "#bk-acts").addEventListener("click", function (e) { var b = e.target.closest("button[data-a]"); if (b) act(root, b.dataset.a); });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.edge = s.house_edge != null ? Number(s.house_edge) : 0.05; } catch (_) {} S.loaded = true; }
    $(root, "#bk-note").textContent = "6 ዴክ · ሻጩ በ17 ይቆማል · አሸናፊ " + payX().toFixed(2) + "× · Blackjack " + bjX().toFixed(2) + "× · Push = ገንዘብ ይመለሳል · Split/Insurance የለም። ሰርቨሩ ካርዶቹን ይደባልቃል፣ ይሰጣል፣ ይከፍላል።";
    if (!S.round) { try { var a = await apiFetch("/blackjack/active"); if (a && a.round_id && a.status === "ACTIVE") { S.round = a; S.over = null; } } catch (_) {} }
    paint(root, false);
  };
  function active() { return !!S.round && S.round.status === "ACTIVE"; }

  function paint(root, fresh) {
    var r = S.round || S.over, act = active();
    $(root, "#bk-d").innerHTML = r ? r.dealer.map(function (c) { return card(c, fresh); }).join("") + (act && r.dealer_hidden ? card(null, fresh) : "") : card(null) + card(null);
    $(root, "#bk-p").innerHTML = r ? r.player.map(function (c) { return card(c, fresh); }).join("") : card(null) + card(null);
    $(root, "#bk-dl").textContent = r ? "Dealer · " + (act ? r.dealer_total + "+?" : r.dealer_total) : "Dealer";
    $(root, "#bk-pl").textContent = r ? "You · " + r.player_total : "You";
    $(root, "#bk-pay").textContent = "BLACKJACK PAYS " + bjX().toFixed(2) + "×";
    var chip = $(root, "#bk-chip"); chip.hidden = !r; if (r) chip.textContent = money(r.total_stake);
    var inp = $(root, "#blackjack-stake"); inp.disabled = act || S.busy; root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = act || S.busy; });
    $(root, "#bk-acts").classList.toggle("off", !act);
    root.querySelectorAll(".bk-a:not(.split)").forEach(function (b) { b.disabled = !act || S.busy; });
    if (act) $(root, '[data-a="double"]').disabled = S.busy || (r.actions || []).indexOf("double") < 0;
    var stake = act ? Number(r.total_stake) : (Number(inp.value) || 0);
    $(root, "#bk-wl").textContent = act ? "Win if you stand" : (S.over ? (S.over.payout > 0 ? "Paid out" : "Round result") : "Win if you stand");
    $(root, "#bk-win").textContent = act ? money(stake * payX()) + " ETB" : (S.over ? money(S.over.payout) + " ETB" : money(stake * payX()) + " ETB");
    $(root, "#bk-deal").hidden = act; $(root, "#bk-deal").disabled = S.busy;
    $(root, "#bk-deal").textContent = S.over ? "Deal again · " + money(Number(inp.value) || 0) + " ETB" : "Deal";
  }
  function say(root, cls, t) { var e = $(root, "#bk-msg"); e.className = "kx-msg " + cls; e.textContent = t; }

  async function deal(root) {
    if (S.busy || active()) return; var stake = Number($(root, "#blackjack-stake").value);
    if (!(stake > 0)) return say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ");
    if (stake < S.min || stake > S.max) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.over = null; S.last = stake; say(root, "", ""); $(root, "#bk-proof").textContent = ""; paint(root);
    try {
      var r = await apiFetch("/blackjack/start", { method: "POST", json: { stake: stake, client_seed: makeClientSeed() } });
      S.round = r; hap("light"); paint(root, true); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
      if (r.status !== "ACTIVE") await finish(root, r);
    } catch (e) { say(root, "bad", "❌ " + e.message); }
    S.busy = false; paint(root);
  }
  async function act(root, a) {
    var r = S.round; if (!r || S.busy || r.status !== "ACTIVE") return; S.busy = true; paint(root);
    try {
      var n = await apiFetch("/blackjack/" + r.round_id + "/action", { method: "POST", json: { action: a, seq: r.player.length } });
      hap("light"); S.round = n; paint(root, true); if (n.status !== "ACTIVE") await finish(root, n);
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) {
      say(root, "bad", "❌ " + e.message);
      try { var s = await apiFetch("/blackjack/active"); if (s && s.round_id && s.status === "ACTIVE") S.round = s; else S.round = null; } catch (_) {}
    }
    S.busy = false; paint(root);
  }
  async function finish(root, r) {
    await sleep(350);
    var o = r.outcome || {}, pay = Number(r.payout || 0), tot = Number(r.total_stake), net = Math.round((pay - tot) * 100) / 100;
    S.over = { player: r.player, dealer: r.dealer, player_total: r.player_total, dealer_total: r.dealer_total, total_stake: tot, payout: pay, status: r.status, dealer_hidden: false, actions: [] };
    S.round = null;
    var title = { blackjack: "🂡 BLACKJACK!", win: "🎉 አሸንፈዋል!", push: "↩️ Push", lose: (o.player_total > 21 ? "💥 Bust" : "😕 ተሸንፈዋል") }[o.result] || "";
    var win = (o.result === "win" || o.result === "blackjack") && pay > tot;
    say(root, win ? "win" : o.result === "push" ? "bad" : "lose", title + " " + (win ? "+" + money(net) + " ብር" : o.result === "push" ? money(pay) + " ብር ተመለሰ" : "-" + money(tot) + " ብር") + (o.doubled ? " · Double" : ""));
    hap(win ? "success" : o.result === "push" ? "light" : "error");
    if (r.server_seed) $(root, "#bk-proof").textContent = "COMMIT " + String(r.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(r.server_seed).slice(0, 12) + "…";
  }
})();
