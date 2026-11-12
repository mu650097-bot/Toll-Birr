# የተዋሃደ ስሪት (Habtam-bet-main + KDM-design)

መሰረት: `KDM-design` zip (ከ`main` zip የበለጠ አዲስ ነበር: አዲስ ጨዋታዎች፣ Road games፣ KDM ዲዛይን፣ Boom ማስተካከያ)። ከ`main` ውስጥ የጎደለ ፋይል ወይም ኮድ አልነበረም።

## ከሁለቱም zip ውስጥ የጎደሉ ነገሮች (አሁን ተስተካክለዋል)
1. `kdm_design.css`, `kdm_ui.js`, `kdm_art.js` በ`MINI_PUBLIC_ASSETS` ውስጥ አልነበሩም → docker-compose ላይ 404 ይሰጡ ነበር (ያልተቀባ ገጽ)። ተጨምረዋል።
2. `Caddyfile.render` መላውን `/app` በ`file_server` ያቀርብ ነበር → source ኮድ እና `/app/data/*.db` መውረድ ይችሉ ነበር። አሁን ወደ bot whitelist server (127.0.0.1:8080) ይሄዳል።
3. Bottom nav: Home / Games / Sports / Marketplace / Profile (Wallet በ header balance + Deposit ቁልፍ እና drawer ይደረሳል)። Pending-payment ነጥብ ወደ Deposit ቁልፍ ተዛወረ።
4. `release_self_check.py` አሁን ያረጋግጣል: index.html የሚጭነው ፋይል ሁሉ በwhitelist ውስጥ አለ፣ Render file_server የለም፣ 5ቱ nav ቁልፎች አሉ፣ እና Chicken/Rabbit/Roast/Roulette/Bingo/Fast Keno tests (chicken_road, new_games, pool_games, crash_refund) ይሮጣሉ።

## ተፈትሿል
`release_self_check.py` → SELF_CHECK=PASS፤ እንዲሁም risk_controls, blocker, engagement_v8, table_games_rtp tests PASS።
## አልተፈተነም
Render/Docker build፣ live Telegram፣ Chapa/TURN፣ `production_smoke_test.py` (SMOKE_API_URL ይፈልጋል)።

## ሁለተኛ ዙር: ከreference ፎቶ ጋር የተመሳሰለ layout (KDM brand ብቻ — የሌላ ድርጅት logo/ስም አልተቀዳም)
- Home: "BET ON SPORTS" banner (ወደ Sports ገጽ ይወስዳል)።
- Sports: ግጥሚያ ረድፍ ከ 1 / X / 2 odds ቁልፎች ጋር፤ ኮምፒውተር ላይ ቡድኖች ግራ፣ odds+መጠን ቀኝ። ውርርድ/API/ክፍያ ኮድ አልተነካም (ቁልፎቹ ተመሳሳይ `data-sel`)።
- Marketplace: product grid (ስልክ 2፣ ታብሌት 3፣ ኮምፒውተር 4 ዓምድ)።
- Wallet: ዘዴዎች (CBE/BOA/Telebirr) ከ chevron ጋር በዝርዝር መልክ።
- አልተጨመረም (backend የለም): Bet Slip፣ Live score፣ ሐሰተኛ ውጤት ማሳየት። እነዚህ ከፈለጉ የbackend ሥራ ያስፈልጋቸዋል።

## ዙር: Live Aviator / Keno / Rocket + አዲስ Number Game
- Aviator (Crash)፣ Rocket እና Keno አሁን በየ60 ሰከንድ አንድ የጋራ ዙር ይሮጣሉ (ሁሉም ተጫዋች አንድ አይሮፕላን/ሮኬት/ዕጣ ያያል)። ሰርቨር: live_engine_v1.py (keys: aviator, rocket, keno)። ፋይሎች: kdm_aviator_live.js, kdm_rocket_live.js, kdm_keno_live.js።
- Number Game: በፎቶው መሠረት 4 ቁጥር (x3.8)፣ Odd/Even/Low/High (x1.9)፣ Bet Amount + Confirm፣ ዙር በየ30 ሰከንድ (22 ሰ ውርርድ)። ሰርቨር: /api/live/number/state እና /bet። ፋይሎች: kdm_number.js, kdm_number.css። ሂሳብ: ሁሉም ውርርድ RTP = 1 - house edge (5%)።
- ሙከራ: live_engine_regression_test.py → LIVE_ENGINE_TEST=PASS
