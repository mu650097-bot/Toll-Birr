# Admin Post ገንቢ (Bot ውስጥ)

## አጠቃቀም
Bot → Admin Panel → **📢 ማስታወቂያ Post ላክ**

1. **ጨዋታ ይምረጡ** -- Post «▶️ አሁን ይጫወቱ» ቁልፍ ይኖረዋል፤ ተጫዋቹ ሲነካ Mini App በቀጥታ በዚያ ጨዋታ ላይ ይከፈታል.
   (🏠 ሎቢ / ⚽ Sports / 🛍 Marketplace / 🎡 Lucky Spin / ማንኛውም ጨዋታ / «ቁልፍ አይኑር»)
2. **Post ይላኩ** -- ጽሑፍ፣ 📸 ፎቶ፣ 🎥 ቪዲዮ ወይም GIF (ፎቶ ከሆነ ጽሑፉ Caption ላይ). Bold፣ Quote፣ Emoji ሁሉ እንዳለ ይቀራል.
3. **ቅድመ እይታ** ያያሉ -- ከዚያ **ለሁሉም** / **Channel ብቻ** / **Users ብቻ** ይምረጡ.
4. (ከፈለጉ) **➕ ተጨማሪ ቁልፎች** -- አንድ መስመር = አንድ ቁልፍ:

```
ሊቨርፑል | vote
አርሰናል | vote
Keno ተጫወት | game:keno
Channel | https://t.me/yourchannel
```

* `vote` ቁልፎች ጎን ለጎን ይታያሉ፤ አንድ ሰው አንድ ድምጽ (ሃሳቡን መቀየር ይችላል). ጠቅላላ ድምጽ በቁልፉ ላይ ይታያል: `ሊቨርፑል (12)`.
* ሁሉንም ቁልፎች ለማጥፋት `clear` ይጻፉ. ለመሰረዝ `/cancel`.
* ፎቶ Post ሲላክ በ App ሎቢ ላይ banner ሆኖ ይለጠፋል (ሲነካ ወደተመረጠው ጨዋታ ይወስዳል).

## Channel ላይ ቁልፉ እንዲሰራ (አንድ ጊዜ ብቻ)
Telegram Channel ውስጥ Mini App ቁልፍ መሆን የሚችለው `t.me` ሊንክ ብቻ ነው. ስለዚህ:

* Render **Environment** ውስጥ `BOT_USERNAME` ያስገቡ (ያለ @).
* BotFather → ቦትዎን ይምረጡ → **Bot Settings → Configure Mini App** (Main Mini App) → የ Mini App URL ያስገቡ.
  * Main Mini App ካልተዋቀረ ግን «Direct Link Mini App» (`/newapp`) ፈጥረው short name ን `MINI_APP_SHORT_NAME` ላይ ያስገቡ.
* `ANNOUNCEMENT_CHANNEL_ID` (ለምሳሌ `-1001234567890`) ያስገቡና ቦቱን የ Channel admin ያድርጉ.

ለ Users (የግል ቻት) ቁልፉ እውነተኛ Mini App ቁልፍ ስለሆነ ምንም ተጨማሪ ቅንብር አያስፈልገውም.
