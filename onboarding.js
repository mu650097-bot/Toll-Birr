/* ONBOARDING LAYER (loaded after engagement.js; shares app.js globals such as goToPage).
   1. Amharic / English toggle   2. "Start in 3 steps" card   3. Easy deposit (Telebirr/CBE first, quick amounts)
   5. Welcome banner on the first screen.
   No amounts or bonuses are invented here: the banner only points people to Deposit. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var LANG_KEY = "kdm_lang", DISMISS_BANNER = "kdm_wb_dismissed", DISMISS_STEPS = "kdm_steps_dismissed";

  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } }

  // ------------------------------------------------------------------ i18n
  // [Amharic, English]. Add a pair here to translate any other fixed UI text.
  // Matching is on the whole text of one element, so each Amharic string must be unique.
  var PAIRS = [
    // bottom nav
    ["ስፖርት", "Sports"], ["ማስተዋወቂያ", "Promotions"], ["ገንዘብ አስገባ", "Deposit"], ["ጋብዝ", "Invite"], ["መገለጫ", "Profile"],
    // lobby tabs + headings
    ["ሎቢ", "Lobby"], ["ተወዳጅ", "Hot"], ["ታዋቂ", "Popular"], ["አዲስ", "New"],
    ["🔥 ተወዳጅ", "🔥 Hot"], ["ሁሉንም ›", "View All ›"], ["ℹ️ በቻት በኩል ብቻ", "ℹ️ Chat only"],
    ["⌕  ጨዋታ ፈልግ", "⌕  Find a Game"],
    // header / hero / quick buttons
    ["ይጫወቱ · ያሸንፉ · ይደሰቱ", "Play · Win · Enjoy"],
    ["ተለይቶ አሸንፉ!", "Play and win!"], ["ይጫወቱ · ያሸንፉ · ይደነቁ", "Play · Win · Be a legend"],
    ["ዕድለኛ ጎማ", "Lucky Spin"], ["ኩፖን", "Coupon"], ["ቅናሽ", "Promo"], ["ድጋፍ", "Support"],
    // wins ticker
    ["የቅርብ ጊዜ ትልልቅ ድሎች", "RECENT BIG WINS"], ["ቀጥታ ድሎች", "Live Wins"],
    // nav bar
    ["← ተመለስ", "← Back"], ["✕ ዝጋ", "✕ Close"], ["← ሎቢ", "← Lobby"],
    // wallet
    ["💰 ቦርሳ", "💰 Wallet"], ["💳 ገንዘብ አስገባ", "💳 Deposit"], ["💸 ገንዘብ አውጣ", "💸 Withdraw"], ["📜 ታሪክ", "📜 History"],
    ["የከፈሉት መጠን (ብር)", "Amount paid (ETB)"], ["የክፍያ Screenshot", "Payment screenshot"], ["✅ ላክ", "✅ Send"],
    // welcome + age gate
    ["🚀 ጀምር", "🚀 Start"], ["እንኳን ወደ Mini App በደህና መጡ! ይጫወቱ፣ ይወራረዱ፣ ያሸንፉ።", "Welcome to the Mini App! Play, bet and win."],
    ["የእድሜ ማረጋገጫ", "Age verification"],
    ["ይህ መተግበሪያ እውነተኛ ገንዘብ የያዘ የውርርድ/ጨዋታ አገልግሎት ነው። ለመቀጠል እድሜዎ 18 እና ከዚያ በላይ መሆኑን ማረጋገጥ አለብዎት።",
     "This app is a betting/gaming service that uses real money. To continue you must confirm you are 18 or older."],
    ["✅ አዎ፣ እድሜዬ 18+ ነው", "✅ Yes, I am 18+"], ["❌ አይደለም / አልፈልግም", "❌ No / I don't want to"],
    // this file's own UI
    ["በ3 ደረጃ ጀምር", "Start in 3 steps"], ["ጨዋታ ምረጥ", "Pick a game"], ["ተጫወት", "Play"],
    ["🎁 እንኳን ደህና መጡ! ቦነስ እና ማስተዋወቂያ ይጠብቅዎታል", "🎁 Welcome! Bonuses and promotions await you"],
    ["ገንዘብ አስገብተው ይጀምሩ — ፈጣን እና ቀላል።", "Deposit and get started — fast and simple."],
    ["💳 አሁን ጀምር", "💳 Start now"],
    ["💳 እንዴት ገንዘብ ማስገባት ይቻላል?", "💳 How to deposit"],
    ["1. ወደ Telebirr ወይም CBE አካውንት ገንዘብ ይላኩ።", "1. Send money to the Telebirr or CBE account."],
    ["2. የክፍያውን Screenshot ያንሱ።", "2. Take a screenshot of the payment."],
    ["3. ከታች መጠኑን እና Screenshot ልከው ✅ ይጫኑ።", "3. Enter the amount and screenshot below, then tap ✅."],
    ["ፈጣን መጠን፦", "Quick amount:"],
    // KDM design layer (sidebar, home hero, wallet)
    ["መነሻ", "Home"], ["ጨዋታዎች", "Games"], ["ገበያ", "Marketplace"], ["ገንዘብ አውጣ", "Withdraw"], ["የኔ ቦርሳ", "My Wallet"], ["ቦርሳ", "Wallet"],
    ["ተወዳጅ ጨዋታዎች", "Popular Games"], ["ሁሉም ጨዋታዎች", "All Games"], ["ሁሉንም", "View All"],
    ["ተጫወት • አሸንፍ • አውጣ", "PLAY • WIN • WITHDRAW"], ["የሚወዷቸው ጨዋታዎች በአንድ ቦታ!", "Your Favorite Games, All in One Place!"], ["ጀምር", "Start Playing"],
    ["እንኳን ደህና መጡ!", "Welcome Back!"], ["መልካም እድል", "Good luck"], ["እና ይዝናኑ!", "and have fun!"],
    ["ጠቅላላ ሂሳብ", "Total Balance"], ["ጨዋታ ፈልግ", "Find a Game"], ["የማውጫ ዘዴ ይምረጡ", "Choose a withdrawal method"]
  ];
  var norm = function (s) { return String(s).replace(/\s+/g, " ").trim(); };
  var byAm = {}, byEn = {};
  PAIRS.forEach(function (p) { byAm[norm(p[0])] = p; byEn[norm(p[1])] = p; });

  var lang = lsGet(LANG_KEY) === "en" ? "en" : "am";
  var nodeState = new WeakMap(); // text node -> { orig, last }
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, CODE: 1, NOSCRIPT: 1 };

  function translateText(node) {
    var st = nodeState.get(node);
    var cur = node.nodeValue;
    if (!st || st.last !== cur) st = { orig: cur, last: cur }; // app rewrote it: treat as new original
    var key = norm(st.orig), pair = byEn[key] || byAm[key];
    var out = st.orig;
    if (pair) {
      var lead = (st.orig.match(/^\s*/) || [""])[0], trail = (st.orig.match(/\s*$/) || [""])[0];
      out = lead + pair[lang === "en" ? 1 : 0] + trail;
    }
    st.last = out;
    nodeState.set(node, st);
    if (cur !== out) node.nodeValue = out;
  }

  function translateAttrs(el) {
    var ph = el.getAttribute && el.getAttribute("placeholder");
    if (ph == null) return;
    if (el.dataset.i18nPh == null) el.dataset.i18nPh = ph;
    var pair = byEn[norm(el.dataset.i18nPh)] || byAm[norm(el.dataset.i18nPh)];
    if (pair) el.setAttribute("placeholder", pair[lang === "en" ? 1 : 0]);
  }

  function translateTree(root) {
    if (!root) return;
    if (root.nodeType === 3) { translateText(root); return; }
    if (root.nodeType !== 1) return;
    if (SKIP[root.tagName] || root.id === "lang-toggle" || root.id === "wins-track") return;
    translateAttrs(root);
    for (var c = root.firstChild; c; c = c.nextSibling) translateTree(c);
  }

  var obs = null, pending = [], scheduled = false;
  function flush() {
    scheduled = false;
    var list = pending; pending = [];
    list.forEach(function (n) { if (n.isConnected) translateTree(n); });
  }
  function startObserver() {
    if (obs || !window.MutationObserver) return;
    obs = new MutationObserver(function (muts) {
      muts.forEach(function (m) { m.addedNodes.forEach(function (n) { pending.push(n); }); });
      if (pending.length && !scheduled) { scheduled = true; requestAnimationFrame(flush); }
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  function setLang(next) {
    lang = next; lsSet(LANG_KEY, lang);
    document.documentElement.lang = lang === "en" ? "en" : "am";
    var btn = $("lang-toggle"); if (btn) btn.textContent = lang === "en" ? "🌐 EN" : "🌐 አማ";
    translateTree(document.body);
  }

  function injectLangToggle() {
    if ($("lang-toggle")) return;
    var btn = document.createElement("button");
    btn.id = "lang-toggle"; btn.type = "button"; btn.setAttribute("aria-label", "Language");
    btn.addEventListener("click", function () { setLang(lang === "en" ? "am" : "en"); });
    var bar = $("nav-bar"), close = $("nav-close");
    if (bar && close) bar.insertBefore(btn, close);
    else {
      var top = document.querySelector("#topbar .top-actions");
      if (top) top.insertBefore(btn, top.firstChild); else return;
    }
    btn.textContent = lang === "en" ? "🌐 EN" : "🌐 አማ";
  }

  // ------------------------------------------------- welcome banner + steps
  function injectWelcomeBanner() {
    if ($("welcome-bonus-banner") || lsGet(DISMISS_BANNER) === "1") return;
    var anchor = $("home-banners") || document.querySelector(".royal-hero");
    if (!anchor) return;
    var box = document.createElement("div");
    box.id = "welcome-bonus-banner";
    box.innerHTML =
      '<button class="wb-x" type="button" aria-label="Close">✕</button>' +
      '<div class="wb-title">🎁 እንኳን ደህና መጡ! ቦነስ እና ማስተዋወቂያ ይጠብቅዎታል</div>' +
      '<div class="wb-sub">ገንዘብ አስገብተው ይጀምሩ — ፈጣን እና ቀላል።</div>' +
      '<button class="wb-cta" type="button">💳 አሁን ጀምር</button><span class="wb-gift" aria-hidden="true">🎁</span>';
    anchor.insertAdjacentElement("beforebegin", box);
    box.querySelector(".wb-x").addEventListener("click", function () { lsSet(DISMISS_BANNER, "1"); box.remove(); });
    box.querySelector(".wb-cta").addEventListener("click", function () { goToPage("wallet"); });
    translateTree(box);
  }

  function injectStepsCard() {
    if ($("steps-card") || lsGet(DISMISS_STEPS) === "1") return;
    var anchor = document.querySelector(".quick-cabinet");
    if (!anchor) return;
    var card = document.createElement("div");
    card.id = "steps-card";
    card.innerHTML =
      '<div class="st-head"><span>በ3 ደረጃ ጀምር</span><button class="st-x" type="button" aria-label="Close">✕</button></div>' +
      '<div class="st-row">' +
      '<button class="st-step" type="button" data-go="wallet"><span class="st-num">1</span><span>ገንዘብ አስገባ</span></button>' +
      '<button class="st-step" type="button" data-go="focus-games"><span class="st-num">2</span><span>ጨዋታ ምረጥ</span></button>' +
      '<button class="st-step" type="button" data-go="focus-games"><span class="st-num">3</span><span>ተጫወት</span></button>' +
      '</div>';
    anchor.insertAdjacentElement("afterend", card);
    card.querySelector(".st-x").addEventListener("click", function () { lsSet(DISMISS_STEPS, "1"); card.remove(); });
    card.addEventListener("click", function (e) {
      var b = e.target.closest(".st-step"); if (!b) return;
      if (b.dataset.go === "wallet") goToPage("wallet");
      else {
        goToPage("lobby");
        var grid = $("game-grid"); if (grid) grid.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    translateTree(card);
  }

  var currentPage = "lobby";
  function syncLobbyOnly() {
    var onLobby = currentPage === "lobby";
    ["welcome-bonus-banner", "steps-card"].forEach(function (id) {
      var el = $(id); if (el) el.style.display = onLobby ? "" : "none";
    });
  }
  function wrapGoToPage() {
    var prev = goToPage;
    goToPage = function (page) { currentPage = page; prev(page); syncLobbyOnly(); };
  }

  // ------------------------------------------------------ easy deposit page
  function injectDepositHelpers() {
    var amount = $("deposit-amount"), accounts = $("deposit-accounts");
    if (!amount || !accounts) return;
    if (!$("deposit-howto")) {
      var how = document.createElement("div");
      how.id = "deposit-howto";
      how.innerHTML = "<b>💳 እንዴት ገንዘብ ማስገባት ይቻላል?</b><div>1. ወደ Telebirr ወይም CBE አካውንት ገንዘብ ይላኩ።</div>" +
        "<div>2. የክፍያውን Screenshot ያንሱ።</div><div>3. ከታች መጠኑን እና Screenshot ልከው ✅ ይጫኑ።</div>";
      accounts.insertAdjacentElement("beforebegin", how);
      translateTree(how);
    }
    if (!$("quick-amounts")) {
      var wrap = document.createElement("div");
      wrap.id = "quick-amounts";
      [50, 100, 200, 500].forEach(function (v) {
        var b = document.createElement("button");
        b.type = "button"; b.textContent = String(v); b.dataset.v = String(v);
        b.addEventListener("click", function () {
          amount.value = String(v);
          amount.dispatchEvent(new Event("input", { bubbles: true }));
          wrap.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
        });
        wrap.appendChild(b);
      });
      amount.addEventListener("input", function () {
        wrap.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x.dataset.v === amount.value); });
      });
      amount.insertAdjacentElement("afterend", wrap);
    }
  }

  // ------------------------------------------------------------------- boot
  function boot() {
    wrapGoToPage();
    injectLangToggle();
    injectWelcomeBanner();
    injectStepsCard();
    injectDepositHelpers();
    syncLobbyOnly();
    document.documentElement.lang = lang === "en" ? "en" : "am";
    translateTree(document.body);
    startObserver();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
