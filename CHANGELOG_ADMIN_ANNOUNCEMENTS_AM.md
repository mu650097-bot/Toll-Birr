# KDM Mini App — የማሻሻያ ማስታወሻ

- Admin Announcements ላይ እስከ 5 የHTTPS ፎቶ URL ማስገቢያዎች ተጨምረዋል።
- በLobby የመጨረሻው የተላከ ማስታወቂያ ይታያል፤ ፎቶዎች በየ1 ሰከንዱ ይቀያየራሉ።
- Telegram broadcast ከ1 በላይ ፎቶ ሲኖር sendMediaGroup ይጠቀማል።
- ለannouncement photo list የDB migration ተጨምሯል፤ ነባር DB ላይ የሚሰራ ነው።
- Telegram native BackButton በsub-page ላይ ወደ Lobby ይመልሳል፤ Lobby ላይ ሲሆን Close ያደርጋል።
- Deposit screenshot + Approve/Reject ያለውን ነባር ፍሰት አልተቀየረም። Shamo ነባሩ ጨዋታ እንደነበረ ተጠብቋል።

## የፎቶ ማስገቢያ
Admin Panel → Announcements → በHTTPS የሚደረስባቸውን የፎቶ URL ዎች አንድ በአንድ በመስመር ያስገቡ (እስከ 5)። ይህ ስሪት ከስልክ ቀጥታ file-upload አያቀርብም።
