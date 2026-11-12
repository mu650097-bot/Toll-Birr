/* BACCARAT (new look): pick Player / Tie / Banker, build the bet with chips, Deal. Same server engine as before: the server shuffles (8 decks),
   deals and draws by Punto Banco rules and pays; payout per side is computed from the disclosed house edge, so the "pays" numbers are real.
   One side per round (the engine takes a single choice). Loaded after cards_ui.js; replaces window.setupBaccarat. Presentation only. */
(function () {
  "use strict";
  var KEY = "baccarat", CHIPS = [10, 50, 100, 500];
  var BW = { player: 0.4462466093, banker: 0.4585974226, tie: 0.0951559680 }, BM = { player: 2.0, banker: 1.95, tie: 9.0 };   // MUST match the engine
  var S = { sel: "player", total: 50, busy: false, min: 1, max: 10000, edge: 0.05, loaded: false, hist: [] };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var SUITS = ["♠", "♥", "♦", "♣"], RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
  function card(c) { var s = Math.floor(c / 13) % 4, red = s === 1 || s === 2; return '<div class="bjc fresh ' + (red ? "red" : "") + '"><b>' + RANKS[c % 13] + "</b><i>" + SUITS[s] + "</i></div>"; }
  function val(c) { var r = (c % 13) + 1; return r < 10 ? r : 0; }
  function tot(h) { return h.reduce(function (a, c) { return a + val(c); }, 0) % 10; }
  function scale(choice, target) { var t = choice === "tie" ? 0 : BW.tie; return Math.max(0, (target - t) / (BW[choice] * BM[choice])); }
  function pay(choice) { return BM[choice] * scale(choice, 1 - S.edge); }
  var NAMES = { player: "Player", tie: "Tie", banker: "Banker" };

  window.setupBaccarat = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("ng-page", "cu-page", "cu-page-baccarat"); pg.classList.add("kx-page"); }
    if (!root.dataset.bc2) {
      root.dataset.bc2 = "1";
      root.innerHTML = '<div class="bq-wrap"><div class="bq-table">' +
        '<div class="bq-sides"><div class="bq-side"><span class="bq-tag p">PLAYER</span><div class="bq-cards" id="bq-pc"></div><div class="bq-tot" id="bq-pt">—</div></div>' +
        '<div class="bq-side"><span class="bq-tag b">BANKER</span><div class="bq-cards" id="bq-bc"></div><div class="bq-tot" id="bq-bt">—</div></div></div>' +
        '<div class="bq-banner" id="bq-ban">Pick a side and press Deal</div></div>' +
        '<div class="bq-hist" id="bq-hist"></div>' +
        '<div class="bq-bets" id="bq-bets"></div>' +
        '<div class="bq-chips" id="bq-chips">' + CHIPS.map(function (c) { return '<button type="button" data-c="' + c + '">' + c + "</button>"; }).join("") + "</div>" +
        '<div class="bq-row"><div class="bq-total"><small>Total bet</small><b id="bq-tb">50.00</b></div><button type="button" id="bq-clear" class="bq-clear">Clear</button><button type="button" id="bq-deal" class="av-go">Deal</button></div>' +
        '<div class="kx-msg" id="bq-msg" aria-live="polite"></div><div class="kx-proof" id="bq-proof"></div>' +
        '<small class="kx-note">8 ዴክ፤ ካርድ ማውጣት በ Punto Banco ህግ ነው። በአንድ ዙር አንድ ጎን ብቻ ይመርጣሉ። Player/Banker ላይ ከተወራረዱ እና Tie ከወጣ ገንዘብዎ ይመለሳል (Push)። "pays" የሚለው ቁጥር እውነተኛው ክፍያ ነው (ከቤቱ ድርሻ ጋር የተሰላ)።</small></div>';
      $(root, "#bq-chips").addEventListener("click", function (e) { var b = e.target.closest("button[data-c]"); if (!b || S.busy) return; S.total = Math.min(S.max, S.total + Number(b.dataset.c)); hap("light"); paint(root); });
      $(root, "#bq-clear").addEventListener("click", function () { if (S.busy) return; S.total = 0; hap("light"); paint(root); });
      $(root, "#bq-deal").addEventListener("click", function () { deal(root); });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; S.edge = s.house_edge != null ? Number(s.house_edge) : 0.05; } catch (_) {} S.loaded = true; }
    paint(root);
  };
  function paint(root) {
    $(root, "#bq-bets").innerHTML = ["player", "tie", "banker"].map(function (k) {
      return '<button type="button" class="bq-bet ' + k + (S.sel === k ? " on" : "") + '" data-k="' + k + '"' + (S.busy ? " disabled" : "") + "><b>" + NAMES[k] + "</b><small>pays x" + pay(k).toFixed(2) + "</small></button>";
    }).join("");
    $(root, "#bq-bets").querySelectorAll(".bq-bet").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; S.sel = b.dataset.k; hap("light"); paint(root); }); });
    $(root, "#bq-tb").textContent = money(S.total);
    root.querySelectorAll("#bq-chips button,#bq-clear").forEach(function (b) { b.disabled = S.busy; });
    $(root, "#bq-deal").disabled = S.busy || !(S.total >= S.min && S.total <= S.max);
    $(root, "#bq-hist").innerHTML = S.hist.length ? "<span>History</span>" + S.hist.map(function (w) { return '<i class="' + w + '">' + (w === "player" ? "P" : w === "banker" ? "B" : "T") + "</i>"; }).join("") : "";
  }
  function say(root, cls, t) { var e = $(root, "#bq-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function deal(root) {
    if (S.busy) return;
    if (!(S.total >= S.min && S.total <= S.max)) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    var stake = S.total; S.busy = true; paint(root); say(root, "", ""); $(root, "#bq-proof").textContent = "";
    $(root, "#bq-pc").innerHTML = ""; $(root, "#bq-bc").innerHTML = ""; $(root, "#bq-pt").textContent = "—"; $(root, "#bq-bt").textContent = "—"; $(root, "#bq-ban").textContent = "Dealing…";
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, choice: S.sel, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome, order = [["p", 0], ["b", 0], ["p", 1], ["b", 1], ["p", 2], ["b", 2]], shown = { p: [], b: [] };
      for (var i = 0; i < order.length; i++) {
        var side = order[i][0], idx = order[i][1], hand = side === "p" ? o.player : o.banker;
        if (idx >= hand.length) continue;
        await sleep(i < 4 ? 450 : 700); shown[side].push(hand[idx]); hap("light");
        $(root, "#bq-" + side + "c").innerHTML = shown[side].map(card).join(""); $(root, "#bq-" + side + "t").textContent = tot(shown[side]);
      }
      await sleep(450);
      var w = o.winner, pv = tot(o.player), bv = tot(o.banker);
      $(root, "#bq-ban").textContent = w === "tie" ? "TIE • " + pv + " vs " + bv : (w === "player" ? "PLAYER WINS" : "BANKER WINS") + " • " + (w === "player" ? pv + " vs " + bv : bv + " vs " + pv);
      S.hist.unshift(w); S.hist = S.hist.slice(0, 12);
      var p = Number(act.payout || 0), net = Math.round((p - stake) * 100) / 100;
      if (o.push) { say(root, "bad", "↩️ Push — " + money(p) + " ብር ተመለሰ"); hap("light"); }
      else if (act.won) { say(root, "win", "🎉 +" + money(net) + " ብር (" + money(p) + ")"); hap("success"); }
      else { say(root, "lose", "😕 አልተሳካም -" + money(stake) + " ብር"); hap("error"); }
      if (act.server_seed) $(root, "#bq-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { $(root, "#bq-ban").textContent = "Pick a side and press Deal"; say(root, "bad", "❌ " + (e.message || e)); }
    S.busy = false; paint(root);
  }
})();
