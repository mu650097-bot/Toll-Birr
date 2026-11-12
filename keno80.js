/* KENO 80 -- Classic (shared timed rounds) + Instant. Visual layer only: every number, hit and payout comes from the server. */
(function () {
  "use strict";
  var st = null, offset = 0, mode = "classic", picks = new Set(), stake = 10, active = false;
  var pollT = null, tickT = null, lastFetch = 0, instant = null, shownRound = null, resultShownFor = null, root = null;
  var tab = "live", history = null;

  function $(id) { return document.getElementById(id); }
  function now() { return Date.now() / 1000 + offset; }
  function money(n) { return Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function esc(s) { return typeof escapeHtml === "function" ? escapeHtml(String(s)) : String(s); }

  function build() {
    var sec = $("page-keno"); if (!sec) return false;
    if (sec.dataset.k80) { root = sec; return true; }
    sec.dataset.k80 = "1"; root = sec;
    var cells = ""; for (var i = 1; i <= 80; i++) cells += '<button type="button" class="k80-cell" data-n="' + i + '">' + i + "</button>";
    sec.innerHTML =
      '<button class="back-btn" data-back="lobby">← Lobby</button>' +
      '<div class="k80">' +
      '<div class="k80-head"><div class="k80-title">KENO <b>80</b></div>' +
      '<div class="k80-modes"><button type="button" data-mode="classic" class="on">⏱ Classic</button><button type="button" data-mode="instant">⚡ Instant</button></div>' +
      '<button type="button" class="k80-help" id="k80-help" aria-label="How to play">?</button></div>' +
      '<div class="k80-round"><div><small id="k80-rlabel">ROUND</small><b id="k80-rid">#—</b></div><div class="k80-timer" id="k80-timer">--</div></div>' +
      '<div class="k80-bar"><i id="k80-fill"></i></div>' +
      '<div class="k80-stage"><div class="k80-ball" id="k80-ball">·</div><div class="k80-drawn" id="k80-drawn"></div></div>' +
      '<div id="k80-banner" class="k80-banner" hidden></div>' +
      '<div class="k80-info"><span id="k80-pn">0 picks</span><b id="k80-mw">Win up to 0.00 ETB</b><button type="button" id="k80-clear" class="k80-mini">Clear</button></div>' +
      '<div class="k80-hint" id="k80-hint">1–10 ቁጥሮችን ይምረጡ · Select up to 10 numbers</div>' +
      '<div class="k80-grid" id="k80-grid">' + cells + "</div>" +
      '<div class="k80-pt" id="k80-pt"></div>' +
      '<div class="k80-bets"><div class="k80-stake"><button type="button" id="k80-minus" aria-label="less">−</button><input id="k80-stake" type="number" inputmode="decimal" min="1" step="1" value="10"><button type="button" id="k80-plus" aria-label="more">+</button></div>' +
      '<button type="button" class="k80-mini" id="k80-x2">x2</button><button type="button" class="k80-mini" id="k80-rand" title="Random picks">🎲</button></div>' +
      '<button type="button" class="k80-betbtn" id="k80-bet">BET</button>' +
      '<div class="k80-msg" id="k80-msg"></div>' +
      '<div class="k80-tabs"><button type="button" data-tab="live" class="on">Live <span id="k80-live-n">0</span></button><button type="button" data-tab="mine">My bets</button><button type="button" data-tab="results">Results</button></div>' +
      '<div class="k80-tabbody" id="k80-tabbody"></div>' +
      '<div class="k80-foot" id="k80-foot"></div>' +
      '<div class="k80-sheet" id="k80-sheet" hidden></div></div>';
    sec.querySelector(".back-btn").addEventListener("click", function () { goToPage("lobby"); });
    $("k80-grid").addEventListener("click", function (e) { var b = e.target.closest(".k80-cell"); if (b) togglePick(+b.dataset.n); });
    sec.querySelectorAll(".k80-modes button").forEach(function (b) { b.addEventListener("click", function () { setMode(b.dataset.mode); }); });
    sec.querySelectorAll(".k80-tabs button").forEach(function (b) { b.addEventListener("click", function () { tab = b.dataset.tab; sec.querySelectorAll(".k80-tabs button").forEach(function (x) { x.classList.toggle("on", x === b); }); if (tab === "mine") loadHistory(); renderTab(); }); });
    $("k80-clear").addEventListener("click", function () { picks.clear(); paintPicks(); });
    $("k80-rand").addEventListener("click", randomPicks);
    $("k80-minus").addEventListener("click", function () { setStake(stake - stepOf(stake)); });
    $("k80-plus").addEventListener("click", function () { setStake(stake + stepOf(stake)); });
    $("k80-x2").addEventListener("click", function () { setStake(stake * 2); });
    $("k80-stake").addEventListener("change", function () { setStake(parseFloat(this.value) || 1); });
    $("k80-bet").addEventListener("click", placeBet);
    $("k80-help").addEventListener("click", toggleSheet);
    return true;
  }

  function stepOf(v) { return v >= 100 ? 50 : v >= 20 ? 10 : v >= 10 ? 5 : 1; }
  function limits() { return (st && st.limits) || { min: 1, max: 500, max_picks: 10, max_bets_per_round: 5 }; }
  function setStake(v) { var l = limits(); stake = Math.max(l.min, Math.min(l.max, Math.round(v * 100) / 100)); $("k80-stake").value = stake; paintInfo(); }

  function setMode(m) {
    mode = m; instant = null; hideBanner();
    root.querySelectorAll(".k80-modes button").forEach(function (b) { b.classList.toggle("on", b.dataset.mode === m); });
    $("k80-rlabel").textContent = m === "classic" ? "ROUND" : "INSTANT";
    clearDrawn(); paintAll();
  }

  function togglePick(n) {
    if (!canEdit()) return;
    if (picks.has(n)) picks.delete(n);
    else { if (picks.size >= limits().max_picks) { msg("Max " + limits().max_picks + " numbers", true); return; } picks.add(n); }
    if (typeof haptic === "function") haptic("light");
    paintPicks();
  }
  function randomPicks() {
    if (!canEdit()) return;
    var k = picks.size || 5; picks.clear();
    while (picks.size < k) picks.add(1 + Math.floor(Math.random() * 80));
    paintPicks();
  }
  function canEdit() {
    if (mode === "instant") return !instant || instant.done;
    return !st || st.phase === "betting";
  }

  function paintPicks() {
    root.querySelectorAll(".k80-cell").forEach(function (c) { c.classList.toggle("sel", picks.has(+c.dataset.n)); });
    paintInfo();
  }

  function table() { return (st && st.paytable) || {}; }
  function paintInfo() {
    var k = picks.size, t = table()[String(k)] || {};
    var hits = Object.keys(t).map(Number).sort(function (a, b) { return a - b; });
    var top = hits.length ? t[String(hits[hits.length - 1])] : 0;
    $("k80-pn").textContent = k + (k === 1 ? " pick" : " picks");
    $("k80-mw").textContent = "Win up to " + money(top * stake) + " ETB";
    $("k80-pt").innerHTML = hits.map(function (h) { return '<span><i>' + h + '✓</i>×' + t[String(h)] + "</span>"; }).join("") || '<span class="k80-dim">Pick numbers to see payouts</span>';
    var btn = $("k80-bet");
    var l = limits();
    if (mode === "classic") {
      var mine = st && st.my_bets ? st.my_bets.length : 0;
      btn.textContent = (st && st.phase !== "betting") ? "DRAWING…" : (k ? "BET · " + k + " picks" : "BET");
      if (mine && st && st.phase === "betting") $("k80-hint").textContent = "✅ " + mine + "/" + l.max_bets_per_round + " bets placed this round";
      else $("k80-hint").textContent = "1–10 ቁጥሮችን ይምረጡ · Select up to 10 numbers";
    } else {
      btn.textContent = (instant && !instant.done) ? "DRAWING…" : (k ? "PLAY NOW · " + k + " picks" : "PLAY NOW");
      $("k80-hint").textContent = "⚡ Instant: your own private draw, paid at once";
    }
    $("k80-foot").textContent = st ? "RTP " + Math.round(st.rtp * 1000) / 10 + "% · Stake " + l.min + "–" + l.max + " ETB · 18+ · play responsibly" : "";
  }

  function paintAll() { paintPicks(); paintTimer(); renderTab(); }

  function msg(t, err) { var m = $("k80-msg"); if (!m) return; m.textContent = t || ""; m.className = "k80-msg" + (err ? " err" : ""); }
  function hideBanner() { var b = $("k80-banner"); if (b) b.hidden = true; }
  function showBanner(html, win) { var b = $("k80-banner"); b.innerHTML = html; b.className = "k80-banner " + (win ? "win" : "lose"); b.hidden = false; }

  function clearDrawn() {
    root.querySelectorAll(".k80-cell").forEach(function (c) { c.classList.remove("drawn", "hit"); });
    $("k80-drawn").innerHTML = ""; $("k80-ball").textContent = "·"; $("k80-ball").classList.remove("pop");
  }

  /* reveal the first `count` balls of `draw` */
  function paintDraw(draw, count) {
    var set = {}; for (var i = 0; i < count; i++) set[draw[i]] = true;
    root.querySelectorAll(".k80-cell").forEach(function (c) {
      var n = +c.dataset.n, d = !!set[n];
      c.classList.toggle("drawn", d); c.classList.toggle("hit", d && picks.has(n));
    });
    var strip = $("k80-drawn"), html = "";
    for (var j = 0; j < count; j++) html += '<i class="' + (picks.has(draw[j]) ? "hit" : "") + '">' + draw[j] + "</i>";
    strip.innerHTML = html;
    var ball = $("k80-ball");
    if (count > 0) { ball.textContent = draw[count - 1]; ball.classList.remove("pop"); void ball.offsetWidth; ball.classList.add("pop"); }
  }

  function fmtT(s) { s = Math.max(0, Math.ceil(s)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }

  function paintTimer() {
    if (!root) return;
    var timer = $("k80-timer"), fill = $("k80-fill");
    if (mode === "instant") { timer.textContent = "⚡"; fill.style.width = "100%"; return; }
    if (!st) { timer.textContent = "--"; return; }
    var t = now(), left = st.close_ts - t;
    if (left > 0) {
      timer.textContent = fmtT(left); timer.classList.toggle("urgent", left <= 10);
      fill.style.width = Math.max(0, Math.min(100, left / (st.close_ts - st.start_ts) * 100)) + "%";
    } else {
      var cnt = Math.min(20, Math.max(0, Math.floor((t - st.close_ts) / st.reveal_sec)));
      timer.textContent = cnt + " / 20"; timer.classList.remove("urgent");
      fill.style.width = (cnt / 20 * 100) + "%";
    }
  }

  function tick() {
    if (!active || !st) return;
    var t = now();
    paintTimer();
    if (mode === "classic") {
      if (t >= st.end_ts) { // next round started
        if (Date.now() - lastFetch > 700) fetchState();
        return;
      }
      if (t >= st.close_ts) {
        if (!st.draw) { if (Date.now() - lastFetch > 800) fetchState(); return; }
        var cnt = Math.min(20, Math.floor((t - st.close_ts) / st.reveal_sec));
        paintDraw(st.draw, cnt);
        if (cnt >= 20 && resultShownFor !== st.round_id) { resultShownFor = st.round_id; setTimeout(finishClassic, 600); }
      }
    }
  }

  function finishClassic() {
    fetchState(function () {
      var mine = st.my_bets || [], total = 0, any = mine.length > 0;
      mine.forEach(function (b) { total += b.payout || 0; });
      if (any) {
        if (total > 0) { showBanner("🎉 You won <b>" + money(total) + " ETB</b>", true); if (typeof haptic === "function") haptic("success"); }
        else showBanner("No win this round. Next round starts soon.", false);
      }
      if (typeof refreshBalance === "function") refreshBalance();
    });
  }

  function fetchState(cb) {
    lastFetch = Date.now();
    apiFetch("/keno80/state").then(function (s) {
      offset = s.server_time - Date.now() / 1000;
      var newRound = !st || st.round_id !== s.round_id;
      st = s;
      if (newRound && mode === "classic") { clearDrawn(); hideBanner(); resultShownFor = null; if (shownRound !== null) msg(""); shownRound = s.round_id; }
      $("k80-rid").textContent = "#" + s.round_id; $("k80-live-n").textContent = s.live.count;
      if (!$("k80-stake").dataset.init) { $("k80-stake").dataset.init = "1"; setStake(Math.max(s.limits.min, Math.min(10, s.limits.max))); }
      paintInfo(); renderTab();
      if (cb) cb();
    }).catch(function () { /* server waking up -- retry on next poll */ });
  }

  function placeBet() {
    var l = limits();
    if (!picks.size) { msg("Pick at least 1 number", true); return; }
    var arr = Array.from(picks).sort(function (a, b) { return a - b; });
    var btn = $("k80-bet"); btn.disabled = true;
    if (mode === "classic") {
      if (!st || st.phase !== "betting") { msg("Betting is closed – wait for the next round", true); btn.disabled = false; return; }
      apiFetch("/keno80/bet", { method: "POST", json: { picks: arr, stake: stake } }).then(function () {
        msg("✅ Bet placed – good luck!"); if (typeof haptic === "function") haptic("success");
        if (typeof refreshBalance === "function") refreshBalance(); fetchState();
      }).catch(function (e) { msg("❌ " + e.message, true); if (typeof haptic === "function") haptic("error"); })
        .then(function () { btn.disabled = false; });
    } else {
      if (instant && !instant.done) { btn.disabled = false; return; }
      hideBanner(); clearDrawn();
      apiFetch("/keno80/instant", { method: "POST", json: { picks: arr, stake: stake } }).then(function (r) {
        instant = { done: false }; var i = 0;
        var iv = setInterval(function () {
          i++; paintDraw(r.draw, i);
          if (i >= 20) {
            clearInterval(iv); instant.done = true;
            if (r.payout > 0) { showBanner("🎉 " + r.hits + " hits · ×" + r.multiplier + " · You won <b>" + money(r.payout) + " ETB</b>", true); if (typeof haptic === "function") haptic("success"); }
            else showBanner(r.hits + " hits – no win this time.", false);
            if (typeof refreshBalance === "function") refreshBalance(); paintInfo();
          }
        }, 140);
        paintInfo();
      }).catch(function (e) { msg("❌ " + e.message, true); if (typeof haptic === "function") haptic("error"); })
        .then(function () { btn.disabled = false; });
    }
  }

  function loadHistory() { apiFetch("/keno80/history").then(function (r) { history = r.bets; renderTab(); }).catch(function () {}); }

  function chips(arr, drawSet) { return arr.map(function (n) { return '<i class="' + (drawSet && drawSet[n] ? "hit" : "") + '">' + n + "</i>"; }).join(""); }

  function renderTab() {
    var box = $("k80-tabbody"); if (!box) return;
    if (tab === "live") {
      if (!st) { box.innerHTML = ""; return; }
      var lv = st.live;
      var h = '<div class="k80-livebar"><b>' + lv.count + "</b> bets · <b>" + money(lv.total) + "</b> ETB</div>";
      if (!lv.top.length) h += '<div class="k80-empty">No bets yet this round – be the first.</div>';
      var ds = null; if (st.draw) { ds = {}; st.draw.forEach(function (n) { ds[n] = true; }); }
      h += lv.top.map(function (b) {
        return '<div class="k80-row"><div class="k80-av">' + esc(b.name[0]) + "</div><div class=\"k80-rw\"><b>" + esc(b.name) + '</b><div class="k80-chips">' + chips(b.picks, ds) + '</div></div><div class="k80-rs"><b>' + money(b.stake) + "</b><small class=\"" + b.status + '">' + (b.status === "pending" ? "Waiting" : b.status === "won" ? "+" + money(b.payout) : "Lost") + "</small></div></div>";
      }).join("");
      box.innerHTML = h;
    } else if (tab === "mine") {
      if (!history) { box.innerHTML = '<div class="k80-empty">Loading…</div>'; return; }
      box.innerHTML = history.length ? history.map(function (b) {
        var ds = null; if (b.draw) { ds = {}; b.draw.forEach(function (n) { ds[n] = true; }); }
        return '<div class="k80-row"><div class="k80-rw"><b>' + (b.mode === "instant" ? "⚡ Instant" : "Round #" + b.round_id) + '</b><div class="k80-chips">' + chips(b.picks, ds) + '</div></div><div class="k80-rs"><b>' + money(b.stake) + "</b><small class=\"" + b.status + '">' + (b.status === "pending" ? "Waiting" : b.status === "won" ? "+" + money(b.payout) : "Lost") + "</small></div></div>";
      }).join("") : '<div class="k80-empty">No bets yet.</div>';
    } else {
      box.innerHTML = st && st.results.length ? st.results.map(function (r) {
        return '<div class="k80-row"><div class="k80-rw"><b>Round #' + r.round_id + '</b><div class="k80-chips">' + chips(r.draw.slice().sort(function (a, b) { return a - b; }), null) + "</div></div></div>";
      }).join("") : '<div class="k80-empty">No results yet.</div>';
    }
  }

  function toggleSheet() {
    var s = $("k80-sheet"); if (!s.hidden) { s.hidden = true; return; }
    var t = table(), rows = "";
    for (var k = 1; k <= 10; k++) {
      var tk = t[String(k)]; if (!tk) continue;
      rows += "<tr><td>" + k + "</td><td>" + Object.keys(tk).map(Number).sort(function (a, b) { return a - b; }).map(function (h) { return h + "→×" + tk[String(h)]; }).join(" · ") + "</td></tr>";
    }
    s.innerHTML = "<h3>How to play Keno 80 · እንዴት ይጫወታሉ</h3><ol>" +
      "<li>1–10 ቁጥሮችን ከ1–80 ይምረጡ። Pick 1 to 10 numbers from 1–80.</li>" +
      "<li>Stake ያስገቡና BET ይጫኑ። Enter your stake and press BET.</li>" +
      "<li>20 ቁጥሮች ይወጣሉ። 20 numbers are drawn.</li>" +
      "<li>የተገጣጠሙ ቁጥሮች ብዙ ሲሆኑ ሽልማቱ ይጨምራል። More matches = bigger multiplier.</li></ol>" +
      "<p><b>Classic</b>: everyone shares one round, bets close when the timer ends. <b>Instant</b>: your own private draw right away.</p>" +
      '<table class="k80-ptt"><tr><th>Picks</th><th>Hits → multiplier</th></tr>' + rows + "</table>" +
      '<button type="button" class="k80-betbtn" id="k80-sheet-close">OK</button>';
    s.hidden = false; $("k80-sheet-close").addEventListener("click", function () { s.hidden = true; });
  }

  window.Keno80 = {
    open: function () {
      if (!build()) return;
      active = true; paintAll();
      fetchState(); clearInterval(pollT); clearInterval(tickT);
      pollT = setInterval(function () { if (!document.hidden) fetchState(); }, 3000);
      tickT = setInterval(tick, 250);
    },
    close: function () { active = false; clearInterval(pollT); clearInterval(tickT); }
  };
})();
