import os, sys, urllib.request, json

url=os.getenv('SMOKE_API_URL','').rstrip('/')
if not url:
    print('FAIL: SMOKE_API_URL is required; refusing a false-green production smoke result')
    sys.exit(2)
if os.getenv('SMOKE_REQUIRE_HTTPS','1')=='1' and not url.startswith('https://'):
    print('FAIL: SMOKE_API_URL must be HTTPS in production')
    sys.exit(2)
for path in ('/api/health','/api/payments/chapa/status'):
    try:
        with urllib.request.urlopen(url+path,timeout=15) as r:
            body=json.loads(r.read().decode())
            print(path, r.status, body)
            if r.status != 200: sys.exit(3)
    except Exception as e:
        print('FAIL', path, e); sys.exit(4)
print('LIVE DEPLOYMENT SMOKE: PASS')
