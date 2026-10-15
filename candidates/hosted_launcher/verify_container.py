"""Build and smoke-test locally. Does not deploy to any hosting service."""
import json,subprocess,time,urllib.request,urllib.error,uuid,shutil
from pathlib import Path
D=Path(__file__).resolve().parent
if not shutil.which('docker'):raise SystemExit('BLOCKED: Docker is required; no build attempted.')
tag='civic-hosted-candidate:'+uuid.uuid4().hex[:12];container=None
try:
 subprocess.run(['docker','build','--platform','linux/amd64','-t',tag,str(D)],check=True)
 container=subprocess.check_output(['docker','run','--platform','linux/amd64','--rm','-d','-p','127.0.0.1::8080',tag],text=True).strip()
 mapping=subprocess.check_output(['docker','port',container,'8080/tcp'],text=True).strip();port=mapping.rsplit(':',1)[1];base='http://127.0.0.1:'+port
 for attempt in range(60):
  try:
   with urllib.request.urlopen(base+'/readyz',timeout=2) as r:ready=json.load(r)
   assert ready['status']=='PASS' and ready['pilots_enabled'] is False;break
  except OSError:time.sleep(.5)
 else:raise RuntimeError('Container readiness failed')
 for route in ['/health','/healthz']:
  with urllib.request.urlopen(base+route,timeout=2) as r:assert r.status==200
 request=urllib.request.Request(base+'/v1/pilots/representation',data=b'{}',headers={'Content-Type':'application/json'})
 try:urllib.request.urlopen(request,timeout=2);raise AssertionError('pilot route unexpectedly enabled')
 except urllib.error.HTTPError as r:assert r.code==503 and json.load(r)['error']=='PILOT_ACTIVATION_HELD'
 receipt={'status':'PASS','image_tag':tag,'readiness':ready,'health_checks':2,'pilot_route':'HELD','deployment':'NOT_EXECUTED'}
 (D/'container_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
finally:
 if container:subprocess.run(['docker','rm','-f',container],stdout=subprocess.DEVNULL,check=False)
