/* BETPRO THEME + ADMIN PHOTOS. Load LAST (after kdm_fix.js, with kdm_betpro.css). Needs betpro_v1.py on the server.
   - Home: BetPro wordmark, hero banner (photo = admin upload per Sports / Casino), Sports|Casino switch, Live Now + Popular Leagues from the real
     /sports/matches, Game Categories grid with covers (admin can replace any game's cover).
   - Profile: level + Total Wins / Games Played / Day Streak. Admin panel: "Promo photos" box to upload/remove the photos.
   No game or money logic is touched. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var IMG_BASE = ""; try { IMG_BASE = String(API_BASE).replace(/\/api\/?$/, ""); } catch (_) {}
  var S = { mode: "casino", promo: {}, matches: [], timer: null };
  try { var m0 = localStorage.getItem("bp_mode"); if (m0 === "sports" || m0 === "casino") S.mode = m0; } catch (_) {}

  /* ---------------------------------------------------------------- brand */
  function sub() { var l = $("page-lobby"); document.body.classList.toggle("bp-sub-hide", !!l && !l.classList.contains("active")); }
  function brand() { sub();
    var n = document.querySelector("#topbar .brand-name"); if (n && n.dataset.bp !== "1") { n.dataset.bp = "1"; n.innerHTML = 'Bet<b>Pro</b>'; }
    var d = $("top-deposit-btn"); if (d && !d.getAttribute("aria-label")) d.setAttribute("aria-label", "Deposit");
  }

  /* ---------------------------------------------------------------- promo photos */
  async function loadPromo() {
    try { var r = await apiFetch("/promo/images"); S.promo = r.items || {}; } catch (_) { S.promo = {}; }
    paintHero(); paintCovers();
  }
  function img(slot) { var p = S.promo[slot]; return p ? IMG_BASE + p.image : ""; }

  /* ---------------------------------------------------------------- home */
  function build() {
    var lobby = $("page-lobby"); if (!lobby || $("bp-hero")) return;
    var hero = document.createElement("div"); hero.id = "bp-hero"; hero.className = "bp-hero";
    hero.innerHTML = '<div class="bp-hero-art" id="bp-hero-art"></div><div class="bp-hero-shade"></div><div class="bp-hero-copy"><h2 id="bp-hero-t"></h2><p id="bp-hero-s"></p>' +
      '<button type="button" id="bp-hero-cta" class="bp-cta"></button></div>';
    var tog = document.createElement("div"); tog.className = "bp-toggle"; tog.id = "bp-toggle";
    tog.innerHTML = '<button type="button" data-m="sports"><span>\u26BD</span> Sports</button><button type="button" data-m="casino"><span>\u2660\uFE0F</span> Casino</button>';
    var sp = document.createElement("div"); sp.id = "bp-sports"; sp.className = "bp-sports";
    sp.innerHTML = '<div class="bp-chips" id="bp-chips">' +
      [["\u26BD", "Football"], ["\uD83C\uDFC0", "Basketball"], ["\uD83C\uDFBE", "Tennis"], ["\u2026", "More"]].map(function (c) { return '<button type="button" data-go="sports"><i>' + c[0] + '</i>' + c[1] + '</button>'; }).join("") + '</div>' +
      '<div class="bp-sec"><b><i class="bp-dot"></i>Live Now</b><button type="button" data-go="sports">See All \u2192</button></div><div id="bp-live"></div>' +
      '<div class="bp-sec"><b><i class="bp-cup">\uD83C\uDFC6</i>Popular Leagues</b><button type="button" data-go="sports">See All \u2192</button></div><div id="bp-leagues" class="bp-leagues"></div>';
    lobby.insertBefore(hero, lobby.firstChild); hero.after(tog); tog.after(sp);
    tog.addEventListener("click", function (e) { var b = e.target.closest("button[data-m]"); if (b) setMode(b.dataset.m); });
    sp.addEventListener("click", function (e) { var b = e.target.closest("[data-go]"); if (b) goToPage(b.dataset.go); });
    $("bp-hero-cta").addEventListener("click", function () {
      if (S.mode === "sports") goToPage("sports"); else { var g = $("game-grid"); if (g) g.scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
    var gt = $("lobby-section-title"); if (gt) gt.textContent = "Game Categories";
    setMode(S.mode, true);
  }
  function setMode(m, silent) {
    S.mode = m; document.body.dataset.bpMode = m; try { localStorage.setItem("bp_mode", m); } catch (_) {}
    document.querySelectorAll("#bp-toggle button").forEach(function (b) { b.classList.toggle("on", b.dataset.m === m); });
    paintHero(); if (m === "sports" && !silent) loadSports();
  }
  function paintHero() {
    var a = $("bp-hero-art"); if (!a) return; var sports = S.mode === "sports", url = img(sports ? "sports_hero" : "casino_hero");
    a.style.backgroundImage = url ? 'url("' + url + '")' : ""; $("bp-hero").classList.toggle("has-img", !!url); $("bp-hero").dataset.m = S.mode;
    $("bp-hero-t").innerHTML = sports ? 'Play <i>\u2022</i> Bet <i>\u2022</i> Win' : 'Casino Games';
    $("bp-hero-s").textContent = sports ? "Your Ultimate Gaming Experience" : "Play 16+ Exciting Games";
    $("bp-hero-cta").textContent = sports ? "Join Now \u2192" : "Play Now \u2192";
  }

  /* ---------------------------------------------------------------- live matches (real data from /sports/matches) */
  function crest(url, name) { return url ? '<img src="' + esc(IMG_BASE && url.charAt(0) === "/" ? IMG_BASE + url : url) + '" alt="" loading="lazy">' : '<span class="bp-ini">' + esc((name || "?").trim().charAt(0).toUpperCase()) + "</span>"; }
  async function loadSports() {
    if (!$("bp-live")) return;
    try { var r = await apiFetch("/sports/matches"); S.matches = r.matches || []; } catch (_) { S.matches = []; }
    var live = S.matches.filter(function (m) { return m.live; }), m = live[0] || S.matches[0];
    $("bp-live").innerHTML = m ? '<div class="bp-match" data-go="sports"><div class="bp-m-top"><em class="' + (m.live ? "live" : "soon") + '">' + (m.live ? "\u2022 LIVE" : "SOON") + "</em><small>" + esc(m.league || "") + (m.live && m.live_minute != null ? " \u00B7 " + esc(m.live_minute) + "'" : "") + '</small></div>' +
      '<div class="bp-m-main"><div class="bp-team">' + crest(m.home_logo, m.home_team) + "<b>" + esc(m.home_team) + '</b></div><div class="bp-score">' + (m.live && m.home_score != null ? esc(m.home_score) + " - " + esc(m.away_score) : "VS") + '</div><div class="bp-team">' + crest(m.away_logo, m.away_team) + "<b>" + esc(m.away_team) + "</b></div></div>" +
      '<div class="bp-odds"><span><s>1</s>' + Number(m.odds_home).toFixed(2) + "</span>" + (Number(m.odds_draw) > 0 ? "<span><s>X</s>" + Number(m.odds_draw).toFixed(2) + "</span>" : "") + "<span><s>2</s>" + Number(m.odds_away).toFixed(2) + "</span></div></div>"
      : '<div class="bp-empty">\u26BD No matches right now \u2014 check back soon.</div>';
    var by = {}; S.matches.forEach(function (x) { var k = x.league || (x.sport ? x.sport.charAt(0).toUpperCase() + x.sport.slice(1) : "Football"); by[k] = (by[k] || 0) + 1; });
    var keys = Object.keys(by).sort(function (a, b) { return by[b] - by[a]; }).slice(0, 5);
    $("bp-leagues").innerHTML = keys.length ? keys.map(function (k) { return '<button type="button" data-go="sports"><i>\uD83C\uDFC6</i><span>' + esc(k) + "</span><em>" + by[k] + ' \u203A</em></button>'; }).join("") : "";
  }

  /* ---------------------------------------------------------------- game covers (admin photo wins over the built-in art) */
  function paintCovers() {
    document.querySelectorAll("#game-grid .game-card").forEach(function (card) {
      var th = card.querySelector(".game-thumb"); if (!th) return;
      var m = /game-thumb-([a-z0-9_]+)/.exec(th.className); if (!m) return;
      var url = img("game_" + m[1]), want = url ? 'url("' + url + '")' : "";
      if ((card.style.getPropertyValue("--bp-cover") || "") === want) return;       // nothing to change = no DOM write = no observer loop
      if (want) { card.style.setProperty("--bp-cover", want); card.classList.add("has-cover"); } else { card.style.removeProperty("--bp-cover"); card.classList.remove("has-cover"); }
    });
  }

  /* ---------------------------------------------------------------- profile header */
  async function profile() {
    var p = $("page-profile"); if (!p) return;
    var box = $("bp-profile");
    if (!box) { box = document.createElement("div"); box.id = "bp-profile"; box.className = "bp-profile"; p.insertBefore(box, p.firstChild); }
    var u = {}; try { u = (tg.initDataUnsafe && tg.initDataUnsafe.user) || {}; } catch (_) {}
    var name = [u.first_name, u.last_name].filter(Boolean).join(" ") || u.username || "Player", st = { level: 1, progress_pct: 0, total_wins: 0, games_played: 0, day_streak: 0 };
    try { st = await apiFetch("/betpro/stats"); } catch (_) {}
    box.innerHTML = '<div class="bp-p-top"><div class="bp-av">' + esc(name.charAt(0).toUpperCase()) + '<i>VIP</i></div><div class="bp-p-id"><h3>' + esc(name) + ' <span class="bp-ok">\u2713</span></h3><p>Level ' + st.level + '</p><div class="bp-bar"><i style="width:' + st.progress_pct + '%"></i></div></div><b class="bp-pct">' + st.progress_pct + '%</b></div>' +
      '<div class="bp-stats"><div><i>\uD83C\uDFC6</i><b>' + Number(st.total_wins).toLocaleString() + "</b><small>Total Wins</small></div><div><i>\uD83C\uDFAE</i><b>" + Number(st.games_played).toLocaleString() + "</b><small>Games Played</small></div><div><i>\u2B50</i><b>" + st.day_streak + "</b><small>Day Streak</small></div></div>";
  }

  /* ---------------------------------------------------------------- admin: promo photos */
  function slots() {
    var l = [["sports_hero", "\u26BD Home banner \u2014 Sports"], ["casino_hero", "\u2660\uFE0F Home banner \u2014 Casino"]];
    try { (GAMES || []).forEach(function (g) { l.push(["game_" + g.key, "\uD83C\uDFAE Cover \u2014 " + g.name]); }); } catch (_) {}
    return l;
  }
  function adminBox() {
    var pg = $("page-admin"); if (!pg || $("bp-admin")) return;
    var tabs = pg.querySelector(".admin-tabs"); if (!tabs) return;
    var box = document.createElement("div"); box.id = "bp-admin"; box.className = "admin-bonus-box";
    box.innerHTML = '<h3>\uD83D\uDDBC Promo photos (BetPro)</h3><p class="admin-note">Sports/Casino ዋና banner እና የእያንዳንዱ ጨዋታ cover ፎቶ እዚህ ይቀይሩ። JPG / PNG / WEBP, እስከ 15MB። ሰፊ (16:9) ፎቶ ይሻላል።</p>' +
      '<select id="bp-slot">' + slots().map(function (s) { return '<option value="' + esc(s[0]) + '">' + esc(s[1]) + "</option>"; }).join("") + '</select> <input type="file" id="bp-file" accept="image/jpeg,image/png,image/webp"> ' +
      '<button type="button" id="bp-up" class="admin-save-game">\u2B06 Upload</button> <button type="button" id="bp-rm" class="admin-save-game">\uD83D\uDDD1 Remove</button> <small id="bp-st"></small><div id="bp-thumbs" class="bp-thumbs"></div>';
    tabs.insertAdjacentElement("beforebegin", box);
    $("bp-up").addEventListener("click", async function () {
      var f = $("bp-file").files[0], st = $("bp-st"); if (!f) { st.textContent = "ፎቶ ይምረጡ"; return; }
      var fd = new FormData(); fd.append("photo", f); st.textContent = "\u23F3";
      try { var r = await apiFetch("/admin/promo/" + $("bp-slot").value, { method: "POST", formData: fd }); S.promo = r.items || S.promo; st.textContent = "\u2705 Saved"; $("bp-file").value = ""; thumbs(); paintHero(); paintCovers(); } catch (e) { st.textContent = "\u274C " + (e.message || e); }
    });
    $("bp-rm").addEventListener("click", async function () {
      var st = $("bp-st"); try { var r = await apiFetch("/admin/promo/" + $("bp-slot").value, { method: "DELETE" }); S.promo = r.items || {}; st.textContent = "\u2705 Removed"; thumbs(); paintHero(); paintCovers(); } catch (e) { st.textContent = "\u274C " + (e.message || e); }
    });
    thumbs();
  }
  function thumbs() {
    var t = $("bp-thumbs"); if (!t) return; var names = {}; slots().forEach(function (s) { names[s[0]] = s[1]; });
    t.innerHTML = Object.keys(S.promo).map(function (k) { return '<figure><img src="' + esc(IMG_BASE + S.promo[k].image) + '" alt=""><figcaption>' + esc(names[k] || k) + "</figcaption></figure>"; }).join("") || '<small class="admin-note">No photos yet.</small>';
  }

  /* ---------------------------------------------------------------- wiring */
  function onPage(p) {
    setTimeout(sub, 0);
    if (p === "lobby") { loadPromo(); if (S.mode === "sports") loadSports(); startPoll(); } else stopPoll();
    if (p === "profile") profile();
    if (p === "admin") setTimeout(function () { adminBox(); loadPromo().then(thumbs); }, 600);
  }
  function startPoll() { stopPoll(); S.timer = setInterval(function () { var l = $("page-lobby"); if (!l || !l.classList.contains("active")) return stopPoll(); if (S.mode === "sports") loadSports(); }, 20000); }
  function stopPoll() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }
  try { var raw = goToPage; goToPage = function (p) { var r = raw.apply(this, arguments); try { onPage(p); } catch (_) {} return r; }; } catch (_) {}
  function boot() {
    brand(); build(); paintCovers();
    var t = null;       // debounced: other scripts re-render the grid, never react synchronously to our own writes
    new MutationObserver(function () { if (t) return; t = setTimeout(function () { t = null; brand(); build(); paintCovers(); }, 250); }).observe(document.body, { childList: true, subtree: true });
    var go = function () { loadPromo(); if (S.mode === "sports") loadSports(); };
    go(); setTimeout(go, 2500);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
