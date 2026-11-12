# V8 ለውጦች (Banners · Back/Close · Shamo · Deposit approve fix)

1. **Deposit Approve/Reject "Admin PIN" ችግር** — በፊት ሁሉም Approve/Reject button ላይ `/adminpin` (15 ደቂቃ) ይጠየቅ ነበር። አሁን deposit/withdraw Approve/Reject/Proof PIN አይጠይቁም (staff check ይቀራል)።
   PIN መልሶ እንዲጠየቅ `.env` ላይ `BOT_PAYMENT_ACTIONS_REQUIRE_PIN=1` ያድርጉ።
2. **Home Banners** — ከላይ ፎቶዎች ወደ ጎን እየተላለፉ ይታያሉ (እስከ 5፣ እያንዳንዱ በራሱ ሰከንድ)። Admin Panel → "Home Banners" ላይ ይጨምሩ/ይሰርዙ፤
   Bot ላይ **Photo ማስታወቂያ** ሲልኩም በራሱ banner ይሆናል። ፎቶ ከሌለ የድሮው hero ይታያል።
3. **Back / Close** — ከ header በታች ← Back እና ✕ Close ሁልጊዜ አሉ (Telegram's native Back button ም ይሰራል)።
4. **Shamo** — በየቀኑ በተወሰነ ሰዓት (default 9:00 PM አዲስ አበባ) የሚከፈት Mystery Box። countdown፣ 8 ሳጥኖች፣ አንድ ሰው በቀን አንድ ጊዜ፣ ሽልማቱ በServer ይወጣል።
   **በ default ዝግ ነው** — Admin Panel → "Shamo" ላይ Enabled ያድርጉ፣ prizes (`amount:weight`) እና Daily budget ያስገቡ።
5. **ሌላ ያገኘሁት** — `premium.js/premium.css` ከ bot server አይቀርቡም ነበር (app.js እና style.css ብቻ)፤ አሁን ተስተካክሏል።

Test: `python3 engagement_v8_test.py`

6. **Game scenes (Aviator, Jet, Chicken Road, Rabbit Road, Keno, Fish)** — የድሮው ሲሊንደር/ኳስ/ሳጥን 3D ቅርጾች በ `game_stage.js` (original vector art) ተተክተዋል። ቁጥሮቹ ሁሉ ከServer outcome ብቻ ናቸው (ምንም አይፈጠርም)።
   ሌሎቹ (Dice, Slot, Wheel, Plinko, Mines, Card) አሁንም የድሮው ናቸው።
