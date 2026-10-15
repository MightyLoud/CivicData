import sys,os,json,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from hosted_candidate import create_app,settings
D=Path(__file__).resolve().parent;c=TestClient(create_app(sys.argv[1]));checks=[]
for p in ['/health','/healthz','/readyz']:
 r=c.get(p);assert r.status_code==200,(p,r.text);checks.append(p+' PASS')
r=c.post('/v1/pilots/representation');assert r.status_code==503 and r.json()['error']=='PILOT_ACTIVATION_HELD';checks.append('pilot route held')
r=c.post('/v1/representation',json={'address':''});assert r.status_code==422;checks.append('existing input validation preserved')
os.environ['PORT']='8080';assert settings()==('0.0.0.0',8080);checks.append('host and port compatible')
os.environ['PORT']='70000'
try:settings();raise AssertionError('invalid port accepted')
except ValueError:checks.append('invalid port rejected')
with tempfile.TemporaryDirectory() as t:
 bad=TestClient(create_app(t));r=bad.get('/readyz');assert r.status_code==503;checks.append('missing repository fails readiness')
 r=bad.post('/v1/representation',json={'address':'fixture'});assert r.status_code==503 and r.json()['error']=='REPOSITORY_PIN_INVALID';checks.append('lookup blocked when pin invalid')
(D/'validation.json').write_text(json.dumps({'status':'LOCAL_HOSTED_LAUNCHER_CHECKS_PASS','checks':checks,'deployment':'NOT_EXECUTED','container_build':'NOT_TESTED','hosted_parity':'NOT_VERIFIED'},indent=2)+'\n');print(len(checks),'local service checks PASS')
