/* CHICKEN ROAD 2 (night road): cross 7 traffic lanes one by one, cash out after any safe crossing.
   Own server game key "chicken2" (own enable switch, limits, house edge, history). Every crossing is a server-side roll and the
   multiplier after n safe crossings = RTP / p^n, so every number shown is exactly what is paid. Presentation only.
   Loaded after app.js. */
(function () {
  "use strict";
  var KEY = "chicken2", MAX = 7, P = { calm: 0.80, rush: 0.59 };   // MUST match CHICKEN2_* in realtime_engine_v3.py
  var LV = [["calm", "Calm"], ["rush", "Rush"]], CHIPS = [10, 50, 100, 500];
  var S = { level: "calm", rtp: 0.95, min: 1, max: 10000, busy: false, round: null, over: null };
  var $ = function (r, s) { return r.querySelector(s); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var fmtX = function (m) { return "x" + (m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(2) : m.toFixed(2).replace(/0$/, "")); };
  var mult = function (lv, n) { return S.rtp / Math.pow(P[lv], n); };
  function lvMult(lv) { var a = []; for (var i = 1; i <= MAX; i++) a.push(mult(lv, i)); return a; }

  var CAR_COL = ["#ef4444", "#3b82f6", "#f59e0b", "#a855f7", "#22c55e", "#06b6d4", "#ec4899", "#eab308"];
  function car(n, boom) {
    var c = CAR_COL[(n * 3 + 1) % CAR_COL.length], flip = n % 2 === 0;
    return '<svg class="c2-car' + (boom ? " boom" : "") + '" viewBox="0 0 80 34" width="76" height="32" aria-hidden="true" style="' + (flip ? "" : "transform:scaleX(-1)") + '">' +
      '<rect x="4" y="12" width="66" height="16" rx="6" fill="' + c + '"/><path d="M18 12l7-10h22l9 10z" fill="#fff" opacity=".55"/><path d="M18 12l7-10h22l9 10z" fill="' + c + '" opacity=".55"/>' +
      '<circle cx="22" cy="29" r="5" fill="#0b1226"/><circle cx="54" cy="29" r="5" fill="#0b1226"/><path d="M70 16l8-3v8l-8-2z" fill="#fde68a"/></svg>';
  }
  var HEN = '<svg class="c2-hen" viewBox="0 0 48 52" width="36" height="40" aria-hidden="true"><path d="M20 8c0-4 3-6 5-4 2-3 6-1 5 3" fill="#ef4444"/><ellipse cx="24" cy="28" rx="15" ry="13" fill="#fff"/><circle cx="24" cy="14" r="8" fill="#fff"/><path d="M30 14l6 2-6 3z" fill="#f59e0b"/><circle cx="26" cy="12" r="1.5" fill="#111"/><path d="M12 28c-4 0-5 5-2 7 4 2 9-3 7-7z" fill="#f3f4f6"/><path d="M20 40v8M28 40v8M16 48h8M24 48h8" stroke="#f59e0b" stroke-width="2.4" stroke-linecap="round"/></svg>';

  var CSS = ".c2-wrap{display:flex;flex-direction:column;gap:10px}.c2-board{border-radius:18px;overflow:hidden;border:1px solid #23407f;background:#0b1226}" +
    ".c2-head{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;font-size:11px;font-weight:800;color:#c4b5fd;letter-spacing:.04em;background:#0f1a3d}.c2-head b:first-child{color:#e8eefc}.c2-head b:last-child{color:#ffd84a}" +
    ".c2-lane{position:relative;display:flex;align-items:center;justify-content:space-between;height:56px;padding:0 12px;border-bottom:2px dashed #b8892f55;background:linear-gradient(180deg,#141c3f,#0e1530)}.c2-lane:last-child{border-bottom:0}" +
    ".c2-lane.cur{background:linear-gradient(180deg,#232b66,#171f4d)}.c2-tag{min-width:44px;padding:3px 9px;border-radius:999px;background:#23304f;color:#c3d0ee;font-size:11px;font-weight:800;text-align:center}.c2-lane.cur .c2-tag{background:#1e6bff;color:#fff}.c2-lane.done .c2-tag{background:#166534;color:#bbf7d0}" +
    ".c2-mid{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:flex;align-items:center}.c2-car{filter:drop-shadow(0 3px 4px rgba(0,0,0,.5))}.c2-car.boom{filter:drop-shadow(0 0 10px #ef4444)}" +
    ".c2-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.c2-tiles .kx-tile b{font-size:18px}.c2-card{padding:12px;border-radius:16px;background:#0f1a3d;border:1px solid #1d3470;display:flex;flex-direction:column;gap:10px}" +
    ".c2-chips{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.c2-chips button{height:34px;border:0;border-radius:10px;background:#12204d;color:#c3d0ee;font-weight:700}.c2-chips button.on{background:#1e6bff;color:#fff}" +
    ".c2-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:end}.c2-row .kx-step{min-width:0}.c2-seg{display:flex;gap:4px;padding:4px;border-radius:12px;background:#0a1330}.c2-seg button{height:34px;padding:0 10px;border:0;border-radius:9px;background:transparent;color:#9fb0da;font-weight:800}.c2-seg button.on{background:#1e6bff;color:#fff}" +
    ".c2-seg label,.c2-row label{display:block}.c2-acts{display:grid;grid-template-columns:1fr 1fr;gap:10px}.c2-acts button{min-height:50px;border:0;border-radius:14px;font-weight:800;font-size:16px}.c2-cross{background:linear-gradient(180deg,#34d46a,#1fb356);color:#04150b}.c2-cash{background:linear-gradient(180deg,#fbbf24,#d99a0b);color:#1c1200}.c2-acts button:disabled{opacity:.5}" +
    ".c2-night{align-self:flex-end;padding:4px 10px;border-radius:999px;background:#1b1f4a;color:#ffd84a;font-size:11px;font-weight:800;margin:0 0 6px}";
  function css() { if (document.getElementById("c2-css")) return; var s = document.createElement("style"); s.id = "c2-css"; s.textContent = CSS; document.head.appendChild(s); }

  window.setupChicken2 = async function () {
    var root = document.getElementById(KEY + "-controls"); if (!root) return;
    ["-scene", "-play", "-result"].forEach(function (s) { var e = document.getElementById(KEY + s); if (e) e.style.display = "none"; });
    var pg = document.getElementById("page-" + KEY); if (pg) pg.classList.add("kx-page");
    css();
    if (!root.dataset.c2) {
      root.dataset.c2 = "1";
      var seg = LV.map(function (l) { return '<button type="button" data-l="' + l[0] + '">' + l[1] + "</button>"; }).join("");
      var chips = CHIPS.map(function (c) { return '<button type="button" data-v="' + c + '">' + c + "</button>"; }).join("");
      root.innerHTML = '<div class="c2-wrap"><span class="c2-night">Night mode</span>' +
        '<div class="c2-board"><div class="c2-head"><b>START</b><b id="c2-cross">Crossing 0 of ' + MAX + '</b><b id="c2-fin">—</b></div><div id="c2-lanes"></div></div>' +
        '<div class="c2-tiles"><div class="kx-tile"><small>Multiplier</small><b id="c2-mult" class="b">x1.00</b></div><div class="kx-tile"><small>Next</small><b id="c2-next">—</b></div><div class="kx-tile"><small>Cash out</small><b id="c2-win" class="g">—</b></div></div>' +
        '<div class="c2-card"><div class="c2-chips" id="c2-chips">' + chips + '</div>' +
        '<div class="c2-row"><div class="av-bet-col"><label for="chicken2-stake">Bet Amount</label><div class="kx-step"><button type="button" data-d="-1">−</button><input id="chicken2-stake" class="game-stake" type="number" inputmode="decimal" min="0.01" step="0.01" value="50"><button type="button" data-d="1">+</button></div></div>' +
        '<div><label>Traffic</label><div class="c2-seg" id="c2-seg">' + seg + "</div></div></div>" +
        '<div class="c2-acts"><button type="button" id="c2-go" class="c2-cross">Cross</button><button type="button" id="c2-cash" class="c2-cash">Cash Out</button></div>' +
        '<div class="kx-msg" id="c2-msg" aria-live="polite"></div><div class="kx-proof" id="c2-proof"></div></div>' +
        '<small class="kx-note">በእያንዳንዱ መሻገሪያ ሰርቨሩ ይወስናል። ደህና ሲሻገሩ ማባዣው ይጨምራል፤ ከማንኛውም ደህና መሻገሪያ በኋላ Cash Out ይችላሉ። ማባዣ = RTP ÷ (የደህንነት ዕድል)<sup>መሻገሪያ</sup>፤ የሚታየው ሁሉ እውነተኛ ክፍያ ነው።</small></div>';
      root.querySelectorAll("[data-d]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (S.busy || S.round) return; var i = $(root, "#chicken2-stake"), v = Number(i.value) || 0, st = v < 20 ? 1 : v < 100 ? 5 : v < 500 ? 10 : 50;
          i.value = Math.max(S.min, Math.min(S.max, v + Number(b.dataset.d) * st)); hap("light"); paint(root);
        });
      });
      root.querySelectorAll("#c2-chips button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || S.round) return; $(root, "#chicken2-stake").value = b.dataset.v; hap("light"); paint(root); }); });
      $(root, "#chicken2-stake").addEventListener("input", function () { paint(root); });
      root.querySelectorAll("#c2-seg button").forEach(function (b) { b.addEventListener("click", function () { if (S.busy || S.round) return; S.level = b.dataset.l; S.over = null; hap("light"); paint(root); }); });
      $(root, "#c2-go").addEventListener("click", function () { go(root); });
      $(root, "#c2-cash").addEventListener("click", function () { cash(root); });
    }
    try { var s = await apiFetch("/games/" + KEY + "/settings"); S.rtp = Number(s.rtp) || (1 - Number(s.house_edge || 0.05)); S.min = Number(s.min_stake) || 1; S.max = Number(s.max_stake) || 10000; } catch (_) {}
    if (!S.round) { try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); } catch (_) {} }
    paint(root);
  };
  function adopt(d) {
    var st = d.state || {}, inp = st.input || {}; S.level = inp.difficulty || S.level; S.over = null;
    S.round = { id: d.round_id, stake: Number(d.stake), level: S.level, progress: Number(st.progress || 0), mult: st.multipliers || lvMult(S.level) };
  }

  function paint(root) {
    var r = S.round, o = S.over, lv = r ? r.level : (o ? o.level : S.level), ms = r ? r.mult : (o ? o.mult : lvMult(lv)), prog = r ? r.progress : (o ? o.progress : 0);
    var stake = r ? r.stake : (o ? o.stake : (Number($(root, "#chicken2-stake").value) || 0)), hit = o && o.hit ? o.hit : 0;
    root.querySelectorAll("#c2-seg button").forEach(function (b) { b.classList.toggle("on", b.dataset.l === lv); b.disabled = !!r || S.busy; });
    root.querySelectorAll("#c2-chips button").forEach(function (b) { b.classList.toggle("on", Number(b.dataset.v) === stake); b.disabled = !!r || S.busy; });
    root.querySelectorAll(".kx-step button").forEach(function (b) { b.disabled = !!r || S.busy; }); $(root, "#chicken2-stake").disabled = !!r || S.busy;
    $(root, "#c2-cross").textContent = "Crossing " + Math.min(MAX, hit ? hit : prog + (r ? 1 : 0)) + " of " + MAX;
    $(root, "#c2-fin").textContent = fmtX(ms[MAX - 1]);
    var m = prog ? ms[prog - 1] : 1; $(root, "#c2-mult").textContent = fmtX(m);
    $(root, "#c2-next").textContent = (r && prog < MAX) ? fmtX(ms[prog]) : "—";
    var win = r ? (prog ? stake * m : 0) : (o && o.won ? o.payout : 0); $(root, "#c2-win").textContent = win > 0 ? money(win) : "—";
    // 5 visible lanes; row 0 = START (kerb)
    var first = Math.max(0, Math.min(MAX - 4, prog - 2)), html = "";
    for (var n = first; n < first + 5; n++) {
      var cls = "c2-lane", tag = n === 0 ? "START" : fmtX(ms[n - 1]), mid = "", side = "";
      if (hit && n === hit) { cls += " cur"; mid = car(n, true); }
      else if (n === prog && !hit) { cls += " cur"; mid = HEN; }
      else if (n < prog) cls += " done";
      if (n > 0 && !(n === prog && !hit) && !(hit && n === hit)) side = car(n, false);
      html += '<div class="' + cls + '"><span class="c2-tag">' + tag + '</span><span class="c2-mid">' + mid + "</span>" + side + "</div>";
    }
    $(root, "#c2-lanes").innerHTML = html;
    var live = !!r; $(root, "#c2-go").disabled = S.busy || (live && prog >= MAX); $(root, "#c2-cash").disabled = S.busy || !r || r.progress < 1;
    $(root, "#c2-go").textContent = "Cross";
  }
  function say(root, cls, t) { var e = $(root, "#c2-msg"); e.className = "kx-msg " + cls; e.textContent = t; }

  async function start(root) {
    var stake = Number($(root, "#chicken2-stake").value);
    if (!(stake > 0)) { say(root, "bad", "❌ የBet መጠን ትክክል ያስገቡ"); return false; }
    if (stake < S.min || stake > S.max) { say(root, "bad", "❌ Bet ከ " + S.min + " እስከ " + S.max + " ብር መሆን አለበት"); return false; }
    S.over = null; say(root, "", ""); $(root, "#c2-proof").textContent = "";
    try {
      var r = await apiFetch("/games/" + KEY + "/round/start", { method: "POST", json: { stake: stake, difficulty: S.level, client_seed: makeClientSeed() } });
      var st = r.state || {}; S.round = { id: r.round_id, stake: stake, level: S.level, progress: 0, mult: st.multipliers || lvMult(S.level) };
      $(root, "#c2-proof").textContent = "ROUND " + (r.round_code || "") + " · COMMIT " + String(r.seed_commit || "").slice(0, 16) + "…";
      try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
      return true;
    } catch (e) { say(root, "bad", "❌ " + e.message); return false; }
  }
  function end(root, a, hit) {
    var r = S.round, o = a.outcome || {}, won = a.status === "WON", pay = Number(a.payout || 0);
    S.over = { level: r.level, mult: r.mult, progress: Number(o.steps_cleared != null ? o.steps_cleared : r.progress), hit: hit || 0, won: won, payout: pay, stake: r.stake };
    S.round = null;
    if (won) { say(root, "win", "🎉 +" + money(pay - r.stake) + " ብር (" + fmtX(Number(o.multiplier || 0)) + ")"); hap("success"); }
    else { say(root, "lose", "💥 መኪና ገጭቷል -" + money(r.stake) + " ብር"); hap("error"); }
    if (o.server_seed) $(root, "#c2-proof").textContent = "ROUND " + (a.round_code || "") + " · SERVER SEED " + String(o.server_seed).slice(0, 16) + "…";
    try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
  }
  async function resync() {
    try { var d = await apiFetch("/games/" + KEY + "/active"); if (d && d.round_id && d.status === "ACTIVE") adopt(d); else S.round = null; } catch (_) {}
  }
  async function stepOnce(root) {
    var r = S.round; if (!r) return;
    try {
      var a = await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "step" } });
      if (a.status === "ACTIVE") { r.progress = a.progress; hap("light"); }
      else if (a.status === "LOST") end(root, a, a.outcome && a.outcome.hit_step);
      else if (a.status === "WON") { r.progress = a.progress || MAX; end(root, a, 0); }
    } catch (e) { say(root, "bad", "❌ " + e.message); await resync(); }
  }
  // "Cross": opens the round if none is running (server start), then asks the server for one crossing.
  async function go(root) {
    if (S.busy) return; S.busy = true; paint(root);
    if (!S.round) { var ok = await start(root); if (!ok) { S.busy = false; paint(root); return; } paint(root); }
    await stepOnce(root);
    S.busy = false; paint(root);
  }
  async function cash(root) {
    var r = S.round; if (!r || S.busy || r.progress < 1) return; S.busy = true; paint(root); hap("medium");
    try { end(root, await apiFetch("/games/" + KEY + "/round/" + r.id + "/action", { method: "POST", json: { action: "cashout" } }), 0); }
    catch (e) { say(root, "bad", "❌ " + e.message); await resync(); }
    S.busy = false; paint(root);
  }
})();
