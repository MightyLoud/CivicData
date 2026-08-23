#!/usr/bin/env python3
"""Promote a reviewed EV onboarding materialization into a repository checkout.

EV-IMP-011 is deliberately narrower than repository publication. It regenerates
an EV-IMP-010 staging bundle, binds approval to a deterministic bundle SHA-256,
preflights every allowed repository surface, applies only the reviewed ADD
changes, and rolls back on any post-write verification failure.

It never creates civic facts, never researches routing authority, never pushes a
branch, never opens or merges a pull request, and never publishes externally.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZE_TOOL = ROOT / "tools" / "ev_onboarding_materialize.py"
_spec = importlib.util.spec_from_file_location("ev_onboarding_materialize_for_promote", MATERIALIZE_TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load onboarding materializer")
materialize_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(materialize_tool)


class PromotionError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _json_equivalent(left: bytes, right: bytes) -> bool:
    try:
        return json.loads(left.decode("utf-8")) == json.loads(right.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def _allowed_path(rel: str) -> bool:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return False
    if rel == "consumers/empowered_vote/package_catalog.v0.1.json":
        return True
    if rel == "civic_gps_extensions/registry_bundles.v0.1.json":
        return True
    return len(path.parts) == 3 and path.parts[:2] == ("onboarding", "ev") and path.name.endswith(".v0.1.json")


def bundle_descriptor(staging_dir: Path) -> dict[str, Any]:
    manifest_path = staging_dir / "materialization-manifest.json"
    if not manifest_path.is_file():
        raise PromotionError("materialization manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("gate") != "EV-IMP-010" or manifest.get("status") != "PASS":
        raise PromotionError("materialization manifest is not EV-IMP-010 PASS")
    if manifest.get("conflicts") != 0 or manifest.get("canonical_writes") != 0 or manifest.get("repository_mutated") is not False:
        raise PromotionError("materialization manifest violates promotion boundary")
    changes = manifest.get("changes")
    if not isinstance(changes, list) or not changes:
        raise PromotionError("materialization change list missing")

    files = []
    seen: set[str] = set()
    for row in changes:
        if not isinstance(row, dict):
            raise PromotionError("invalid materialization change row")
        rel = str(row.get("path") or "")
        action = str(row.get("action") or "")
        if not _allowed_path(rel):
            raise PromotionError(f"materialization path not allowed: {rel}")
        if action not in {"ADD", "NOOP"}:
            raise PromotionError(f"unsupported materialization action: {action}")
        if rel in seen:
            raise PromotionError(f"duplicate materialization path: {rel}")
        seen.add(rel)
        staged = staging_dir / "staged" / rel
        if not staged.is_file():
            raise PromotionError(f"staged file missing: {rel}")
        files.append({"path": rel, "action": action, "sha256": sha256_file(staged)})

    descriptor = {
        "gate": "EV-IMP-011-BUNDLE",
        "package_jurisdiction_id": manifest.get("package_jurisdiction_id"),
        "entry_id": manifest.get("entry_id"),
        "routing_strategy": manifest.get("routing_strategy"),
        "changes_required": manifest.get("changes_required"),
        "files": sorted(files, key=lambda row: row["path"]),
        "canonical_writes": 0,
    }
    descriptor["bundle_sha256"] = sha256_bytes(canonical(descriptor))
    return descriptor


def generate(repo_root: Path, package_jurisdiction_id: str, out: Path) -> dict[str, Any]:
    staging = out / "materialization"
    manifest = materialize_tool.materialize(repo_root, package_jurisdiction_id, staging)
    descriptor = bundle_descriptor(staging)
    report = {
        "gate": "EV-IMP-011",
        "status": "READY_FOR_REVIEW" if manifest["changes_required"] else "NOOP",
        "package_jurisdiction_id": package_jurisdiction_id,
        "entry_id": manifest["entry_id"],
        "routing_strategy": manifest["routing_strategy"],
        "changes_required": manifest["changes_required"],
        "bundle_sha256": descriptor["bundle_sha256"],
        "repository_mutated": False,
        "canonical_writes": 0,
        "branch_push_authorized": False,
        "pull_request_authorized": False,
        "merge_authorized": False,
        "publication_authorized": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "bundle-descriptor.json").write_bytes(canonical(descriptor))
    (out / "promotion-plan.json").write_bytes(canonical(report))
    return report


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def apply_reviewed(repo_root: Path, package_jurisdiction_id: str, expected_bundle_sha256: str, out: Path) -> dict[str, Any]:
    if len(expected_bundle_sha256) != 64:
        raise PromotionError("expected bundle SHA-256 must be 64 hexadecimal characters")
    try:
        int(expected_bundle_sha256, 16)
    except ValueError as exc:
        raise PromotionError("expected bundle SHA-256 is not hexadecimal") from exc

    with tempfile.TemporaryDirectory() as td:
        regenerated = Path(td) / "reviewed"
        plan = generate(repo_root, package_jurisdiction_id, regenerated)
        actual = plan["bundle_sha256"]
        if actual != expected_bundle_sha256:
            raise PromotionError(f"reviewed bundle drift: expected {expected_bundle_sha256}, regenerated {actual}")

        staging = regenerated / "materialization"
        manifest = json.loads((staging / "materialization-manifest.json").read_text(encoding="utf-8"))
        changes = manifest["changes"]

        preimages: dict[str, bytes | None] = {}
        staged_bytes: dict[str, bytes] = {}
        for row in changes:
            rel = str(row["path"])
            action = str(row["action"])
            target = repo_root / rel
            staged = staging / "staged" / rel
            content = staged.read_bytes()
            staged_bytes[rel] = content
            preimages[rel] = target.read_bytes() if target.exists() else None
            if action == "NOOP":
                if preimages[rel] is None or not _json_equivalent(preimages[rel], content):
                    raise PromotionError(f"NOOP preimage drift: {rel}")
            elif action == "ADD" and rel.startswith("onboarding/ev/") and preimages[rel] is not None:
                raise PromotionError(f"new onboarding spec path already exists: {rel}")

        applied: list[str] = []
        try:
            for row in changes:
                if row["action"] != "ADD":
                    continue
                rel = str(row["path"])
                _atomic_write(repo_root / rel, staged_bytes[rel])
                applied.append(rel)

            post = materialize_tool.materialize(repo_root, package_jurisdiction_id, Path(td) / "post")
            if post.get("changes_required") != 0 or any(row.get("action") != "NOOP" for row in post.get("changes", [])):
                raise PromotionError("post-apply idempotence verification failed")
        except Exception:
            for rel in reversed(applied):
                target = repo_root / rel
                before = preimages[rel]
                if before is None:
                    try:
                        target.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    _atomic_write(target, before)
            raise

    report = {
        "gate": "EV-IMP-011",
        "status": "APPLIED" if applied else "NOOP",
        "package_jurisdiction_id": package_jurisdiction_id,
        "bundle_sha256": expected_bundle_sha256,
        "files_applied": sorted(applied),
        "changes_applied": len(applied),
        "post_apply_idempotence": True,
        "repository_mutated": bool(applied),
        "canonical_writes": 0,
        "branch_push_authorized": False,
        "pull_request_authorized": False,
        "merge_authorized": False,
        "publication_authorized": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "promotion-result.json").write_bytes(canonical(report))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--package-jurisdiction-id", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--expected-bundle-sha256")
    args = ap.parse_args()
    root = args.repo_root.resolve()
    if args.apply:
        if not args.expected_bundle_sha256:
            raise SystemExit("--expected-bundle-sha256 is required with --apply")
        report = apply_reviewed(root, args.package_jurisdiction_id, args.expected_bundle_sha256, args.output)
    else:
        report = generate(root, args.package_jurisdiction_id, args.output)
    print(canonical(report).decode("utf-8").strip())


if __name__ == "__main__":
    main()
