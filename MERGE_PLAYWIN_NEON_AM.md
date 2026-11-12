# የተዋሃደ ስሪት — Play Win + Neon ዲዛይን + Skins

መሠረት: Habtam-bet-main (neon ዲዛይን፣ አዲሱ app.js / game_help.js / webapp_api.py)።

## ከ Only_changed የገቡ (Play Win)
* kdm_mini_app.py: «Play Win 🥳» ስም፣ `/start ref_` እና `g_` ማስተናገድ፣ የቦነስ ማውጣት ገደብ (በ API እና በ bot ሁለቱም)፣ `/rewards.js` whitelist።
* index.html: Play Win ርዕስ/አርማ፣ የቦነስ ማስታወሻዎች፣ የአድሚን ማስታወቂያ ጨዋታ መምረጫ፣ `rewards.js`።

## ከተጫኑት ፋይሎች የገቡ
* 5ቱ `kdm_skin_*.js` በ index.html ተገናኝተዋል (kdm_betpro.js በኋላ፣ kdm_covers/neon በፊት) እና በ kdm_mini_app.py whitelist ተመዝግበዋል።

## የተስተካከለ
* Bottom nav: Home / Games / Sports / Marketplace / Profile (ከዚህ በፊት Sports ጠፍቶ Wallet ነበር)።
* rewards.js እና skin ፋይሎች whitelist ውስጥ ስላልነበሩ 404 ይሰጡ ነበር።

## ያልገቡ (ከመሠረቱ የቆዩ)
app_1.js, index_1.html, index_c2f098.html, kdm_mini_app_1.py, PlayWin_changes.zip ፋይሎች።

## ተፈትሿል
Python/JS syntax፣ 78 የ index.html ፋይሎች ሁሉ አሉ እና whitelist ውስጥ ናቸው፣ እና regression tests (casino_cards, cards2, dice2, pool_games, crash_refund, live_all, new_games, sports_live ወዘተ) PASS።
## አልተፈተነም
Browser ላይ ምስላዊ ሙከራ (skins + neon አብረው)፣ Render deploy፣ እውነተኛ Telegram።

---
# ሁለተኛ ዙር ማስተካከያዎች
* **Admin upload 404:** `betpro_v1.py` ከ `webapp_api.py` ጋር አልተገናኘም ነበር → ተገናኝቷል (`apply_betpro.py`)። የፎቶ ገደብ 15MB።
* **Mystery Box:** አድሚን «🚀 አሁን ልቀቅ» ሲጫን ለሁሉም ለተመረጠ ደቂቃ ይከፈታል (በአንድ ልቀት አንድ ጊዜ፣ ሽልማቱ play-only ቦነስ)። Home + Profile ላይ ይታያል። «በየ ሰዓቱ» ሁነታም አለ።
* **Invite:** በየተጋበዘ ሰው 1 ብር play-only ቦነስ፤ አዲስ አካውንት የመጀመሪያ request ሲሆን invite እንዳይጠፋ ተስተካክሏል።
* **Admin ኢኮኖሚ:** Buffalo / Aztec / Flame / Triple Gold ወደ Game Economics ተጨመሩ → 33ቱም የ lobby ጨዋታዎች በአድሚን ይቆጣጠራሉ።
* **Recent Big Wins ticker (app.js):** ዙር መዝለል፣ ባዶ ቦታ፣ በስልክ መቆም እና የጨዋታ ቁልፍ አለመመሳሰል ተስተካክሏል።
* **የሚሽከረከረው ባነር (kdm_neon.js):** Aviator / Jet / Crash / High Flyer / Sky Masters ምስሎች (ከተላከው ምስል የተቆረጡ) በባነሩ ውስጥ ገብተዋል፤ ንኪያቸው ወደ ጨዋታው ይወስዳል። የአሸናፊ slide ንኪታም ትክክለኛውን ጨዋታ ይከፍታል። ምስሎቹ በ lobby ካርዶች ላይም (Aviator ካርድን ጨምሮ) ተቀይረዋል (`kdm_covers.js`)።
* **`_unused_legacy/`:** በ index.html ተጭነው የማያውቁ 6 ፋይሎች እዚያ ተንቀሳቅሰዋል (README ይመልከቱ)።
* አዲስ test: `playwin_fixes_regression_test.py` (በ release_self_check ውስጥ ተመዝግቧል)።
