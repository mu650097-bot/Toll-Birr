# KDM Mini App — Render deploy (GitHub -> Render, ONE service)

API + bot + backup + proxy be-and container wist new (Render disk le-and service bicha slehone).
Plan: **Starter (paid)** — disk yifelegal. **Instance 1 bicha** (bot polling + SQLite).

## 1. BotFather (Telegram)
1. @BotFather -> /mybots -> bot -> API Token -> **Revoke current token** -> aduis token kopi adrg (yih BOT_TOKEN).
2. Bot username (be-@ yelelew) = `BOT_USERNAME`.
3. Mini App URL (behala, step 5): /mybots -> bot -> Bot Settings -> Menu Button -> Configure -> URL = `https://<service>.onrender.com/`.

## 2. Ye-ante Telegram ID
@userinfobot -> Start -> "Id: ..." = `ADMIN_ID` = `OWNER_ID`.

## 3. GitHub (PRIVATE repo)
1. github.com -> New repository -> **Private**.
2. Zip unzip adrg, wist `.gitignore` alle (.env, *.db, backups/ aytefalem).
3. `git init && git add . && git status` -> `.env` ena `*.db` be-list wist **yelem** mehonun ayu.
4. `git commit -m "kdm" && git remote add origin <repo-url> && git push -u origin main`.

## 4. Render
1. render.com -> Sign up (GitHub bet) -> **New -> Blueprint** -> private repo -> Connect (Render GitHub App-n le-repo-u fekad).
2. Render `render.yaml` yanbebal, service `kdm-mini-app` (Starter, Frankfurt, 1GB disk) yimeslal.
3. Render ye-"sync: false" values yigeltsal. Mulat:

| Variable | Ye-t new yemetaw |
|---|---|
| BOT_TOKEN | BotFather (aduis) |
| ADMIN_ID, OWNER_ID | @userinfobot |
| ACCOUNT_NAME, CBE_ACCOUNT, BOA_ACCOUNT, TELEBIRR_NUMBER | ye-ante real account (deposit yemitekebelibet) |
| ADMIN_PANEL_PIN | ye-ante meres, 8+ characters |
| SUPPORT_CONTACT | `@support_username` |
| BOT_USERNAME | BotFather (be-@ yelelew) |
| MINI_APP_URL | `https://kdm-mini-app.onrender.com/` (Render ye-service URL; sem kefeso zeyayer kalawet) |
| MINI_APP_API_URL | `https://kdm-mini-app.onrender.com/api` |
| PLATFORM_BANKROLL_ETB | winners lemekfel yaleh real ገንዘብ (0 = guard off) |
| CHAPA_* | Chapa dashboard (kefatere bicha, ke-yelem hid yitew). CHAPA_CALLBACK_URL = `https://<url>/api/payments/chapa/callback`, CHAPA_RETURN_URL = `https://<url>/` |
| TURN_URL / USERNAME / CREDENTIAL | TURN provider (WebRTC calls kalefelegu hid yitew) |

4. **Apply**. Build ~5-10 daqiqa.
5. Service URL be-Render lay yitayal. MINI_APP_URL/API_URL kesehetu (sem zeyayer kehone) -> Environment tab -> asteka -> Save -> auto redeploy.
6. Logs tab: "Telegram Mini App server listening" ena gunicorn "Booting worker" yitayal. Health: `https://<url>/api/health` -> `{"ok": true, "db_integrity": "ok"}`.
7. BotFather Menu Button URL set (step 1.3).

## 5. Be-launch befit test (small amounts)
Telegram bot -> Mini App yiket -> age gate -> 10 ብር deposit -> Admin approve (1 credit) -> withdrawal request -> reject (1 refund) -> request -> approve (extra debit yelem). Aviator/Jet crash-wait -> LOST. LAUNCH_RUNBOOK.md section 5 hulum.

## Yemichal sehtetoch
- **"Missing required environment variable"** -> Environment tab lay yetefa value mulat.
- **Bot ayimeletem** -> BOT_TOKEN sehtet, ወይም 2ተኛ instance (scaling 1 yihun).
- **Mini App ayiketem** -> MINI_APP_URL be-https:// ena be-"/" yikeshal.
- **DB hulum yetefa** -> Disk (`/app/data`) attach mehonun Settings -> Disks lay ayu.
- Backup: be-6 saat, `/app/data/backups` ena Telegram be-admin chat (file ke-49MB belay kehone message bicha).

Secrets (token, PIN, account) be-GitHub ወይም chat ፈጽሞ ayitsafu — be-Render Environment bicha.
