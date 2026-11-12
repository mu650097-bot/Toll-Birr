/* ROULETTE (new look): spinning wheel, recent numbers, betting table, chips. Same server engine as before: American wheel (0 and 00),
   the server draws the pocket and pays; one bet per round (the engine takes a single bet). The wheel animation only replays the server's result.
   There is no live countdown: a round starts when YOU press Spin. Loaded after new_games.js; replaces window.setupRoulette. Presentation only. */
(function () {
  "use strict";
  var KEY = "roulette", CHIPS = [10, 25, 50, 100];
  var RED = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36];
  var WHEEL = [0, 28, 9, 26, 30, 11, 7, 20, 32, 17, 5, 22, 34, 15, 3, 24, 36, 13, 1, 37, 27, 10, 25, 29, 12, 8, 19, 31, 18, 6, 21, 33, 16, 4, 23, 35, 14, 2];   // American wheel order, 37 = 00
  var S = { sel: null, total: 50, busy: false, min: 1, max: 10000, loaded: false, hist: [], rot: 0 };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var col = function (n) { return (n === 0 || n === 37) ? "green" : (RED.indexOf(n) >= 0 ? "red" : "black"); };
  var lab = function (n) { return n === 37 ? "00" : String(n); };
  var FILL = { green: "#16a34a", red: "#dc2626", black: "#111827" };

  function wheelSvg() {
    var N = WHEEL.length, R = 100, r = 62, h = "";
    for (var i = 0; i < N; i++) {
      var a0 = (i - 0.5) * 2 * Math.PI / N - Math.PI / 2, a1 = (i + 0.5) * 2 * Math.PI / N - Math.PI / 2, am = (a0 + a1) / 2;
      var p = function (rad, a) { return (110 + rad * Math.cos(a)).toFixed(1) + " " + (110 + rad * Math.sin(a)).toFixed(1); };
      h += '<path d="M' + p(r, a0) + " L" + p(R, a0) + " A" + R + " " + R + " 0 0 1 " + p(R, a1) + " L" + p(r, a1) + " A" + r + " " + r + ' 0 0 0 ' + p(r, a0) + 'z" fill="' + FILL[col(WHEEL[i])] + '" stroke="#d4a017" stroke-width=".8"/>';
      var tx = 110 + 82 * Math.cos(am), ty = 110 + 82 * Math.sin(am);
      h += '<text x="' + tx.toFixed(1) + '" y="' + ty.toFixed(1) + '" fill="#fff" font-size="8" font-weight="800" text-anchor="middle" dominant-baseline="middle" transform="rotate(' + (am * 180 / Math.PI + 90).toFixed(1) + " " + tx.toFixed(1) + " " + ty.toFixed(1) + ')">' + lab(WHEEL[i]) + "</text>";
    }
    return '<svg viewBox="0 0 220 220" width="150" height="150" aria-hidden="true"><g id="rt-rot" style="transform-origin:110px 110px">' + h + '<circle cx="110" cy="110" r="60" fill="#3b2a12" stroke="#d4a017" stroke-width="2"/><circle cx="110" cy="110" r="14" fill="#d4a017"/></g><path d="M110 4l-7 -4h14z" fill="#fff" transform="translate(0 6)"/><circle cx="110" cy="12" r="5" fill="#fff"/></svg>';
  }
  var OUT = [["low", "1–18", 2], ["even", "EVEN", 2], ["red", "RED", 2], ["black", "BLACK", 2], ["odd", "ODD", 2], ["high", "19–36", 2]];

  window.setupRoulette = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) { pg.classList.remove("ng-page", "ng-page-roulette"); pg.classList.add("kx-page"); }
    if (!root.dataset.rt2) {
      root.dataset.rt2 = "1";
      var rows = [[3, 3], [2, 3], [1, 3]], grid = "";
      rows.forEach(function (rw) { for (var c = 0; c < 12; c++) { var n = 3 * c + rw[0]; grid += '<button type="button" class="rt-n ' + col(n) + '" data-t="n" data-v="' + n + '">' + n + "</button>"; } });
      root.innerHTML = '<div class="rt-wrap"><div class="rt-top"><div class="rt-wheel" id="rt-wheel">' + wheelSvg() + '<div class="rt-res" id="rt-res">?</div></div>' +
        '<div class="rt-recent"><small>Recent numbers</small><div class="rt-hist" id="rt-hist"></div><small class="rt-tip">Pick a bet, add chips, press Spin</small></div></div>' +
        '<div class="rt-table"><div class="rt-zeros"><button type="button" class="rt-n green" data-t="n" data-v="0">0</button><button type="button" class="rt-n green" data-t="n" data-v="37">00</button></div>' +
        '<div class="rt-grid">' + grid + "</div></div>" +
        '<div class="rt-doz">' + [1, 2, 3].map(function (d) { return '<button type="button" class="rt-o" data-t="dozen" data-v="' + d + '">' + ["1st 12", "2nd 12", "3rd 12"][d - 1] + "<small>3×</small></button>"; }).join("") +
        [1, 2, 3].map(function (d) { return '<button type="button" class="rt-o" data-t="column" data-v="' + d + '">Col ' + d + "<small>3×</small></button>"; }).join("") + "</div>" +
        '<div class="rt-out">' + OUT.map(function (o) { return '<button type="button" class="rt-o ' + (o[0] === "red" ? "r" : o[0] === "black" ? "k" : "") + '" data-t="' + o[0] + '">' + o[1] + "<small>2×</small></button>"; }).join("") + "</div>" +
        '<div class="rt-sel" id="rt-sel">No bet selected</div>' +
        '<div class="rt-chips" id="rt-chips">' + CHIPS.map(function (c) { return '<button type="button" data-c="' + c + '">' + c + "</button>"; }).join("") + "</div>" +
        '<div class="bq-row"><div class="bq-total"><small>Total bet</small><b id="rt-tb">50.00</b></div><button type="button" id="rt-clear" class="bq-clear">Clear</button><button type="button" id="rt-spin" class="av-go">Spin</button></div>' +
        '<div class="kx-msg" id="rt-msg" aria-live="polite"></div><div class="kx-proof" id="rt-proof"></div>' +
        '<small class="kx-note">American roulette (0 እና 00)። ሰርቨሩ ቁጥሩን ይመርጣል፣ ጎማው ውጤቱን ብቻ ያሳያል። በአንድ ዙር አንድ ውርርድ ብቻ። ዙሩ የሚጀምረው Spin ሲጫኑ ነው (የሰዓት ቆጣሪ የለም)። 0/00 ሲመጣ የውጭ ውርርዶች ይጠፋሉ። ሁሉም ውርርድ RTP 94.74%።</small></div>';
      root.addEventListener("click", function (e) {
        var b = e.target.closest("button"); if (!b || S.busy) return;
        if (b.dataset.t) {
          var t = b.dataset.t, v = b.dataset.v !== undefined ? Number(b.dataset.v) : undefined;
          S.sel = t === "n" ? { bet: "number", value: v, label: "Number " + lab(v), pay: 36, k: "n" + v } : t === "dozen" || t === "column" ? { bet: t, value: v, label: (t === "dozen" ? ["1st 12", "2nd 12", "3rd 12"] : ["Col 1", "Col 2", "Col 3"])[v - 1], pay: 3, k: t + v } : { bet: t, label: b.textContent.replace(/2×/, ""), pay: 2, k: t };
          hap("light"); paint(root);
        } else if (b.dataset.c) { S.total = Math.min(S.max, S.total + Number(b.dataset.c)); hap("light"); paint(root); }
        else if (b.id === "rt-clear") { S.total = 0; hap("light"); paint(root); }
        else if (b.id === "rt-spin") spin(root);
      });
    }
    if (!S.loaded) { try { var s = await apiFetch("/games/" + KEY + "/settings"); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; } catch (_) {} S.loaded = true; }
    paint(root);
  };
  function paint(root) {
    var k = S.sel ? S.sel.k : "";
    root.querySelectorAll("[data-t]").forEach(function (b) {
      var t = b.dataset.t, v = b.dataset.v, key = t === "n" ? "n" + v : (t === "dozen" || t === "column") ? t + v : t;
      b.classList.toggle("on", key === k); b.disabled = S.busy;
    });
    root.querySelectorAll("#rt-chips button,#rt-clear").forEach(function (b) { b.disabled = S.busy; });
    $(root, "#rt-tb").textContent = money(S.total);
    $(root, "#rt-sel").innerHTML = S.sel ? "Bet: <b>" + S.sel.label + "</b> · pays <b>" + S.sel.pay + "×</b>" : "No bet selected";
    $(root, "#rt-spin").disabled = S.busy || !S.sel || !(S.total >= S.min && S.total <= S.max);
    $(root, "#rt-hist").innerHTML = S.hist.map(function (n) { return '<i class="' + col(n) + '">' + lab(n) + "</i>"; }).join("");
  }
  function say(root, cls, t) { var e = $(root, "#rt-msg"); e.className = "kx-msg " + cls; e.textContent = t; }
  async function spin(root) {
    if (S.busy || !S.sel) return;
    if (!(S.total >= S.min && S.total <= S.max)) return say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት");
    var stake = S.total, body = { stake: stake, bet: S.sel.bet, client_seed: makeClientSeed() }; if (S.sel.value !== undefined) body.value = S.sel.value;
    S.busy = true; paint(root); say(root, "", ""); $(root, "#rt-proof").textContent = ""; $(root, "#rt-res").textContent = "…"; $(root, "#rt-res").className = "rt-res";
    try {
      var st = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: body });
      var act = await apiFetch("/games/" + KEY + "/round/" + st.round_id + "/action", { method: "POST", json: { action: "play" } });
      var o = act.outcome, idx = WHEEL.indexOf(o.spin), rot = $(root, "#rt-rot");
      S.rot += 360 * 4 + ((-(idx * 360 / WHEEL.length)) - (S.rot % 360) + 360) % 360;
      rot.style.transition = "transform 2.4s cubic-bezier(.15,.7,.2,1)"; rot.style.transform = "rotate(" + S.rot + "deg)";
      await sleep(2500);
      $(root, "#rt-res").textContent = o.label; $(root, "#rt-res").className = "rt-res " + o.color; hap("light");
      S.hist.unshift(o.spin); S.hist = S.hist.slice(0, 8);
      var p = Number(act.payout || 0), net = Math.round((p - stake) * 100) / 100, where = o.label + " " + (o.color === "red" ? "🔴" : o.color === "black" ? "⚫" : "🟢");
      if (p > stake) { say(root, "win", "🎉 " + where + " · +" + money(net) + " ብር"); hap("success"); }
      else if (p > 0) { say(root, "bad", "↩️ " + where + " · ክፍል ተመልሷል " + money(p) + " ብር"); }
      else { say(root, "lose", "😕 " + where + " · -" + money(stake) + " ብር"); hap("error"); }
      if (act.server_seed) $(root, "#rt-proof").textContent = "COMMIT " + String(st.seed_commit || "").slice(0, 12) + "… · SERVER SEED " + String(act.server_seed).slice(0, 12) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    } catch (e) { $(root, "#rt-res").textContent = "?"; say(root, "bad", "❌ " + (e.message || e)); }
    S.busy = false; paint(root);
  }
})();
