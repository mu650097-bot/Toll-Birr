"""Offline production contract gate plus explicit live-test requirements."""
from pathlib import Path
import ast, json, subprocess, sys
from collections import Counter
ROOT=Path(__file__).resolve().parent
checks=[]
def check(name, ok): checks.append((name,'PASS' if ok else 'FAIL'))

# First run the stricter release gate instead of duplicating weak substring checks.
r=subprocess.run([sys.executable,str(ROOT/'release_self_check.py')],capture_output=True,text=True)
check('release_self_check', r.returncode==0 and 'SELF_CHECK=PASS' in r.stdout)
for p in ROOT.rglob('__pycache__'):
    import shutil; shutil.rmtree(p, ignore_errors=True)

# Route uniqueness across API + realtime engine.
routes=[]
for fn in ('webapp_api.py','realtime_engine_v3.py'):
    tree=ast.parse((ROOT/fn).read_text(encoding='utf-8'))
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='route' and d.args:
                    path=ast.literal_eval(d.args[0])
                    methods=('GET',)
                    for kw in d.keywords:
                        if kw.arg=='methods': methods=tuple(sorted(ast.literal_eval(kw.value)))
                    routes.append((path,methods))
counts=Counter(routes)
check('route uniqueness', all(v==1 for v in counts.values()))

required_files=['webapp_api.py','kdm_mini_app.py','extended_schema.py','realtime_engine_v3.py','Dockerfile.api','Dockerfile.bot','docker-compose.yml','Caddyfile','.dockerignore','.env.example','backup_db.py','app.js','index.html','style.css','realtime_path_regression_test.py','api_path_audit.py','rtp_regression_test.py','blocker_regression_test.py','launch_blocker_regression_test.py']
check('required release files', all((ROOT/x).is_file() for x in required_files))
check('no legacy secret filenames', not (ROOT/'_dockerignore').exists() and not (ROOT/'_env.example').exists())
check('no pycache in release tree', not any(p.is_dir() and p.name=='__pycache__' for p in ROOT.rglob('*')))
js=(ROOT/'app.js').read_text(encoding='utf-8'); api=(ROOT/'webapp_api.py').read_text(encoding='utf-8'); rt=(ROOT/'realtime_engine_v3.py').read_text(encoding='utf-8')
check('Three.js/WebGL', 'WebGLRenderer' in js and 'script.integrity' in js)
check('stateful round client', '/round/start' in js and '/games/${key}/play' not in js)
check('single-worker in-memory rate limiter contract', '"--workers", "1"' in (ROOT/'Dockerfile.api').read_text())
check('embedded WebRTC client', '/calls/session' in js)
check('payment client', '/payments/intent' in js or '/payments/chapa/initialize' in js)
check('realtime engine loaded', 'realtime_engine_v3.py' in api)
check('provider webhook JSON guard', 'json.loads(raw.decode' in rt and 'invalid JSON' in rt)

live_requirements={
 'live_provider_e2e':'NOT RUN: real payment-provider credentials/endpoint were not supplied',
 'live_https_deployment':'NOT RUN: no external deployment target/credentials were supplied',
 'live_webrtc':'NOT RUN: two reachable real clients and production TURN were not supplied',
 'docker_build_start':'NOT RUN: Docker daemon is not available in this audit environment',
}
print(json.dumps({'checks':checks,**live_requirements},ensure_ascii=False,indent=2))
if not all(v=='PASS' for _,v in checks):
    sys.exit(1)
