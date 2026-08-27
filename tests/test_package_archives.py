import base64
import hashlib
import json
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).parents[1]
PACKAGE_ROOT = ROOT / "data" / "packages"
TACOMA = PACKAGE_ROOT / "wa" / "tacoma" / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip"
TACOMA_SHA256 = "2c6219303eff3f49b4202f72048910ba970cd65353032b6bfda2975791701d53"


def _decoded_parts(archive):
    parts = sorted(archive.parent.glob(archive.name + ".b64.part*"))
    assert parts, archive
    encoded = b"".join(b"".join(part.read_bytes().split()) for part in parts)
    return base64.b64decode(encoded, validate=True)


def test_every_committed_package_archive_is_valid_and_reproducible():
    archives = sorted(PACKAGE_ROOT.rglob("*.zip"))
    assert archives
    for archive in archives:
        data = archive.read_bytes()
        assert data == _decoded_parts(archive)
        with zipfile.ZipFile(archive) as handle:
            assert handle.testzip() is None
            names = handle.namelist()
            assert len(names) == len(set(names))
            for name in names:
                assert "\\" not in name
                path = pathlib.PurePosixPath(name)
                assert not path.is_absolute()
                assert ".." not in path.parts


def test_tacoma_archive_matches_governed_parts_exactly():
    data = TACOMA.read_bytes()
    assert len(data) == 23678
    assert hashlib.sha256(data).hexdigest() == TACOMA_SHA256
    assert data == _decoded_parts(TACOMA)


def run():
    test_every_committed_package_archive_is_valid_and_reproducible()
    test_tacoma_archive_matches_governed_parts_exactly()
    print(json.dumps({
        "status": "PASS",
        "decision_id": "D-387",
        "package_archives": len(list(PACKAGE_ROOT.rglob("*.zip"))),
        "tacoma_sha256": TACOMA_SHA256,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
