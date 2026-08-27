import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from tools import co_factory_export as exporter
from tools import jurisdiction_package as jp

SNAPSHOT = ROOT / "data" / "source" / "co" / "d329-co-factory-snapshot.json"

EXPECTED = {
    "jurisdiction-co-akron": (1, 2, 7, 7, 11, 23, 0),
    "jurisdiction-co-alamosa": (5, 6, 7, 7, 11, 28, 1),
    "jurisdiction-co-alma": (1, 2, 5, 5, 11, 20, 1),
    "jurisdiction-co-arvada": (5, 7, 7, 7, 19, 40, 1),
    "jurisdiction-co-aspen": (1, 5, 5, 5, 11, 40, 1),
}


def test_snapshot_exports_five_exact_deterministic_packages():
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        first_path, second_path = pathlib.Path(first), pathlib.Path(second)
        first_results = exporter.export_snapshot(snapshot, first_path)
        second_results = exporter.export_snapshot(snapshot, second_path)
        assert [row["jurisdiction_id"] for row in first_results] == list(exporter.AUTHORIZED_IDS)
        assert first_results == [
            {**row, "output": str(first_path / row["jurisdiction_id"])}
            for row in first_results
        ]
        for jurisdiction_id in exporter.AUTHORIZED_IDS:
            one = first_path / jurisdiction_id
            two = second_path / jurisdiction_id
            package = json.loads((one / "jurisdiction.json").read_text(encoding="utf-8"))
            counts = package["qa"]["source_counts"]
            expected = EXPECTED[jurisdiction_id]
            assert (
                counts["divisions"],
                counts["offices"],
                counts["people"],
                counts["role_terms"],
                counts["source_evidence"],
                counts["source_assertions"],
                counts["warnings"],
            ) == expected
            assert package["qa"]["parity_ok"] is True
            assert package["qa"]["tracker_complete"] is True
            assert package["qa"]["release_ready"] is True
            assert package["qa"]["qa_fail_count"] == 0
            assert package["qa"]["blocking_gap_count"] == 0
            assert len(package["qa"]["address_tests"]) == 2
            assert jp.verify_package(one) == []
            assert {
                path.name: path.read_bytes() for path in one.iterdir()
            } == {
                path.name: path.read_bytes() for path in two.iterdir()
            }
        for jurisdiction_id in exporter.EXCLUDED_IDS:
            assert not (first_path / jurisdiction_id).exists()


if __name__ == "__main__":
    test_snapshot_exports_five_exact_deterministic_packages()
    print(json.dumps({"status": "PASS", "decision_id": "D-329"}, sort_keys=True))
