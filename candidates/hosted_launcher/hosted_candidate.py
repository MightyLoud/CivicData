"""Unpublished hosted launcher candidate for the existing governed address API."""
import os,subprocess,sys
from pathlib import Path
PIN='e9c11f26c0cec8acd409d92f4d4867b5ee5715f7'

def create_app(repo_root):
 root=Path(repo_root).resolve();sys.path.insert(0,str(root))
 from services.governed_address_api.main import create_app as existing_app
 from fastapi.responses import JSONResponse
 app=existing_app(repo_root=root)
 def state():
  try:
   head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
   tracked=subprocess.run(['git','diff','--quiet','HEAD'],cwd=root).returncode==0
   valid=head==PIN and tracked
  except (OSError,subprocess.SubprocessError):head=None;valid=False
  return {'status':'PASS' if valid else 'FAIL-CLOSED','repository_head':head,'expected_repository_head':PIN,'scope':'HOSTED_LAUNCHER_CANDIDATE_ONLY','pilots_enabled':False,'production_accepted':False,'canonical_writes':0}
 @app.middleware('http')
 async def pin_guard(request,call_next):
  if request.url.path.startswith('/v1/') and state()['status']!='PASS':
   return JSONResponse({'status':'FAIL-CLOSED','error':'REPOSITORY_PIN_INVALID','canonical_writes':0},status_code=503)
  return await call_next(request)
 @app.get('/health')
 def health():return JSONResponse({'status':'PASS','scope':'PROCESS_LIVENESS_ONLY','pilots_enabled':False},headers={'Cache-Control':'no-store'})
 @app.get('/readyz')
 def ready():
  s=state();return JSONResponse(s,status_code=200 if s['status']=='PASS' else 503,headers={'Cache-Control':'no-store'})
 @app.post('/v1/pilots/representation')
 def pilots():return JSONResponse({'status':'FAIL-CLOSED','error':'PILOT_ACTIVATION_HELD','canonical_writes':0},status_code=503,headers={'Cache-Control':'no-store'})
 return app

def settings():
 port=int(os.environ.get('PORT','8080'))
 if not 1<=port<=65535:raise ValueError('PORT_INVALID')
 return '0.0.0.0',port

if __name__=='__main__':
 import uvicorn
 host,port=settings();uvicorn.run(create_app(os.environ['CIVICDATA_REPO_ROOT']),host=host,port=port,access_log=False)
