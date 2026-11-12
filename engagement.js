/* ENGAGEMENT LAYER: home banner carousel, Back/Close bar, Shamo daily mystery boxes, admin tools.
   Loaded after app.js (shares its globals: tg, apiFetch, goToPage, API_BASE, escapeHtml, refreshBalance). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var IMG_BASE = String(API_BASE).replace(/\/api\/?$/, "");

  // ------------------------------------------------------------ Back / Close
  var pageStack = [], currentPage = "lobby";
  var rawGoToPage = goToPage;

  function syncNavBar() {
    var bar = $("nav-bar"); if (!bar) return;
    var onLobby = currentPage === "lobby";
    $("nav-back").style.visibility = onLobby ? "hidden" : "visible";
    try {
      if (onLobby) tg.BackButton.hide(); else tg.BackButton.show();
    } catch (e) { /* old Telegram client */ }
  }

  goToPage = function (page) {
    if (page !== currentPage) {
      if (pageStack.length && pageStack[pageStack.length - 1] === page) pageStack.pop(); // acts as "back"
      else { pageStack.push(currentPage); if (pageStack.length > 20) pageStack.shift(); }
    }
    currentPage = page;
    rawGoToPage(page);
    syncNavBar();
    if (page === "shamo") loadShamo();
    if (page === "lobby") startCarousel(); else stopCarousel();
    window.scrollTo(0, 0);
  };

  function goBack() { goToPage(pageStack.length ? pageStack[pageStack.length - 1] : "lobby"); }

  function buildNavBar() {
    if ($("nav-bar")) return;
    var bar = document.createElement("div");
    bar.id = "nav-bar";
    bar.innerHTML = '<button id="nav-back" type="button">← Back</button><button id="nav-close" type="button">✕ Close</button>';
    var top = $("topbar");
    if (top) top.insertAdjacentElement("afterend", bar);
    $("nav-back").addEventListener("click", goBack);
    $("nav-close").addEventListener("click", function () { try { tg.close(); } catch (e) {} });
    try { tg.BackButton.onClick(goBack); } catch (e) {}
    syncNavBar();
  }

  // ---------------------------------------------------------------- carousel
  var slides = [], slideIdx = 0, slideTimer = null, startX = null;

  function showSlide(i) {
    var track = $("hb-track"); if (!track || !slides.length) return;
    slideIdx = (i + slides.length) % slides.length;
    track.style.transform = "translateX(-" + (slideIdx * 100) + "%)";
    document.querySelectorAll("#hb-dots i").forEach(function (d, k) { d.classList.toggle("on", k === slideIdx); });
  }
  function scheduleNext() {
    clearTimeout(slideTimer);
    if (slides.length < 2) return;
    var secs = Math.max(2, Math.min(30, (slides[slideIdx] && slides[slideIdx].seconds) || 4));
    slideTimer = setTimeout(function () {
      if (!document.hidden) showSlide(slideIdx + 1);
      scheduleNext();
    }, secs * 1000);
  }
  function startCarousel() { if (slides.length) scheduleNext(); }
  function stopCarousel() { clearTimeout(slideTimer); }

  async function loadBanners() {
    var host = $("home-banners"); if (!host) return;
    var items = [];
    try { items = (await apiFetch("/banners")).items || []; } catch (e) { /* keep static hero */ }
    slides = items.slice(0, 5);
    var hero = document.querySelector(".royal-hero");
    if (!slides.length) { host.style.display = "none"; if (hero) hero.style.display = ""; return; }
    if (hero) hero.style.display = "none";
    host.style.display = "";
    host.innerHTML =
      '<div id="hb-viewport"><div id="hb-track">' +
      slides.map(function (s) {
        return '<div class="hb-slide" data-link="' + escapeHtml(s.link_page || "") + '"><img alt="" loading="lazy" src="' +
          escapeHtml(IMG_BASE + s.image) + '"></div>';
      }).join("") + '</div></div><div id="hb-dots">' + slides.map(function () { return "<i></i>"; }).join("") + "</div>";
    var vp = $("hb-viewport");
    vp.addEventListener("click", function (e) {
      var sl = e.target.closest(".hb-slide"); var link = sl && sl.dataset.link;
      if (link && $("page-" + link)) goToPage(link);
    });
    vp.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; stopCarousel(); }, { passive: true });
    vp.addEventListener("touchend", function (e) {
      if (startX !== null) {
        var dx = e.changedTouches[0].clientX - startX;
        if (Math.abs(dx) > 40) showSlide(slideIdx + (dx < 0 ? 1 : -1));
      }
      startX = null; scheduleNext();
    });
    showSlide(0); startCarousel();
  }

  // ------------------------------------------------------------------- Shamo
  var shamo = null, shamoTick = null, shamoBusy = false;
  function pad(n) { return String(n).padStart(2, "0"); }

  function injectShamoPage() {
    if ($("page-shamo")) return;
    var sec = document.createElement("section");
    sec.id = "page-shamo"; sec.className = "page";
    sec.innerHTML =
      '<div class="shamo-hero"><div class="shamo-coin">🪙</div><h2 class="shamo-title">SHAMO</h2>' +
      '<div class="shamo-sub" id="shamo-sub">EVERY DAY AT 9:00 PM</div></div>' +
      '<div class="shamo-card"><div class="shamo-card-title" id="shamo-card-title">Next Shamo starts in</div>' +
      '<div class="shamo-clock" id="shamo-clock"></div><div class="shamo-bar"><span id="shamo-bar-fill"></span></div></div>' +
      '<div class="shamo-card"><div class="shamo-card-head"><div><b>Pick a Mystery Box</b>' +
      '<small id="shamo-hint">Once Shamo opens, tap a gift box</small></div><span class="shamo-pill" id="shamo-pill"></span></div>' +
      '<div id="shamo-grid"></div><div id="shamo-result"></div></div>';
    $("pages").appendChild(sec);
  }

  function renderShamo() {
    if (!shamo) return;
    $("shamo-sub").textContent = "EVERY DAY AT " + shamo.open_label.toUpperCase();
    $("shamo-pill").textContent = shamo.open_label;
    var grid = $("shamo-grid");
    if (!grid.dataset.n || grid.dataset.n !== String(shamo.boxes) || shamo.picked) {
      grid.dataset.n = shamo.boxes;
      grid.innerHTML = "";
      for (var i = 0; i < shamo.boxes; i++) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "shamo-box"; b.dataset.i = i; b.textContent = "🎁";
        if (shamo.picked && shamo.picked.box === i) { b.classList.add("opened"); b.textContent = shamo.picked.prize > 0 ? "🪙" : "💨"; }
        b.addEventListener("click", function (ev) { pickBox(Number(ev.currentTarget.dataset.i)); });
        grid.appendChild(b);
      }
    }
    var open = shamo.enabled && shamo.is_open && !shamo.picked;
    grid.querySelectorAll(".shamo-box").forEach(function (b) { b.disabled = !open || shamoBusy; b.classList.toggle("ready", open); });
    var res = $("shamo-result");
    if (!shamo.enabled) {
      res.textContent = "Shamo is coming soon. Stay tuned!";
    } else if (shamo.picked) {
      res.textContent = shamo.picked.prize > 0 ? "🎉 You won " + shamo.picked.prize.toFixed(2) + " ብር!" : "😅 No prize this time — try again tomorrow!";
      res.className = shamo.picked.prize > 0 ? "win" : "";
    } else { res.textContent = ""; }
    $("shamo-hint").textContent = shamo.picked ? "You already picked today" : (open ? "Shamo is OPEN — pick now!" : "Once Shamo opens, tap a gift box");
    $("shamo-card-title").textContent = shamo.is_open ? "Shamo closes in" : "Next Shamo starts in";
    drawClock();
  }

  function drawClock() {
    if (!shamo) return;
    var s = shamo.is_open ? shamo.seconds_to_close : shamo.seconds_to_open;
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    $("shamo-clock").innerHTML =
      "<div><b>" + pad(h) + "</b><small>HOURS</small></div><i>:</i><div><b>" + pad(m) + "</b><small>MINUTES</small></div><i>:</i><div><b>" + pad(x) + "</b><small>SECONDS</small></div>";
    var total = shamo.is_open ? Math.max(shamo.window_total || 600, s) : shamo.cycle_seconds;
    var pct = shamo.is_open ? (s / total) : (1 - s / total);
    $("shamo-bar-fill").style.width = Math.max(0, Math.min(100, pct * 100)) + "%";
  }

  async function loadShamo() {
    injectShamoPage();
    clearInterval(shamoTick);
    try { shamo = await apiFetch("/shamo/status"); } catch (e) { $("shamo-result").textContent = "❌ " + e.message; return; }
    shamo.window_total = shamo.is_open ? shamo.seconds_to_close : 0;
    renderShamo();
    shamoTick = setInterval(function () {
      if (currentPage !== "shamo") { clearInterval(shamoTick); return; }
      var key = shamo.is_open ? "seconds_to_close" : "seconds_to_open";
      if (shamo[key] > 0) { shamo[key]--; drawClock(); }
      else { loadShamo(); } // state flips (opens / closes) -> ask the server again
    }, 1000);
  }

  async function pickBox(i) {
    if (shamoBusy || !shamo || !shamo.is_open || shamo.picked) return;
    shamoBusy = true; renderShamo();
    var btn = $("shamo-grid").children[i]; if (btn) btn.classList.add("shaking");
    try {
      var r = await apiFetch("/shamo/pick", { method: "POST", json: { box: i } });
      shamo.picked = { box: r.box, prize: r.prize };
      shamoBusy = false; renderShamo();
      if (r.prize > 0) { try { celebrateWin(); } catch (e) {} try { refreshBalance(); } catch (e) {} }
    } catch (e) {
      shamoBusy = false;
      if (btn) btn.classList.remove("shaking");
      $("shamo-result").textContent = "❌ " + e.message;
      loadShamo();
    }
  }

  // ------------------------------------------------------------------- admin
  function injectAdminBoxes() {
    if ($("admin-engagement")) return;
    var tabs = document.querySelector("#page-admin .admin-tabs"); if (!tabs) return;
    var box = document.createElement("div");
    box.id = "admin-engagement";
    box.innerHTML =
      '<div class="admin-bonus-box"><h3>🖼 Home Banners (max 5)</h3>' +
      '<p class="admin-note">ፎቶ ያስገቡ — ከላይ ወደ ጎን እየተላለፈ ይታያል። Bot ላይ Photo ማስታወቂያ ሲልኩም በራሱ እዚህ ይገባል።</p>' +
      '<div id="admin-banner-list"></div>' +
      '<input type="file" id="admin-banner-file" accept="image/jpeg,image/png,image/webp">' +
      '<label class="admin-note">Seconds: <input type="number" id="admin-banner-secs" value="4" min="2" max="30" style="width:64px"></label> ' +
      '<button id="admin-banner-add" class="admin-save-game">➕ Add banner</button><small id="admin-banner-status"></small></div>' +
      '<div class="admin-bonus-box"><h3>🪙 Shamo (daily mystery box)</h3>' +
      '<p class="admin-note">Prizes = <code>amount:weight</code> በኮማ ለምሳሌ <code>0:50,5:25,10:15,20:8,50:2</code>። Daily budget ሲያልቅ ሁሉም 0 ይሆናል።</p>' +
      '<div id="admin-shamo-form"></div><small id="admin-shamo-status"></small></div>';
    tabs.insertAdjacentElement("beforebegin", box);
    $("admin-banner-add").addEventListener("click", addBanner);
  }

  async function loadAdminBanners() {
    var list = $("admin-banner-list"); if (!list) return;
    try {
      var r = await apiFetch("/admin/banners");
      list.innerHTML = (r.items || []).map(function (b) {
        return '<div class="admin-banner-row"><img src="' + escapeHtml(IMG_BASE + b.image) + '" alt=""><span>#' + b.id + " · " + b.seconds +
          's</span><button data-del="' + b.id + '">🗑</button></div>';
      }).join("") || '<div class="empty-state">No banners yet.</div>';
      list.querySelectorAll("button[data-del]").forEach(function (btn) {
        btn.addEventListener("click", async function () {
          if (!confirm("Delete this banner?")) return;
          try { await apiFetch("/admin/banners/" + btn.dataset.del, { method: "DELETE" }); loadAdminBanners(); loadBanners(); }
          catch (e) { alert(e.message); }
        });
      });
    } catch (e) { list.textContent = "❌ " + e.message; }
  }

  async function addBanner() {
    var f = $("admin-banner-file").files[0], st = $("admin-banner-status");
    if (!f) { st.textContent = "ፎቶ ይምረጡ"; return; }
    var fd = new FormData(); fd.append("photo", f); fd.append("seconds", $("admin-banner-secs").value || "4");
    try {
      await apiFetch("/admin/banners", { method: "POST", formData: fd });
      st.textContent = "✅ Added"; $("admin-banner-file").value = "";
      loadAdminBanners(); loadBanners();
    } catch (e) { st.textContent = "❌ " + e.message; }
  }

  async function loadAdminShamo() {
    var form = $("admin-shamo-form"); if (!form) return;
    try {
      var r = await apiFetch("/admin/shamo"), s = r.settings;
      var prizes = (s.prizes || []).map(function (p) { return p[0] + ":" + p[1]; }).join(",");
      form.innerHTML =
        '<label><input type="checkbox" id="sh-enabled"' + (s.enabled ? " checked" : "") + "> Enabled</label><br>" +
        'Opens at <input type="number" id="sh-hour" min="0" max="23" value="' + s.open_hour + '" style="width:54px"> : ' +
        '<input type="number" id="sh-min" min="0" max="59" value="' + s.open_minute + '" style="width:54px"> (Addis time)<br>' +
        'Open for <input type="number" id="sh-window" min="1" max="240" value="' + s.window_minutes + '" style="width:64px"> min · Boxes ' +
        '<input type="number" id="sh-boxes" min="2" max="20" value="' + s.boxes + '" style="width:54px"><br>' +
        'Daily budget (ብር) <input type="number" id="sh-budget" min="0" value="' + s.daily_budget + '" style="width:90px"><br>' +
        '<label><input type="checkbox" id="sh-dep"' + (s.require_deposit ? " checked" : "") + "> Require an approved deposit</label><br>" +
        'Prizes <input id="sh-prizes" value="' + escapeHtml(prizes) + '" style="width:100%"><br>' +
        '<button id="sh-save" class="admin-save-game">💾 Save</button>' +
        '<div class="admin-note">Today: ' + r.today_picks + " picks · " + Number(r.today_paid).toFixed(2) + " ብር paid</div>";
      $("sh-save").addEventListener("click", saveShamo);
    } catch (e) { form.textContent = "❌ " + e.message; }
  }

  async function saveShamo() {
    var st = $("admin-shamo-status");
    var prizes = $("sh-prizes").value.split(",").map(function (x) { return x.trim().split(":").map(Number); })
      .filter(function (p) { return p.length === 2 && isFinite(p[0]) && isFinite(p[1]); });
    try {
      await apiFetch("/admin/shamo", { method: "POST", json: {
        enabled: $("sh-enabled").checked, open_hour: +$("sh-hour").value, open_minute: +$("sh-min").value,
        window_minutes: +$("sh-window").value, boxes: +$("sh-boxes").value, daily_budget: +$("sh-budget").value,
        require_deposit: $("sh-dep").checked, prizes: prizes } });
      st.textContent = "✅ Saved"; loadAdminShamo();
    } catch (e) { st.textContent = "❌ " + e.message; }
  }

  var rawLoadAdminPanel = loadAdminPanel;
  loadAdminPanel = async function () {
    injectAdminBoxes();
    await rawLoadAdminPanel();
    loadAdminBanners(); loadAdminShamo();
  };

  // -------------------------------------------------------------------- boot
  function boot() {
    buildNavBar(); injectShamoPage(); loadBanners();
    document.addEventListener("visibilitychange", function () { if (!document.hidden && currentPage === "lobby") scheduleNext(); });
  }
  // #content is shown only after login; boot once the topbar exists in the DOM (it always does) and
  // refresh banners each time the lobby is shown.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
