# ለውጥ፦ ቦነስ ማባዛት መከላከያ + የወጪ ሪፖርት

## 1. Welcome bonus የሚከፈተው የመጀመሪያ ገንዘብ ካስገቡ በኋላ ነው
- አዲስ ቅንብሮች (admin `/api/admin/platform-controls`):
  - `welcome_bonus_requires_deposit` (ነባሪ: true) — false ካደረጉ ቦነሱ እንደ ቀድሞው ሲመዘገቡ ይሰጣል።
  - `welcome_bonus_min_deposit` (ነባሪ: 10 ብር) — ቦነሱን የሚከፍት ትንሹ የመጀመሪያ ገንዘብ ማስገባት።
- ቦነሱ በ `grant_welcome_after_deposit()` (platform_controls.py) ይከፈላል፤ በአንድ ተጠቃሚ አንድ ጊዜ ብቻ።
- ሁለቱም የማጽደቂያ መንገዶች ተሸፍነዋል፦ የእጅ (kdm_mini_app.py `approve_payment`) እና Chapa (webapp_api.py `_credit_verified_chapa`)።
- ቦነሱ አሁንም play-only ነው (`welcome_bonus_locked`)።

## 2. የወጪ ሪፖርት
`GET /api/admin/bonus-report?days=30` (0 = ሁሉም ጊዜ) — admin ብቻ፦
- የተሰጠ ቦነስ በዓይነት (welcome / invite / mystery box / deposit bonus / cashback)
- ተጫዋቾች እጅ ያልተጠቀሙበት ቦነስ
- በእያንዳንዱ ጌም የቤቱ ትርፍ እና hold %
- ቦነስ ከትርፍ ምን ያህል % እንደበላ + ማስጠንቀቂያዎች (PLATFORM_BANKROLL_ETB=0 ጨምሮ)

## ማስታወሻ
`.env` ውስጥ `PLATFORM_BANKROLL_ETB` ከ0 በላይ ያድርጉ።

## 3. VIP cashback ደረጃዎች
- `/api/admin/platform-controls` ላይ፦ `cashback_tiers_enabled` (ነባሪ: ጠፍቷል) እና `cashback_tiers` (ዝርዝር)።
- ነባሪ ደረጃዎች፦ Silver (≥1,000 ውርርድ) 5%፣ Gold (≥5,000) 8%፣ Platinum (≥20,000) 12%።
- ደረጃው በcashback መስኮቱ (ነባሪ 7 ቀን) ውስጥ ባለው ውርርድ ይወሰናል፤ % ከ `cashback_mode` ጋር ይሠራል (percent_loss = ከኪሳራ፣ percent_wager = ከውርርድ)። `fixed` ሁነታ ደረጃ አይጠቀምም።
- `cashback_max_per_player` cap አሁንም ይሠራል። preview/run ላይ ለእያንዳንዱ ተጫዋች `tier` ይታያል።
- ምሳሌ ማዘመኛ፦ POST `{"cashback_tiers_enabled": true, "cashback_tiers": [{"name":"Silver","min_wager":1000,"percent":5}, ...]}`
- ሙከራ፦ `cashback_tiers_regression_test.py`

## 4. የአድሚን ገጽ (UI)
- "ዓለም አቀፍ ቅንብር" ካርድ ላይ ተጨምሯል፦ ቦነስ ከገንዘብ ማስገባት በኋላ ብቻ እንዲሰጥ ማብሪያ + ዝቅተኛ የመጀመሪያ ገንዘብ፣ እና VIP ደረጃዎች (በአንድ መስመር `ስም, ዝቅተኛ ውርርድ, መቶኛ`)።
- አዲስ "📊 የቦነስ እና Cashback ወጪ ሪፖርት" ካርድ (7 / 30 / 90 ቀን / ሁሉም ጊዜ)።
- Cashback preview ላይ የእያንዳንዱ ተጫዋች ደረጃ ይታያል።

## 5. Invite ቦነስ ከተጋበዘው ሰው የመጀመሪያ ገንዘብ በኋላ
- `invite_bonus_requires_deposit` (ነባሪ: ተከፍቷል) እና `invite_bonus_min_deposit` (ነባሪ: 10 ብር)።
- ጓደኛ ሲቀላቀል ግንኙነቱ ይመዘገባል (`invite_bonuses.paid_at` ባዶ)፤ የተጋበዘው ሰው የመጀመሪያ ገንዘብ ሲያስገባ (ከ min በላይ) ጋባዡ አንድ ጊዜ ይከፈለዋል።
- ነባር ረድፎች እንደተከፈሉ ይመዘገባሉ (ራስ-ሰር migration)። ቅንብሩን ካጠፉት ቦነሱ እንደ ቀድሞው ወዲያውኑ ይከፈላል።
- ጋባዡ ማሳወቂያ ያገኛል፤ `/api/referral` እና rewards `pending_invites` / `bonus_after_deposit` ይመልሳሉ።
- ማስታወሻ፦ የእጅ ማጽደቅ መንገዱ (kdm_mini_app.py) እዚህ አካባቢ አልተሞከረም (aiohttp አልተጫነም)፤ ኮዱ compile ያደርጋል፤ ከማስጀመርዎ በፊት አንድ የሙከራ ገንዘብ ማስገባት በእጅ ያጽድቁ።

## 6. የባለቤት Telegram ማስጠንቀቂያ
- በየ15 ደቂቃ ይፈትሻል፤ ቦነስ + cashback ከቤቱ ትርፍ ከ `cost_alert_bonus_pct` (ነባሪ 50%) ሲበልጥ ወይም ትርፉ አሉታዊ ሲሆን ለ `OWNER_ID` መልዕክት ይልካል።
- ቅንብሮች፦ `cost_alert_enabled`፣ `cost_alert_window_days` (7)፣ `cost_alert_bonus_pct` (50)፣ `cost_alert_min_bonus` (100 ብር)።
- ተመሳሳይ ማስጠንቀቂያ በ24 ሰዓት አንድ ጊዜ ብቻ፤ በብዙ worker ቢሮጥም አንድ ጊዜ ይላካል።
- ለማጥፋት፦ `DISABLE_COST_ALERT_WORKER=1`።
