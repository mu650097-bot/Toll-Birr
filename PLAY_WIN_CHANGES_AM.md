# Play Win — የተቀየሩ ፋይሎች

ፋይሎቹን በ Tolo-main ውስጥ ባሉት በመተካት Render ላይ እንደገና Deploy ያድርጉ (bot እና API ሁለቱም)።

| ፋይል | ለውጥ |
|---|---|
| kdm_mini_app.py | Keyboard + Menu ቁልፍ ስም «Play Win 🥳»፤ /start ref_ እና g_ link ማስተናገድ (ጋባዡን ማስቀመጥ + «Play Win 🥳» ቁልፍ) |
| webapp_api.py | Invite link ማስተካከያ፤ `/api/referral/claim`፤ አድሚን ማስታወቂያ ጨዋታ ጋር (private = web_app ቁልፍ፣ channel = t.me ሊንክ)፤ Chapa ስም |
| config.py | `BOT_USERNAME` ላይ `@` ይወገዳል (ችግሩ ይሄ ነበር: `t.me/@Kingbirrbot` = "Username not found") |
| index.html | Title / Header ስም «Play Win»፤ በአድሚን ማስታወቂያ ላይ የጨዋታ መምረጫ |
| app.js | ማስታወቂያ ሲላክ ጨዋታ ይላካል፤ `startapp=ref_` ይመዘገባል፤ Share ጽሑፍ |

## Render Environment (አንዱን ብቻ ያስገቡ — Invite link በቀጥታ Mini App እንዲከፍት)
* `BOT_USERNAME` = `Kingbirrbot` (@ ቢኖርም አሁን ችግር የለውም)
* BotFather ላይ **Main Mini App** ካዋቀሩ → `MINI_APP_MAIN=1`
* ወይም BotFather `/newapp` short name → `MINI_APP_SHORT_NAME=<short name>`
* ሁለቱም ከሌሉ Invite link `t.me/<bot>?start=ref_ID` ይሆናል፤ Bot «Play Win 🥳» ቁልፍ ያሳያል (አንድ ጊዜ መንካት)።

BotFather ላይ የ Mini App ስሙን «Play Win» ብለው ይቀይሩ (Bot Settings → Configure Mini App) — ይህ በ Telegram በኩል የሚታይ ስለሆነ በኮድ መቀየር አይቻልም።

## ቦነስ + Mystery Box + Level
* **የጋበዙ ቦነስ:** ለእያንዳንዱ ለጋበዙት ሰው 1 ብር (Render env `INVITE_BONUS_ETB` ለመቀየር)። ቦነሱ ለጨዋታ ብቻ ነው፤ ማውጣት የሚቻለው `balance − bonus_locked` ነው። ቦነስ ባለው ሰው Marketplace ላይም ሊጠቀሙት አይችሉም።
* **Mystery Box:** በየ 60 ደቂቃ ነፃ። Admin Panel → «📦 Mystery Box» ላይ Enabled ያድርጉ፣ ሽልማቶችን (`መጠን:ዕድል`)፣ Daily budget እና ደቂቃውን ያስገቡ። **በ default ዝግ ነው።** ሽልማቱ እንደ ቦነስ (ለጨዋታ ብቻ) ይገባል።
* **Level:** ከተወራረደው ጠቅላላ ብር (Bronze → King)፤ Profile ገጽ ላይ ከ Challenge እና Mystery Box ጋር ይታያል።
* አዲስ ፋይሎች: `bonus_wallet.py`, `rewards_v9.py`, `rewards.js`
