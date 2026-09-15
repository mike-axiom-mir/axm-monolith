#!/usr/bin/env python3
"""Run the exact verified Discovery Buddy -> Front Door review-intake bridge.

This rule was learned from a real current-totality wiring run. It is intentionally
narrow and fail-closed: only the exact selected provider/consumer revisions that
were executed successfully are eligible. Changed refs remain HOLD until they are
revalidated and this recipe is deliberately updated.

The bridge never mutates donor module bytes. It copies both modules to a temporary
workspace, builds and verifies Discovery Buddy's portable zipapp, feeds that exact
artifact + SHA-256 to Front Door's portable discovery intake, and checks that the
result stays review-only with no publish/registry-write authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

PROVIDER_MODULE = "axm-discovery-buddy"
PROVIDER_REPOSITORY = "mike-axiom-mir/axm-discovery-buddy"
PROVIDER_COMMIT = "a1e28aba31c453023298e01ce4e54107c3f74583"
CONSUMER_MODULE = "axm-front-door"
CONSUMER_REPOSITORY = "mike-axiom-mir/axm-front-door"
CONSUMER_COMMIT = "05e25b557d076551ac740c4e043a9ccbbb0160ba"
SOURCE_NAME = "AXM_MONOLITH_SOURCE.json"
RECEIPT_NAME = "FRONTDOOR_DISCOVERY_BRIDGE.json"


class BridgeError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError(f"cannot read valid JSON: {path}: {exc}") from exc


def _snapshot_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    modules = root / "modules"
    if root.is_symlink() or not root.is_dir() or modules.is_symlink() or not modules.is_dir():
        raise BridgeError("snapshot must be one real directory containing modules/")
    return root


def _module(root: Path, name: str) -> Path:
    modules = (root / "modules").resolve()
    candidate = (modules / name).resolve()
    try:
        candidate.relative_to(modules)
    except ValueError as exc:
        raise BridgeError(f"module path escapes snapshot: {name}") from exc
    if candidate.is_symlink() or not candidate.is_dir():
        raise BridgeError(f"selected module missing: {name}")
    return candidate


def _identity(module: Path) -> tuple[str, str]:
    record = _read_json(module / SOURCE_NAME)
    if not isinstance(record, dict):
        raise BridgeError(f"malformed {SOURCE_NAME}: {module}")
    return str(record.get("repository") or ""), str(record.get("commit") or "").lower()


def _run(argv: list[str], cwd: Path, env: dict[str, str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def run(snapshot: str | Path) -> dict[str, Any]:
    root = _snapshot_root(snapshot)
    provider_source = _module(root, PROVIDER_MODULE)
    consumer_source = _module(root, CONSUMER_MODULE)

    provider_identity = _identity(provider_source)
    consumer_identity = _identity(consumer_source)
    if provider_identity != (PROVIDER_REPOSITORY, PROVIDER_COMMIT):
        return {
            "schema": "axm.monolith.frontdoor-discovery-bridge/v0.1",
            "status": "HOLD_PROVIDER_REF_MISMATCH",
            "executed": False,
            "observed": {"repository": provider_identity[0], "commit": provider_identity[1]},
        }
    if consumer_identity != (CONSUMER_REPOSITORY, CONSUMER_COMMIT):
        return {
            "schema": "axm.monolith.frontdoor-discovery-bridge/v0.1",
            "status": "HOLD_CONSUMER_REF_MISMATCH",
            "executed": False,
            "observed": {"repository": consumer_identity[0], "commit": consumer_identity[1]},
        }

    provider_tool = provider_source / "tools" / "build_portable_discovery.py"
    consumer_tool = consumer_source / "scripts" / "portable_discovery_intake.py"
    if not provider_tool.is_file() or not consumer_tool.is_file():
        return {
            "schema": "axm.monolith.frontdoor-discovery-bridge/v0.1",
            "status": "HOLD_EXACT_BRIDGE_SURFACE_MISSING",
            "executed": False,
        }

    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"}
    with tempfile.TemporaryDirectory(prefix="axm-frontdoor-discovery-") as td:
        work = Path(td)
        provider = work / "provider"
        consumer = work / "consumer"
        ignore = shutil.ignore_patterns(".git", "__pycache__", ".venv", "node_modules")
        shutil.copytree(provider_source, provider, ignore=ignore)
        shutil.copytree(consumer_source, consumer, ignore=ignore)

        artifact = work / "discovery-buddy.pyz"
        provider_receipt = work / "discovery-buddy.pyz.receipt.json"
        commands: list[dict[str, Any]] = []
        for argv in (
            [sys.executable, str(provider / "tools" / "build_portable_discovery.py"), "build", "--output", str(artifact), "--receipt", str(provider_receipt)],
            [sys.executable, str(provider / "tools" / "build_portable_discovery.py"), "verify", "--output", str(artifact), "--receipt", str(provider_receipt)],
        ):
            cp = _run(argv, provider, env)
            commands.append({"argv": argv, "returncode": cp.returncode, "stdout_tail": (cp.stdout or "")[-4000:]})
            if cp.returncode != 0:
                return {
                    "schema": "axm.monolith.frontdoor-discovery-bridge/v0.1",
                    "status": "HOLD_PROVIDER_BUILD_OR_VERIFY_FAILED",
                    "executed": True,
                    "commands": commands,
                }

        provider_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        fleet = work / "fleet" / "example"
        (fleet / ".git").mkdir(parents=True)
        (fleet / ".axm").mkdir(parents=True)
        (fleet / "registry").mkdir(parents=True)
        (fleet / ".axm" / "discovery-public.json").write_text(
            '{"schema":"axm.discovery-public/v1","repo":"mike-axiom-mir/example-provider","display_name":"Example Provider","public":true}\n',
            encoding="utf-8",
        )
        (fleet / "registry" / "capabilities.jsonl").write_text(
            '{"id":"axm.example-capability/v1","providers":["example-provider"],"consumers":[],"status":"IMPLEMENTED_REFERENCE"}\n',
            encoding="utf-8",
        )

        intake = work / "frontdoor-intake.json"
        bridge = work / "frontdoor-portable-bridge.json"
        argv = [
            sys.executable,
            str(consumer / "scripts" / "portable_discovery_intake.py"),
            "--provider", str(artifact),
            "--provider-sha256", provider_sha,
            "--workspace", str(work / "fleet"),
            "--output", str(intake),
            "--receipt", str(bridge),
        ]
        cp = _run(argv, consumer, {**env, "PYTHONPATH": ""})
        commands.append({"argv": argv, "returncode": cp.returncode, "stdout_tail": (cp.stdout or "")[-4000:]})
        if cp.returncode != 0 or not intake.is_file() or not bridge.is_file():
            return {
                "schema": "axm.monolith.frontdoor-discovery-bridge/v0.1",
                "status": "HOLD_FRONTDOOR_BRIDGE_FAILED",
                "executed": True,
                "commands": commands,
            }

        intake_data = _read_json(intake)
        bridge_data = _read_json(bridge)
        provider_data = _read_json(provider_receipt)
        checks = {
            "intake_review_only": intake_data.get("summary") == {
                "capability_records": 1,
                "ready_for_publication": 0,
                "repositories": 1,
                "requires_human_review": 1,
            },
            "no_publish_authority": (intake_data.get("authority") or {}).get("publish") is False,
            "no_registry_write_authority": (intake_data.get("authority") or {}).get("registry_write") is False,
            "bridge_schema": bridge_data.get("schema") == "axm.frontdoor.portable-discovery-intake/v0.1",
            "exact_provider_hash": (bridge_data.get("provider") or {}).get("artifact_sha256") == provider_sha,
            "no_automatic_download": (bridge_data.get("provider") or {}).get("automatic_download") is False,
            "offline_provider": (provider_data.get("artifact") or {}).get("network_required") is False,
            "dependency_free_provider": (provider_data.get("artifact") or {}).get("runtime_dependencies") == [],
        }
        return {
            "schema": "axm.monolith.frontdoor-discovery-bridge/v0.1",
            "status": "PASS" if all(checks.values()) else "HOLD_CONTRACT_CHECK_FAILED",
            "executed": True,
            "provider_module": PROVIDER_MODULE,
            "provider_repository": PROVIDER_REPOSITORY,
            "provider_commit": PROVIDER_COMMIT,
            "consumer_module": CONSUMER_MODULE,
            "consumer_repository": CONSUMER_REPOSITORY,
            "consumer_commit": CONSUMER_COMMIT,
            "checks": checks,
            "provider_artifact_sha256": provider_sha,
            "commands": commands,
            "intake_summary": intake_data.get("summary"),
            "intake_authority": intake_data.get("authority"),
            "source_snapshot_mutated": False,
            "truth_boundary": "PASS proves only the exact pinned Discovery Buddy portable provider can feed the exact pinned Front Door review-only intake in an isolated copied workspace; it grants no publication, registry-write, merge or CANON authority.",
        }


def apply(snapshot: str | Path) -> dict[str, Any]:
    root = _snapshot_root(snapshot)
    result = run(root)
    (root / RECEIPT_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the exact Discovery Buddy -> Front Door review-intake bridge")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = apply(args.snapshot)
    except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
