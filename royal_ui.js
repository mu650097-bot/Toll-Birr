/* ROYAL UI LAYER -- presentation + in-app announcements + profile stats + daily mission (points).
   Never touches a bet, payout, RNG or round. Talks only to:
     GET /api/announcements, POST /api/announcements/seen   (bell inbox)
     GET /api/royal/summary, POST /api/royal/mission/claim  (stats, level, daily mission points)
     GET /api/rewards/summary                               (already existed: level / wagered)
     admin: GET/POST /api/admin/app-announcements, DELETE /api/admin/app-announcements/<id>
   Loaded after kdm_ui.js / kdm_fix.js. Every block is wrapped so a failure never breaks the app. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var qs = function (s, r) { return (r || document).querySelector(s); };
  var qsa = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function api(path, opts) { return (typeof apiFetch === "function") ? apiFetch(path, opts || {}) : Promise.reject(new Error("api not ready")); }
  function buzz(t) { try { if (typeof haptic === "function") haptic(t); } catch (e) {} }
  function go(page) { try { goToPage(page); } catch (e) {} }
  function fmt(n) { return Number(n || 0).toLocaleString("en-US"); }

  var BADGES = {
    first_game: ["🎮", "First Game"], games_10: ["🔟", "10 Games"], games_100: ["💯", "100 Games"],
    first_win: ["🏆", "First Win"], wins_50: ["⭐", "50 Wins"], streak_3: ["🔥", "3-Day Streak"],
    streak_7: ["🌋", "7-Day Streak"], invite_1: ["🤝", "Invited a Friend"], deposit_1: ["💳", "First Deposit"], level_5: ["👑", "Level 5"]
  };

  // ------------------------------------------------------------ balance mirrors
  function syncBalance() {
    var b = $("balance"); if (!b) return;
    var v = (b.textContent || "0.00").trim();
    var r1 = $("royal-balance"); if (r1) r1.innerHTML = esc(v) + " <em>ETB</em>";
    var r2 = $("rr-balance"); if (r2) r2.textContent = v + " ETB";
  }
  (function () {
    var b = $("balance");
    if (b && window.MutationObserver) new MutationObserver(syncBalance).observe(b, { childList: true, characterData: true, subtree: true });
    syncBalance();
  })();

  // ------------------------------------------------------------ summary (stats / level / mission)
  var summary = null, rewards = null, busy = false, lastLoad = 0;
  function levelPct(rw) {
    if (!rw) return 0;
    var base = Number(rw.level_base || 0), nxt = rw.next_level_at;
    if (nxt == null) return 100;
    var span = Number(nxt) - base; if (span <= 0) return 100;
    return Math.max(0, Math.min(100, ((Number(rw.wagered || 0) - base) / span) * 100));
  }
  function paintSummary() {
    var s = summary, rw = rewards || summary;
    if (rw) {
      var lv = $("royal-level-line"), nm = $("royal-level-name"), br = $("royal-level-bar");
      if (lv) lv.textContent = "Level " + (rw.level || 1);
      if (nm) nm.textContent = rw.level_name || "Bronze";
      var pct = levelPct(rw);
      if (br) br.style.width = pct + "%";
      var vn = $("royal-vip-name"), vb = $("royal-vip-bar"), vx = $("royal-vip-next");
      if (vn) vn.textContent = "VIP " + String(rw.level_name || "Bronze").toUpperCase();
      if (vb) vb.style.width = pct + "%";
      if (vx) vx.textContent = rw.next_level_at != null ? (fmt(Math.max(0, Math.ceil(rw.next_level_at - rw.wagered))) + " ETB to next level") : "Top level reached 👑";
    }
    if (!s) return;
    var set = function (id, v) { var e = $(id); if (e) e.textContent = v; };
    var pc = $("profile-card");
    if (pc && rw) {
      var pill = $("royal-lvl-pill");
      if (!pill) { pill = document.createElement("span"); pill.id = "royal-lvl-pill"; pill.className = "royal-lvl-pill"; pc.appendChild(pill); }
      pill.textContent = "★ Level " + (rw.level || 1) + " · " + (rw.level_name || "Bronze");
    }
    set("rs-wins", fmt(s.wins)); set("rs-played", fmt(s.games_played)); set("rs-streak", fmt(s.streak));
    set("rr-points", fmt(s.points) + " Points");
    set("rr-badges", s.badges_earned + " / " + s.badges_total + " Badges");
    var bx = $("royal-badges");
    if (bx) bx.innerHTML = (s.badges || []).map(function (b) {
      var d = BADGES[b.key] || ["🏅", b.key];
      return '<span class="rb ' + (b.earned ? "on" : "off") + '"><i>' + d[0] + "</i>" + esc(d[1]) + "</span>";
    }).join("");
    var m = s.mission, box = $("royal-mission");
    if (m && box) {
      box.hidden = false;
      var txt = $("royal-mission-text"), bar = $("royal-mission-bar"), btn = $("royal-mission-btn");
      var pts = fmt(m.points) + " Bonus Points";
      if (m.claimed) txt.textContent = "Mission complete! Come back tomorrow 🎉";
      else if (m.claimable) txt.textContent = "Done! Claim your " + pts + ".";
      else txt.textContent = "Play " + m.target + " games today & get " + pts + "! (" + m.played + "/" + m.target + ")";
      if (bar) bar.style.width = Math.round((m.played / m.target) * 100) + "%";
      if (btn) {
        btn.disabled = !m.claimable; btn.textContent = m.claimed ? "Claimed ✓" : "Claim";
        btn.classList.toggle("ready", !!m.claimable);
      }
      box.classList.toggle("done", !!m.claimed);
    }
  }
  async function loadSummary(force) {
    if (busy) return;
    if (!force && Date.now() - lastLoad < 15000) return;
    busy = true;
    try {
      var r = await Promise.allSettled([api("/royal/summary"), api("/rewards/summary")]);
      if (r[0].status === "fulfilled") summary = r[0].value;
      if (r[1].status === "fulfilled") rewards = r[1].value;
      lastLoad = Date.now(); paintSummary();
    } catch (e) { /* keep the static layout */ }
    busy = false;
  }
  var mbtn = $("royal-mission-btn");
  if (mbtn) mbtn.addEventListener("click", async function () {
    if (mbtn.disabled) return;
    mbtn.disabled = true;
    try { var r = await api("/royal/mission/claim", { method: "POST", json: {} }); buzz("success"); if (summary) { summary.points = r.points; } await loadSummary(true); }
    catch (e) { buzz("error"); try { alert("❌ " + (e.message || e)); } catch (x) {} await loadSummary(true); }
  });

  // ------------------------------------------------------------ bell inbox
  var inbox = $("royal-inbox"), list = $("royal-inbox-list"), bell = $("top-notification-btn"), dot = $("royal-bell-count");
  var items = [], unread = 0;
  function setBadge(n) {
    unread = n;
    if (!dot) return;
    dot.hidden = !n; dot.textContent = n > 9 ? "9+" : String(n || "");
  }
  function when(ts) {
    if (!ts) return "";
    var d = new Date(String(ts).replace(" ", "T") + "Z"); if (isNaN(d)) return String(ts).slice(0, 16);
    var m = Math.floor((Date.now() - d.getTime()) / 60000);
    if (m < 1) return "now"; if (m < 60) return m + "m ago"; if (m < 1440) return Math.floor(m / 60) + "h ago";
    return Math.floor(m / 1440) + "d ago";
  }
  function targetFor(link) {
    link = String(link || "");
    if (!link) return null;
    if (link.indexOf("game:") === 0) return link.slice(5);
    return link;
  }
  function renderInbox() {
    if (!list) return;
    if (!items.length) { list.innerHTML = '<div class="ri-empty">ምንም ማስታወቂያ የለም</div>'; return; }
    list.innerHTML = items.map(function (a) {
      var t = targetFor(a.link_page);
      return '<div class="ri-item' + (a.pinned ? " pin" : "") + '">' +
        '<div class="ri-top"><b>' + (a.pinned ? "📌 " : "") + esc(a.title || "📢 ማስታወቂያ") + "</b><small>" + esc(when(a.created_at)) + "</small></div>" +
        '<p>' + esc(a.body).replace(/\n/g, "<br>") + "</p>" +
        (t ? '<button type="button" class="ri-go" data-target="' + esc(t) + '">▶️ አሁን ይጫወቱ</button>' : "") + "</div>";
    }).join("");
  }
  async function loadAnnouncements() {
    try {
      var r = await api("/announcements");
      items = r.items || []; setBadge(Number(r.unread || 0));
      if (inbox && !inbox.hidden) renderInbox();
    } catch (e) { /* silent */ }
  }
  function openInbox() {
    if (!inbox) return;
    renderInbox(); inbox.hidden = false; document.body.classList.add("royal-inbox-open");
    if (unread) { setBadge(0); api("/announcements/seen", { method: "POST", json: {} }).catch(function () {}); }
  }
  function closeInbox() { if (inbox) { inbox.hidden = true; document.body.classList.remove("royal-inbox-open"); } }
  // capture phase: app.js also binds this button (-> profile); the inbox replaces that.
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("#top-notification-btn")) { e.stopImmediatePropagation(); e.preventDefault(); openInbox(); }
  }, true);
  if (inbox) inbox.addEventListener("click", function (e) {
    if (e.target.closest("[data-close]")) { closeInbox(); return; }
    var g = e.target.closest(".ri-go");
    if (g) {
      closeInbox(); var t = g.dataset.target;
      if (t === "lobby") { var h = qs('#bottom-nav [data-key="home"]'); if (h) h.click(); else go("lobby"); }
      else go(t);
    }
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeInbox(); });

  // ------------------------------------------------------------ navigation shortcuts
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t.closest) return;
    var cat = t.closest("[data-royal-cat]");
    if (cat) {
      var g = qs('#bottom-nav [data-key="games"]'); if (g) g.click();
      var tab = qs('.cabinet-tab[data-cat="' + cat.dataset.royalCat + '"]');
      if (tab) setTimeout(function () { tab.click(); }, 30);
      return;
    }
    var qp = t.closest(".royal-cat[data-quick-page]");
    if (qp) { go(qp.dataset.quickPage); return; }
    if (t.closest("#royal-balance-card")) { go("wallet"); var d = qs('#wallet-subtabs button[data-wsub="deposit"]'); if (d) d.click(); return; }
    if (t.closest("#royal-level-card")) { go("profile"); setTimeout(function () { var v = $("royal-vip"); if (v) v.scrollIntoView({ behavior: "smooth", block: "center" }); }, 120); return; }
    if (t.closest("#nav-crown") || t.closest("#rr-rewards")) { go("profile"); setTimeout(function () { var v = $("royal-vip"); if (v) v.scrollIntoView({ behavior: "smooth", block: "center" }); }, 120); return; }
    if (t.closest("#top-gift-btn")) { go("wheel"); return; }
    if (t.closest("#rr-deposit")) { go("wallet"); var dd = qs('#wallet-subtabs button[data-wsub="deposit"]'); if (dd) dd.click(); return; }
    if (t.closest("#rr-ach-row")) { var bx = $("royal-badges"); if (bx) bx.hidden = !bx.hidden; return; }
    var mw = t.closest("[data-go-wallet]");
    if (mw) { go("wallet"); var w = qs('#wallet-subtabs button[data-wsub="' + mw.dataset.goWallet + '"]'); if (w) w.click(); return; }
    var mp = t.closest("[data-go-page]"); if (mp) { go(mp.dataset.goPage); return; }
    if (t.closest("#royal-support-go")) { var sb = qs(".support-box"); if (sb) sb.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  });

  // ------------------------------------------------------------ admin: in-app announcements
  async function loadAdminInapp() {
    var box = $("admin-inapp-list"); if (!box) return;
    try {
      var r = await api("/admin/app-announcements");
      box.innerHTML = (r.items || []).map(function (a) {
        return '<div class="admin-log-line"><b>#' + a.id + "</b> " + (a.pinned ? "📌 " : "") + esc(a.title || "") + " — " + esc(String(a.body).slice(0, 80)) +
          ' <button type="button" class="admin-mini-support" data-del="' + a.id + '">🗑</button></div>';
      }).join("") || "ምንም የለም";
    } catch (e) { box.textContent = "❌ " + (e.message || e); }
  }
  var send = $("admin-inapp-send");
  if (send) send.addEventListener("click", async function () {
    var body = ($("admin-inapp-body").value || "").trim(), st = $("admin-inapp-status");
    if (!body) { st.textContent = "መልዕክት ይጻፉ"; return; }
    send.disabled = true; st.textContent = "…";
    try {
      await api("/admin/app-announcements", { method: "POST", json: { title: $("admin-inapp-title").value.trim(), body: body, link_page: $("admin-inapp-link").value, pinned: $("admin-inapp-pin").checked } });
      $("admin-inapp-body").value = ""; $("admin-inapp-title").value = ""; st.textContent = "✅ ተለጥፏል"; buzz("success");
      loadAdminInapp(); loadAnnouncements();
    } catch (e) { st.textContent = "❌ " + (e.message || e); buzz("error"); }
    send.disabled = false;
  });
  var il = $("admin-inapp-list");
  if (il) il.addEventListener("click", async function (e) {
    var d = e.target.closest("[data-del]"); if (!d) return;
    try { await api("/admin/app-announcements/" + d.dataset.del, { method: "DELETE" }); loadAdminInapp(); loadAnnouncements(); } catch (x) { alert("❌ " + (x.message || x)); }
  });

  // ------------------------------------------------------------ hooks
  if (typeof goToPage === "function") {
    var prev = goToPage;
    goToPage = function (page) {
      prev(page);
      try {
        if (page === "lobby" || page === "profile") loadSummary(false);
        if (page === "admin") loadAdminInapp();
        document.body.classList.toggle("royal-profile", page === "profile");
        qsa("#bottom-nav .nav-crown").forEach(function (c) { c.classList.toggle("kdm-on", page === "profile" && false); });
      } catch (e) {}
    };
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { loadSummary(false); loadAnnouncements(); } });
  setInterval(function () { if (!document.hidden) loadAnnouncements(); }, 60000);
  // first load: wait until the Telegram auth/profile is ready (app.js fills lastProfile), then fetch once
  var tries = 0, t0 = setInterval(function () {
    var ready = false; try { ready = typeof lastProfile !== "undefined" && !!lastProfile; } catch (e) {}
    if (ready || ++tries > 40) { clearInterval(t0); if (ready) { loadSummary(true); loadAnnouncements(); } }
  }, 500);
})();
