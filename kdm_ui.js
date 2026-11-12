/* KDM UI LAYER -- presentation only.
   Drives the sidebar/drawer, header (back button, page title, user chip), bottom nav highlight,
   Home vs Games view, wallet shortcuts and the quick-stake buttons on game pages.
   It never calls a money/game API and never changes a bet, payout or round: it only moves the
   user between existing pages (via goToPage) and fills existing form inputs the user could type into.
   Loaded LAST (after app.js, premium.js, engagement.js, onboarding.js, ...). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var body = document.body;
  var currentPage = "lobby";

  // ------------------------------------------------------------------ helpers
  function setCategory(cat) {
    try { activeCategory = cat; } catch (e) { /* app.js not ready */ }
    document.querySelectorAll(".cabinet-tab").forEach(function (b) { b.classList.toggle("active", b.dataset.cat === cat); });
    try {
      var q = $("game-search");
      if (typeof renderGameGrid === "function") renderGameGrid(q ? q.value : "");
    } catch (e) { /* grid not ready yet; main() renders it */ }
    var title = $("lobby-section-title");
    if (title) title.textContent = body.classList.contains("kdm-games-view") ? "All Games" : "Popular Games";
  }
  function showHome() {
    body.classList.remove("kdm-games-view");
    setCategory("popular");
    goToPage("lobby");
  }
  function showGames(cat) {
    body.classList.add("kdm-games-view");
    setCategory(cat || "all");
    goToPage("lobby");
  }
  function walletTab(name) {
    var b = document.querySelector('#wallet-subtabs button[data-wsub="' + name + '"]');
    if (b) b.click();
  }
  function scrollTo(sel) {
    if (!sel) return;
    setTimeout(function () {
      var el = document.querySelector(sel);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }
  function plainTitle(page) {
    var h = document.querySelector("#page-" + page + " h2");
    var t = h ? h.textContent : page;
    return String(t).replace(/^[^\p{L}\p{N}]+/u, "").trim();
  }
  function closeDrawer() { body.classList.remove("kdm-drawer-open"); var m = $("kdm-menu-btn"); if (m) m.setAttribute("aria-expanded", "false"); }
  function toggleDrawer() {
    var open = body.classList.toggle("kdm-drawer-open");
    var m = $("kdm-menu-btn"); if (m) m.setAttribute("aria-expanded", open ? "true" : "false");
  }

  // ------------------------------------------------------- which nav item is "on"
  var GAME_PAGES = /^(boom|number|dice|slot|triplegold|flame|aztec|buffalo|wheel|keno|roulette|bingo|fastkeno|roast|rabbit|chicken2|chicken|penaltystreak|tower|aviator|plinko|mines|jet|fish|card|coinflip|dice2|coinstreak|penalty|baccarat|blackjack|dragontiger|andarbahar)$/;
  function navKeyFor(page) {
    if (page === "lobby") return body.classList.contains("kdm-games-view") ? "games" : "home";
    if (GAME_PAGES.test(page)) return "games";
    if (page === "wallet") {
      var w = document.querySelector(".wsub.active");
      var id = w ? w.id.replace("wsub-", "") : "deposit";
      return id === "history" ? "wallet" : id;
    }
    if (page === "admin" || page === "terms" || page === "privacy") return "profile";
    return page; // sports, marketplace, invite, profile, shamo ...
  }
  function syncNav() {
    var key = navKeyFor(currentPage);
    document.querySelectorAll("#side-nav [data-key], #bottom-nav [data-key]").forEach(function (b) {
      // the bottom bar has no Deposit/Withdraw entries: those light up "Wallet"
      var k = b.dataset.key, on = k === key;
      if (!on && k === "wallet" && b.closest("#bottom-nav") && (key === "deposit" || key === "withdraw")) on = true;
      b.classList.toggle("kdm-on", on);
    });
    var onLobby = currentPage === "lobby";
    var back = $("kdm-back"), lock = $("brand-lockup"), title = $("kdm-page-title");
    if (back) back.hidden = onLobby;
    if (lock) lock.classList.toggle("kdm-hide-sm", !onLobby);
    if (title) title.textContent = onLobby ? "" : (GAME_PAGES.test(currentPage) ? plainTitle(currentPage) : titleFor(currentPage));
    body.dataset.kdmPage = currentPage;
    body.classList.toggle("kdm-on-lobby", onLobby);
  }
  function titleFor(page) {
    if (page === "wallet") {
      var k = navKeyFor("wallet");
      return k === "deposit" ? "Deposit" : k === "withdraw" ? "Withdraw" : "My Wallet";
    }
    return plainTitle(page);
  }

  // ------------------------------------------------------------ wrap goToPage
  (function wrap() {
    if (typeof goToPage !== "function") return;
    var prev = goToPage;
    goToPage = function (page) {
      currentPage = page;
      prev(page);
      closeDrawer();
      syncNav();
    };
  })();

  // ----------------------------------------------------------- sidebar + bottom nav
  function onNavClick(e) {
    var b = e.target.closest("[data-key]");
    if (!b) return;
    var key = b.dataset.key;
    if (key === "home") { showHome(); return; }
    if (key === "games") { showGames("all"); return; }
    if (b.dataset.go) {
      goToPage(b.dataset.go);
      if (b.dataset.wsub) { walletTab(b.dataset.wsub); syncNav(); }
      if (b.dataset.scroll) scrollTo(b.dataset.scroll);
    }
    // bottom-nav buttons that carry data-page are already handled by app.js's own listener
  }
  var side = $("side-nav"); if (side) side.addEventListener("click", onNavClick);
  var bnav = $("bottom-nav");
  if (bnav) bnav.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-key]"); if (!b) return;
    if (b.dataset.key === "home") showHome();
    else if (b.dataset.key === "games") showGames("all");
    else if (b.dataset.key === "wallet") { /* app.js opens it; remember which tab is showing */ setTimeout(syncNav, 0); }
  });

  // --------------------------------------------------------------------- header
  var menu = $("kdm-menu-btn"); if (menu) menu.addEventListener("click", toggleDrawer);
  var scrim = $("side-scrim"); if (scrim) scrim.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
  var back = $("kdm-back");
  if (back) back.addEventListener("click", function () { var nb = $("nav-back"); if (nb) nb.click(); else goToPage("lobby"); });
  var dep = $("top-deposit-btn");
  if (dep) dep.addEventListener("click", function () { goToPage("wallet"); walletTab("deposit"); syncNav(); });
  var pill = $("balance-pill");
  if (pill) pill.addEventListener("click", function () { goToPage("wallet"); walletTab("history"); syncNav(); });

  // home "Bet on Sports" banner -> existing Sports page
  document.addEventListener("click", function (e) {
    if (e.target.closest(".sports-promo")) goToPage("sports");
  });
  document.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("sports-promo")) { e.preventDefault(); goToPage("sports"); }
  });

  // hero + quick buttons that also want to scroll somewhere
  document.addEventListener("click", function (e) {
    var cta = e.target.closest(".hero-cta");
    if (cta) { showGames("all"); scrollTo("#game-grid"); return; }
    var q = e.target.closest(".quick-cabinet-btn[data-scroll]");
    if (q) scrollTo(q.dataset.scroll);
    var va = e.target.closest(".view-all-btn");
    if (va) { body.classList.add("kdm-games-view"); setCategory("all"); syncNav(); }
  });

  // user chip (name / id / avatar) + wallet total, kept in sync with the real balance element
  function fillUser() {
    var p = null;
    try { p = typeof lastProfile !== "undefined" ? lastProfile : null; } catch (e) { p = null; }
    if (!p) return false;
    var name = (p.first_name || p.username || "Player").trim();
    var n = $("kdm-user-name"), i = $("kdm-user-id"), a = $("kdm-avatar");
    if (n) n.textContent = name;
    if (i) i.textContent = "ID: " + p.user_id;
    if (a) {
      var photo = null;
      try { photo = window.Telegram.WebApp.initDataUnsafe.user.photo_url; } catch (e) { photo = null; }
      if (photo) { a.textContent = ""; var im = document.createElement("img"); im.alt = ""; im.src = photo; im.referrerPolicy = "no-referrer"; a.appendChild(im); }
      else a.textContent = name.charAt(0).toUpperCase();
    }
    return true;
  }
  function syncTotal() {
    var b = $("balance"), t = $("wallet-total");
    if (b && t) t.textContent = b.textContent;
  }
  var tries = 0;
  var userTimer = setInterval(function () { if (fillUser() || ++tries > 40) clearInterval(userTimer); }, 500);
  var bal = $("balance");
  if (bal && window.MutationObserver) new MutationObserver(syncTotal).observe(bal, { childList: true, characterData: true, subtree: true });
  syncTotal();

  // -------------------------------------------------------------------- wallet
  document.addEventListener("click", function (e) {
    var g = e.target.closest("[data-wsub-go]");
    if (g) { walletTab(g.dataset.wsubGo); syncNav(); return; }
    var sub = e.target.closest("#wallet-subtabs button");
    if (sub) { setTimeout(syncNav, 0); return; }
    var m = e.target.closest("#withdraw-methods button");
    if (m) {
      document.querySelectorAll("#withdraw-methods button").forEach(function (x) { x.classList.toggle("on", x === m); });
    }
    var c = e.target.closest(".wx-chips button");
    if (c) {
      var inp = $(c.parentNode.dataset.fill), v = c.dataset.v;
      if (v === "max") v = String(Math.floor(((window.__kdmBalance && window.__kdmBalance()) || 0) * 100) / 100);
      if (inp && Number(v) > 0) { inp.value = v; inp.dispatchEvent(new Event("input", { bubbles: true })); }
    }
  });

  // ---- withdraw: show available balance, remember last account
  function syncAvail() { var a = $("withdraw-avail"), b = $("balance"); if (a && b) a.textContent = b.textContent; }
  window.__kdmBalance = function () { var b = $("balance"); return b ? parseFloat(b.textContent) || 0 : 0; };
  if (bal && window.MutationObserver) new MutationObserver(syncAvail).observe(bal, { childList: true, characterData: true, subtree: true });
  syncAvail();
  try {
    var saved = JSON.parse(localStorage.getItem("kdm_wd_acc") || "null");
    if (saved) {
      if ($("withdraw-name")) $("withdraw-name").value = saved.name || "";
      if ($("withdraw-number")) $("withdraw-number").value = saved.number || "";
      var mb = document.querySelector('#withdraw-methods button[data-method="' + saved.method + '"]');
      if (mb) mb.classList.add("on");
    }
  } catch (_) {}

  // --------------------------------------------- language toggle lives in the sidebar
  function moveLang() {
    var l = $("lang-toggle"), f = $("side-foot");
    if (l && f && l.parentNode !== f) f.appendChild(l);
  }

  // ------------------------------------------------ quick-stake row on game pages
  function enhanceStakes(root) {
    (root || document).querySelectorAll("input.game-stake").forEach(function (inp) {
      if (inp.dataset.kdmQuick) return;
      inp.dataset.kdmQuick = "1";
      var row = document.createElement("div");
      row.className = "kdm-stake-quick";
      [["½", "half"], ["2×", "double"], ["Max", "max"]].forEach(function (d) {
        var b = document.createElement("button");
        b.type = "button"; b.textContent = d[0]; b.dataset.act = d[1];
        row.appendChild(b);
      });
      row.addEventListener("click", function (e) {
        var b = e.target.closest("button"); if (!b) return;
        var v = parseFloat(inp.value) || 0, min = parseFloat(inp.min) || 0.01, max = parseFloat(inp.max) || Infinity;
        var bal = parseFloat(($("balance") || {}).textContent) || 0;
        if (b.dataset.act === "half") v = v / 2;
        else if (b.dataset.act === "double") v = v * 2;
        else v = Math.floor(bal * 100) / 100;
        v = Math.max(min, Math.min(v, max));
        if (b.dataset.act === "max" && bal < min) v = min;
        inp.value = (Math.round(v * 100) / 100).toString();
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        inp.dispatchEvent(new Event("change", { bubbles: true }));
      });
      inp.insertAdjacentElement("afterend", row);
    });
  }

  // ------------------------------------------------------------------- boot
  var queued = false;
  function onMutate() {
    if (queued) return; queued = true;
    requestAnimationFrame(function () { queued = false; moveLang(); enhanceStakes(); });
  }
  function boot() {
    body.classList.remove("kdm-games-view");
    setCategory("popular");
    moveLang(); enhanceStakes(); syncNav();
    if (window.MutationObserver) new MutationObserver(onMutate).observe(document.body, { childList: true, subtree: true });
    // after wallet sub-tab / page changes made by other scripts
    var pages = $("pages");
    if (pages && window.MutationObserver) new MutationObserver(function () { syncNav(); }).observe(pages, { attributes: true, attributeFilter: ["class"], subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
