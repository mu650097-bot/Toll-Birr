# የMarketplace ማሻሻያ እና የRefresh ማስታወሻ

- የእኔ አገልግሎቶች ክፍል አሁን ርዕስ፣ መግለጫ፣ ካታጎሪ፣ የአገልግሎት አይነት፣ ዋጋ እና ቆይታ ጊዜ ማስተካከል ያስችላል።
- Backend በTelegram-authenticated user ID የፖስቱን ባለቤትነት ይፈትሻል፤ ሌላ ሰው የሌላውን ፖስት ማስተካከል አይችልም።
- ይዘት/ዋጋ ሲቀየር ፖስቱ ለmoderation እንደገና ይላካል፤ እስኪፈቀድ ድረስ በpublic marketplace ላይ አይታይም።
- Telegram Mini App ወደ foreground ሲመለስ balance እና ክፍት Marketplace ዳግም ይጫናሉ።
- Render Blueprint ውስጥ `DB_FILE=/app/data/auction_wallet.db` እና `/app/data` persistent disk አስቀድሞ ተዋቅረዋል። በRender ላይ ይህ Blueprint/ዲስክ እንዲጠቀም ማረጋገጥ አለበት፤ ያለውን DB_FILE በሌላ path መቀየር ወይም persistent disk ማስወገድ የውሂብ መጥፋት አደጋ ይፈጥራል።

## ያልተረጋገጡ ነገሮች

- ይህ ምንጭ-ኮድ ማሻሻያ ነው፤ በተጠቃሚው Render አካውንት ላይ deploy ወይም live payment/withdrawal አልተፈጸመም።
- የMarketplace listing ሚዲያ upload በአዲስ ፖስት ጊዜ ያለውን Telegram storage መንገድ ይጠቀማል፤ የተቀመጠውን የsample ፎቶ/ቪዲዮ/ድምፅ በedit ጊዜ መተካት በዚህ ማሻሻያ አልተጨመረም።
- Live withdrawal ለመፈተን Render HTTPS, Telegram auth, DB, admin approval እና payout notifications ያስፈልጋሉ።
