/* BINGO (new look): gold ball + last balls, B-I-N-G-O card, Marked / Pattern / Max win, Card price + BINGO!.
   The server deals the card, draws the 40 balls and pays by number of completed lines (12 possible); the client only replays them.
   Replaces window.setupBingo. Presentation only - the pay table is the server's (BINGO_PAYTABLE). */
(function () {
  "use strict";
  var KEY = "bingo", TABLE = [[1, 0.8], [2, 2.5], [3, 8.5], [4, 30], [5, 105], [6, 300], [7, 1000]];
  var LINES = [[0,1,2,3,4],[5,6,7,8,9],[10,11,12,13,14],[15,16,17,18,19],[20,21,22,23,24],[0,5,10,15,20],[1,6,11,16,21],[2,7,12,17,22],[3,8,13,18,23],[4,9,14,19,24],[0,6,12,18,24],[4,8,12,16,20]];
  var LET = "BINGO", COL = ["#2563eb", "#7c3aed", "#0891b2", "#16a34a", "#e11d48"];
  var S = { min: 1, max: 10000, busy: false, skip: false, loaded: false, stake: 10 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var ci = function (n) { return Math.min(4, Math.floor((n - 1) / 15)); };
  window.setupBingo = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; } catch (_) {} S.loaded = true; }
    if (root.dataset.bg) return; root.dataset.bg = "1";
    var cells = ""; for (var i = 0; i < 25; i++) cells += '<div class="bg-c" data-i="' + i + '">' + (i === 12 ? "FREE" : "") + "</div>";
    root.innerHTML = '<div class="kx-wrap"><div class="bg-top"><div class="bg-ball" id="bg-ball"><small>—</small><b>?</b></div><div class="bg-last"><small>Last balls</small><div id="bg-balls"></div></div><span class="bg-cnt" id="bg-cnt">Ball 0 / 40</span></div>' +
      '<div class="bg-card"><div class="bg-head">' + LET.split("").map(function (c, k) { return '<b style="background:' + COL[k] + '">' + c + "</b>"; }).join("") + '</div><div class="bg-grid" id="bg-grid">' + cells + "</div></div>" +
      '<div class="bg-stats"><div><small>Marked</small><b id="bg-marked">0 / 24</b></div><div><small>Pattern</small><b class="bl">Any line</b></div><div><small>Max win</small><b class="yl" id="bg-max">—</b></div></div>' +
      '<div class="bg-pay" id="bg-pay">' + TABLE.map(function (r) { return '<div data-l="' + r[0] + '"><small>' + r[0] + (r[0] === 7 ? "+" : "") + ' line</small><b>x' + r[1] + "</b></div>"; }).join("") + "</div>" +
      '<div class="kx-bet"><label for="bg-stake">Card price</label><div class="kx-row"><div class="kx-step"><button type="button" data-d="-1" aria-label="minus">−</button><input id="bg-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1" aria-label="plus">+</button></div><button type="button" id="bg-go" class="bg-go">BINGO!</button></div></div>' +
      '<div class="kx-msg" id="bg-msg" aria-live="polite"></div><div class="kx-proof" id="bg-proof"></div></div>';
    var inp = $(root, "#bg-stake");
    var mx = function () { $(root, "#bg-max").textContent = money((Number(inp.value) || 0) * 1000); }; mx();
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy) return; var v = Number(inp.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; inp.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); mx(); }); });
    inp.addEventListener("input", mx);
    $(root, "#bg-go").addEventListener("click", function () { if (S.busy) { S.skip = true; return; } play(root, inp); });
  };
  function say(root, cls, t) { var e = $(root, "#bg-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function play(root, inp) {
    var stake = Number(inp.value);
    if (!(stake >= S.min && stake <= S.max)) return say(root, "bad", "❌ Card price ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    S.busy = true; S.skip = false; var go = $(root, "#bg-go"); go.textContent = "Skip ⏩"; say(root, "", ""); $(root, "#bg-proof").textContent = "";
    var cells = root.querySelectorAll(".bg-c"), balls = $(root, "#bg-balls"); balls.innerHTML = "";
    cells.forEach(function (c, i) { c.className = "bg-c"; c.textContent = i === 12 ? "FREE" : ""; }); cells[12].classList.add("mark");
    root.querySelectorAll("#bg-pay > div").forEach(function (d) { d.classList.remove("on"); });
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, client_seed: makeClientSeed() } });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome, pos = {}; o.card.forEach(function (n, i) { if (i !== 12) { cells[i].textContent = n; pos[n] = i; } });
      var marked = 0;
      for (var k = 0; k < o.draws.length; k++) {
        var n = o.draws[k], c = ci(n), hit = pos[n] !== undefined;
        var big = $(root, "#bg-ball"); big.style.background = "radial-gradient(circle at 35% 30%,#fde68a," + COL[c] + ")"; big.innerHTML = "<small>" + LET[c] + "</small><b>" + n + "</b>";
        $(root, "#bg-cnt").textContent = "Ball " + (k + 1) + " / " + o.draws.length;
        var chip = document.createElement("span"); chip.style.background = COL[c]; chip.textContent = LET[c] + " " + n; balls.insertBefore(chip, balls.firstChild); while (balls.children.length > 6) balls.removeChild(balls.lastChild);
        if (hit) { cells[pos[n]].classList.add("mark"); marked++; $(root, "#bg-marked").textContent = marked + " / 24"; hap("light"); }
        if (!S.skip) await sleep(110);
      }
      o.line_ids.forEach(function (li) { LINES[li].forEach(function (x) { cells[x].classList.add("line"); }); });
      $(root, "#bg-marked").textContent = (o.marked || []).filter(Boolean).length - 1 + " / 24";
      var row = root.querySelector('#bg-pay [data-l="' + Math.min(o.lines, 7) + '"]'); if (row && o.lines > 0) row.classList.add("on");
      var p = Number(act.payout || 0);
      if (p > stake) { say(root, "win", "🎉 " + o.lines + " line · +" + money(p - stake) + " ብር"); hap("success"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else if (p > 0) say(root, "bad", "↩️ " + o.lines + " line · " + money(p) + " ብር ተመልሷል");
      else say(root, "lose", "😕 " + (o.lines ? o.lines + " line" : "No line") + " · -" + money(stake) + " ብር");
      if (act.server_seed) $(root, "#bg-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { say(root, "bad", "❌ " + (e.message || e)); }
    S.busy = false; go.textContent = "BINGO!";
  }
})();
