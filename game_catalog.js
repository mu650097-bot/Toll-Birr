/* KDM GAME CATALOG -- presentation only. Loaded LAST (after kdm_art.js).
   Adds extra lobby tiles (Slots / Crash / Keno & Spin). Every tile is a themed "skin" over an ALREADY EXISTING,
   server-authoritative engine: Slot -> /games/slot, Crash -> aviator/jet, Keno -> keno/fastkeno, Road -> chicken.
   Stakes, RNG, house edge, payouts, history and provably-fair proof all stay the engine's. A skin only changes the
   name, colours and (for slots) the symbols the player sees -- it never decides a result. */
(function () {
  "use strict";

  // Server slot symbols (webapp_api.py): low -> top prize. A theme maps each to a themed symbol, 1:1.
  var BASE = ["🍒", "🍋", "🔔", "⭐", "7️⃣"];
  var THEMES = {
    fruit:   ["🍒", "🍋", "🔔", "⭐", "7️⃣"],
    fruit2:  ["🍓", "🍇", "🍉", "🍊", "7️⃣"],
    lion:    ["🌴", "🔔", "🦅", "👑", "🦁"],
    coin:    ["🪙", "💰", "🔔", "⭐", "💎"],
    clover:  ["☘️", "🐞", "🌈", "🪙", "🍀"],
    fire:    ["🔥", "🍒", "🔔", "⭐", "7️⃣"],
    crown:   ["🍒", "🍇", "🔔", "💎", "👑"],
    aztec:   ["🌽", "🐍", "☀️", "💎", "🗿"],
    book:    ["📜", "🪲", "🏺", "👁️", "📖"],
    buffalo: ["🌵", "🦅", "🐺", "🪙", "🦬"],
    zeus:    ["🍇", "🏺", "⚡", "👑", "🔱"],
    farm:    ["🥕", "🌽", "🍉", "🥚", "🐔"],
    fox:     ["🍒", "🍋", "🍇", "💎", "🦊"],
    soccer:  ["👟", "🧤", "🥅", "🏆", "⚽"],
    habesha: ["🌼", "☕", "🥁", "👑", "🦁"],
    bell:    ["🍒", "🍀", "⭐", "💰", "🔔"],
    tgd:     ["🔔", "🍒", "💎", "7️⃣", "👑"]
  };

  // [name, icon, theme, colour1, colour2, isNew]
  var SLOTS = [
    ["Abyssinian Lion", "🦁", "lion", "#b45309", "#451a03", 1],
    ["Mega Fruit 777", "7️⃣", "fruit2", "#7c3aed", "#2e1065", 1],
    ["Gold 888", "🥇", "coin", "#eab308", "#713f12", 1],
    ["Lucky Clover 5", "☘️", "clover", "#16a34a", "#052e16", 1],
    ["Fire Fruit 5", "🔥", "fire", "#dc2626", "#450a0a", 0],
    ["Fruity Wilds", "🍉", "fruit2", "#be123c", "#4c0519", 0],
    ["Fruits Rush", "🍓", "fruit2", "#ea580c", "#431407", 0],
    ["Top Fire 5", "5️⃣", "fire", "#ef4444", "#7f1d1d", 0],
    ["Safari King", "🦁", "lion", "#ca8a04", "#422006", 0],
    ["Sizzling Fruits", "🍒", "fruit", "#dc2626", "#14532d", 0],
    ["Royal Crown", "👑", "crown", "#b91c1c", "#450a0a", 0],
    ["Fruity Fortune", "🍌", "fruit2", "#d97706", "#450a0a", 1],
    ["Royal Bags", "💰", "coin", "#dc2626", "#7f1d1d", 0],
    ["Hot Strike 7", "⚡", "fire", "#15803d", "#052e16", 1],
    ["Sunshine Fruits", "☀️", "fruit2", "#f59e0b", "#78350f", 0],
    ["Royal Coins 5", "🪙", "coin", "#f59e0b", "#7c2d12", 0],
    ["Strike 777", "🎯", "fruit", "#ca8a04", "#14532d", 0],
    ["Aztec Gold", "🗿", "aztec", "#0ea5e9", "#1e3a8a", 0],
    ["Book of Dunes", "📖", "book", "#92400e", "#1c1917", 0],
    ["Penalty Kick", "🥅", "soccer", "#ef4444", "#14532d", 0],
    ["Hit Slot 2026", "🎰", "fruit", "#f97316", "#7c2d12", 0],
    ["ሜዳ ፎርቹን", "⚽", "soccer", "#65a30d", "#1a2e05", 1],
    ["እንቁጣጣሽ", "🌼", "habesha", "#ca8a04", "#365314", 1],
    ["Habesha Fortune 5", "🦁", "habesha", "#16a34a", "#713f12", 1],
    ["Thunder Olympus", "⚡", "zeus", "#7c3aed", "#1e1b4b", 1],
    ["Buffalo Plains", "🦬", "buffalo", "#c2410c", "#431407", 0],
    ["Mother Hen", "🐓", "farm", "#dc2626", "#450a0a", 1],
    ["Hen & Fruits", "🍉", "farm", "#22c55e", "#14532d", 1],
    ["Coin Hen", "🐔", "farm", "#f97316", "#7c2d12", 1],
    ["Coin Hen 5", "🪙", "farm", "#2563eb", "#1e1b4b", 1],
    ["Foxy Hot 20", "🦊", "fox", "#f97316", "#064e3b", 1],
    ["Golden Bells", "🔔", "bell", "#eab308", "#581c87", 1],
    ["Flame Wins", "🔥", "fire", "#dc2626", "#7f1d1d", 1],
    ["Inferno Streak", "🌋", "fire", "#f97316", "#7c2d12", 1],
    ["Flame Classics", "🔥", "fire", "#b91c1c", "#1c1917", 0],
    ["Triple Gold", "🪙", "coin", "#ca8a04", "#581c87", 0]
  ];

  // [name, icon, engine, colour1, colour2, categories, isNew, backendKey]
  var OTHERS = [
    ["Crash", "📈", "aviator", "#2563eb", "#1e3a8a", ["crash", "popular", "hot"], 0, "crash"],
    ["Rocket", "🚀", "jet", "#7c3aed", "#1e1b4b", ["crash", "popular"], 0, "rocket"],
    ["High Flyer", "🛩️", "aviator", "#9333ea", "#3b0764", ["crash", "popular"], 0, "highflyer"],
    ["Sky Masters", "🛫", "aviator", "#0ea5e9", "#1e3a8a", ["crash", "new"], 1, "skymasters"],
    ["Power Keno", "🎱", "fastkeno", "#0d9488", "#134e4a", ["keno", "new"], 1, "keno_power"],
    ["Super Keno", "🟢", "fastkeno", "#16a34a", "#052e16", ["keno", "new"], 1, "keno_super"],
    ["Insta Keno", "💎", "fastkeno", "#06b6d4", "#083344", ["keno", "popular"], 0, "keno_insta"],
    ["Triple Gold Deluxe", "🔔", "triplegold", "#c9a227", "#0c0c0c", ["slots", "new", "popular"], 1, "triplegold_deluxe"]
  ];

  var BY_KEY = {};          // alias key -> variant
  var current = null;       // variant being played (or null = a plain engine page)

  function build() {
    var list;
    try { list = GAMES; } catch (e) { return false; }
    if (!list || list.__kdmCatalog) return !!list;
    list.__kdmCatalog = true;

    // 1) tag existing games with the new categories
    var tag = {
      crash: ["aviator", "jet", "chicken", "rabbit", "roast", "penaltystreak", "tower", "chicken2", "fish", "dice2"],
      keno: ["keno", "fastkeno", "wheel"],
      slots: ["slot", "triplegold", "flame", "aztec", "buffalo"]
    };
    list.forEach(function (g) {
      Object.keys(tag).forEach(function (c) {
        if (tag[c].indexOf(g.key) >= 0 && g.cats.indexOf(c) < 0) g.cats.push(c);
      });
    });

    // 2) add the new tiles
    SLOTS.forEach(function (s, i) {
      var v = { key: "slot_" + (i < 9 ? "0" : "") + (i + 1), engine: "slot", api: true, name: s[0], icon: s[1], theme: s[2], color: s[3], color2: s[4],
        badge: s[5] ? "🆕 NEW" : "", cats: s[5] ? ["slots", "new", "popular"] : ["slots", "popular"] };
      BY_KEY[v.key] = v; BY_NAME[v.name] = v; list.push(v);
    });
    OTHERS.forEach(function (o, i) {
      var v = { key: o[7], engine: o[2], api: o[7] !== "chicken2", name: o[0], icon: o[1], color: o[3], color2: o[4],
        badge: o[6] ? "🆕 NEW" : "", cats: o[5].slice() };
      if (v.key === "triplegold_deluxe") v.theme = "tgd";
      BY_KEY[v.key] = v; BY_NAME[v.name] = v; list.push(v);
    });
    return true;
  }


  // ---------------------------------------------------------------- cover art (original vector, no external images)
  function shade(hex, amt) {            // lighten (+) / darken (-) a #rrggbb colour
    var n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    function f(c) { return Math.max(0, Math.min(255, Math.round(c + (amt > 0 ? (255 - c) : c) * amt))); }
    return "#" + ((1 << 24) + (f(r) << 16) + (f(g) << 8) + f(b)).toString(16).slice(1);
  }
  function coverSvg(v) {
    var c1 = v.color, c2 = v.color2, hi = shade(c1, 0.45), lo = shade(c2, -0.35), i, x, y, a, out = "";
    var kind = v.cats.indexOf("crash") >= 0 ? "crash" : v.cats.indexOf("keno") >= 0 ? "keno" : "slot";
    var syms = v.theme ? THEMES[v.theme] : kind === "crash" ? [v.icon, "💥", "💰", "⭐", "🔥"] : [v.icon, "🔢", "💎", "⭐", "🍀"];
    out += '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><defs>' +
      '<radialGradient id="b" cx="50%" cy="38%" r="75%"><stop offset="0" stop-color="' + hi + '"/><stop offset=".45" stop-color="' + c1 + '"/><stop offset="1" stop-color="' + lo + '"/></radialGradient>' +
      '<linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>' +
      '<filter id="d" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#000" flood-opacity=".6"/></filter></defs>' +
      '<rect width="200" height="200" fill="url(#b)"/>';
    // sunburst rays
    for (i = 0; i < 14; i++) {
      a = (i / 14) * Math.PI * 2; var a2 = a + Math.PI / 28;
      out += '<polygon points="100,96 ' + (100 + 260 * Math.cos(a)).toFixed(1) + ',' + (96 + 260 * Math.sin(a)).toFixed(1) + ' ' +
        (100 + 260 * Math.cos(a2)).toFixed(1) + ',' + (96 + 260 * Math.sin(a2)).toFixed(1) + '" fill="#fff" opacity=".09"/>';
    }
    if (kind === "crash") {   // rising multiplier curve
      out += '<path d="M12 168 Q80 160 120 112 T190 28" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="9" stroke-linecap="round"/>' +
        '<path d="M12 168 Q80 160 120 112 T190 28" fill="none" stroke="' + hi + '" stroke-width="4" stroke-linecap="round"/>';
    }
    if (kind === "keno") {    // lottery balls
      var pos = [[34, 40, 17], [168, 52, 14], [152, 148, 16], [40, 150, 13]], nums = [7, 23, 36, 12];
      for (i = 0; i < pos.length; i++) {
        out += '<circle cx="' + pos[i][0] + '" cy="' + pos[i][1] + '" r="' + pos[i][2] + '" fill="#fff" opacity=".92" filter="url(#d)"/>' +
          '<text x="' + pos[i][0] + '" y="' + (pos[i][1] + 1) + '" font-size="' + (pos[i][2] * 1.1) + '" font-weight="900" font-family="Arial,sans-serif" fill="' + c2 + '" text-anchor="middle" dominant-baseline="central">' + nums[i] + '</text>';
      }
    }
    // sparkles
    var sp = [[24, 30, 3], [176, 26, 2.5], [180, 120, 2], [18, 112, 2.5], [60, 18, 2], [140, 14, 3]];
    for (i = 0; i < sp.length; i++) out += '<circle cx="' + sp[i][0] + '" cy="' + sp[i][1] + '" r="' + sp[i][2] + '" fill="#fff" opacity=".85"/>';
    // hero symbol
    out += '<ellipse cx="100" cy="132" rx="52" ry="9" fill="#000" opacity=".28"/>' +
      '<text x="100" y="' + (kind === "crash" ? 82 : 96) + '" font-size="' + (kind === "crash" ? 80 : 92) + '" text-anchor="middle" dominant-baseline="central" filter="url(#d)" font-family="Apple Color Emoji,Segoe UI Emoji,Noto Color Emoji,sans-serif">' + v.icon + '</text>';
    if (kind === "crash" && !v.noMult) out += '<text x="100" y="138" font-size="22" font-weight="900" font-family="Arial,sans-serif" fill="#fff" text-anchor="middle" filter="url(#d)">x2.40</text>';
    // bottom reel strip of theme symbols
    out += '<rect x="14" y="156" width="172" height="30" rx="15" fill="#000" opacity=".42"/>' +
      '<rect x="14" y="156" width="172" height="30" rx="15" fill="none" stroke="#fff" stroke-opacity=".35"/>';
    for (i = 0; i < 5; i++) out += '<text x="' + (34 + i * 33) + '" y="172" font-size="19" text-anchor="middle" dominant-baseline="central" font-family="Apple Color Emoji,Segoe UI Emoji,Noto Color Emoji,sans-serif">' + syms[i] + '</text>';
    out += '<rect width="200" height="100" fill="url(#s)" opacity=".5"/></svg>';
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(out);
  }
  var BY_NAME = {};
  function paintTiles() {
    document.querySelectorAll("#game-grid .game-card").forEach(function (card) {
      if (card.dataset.vart) return;
      var n = card.querySelector(".game-name"), o = card.querySelector(".preview-game-object");
      if (!n || !o) return;
      var v = BY_NAME[n.textContent.trim()];
      if (!v) return;
      card.dataset.vart = "1";
      var th = card.querySelector(".game-thumb");
      if (th) th.style.background = "none";
      o.style.cssText = "position:absolute;inset:0;width:100%;height:100%;margin:0;transform:none;font-size:0;animation:none";
      o.innerHTML = '<img alt="" draggable="false" style="width:100%;height:100%;object-fit:cover;display:block;border-radius:inherit" src="' + coverSvg(v) + '">';
      ["preview-orb", "preview-spark", "preview-track", "preview-stars"].forEach(function (c) {
        card.querySelectorAll("." + c).forEach(function (e) { e.style.display = "none"; });
      });
    });
  }
  function watchGrid() {
    var grid = document.getElementById("game-grid"), q = false;
    if (!grid) return;
    new MutationObserver(function () {
      if (q) return; q = true;
      requestAnimationFrame(function () { q = false; try { paintTiles(); } catch (e) {} });
    }).observe(grid, { childList: true });
    paintTiles();
  }

  function mapSym(s) {
    if (!current || !current.theme) return s;
    var i = BASE.indexOf(s);
    return i < 0 ? s : THEMES[current.theme][i];
  }

  // Cover art for ANY game key (used by the Recent Big Wins tiles so they match the lobby cards).
  // A catalog skin (slot_05, crash, highflyer, keno_power ...) is a real lobby page: a win on it must open THAT skin.
  window.kdmHasVariant = function (key) { return !!BY_KEY[key]; };

  // Always returns a picture for a win/promo card (never null): 1) the approved KDM art by game name, 2) the generated vector cover,
  // 3) a neutral coloured cover with the game's emoji (unknown / future server keys), so no card is ever left without a game image.
  function fallbackCover(icon, seed) {
    var h = 0, t = String(seed || icon || "x"), i;
    for (i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % 360;
    var c1 = "hsl(" + h + ",70%,42%)", c2 = "hsl(" + ((h + 40) % 360) + ",75%,16%)";
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><defs><radialGradient id="b" cx="50%" cy="38%" r="75%"><stop offset="0" stop-color="hsl(' + h + ',80%,62%)"/><stop offset=".5" stop-color="' + c1 + '"/><stop offset="1" stop-color="' + c2 + '"/></radialGradient></defs>' +
      '<rect width="200" height="200" fill="url(#b)"/><text x="100" y="104" font-size="92" text-anchor="middle" dominant-baseline="central">' + (icon || "\uD83C\uDFB2") + '</text></svg>';
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg).replace(/'/g, "%27");
  }
  window.kdmCover = function (key, icon) {
    try {
      var v = BY_KEY[key]; if (!v) { var l = (typeof GAMES !== "undefined" ? GAMES : []); for (var i = 0; i < l.length; i++) if (l[i].key === key) { v = l[i]; break; } }
      if (v && window.KDM_ART && window.KDM_ART[v.name]) return window.KDM_ART[v.name];
      if (v && v.color && v.color2) {
        v = Object.assign({ cats: [] }, v, { noMult: true });   // win tiles show the REAL multiplier, never the decorative "x2.40"
        var uri = coverSvg(v);   // already a complete, encoded data: URI
        if (uri && uri.indexOf("'") < 0) return uri;
      }
      return fallbackCover(icon || (v && v.icon), key);
    } catch (e) { return null; }
  };

  window.kdmSkinKey = function () { return current ? current.key : null; };   // which catalog skin is on the shared engine page (null = plain engine)
  window.kdmVariantKey = window.kdmSkinKey;   // kdm_fastkeno.js asks this to decide Power Keno (meter) vs Fast / Super / Insta

  window.kdmSlotSkin = function () {
    if (!current || current.engine !== "slot") return null;
    return { map: mapSym, c1: current.color2 && current.color ? current.color : "#2a0a3d", c2: current.color2 || "#0d0318", frame: current.color, icon: current.icon };
  };

  function skinPage(engine, v) {
    var page = document.getElementById("page-" + engine);
    if (!page) return;
    var h = page.querySelector("h2");
    if (h) {
      if (!h.dataset.kdmOrig) h.dataset.kdmOrig = h.textContent;
      h.textContent = v ? v.icon + " " + v.name : h.dataset.kdmOrig;
    }
    if (v) { page.style.setProperty("--card-c1", v.color); page.style.setProperty("--card-c2", v.color2); }
    else { page.style.removeProperty("--card-c1"); page.style.removeProperty("--card-c2"); }
    page.classList.toggle("tgd-deluxe", !!(v && v.key === "triplegold_deluxe"));   // black + gold Deluxe palette (CSS below)
    if (engine === "slot") reskinSlot();
  }

  function reskinSlot() {
    var page = document.getElementById("page-slot");
    if (!page) return;
    // remember the server symbol so switching skins never double-maps
    page.querySelectorAll(".slot-reel, .slot-reels-3d span").forEach(function (el) {
      if (!el.dataset.kdmBase) {
        var t = el.textContent.trim();
        // initial board shows "7️⃣" etc.; result spans show the raw server symbol
        el.dataset.kdmBase = t;
      }
      el.textContent = mapSym(el.dataset.kdmBase);
    });
  }

  function wrapNavigation() {
    var prev = goToPage;
    goToPage = function (page) {
      var v = BY_KEY[page];
      if (v) {
        var changed = current !== v;
        current = v;
        skinPage(v.engine, v);
        // other engine pages never keep a stale skin
        ["slot", "aviator", "jet", "keno", "fastkeno", "chicken", "triplegold"].forEach(function (e) { if (e !== v.engine) skinPage(e, null); });
        var rv = prev(v.engine);
        if (changed) {   // a different skin shares this engine page: never show the previous game's last spin
          try { render3DScene(v.engine, {}, "idle"); renderThreeGameScene(v.engine, {}, "idle"); } catch (e) {}
          var rr2 = document.getElementById(v.engine + "-result"); if (rr2) rr2.innerHTML = "";
        }
        return rv;
      }
      current = null;
      ["slot", "aviator", "jet", "keno", "fastkeno", "chicken", "triplegold"].forEach(function (e) { skinPage(e, null); });
      return prev(page);
    };
  }

  function wrapDrawSlot() {
    if (typeof drawSlot !== "function") return;
    var orig = drawSlot;
    drawSlot = function (ctx, w, h, t, o) {
      if (current && current.theme && o && Array.isArray(o.reels)) {
        o = Object.assign({}, o, { reels: o.reels.map(mapSym) });
      }
      return orig(ctx, w, h, t, o);
    };
  }

  function watchSlotResults() {
    var page = document.getElementById("page-slot");
    if (!page) return;
    var busy = false;
    new MutationObserver(function () {
      if (busy) return; busy = true;
      requestAnimationFrame(function () { busy = false; try { reskinSlot(); } catch (e) {} });
    }).observe(page, { childList: true, subtree: true });
  }

  // Route the engine page's API calls to the variant's own game_key (own limits, RTP, history, rounds).
  function wrapApi() {
    if (typeof apiFetch !== "function") return;
    var orig = apiFetch;
    apiFetch = function (path, opts) {
      if (current && current.api && typeof path === "string") {
        var pre = "/games/" + current.engine + "/";
        if (path.indexOf(pre) === 0) path = "/games/" + current.key + "/" + path.slice(pre.length);
      }
      return orig.call(this, path, opts);
    };
  }


  // Triple Gold Deluxe: same server engine and pay table as Triple Gold; only the palette changes (design: black + gold, cream text).
  function deluxeCss() {
    if (document.getElementById("tgd-css")) return;
    var st = document.createElement("style"); st.id = "tgd-css";
    st.textContent = "#page-triplegold.tgd-deluxe{background:#0c0c0c;color:#fff8e1}" +
      "#page-triplegold.tgd-deluxe h2,#page-triplegold.tgd-deluxe .fairness-note{color:#f5d142}" +
      "#page-triplegold.tgd-deluxe .tg-frame{background:linear-gradient(180deg,#1a1710,#0c0c0c);border-color:#c9a227;box-shadow:0 0 0 2px #c9a22733,0 10px 30px #000a}" +
      "#page-triplegold.tgd-deluxe .tg-ribbon{background:linear-gradient(180deg,#f5d142,#c9a227);color:#1a1710}" +
      "#page-triplegold.tgd-deluxe .kx-tile,#page-triplegold.tgd-deluxe .av-card{background:#1a1710;border:1px solid #c9a227;color:#fff8e1}" +
      "#page-triplegold.tgd-deluxe .kx-tile small{color:#d9c88a}#page-triplegold.tgd-deluxe .kx-tile b{color:#f5d142}" +
      "#page-triplegold.tgd-deluxe .kx-step button{background:#2a2412;color:#f5d142;border-color:#c9a227}" +
      "#page-triplegold.tgd-deluxe .kx-step input{background:#0c0c0c;color:#fff8e1;border-color:#c9a227}" +
      "#page-triplegold.tgd-deluxe #tg-go{background:linear-gradient(180deg,#f5d142,#c9a227);color:#1a1710}" +
      "#page-triplegold.tgd-deluxe .tg-ribbon{position:relative;color:transparent}#page-triplegold.tgd-deluxe .tg-ribbon::after{content:'TRIPLE GOLD DELUXE';position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#1a1710}";
    document.head.appendChild(st);
  }
  function boot() {
    if (!build()) return;
    try { deluxeCss(); } catch (e) { /* palette only */ }
    try { watchGrid(); } catch (e) { /* tiles keep their emoji */ }
    try { wrapNavigation(); wrapDrawSlot(); wrapApi(); } catch (e) { /* keep lobby working if anything is missing */ }
    // pages are created lazily by app.js: watch for the slot page
    var tries = 0;
    (function wait() {
      if (document.getElementById("page-slot")) { watchSlotResults(); return; }
      if (++tries < 40) setTimeout(wait, 250);
    })();
    try {
      var q = document.getElementById("game-search");
      if (typeof renderGameGrid === "function") renderGameGrid(q ? q.value : "");
    } catch (e) { /* main() renders the grid */ }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
