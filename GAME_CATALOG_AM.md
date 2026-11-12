# አዲስ የጨዋታ ካታሎግ (game_catalog.js)

- 36 Slot ጨዋታዎች + Crash / Rocket / High Flyer / Sky Masters / Chicken Road 2 + Power / Super / Insta Keno ወደ lobby ተጨምረዋል።
- አዲስ tabs: Slots, Crash, Keno & Spin (ነባሮቹ aviator, jet, chicken, rabbit, roast, fish, dice, keno, fastkeno, wheel ወደ ተገቢው tab ተመድበዋል)።
- እያንዳንዱ አዲስ tile ነባር server engine ይጠቀማል (slot / aviator / jet / keno / fastkeno / chicken)፤ RNG, RTP, payout, history, provably-fair አልተቀየሩም።
- Slot tiles የራሳቸው ስም፣ ቀለም እና ምልክቶች (symbols) አሏቸው (ማሳያ ብቻ)።
- Backend: እያንዳንዱ አዲስ ጨዋታ (slot_01..slot_36, crash, rocket, highflyer, skymasters, keno_power, keno_super, keno_insta) የራሱ game_key፣ enable switch፣ stake limit፣ house edge (RTP)፣ history አለው፤ ሂሳቡ ግን ነባሩ engine ነው (`GAME_ENGINE` በ webapp_api.py)። Chicken Road 2 የChicken engine settings ይጠቀማል።
- release_self_check.py = SELF_CHECK=PASS። Live (Render/Telegram) ላይ አልተሞከረም።
- Cover art: ለእያንዳንዱ አዲስ ጨዋታ በvector (SVG) የተሠራ የራሱ ሽፋን ምስል (sunburst፣ ትልቅ ምልክት፣ የtheme symbols strip፣ Crash ላይ ጥምዝ መስመር፣ Keno ላይ ኳሶች) — ውጫዊ ምስል አይጠቀምም።
- Admin: ሁሉም አዲስ ጨዋታዎች በAdmin ፓነል (game-control እና cabinet-games/settings) ይታያሉ፤ ON/OFF፣ Min/Max Bet፣ House Edge (RTP) ለእያንዳንዳቸው ይስተካከላል።
- ማስታወሻ: pool_games_regression_test.py በመጀመሪያው zip ላይም አልፎ አልፎ ይወድቃል (random/timing) — ከዚህ ለውጥ ጋር የተያያዘ አይደለም።
