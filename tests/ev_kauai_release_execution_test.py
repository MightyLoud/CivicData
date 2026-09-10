#!/usr/bin/env python3
"""Offline rejection and recovery tests; all execution requests use an in-memory API."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import ev_kauai_release_execution as e

NOW = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
HEAD, CERTIFIED = "a" * 40, "b" * 40


def source():
    # Synthetic complete review: never written to a candidate or passed to a live client.
    value = e.load_json((ROOT / e.RECHECK).read_bytes())
    value.update(status="PASS", leadership_matches_package=True, blockers=[], checked_at_utc=NOW.isoformat())
    value["sources"][-1].update(retrieval="DIRECT_FETCH", supports=["COUNCIL_CHAIR", "COUNCIL_VICE_CHAIR"])
    return value


def approved(review):
    value = e.approval_template()
    value.update(approved=True, publication_authorized=True, expected_execution_head=HEAD,
        certified_candidate_head=CERTIFIED, candidate_pr=62, source_recheck_sha256=e.sha(e.encoded(review)),
        approved_at_utc=NOW.isoformat(), expires_at_utc=(NOW + timedelta(hours=1)).isoformat(),
        approval_reference="SYNTHETIC_TEST_ONLY", operation_id="synthetic_test_001")
    return value


class FakeAPI:
    pages = e.GitHub.pages

    def __init__(self):
        self.allow_writes = False
        self.calls, self.writes = [], []
        self.release, self.assets, self.tag = None, [], None
        self.fail_at = None
        self.corrupt_bytes, self.extra_asset, self.bad_target, self.bad_tag = False, False, False, False
        self.fail_final = False
        self.bad_main, self.bad_ci, self.bad_diff, self.bad_texas = False, False, False, False

    def get(self, path):
        return self.request("GET", path)

    def request(self, method, path, data=None, *, binary=False):
        self.calls.append((method, path))
        if method != "GET":
            e.require(self.allow_writes, "FAKE_WRITES_HELD")
            self.writes.append((method, path, deepcopy(data)))
            if self.fail_at == path:
                raise TimeoutError("Synthetic ambiguous network failure")
        if method == "POST" and path == "releases":
            self.release = dict(deepcopy(data), id=999)
            if self.bad_target:
                self.release["target_commitish"] = HEAD
            return deepcopy(self.release)
        if method == "POST" and "/assets?name=" in path:
            self.assets = [{"id": 888, "name": e.manifest.ASSET, "size": len(data), "state": "uploaded",
                            "digest": "sha256:" + e.sha(data), "content_type": "application/json"}]
            self.raw = data
            if self.extra_asset:
                self.assets.append(dict(self.assets[0], id=889, name="forbidden-package.zip"))
            return deepcopy(self.assets[0])
        if method == "POST" and path == "git/refs":
            self.tag = {"ref": data["ref"], "object": {"type": "commit", "sha": HEAD if self.bad_tag else data["sha"]}}
            return deepcopy(self.tag)
        if method == "PATCH" and path == "releases/999":
            self.release.update(data)
            return deepcopy(self.release)
        if method != "GET":
            raise AssertionError((method, path))
        if path == "git/ref/heads/main":
            return {"object": {"sha": CERTIFIED if self.bad_main else HEAD}}
        if path == "git/ref/heads/" + e.RAILWAY_REF:
            return {"object": {"sha": e.RAILWAY_SHA}}
        if path == "pulls/62":
            return {"merged": True, "state": "closed", "draft": False,
                    "head": {"sha": CERTIFIED, "repo": {"full_name": e.REPOSITORY}},
                    "base": {"ref": "main", "sha": e.BASE}, "merge_commit_sha": HEAD}
        if path.startswith("pulls/62/files?"):
            rows = [{"filename": p, "status": "added"} for p in sorted(e.ALLOWED_PATHS)]
            if self.bad_diff:
                rows[0]["status"] = "modified"
            return rows
        if path.startswith("actions/runs?"):
            return {"workflow_runs": [{"id": i, "path": p, "head_sha": CERTIFIED, "event": "pull_request",
                    "status": "completed", "conclusion": "failure" if self.bad_ci else "success"}
                    for i, p in enumerate(sorted(e.WORKFLOWS))]}
        if path == "git/commits/" + e.manifest.TARGET:
            return {"sha": e.manifest.TARGET, "tree": {"sha": e.manifest.TARGET_TREE}}
        if path in {"git/commits/" + HEAD, "git/commits/" + CERTIFIED}:
            return {"tree": {"sha": "c" * 40}, "parents": [{"sha": e.BASE}]}
        if path == "git/matching-refs/tags/" + e.manifest.TAG:
            return [deepcopy(self.tag)] if self.tag else []
        if path.startswith("releases?per_page="):
            return [deepcopy(self.release)] if self.release else []
        if path == f"releases/{e.TEXAS_ID}":
            return {"id": e.TEXAS_ID, "target_commitish": e.TEXAS_TARGET,
                    "tag_name": "tx-legislative-two-office-v0.1", "draft": False}
        if path == "releases/latest":
            return {"id": e.TEXAS_ID}
        if path.startswith(f"releases/{e.TEXAS_ID}/assets?"):
            return [{"id": 547794640, "size": 2 if self.bad_texas else 1766, "digest": "sha256:" + e.TEXAS_ASSET_SHA}]
        if path == "releases/999":
            if self.fail_final and not self.release["draft"]:
                raise ValueError("SYNTHETIC_FINAL_READBACK_FAILURE")
            return deepcopy(self.release)
        if path.startswith("releases/999/assets?"):
            return deepcopy(self.assets)
        if path == "releases/assets/888" and binary:
            return self.raw + (b"x" if self.corrupt_bytes else b"")
        raise AssertionError((method, path, binary))


class ExecutionTests(unittest.TestCase):
    def run_execution(self, api=None, review=None, approval=None):
        review = review if review is not None else source()
        approval = approval if approval is not None else approved(review)
        api = api or FakeAPI()
        return e.execute(ROOT, api, e.encoded(approval), e.encoded(review), HEAD, NOW)

    def test_original_inputs_and_held_bundle(self):
        self.assertEqual(len(e.verify_local(ROOT, NOW.date())), 4593)
        self.assertEqual(e.load_json((ROOT / e.CONTRACT).read_bytes()), e.contract())
        self.assertFalse(e.approval_template()["approved"])
        with self.assertRaisesRegex(ValueError, "COMPLETE_LIVE_SOURCE_RECHECK_REQUIRED"):
            e.validate_recheck((ROOT / e.RECHECK).read_bytes(), NOW)

    def test_unapproved_template_makes_zero_api_calls(self):
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, "SEPARATE_PUBLICATION_APPROVAL_REQUIRED"):
            self.run_execution(api, approval=e.approval_template())
        self.assertEqual(api.calls, [])
        self.assertEqual(api.writes, [])

    def test_approval_bindings_fail_before_network(self):
        values = {"repository": "someone/else", "tag": "other-tag", "target_commit": HEAD,
                  "asset_sha256": "0" * 64, "notes_sha256": "0" * 64, "contract_sha256": "0" * 64,
                  "source_recheck_sha256": "0" * 64, "expected_execution_head": CERTIFIED,
                  "deployment_authorized": True, "catalog_promotion": True, "canonical_writes": 1,
                  "kalawao_work": True, "candidate_pr": 61, "operation_id": "../escape", "approval_reference": ""}
        for key, value in values.items():
            with self.subTest(key=key):
                api, a = FakeAPI(), approved(source())
                a[key] = value
                with self.assertRaises(ValueError):
                    self.run_execution(api, approval=a)
                self.assertEqual(api.calls, [])

    def test_expired_future_and_overlong_approvals(self):
        for start, end in [(NOW - timedelta(hours=2), NOW), (NOW + timedelta(seconds=1), NOW + timedelta(hours=1)),
                           (NOW, NOW + timedelta(hours=25))]:
            a = approved(source())
            a.update(approved_at_utc=start.isoformat(), expires_at_utc=end.isoformat())
            with self.assertRaisesRegex(ValueError, "APPROVAL_EXPIRED_OR_FUTURE"):
                self.run_execution(approval=a)

    def test_partial_stale_future_and_extended_review_fail(self):
        for field, value in [("status", "PARTIAL"), ("leadership_matches_package", None),
                ("checked_at_utc", (NOW - timedelta(hours=25)).isoformat()),
                ("checked_at_utc", (NOW + timedelta(seconds=1)).isoformat()),
                ("source_review_expires_on", "2027-01-01"), ("production_receipt_extended", True)]:
            with self.subTest(field=field, value=value):
                api, review = FakeAPI(), source()
                review[field] = value
                with self.assertRaises(ValueError):
                    self.run_execution(api, review)
                self.assertEqual(api.calls, [])
        with self.assertRaisesRegex(ValueError, "RECHECK_EXPIRED_OR_FUTURE"):
            e.validate_recheck(e.encoded(source()), datetime(2026, 12, 1, tzinfo=timezone.utc))

    def test_indexed_or_nonprimary_leadership_cannot_pass(self):
        for change in [{"retrieval": "INDEXED_EXCERPT"}, {"retrieval": "HTTP_403"}, {"url": "https://untrusted.example/council"}]:
            review = source()
            review["sources"][-1].update(change)
            with self.assertRaises(ValueError):
                self.run_execution(review=review)

    def test_duplicate_nonfinite_and_extra_approval_fields_rejected(self):
        for raw in [b'{"approved":true,"approved":false}', b'{"approved":NaN}']:
            with self.assertRaises(ValueError):
                e.validate_approval(raw, e.encoded(source()), HEAD, NOW)
        value = approved(source())
        value["bypass"] = True
        with self.assertRaisesRegex(ValueError, "APPROVAL_SCHEMA_INVALID"):
            self.run_execution(approval=value)

    def test_context_and_external_boundary_rejections_make_zero_writes(self):
        for field in ["bad_main", "bad_ci", "bad_diff", "bad_texas"]:
            with self.subTest(field=field):
                api = FakeAPI()
                setattr(api, field, True)
                with self.assertRaises(e.ExecutionFailure) as caught:
                    self.run_execution(api)
                self.assertEqual(caught.exception.receipt["phase"], "PREFLIGHT")
                self.assertEqual(api.writes, [])
                self.assertFalse(api.allow_writes)

    def test_tag_and_draft_collisions_make_zero_writes(self):
        for tag in [True, False]:
            api = FakeAPI()
            if tag:
                api.tag = {"ref": "refs/tags/" + e.manifest.TAG, "object": {"type": "commit", "sha": e.manifest.TARGET}}
            else:
                api.release = {"tag_name": e.manifest.TAG, "draft": True}
            with self.assertRaisesRegex(e.ExecutionFailure, "TAG_OR_RELEASE_COLLISION"):
                self.run_execution(api)
            self.assertEqual(api.writes, [])

    def test_wrong_release_asset_or_tag_never_publishes(self):
        for field in ["corrupt_bytes", "extra_asset", "bad_target", "bad_tag"]:
            with self.subTest(field=field):
                api = FakeAPI()
                setattr(api, field, True)
                with self.assertRaises(e.ExecutionFailure):
                    self.run_execution(api)
                self.assertFalse(any(method == "PATCH" for method, _, _ in api.writes))
                self.assertTrue(api.release["draft"])

    def test_complete_execution_preserves_exact_bytes_and_boundaries(self):
        api = FakeAPI()
        receipt = self.run_execution(api)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["completed_phases"], e.contract()["execution_steps"])
        self.assertEqual([(m, p) for m, p, _ in api.writes], [
            ("POST", "releases"), ("POST", "releases/999/assets?name=" + e.manifest.ASSET),
            ("POST", "git/refs"), ("PATCH", "releases/999")])
        self.assertEqual(api.raw, (ROOT / e.manifest.MANIFEST).read_bytes())
        self.assertEqual(api.writes[0][2]["target_commitish"], e.manifest.TARGET)
        self.assertIs(api.writes[0][2]["draft"], True)
        self.assertEqual(api.writes[0][2]["make_latest"], "false")
        self.assertEqual(api.writes[-1][2], {"draft": False, "make_latest": "false"})
        self.assertEqual(receipt["boundaries_before"], receipt["boundaries_after"])
        self.assertFalse(api.allow_writes)

    def test_repeat_execution_does_not_write_again(self):
        api = FakeAPI()
        self.run_execution(api)
        previous = len(api.writes)
        with self.assertRaisesRegex(e.ExecutionFailure, "TAG_OR_RELEASE_COLLISION"):
            self.run_execution(api)
        self.assertEqual(len(api.writes), previous)

    def test_partial_failure_preserves_ids_without_retry_or_cleanup(self):
        api = FakeAPI()
        api.fail_at = "releases/999/assets?name=" + e.manifest.ASSET
        with self.assertRaises(e.ExecutionFailure) as caught:
            self.run_execution(api)
        receipt = caught.exception.receipt
        self.assertEqual(receipt["phase"], "UPLOAD_ONE_MANIFEST")
        self.assertEqual(receipt["release_id"], 999)
        self.assertIsNone(receipt["publication_completed"])
        self.assertEqual(len(api.writes), 2)
        self.assertFalse(receipt["automatic_retry"])
        self.assertFalse(receipt["automatic_cleanup"])

    def test_final_readback_failure_never_claims_success(self):
        api = FakeAPI()
        api.fail_final = True
        with self.assertRaises(e.ExecutionFailure) as caught:
            self.run_execution(api)
        self.assertEqual(caught.exception.receipt["phase"], "VERIFY_PUBLISHED_RELEASE")
        self.assertIn("PUBLISH", caught.exception.receipt["completed_phases"])
        self.assertIsNone(caught.exception.receipt["publication_completed"])
        self.assertFalse(api.release["draft"])

    def test_output_collisions_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / e.ARTIFACTS / "one"
            self.assertEqual(e.prepare_output(root, output), output)
            for bad in [output, root / "elsewhere", root / e.ARTIFACTS / "one/../two", root / e.ARTIFACTS]:
                with self.assertRaises(ValueError):
                    e.prepare_output(root, bad)
            symlink = root / e.ARTIFACTS / "link"
            symlink.symlink_to(output, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "OUTPUT_SYMLINK_REJECTED"):
                e.prepare_output(root, symlink / "nested")

    def test_http_403_is_not_absence_and_write_switch_defaults_off(self):
        api = e.GitHub("synthetic-not-a-credential")
        with self.assertRaisesRegex(ValueError, "API_WRITES_HELD"):
            api.request("POST", "releases", {})
        with patch.object(api.opener, "open", side_effect=HTTPError("https://api.github.com", 403, "Forbidden", {}, None)):
            with self.assertRaisesRegex(ValueError, "GITHUB_HTTP_403"):
                api.get("git/matching-refs/tags/" + e.manifest.TAG)

    def test_binary_redirect_drops_authorization_and_rejects_other_hosts(self):
        api = e.GitHub("synthetic-not-a-credential")
        requests = []
        def open_request(request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise HTTPError(request.full_url, 302, "Found", {"Location": "https://release-assets.githubusercontent.com/file"}, None)
            return io.BytesIO(b"asset")
        with patch.object(api.opener, "open", side_effect=open_request):
            self.assertEqual(api.request("GET", "releases/assets/888", binary=True), b"asset")
        self.assertIn("Authorization", requests[0].headers)
        self.assertNotIn("Authorization", requests[1].headers)
        with patch.object(api.opener, "open", side_effect=HTTPError("url", 302, "Found", {"Location": "https://evil.example/file"}, None)):
            with self.assertRaisesRegex(ValueError, "ASSET_REDIRECT_REJECTED"):
                api.request("GET", "releases/assets/888", binary=True)

    def test_git_guard_requires_eight_added_paths(self):
        rows = "\n".join("A\t" + path for path in sorted(e.ALLOWED_PATHS))
        with patch.object(e, "git", side_effect=[HEAD, "", e.BASE_TREE, rows]):
            self.assertEqual(e.verify_git(ROOT, HEAD, e.BASE)["status"], "PASS")
        with patch.object(e, "git", side_effect=[HEAD, "", e.BASE_TREE, rows.replace("A\t", "M\t", 1)]):
            with self.assertRaisesRegex(ValueError, "EXACT_EIGHT_ADDITIONS_REQUIRED"):
                e.verify_git(ROOT, HEAD, e.BASE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
