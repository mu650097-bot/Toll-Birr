"""Offline release gate. Fails closed on critical source/package regressions."""
from pathlib import Path
import ast, subprocess, sys, tempfile, sqlite3
ROOT=Path(__file__).resolve().parent
errors=[]
def need(cond,msg):
    if not cond: errors.append(msg)

for name in ("webapp_api.py","kdm_mini_app.py","backup_db.py","config.py","extended_schema.py","realtime_engine_v3.py"):
    p=ROOT/name
    need(p.is_file(),f"missing file: {name}")
    if p.is_file():
        try:
            ast.parse(p.read_text(encoding='utf-8'),filename=str(p)); print(f"PASS syntax: {name}")
        except Exception as e: errors.append(f"syntax {name}: {e}")
try:
    r=subprocess.run(["node","--check",str(ROOT/"app.js")],capture_output=True,text=True)
    need(r.returncode==0,"JavaScript syntax failed")
    print("PASS syntax: app.js")
except FileNotFoundError: print("WARN node unavailable")

api=(ROOT/"webapp_api.py").read_text(encoding='utf-8')
mini=(ROOT/"kdm_mini_app.py").read_text(encoding='utf-8')
rt=(ROOT/"realtime_engine_v3.py").read_text(encoding='utf-8')
schema=(ROOT/"extended_schema.py").read_text(encoding='utf-8')
compose=(ROOT/"docker-compose.yml").read_text()
cfg=(ROOT/"config.py").read_text()
js=(ROOT/"app.js").read_text()
caddy=(ROOT/"Caddyfile").read_text()

for key in ("boom","number","dice2","aztec","triplegold","flame","chicken2","slot","wheel","keno","chicken","rabbit","roast","roulette","bingo","fastkeno","aviator","plinko","mines","jet","fish","card","penaltystreak","tower","coinstreak","dragontiger","andarbahar","sports","marketplace"):
    need(f'key: "{key}"' in js,f"missing module {key}")
need("CREATE TABLE IF NOT EXISTS withdrawals (" in schema and "id INTEGER PRIMARY KEY AUTOINCREMENT" in schema,"canonical withdrawals.id schema missing")
need("CREATE TABLE IF NOT EXISTS transactions (" in schema and "payment_id INTEGER" in schema,"transactions.payment_id schema missing")
need("withdrawal_id" in schema and "withdrawals_legacy" in schema,"legacy withdrawal migration missing")
need("UPDATE transactions SET amount=-ABS(amount)" in schema,"withdrawal ledger sign migration missing")
need("init_extended_schema(DB_FILE, ADMIN_ID)" in mini,"bot does not run shared schema migration")
need('ADMIN_PANEL_PIN = os.getenv("ADMIN_PANEL_PIN", "").strip()' in mini and '"adminpin"' in mini, "bot Admin PIN command/session missing")
need("No legacy /api/* handlers here" in mini and 'app.router.add_post("/api/withdraw"' not in mini, "legacy bot API routes are still exposed")
approve=mini[mini.find("def approve_payment"):mini.find("def reject_payment")]
need("UPDATE payments SET status='approved', approved_at=? WHERE id=? AND status='pending'" in approve,"payment approval lacks atomic pending guard")
need("BEGIN IMMEDIATE" in approve,"payment approval lacks transaction lock")
need("INSERT INTO transactions(user_id,amount,transaction_type,payment_id,created_at)" in approve,"payment approval transaction ledger insert missing")
need("get_user_auction_bids" in mini and "SELECT bid_amount FROM bids" in mini,"auction bid result helper missing")
need("SELECT DISTINCT user_id FROM bids WHERE auction_id=?" in mini,"auction result is not participant-only")
need("asyncio.sleep(0.05)" in mini,"auction result pacing missing")
need("UPDATE withdrawals" in mini and "AND status = 'pending'" in mini,"withdraw status guard missing")
need("withdraw_refund" in mini,"withdraw reject refund ledger missing")
need("-amount, \"withdraw\"" in mini,"bot withdrawal outflow ledger missing")
need("sig.encode('utf-8')" in rt and "expected.encode('ascii')" in rt,"provider webhook signature is not bytes-safe")
need("json.loads(raw.decode('utf-8'))" in rt,"provider webhook JSON decoding is not explicit/safe")
need("q.rollback()" not in rt,"cursor rollback regression")
need("not 1<=mc<=8" in rt,"realtime Mines range not aligned to UI 1-8")
need("m=round(25/(25-mc),2)" in rt,"realtime Mines still pre-applies RTP scaling")
need("datetime.utcnow()" not in rt,"realtime engine still mixes UTC with local _now timestamps")
need("from werkzeug.exceptions import HTTPException" in api and "if isinstance(exc, HTTPException):" in api,"HTTP exceptions are not preserved by the global handler")
need("JSON_BODY_MAX_BYTES = 1024 * 1024" in api,"JSON request body limit missing")
need("_ERROR_NOTICE_INTERVAL = 60" in api,"admin error notifications are not rate limited")
need("BEGIN IMMEDIATE" in api[api.find('def submit_withdraw'):api.find('@app.route("/api/sports/bet"')],"withdraw daily-limit reservation is not transaction-serialized")
need('parse_mode="HTML"' in api[api.find('def submit_withdraw'):api.find('@app.route("/api/sports/bet"')],"withdraw staff message does not use Telegram HTML")
need("secrets.SystemRandom().sample(range(1, 21), 5)" in api and "secrets.SystemRandom().sample(range(1,26), mine_count)" in api,"legacy Keno/Mines still use non-cryptographic random.sample")
need("result, error = _run_cabinet(g.tg_user[\"id\"], key, body)" in api and "if error is not None:" in api,"legacy /play does not return validation errors as proper 400 responses")
need('BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip()' in cfg,"BOT_USERNAME is still hardcoded by default")
need("@rate_limit(max_calls=12, window_seconds=10)" in rt and "@rate_limit(max_calls=5, window_seconds=60)" in rt,"realtime/payment intent rate limits missing")
need("effective_multiplier" in rt and "o['base_multiplier']" in rt,"realtime result does not expose effective payout multiplier")
need("playAddedGameLegacy" not in js and "streamRoundResult" not in js,"dead legacy realtime frontend code remains")
need('return jsonify({"error": exc.description}), exc.code' in api,"HTTP error handler does not preserve status code")
approve=mini[mini.find('elif data.startswith("w_approve:")'):mini.find('elif data.startswith("w_reject:")')]
need("UPDATE withdrawals SET status='approved' WHERE id=? AND status='pending'" in approve,"withdrawal approval pending-state guard missing")
need("screenshot_file_id" not in approve,"withdrawal approval incorrectly depends on a proof upload from a different flow")
need("INSERT INTO transactions" not in approve and "UPDATE users SET balance" not in approve,"withdrawal approval must not debit wallet or add a second ledger row")
need("def send_daily_backup" not in mini,"obsolete bot backup function remains")
need("bot_application.loop" not in mini,"removed PTB loop API still referenced")
need(compose.count("TZ: Africa/Addis_Ababa")>=3,"TZ must be set on api, bot and backup so sports closes_at matches admin local time")
need("kdm-backups:/app/backups:ro" in compose,"api must mount kdm-backups so /api/admin/backups/status sees backups")
need("datetime.utcnow()" not in api,"utcnow mixes UTC with local _now()")
need("TURN_URL=" in (ROOT/".env.example").read_text(),".env.example missing TURN vars")
need("api:\n        condition: service_healthy" in compose,"bot/proxy do not wait for healthy API")
need("HEALTHCHECK" in (ROOT/"Dockerfile.api").read_text(),"API HEALTHCHECK missing")
need('"--workers", "1"' in (ROOT/"Dockerfile.api").read_text(),"API must remain single-worker while rate limiting is in-memory")
need("USER appuser" in (ROOT/"Dockerfile.api").read_text() and "USER appuser" in (ROOT/"Dockerfile.bot").read_text(),"containers still run as root")
need("Strict-Transport-Security" in caddy and "Content-Security-Policy" in caddy,"Caddy security headers missing")
need("script.integrity" in js and "sha384-CI3ELBV" in js,"Three.js SRI pin missing")
need("SMOKE_API_URL is required" in (ROOT/"production_smoke_test.py").read_text(),"production smoke still false-green")
need('ADMIN_PANEL_PIN = _require("ADMIN_PANEL_PIN")' in cfg,"admin PIN is not mandatory")
need('app.router.add_static("/assets/"' not in mini,"/assets static exposure remains")

# Render single-container deployment (API + bot + backup + proxy in one service, one disk).
for f in ("Dockerfile.render","render_start.sh","render_run.sh","Caddyfile.render","render.yaml",".gitignore","RENDER_DEPLOY_AM.md"):
    need((ROOT/f).is_file(),f"missing Render deployment file: {f}")
if (ROOT/"render_run.sh").is_file():
    rr=(ROOT/"render_run.sh").read_text()
    need("wait -n" in rr and "webapp_api:app" in rr and "kdm_mini_app.py" in rr and "backup_db.py" in rr and "caddy run" in rr,"render_run.sh must supervise api+bot+backup+proxy and exit if one dies")
    need('"--workers", "1"' in (ROOT/"Dockerfile.api").read_text() and "--workers 1" in rr,"Render API must stay single-worker")
if (ROOT/"render.yaml").is_file():
    ry=(ROOT/"render.yaml").read_text()
    need("mountPath: /app/data" in ry and "dockerfilePath: ./Dockerfile.render" in ry and "numInstances" not in ry,"render.yaml needs the /app/data disk, Dockerfile.render and a single instance")
    need("BOT_TOKEN" in ry and "sync: false" in ry and "8" not in ry.split("BOT_TOKEN")[1].split("}")[0].replace("sync: false",""),"render.yaml must not contain a hardcoded BOT_TOKEN")
if (ROOT/".gitignore").is_file():
    gi=(ROOT/".gitignore").read_text()
    need(".env" in gi and "*.db" in gi and "backups/" in gi,".gitignore must exclude .env, databases and backups")
if (ROOT/"Caddyfile.render").is_file():
    need("auto_https off" in (ROOT/"Caddyfile.render").read_text() and "{$PORT}" in (ROOT/"Caddyfile.render").read_text(),"Caddyfile.render must listen on $PORT without auto HTTPS")

# Chapa webhook header hardening in the main API.
need("x_chapa_sig.encode('utf-8')" in api and "expected_payload.encode('ascii')" in api,"Chapa webhook signature is not bytes-safe")
# Main API and realtime both must reject malformed provider JSON.
need("except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError)" in rt,"provider webhook malformed JSON handling missing")

# Schema migration smoke on a temporary DB.
try:
    import importlib.util
    spec=importlib.util.spec_from_file_location('ext',ROOT/'extended_schema.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as d:
        db=Path(d)/'x.db'; mod.init_extended_schema(str(db),123)
        c=sqlite3.connect(db); c.row_factory=sqlite3.Row
        wc=c.execute('PRAGMA table_info(withdrawals)').fetchall(); tc=c.execute('PRAGMA table_info(transactions)').fetchall()
        need(any(r['name']=='id' for r in wc),"schema smoke: withdrawals.id missing")
        need(any(r['name']=='payment_id' for r in tc),"schema smoke: transactions.payment_id missing")
        c.close()
    print("PASS schema migration smoke")
except Exception as e:
    errors.append(f"schema migration smoke: {e}")

# Every local CSS/JS file index.html loads must be in MINI_PUBLIC_ASSETS, otherwise the bot server
# 404s it and the Mini App shows up unstyled / broken. And Render must never serve /app as a directory.
import re as _re
_html=(ROOT/"index.html").read_text(encoding='utf-8')
for _ref in _re.findall(r'(?:href|src)="([^":?]+\.(?:css|js))(?:\?[^"]*)?"',_html):
    need((ROOT/_ref).is_file(),f"index.html references missing file: {_ref}")
    need(f'"/{_ref}"' in mini,f"{_ref} is loaded by index.html but missing from MINI_PUBLIC_ASSETS (404 in production)")
need("file_server" not in (ROOT/"Caddyfile.render").read_text(),"Caddyfile.render must not file_server /app (source + DB would be downloadable)")
for _k in ("home","games","sports","marketplace","profile"):
    need(f'<button type="button"' in _html and f'data-key="{_k}"' in _html.split('<nav id="bottom-nav">')[1],f"bottom nav missing {_k}")


# no orphan design files: every kdm_*.js / kdm_*.css that ships must be loaded by index.html (an unloaded screen is a silent "design not applied")
for _f in sorted(list(ROOT.glob("kdm_*.js")) + list(ROOT.glob("kdm_*.css"))):
    need(_f.name in _html, f"{_f.name} ships in the package but index.html never loads it")
need('data-key="home"' in _html, "bottom nav Home missing")

# the ladder games that share the Chicken Road engine are each tested with their own parameters
for _road in ("penaltystreak", "tower", "chicken2"):
    try:
        _t = subprocess.run([sys.executable, str(ROOT/"chicken_road_regression_test.py")], capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(ROOT), "ROAD_GAME": _road})
        if _t.returncode != 0: errors.append(f"road[{_road}] failed: {_t.stdout}{_t.stderr}")
        else: print(_t.stdout.strip())
    except Exception as e:
        errors.append(f"road[{_road}] could not run: {e}")

for test_name in ("royal_v1_regression_test.py", "realtime_path_regression_test.py", "api_path_audit.py", "rtp_regression_test.py", "plinko_regression_test.py", "auto_cashout_regression_test.py", "keno_regression_test.py", "launch_blocker_regression_test.py",
                  "chicken_road_regression_test.py", "triplegold_regression_test.py", "triplegold_deluxe_regression_test.py", "new_games_regression_test.py", "coin_penalty_regression_test.py", "withdraw_limits_regression_test.py", "sports_live_regression_test.py", "casino_cards_regression_test.py", "cards2_regression_test.py", "dice2_regression_test.py", "pool_games_regression_test.py", "crash_refund_regression_test.py", "live_all_regression_test.py", "betpro_regression_test.py", "playwin_fixes_regression_test.py", "platform_controls_e2e_test.py"):
    try:
        test = subprocess.run([sys.executable, str(ROOT/test_name)], capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(ROOT)})
        if test.returncode != 0:
            errors.append(f"{test_name} failed: {test.stdout}{test.stderr}")
        else:
            print(test.stdout.strip())
    except Exception as e:
        errors.append(f"{test_name} could not run: {e}")

if errors:
    print("SELF_CHECK=FAIL")
    for e in errors: print(" -",e)
    sys.exit(1)
print("SELF_CHECK=PASS")
