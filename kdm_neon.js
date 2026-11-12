/* KDM NEON HOME. Load LAST (after kdm_betpro.js, with kdm_neon.css).
   - Header: "Play Win 🥳" wordmark (undoes the BetPro wordmark).
   - Rotating banner: slide 1 = Welcome; the next slides = the REAL recent winners from /api/wins/recent
     (same data as the "Recent Big Wins" strip: nobody is invented, amounts come from the server).
   - Category pills (All / Slots / Table / Sports / Arcade / Crash / Keno) that filter the tiles in place.
   - Tiles: HOT/NEW badge colour + "Play Now" button. Nothing about games, money or the API is changed. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var S = { wins: [], pop: [], ban: [], i: 0, t: null, cat: "all", n: 0 };
  // A win arrives with the server's engine key (e.g. "minesx", "slot_05", "keno_super"); resolve it to a lobby page that really exists,
  // otherwise a tap on the slide silently did nothing.
  function gameKey(k) { try { return typeof resolveWinGame === "function" ? resolveWinGame(k) : (k || ""); } catch (_) { return k || ""; } }
  // The rotating banner also shows these game pictures (key = page/skin to open, name = KDM_ART/KDM_TILE picture). Not wins -- plain game promos.
  var FEATURED = [["aviator", "Aviator"], ["jet", "Jet"], ["crash", "Crash"], ["highflyer", "High Flyer"], ["skymasters", "Sky Masters"]];

  /* ---------------- brand ---------------- */
  function brand() {
    var n = document.querySelector("#topbar .brand-name");
    if (n && n.dataset.knb !== "1") { n.dataset.knb = "1"; n.dataset.bp = "1"; n.innerHTML = "King<b>Bet</b>"; }
    var t = document.querySelector("#topbar .brand-tagline"); if (t && t.textContent !== "Play \u2022 Win \u2022 Enjoy") t.textContent = "Play \u2022 Win \u2022 Enjoy";   // Play Win \uD83E\uDD73 (the brand set in index.html)
    try { document.body.dataset.bpMode = "casino"; localStorage.setItem("bp_mode", "casino"); } catch (_) {}
  }

  /* ---------------- rotating banner ---------------- */
  function welcomeSlide() {
    return '<div class="kn-slide" data-act="play"><span class="kn-side">\uD83C\uDFC6</span><div class="kn-mid"><h2>Welcome to <b>King Bet!</b></h2><p>Play \u2022 Win \u2022 Earn Big!</p>' +
      '<button type="button" class="kn-cta">Play Now \u25B8</button></div><span class="kn-side r">\uD83C\uDF81</span></div>';
  }
  function winSlide(w) {
    var gk = gameKey(w.game);
    var gm = (typeof GAMES !== "undefined" ? GAMES : []).find(function (g) { return g.key === gk; });
    var gname = w.game_name || (gm && gm.name) || "";
    var cover = window.kdmCover ? (window.kdmCover(gk || w.game, w.icon) || window.kdmCover(w.game, w.icon)) : null;
    var icon = w.icon || (gm && gm.icon) || "\uD83C\uDF89";
    var amt = "Br " + Number(w.amount).toLocaleString(undefined, { maximumFractionDigits: 2 });
    var x = Number(w.multiplier) > 1 ? '<span class="kn-x">\u00D7' + Number(w.multiplier).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "</span>" : "";
    return '<div class="kn-slide win" data-act="game" data-game="' + esc(gk) + '"><span class="kn-side">\uD83C\uDFC6</span>' +
      '<div class="kn-mid"><span class="kn-amt">' + esc(amt) + '</span><span class="kn-who">' + esc(w.name || "") + "</span>" +
      '<span class="kn-where">' + (gname ? "won on " + esc(gname) : "big win!") + x + "</span></div>" +
      '<div class="kn-thumb"' + (cover ? ' style="background-image:url(\'' + cover + '\')"' : "") + ">" + (cover ? "" : esc(icon)) + "</div></div>";
  }
  function featSlide(f) {
    var art = window.KDM_ART && window.KDM_ART[f[1]];
    return '<div class="kn-slide feat" data-act="game" data-game="' + esc(f[0]) + '"' + (art ? ' style="background-image:url(\'' + art + '\')"' : "") + '>' +
      '<div class="kn-mid"><span class="kn-feat-name">' + esc(f[1]) + '</span><button type="button" class="kn-cta">Play Now \u25B8</button></div></div>';
  }
  // BIG "most played" slide: the game players really play most (server: /api/games/popular, real rounds).
  function popSlide(p, rank) {
    var gk = gameKey(p.game);
    var gm = (typeof GAMES !== "undefined" ? GAMES : []).find(function (g) { return g.key === gk; });
    var cover = window.kdmCover ? (window.kdmCover(gk || p.game, gm && gm.icon) || null) : null;
    var name = p.name || (gm && gm.name) || p.game;
    return '<div class="kn-slide pop" data-act="game" data-game="' + esc(gk) + '"' + (cover ? ' style="background-image:url(\'' + cover + '\')"' : "") + '>' +
      '<div class="kn-mid"><span class="kn-pop-badge">\uD83D\uDD25 MOST PLAYED #' + rank + '</span>' +
      '<span class="kn-pop-name">' + esc(name) + '</span>' +
      '<span class="kn-pop-stat">' + Number(p.players).toLocaleString() + ' players \u2022 ' + Number(p.plays).toLocaleString() + ' rounds</span>' +
      '<button type="button" class="kn-cta">Play Now \u25B8</button></div></div>';
  }
  // Pictures the admin posted (same /api/banners list as the home banner manager): a new/removed admin picture shows here too.
  function banSlide(b) {
    var base = String(API_BASE).replace(/\/api\/?$/, "");
    return '<div class="kn-slide ban" data-act="game" data-game="' + esc(b.link_page || "") + '" style="background-image:url(\'' + esc(base + b.image) + '\')"></div>';
  }
  function slidesHtml() {   // Welcome, the most played games (big), then admin pictures (or the default game art) alternating with real winners
    var out = [], i;
    for (i = 0; i < Math.min(3, S.pop.length); i++) out.push(popSlide(S.pop[i], i + 1));
    var pics = S.ban.length ? S.ban.map(banSlide) : FEATURED.map(featSlide);
    var n = Math.max(S.wins.length, pics.length);
    for (i = 0; i < n; i++) { if (i < pics.length) out.push(pics[i]); if (i < S.wins.length) out.push(winSlide(S.wins[i])); }
    S.n = 1 + out.length;
    return welcomeSlide() + out.join("");
  }
  function buildHero() {
    var lobby = $("page-lobby"); if (!lobby || $("kn-hero")) return;
    var h = document.createElement("div"); h.id = "kn-hero";
    h.innerHTML = '<span class="kn-live"><i></i>LIVE WIN</span><div class="kn-slides" id="kn-slides"></div><div class="kn-dots" id="kn-dots"></div>';
    lobby.insertBefore(h, lobby.firstChild);
    h.addEventListener("click", function (e) {
      var s = e.target.closest(".kn-slide"); if (!s) return;
      if (s.dataset.act === "game" && s.dataset.game && document.getElementById("page-" + s.dataset.game)) {
        try { goToPage(s.dataset.game); haptic("success"); return; } catch (_) {}
      }
      try { var g = $("game-grid"); if (g) g.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (_) {}
    });
    var sx = 0; // swipe
    h.addEventListener("touchstart", function (e) { sx = e.touches[0].clientX; }, { passive: true });
    h.addEventListener("touchend", function (e) { var d = e.changedTouches[0].clientX - sx; if (Math.abs(d) > 40) go(S.i + (d < 0 ? 1 : -1)); }, { passive: true });
    paintSlides();
  }
  function paintSlides() {
    var box = $("kn-slides"); if (!box) return;
    var cur = S.i;
    box.innerHTML = slidesHtml();
    $("kn-dots").innerHTML = new Array(S.n + 1).join("<i></i>");
    $("kn-dots").style.display = S.n > 1 ? "flex" : "none";
    go(cur < S.n ? cur : 0, true);
    clearInterval(S.t);
    if (S.n > 1) S.t = setInterval(function () { if (!document.hidden) go(S.i + 1); }, 4200);
  }
  function go(i, quiet) {
    if (!S.n) return;
    S.i = (i + S.n) % S.n;
    var box = $("kn-slides"); if (!box) return;
    box.style.transform = "translateX(" + (-100 * S.i) + "%)";
    var d = $("kn-dots").children; for (var k = 0; k < d.length; k++) d[k].classList.toggle("on", k === S.i);
    var cs = box.children[S.i]; $("kn-hero").classList.toggle("on-win", !!(cs && cs.classList.contains("win")));   // "LIVE WIN" only on real winner slides, never on game promos
    if (!quiet && S.n > 1) { clearInterval(S.t); S.t = setInterval(function () { if (!document.hidden) go(S.i + 1); }, 4200); }
  }
  async function loadWins() {
    var jobs = await Promise.all([
      apiFetch("/wins/recent").then(function (r) { return r && r.wins ? r.wins.slice(0, 8) : []; }).catch(function () { return null; }),
      apiFetch("/games/popular").then(function (r) { return r && r.games ? r.games : []; }).catch(function () { return null; }),
      apiFetch("/banners").then(function (r) { return r && r.items ? r.items.slice(0, 5) : []; }).catch(function () { return null; })
    ]);
    if (jobs[0]) S.wins = jobs[0]; if (jobs[1]) S.pop = jobs[1]; if (jobs[2]) S.ban = jobs[2];
    paintSlides();
  }

  /* ---------------- category pills ---------------- */
  var PILLS = [["all", "\uD83D\uDD25", "All Games"], ["slots", "\uD83C\uDFB0", "Slots"], ["table", "\uD83C\uDCCF", "Table Games"], ["sports", "\u26BD", "Sports"], ["arcade", "\uD83C\uDFAE", "Arcade"], ["crash", "\uD83D\uDE80", "Crash"], ["keno", "\uD83C\uDFB1", "Keno"]];
  var TABLE = /roulette|blackjack|baccarat|dragon|andar|card table|coin flip|lucky wheel|bingo/i;
  var SPORTS = /penalty|sports/i;
  var CRASH = /aviator|jet|rocket|crash|flyer|sky masters/i;
  var KENO = /keno|bingo/i;
  var ARCADE = /chicken|rabbit|fish|boom|mines|plinko|dice|number|roast|ladder/i;
  function catOf(name, key) {
    var g = (typeof GAMES !== "undefined" ? GAMES : []).find(function (x) { return x.name === name; }), c = (g && g.cats) || [];
    if (SPORTS.test(name)) return "sports";
    if (CRASH.test(name)) return "crash";
    if (KENO.test(name)) return "keno";
    if (TABLE.test(name)) return "table";
    if (ARCADE.test(name)) return "arcade";
    if (c.indexOf("crash") >= 0) return "crash";
    if (c.indexOf("keno") >= 0) return "keno";
    return "slots";
  }
  function buildPills() {
    var lobby = $("page-lobby"), hero = $("kn-hero"); if (!lobby || $("kn-pills")) return;
    var p = document.createElement("div"); p.id = "kn-pills";
    p.innerHTML = PILLS.map(function (x) { return '<button type="button" data-c="' + x[0] + '" class="' + (x[0] === S.cat ? "on" : "") + '"><i>' + x[1] + "</i>" + x[2] + "</button>"; }).join("");
    var after = $("wins-banner") || hero; after.after(p);
    p.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-c]"); if (!b) return;
      S.cat = b.dataset.c; p.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
      var t = $("lobby-section-title"); if (t) t.textContent = S.cat === "all" ? "Popular Games" : b.textContent.trim();
      tiles();
    });
  }

  /* ---------------- tiles ---------------- */
  var busy = false;
  function tiles() {
    if (busy) return; busy = true;
    try {
      document.querySelectorAll("#game-grid .game-card").forEach(function (card) {
        var n = card.querySelector(".game-name"); if (!n) return;
        var name = n.textContent.trim();
        if (!card.querySelector(".kn-play")) { var s = document.createElement("span"); s.className = "kn-play"; s.textContent = "Play Now"; card.appendChild(s); }
        var b = card.querySelector(".game-badge");
        if (b) { var hot = /hot/i.test(b.textContent) ? "hot" : "new"; if (b.dataset.b !== hot) b.dataset.b = hot; }
        var pic = window.KDM_TILE && window.KDM_TILE[name];
        if (pic && !card.classList.contains("has-cover")) {
          if (card.dataset.knpic !== name) {
            card.dataset.knpic = name; card.style.setProperty("--kn-tile", 'url("' + pic + '")');
            card.classList.add("kn-pic"); card.classList.toggle("kn-fit", (window.KDM_RATIO[name] || 1.5) < 1.25);
          }
        } else if (card.dataset.knpic) { card.classList.remove("kn-pic", "kn-fit"); card.style.removeProperty("--kn-tile"); delete card.dataset.knpic; }
        var show = S.cat === "all" || catOf(name) === S.cat;
        card.classList.toggle("kn-hide", !show);
      });
    } finally { busy = false; }
  }
  function watch() {
    var g = $("game-grid"); if (!g || g.dataset.knw) return; g.dataset.knw = "1";
    var q = false;
    new MutationObserver(function () { if (q || busy) return; q = true; requestAnimationFrame(function () { q = false; tiles(); }); }).observe(g, { childList: true });
    tiles();
  }

  /* ---------------- win cards use the same cover pictures ---------------- */
  (function () {
    var orig = window.kdmCover;
    window.kdmCover = function (key, icon) {
      try {
        var g = (typeof GAMES !== "undefined" ? GAMES : []).find(function (x) { return x.key === key; });
        var a = g && window.KDM_ART && window.KDM_ART[g.name];
        if (a) return a;
      } catch (_) {}
      return orig ? orig(key, icon) : null;
    };
  })();

  /* ---------------- King Bet promo cards (Deposit / Invite / VIP) ---------------- */
  document.addEventListener("click", function (e) {
    var c = e.target.closest && e.target.closest(".kb-promo[data-quick-page]"); if (!c) return;
    try { goToPage(c.dataset.quickPage); } catch (_) {}
  });

  /* ---------------- boot ---------------- */
  function boot() {
    brand(); buildHero(); buildPills(); watch();
    var st = $("lobby-section-title"); if (st && !boot.t0 && /Game Categories/.test(st.textContent)) { boot.t0 = 1; st.textContent = "Popular Games"; }
    if (!boot.done && $("kn-hero")) { boot.done = 1; loadWins(); setInterval(loadWins, 30000); document.addEventListener("visibilitychange", function () { if (!document.hidden) loadWins(); }); }
  }
  var tries = 0, iv = setInterval(function () { boot(); if (++tries > 80 || ($("kn-pills") && $("game-grid") && $("game-grid").dataset.knw && boot.done)) clearInterval(iv); }, 250);
  document.addEventListener("DOMContentLoaded", boot);
  new MutationObserver(function () { brand(); if (!$("kn-hero")) boot(); }).observe(document.body, { childList: true, subtree: false });
})();
