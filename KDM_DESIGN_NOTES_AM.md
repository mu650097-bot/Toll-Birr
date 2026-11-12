# KDM Games UI ማሻሻያ (ከፎቶው ጋር እንዲመሳሰል)

UI ብቻ ተቀይሯል — game logic፣ math፣ payout፣ API እና backend አልተነኩም።

## አዲስ ፋይሎች
- `kdm_design.css` — ሙሉ ዲዛይኑ (navy ጀርባ፣ አንድ ሰማያዊ accent፣ አረንጓዴ ለገንዘብ/ጨዋታ ቁልፍ ብቻ)። ከሁሉም CSS በኋላ ይጫናል።
- `kdm_ui.js` — sidebar/drawer፣ header (back, ርዕስ, user chip)፣ Home vs Games እይታ፣ wallet አቋራጮች፣ ½ / 2× / Max የውርርድ ቁልፎች። ምንም API አይጠራም።

## የተቀየሩ ፋይሎች
- `index.html` — አዲስ header፣ sidebar፣ hero (PLAY • WIN • WITHDRAW)፣ wallet balance card፣ withdraw method ካርዶች (CBE/BOA/Telebirr)፣ 4-tab bottom nav (Home/Games/Wallet/Profile)፣ SVG icons።
- `onboarding.js` — ለአዲሶቹ ጽሑፎች የአማርኛ/English ትርጉም ብቻ ተጨምሯል።

## ባህሪ
- ስልክ፦ bottom nav + ☰ drawer። ኮምፒውተር (≥1024px)፦ ግራ sidebar።
- Home = Popular Games፤ "View All" / Games = ሁሉም ጨዋታዎች ከ tabs እና search ጋር።
- Aviator እና ሌሎች ጨዋታዎች በኮምፒውተር ላይ ሁለት ዓምድ (ግራ መድረክ፣ ቀኝ የውርርድ ፓነል)።
- የገንዘብ ምልክት ETB።

## ተፈትሿል
- `release_self_check.py` → SELF_CHECK=PASS (RTP እና launch-blocker regression ጨምሮ)።
- በChromium በ360 / 390 / 1280 / 1440 ስፋት ተፈትሿል (mock API)። በRender/Telegram ላይ live ሙከራ አይደለም።

## የጨዋታ ሥዕሎች (አዲስ)
- `kdm_art.js` — ለ20ዎቹ ጨዋታዎች እና ለ hero (ዘውድ፣ ዋንጫ፣ ሳንቲም) ራሴ የሳልኳቸው original SVG ሥዕሎች። emoji-ዎችን በነሱ ይተካል። ምንም ነገር ቢሳሳት emoji እንደነበረ ይቀራል።
