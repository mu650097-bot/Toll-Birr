"""Static audit of frontend API calls against Flask route declarations.

Reports each discovered frontend route and any unmatched path so the result can
be reviewed before deployment. Dynamic path segments are matched by position.
"""
import ast, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
js=(ROOT/'app.js').read_text(encoding='utf-8')
route_specs=[]
for name in ('webapp_api.py','realtime_engine_v3.py'):
    tree=ast.parse((ROOT/name).read_text(encoding='utf-8'))
    for n in ast.walk(tree):
        if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
        for d in n.decorator_list:
            if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='route' and d.args:
                try: path=ast.literal_eval(d.args[0])
                except Exception: continue
                if isinstance(path,str) and path.startswith('/api/'):
                    route_specs.append(path[4:])
# Include apiFetch path literals and fetch() calls directly built from API_BASE.
found=set()
for m in re.finditer(r'apiFetch\(\s*([`\"\'])(.*?)\1',js,re.S):
    path=m.group(2)
    if path.startswith('/') and not path.startswith('//'):
        found.add(path.split('?',1)[0])
for m in re.finditer(r'fetch\(\s*`\$\{API_BASE\}([^`]+)`',js,re.S):
    found.add(m.group(1).split('?',1)[0])
for m in re.finditer(r'fetch\(\s*API_BASE\s*\+\s*`([^`]+)`',js,re.S):
    found.add(m.group(1).split('?',1)[0])

def segments(path):
    path=re.sub(r'\$\{[^}]+\}', '<dynamic>', path)
    return [x for x in path.strip('/').split('/') if x]
def match(front, route):
    a,b=segments(front),segments(route)
    if len(a)!=len(b): return False
    for x,y in zip(a,b):
        if '<dynamic>' in x or (y.startswith('<') and y.endswith('>')): continue
        if x!=y: return False
    return True
unmatched=[]
for path in sorted(found):
    if not any(match(path,r) for r in route_specs): unmatched.append(path)
print(f'FRONTEND_API_PATHS_FOUND={len(found)}')
print(f'BACKEND_API_ROUTE_TEMPLATES={len(set(route_specs))}')
print(f'MATCHED={len(found)-len(unmatched)}')
print(f'UNMATCHED={len(unmatched)}')
for path in unmatched: print('UNMATCHED_PATH='+path)
# Static extraction cannot understand every path assembled from variables; fail only
# on literal paths that are clearly intended as app-relative API endpoints.
if unmatched:
    sys.exit(1)
