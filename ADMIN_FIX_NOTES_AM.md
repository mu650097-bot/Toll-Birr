# Admin ቼክ እና ማስተካከያ

## የተፈተነው
ሁሉም 33 የAdmin GET ኤንድፖይንቶች (200 ይመልሳሉ፤ ተጫዋች ወይም PIN የሌለው አድሚን 200 አያገኝም)፣ እና ማስቀመጥ → መልሶ ማንበብ → በተጫዋች ላይ መተግበር፦
Game Economics (77 ጌሞች)፣ Platform Controls (ሁሉም መስኮች)፣ Deposit Bonus፣ Balance Adjust (ትልቅ መጠን 2-ደረጃ ማረጋገጫ፣ አሉታዊ ባላንስ ይከለክላል)፣ Ban/Unban፣ Marketplace commission/moderation፣ Sports (create/live/close/settle)፣ Banner፣ App-announcement፣ Broadcast፣ Support፣ Shamo፣ Mystery box።

## የተገኙ ችግሮች እና ማስተካከያ
1. **Per-game Min Bet / House Edge ተጫዋች ላይ አይደርስም ነበር** — ዓለም አቀፉ Min Bet (በነባሪ ON, 1 ብር) ሁሉንም ጌም ይሽራል፤ ስለዚህ ካርዱ ላይ 5 ብር ብታስቀምጡ ተጫዋቹ 3/1 ያይ ነበር። አሁን `/api/admin/game-control` የ`effective_*` ዋጋዎችን እና `*_overridden` ባንዲራዎችን ይመልሳል፤ ካርዱ ላይም «🔒 ዓለም አቀፍ ቅንብር እየሻረው ነው — ተጫዋቹ የሚያየው፦ …» ማስጠንቀቂያ ይታያል።
2. **House Edge በዝምታ ይጠጋጋ ነበር** — ካርዱ edge ን በ1 ዲጂት (8.25% → 8.3%) ያሳያል፤ ማንኛውንም ሌላ መስክ ሲያስቀምጡ እውነተኛው edge ይቀየር ነበር። አሁን እስከ 4 ዲጂት በትክክል ይታያል።
3. **Support ትኬት** — አድሚኑ የተጠቃሚውን መልዕክት ማንበብ አይችልም ነበር (በጭፍን Reply) እና ትኬት መዝጋት አይችልም ነበር። አሁን፦ የመጨረሻው መልዕክት ይታያል፣ «Read» ሙሉ ውይይቱን ያሳያል (አዲስ `GET /api/admin/support/tickets/<id>`)፣ «Close» ትኬቱን ይዘጋል።
4. ተደጋግሞ የነበረ ዓረፍተ ነገር በGame Economics መግለጫ ላይ ተወግዷል።

## የተለወጡ ፋይሎች
`webapp_api.py`, `app.js` — GitHub ላይ ተክተው ይተኩ። Regression ሙከራዎች ሁሉ ያልፋሉ (platform_controls_e2e, release_self_check, risk_controls, blocker, launch_blocker, withdraw_limits, cashback_tiers, playwin_fixes, sports_league, live_all, ወዘተ)፣ api_path_audit UNMATCHED=0።
