/* NUMBER GAME (FAST, LIVE): one shared draw every 30 s for ALL players. The server (live_engine_v1.py -> /api/live/number/*) owns the clock,
   the secret number (1-4, committed before betting and revealed after), the payout and the history. This file only draws what the server says.
   Pays:  1 / 2 / 3 / 4  ->  x3.8   |   Odd / Even / Low / High  ->  x1.9   (5% house edge, shown to the player, same for every target).
   Everything fits ONE phone screen: header, round ring, 4 tiles, 4 side bets, bet amount + Confirm. Replaces the old pari-mutuel 15-tile page. */
(function () {
  "use strict";
  var COLS = { 1: "#2563eb", 2: "#16a34a", 3: "#eab308", 4: "#e11d48" };
  var SIDES = [["odd", "Odd"], ["even", "Even"], ["low", "Low"], ["high", "High"]];
  var S = { st: null, off: 0, at: 0, timer: null, raf: 0, sel: "1", stake: 50, busy: false, built: false, shown: 0, root: null };
  var $ = function (s) { return S.root && S.root.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var fx = function (m) { return "x" + String(+Number(m).toFixed(2)); };
  var refresh = function () { try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {} };

  function build() {
    var host = document.getElementById("number-grid"); if (!host) return false;
    var pg = document.getElementById("page-number"); if (pg) pg.classList.add("nm-page");
    S.root = host;
    if (host.dataset.nm === "2") return true;
    host.dataset.nm = "2"; host.className = "nm2";
    var tiles = [1, 2, 3, 4].map(function (n) {
      return '<button type="button" class="nm2-t" data-t="' + n + '" style="--c:' + COLS[n] + '"><span class="nm2-chip" hidden></span><b>' + n + '</b><small data-pay>pays x3.8</small></button>';
    }).join("");
    var sides = SIDES.map(function (s) { return '<button type="button" class="nm2-s" data-t="' + s[0] + '"><span class="nm2-chip sm" hidden></span><span data-lbl>' + s[1] + ' x1.9</span></button>'; }).join("");
    host.innerHTML =
      '<div class="nm2-head"><button type="button" class="nm2-back" aria-label="Back">‹</button><h3>Number Game</h3><span class="nm2-fast">FAST</span><span class="nm2-live"><i></i>LIVE</span></div>' +
      '<div class="nm2-round"><div class="nm2-ring" data-ring><b data-sec>—</b></div><div class="nm2-rt"><small data-lab>Next draw in seconds</small><h4>Round #<span data-no>—</span></h4><div class="nm2-last" data-last></div></div></div>' +
      '<div class="nm2-tiles">' + tiles + '</div><div class="nm2-sides">' + sides + '</div>' +
      '<div class="nm2-msg" data-msg aria-live="polite"></div>' +
      '<div class="nm2-bet"><small>Bet Amount</small><div class="nm2-row"><div class="nm2-step"><button type="button" data-d="-1" aria-label="Decrease">−</button><input data-stake type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake.toFixed(2) + '" aria-label="Bet amount"><button type="button" data-d="1" aria-label="Increase">+</button></div><button type="button" class="nm2-go" data-nmgo>Confirm</button></div>' +
      '<div class="nm2-info" data-info></div></div>';
    host.querySelectorAll("[data-t]").forEach(function (b) { b.addEventListener("click", function () { S.sel = b.dataset.t; hap("light"); paint(); }); });
    host.querySelectorAll(".nm2-step button").forEach(function (b) {
      b.addEventListener("click", function () {
        var i = $("[data-stake]"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
        var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000;
        S.stake = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); i.value = S.stake.toFixed(2); hap("light");
      });
    });
    $("[data-stake]").addEventListener("change", function () { S.stake = Number(this.value) || S.stake; });
    $("[data-nmgo]").addEventListener("click", bet);
    $(".nm2-back").addEventListener("click", function () { var b = document.querySelector("#page-number .back-btn"); if (b) b.click(); else if (typeof goToPage === "function") goToPage("lobby"); });
    return true;
  }

  function say(c, t) { var e = $("[data-msg]"); if (e) { e.className = "nm2-msg " + c; e.textContent = t; } }

  async function bet() {
    var st = S.st; if (S.busy || !st) return; S.busy = true; $("[data-nmgo]").disabled = true;
    try {
      var stake = Number($("[data-stake]").value); S.stake = stake;
      await apiFetch("/live/number/bet", { method: "POST", json: { target: S.sel, stake: stake } });
      hap("success"); say("", "✅ " + label(S.sel) + " · " + money(stake) + " ETB ተመዝግቧል"); refresh();
    } catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); }
    S.busy = false; await poll();
  }
  function label(t) { return /^[1-4]$/.test(t) ? "Number " + t : t.charAt(0).toUpperCase() + t.slice(1); }

  function visible() { return S.root && S.root.isConnected && S.root.offsetParent !== null && !document.hidden; }
  function start() { stop(); poll(); S.timer = setInterval(poll, 700); S.raf = requestAnimationFrame(tick); }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0; } }
  async function poll() {
    if (!visible()) return;
    try { var st = await apiFetch("/live/number/state"); S.off = st.server_time * 1000 - Date.now(); S.st = st; S.at = Date.now(); paint(); }
    catch (e) { var l = $("[data-lab]"); if (l) l.textContent = "RECONNECTING…"; }
  }
  function leftNow() { var st = S.st; return st ? Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000) : 0; }

  function tick() {   // smooth ring / countdown between polls
    S.raf = requestAnimationFrame(tick);
    var st = S.st; if (!st || !visible()) return;
    var left = leftNow(), ring = $("[data-ring]"), sec = $("[data-sec]");
    if (st.phase === "BETTING") {
      sec.textContent = Math.ceil(left); sec.className = ""; sec.style.color = "";
      ring.style.background = "conic-gradient(#34d36b " + (left / st.bet_sec * 360) + "deg,#14532d 0)";
    } else {
      sec.textContent = st.result || "—"; sec.className = "res"; sec.style.color = COLS[st.result] || "#fff";
      ring.style.background = "conic-gradient(" + (COLS[st.result] || "#34d36b") + " " + (left / (st.round_sec - st.bet_sec) * 360) + "deg,#14532d 0)";
    }
  }

  function paint() {
    var st = S.st; if (!st || !S.root) return;
    var open = st.phase === "BETTING" && leftNow() >= 1.2 && st.enabled;
    $("[data-no]").textContent = st.round;
    $("[data-lab]").textContent = !st.enabled ? "Number Game is paused" : st.phase === "BETTING" ? "Next draw in seconds" : "Result · next round in " + Math.ceil(leftNow()) + "s";
    $("[data-last]").innerHTML = (st.last || []).slice(0, 8).map(function (n) { return '<i style="background:' + COLS[n] + '">' + n + "</i>"; }).join("");
    S.root.querySelectorAll(".nm2-t").forEach(function (b) {
      var t = b.dataset.t, my = st.mine[t], chip = b.querySelector(".nm2-chip");
      b.classList.toggle("sel", S.sel === t); b.classList.toggle("win", st.phase === "REVEAL" && String(st.result) === t);
      b.classList.toggle("dim", st.phase === "REVEAL" && String(st.result) !== t);
      b.querySelector("[data-pay]").textContent = "pays " + fx(st.pays.num);
      chip.hidden = !my; if (my) chip.textContent = +Number(my.stake).toFixed(2);
    });
    var r = st.result;
    S.root.querySelectorAll(".nm2-s").forEach(function (b) {
      var t = b.dataset.t, my = st.mine[t], chip = b.querySelector(".nm2-chip");
      var w = r && (t === "odd" ? r % 2 === 1 : t === "even" ? r % 2 === 0 : t === "low" ? r <= 2 : r >= 3);
      b.classList.toggle("sel", S.sel === t); b.classList.toggle("win", !!(st.phase === "REVEAL" && w));
      b.querySelector("[data-lbl]").textContent = label(t) + " " + fx(st.pays.side);
      chip.hidden = !my; if (my) chip.textContent = +Number(my.stake).toFixed(2);
    });
    var go = $("[data-nmgo]"), already = !!st.mine[S.sel];
    go.disabled = S.busy || !open || already;
    go.textContent = !st.enabled ? "Paused" : already ? "Placed ✓" : open ? "Confirm" : "Next round…";
    $("[data-info]").textContent = st.players + " players · " + money(st.total_staked) + " ETB this round · pick: " + label(S.sel);
    // settled result of my bets in the round that just ended (shown once)
    if (st.phase === "REVEAL" && S.shown !== st.round) {
      var rows = Object.keys(st.mine).map(function (k) { return st.mine[k]; });
      if (rows.length && rows.every(function (x) { return x.status !== "PENDING"; })) {
        S.shown = st.round; var stake = 0, pay = 0; rows.forEach(function (x) { stake += Number(x.stake); pay += Number(x.payout || 0); });
        if (pay > stake) { say("win", "🎉 Number " + st.result + " · +" + money(pay - stake) + " ETB"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
        else if (pay > 0) say("", "Number " + st.result + " · " + money(pay) + " ETB back");
        else { say("lose", "😕 Number " + st.result + " · -" + money(stake) + " ETB"); hap("error"); }
        refresh();
      }
    }
  }

  window.renderNumberGrid = function () { build(); };
  window.refreshNumberState = async function () { if (!build()) return; if (!S.timer) start(); };   // the lobby re-calls this every 2 s: the live loop below already polls, so only (re)start it
  window.playNumberGame = function (t) { if (t) S.sel = String(t); return bet(); };
  window.addEventListener("pagehide", stop);
  // the lobby calls loadNumberGameInfo() each time the page opens; it ends in refreshNumberState() -> (re)start the live loop here.
  document.addEventListener("visibilitychange", function () { if (!document.hidden && S.root && S.root.isConnected && !S.timer) start(); });
})();
