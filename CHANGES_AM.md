# የዛሬው ማስተካከያ (2026-10-30)

## አዲስ የተጨመረ
- **Chicken Road 2** — backend (`realtime_engine_v3.py`: 7 መስመር፣ Calm 0.80 / Rush 0.59፣ RTP/p^n)፣ `webapp_api.py` (key፣ house edge 5%፣ settings፣ history)፣ lobby tile፣ help፣ በ`index.html` መጫን፣ በ`MINI_PUBLIC_ASSETS` ማቅረብ።
- **Triple Gold Deluxe** — የራሱ game key `triplegold_deluxe` (ራሱ ON/OFF፣ stake ገደብ፣ house edge 8%፣ history) በTriple Gold engine ላይ፤ ጥቁር + ወርቅ ገጽታ።
- **Boom Ladder** — የዲዛይኑ "Boom Game" ደረጃ ጨዋታ (`kdm_boom.js`) ከTower engine ጋር ተገናኝቷል፤ Tower tile ስሙ "Boom Ladder" ሆኗል። የmultiplayer Boom pool ጨዋታ (`boom`) አልተነካም።

## ከገጹ ጋር የተገናኙ (ከዚህ በፊት ፋይላቸው ነበር ግን አይጫኑም ነበር)
- JS: `kdm_boom`, `kdm_jet`, `kdm_sports`, `kdm_wheel`, `kdm_bingo`, `kdm_fastkeno`, `kdm_slot`, `kdm_number`, `kdm_roast`, `kdm_chicken2`
- CSS: `kdm_slot`, `kdm_bingo`, `kdm_fastkeno`, `kdm_boom`, `kdm_jet`, `kdm_triplegold`, `kdm_flame`, `kdm_aztec` (Aztec / Flame / Triple Gold ስክሪኖች ያለ CSS ነበር የሚጫኑት)
- `app.js`: `wheel→setupWheel`, `slot→setupSlot`, `roast→setupRoast`, `chicken2→setupChicken2`

## ሙከራዎች
- የተስተካከለ: `crash_refund_regression_test.py` (`_auto_target` ጎድሎት ነበር — የሙከራው ስህተት)፤ `release_self_check.py` የ`flameclassics` ቁልፍ አሮጌ ነበር (አሁን `flame`)።
- አዲስ: `triplegold_deluxe_regression_test.py`፣ road ሙከራ ለ`chicken2`፣ እና "ያልተጫነ kdm_* ፋይል" መጠበቂያ።
- `SELF_CHECK=PASS`

## ጽዳት
- ተወግዷል: `webapp_api_errors.log`, `app.js.patch`, `kdm_icons_premium (1).css`
- ወደ `_unused/`: `lobby_reference.css`, `marketplace_ui.css`, `icons.css` (አሮጌ ንድፍ፣ ከ navy ዲዛይን ጋር ይጋጫሉ)
- `.dockerignore`: `*.log`, `preview_*.png`, `_unused/`, `*.patch`
- `MAX_ROUND_PAYOUT_ETB` ሰነድ ተስተካክሏል፤ ትክክለኛው default 100,000 ነው።

## አሁንም በቀጥታ አካባቢ መሞከር ያለባቸው
Docker build/start፣ HTTPS Telegram Mini App፣ እውነተኛ Chapa፣ WebRTC/TURN፣ Telegram ማሳወቂያ፤ BotFather token መቀየር፤ `PLATFORM_BANKROLL_ETB` እና `WITHDRAW_TURNOVER_MULTIPLIER` በ`.env`።
