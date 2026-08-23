#!/usr/bin/env python3
"""Load governed Civic GPS registry extensions into the exact packaged engine.

Extensions add geography routing configuration only. They do not replace the
Civic GPS engine or create a separate resolver backend.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

EXTENSION_VERSION = "0.1"
DEFAULT_EXTENSION = Path(__file__).with_name("registry_bundles.v0.1.json")


def load_registry_with_extensions(
    repo_root: str | Path,
    *,
    extension_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    root = Path(repo_root)
    registry_path = root / "civic_gps" / "registry.json"
    if not registry_path.is_file():
        raise FileNotFoundError("reconstructed Civic GPS registry is not present")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        raise ValueError("Civic GPS registry must be an object")

    ext_path = Path(extension_path) if extension_path is not None else root / "civic_gps_extensions" / "registry_bundles.v0.1.json"
    if not ext_path.is_file():
        return registry, registry_path
    extension = json.loads(ext_path.read_text(encoding="utf-8"))
    if not isinstance(extension, dict) or str(extension.get("extension_version")) != EXTENSION_VERSION:
        raise ValueError("unsupported Civic GPS registry extension version")
    bundles = extension.get("bundles")
    if not isinstance(bundles, list):
        raise ValueError("Civic GPS registry extension bundles must be a list")

    merged = copy.deepcopy(registry)
    merged.setdefault("bundles", [])
    existing = {str(row.get("adapter_id")) for row in merged["bundles"] if isinstance(row, dict)}
    for bundle in bundles:
        if not isinstance(bundle, dict) or not bundle.get("adapter_id"):
            raise ValueError("invalid Civic GPS registry extension bundle")
        adapter_id = str(bundle["adapter_id"])
        if adapter_id in existing:
            raise ValueError(f"duplicate Civic GPS adapter extension: {adapter_id}")
        merged["bundles"].append(copy.deepcopy(bundle))
        existing.add(adapter_id)
    return merged, registry_path


def load_resolver_with_extensions(
    repo_root: str | Path,
    *,
    timeout_seconds: float = 30.0,
    extension_path: str | Path | None = None,
):
    root = Path(repo_root)
    engine_path = root / "civic_gps" / "engine.py"
    if not engine_path.is_file():
        raise FileNotFoundError("reconstructed Civic GPS engine is not present")
    registry, registry_path = load_registry_with_extensions(root, extension_path=extension_path)
    spec = importlib.util.spec_from_file_location("civic_gps_engine_with_extensions", engine_path)
    if spec is None or spec.loader is None:
        raise ImportError("unable to load Civic GPS engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.CivicGPSOverlayEngine(
        registry,
        registry_root=registry_path.parent,
        timeout_seconds=timeout_seconds,
    )
