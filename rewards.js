/* Level / Daily Challenge / hourly Mystery Box card on the Profile page + admin settings. Loaded after engagement.js
   (shares apiFetch, goToPage, escapeHtml, refreshBalance, loadAdminPanel). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var mbox = null, tick = null, busy = false;
  var pad = function (n) { return String(n).padStart(2, "0"); };
  function fmt(s) { return pad(Math.floor(s / 3600)) + ":" + pad(Math.floor((s % 3600) / 60)) + ":" + pad(s % 60); }

  function injectStyle() {
    if ($("rw-style")) return;
    var st = document.createElement("style"); st.id = "rw-style";
    st.textContent =
      ".rw-card{margin:12px 0;padding:14px;border-radius:16px;background:linear-gradient(160deg,#0f1b3d,#0a1230);border:1px solid rgba(96,165,250,.25)}" +
      ".rw-card h3{margin:0 0 8px;font-size:16px}.rw-bar{height:8px;border-radius:6px;background:rgba(255,255,255,.12);overflow:hidden;margin:8px 0}" +
      ".rw-bar>span{display:block;height:100%;background:linear-gradient(90deg,#3b82f6,#22d3ee);width:0}" +
      ".rw-row{display:flex;justify-content:space-between;gap:8px;align-items:center}.rw-btn{width:100%;margin-top:8px;padding:12px;border:0;border-radius:12px;font-weight:800;background:#2563eb;color:#fff}" +
      ".rw-btn[disabled]{opacity:.55}.rw-box{font-size:44px;text-align:center;margin:6px 0}.rw-win{color:#34d399;font-weight:800;text-align:center}.rw-small{opacity:.75;font-size:12px}" +
      ".rw-shake{animation:rwshake .5s infinite}@keyframes rwshake{0%,100%{transform:rotate(0)}25%{transform:rotate(-8deg)}75%{transform:rotate(8deg)}}" +
      ".rw-ready .rw-box{animation:rwpulse 1.4s ease-in-out infinite}@keyframes rwpulse{0%,100%{transform:scale(1)}50%{transform:scale(1.12)}}" +
      ".rw-lobby{margin:10px 12px}.rw-lobby .rw-box{font-size:34px;margin:2px 0}.rw-lobby h3{font-size:15px}";
    document.head.appendChild(st);
  }

  function inject() {
    if ($("rewards-card")) return;
    var anchor = $("profile-card"); if (!anchor) return;
    injectStyle();
    var w = document.createElement("div"); w.id = "rewards-card";
    w.innerHTML =
      '<div class="rw-card"><h3>🏅 የእኔ Level</h3><div class="rw-row"><b id="rw-level">Level 1</b><span id="rw-wag" class="rw-small"></span></div>' +
      '<div class="rw-bar"><span id="rw-lvbar"></span></div><div class="rw-small" id="rw-next"></div></div>' +
      '<div class="rw-card"><h3>🎯 የዛሬ Challenge</h3><div id="rw-inv-text">ሰዎችን ጋብዙ -- ለእያንዳንዱ 1 ብር ቦነስ</div>' +
      '<div class="rw-bar"><span id="rw-invbar"></span></div><div class="rw-row"><b id="rw-inv">0/10</b><span class="rw-small" id="rw-earn"></span></div>' +
      '<button class="rw-btn" id="rw-invite-btn" type="button">🎁 ሰው ጋብዝ</button></div>' +
      boxCardHTML();
    anchor.insertAdjacentElement("afterend", w);
    $("rw-invite-btn").addEventListener("click", function () { goToPage("invite"); });
    w.querySelector(".rw-open").addEventListener("click", openBox);
  }

  function boxCardHTML() {
    return '<div class="rw-card rw-mbox"><h3>📦 Mystery Box <span class="rw-small rw-mb-sub"></span></h3><div class="rw-box">🎁</div>' +
      '<div class="rw-win rw-res"></div><div class="rw-small rw-mb-note" style="text-align:center"></div>' +
      '<button class="rw-btn rw-open" type="button" disabled>ክፈት</button></div>';
  }

  // Compact Mystery Box on the Home (lobby) page, under "Recent Big Wins": players check it there; same state as the Profile card.
  function injectLobby() {
    if ($("rewards-lobby")) return;
    var anchor = $("wins-banner"); if (!anchor) return;
    injectStyle();
    var d = document.createElement("div"); d.id = "rewards-lobby"; d.className = "rw-lobby"; d.innerHTML = boxCardHTML();
    anchor.insertAdjacentElement("afterend", d);
    d.querySelector(".rw-open").addEventListener("click", openBox);
  }

  async function load() {
    injectLobby(); inject(); if (!$("rewards-card")) { loadBox(); return; }
    try {
      var s = await apiFetch("/rewards/summary");
      $("rw-level").textContent = "Level " + s.level + " · " + s.level_name;
      $("rw-wag").textContent = "ተወራርደዋል: " + s.wagered.toFixed(0) + " ብር";
      var pct = s.next_level_at ? Math.min(100, (s.wagered - s.level_base) / (s.next_level_at - s.level_base) * 100) : 100;
      $("rw-lvbar").style.width = pct + "%";
      $("rw-next").textContent = s.next_level_at ? "ለቀጣይ Level " + Math.max(0, s.next_level_at - s.wagered).toFixed(0) + " ብር ይቀራል" : "🏆 ከፍተኛ Level ላይ ደርሰዋል!";
      $("rw-inv").textContent = Math.min(s.invited, s.invite_target) + "/" + s.invite_target;
      $("rw-invbar").style.width = Math.min(100, s.invited / s.invite_target * 100) + "%";
      $("rw-inv-text").textContent = "ለእያንዳንዱ ለጋበዙት ሰው " + s.bonus_per_invite + " ብር ቦነስ (" + s.invite_target + " ሰው = " + (s.invite_target * s.bonus_per_invite) + " ብር)" + (s.bonus_after_deposit ? " — ጓደኛዎ የመጀመሪያ ገንዘብ ሲያስገባ ይከፈላል" : "");
      $("rw-earn").textContent = "ያገኙት ቦነስ: " + Number(s.bonus_earned).toFixed(2) + " ብር";
    } catch (e) { /* card keeps defaults */ }
    loadBox();
  }

  async function loadBox() {
    clearInterval(tick);
    try { mbox = await apiFetch("/mbox/status"); } catch (e) { return; }
    draw();
    tick = setInterval(function () {
      if (!mbox || document.hidden) return;
      if (mbox.mode === "admin") {
        if (mbox.released && mbox.release_seconds_left > 0) { mbox.release_seconds_left--; if (mbox.release_seconds_left === 0) { loadBox(); return; } draw(); }
      } else if (mbox.seconds_left > 0) { mbox.seconds_left--; if (mbox.seconds_left === 0) mbox.can_open = mbox.enabled; draw(); }
    }, 1000);
  }

  function each(sel, fn) { Array.prototype.forEach.call(document.querySelectorAll(sel), fn); }

  function draw() {
    if (!mbox) return;
    var label, note = "", dis = true, ready = false, sub = mbox.mode === "admin" ? "(አድሚን ሲለቅ)" : "(በየ ሰዓቱ ነፃ)";
    if (mbox.mode === "admin") {
      if (mbox.released && mbox.can_open) { label = "🎁 ክፈት"; dis = busy; ready = true; note = "ሳጥኑ ተለቋል! ቀሪ ጊዜ " + fmt(mbox.release_seconds_left); }
      else if (mbox.released && mbox.opened_this_release) { label = "✅ ተከፍቷል"; note = "ቀጣዩን ልቀት ይጠብቁ -- ቀሪ " + fmt(mbox.release_seconds_left); }
      else { label = "🔒 አድሚኑ ሲለቅ ይከፈታል"; note = "ሳጥኑ ሲለቀቅ እዚህ ይከፈታል"; }
    } else if (!mbox.enabled) { label = "በቅርብ ቀን ይከፈታል"; }
    else if (mbox.seconds_left > 0) { label = "⏳ " + fmt(mbox.seconds_left); note = "ቀጣዩ ሳጥን ሲደርስ ይከፈታል"; }
    else { label = "🎁 ክፈት"; dis = busy; ready = true; note = "ሳጥኑ ዝግጁ ነው!"; }
    each(".rw-mbox", function (card) {
      var btn = card.querySelector(".rw-open"); btn.disabled = dis; btn.textContent = label;
      card.querySelector(".rw-mb-note").textContent = note; card.querySelector(".rw-mb-sub").textContent = sub;
      card.classList.toggle("rw-ready", ready);
    });
  }

  async function openBox() {
    if (busy || !mbox || !mbox.can_open) return;
    busy = true; draw(); each(".rw-box", function (e) { e.classList.add("rw-shake"); }); each(".rw-res", function (e) { e.textContent = ""; });
    var txt, icon;
    try {
      var r = await apiFetch("/mbox/open", { method: "POST", json: {} });
      await new Promise(function (res) { setTimeout(res, 700); });
      icon = r.prize > 0 ? "🪙" : "💨";
      txt = r.prize > 0 ? "🎉 " + r.prize.toFixed(2) + " ብር ቦነስ አሸነፉ! (ለመጫወት)" : "😅 በዚህ ጊዜ ምንም የለም -- " + (mbox.mode === "admin" ? "በሚቀጥለው ልቀት ይሞክሩ" : "በሚቀጥለው ሰዓት ይሞክሩ");
      mbox.can_open = false; mbox.opened_this_release = true; mbox.seconds_left = r.seconds_left;
      if (r.prize > 0) { try { celebrateWin(); } catch (e) {} try { refreshBalance(); } catch (e) {} }
    } catch (e) {
      txt = "❌ " + e.message; icon = "🎁";
      if (e.body && e.body.seconds_left != null) mbox.seconds_left = e.body.seconds_left;
      loadBox();
    }
    each(".rw-box", function (el) { el.classList.remove("rw-shake"); if (icon !== "🎁") el.textContent = icon; });
    each(".rw-res", function (el) { el.textContent = txt; });
    busy = false; draw();
  }

  // ---------------------------------------------------------------- admin
  function injectAdmin() {
    if ($("admin-mbox")) return;
    var host = $("admin-engagement") || document.querySelector("#page-admin .admin-tabs"); if (!host) return;
    var d = document.createElement("div"); d.id = "admin-mbox"; d.className = "admin-bonus-box";
    d.innerHTML = '<h3>📦 Mystery Box</h3><p class="admin-note">«🚀 አሁን ልቀቅ» ሲጫኑ ሁሉም ተጫዋች ለተወሰነ ደቂቃ አንድ ጊዜ ሳጥኑን መክፈት ይችላል። ሽልማቶች = <code>መጠን:ዕድል</code> በኮማ ለምሳሌ <code>0:40,1:30,2:15,5:10,10:4,20:1</code>። ሽልማቱ ለመጫወት ብቻ ቦነስ ይሆናል። Daily budget ሲያልቅ ሁሉም 0 ይሆናል።</p><div id="admin-mbox-form"></div><small id="admin-mbox-status"></small>';
    if ($("admin-engagement")) $("admin-engagement").appendChild(d); else host.insertAdjacentElement("beforebegin", d);
  }

  async function loadAdmin() {
    injectAdmin(); var form = $("admin-mbox-form"); if (!form) return;
    try {
      var r = await apiFetch("/admin/mbox"), s = r.settings, ar = r.active_release;
      var prizes = (s.prizes || []).map(function (p) { return p[0] + ":" + p[1]; }).join(",");
      form.innerHTML =
        '<div class="rw-card" style="margin:6px 0">' + (ar
          ? '<b>🟢 ተለቋል</b> -- ቀሪ ' + Math.ceil(ar.seconds_left / 60) + ' ደቂቃ · ' + ar.opens + ' ሰው ከፍቷል · ' + Number(ar.paid).toFixed(2) + ' ብር<br><button id="mb-close" class="admin-save-game">⏹ ልቀቱን ዝጋ</button>'
          : '<b>🔒 አልተለቀቀም</b>') +
        '<br>ክፍት የሚሆንበት <input type="number" id="mb-rel-min" min="1" max="1440" value="60" style="width:70px"> ደቂቃ ' +
        '<button id="mb-release" class="admin-save-game">🚀 አሁን ልቀቅ</button></div>' +
        '<label>ሁነታ <select id="mb-mode"><option value="admin"' + (s.mode !== "hourly" ? " selected" : "") + '>አድሚን ሲለቅ ብቻ</option><option value="hourly"' + (s.mode === "hourly" ? " selected" : "") + '>በየ ሰዓቱ በራስ</option></select></label><br>' +
        '<label><input type="checkbox" id="mb-enabled"' + (s.enabled ? " checked" : "") + "> Enabled</label><br>" +
        'በየ <input type="number" id="mb-cd" min="1" max="1440" value="' + s.cooldown_min + '" style="width:70px"> ደቂቃ አንድ ጊዜ (በየ ሰዓቱ ሁነታ ብቻ)<br>' +
        'Daily budget (ብር) <input type="number" id="mb-budget" min="0" value="' + s.daily_budget + '" style="width:90px"><br>' +
        'Prizes <input id="mb-prizes" value="' + escapeHtml(prizes) + '" style="width:100%"><br>' +
        '<button id="mb-save" class="admin-save-game">💾 Save</button><div class="admin-note">ዛሬ: ' + r.today_opens + " ጊዜ ተከፍቷል · " + Number(r.today_paid).toFixed(2) + " ብር ተሰጥቷል</div>";
      var st = $("admin-mbox-status");
      $("mb-release").addEventListener("click", async function () {
        if (!confirm("ሳጥኑን አሁን ለሁሉም ተጫዋች ይለቀቅ?")) return;
        try { await apiFetch("/admin/mbox/release", { method: "POST", json: { minutes: +$("mb-rel-min").value } }); st.textContent = "✅ ተለቋል"; loadAdmin(); loadBox(); }
        catch (e) { st.textContent = "❌ " + e.message; }
      });
      if ($("mb-close")) $("mb-close").addEventListener("click", async function () {
        try { await apiFetch("/admin/mbox/close", { method: "POST", json: {} }); st.textContent = "✅ ተዘግቷል"; loadAdmin(); loadBox(); }
        catch (e) { st.textContent = "❌ " + e.message; }
      });
      $("mb-save").addEventListener("click", async function () {
        var pz = $("mb-prizes").value.split(",").map(function (x) { return x.trim().split(":").map(Number); })
          .filter(function (p) { return p.length === 2 && isFinite(p[0]) && isFinite(p[1]); });
        try {
          await apiFetch("/admin/mbox", { method: "POST", json: { enabled: $("mb-enabled").checked, mode: $("mb-mode").value, cooldown_min: +$("mb-cd").value, daily_budget: +$("mb-budget").value, prizes: pz } });
          st.textContent = "✅ Saved"; loadAdmin(); loadBox();
        } catch (e) { st.textContent = "❌ " + e.message; }
      });
    } catch (e) { form.textContent = "❌ " + e.message; }
  }

  // players "check" the box: refresh on Home/Profile and every 20 s while the app is visible, so a fresh admin release shows up fast
  try { var rawGo = goToPage; goToPage = function (p) { var r = rawGo.apply(this, arguments); if (p === "lobby" || p === "profile") setTimeout(function () { injectLobby(); loadBox(); }, 0); return r; }; } catch (e) {}
  setInterval(function () { if (!document.hidden && mbox && !busy) loadBox(); }, 20000);
  function boot() { injectLobby(); loadBox(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else setTimeout(boot, 800);

  var rawProfile = loadProfile;
  loadProfile = async function () { var p = await rawProfile(); load(); return p; };
  var rawAdmin = loadAdminPanel;
  loadAdminPanel = async function () { await rawAdmin(); loadAdmin(); };
})();
