/* SPORTS BETTING (new look): sport tabs, league line, LIVE pill, 1 / X / 2 odds, a bet slip pinned to the bottom.
   Same server rules as before (this file only redraws the page):
   - odds are set by the admin; the final payout is a pool share (the house keeps its disclosed rake), so "Potential win" is an ESTIMATE and says so;
   - betting closes at kickoff: a LIVE match shows its score and minute but its buttons stay locked (the design's in-play betting is NOT enabled,
     because a pool settled after the score is known would not be fair);
   - league / sport come from the server when the admin sets them (apply_sports_patch.py); without them the card shows "Football" and no sport tabs.
   Self-contained: injects its own CSS and replaces the global loadSports that app.js calls when the page opens. */
(function () {
  "use strict";
  var SPORTS = { football: "⚽ Football", basketball: "🏀 Basketball", tennis: "🎾 Tennis" };
  var S = { all: [], sport: "football", sel: null };
  var esc = function (v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var money = function (n) { return Number(n || 0).toFixed(2); };
  var hap = function (n) { if (typeof haptic === "function") try { haptic(n); } catch (_) {} };
  var CSS = ".sp2-tabs{display:flex;gap:8px;overflow-x:auto;padding:2px 0 10px}.sp2-tabs button{white-space:nowrap;padding:9px 16px;border-radius:999px;border:1px solid #23407f;background:#0d1b45;color:#cbd8ff;font-weight:800;font-size:13px}.sp2-tabs button.on{background:#1d6bff;border-color:#1d6bff;color:#fff}" +
    ".sp2-live{float:right;padding:4px 12px;border-radius:999px;background:#13361f;color:#86efac;font-weight:800;font-size:12px}" +
    ".sp2-card{list-style:none;border-radius:16px;border:1px solid #23407f;background:#0b1535;padding:12px 12px 14px;margin:0 0 12px}" +
    ".sp2-top{display:flex;justify-content:space-between;align-items:center;font-size:12px;opacity:.85;margin-bottom:8px}.sp2-top .lv{color:#fff;background:#dc2626;border-radius:6px;padding:2px 8px;font-weight:900;letter-spacing:.04em;opacity:1}" +
    ".sp2-teams{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;margin-bottom:12px}.sp2-teams b{font-size:16px}.sp2-teams b:last-child{text-align:right}.sp2-mid{opacity:.7;font-size:13px;text-align:center}.sp2-mid strong{font-size:18px;opacity:1}" +
    ".sp2-lock{text-align:center;font-size:12px;opacity:.8;margin-bottom:8px}" +
    ".sp2-odds{display:grid;gap:8px}.sp2-odds.t3{grid-template-columns:1fr 1fr 1fr}.sp2-odds.t2{grid-template-columns:1fr 1fr}" +
    ".sp2-opt{border-radius:12px;border:1px solid #23407f;background:#13224f;color:#fff;padding:9px 4px;display:flex;flex-direction:column;align-items:center;gap:2px}.sp2-opt i{font-style:normal;font-size:11px;opacity:.7}.sp2-opt b{font-size:18px}.sp2-opt.on{background:#1d6bff;border-color:#8bb8ff}.sp2-opt:disabled{opacity:.4}" +
    ".sp2-slip{position:sticky;bottom:calc(70px + env(safe-area-inset-bottom,0px));z-index:20;margin-top:12px;padding:14px;border-radius:16px;background:#0f1b33;border:1px solid #3b82f6;box-shadow:0 -6px 24px rgba(0,0,0,.5)}" +
    ".sp2-sh{display:flex;justify-content:space-between;align-items:center;font-size:13px;margin-bottom:8px}.sp2-sh b{font-size:13px}.sp2-pick{font-size:13px;opacity:.9;margin-bottom:8px}" +
    ".sp2-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end}.sp2-row input{width:100%;box-sizing:border-box;min-height:50px;border-radius:12px;border:1px solid #23407f;background:#070d24;color:#fff;font-weight:800;font-size:18px;text-align:center}" +
    ".sp2-pw small{display:block;font-size:11px;opacity:.7;text-align:right}.sp2-pw b{font-size:20px;color:#4ade80}.sp2-ch{display:flex;gap:8px;margin:10px 0}.sp2-ch button{flex:1;min-height:36px;border-radius:10px;border:1px solid #23407f;background:#0d1b45;color:#fff;font-weight:800}" +
    ".sp2-place{width:100%;min-height:52px;border-radius:14px;border:0;background:linear-gradient(180deg,#34d27b,#1ea75a);color:#04210f;font-weight:900;font-size:17px}.sp2-place:disabled{opacity:.6}.sp2-msg{display:block;margin-top:8px;font-size:12px;line-height:1.4}";
  function css() { if (document.getElementById("kdm-sports-css")) return; var s = document.createElement("style"); s.id = "kdm-sports-css"; s.textContent = CSS; document.head.appendChild(s); }

  window.loadSports = async function () {
    css();
    var list = document.getElementById("sports-list"); if (!list) return; var page = list.parentElement;
    ["sb-tabs", "sb-slip"].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); });   // the old layout's elements
    var tabs = document.getElementById("sp2-tabs"), slip = document.getElementById("sp2-slip");
    if (!tabs) { tabs = document.createElement("div"); tabs.id = "sp2-tabs"; tabs.className = "sp2-tabs"; page.insertBefore(tabs, list); tabs.addEventListener("click", function (e) { var b = e.target.closest("button[data-s]"); if (!b) return; S.sport = b.dataset.s; paint(); }); }
    if (!slip) { slip = document.createElement("div"); slip.id = "sp2-slip"; slip.className = "sp2-slip"; slip.hidden = true; page.appendChild(slip); }
    list.innerHTML = '<li class="skeleton-card"><div class="skeleton-line" style="width:60%"></div><div class="skeleton-line" style="width:100%;margin-bottom:0"></div></li>';
    var data; try { data = await apiFetch("/sports/matches"); } catch (e) { list.innerHTML = '<div class="empty-state">❌ ' + esc(e.message || e) + "</div>"; return; }
    S.all = (data && data.matches) || []; S.sel = null; slip.hidden = true;
    var present = Object.keys(SPORTS).filter(function (k) { return S.all.some(function (m) { return (m.sport || "football") === k; }); });
    if (present.indexOf(S.sport) < 0) S.sport = present[0] || "football";
    paint();
  };
  function sportOf(m) { return m.sport || "football"; }
  function paint() {
    var list = document.getElementById("sports-list"), tabs = document.getElementById("sp2-tabs"), slip = document.getElementById("sp2-slip");
    var present = Object.keys(SPORTS).filter(function (k) { return S.all.some(function (m) { return sportOf(m) === k; }); });
    tabs.innerHTML = present.length > 1 ? present.map(function (k) { return '<button type="button" data-s="' + k + '" class="' + (S.sport === k ? "on" : "") + '">' + SPORTS[k].replace(/^\S+\s/, "") + "</button>"; }).join("") : "";
    tabs.style.display = present.length > 1 ? "" : "none";
    var anyLive = S.all.some(function (m) { return m.live; }), h2 = list.parentElement.querySelector("h2");
    if (h2) { var old = h2.querySelector(".sp2-live"); if (old) old.remove(); if (anyLive) { var p = document.createElement("span"); p.className = "sp2-live"; p.textContent = "Live"; h2.appendChild(p); } }
    var shown = S.all.filter(function (m) { return sportOf(m) === S.sport; });
    S.sel = null; slip.hidden = true; list.innerHTML = "";
    if (!shown.length) { list.innerHTML = '<div class="empty-state"><span class="empty-emoji">⚽</span>' + (S.all.length ? "በዚህ ምድብ ግጥሚያ የለም" : "ንቁ ግጥሚያ የለም -- ቆይተው ይመልከቱ") + "</div>"; return; }
    shown.forEach(function (m) {
      var li = document.createElement("li"), two = !m.odds_draw, kick = String(m.closes_at || "").slice(5, 16).replace("-", "/");
      li.className = "sp2-card";
      var left = esc(m.league || SPORTS[sportOf(m)].replace(/^\S+\s/, "")), right = m.live ? '<span class="lv">LIVE' + (m.live_minute ? " · " + esc(m.live_minute) : "") + "</span>" : "🕒 " + esc(kick);
      var mid = m.live ? "<strong>" + (m.home_score == null ? 0 : m.home_score) + " - " + (m.away_score == null ? 0 : m.away_score) + "</strong>" : "vs";
      li.innerHTML = '<div class="sp2-top"><span>' + left + "</span><span>" + right + "</span></div>" +
        '<div class="sp2-teams"><b>' + logo(m.home_logo) + esc(m.home_team) + '</b><span class="sp2-mid">' + mid + "</span><b>" + logo(m.away_logo) + esc(m.away_team) + "</b></div>" +
        (m.live ? '<div class="sp2-lock">🔒 ጨዋታው ተጀምሯል -- Betting ዝግ ነው</div>' : "") +
        '<div class="sp2-odds ' + (two ? "t2" : "t3") + '"><button type="button" class="sp2-opt" data-sel="HOME"' + (m.live ? " disabled" : "") + "><i>1</i><b>" + esc(m.odds_home) + "</b></button>" +
        (two ? "" : '<button type="button" class="sp2-opt" data-sel="DRAW"' + (m.live ? " disabled" : "") + "><i>X</i><b>" + esc(m.odds_draw) + "</b></button>") +
        '<button type="button" class="sp2-opt" data-sel="AWAY"' + (m.live ? " disabled" : "") + "><i>2</i><b>" + esc(m.odds_away) + "</b></button></div>";
      li.querySelectorAll(".sp2-opt").forEach(function (b) { b.addEventListener("click", function () { if (b.classList.contains("on")) { closeSlip(); return; } openSlip(m, b.dataset.sel, b); hap("light"); }); });
      list.appendChild(li);
    });
  }
  function logo(u) {   // admin-uploaded club logo (optional)
    if (!u) return "";
    var base = String(API_BASE).replace(/\/api\/?$/, "");
    return '<img src="' + esc(base + u) + '" alt="" width="30" height="30" style="object-fit:contain;border-radius:6px;vertical-align:middle;margin-right:6px" onerror="this.style.display=\'none\'">';
  }
  function closeSlip() { S.sel = null; var s = document.getElementById("sp2-slip"); s.hidden = true; document.querySelectorAll("#sports-list .sp2-opt.on").forEach(function (x) { x.classList.remove("on"); }); }
  function openSlip(m, sel, btn) {
    var slip = document.getElementById("sp2-slip"); S.sel = { m: m, sel: sel };
    document.querySelectorAll("#sports-list .sp2-opt.on").forEach(function (x) { x.classList.remove("on"); }); btn.classList.add("on");
    var odds = Number(sel === "HOME" ? m.odds_home : sel === "DRAW" ? m.odds_draw : m.odds_away);
    var label = sel === "HOME" ? m.home_team + " ያሸንፋል" : sel === "AWAY" ? m.away_team + " ያሸንፋል" : "አቻ (Draw)";
    slip.hidden = false;
    slip.innerHTML = '<div class="sp2-sh"><span>Bet slip (1)</span><span><b>Odds ' + odds + '</b> <button type="button" class="sp2-x" aria-label="close" style="background:none;border:0;color:#fff;font-size:16px">✕</button></span></div>' +
      '<div class="sp2-pick">' + esc(m.home_team) + " vs " + esc(m.away_team) + " · <b>" + esc(label) + "</b></div>" +
      '<div class="sp2-row"><input id="sp2-stake" type="number" inputmode="decimal" min="1" step="0.01" value="50" aria-label="Stake ETB"><div class="sp2-pw"><small>Potential win (ግምት)</small><b id="sp2-ret">' + money(50 * odds) + "</b></div></div>" +
      '<div class="sp2-ch"><button type="button" data-v="10">10</button><button type="button" data-v="50">50</button><button type="button" data-v="100">100</button><button type="button" data-v="max">Max</button></div>' +
      '<button type="button" id="sp2-place" class="sp2-place">Place Bet</button><small class="sp2-msg" id="sp2-msg">ግምታዊ ክፍያ ብቻ ነው፤ የመጨረሻው በpool ድርሻ ይወሰናል (ቤቱ የተወሰነ ድርሻ ይወስዳል)።</small>';
    var stake = slip.querySelector("#sp2-stake"), ret = slip.querySelector("#sp2-ret"), msg = slip.querySelector("#sp2-msg");
    var upd = function () { ret.textContent = money((parseFloat(stake.value) || 0) * odds); };
    stake.addEventListener("input", upd); slip.querySelector(".sp2-x").onclick = closeSlip;
    slip.querySelector(".sp2-ch").onclick = function (e) { var c = e.target.closest("button[data-v]"); if (!c) return; stake.value = c.dataset.v === "max" ? String(Math.floor((window.__kdmBalance ? window.__kdmBalance() : 0) * 100) / 100) : c.dataset.v; upd(); };
    slip.querySelector("#sp2-place").onclick = async function () {
      var v = parseFloat(stake.value); if (!v || v <= 0) { msg.textContent = "❌ ትክክለኛ መጠን ያስገቡ"; return; }
      var pb = slip.querySelector("#sp2-place"); pb.disabled = true;
      try {
        var r = await apiFetch("/sports/bet", { method: "POST", json: { match_id: m.id, selection: sel, stake: v } });
        msg.textContent = "✅ " + r.stake + " ብር @ " + r.odds + " -- ግምታዊ ክፍያ " + r.potential_payout + " ብር (የመጨረሻው ክፍያ በpool ድርሻ ይወሰናል፤ ቤቱ " + Math.round((r.rake_pct || 0.08) * 100) + "% ይወስዳል)";
        hap("success"); try { if (typeof refreshBalance === "function") refreshBalance(); } catch (_) {}
      } catch (e) { msg.textContent = "❌ " + (e.message || e); hap("error"); }
      pb.disabled = false;
    };
    slip.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
})();
