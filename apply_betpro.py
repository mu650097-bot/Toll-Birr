#!/usr/bin/env python3
"""Run ONCE from the Tolo-main folder after copying the zip files over your project:   python3 apply_betpro.py
Registers the BetPro files: index.html (css + js tags), kdm_mini_app.py (MINI_PUBLIC_ASSETS - without it the server answers 404 for the
new files) and webapp_api.py (loads betpro_v1.py). Safe to run again. Restart the server afterwards."""
import re, sys, os
H = os.path.dirname(os.path.abspath(__file__)); V = "20261107a"
def rd(n): return open(os.path.join(H, n), encoding="utf-8", errors="surrogateescape").read()
def wr(n, s): open(os.path.join(H, n), "w", encoding="utf-8", errors="surrogateescape").write(s)
for f in ("kdm_betpro.css", "kdm_betpro.js", "betpro_v1.py"):
    if not os.path.exists(os.path.join(H, f)): sys.exit("MISSING FILE: " + f + " (copy the zip contents into this folder first)")
log = []
idx = rd("index.html")
if "kdm_betpro.css" not in idx:
    i = idx.rfind("</head>"); idx = idx[:i] + '  <link rel="stylesheet" href="kdm_betpro.css?v=%s">\n' % V + idx[i:]; log.append("index.html + kdm_betpro.css")
if "kdm_betpro.js" not in idx:
    i = idx.rfind("</body>"); idx = idx[:i] + '  <script src="kdm_betpro.js?v=%s"></script>\n' % V + idx[i:]; log.append("index.html + kdm_betpro.js")
wr("index.html", idx)
py = rd("kdm_mini_app.py")
m = re.search(r'^([ \t]*)"/kdm_fix\.js":[^\n]*\n', py, re.M) or re.search(r'^([ \t]*)"/kdm_fix\.css":[^\n]*\n', py, re.M)
if not m: sys.exit('Could not find the "/kdm_fix.js" line in kdm_mini_app.py (MINI_PUBLIC_ASSETS)')
for f, ct in (("kdm_betpro.js", "application/javascript; charset=utf-8"), ("kdm_betpro.css", "text/css; charset=utf-8")):
    if '"/%s"' % f in py: log.append("whitelist already has " + f); continue
    m = re.search(r'^([ \t]*)"/kdm_fix\.js":[^\n]*\n', py, re.M)
    py = py[:m.end()] + '%s"/%s": "%s",\n' % (m.group(1), f, ct) + py[m.end():]; log.append("whitelist + " + f)
wr("kdm_mini_app.py", py)
api = rd("webapp_api.py")
if "betpro_v1.py" not in api:
    m = re.search(r"^exec\(compile\(open\(os\.path\.join\(os\.path\.dirname\(__file__\), 'engagement_v8\.py'\)[^\n]*\n", api, re.M)
    if not m: sys.exit("Could not find the engagement_v8.py exec line in webapp_api.py")
    api = api[:m.end()] + "exec(compile(open(os.path.join(os.path.dirname(__file__), 'betpro_v1.py')).read(), os.path.join(os.path.dirname(__file__), 'betpro_v1.py'), 'exec'), globals())  # BETPRO: promo images + profile stats\n" + api[m.end():]
    wr("webapp_api.py", api); log.append("webapp_api.py + betpro_v1.py")
print("\n".join(log) or "nothing to do"); print("DONE - now restart the server (API + Mini App) and reopen the Mini App.")
