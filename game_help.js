/* KDM GAME HELP -- presentation only. Adds a "How to play" sheet to every game page and shows it once,
   the first time a player opens that game. Never touches stakes, RNG, payouts or any API call. */
(function () {
  "use strict";
  var NOTE = "ውጤቱ በ server በዘፈቀደ ይወሰናል፤ ሁልጊዜ ማሸነፍ አይቻልም። ማጣት ከሚችሉት በላይ አይጫወቱ።";
  var H = {
    dice: ["🎲 Dice", ["Stake (መጠን) ያስገቡ።", "ከ1–6 ቁጥር ይምረጡ።", "▶️ ይጫኑ -- ዳይሱ ሲቆም ቁጥርዎ ከወጣ ያሸንፋሉ።"]],
    slot: ["🎰 Slot", ["Stake ያስገቡ።", "▶️ ይጫኑ -- 3 reels ይዞራሉ።", "ምልክቶች ሲመሳሰሉ ያሸንፋሉ፤ ዋጋው በምልክቱ ይለያያል።"]],
    wheel: ["🎡 Lucky Wheel", ["Stake ያስገቡ።", "▶️ ይጫኑ -- መንኮራኩሩ ይዞራል።", "በሚቆምበት ክፍል ላይ ያለው multiplier × stake ያገኛሉ (0× ከሆነ ይጠፋል)።"]],
    keno: ["🎯 Keno", ["ከ1–80 ውስጥ 1 እስከ 10 ቁጥሮች ይምረጡ፣ Stake ያስገቡ እና Bet ይጫኑ።", "ዕጣው በየ1 ደቂቃው ለሁሉም ተጫዋች አንድ ነው፤ ሰርቨሩ 20 ኳሶችን አንድ በአንድ ያወጣል።", "ብዙ ቁጥር ሲገጥም ሽልማቱ ይጨምራል። ውርርድ የሚቀበለው በዙሩ መጀመሪያ ባሉት ሰከንዶች ብቻ ነው።"]],
    fastkeno: ["⚡ Fast Keno", ["ከ1–40 ውስጥ 1 እስከ 8 ቁጥሮች ይምረጡ።", "▶️ ይጫኑ -- 10 ኳሶች ይወጣሉ።", "ብዙ ሲገጥም ሽልማቱ ይጨምራል።"]],
    roulette: ["🎡 Roulette", ["ውርርድ ይምረጡ: Red/Black, Odd/Even, Dozen, Column ወይም አንድ ቁጥር።", "Stake ያስገቡና ያሽክርክሩ።", "ኳሱ በመረጡት ላይ ካረፈ ያሸንፋሉ (ቁጥር 36×)።"]],
    bingo: ["🎱 Bingo", ["Stake ያስገቡ -- ካርድ ይታደልዎታል።", "40 ኳሶች ይወጣሉ።", "ብዙ መስመር ሲሞላ ሽልማቱ ይጨምራል።"]],
    aviator: ["✈️ Aviator", ["በየ1 ደቂቃው አንድ በረራ ለሁሉም ተጫዋች ይካሄዳል፤ በመጀመሪያዎቹ 15 ሰከንዶች Bet A / Bet B ያስገቡ።", "አውሮፕላኑ ሲበር Cash ን ይጫኑ፣ ወይም Auto cash-out (ምሳሌ x2.00) ያስቀምጡ።", "ከመከስከሱ በፊት Cash ካደረጉ stake × multiplier ያሸንፋሉ፤ ቀድሞ ከተከሰከሰ stake ይጠፋል።"]],
    jet: ["🚀 Jet", ["በየ1 ደቂቃው አንድ በረራ ለሁሉም ተጫዋች ይካሄዳል፤ በመጀመሪያዎቹ 15 ሰከንዶች Bet 1 / Bet 2 ያስገቡ።", "ሮኬቱ ሲወጣ Cash ን ይጫኑ፣ ወይም Auto cash-out ያስቀምጡ።", "ከመከስከሱ በፊት Cash ካደረጉ ያሸንፋሉ፤ ቀድሞ ከተከሰከሰ stake ይጠፋል።"]],
    chicken: ["🐔 Chicken Road", ["Stake ያስገቡ እና Start ይጫኑ።", "መንገዱን ሌን በሌን ይሻገሩ -- እያንዳንዱ ሌን ሽልማቱን ይጨምራል።", "ቀድመው 💰 Cash Out ካልጫኑ እና አደጋ ካጋጠመ ሁሉም ይጠፋል።"]],
    rabbit: ["🐇 Rabbit Road", ["Stake ያስገቡ እና Start ይጫኑ።", "10 ዝላይ አለ -- እያንዳንዱ ዝላይ ሽልማቱን ያሳድጋል።", "በማንኛውም ዝላይ 💰 Cash Out ያድርጉ፤ ካልሆነ አደጋ ሲመጣ ይጠፋል።"]],
    penaltystreak: ["⚽ Penalty Streak", ["Stake ያስገቡ፣ ደረጃ (Easy / Medium / Hard) ይምረጡ እና ⚽ ምታ ይጫኑ።", "እያንዳንዱ ግብ ሽልማቱን ያሳድጋል (ከታች ያለው ሠንጠረዥ ትክክለኛውን ያሳያል)።", "በማንኛውም ግብ በኋላ 💰 Cash Out ያድርጉ፤ ጠባቂው ካዳነ ሁሉም ይጠፋል።"]],
    chicken2: ["🐔 Chicken Road 2", ["Stake ያስገቡ፣ Calm ወይም Rush ይምረጡ እና Cross ይጫኑ።", "7 መሻገሪያዎች አሉ -- እያንዳንዱ ደህና መሻገሪያ ማባዣውን ያሳድጋል።", "መኪና ከገጨዎት ይጠፋሉ፤ ከማንኛውም ደህና መሻገሪያ በኋላ 💰 Cash Out ያድርጉ።"]],
  chicken2: ["🐔 Chicken Road 2", ["Stake ያስገቡ፣ Calm ወይም Rush ትራፊክ ይምረጡ እና Cross ይጫኑ።", "እያንዳንዱ ደህና መሻገሪያ ሽልማቱን ያሳድጋል (7 መስመሮች)።", "መኪና ከመታዎት ዙሩ ይጠፋል፤ ከማንኛውም ደህና መሻገሪያ በኋላ Cash Out ይጫኑ።"]],
  tower: ["🏗 Tower", ["Stake ያስገቡ፣ ደረጃ ይምረጡ እና 🏗 ውጣ ይጫኑ።", "እያንዳንዱ ደረጃ ሽልማቱን ያሳድጋል።", "ወጥመድ ከነኩ ይጠፋል፤ ከዚያ በፊት 💰 Cash Out ያድርጉ።"]],
    roast: ["🔥 Chicken Roast", ["Stake ያስገቡ እና Start ይጫኑ።", "ዶሮዋን ከእሳት ደረጃ በደረጃ ያሻግሩ።", "በፈለጉት ጊዜ 💰 Cash Out ያድርጉ፤ እሳት ከነካ ይጠፋል።"]],
    mines: ["💣 Mines", ["Stake እና የ mine ቁጥር ይምረጡ።", "ሴሎችን ይክፈቱ -- እያንዳንዱ ደህንነቱ የተጠበቀ ሴል ሽልማቱን ይጨምራል።", "Mine ከነካ ይጠፋል፤ ከዚያ በፊት Cash Out ያድርጉ።"]],
    plinko: ["🟣 Plinko", ["Stake ያስገቡ።", "▶️ ይጫኑ -- ኳሱ ይወርዳል።", "ባረፈበት ክፍል ያለው multiplier × stake ያገኛሉ።"]],
    fish: ["🐟 Fish", ["Stake እና Shot ይምረጡ።", "▶️ ይጫኑ።", "ዓሣውን ከመቱ ሽልማቱ ይከፈላል።"]],
    card: ["🃏 Card Table", ["Stake ያስገቡ።", "High ወይም Low ይምረጡ።", "የሚቀጥለው ካርድ መረጡት ከሆነ ያሸንፋሉ።"]],
    coinflip: ["🪙 Coin Flip", ["Stake ያስገቡ።", "Heads ወይም Tails ይምረጡ።", "ሳንቲሙ ሲቆም የመረጡት ከወጣ ያሸንፋሉ -- 50% ዕድል፤ ሽልማቱ ከ2× ትንሽ ዝቅ ይላል (house edge)።"]],
    penalty: ["⚽ Penalty Shootout", ["Stake ያስገቡ።", "ኳሱን የሚመቱበትን ጎን ይምረጡ (ግራ / መሃል / ቀኝ)።", "ግብ ጠባቂው ካልዘለለበት ጎን ከመቱ ግብ ነው -- ያሸንፋሉ (ዕድል 2 ከ 3)። ጠባቂው ከያዘው ይጠፋል።"]],
    blackjack: ["🃏 Blackjack", ["Bet ያስገቡና «ካርድ ስጥ» ይጫኑ -- 2 ካርድ ይታደልዎታል።", "Hit = ተጨማሪ ካርድ፣ Stand = ይበቃኛል፣ Double = Bet በእጥፍ እና አንድ ካርድ ብቻ።", "ከ21 ሳያልፉ ከ Dealer የበለጠ ቁጥር ካገኙ ያሸንፋሉ። ከ21 ካለፉ (Bust) ይሸነፋሉ። ሁለት ካርድ 21 = Blackjack (ከፍተኛ ክፍያ)።"]],
    baccarat: ["🎴 Baccarat", ["Bet ያስገቡና Player፣ Banker ወይም Tie ይምረጡ።", "ሁለቱም እጅ ካርድ ይቀበላሉ -- ወደ 9 የቀረበው (ከ10 በኋላ 0 ይጀምራል) ያሸንፋል።", "Player/Banker ላይ ከተወራረዱና Tie ከወጣ ገንዘብዎ ይመለሳል። Tie ላይ ከተወራረዱ ክፍያው ከፍተኛ ነው።"]],
    dragontiger: ["🐉 Dragon Tiger", ["Stake ያስገቡ እና Dragon፣ Tiger ወይም Tie ይምረጡ።", "ለ Dragon እና ለ Tiger አንድ አንድ ካርድ ይሰጣል (A ትንሹ፣ K ትልቁ)።", "ትልቁ ካርድ ያሸንፋል። Dragon/Tiger ላይ ሲወራረዱ እኩል ከወጣ ገንዘብዎ ይመለሳል።"]],
    andarbahar: ["🃏 Andar Bahar", ["Stake ያስገቡ እና አንደር ወይም ባሃር ይምረጡ።", "አንድ ጆከር ካርድ ይገለጣል፣ ከዚያ ካርዶች አንደር እና ባሃር በተራ ይሰጣሉ።", "የጆከሩን ቁጥር መጀመሪያ ያገኘው ወገን ያሸንፋል። አንደር ትንሽ የበለጠ ዕድል አለው፣ ስለዚህ ክፍያው ከባሃር ዝቅ ይላል።"]],
    buffalo: ["🦬 Buffalo Plains", ["Stake ያስገቡና Spin ይጫኑ።", "ተመሳሳይ ምልክት ከግራ በተከታታይ ሪሎች (ቢያንስ 3) ሲታይ ይከፍላል፤ ብዛታቸው ይባዛል (243 ways)።", "3 / 4 / 5 🪙 ሲወጣ 8 / 12 / 20 ነጻ ዙሮች (ክፍያ x2) ይጀምራሉ።"]],
    aztec: ["🗿 Aztec Gold", ["Stake ያስገቡና Spin ይጫኑ።", "ውርርድዎ በ5 መስመሮች (3 ረድፍ + 2 ሰያፍ) እኩል ይከፈላል።", "መስመር ሦስት ተመሳሳይ ምልክት ሲይዝ ይከፍላል፤ የመስመሮች ድምር ይከፈላል።"]],
    flame: ["🔥 Flame Classics", ["Stake ያስገቡና Spin ይጫኑ።", "መስመሩ ሦስት ተመሳሳይ ምልክት ወይም ሁለት 🍒 ሲይዝ ይከፍላል።", "በእያንዳንዱ ዙር 1 ከ 8 ዕድል በነጻ Hot Respin ይመጣል፤ ክፍያው ይደመራል።"]],
    triplegold: ["🔔 Triple Gold", ["Stake ያስገቡና Spin ይጫኑ።", "መካከለኛው መስመር ሦስት ተመሳሳይ ምልክት ወይም ሁለት 🍒 ሲይዝ ይከፍላል።", "ሁሉም ክፍያዎች house edge ተቀንሶ በገጹ ላይ ይታያሉ።"]],
    dice2: ["🎲 Dice", ["Stake ያስገቡ፣ ከ2–12 ቁጥር እና Under / Exact / Over ይምረጡ።", "ሁለት ዳይስ ይጣላሉ፤ ድምሩ ከምርጫዎ ጋር ከተስማማ ያሸንፋሉ።", "የማሸነፍ ዕድሉ እና ክፍያው በቀጥታ ይታያል -- ዕድሉ ዝቅ ሲል ክፍያው ከፍ ይላል።"]],
    coinstreak: ["🪙 Coin Flip", ["Stake ያስገቡ፣ Heads ወይም Tails ይምረጡ እና Flip ይጫኑ።", "ከተሳካ ተከታታይ (Streak) ይጨምራል፣ ሽልማቱም ያድጋል። እያንዳንዱ Flip 50/50 ነው።", "በማንኛውም ጊዜ 💰 Cash Out ያድርጉ፣ ሲሸነፉ ሁሉም ይጠፋል።"]],
    boom: ["💣 Boom Game", ["ለዙሩ ገንዘብ ከፍለው ይግቡ።", "ከፍርግርጉ ውስጥ ቦታ ይምረጡ።", "ቦምብ የያዘ ቦታ የመረጠ ይወጣል፤ የቀሩት ሽልማቱን ይካፈላሉ። 🔒 Commitment ዙሩ ሲያልቅ ይገለጣል።"]],
    number: ["🔢 Number Game", ["Stake ያስገቡ፣ ከ1–4 ቁጥር አንዱን ወይም Odd / Even / Low / High ይምረጡ እና Confirm ይጫኑ።", "ዙሩ በየ30 ሰከንዱ ለሁሉም ተጫዋች አንድ ነው፤ ሰርቨሩ አንድ ቁጥር (1–4) ይመዝናል።", "ቁጥር ሲገምቱ x3.8፣ Odd / Even / Low / High ሲመርጡ x1.9 ይከፈላል (ቤቱ 5% ብቻ)። በአንድ ዙር ከአንድ በላይ ምርጫ መያዝ ይቻላል።"]]
  };
  var SEEN = "kdm_help_seen";
  function seen() { try { return JSON.parse(localStorage.getItem(SEEN) || "{}"); } catch (_) { return {}; } }
  function mark(k) { try { var s = seen(); s[k] = 1; localStorage.setItem(SEEN, JSON.stringify(s)); } catch (_) {} }

  function sheet(k) {
    var d = H[k]; if (!d) return;
    close();
    var el = document.createElement("div"); el.id = "kdm-help-sheet"; el.className = "kh-back";
    var steps = d[1].map(function (t, i) { return '<li><b>' + (i + 1) + '</b><span></span></li>'; }).join("");
    el.innerHTML = '<div class="kh-card" role="dialog" aria-modal="true"><h3></h3><ol>' + steps +
      '</ol><p class="kh-min">ዝቅተኛ stake: <b>1 ብር</b></p><p class="kh-note"></p><button type="button" class="kh-ok">ገብቶኛል ✅</button></div>';
    el.querySelector("h3").textContent = d[0] + " -- እንዴት ይጫወታሉ?";
    el.querySelectorAll("li span").forEach(function (s, i) { s.textContent = d[1][i]; });
    el.querySelector(".kh-note").textContent = NOTE;
    el.addEventListener("click", function (e) { if (e.target === el || e.target.classList.contains("kh-ok")) close(); });
    document.body.appendChild(el);
    mark(k);
  }
  function close() { var o = document.getElementById("kdm-help-sheet"); if (o) o.remove(); }

  function decorate() {
    var p = document.querySelector(".page.active"); if (!p || p.id.indexOf("page-") !== 0) return;
    var k = p.id.slice(5); if (!H[k]) return;
    if (!p.querySelector(".kh-btn")) {
      var b = document.createElement("button"); b.type = "button"; b.className = "kh-btn"; b.textContent = "❓ እንዴት ይጫወታሉ?";
      b.addEventListener("click", function () { sheet(k); });
      var h = p.querySelector("h2"); if (h) h.after(b); else p.prepend(b);
    }
    if (!seen()[k] && !document.getElementById("kdm-help-sheet")) sheet(k);
  }
  function init() {
    var pages = document.getElementById("pages") || document.body;
    new MutationObserver(function () { decorate(); }).observe(pages, { attributes: true, attributeFilter: ["class"], subtree: true, childList: true });
    decorate();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
