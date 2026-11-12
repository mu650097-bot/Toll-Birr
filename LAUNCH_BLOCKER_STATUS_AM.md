# KDM Mini App — Launch blocker update

## በኮድ የተስተካከሉ

- Realtime RTP regression አሁን በproduction `rt_action` ላይ 12ቱን ጌሞች በsample ይፈትሻል፤ ከlegacy `/play` ብቻ አይወሰንም።
- `/round/start` ላይ input validation ከstake reservation በፊት ይካሄዳል። የተሳሳተ input 400 ይመልሳል።
- የ`/round/start` ምላሽ በnetwork ከጠፋ ተመሳሳይ client seed/input ተጠቅሞ ያለውን ACTIVE round መመለስ ይቻላል።
- `/action` ምላሽ ከጠፋ frontend የserver state በመመርመር የተፈጸመውን ውጤት ለማግኘት ይሞክራል። 120 ሰከንድ ያለፈ ACTIVE round ከመጥፋት ይልቅ stake ተመላሽ ሆኖ `REFUNDED` ይሆናል።
- Client seed ከserver seed በፊት ይፈጠራል፤ realtime outcome ላይ seed commitment እና seed መረጃ ይታያል።
- Mines WIN payout ከstake በታች እንዳይሆን ተደርጓል። Plinko/Fish ከstake በታች የሚመልሱ ውጤቶች `WON` አይባሉም፤ partial payout ከሆነ በwallet ይመዘገባል።
- Plinko landing bucket ከሚታየው path ጋር ተያይዟል። Wheel 10 sectors ይጠቀማል፣ ወደ server የተመረጠው sector ይቆማል፣ እና effective payout values ያሳያል።
- Wheel admin prize values ከconfigured RTP ጋር በመደበኛነት ይመጣጠናሉ፤ የሚታየው ዋጋ ከሚከፈለው multiplier ጋር ይቀራረባል።
- `MAX_ROUND_PAYOUT_ETB` ከፍተኛ የአንድ ዙር payout ገደብ ተጨምሯል፤ default `100,000 ETB` ነው።
- Number game የሚጠቀመው `secrets` random ነው፤ ስህተት ሲፈጠር internal exception ወደ client አይላክም። Number game የpublic commit-reveal proof እንዳለው የሚያመለክት የቆየ ጽሑፍ ተስተካክሏል።
- Deposit bonus በdefault 10%፣ 6 ሰዓት በኋላ፣ በመደበኛ wallet balance ውስጥ ይገባል። Default minimum deposit 1 ETB ሆኗል፤ bonus የተለየ locked balance ወይም wagering condition የለውም።
- Bot payment approval/rejection በ`BEGIN IMMEDIATE` እና `status='pending'` guard ተጠብቋል። Chapa payments በmanual staff approve/reject አይቀየሩም።
- Chapa credit በpending state፣ transaction reference፣ amount/currency እና `credited_at` ይፈተሻል፤ double-credit ተከላክሏል። Callback error ውስጣዊ ዝርዝር አያሳይም።
- Marketplace buyer “Confirm receipt” ተጨምሯል። Review በtransaction አንድ ብቻ ይፈቀዳል። Auto-refund የdelivery timestamp ይመለከታል፤ Telegram notification በDB transaction ውስጥ አይላክም፣ በoutbox ከcommit በኋላ ይላካል።
- Pending withdrawals ከ30 ደቂቃ በላይ ሲቆዩ staff reminder በ15 ደቂቃ ክፍተት ይላካል።
- Admin balance adjustment በplayer transaction እና platform ledger ውስጥ ይመዘገባል። Health endpoint `PRAGMA quick_check` ይጠቀማል። JSON body 1 MiB ገደብ አለው፤ multipart upload 60 MiB ነው።

## የሙከራ ውጤቶች

- `release_self_check.py` — PASS
- `realtime_path_regression_test.py` — PASS; 12 realtime `/action` payout paths በsample ተፈትነዋል።
- `rtp_regression_test.py` — PASS
- `launch_blocker_regression_test.py` — PASS; approve/reject race, Chapa guard, escrow/review guards ተፈትነዋል።
- `api_path_audit.py` — 81 frontend API paths, 81 matched, 0 unmatched.

## ከproduction በፊት አሁንም የሚፈለጉ

1. **[2026-10-11 ተሻሽሏል — code ውስጥ አለ፤ `PLATFORM_BANKROLL_ETB` በ.env ማስገባት ብቻ ቀርቷል]** ~~Bankroll exposure guard አልተጠናቀቀም።~~ ከፍተኛ payout cap ተጨምሯል፤ ግን በእውነተኛ bankroll ላይ የconcurrent exposure reservation አሁን የለም። የplatform በቀጥታ የሚገኝ bankroll መጠን እና የreserve ፖሊሲ ሳይገለጽ ይህን በደህና መገመት አይቻልም።
2. **[2026-10-11 ተሻሽሏል — `WITHDRAW_TURNOVER_MULTIPLIER` code ውስጥ አለ፤ default አሁን 3፤ በ.env ያረጋግጡ]** ~~Withdrawal turnover rule አልተጨመረም።~~ የተጠቃሚው deposit amount ስንት ጊዜ መወራረድ እንዳለበት አልተገለጸም። ይህን እንደ ግምት አልጨመርኩም፣ ምክንያቱም bonus ላይ wagering እንዳይኖር ተጠይቋል።
3. **Boom / Number / Sports ሙሉ statistical RTP suite አልተጠናቀቀም።** Number randomness እና existing source contracts ተፈትነዋል፤ የእነዚህ ሶስት ጌሞች ሙሉ Monte Carlo RTP በዚህ ሙከራ አልተካሄደም።
4. **Live-only tests አልተካሄዱም:** Docker build/start፣ HTTPS deployment፣ እውነተኛ Telegram callbacks፣ Chapa transaction፣ እና ሁለት clients/TURN የሚፈልገው WebRTC ከproduction credentials/targets ጋር መፈተን አለባቸው።
5. እውነተኛ BotFather token ከዚህ አካባቢ ሊቀየር አይችልም፤ ከlaunch በፊት በBotFather ላይ token revoke/rotate ያድርጉ።
