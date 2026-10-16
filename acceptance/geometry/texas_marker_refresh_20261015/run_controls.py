"""Fresh bounded network evidence; no deployment or source-system writes.
Run with requests installed. Captures are append-only; use a new --output for each attempt.
"""
import argparse,base64,io,json,pathlib,sys,tempfile,zipfile
REPO=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO))
from civic_gps_extensions.texas_geometry_governance import verify_texas_geometry_governance
parser=argparse.ArgumentParser();parser.add_argument('--output',type=pathlib.Path,required=True);args=parser.parse_args()
assert not args.output.exists(), 'Use a new output directory; never overwrite an attempt'
args.output.mkdir(parents=True)
with tempfile.TemporaryDirectory() as tmp:
 temp=pathlib.Path(tmp);runtime=temp/'runtime';runtime.mkdir()
 raw=b''.join(p.read_bytes() for p in sorted((REPO/'civic_gps_runtime_parts').glob('part.*')))
 with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(runtime)
 parts=sorted((REPO/'data/packages/tx/legislative').glob('Tx_Legislative_Two_Office_v0.1.zip.b64.part*'))
 raw=base64.b64decode(''.join(p.read_text().strip() for p in parts),validate=True)
 with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(temp/'package')
 import run_address_controls as address
 address.ROOT=args.output;address.REPO=REPO;address.RUNTIME=runtime
 address.PACKAGE_PATH=temp/'package/Tx_Legislative_Two_Office_v0.1/package/jurisdiction.json'
 address.write(args.output/'preflight_before.json',verify_texas_geometry_governance())
 address.write(args.output/'boundary_fixtures.json',json.loads((pathlib.Path(__file__).parent/'evidence/boundary_fixtures.json').read_text()))
 address.main()
 import run_boundary_controls as boundary
 boundary.main()
 address.write(args.output/'preflight_after.json',verify_texas_geometry_governance())
 a=json.loads((args.output/'address_control_summary.json').read_text());b=json.loads((args.output/'boundary_control_summary.json').read_text())
 ok=len(a)==2 and len(b)==6 and all(r['expected_status_met'] for r in a+b)
 summary={'status':'PASS' if ok else 'FAIL','address_controls':len(a),'boundary_controls':len(b),'all_expected_statuses_met':ok,'live_network':True,'preflight_before_and_after':True,'scope':'Internal bounded House 49 / Senate 14; injected recording session is not production release evidence','deployment_performed':False,'source_writes':0}
 address.write(args.output/'summary.json',summary);print(json.dumps(summary))
 if not ok:raise SystemExit(1)
