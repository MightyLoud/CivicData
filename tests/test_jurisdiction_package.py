import importlib.util, json, pathlib, tempfile
P=pathlib.Path(__file__).parents[1]/"tools"/"jurisdiction_package.py"
spec=importlib.util.spec_from_file_location("jp",P); jp=importlib.util.module_from_spec(spec); spec.loader.exec_module(jp)

def fixture():
    return {"schema_version":"0.1","jurisdiction":{"jurisdiction_id":"jurisdiction-test","name":"Test","state_abbr":"CO","geoid":"0800000"},"records":{"divisions":[],"bodies":[],"offices":[],"people":[],"role_terms":[],"leadership_roles":[],"identifier_crosswalk":[]},"provenance":{"source_evidence":[{"source_id":"src-1"}],"source_assertions":[]},"qa":{"parity_ok":True,"qa_fail_count":0,"blocking_gap_count":0,"address_tests":[{"result":True},{"result":True}],"checks":[]},"warnings":[]}

def test_valid_fixture(): assert jp.validate(fixture()) == []
def test_fail_closed_parity():
    x=fixture(); x["qa"]["parity_ok"]=False; assert "parity_ok" in jp.validate(x)
def test_deterministic_json(): assert jp.canonical_json(fixture()) == jp.canonical_json(fixture())
def test_build_has_manifest_and_checksums():
    with tempfile.TemporaryDirectory() as d:
        jp.build(fixture(),pathlib.Path(d)); assert (pathlib.Path(d)/"manifest.json").exists(); assert (pathlib.Path(d)/"SHA256SUMS.txt").exists()
