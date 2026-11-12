# ማስተካከያ: የአሸናፊዎች banner / ticker — የጌም ምስል የሌላቸው

## ምክንያት
1. Live ዙሮች (Aviator/Rocket/Keno/Number) አሸናፊነት `game_<ቁልፍ>_live_payout` ብለው ይመዘገባሉ → `/api/wins/recent` ቁልፉን `aviator_live`፣ `number_live_live` ብሎ ይልክ ነበር። እነዚህ ከሎቢ ጌም ጋር አይዛመዱም ነበር → ምስል የለም፣ ጠቅ ሲደረግ ወደ ሎቢ ብቻ።
2. `dice` (አሮጌው ቁልፍ) ከ`dice2` ጋር አልተገናኘም ነበር፤ `auction_win` ምንም ጌም አልነበረውም።
3. Crash / Rocket / High Flyer / Sky Masters / Power|Super|Insta Keno / Triple Gold Deluxe / slot_NN አሸናፊዎች ወደ ዋናው Aviator/Keno/Slot ምስል እና ገጽ ይቀየሩ ነበር (የራሳቸው skin ምስል አይታይም ነበር)።
4. ለማንኛውም ያልታወቀ ወደፊት ቁልፍ ምስል አልነበረም።

## ማስተካከያ
- `webapp_api.py`: `_live` ቅጥያ ይወገዳል (aviator_live→aviator፣ number_live_live→number)፤ `auction_win`→marketplace፤ live ዓይነቶች icon ያገኛሉ።
- `game_catalog.js`: `kdmCover(key, icon)` ሁልጊዜ ምስል ይመልሳል (1. KDM_ART በስም፣ 2. የተሰራ vector፣ 3. ከ emoji ጋር የቀለም ሽፋን)። `kdmHasVariant()` ተጨመረ።
- `app.js` (`resolveWinGame`): ትክክለኛው skin ገጽ ይከፈታል (slot_05፣ crash፣ highflyer፣ keno_power …)፤ alias ተጨመሩ (dice, auction, *_live)።
- `kdm_neon.js`: የሚሽከረከረው banner ተመሳሳይ ምስል ይጠቀማል።
- ሙከራዎች: አዲስ `wins_recent_keys_regression_test.py`፣ `wins_cover_check.js` (node)። ያረጁ ሙከራዎች ተስተካክለዋል: `live_engine_regression_test.py` (ሰንጠረዥ እና የተሰየሙ ተግባራት)፣ `playwin_fixes_regression_test.py` (invite bonus አሁን ከ deposit በኋላ ነው የሚከፈለው — ነባሪው ቀጥሏል)።

## ያልተነካ (ማወቅ ያለብዎት)
- `royal_ui.js` / `royal_theme.css`: backend (`royal_v1.py`, /api/announcements) አለ፣ ግን index.html markup (inbox፣ mission፣ admin-inapp) በ merge ጠፍቷል እና theme አሁን ካለው neon ዲዛይን ጋር ይጋጫል። ስለዚህ አልተገናኘም — in-app ማስታወቂያ inbox ከፈለጉ ልንገነባ እንችላለን።
- `release_self_check.py` በዚህ አካባቢ ከ5 ደቂቃ በላይ ይወስዳል (አልጨረሰም)፤ ነጠላ ሙከራዎች ግን ሁሉም ተሮጠዋል።
