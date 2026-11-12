/* SKY MASTERS LIVE: one shared flight for ALL players every 60 s (15 s betting). Same server engine as High Flyer live
   (live_engine_v1.py, game key "skymasters"). Plane = your auto-land target (Falcon x2, Viper x5, Phoenix x20); you can also
   tap "Land & Cash Out" any time before the crash. Stunts (Loop x1.5, Roll x2, Dive x3) are show-only milestones: they do NOT change the payout.
   Replaces window.setupAviator ONLY for the skymasters skin. */
(function () {
  "use strict";
  var GK = "skymasters", orig = window.setupAviator;
  var PLANES = [["Falcon", "steady", 2.0], ["Viper", "risky", 5.0], ["Phoenix", "jackpot", 20.0]], STUNTS = [["Loop", 1.5], ["Roll", 2], ["Dive", 3]];
  var S = { st: null, off: 0, at: 0, timer: null, raf: 0, root: null, busy: false, queue: false, stake: 50, plane: 0, trail: [], dots: [], seen: 0, shown: {}, rtp: 0.95 };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var $ = function (s) { return S.root && S.root.querySelector(s); };

  function css() {
    if (document.getElementById("sml-css")) return;
    var s = document.createElement("style"); s.id = "sml-css";
    s.textContent = ".sml{display:flex;flex-direction:column;gap:12px;color:#fff}.sml-stage{position:relative;height:300px;border-radius:24px;overflow:hidden;border:1.5px solid #14b8a6;background:linear-gradient(#06303a,#0a4a5a 60%,#0b6577)}" +
      ".sml-stage.crashed{background:linear-gradient(#2a0f14,#4a1a22)}.sml-mult{position:absolute;left:14px;top:6px;font-size:70px;font-weight:900;line-height:1;text-shadow:0 0 22px #2dd4bf88}" +
      ".sml-bonus{position:absolute;right:10px;top:10px;border:1px solid #facc15;border-radius:20px;padding:6px 14px;font-weight:800;color:#facc15;background:#0006;font-size:14px}" +
      ".sml-svg{position:absolute;inset:0;width:100%;height:100%}.sml-plane{position:absolute;font-size:40px;line-height:1;transform:translate(-50%,50%) rotate(-30deg)}" +
      ".sml-cd{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:900;background:#03181e88;text-align:center;font-size:18px}.sml-cd b{font-size:54px;color:#2dd4bf}" +
      ".sml-st{position:absolute;left:10px;right:10px;bottom:8px;display:flex;gap:8px}.sml-st span{flex:1;text-align:center;background:#0a3a47;border-radius:12px;padding:8px 0;font-weight:800;color:#5eead4;font-size:15px;opacity:.65}.sml-st span.on{opacity:1;background:#0f766e;color:#fff}" +
      ".sml-card{background:#07303b;border:1.5px solid #14b8a6;border-radius:20px;padding:12px}.sml-h{color:#9be7dc;font-size:14px;margin-bottom:8px}.sml-planes{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}" +
      ".sml-planes button{border:1.5px solid transparent;border-radius:14px;background:#0a3a47;color:#e6fffb;padding:10px 0;font-weight:800;font-size:16px}.sml-planes button small{display:block;color:#9be7dc;font-weight:600;font-size:13px}.sml-planes button.on{border-color:#2dd4bf;background:#0b4a52}.sml-planes button:disabled{opacity:.6}" +
      ".sml-row{display:flex;gap:12px;align-items:flex-end}.sml-in{flex:1.3;display:flex;align-items:center;background:#042229;border:1px solid #14b8a6;border-radius:16px;padding:4px}.sml-in button{width:46px;height:46px;border:0;border-radius:12px;background:#0f6a6e;color:#fff;font-size:24px}.sml-in input{flex:1;min-width:0;text-align:center;background:transparent;border:0;color:#fff;font-size:22px;font-weight:900}" +
      ".sml-cash{flex:1}.sml-cash small{color:#9be7dc;font-size:14px}.sml-cash b{display:block;color:#4ade80;font-size:30px}.sml-go{width:100%;height:58px;border:0;border-radius:18px;margin-top:10px;font-weight:900;font-size:20px;background:linear-gradient(#4ade80,#22c55e);color:#04200f}.sml-go.wait{background:#0a3a47;color:#9be7dc;font-size:16px}.sml-go:disabled{opacity:.55}" +
      ".sml-info{color:#9be7dc;font-size:12px;margin-top:6px}.sml-msg{min-height:20px;text-align:center;font-weight:800}.sml-msg.win{color:#facc15}.sml-msg.lose{color:#fca5a5}.sml-msg.bad{color:#fdba74}.sml-chips{position:absolute;left:16px;top:84px;display:flex;gap:6px}.sml-chips span{background:#0a3a47;border-radius:12px;padding:2px 9px;font-weight:800;font-size:13px;color:#5eead4}";
    document.head.appendChild(s);
  }

  window.setupAviator = async function () {
    var skin = typeof window.kdmSkinKey === "function" ? window.kdmSkinKey() : null;
    if (skin !== GK) { stop(); return orig && orig.apply(this, arguments); }
    var root = document.getElementById("aviator-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById("aviator" + s); if (e) e.style.display = "none"; });
    css(); S.root = root;
    if (root.dataset.sml !== "1") {
      delete root.dataset.hfl; delete root.dataset.klcGk; root.dataset.sml = "1"; root.dataset.built = "1";
      root.innerHTML = '<div class="sml"><div class="sml-stage" id="sml-stage"><svg class="sml-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline id="sml-trail" fill="none" stroke="#2dd4bf" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" points=""/></svg><svg class="sml-svg" id="sml-dots" viewBox="0 0 100 100" preserveAspectRatio="none"></svg>' +
        '<div class="sml-mult" id="sml-mult">1.00x</div><div class="sml-chips" id="sml-chips"></div><div class="sml-bonus" id="sml-bonus">Stunts 0/3</div><div class="sml-plane" id="sml-plane">✈️</div><div class="sml-cd" id="sml-cd" hidden></div>' +
        '<div class="sml-st" id="sml-stunts">' + STUNTS.map(function (t) { return '<span data-t="' + t[1] + '">' + t[0] + " x" + t[1] + "</span>"; }).join("") + '</div></div>' +
        '<div class="sml-card"><div class="sml-h">Choose your plane</div><div class="sml-planes" id="sml-planes">' + PLANES.map(function (p, i) { return '<button type="button" data-p="' + i + '">' + p[0] + "<small>" + p[1] + "</small></button>"; }).join("") + '</div><div class="sml-info" id="sml-chance"></div></div>' +
        '<div class="sml-card"><div class="sml-row"><div style="flex:1.3"><div class="sml-h">Bet Amount</div><div class="sml-in"><button type="button" data-d="-1">−</button><input id="sml-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="' + S.stake + '"><button type="button" data-d="1">+</button></div></div>' +
        '<div class="sml-cash"><small>Cash now</small><b id="sml-now">—</b></div></div><button type="button" class="sml-go" id="sml-go">Take off</button><div class="sml-info" id="sml-pl"></div></div>' +
        '<div class="sml-msg" id="sml-msg" aria-live="polite"></div></div>';
      root.querySelectorAll("[data-p]").forEach(function (b) { b.addEventListener("click", function () { S.plane = Number(b.dataset.p); hap("light"); render(); }); });
      root.querySelectorAll(".sml-in button").forEach(function (b) { b.addEventListener("click", function () { var i = $("#sml-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50; var lo = (S.st && S.st.min_stake) || 1, hi = (S.st && S.st.max_stake) || 10000; i.value = Math.max(lo, Math.min(hi, v + Number(b.dataset.d) * st)); hap("light"); }); });
      $("#sml-go").addEventListener("click", press);
    }
    start();
  };

  function say(c, t) { var e = $("#sml-msg"); if (e) { e.className = "sml-msg " + c; e.textContent = t; } }
  function curMult() {
    var st = S.st; if (!st) return 1; if (st.phase === "CRASHED") return st.crash || 1; if (st.phase !== "FLYING") return 1;
    var t = (Date.now() + S.off) / 1000 - st.flight_start; return Math.max(1, Math.floor(Math.exp(st.k * Math.max(0, t)) * 100) / 100);
  }
  async function place() {
    if (S.busy) return false; S.busy = true;
    try {
      var stake = Number($("#sml-stake").value);
      await apiFetch("/live/" + GK + "/crash-bet", { method: "POST", json: { slot: "A", stake: stake, auto: PLANES[S.plane][2] } });
      S.stake = stake; hap("success"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
      S.busy = false; poll(); return true;
    } catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); S.busy = false; return false; }
  }
  async function press() {
    var st = S.st; if (!st) return; var my = st.my.A, cur = my && my.round_no === st.draw_no;
    if (cur && my.status === "PENDING" && st.phase === "FLYING") {
      if (S.busy) return; S.busy = true;
      try { var r = await apiFetch("/live/" + GK + "/cashout", { method: "POST", json: { slot: "A" } }); hap("success"); say("win", "🛬 Landed x" + r.multiplier.toFixed(2) + " · +" + money(r.payout - my.stake) + " ETB"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {} }
      catch (e) { say("bad", "❌ " + (e.message || e)); hap("error"); }
      S.busy = false; poll(); return;
    }
    if (st.phase === "BETTING" && !cur) { await place(); return; }
    if (!cur) { S.queue = !S.queue; hap("light"); render(); }
  }

  function start() { stop(); poll(); S.timer = setInterval(poll, 450); S.raf = requestAnimationFrame(frame); }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0; } }
  function visible() { return S.root && S.root.dataset.sml === "1" && S.root.isConnected && S.root.offsetParent !== null && !document.hidden; }
  async function poll() {
    if (!visible()) return;
    try { var st = await apiFetch("/live/" + GK + "/crash-state"); S.off = st.server_time * 1000 - Date.now(); S.st = st; S.at = Date.now(); onState(); }
    catch (e) { var p = $("#sml-pl"); if (p) p.textContent = "RECONNECTING…"; }
  }
  function onState() {
    var st = S.st;
    if (st.draw_no !== S.seen) { S.seen = st.draw_no; S.trail = []; S.dots = []; $("#sml-dots").innerHTML = ""; }
    var my = st.my.A;
    if (st.phase === "BETTING" && S.queue && !(my && my.round_no === st.draw_no) && st.seconds_left > 2) { S.queue = false; place(); }
    if (my && my.status !== "PENDING" && !S.shown[my.round_no]) {
      S.shown[my.round_no] = 1;
      if (Number(my.payout) > 0) { say("win", "🎉 x" + Number(my.mult).toFixed(2) + " · +" + money(my.payout - my.stake) + " ETB"); try { if (typeof celebrateWin === "function") celebrateWin(); } catch (_) {} }
      else say("lose", "💥 Crashed · -" + money(my.stake) + " ETB");
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
    }
    render();
  }

  function frame() {
    S.raf = requestAnimationFrame(frame);
    if (!visible() || !S.st) return;
    var st = S.st, m = curMult(), t = st.phase === "FLYING" || st.phase === "CRASHED" ? Math.log(Math.max(1, m)) / st.k : 0;
    $("#sml-mult").textContent = "x" + m.toFixed(2);
    var span = Math.max(8, t), px = 4 + 90 * (t / span), py = 12 + 70 * (Math.log(Math.max(1, m)) / Math.log(Math.max(4, m))) + 5 * Math.sin(t * 1.3);
    if (st.phase === "FLYING") {
      S.trail.push(px.toFixed(1) + "," + (100 - py).toFixed(1)); if (S.trail.length > 600) S.trail.shift();
      $("#sml-trail").setAttribute("points", S.trail.join(" "));
      STUNTS.forEach(function (s) { if (m >= s[1] && S.dots.indexOf(s[1]) < 0) { S.dots.push(s[1]); $("#sml-dots").insertAdjacentHTML("beforeend", '<circle cx="' + px.toFixed(1) + '" cy="' + (100 - py).toFixed(1) + '" r="1.6" fill="#facc15"/>'); } });
    } else if (st.phase === "BETTING") $("#sml-trail").setAttribute("points", "");
    var pl = $("#sml-plane"); pl.style.left = px + "%"; pl.style.bottom = py + "%"; pl.style.opacity = st.phase === "CRASHED" ? 0.45 : 1;
    var left = Math.max(0, st.seconds_left - (Date.now() - S.at) / 1000), cd = $("#sml-cd");
    cd.hidden = st.phase !== "BETTING"; if (!cd.hidden) cd.innerHTML = "TAKE-OFF IN<b>" + Math.ceil(left) + "</b>";
    var done = STUNTS.filter(function (s) { return m >= s[1] && st.phase !== "BETTING"; }).length;
    $("#sml-bonus").textContent = "Stunts " + done + "/3";
    $("#sml-stunts").querySelectorAll("span").forEach(function (e) { e.classList.toggle("on", st.phase !== "BETTING" && m >= Number(e.dataset.t)); });
    var my = st.my.A, cur = my && my.round_no === st.draw_no && my.status === "PENDING";
    if (cur && st.phase === "FLYING") { $("#sml-now").textContent = money(my.stake * m); $("#sml-go").textContent = "Land & Cash Out"; }
    else if (cur) $("#sml-now").textContent = money(my.stake);
    else $("#sml-now").textContent = money(Number($("#sml-stake").value) * (st.phase === "FLYING" ? m : 1));
  }

  function render() {
    var st = S.st; if (!st) return;
    $("#sml-stage").classList.toggle("crashed", st.phase === "CRASHED");
    var my = st.my.A, cur = my && my.round_no === st.draw_no, locked = cur;
    $("#sml-planes").querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.p) === S.plane); b.disabled = !!locked; });
    var tg = PLANES[S.plane][2], wc = Math.min(100, (1 - 0.05) / tg * 100);
    $("#sml-chance").textContent = PLANES[S.plane][0] + ": lands automatically at x" + tg.toFixed(2) + " · win chance ≈ " + wc.toFixed(wc < 10 ? 1 : 0) + "% · you can also cash out earlier";
    $("#sml-chips").innerHTML = (st.last || []).slice(0, 3).map(function (v) { return "<span>" + v.toFixed(2) + "x</span>"; }).join("");
    $("#sml-pl").textContent = "LIVE · Round #" + st.draw_no + " · " + st.players + " players · " + money(st.total_staked) + " ETB";
    var go = $("#sml-go"); go.classList.remove("wait");
    if (cur && my.status === "PENDING") { if (st.phase === "FLYING") { go.textContent = "Land & Cash Out"; go.disabled = false; } else { go.textContent = "Ready for take-off ✓"; go.disabled = true; } }
    else if (cur) { go.textContent = my.status === "WON" ? "Landed x" + Number(my.mult).toFixed(2) : "Crashed"; go.disabled = true; }
    else if (st.phase === "BETTING" && st.seconds_left > 1.5) { go.textContent = "Take off (Bet)"; go.disabled = false; }
    else { go.classList.add("wait"); go.textContent = S.queue ? "Queued for next flight ✓ (tap to cancel)" : "Bet next flight"; go.disabled = false; }
  }
  window.addEventListener("pagehide", stop);
})();
