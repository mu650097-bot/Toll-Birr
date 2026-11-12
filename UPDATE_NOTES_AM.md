# የዚህ ማሻሻያ ማስታወሻ

1. Recent Big Wins: እያንዳንዱ ካርድ አሁን ያሸነፈበትን game ስም + አይኮን ያሳያል (webapp_api.py `/api/wins/recent` -> `game`).
2. Withdraw: session ከ1 ሰዓት በላይ ሲቆይ ይከለከል ነበር -> አሁን 6 ሰዓት (env `SENSITIVE_INITDATA_MAX_AGE_SEC`). አዲስ `/api/withdraw/info` ቀሪ turnover እና ዕለታዊ ገደብ ያሳያል።
3. Data እንዳይጠፋ (Render free): `backup_db.py --pin` በየ5 ደቂቃ (ዳታ ሲቀየር) DB ን ለAdmin Telegram ይልካል + pin ያደርጋል። ሲነሳ `restore_db.py` ከpinned backup ይመልሳል። `render.free.yaml` + keep-alive ping ተጨምሯል።
4. Balance auto-refresh: በየ5 ሰከንድ (ከgame ውጭ)፤ game ውስጥ deposit ሲገባ ብቻ ይዘምናል (የround ውጤት እንዳይታይ)።
5. Marketplace: photo/video/voice ሲገዛ ፋይሉ ከTelegram storage (file_id) ወደ ገዢው Telegram ID በቀጥታ ይላካል፤ ከተላከ ክፍያ ወዲያው ለአቅራቢው ይለቀቃል (commission ተቀንሶ)፤ ካልተላከ ሙሉ refund። `AUTO_DELIVER_MEDIA=0` ለማጥፋት።

## ዙር 2
6. **Keno 80** (ወደ አዲስ): `keno80.py` + `keno80.js` + `keno80.css`. Classic (የጋራ ዙር: 50 ሰከንድ bet + 20 ኳስ አንድ በአንድ) እና Instant (የግል ወዲያው)። 1–10 ቁጥር ከ80፤ 20 ይወጣል። Paytable በራሱ የሚሰላ (hypergeometric) ስለሆነ RTP = 1 − house edge (Admin የሚያስቀምጠው 'keno' edge)። Live/Top bets እውነተኛ bets ብቻ ናቸው።
7. **Promo Post** (`promo_post.py`): Admin/Manager/Owner: Admin panel → 📢 ወይም `/promo` → ማንኛውም message (text/photo/video/GIF) → Preview + «🎮 አሁን ይጫወቱ» button → ✅ ላክ / + Channel። Formatting እና emoji እንዳለ ይቀራል (copy_message)። የታገዱ እና self-exclude ያደረጉ አይደርሳቸውም። Owner ሌላ staff ሲልክ ማሳወቂያ ያገኛል። Channel: `ANNOUNCEMENT_CHANNEL_ID` + `BOT_USERNAME` env።
