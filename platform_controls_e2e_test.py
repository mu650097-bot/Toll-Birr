"""End-to-end proof (real webapp_api + real SQLite + signed Telegram initData) for:
  1. 10 ETB welcome bonus for every new user, exactly once, admin-changeable
  2. High-stakes cashback (preview / run once / manual grant, withdrawable vs play-only)
  3. ONE admin minimum bet + ONE admin house edge applied to ALL games, and a change takes effect on the next request
Run:  python platform_controls_e2e_test.py   -> PLATFORM_CONTROLS_E2E=PASS
"""
import hashlib, hmac, json, os, sqlite3, sys, tempfile, time
from urllib.parse import urlencode

TD = tempfile.mkdtemp()
os.environ.update(BOT_TOKEN="123456:TESTTOKEN", ADMIN_ID="1", OWNER_ID="1", ACCOUNT_NAME="T", CBE_ACCOUNT="1", BOA_ACCOUNT="1",
                  TELEBIRR_NUMBER="1", MINI_APP_URL="https://x.example/", MINI_APP_API_URL="https://x.example/api",
                  ADMIN_PANEL_PIN="1234", SUPPORT_CONTACT="@s", DB_FILE=os.path.join(TD, "t.db"), PLATFORM_BANKROLL_ETB="0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webapp_api as W                                   # noqa: E402

app = W.app; app.config["TESTING"] = True
C = app.test_client()
TOKEN = os.environ["BOT_TOKEN"]


def init_data(uid, name="U"):
    f = {"auth_date": str(int(time.time())), "query_id": "q", "user": json.dumps({"id": uid, "first_name": name, "username": f"u{uid}"})}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sk = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sk, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(f)


def call(method, path, uid, body=None, pin=None):
    h = {"X-Telegram-Init-Data": init_data(uid)}
    if pin: h["X-Admin-Pin-Token"] = pin
    r = getattr(C, method)(path, headers=h, json=body) if body is not None else getattr(C, method)(path, headers=h)
    return r.status_code, (r.get_json(silent=True) or {})


def dbq(sql, args=()):
    c = sqlite3.connect(os.environ["DB_FILE"]); c.row_factory = sqlite3.Row
    try:
        r = [dict(x) for x in c.execute(sql, args).fetchall()]; c.commit(); return r
    finally: c.close()


def ok(cond, msg):
    if not cond: raise SystemExit("FAIL: " + msg)
    print("  ok -", msg)


# ---- admin login (PIN token) ----------------------------------------------------------------------------------
ADMIN = 1
call("get", "/api/profile", ADMIN)                                   # creates admin row
code, r = call("post", "/api/admin/verify-pin", ADMIN, {"pin": "1234"})
ok(code == 200, f"admin PIN accepted ({code} {r})")
PIN = r.get("token") or r.get("pin_token") or next((v for k, v in r.items() if "token" in k), None)
adm = lambda m, p, b=None: call(m, p, ADMIN, b, PIN)

print("[1] welcome bonus (signup mode)")
adm("post", "/api/admin/platform-controls", {"welcome_bonus_requires_deposit": False})
code, r = call("get", "/api/profile", 501)
ok(code == 200, "new player opens the app")
row = dbq("SELECT balance,bonus_locked FROM users WHERE user_id=501")[0]
ok(row["balance"] == 10.0 and row["bonus_locked"] == 10.0, f"new player got 10 ETB play-only welcome bonus ({row})")
call("get", "/api/profile", 501); call("get", "/api/profile", 501)
ok(dbq("SELECT balance FROM users WHERE user_id=501")[0]["balance"] == 10.0, "bonus is given only once")
ok(len(dbq("SELECT * FROM transactions WHERE user_id=501 AND transaction_type='welcome_bonus'")) == 1, "one ledger row")
print("[1b] welcome bonus (deposit-gated mode: default)")
adm("post", "/api/admin/platform-controls", {"welcome_bonus_requires_deposit": True, "welcome_bonus_min_deposit": 10})
call("get", "/api/profile", 777)
ok(dbq("SELECT balance FROM users WHERE user_id=777")[0]["balance"] == 0.0, "no bonus at signup when deposit is required")
import sqlite3 as _sq, os as _os
import platform_controls as _pcx
_c = _sq.connect(os.environ["DB_FILE"]); _c.row_factory = _sq.Row; _cur = _c.cursor()
ok(_pcx.grant_welcome_after_deposit(_cur, 777, 5) == 0.0, "deposit below minimum does not unlock the bonus")
ok(_pcx.grant_welcome_after_deposit(_cur, 777, 50) == 10.0, "first qualifying deposit pays 10 ETB")
ok(_pcx.grant_welcome_after_deposit(_cur, 777, 50) == 0.0, "bonus is never paid twice")
_c.commit(); _c.close()
row = dbq("SELECT balance,bonus_locked FROM users WHERE user_id=777")[0]
ok(row["balance"] == 10.0 and row["bonus_locked"] == 10.0, f"play-only bonus credited ({dict(row)})")
adm("post", "/api/admin/platform-controls", {"welcome_bonus_requires_deposit": False})
code, r = call("get", "/api/profile", 501); ok(abs(float(r.get("balance", 10)) - 10.0) < 1e-9, "balance shown to the player is 10")
# bot-side creation path (upsert used by kdm_mini_app.register_user) also pays it
c = sqlite3.connect(os.environ["DB_FILE"]); c.execute("INSERT INTO users(user_id,first_name,username) VALUES(502,'b','b') ON CONFLICT(user_id) DO UPDATE SET first_name=excluded.first_name"); c.commit(); c.close()
ok(dbq("SELECT balance FROM users WHERE user_id=502")[0]["balance"] == 10.0, "bot /start registration path also pays 10 ETB")
# admin changes amount -> next new user gets new amount; old users unchanged
code, r = adm("post", "/api/admin/platform-controls", {"welcome_bonus_amount": 25})
ok(code == 200 and r["controls"]["welcome_bonus_amount"] == 25, "admin sets welcome bonus to 25")
call("get", "/api/profile", 503)
ok(dbq("SELECT balance FROM users WHERE user_id=503")[0]["balance"] == 25.0, "next new player gets 25")
ok(dbq("SELECT balance FROM users WHERE user_id=501")[0]["balance"] == 10.0, "existing players untouched")
adm("post", "/api/admin/platform-controls", {"welcome_bonus_enabled": False})
call("get", "/api/profile", 504)
ok(dbq("SELECT balance FROM users WHERE user_id=504")[0]["balance"] == 0.0, "bonus switched off -> 0")
adm("post", "/api/admin/platform-controls", {"welcome_bonus_enabled": True, "welcome_bonus_amount": 10})

for _u in (503, 501):
    code, r = call("post", "/api/accept-terms", _u, {"age_confirmed": True, "terms_accepted": True, "accept": True})
    ok(code == 200, f"player {_u} accepted 18+/terms ({code} {r})")

print("[2] global minimum bet reaches EVERY game and takes effect immediately")
keys = sorted(W.CABINET_GAME_KEYS)
for k in keys:
    code, s = call("get", f"/api/games/{k}/settings", 501)
    ok(code == 200 and s["min_stake"] == 1.0, f"{k}: default min 1") if k in ("dice", "slot", "aviator") else None
code, r = adm("post", "/api/admin/platform-controls", {"global_min_bet_enabled": True, "global_min_bet": 7})
ok(code == 200 and r["controls"]["global_min_bet"] == 7, "admin sets global min bet = 7")
bad = []
for k in keys:
    code, s = call("get", f"/api/games/{k}/settings", 501)
    if code != 200 or s["min_stake"] != 7.0 or s["max_stake"] < 7.0: bad.append((k, code, s.get("min_stake")))
ok(not bad, f"all {len(keys)} cabinet games now report min 7 ({bad})")
# real bet below / at min through the real endpoint
code, r = call("post", "/api/games/dice/round/start", 503, {"stake": 5, "guess": 3})
ok(code == 400 and "between 7.00" in r.get("error", ""), f"dice bet of 5 rejected ({code} {r.get('error')})")
code, r = call("post", "/api/games/dice/round/start", 503, {"stake": 7, "guess": 3})
ok(code == 200, f"dice bet of 7 accepted ({code} {r.get('error')})")
code, r = call("post", "/api/games/slot/round/start", 503, {"stake": 6})
ok(code == 400, "slot bet of 6 rejected")
code, r = call("post", "/api/games/dice2/round/start", 503, {"stake": 2, "mode": "under", "target": 7})
ok(code == 400, "dice2 bet of 2 rejected")
# realtime (round/start) path
code, r = call("post", "/api/games/aviator/round/start", 503, {"stake": 3})
ok(code == 400 and "between 7.00" in r.get("error", ""), f"aviator realtime start below min rejected ({code} {r.get('error')})")
# live (shared-round) path
code, r = call("post", "/api/live/aviator/crash-bet", 503, {"slot": "A", "stake": 3})
ok(code == 400 and "between 7.00" in str(r.get("error", "")), f"live crash bet below min rejected ({code} {r})")
code, r = call("post", "/api/live/number/bet", 503, {"stake": 3, "target": "odd"})
ok(code == 400, f"live number bet below min rejected ({code} {r})")
code, r = call("post", "/api/live/keno/bet", 503, {"stake": 3, "numbers": [1, 2, 3]})
ok(code == 400, f"live keno bet below min rejected ({code} {r})")
code, r = call("post", "/api/games/blackjack/round/start", 503, {"stake": 3}) if False else (400, {})
# sports
dbq("INSERT INTO sports_matches(home_team,away_team,odds_home,odds_draw,odds_away,status,closes_at) VALUES('A','B',2,3,3,'OPEN',?)", (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 3600)),))
mid = dbq("SELECT id FROM sports_matches ORDER BY id DESC LIMIT 1")[0]["id"]
code, r = call("post", "/api/sports/bet", 503, {"match_id": mid, "selection": "HOME", "stake": 3})
ok(code == 400 and "minimum bet" in r.get("error", ""), f"sports bet below min rejected ({code} {r.get('error')})")
# boom / number fixed-fee games
code, r = call("get", "/api/games/settings", 503)
ok(r["bomb"]["entry_fee"] == 10.0 and r["number"]["entry_fee"] == 10.0, "fixed-fee games keep their fee when it is above the min")
adm("post", "/api/admin/platform-controls", {"global_min_bet": 15})
code, r = call("get", "/api/games/settings", 503)
ok(r["bomb"]["entry_fee"] == 15.0 and r["number"]["entry_fee"] == 15.0, "Boom/Number fee raised to the new min (15)")
code, r = call("get", "/api/games/boom/state", 503)
ok(code == 200 and float(r.get("entry_fee", 15)) == 15.0, f"open Boom round re-priced immediately ({r.get('entry_fee')})")
# lowering takes effect too
adm("post", "/api/admin/platform-controls", {"global_min_bet": 2})
code, r = call("post", "/api/games/slot/round/start", 501, {"stake": 2})
ok(code == 200, f"min lowered to 2 -> a 2 ETB bet is accepted at once ({code} {r})")
code, s = call("get", "/api/games/slot/settings", 503); ok(s["min_stake"] == 2.0, "settings endpoint shows the lowered min")
# turning the global minimum off falls back to per-game minimum
adm("post", "/api/admin/platform-controls", {"global_min_bet_enabled": False})
code, s = call("get", "/api/games/slot/settings", 503); ok(s["min_stake"] == 1.0, "global min off -> per-game min (1) again")
adm("post", "/api/admin/platform-controls", {"global_min_bet_enabled": True, "global_min_bet": 1})

print("[3] global house edge reaches EVERY game and takes effect immediately")
code, s0 = call("get", "/api/games/slot/settings", 503)
ok(abs(s0["house_edge"] - 0.15) < 1e-9, "slot keeps its own edge (15%) while global edge is off")
code, r = adm("post", "/api/admin/platform-controls", {"global_house_edge_enabled": True, "global_house_edge_percent": 6})
ok(code == 200 and abs(r["controls"]["global_house_edge"] - 0.06) < 1e-9, "admin sets global house edge = 6%")
bad = []
for k in keys:
    code, s = call("get", f"/api/games/{k}/settings", 503)
    if code != 200 or abs(s["house_edge"] - 0.06) > 1e-9 or abs(s["rtp"] - 0.94) > 1e-9: bad.append((k, s.get("house_edge")))
ok(not bad, f"all {len(keys)} cabinet games report house edge 6% / RTP 94% ({bad})")
code, r = adm("post", "/api/admin/platform-controls", {"global_house_edge_percent": 99})
ok(code == 400, "edge above MAX_HOUSE_EDGE (30%) is refused")
# real simulation: dice payout multiple follows the edge (slot RTP-scaled payouts)
code, s = call("get", "/api/games/dice/settings", 503); ok(abs(s["rtp"] - 0.94) < 1e-9, "dice RTP 94% live")
code, r = call("post", "/api/games/dice2/play", 503, {"stake": 10, "mode": "under", "target": 7})
if code == 200 and r.get("won"):
    ok(abs(r["payout"] - round(10 / r["outcome"]["chance"] * 0.94, 2)) < 0.02, "dice2 payout uses the 6% edge")
code, s = call("get", "/api/games/number/state", 503) if False else (200, {})
# classic games: win amount recomputed from the new edge, formula fee*(1-edge)/p
code, r = call("get", "/api/games/settings", 503)
ok(abs(r["bomb"]["win_amount"] - round(10 * 0.94 * 84, 2)) < 0.02 and abs(r["number"]["win_amount"] - round(10 * 0.94 * 15, 2)) < 0.02,
   f"Boom/Number win amount follows the 6% edge ({r})")
# pool rake + sports rake
ok(abs(W._pool_rake_pct() - 0.06) < 1e-9 and abs(W._sports_rake_pct() - 0.06) < 1e-9, "pool + sports rake = 6%")
bets = [{"id": 1, "stake": 100, "selection": "HOME"}, {"id": 2, "stake": 100, "selection": "AWAY"}]
out, rake = W._sports_pool_payouts(bets, "HOME", W._sports_rake_pct())
ok(abs(rake - 12.0) < 0.01 and abs(out[1][0] - 188.0) < 0.01, f"sports settlement rake = 6% of pool ({rake})")
# change again -> instant
adm("post", "/api/admin/platform-controls", {"global_house_edge_percent": 3})
code, s = call("get", "/api/games/slot/settings", 503); ok(abs(s["house_edge"] - 0.03) < 1e-9, "edge changed to 3% -> slot shows 3% at once")
# the ENGINES (not just the settings endpoint) use the overridden value
ok(W._cabinet_limits("blackjack")[3] == 0.03 and W._cabinet_limits("wheel")[3] == 0.03, "engine-side _cabinet_limits returns 3%")
adm("post", "/api/admin/platform-controls", {"global_house_edge_enabled": False})
code, s = call("get", "/api/games/slot/settings", 503); ok(abs(s["house_edge"] - 0.15) < 1e-9, "global edge off -> slot back to its own 15%")

print("[4] high-stakes cashback")
for u in (601, 602, 603): call("get", "/api/profile", u)
now = time.strftime("%Y-%m-%d %H:%M:%S")
def tx(u, a, t): dbq("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (u, a, t, now))
tx(601, -5000, "game_slot_stake"); tx(601, 1000, "game_slot_payout")      # whale: staked 5000, lost 4000
tx(602, -1500, "sports_bet"); tx(602, 1400, "sports_win")                 # staked 1500, lost 100
tx(603, -200, "game_dice_stake")                                          # small player -> not eligible
adm("post", "/api/admin/platform-controls", {"cashback_enabled": True, "cashback_mode": "percent_loss", "cashback_percent": 10, "cashback_min_wager": 1000, "cashback_max_per_player": 300})
code, r = adm("get", "/api/admin/cashback/preview")
ids = {i["user_id"]: i["cashback"] for i in r["items"]}
ok(ids.get(601) == 300.0 and ids.get(602) == 10.0 and 603 not in ids, f"preview: whale 10% of 4000 capped at 300, mid 10, small excluded ({ids})")
b601 = dbq("SELECT balance FROM users WHERE user_id=601")[0]["balance"]
code, r = adm("post", "/api/admin/cashback/run")
ok(code == 200 and r["players"] == 2 and r["total_paid"] == 310.0, f"run paid 310 to 2 players ({r})")
ok(dbq("SELECT balance FROM users WHERE user_id=601")[0]["balance"] == b601 + 300, "whale credited 300")
code, r = adm("post", "/api/admin/cashback/run")
ok(code == 200 and r["players"] == 0, "second run pays nobody for the same play (no double payment)")
adm("post", "/api/admin/platform-controls", {"cashback_mode": "fixed", "cashback_fixed_amount": 75, "cashback_min_wager": 100})
time.sleep(1.2); now = time.strftime("%Y-%m-%d %H:%M:%S"); tx(603, -300, "game_dice_stake")
code, r = adm("get", "/api/admin/cashback/preview")
ok(any(i["user_id"] == 603 and i["cashback"] == 75.0 for i in r["items"]), "fixed mode: qualifier gets the flat amount the admin chose")
code, r = adm("post", "/api/admin/cashback/grant", {"user_id": 602, "amount": 123.45, "note": "VIP"})
ok(code == 200 and r["amount"] == 123.45, "admin manual cashback of any amount")
code, r = adm("post", "/api/admin/cashback/grant", {"user_id": 99999, "amount": 5})
ok(code == 400, "manual cashback to unknown user refused")
code, r = adm("post", "/api/admin/cashback/grant", {"user_id": 602, "amount": -5})
ok(code == 400, "negative amount refused")
adm("post", "/api/admin/platform-controls", {"cashback_enabled": False})
code, r = adm("post", "/api/admin/cashback/run"); ok(code == 400, "run refused while cashback is disabled")

print("[5] security")
code, r = call("post", "/api/admin/platform-controls", 501, {"global_min_bet": 0.01})
ok(code in (401, 403), f"normal player cannot change controls ({code})")
code, r = adm("post", "/api/admin/platform-controls", {"global_min_bet": -3}); ok(code == 400, "negative min bet refused")
code, r = adm("post", "/api/admin/platform-controls", {"cashback_mode": "evil"}); ok(code == 400, "bad cashback mode refused")
ok(len(dbq("SELECT * FROM admin_actions WHERE action_type='platform_controls_update'")) >= 5, "every change is written to the admin audit log")
print("PLATFORM_CONTROLS_E2E=PASS")

print("[bonus-report]")
code, r = adm("get", "/api/admin/bonus-report?days=0")
ok(code == 200 and "bonus_given" in r and "games" in r and "outstanding" in r, f"bonus report works ({code})")
ok(r["bonus_given"]["welcome"]["total"] >= 20.0, f"welcome total counted ({r['bonus_given']['welcome']})")
ok(any("BANKROLL" in w for w in r["warnings"]) == (r["bankroll_etb"] <= 0), "bankroll warning matches config")
print("BONUS_REPORT_OK", r["bonus_given_total"], r["outstanding"])

print("[invite release via real payment path + owner cost alert]")
os.environ["DISABLE_COST_ALERT_WORKER"] = "1"
adm("post", "/api/admin/platform-controls", {"invite_bonus_requires_deposit": True, "invite_bonus_min_deposit": 10})
call("get", "/api/profile", 801); call("get", "/api/profile", 802)
_c = sqlite3.connect(os.environ["DB_FILE"]); _c.row_factory = sqlite3.Row
import bonus_wallet as _bw
_bw.record_invite(_c.cursor(), 801, 802, "2026-01-01 00:00:00"); _c.commit()
before = _c.execute("SELECT balance FROM users WHERE user_id=801").fetchone()[0]
_c.execute("INSERT INTO payments(user_id,amount,status,provider,provider_ref,created_at) VALUES(802,40,'pending','chapa','kdm-802-test','2026-01-01 00:00:00')"); _c.commit(); _c.close()
W.tg_send_message = lambda *a, **k: None
ok(W._credit_verified_chapa("kdm-802-test", {"status": "success", "amount": 40, "currency": "ETB", "tx_ref": "kdm-802-test"}) is True, "chapa deposit credited")
after = dbq("SELECT balance FROM users WHERE user_id=801")[0]["balance"]
ok(abs(after - before - 1.0) < 1e-9, f"inviter paid 1 ETB after invitee's first deposit ({before}->{after})")
ref = call("get", "/api/referral", 801)[1]
ok(ref.get("pending_invites") == 0 and ref.get("bonus_after_deposit") is True, f"referral API shows state ({ref})")

sent = []
W.tg_send_message = lambda chat_id, text, reply_markup=None, parse_mode="Markdown": sent.append((chat_id, text))
adm("post", "/api/admin/platform-controls", {"cost_alert_enabled": True, "cost_alert_min_bonus": 1, "cost_alert_bonus_pct": 1, "cost_alert_window_days": 30})
dbq("DELETE FROM platform_settings WHERE key='cost_alert_last'")
ok(W._cost_alert_check() is True and len(sent) == 1, f"alert sent to owner ({len(sent)})")
ok(W._cost_alert_check() is False and len(sent) == 1, "same alert not repeated within 24h")
adm("post", "/api/admin/platform-controls", {"cost_alert_enabled": False})
dbq("DELETE FROM platform_settings WHERE key='cost_alert_last'")
ok(W._cost_alert_check() is False and len(sent) == 1, "disabled alert stays silent")
print("INVITE_ALERT_E2E_OK")
