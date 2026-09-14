#!/usr/bin/env python3
"""Learned exact upstream-provider wiring for selected AXM modules.

This rule came from a real current-totality integration: `axm-global-state-rts`
contains `UPSTREAM_PLANET.json` plus `.gitmodules` declaring an exact pinned
`foundation-planet-experiments` provider at `planet-upstream`. The same provider
is also selected as its own monolith module at that exact repository + commit.

The rule is intentionally narrow. It resolves only the known manifest schema,
requires the declared git-submodule path/repository to agree, and requires exactly
one selected provider module with the exact pinned repository + commit. `apply`
records the resolvable wiring but never alters donor module bytes. `stage` copies
that exact provider only into an isolated caller-supplied execution workspace.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

MANIFEST_NAME = "UPSTREAM_PLANET.json"
MANIFEST_SCHEMA = "axm.global-state-rts.upstream-planet/v0.1"
SOURCE_NAME = "AXM_MONOLITH_SOURCE.json"
RECEIPT_NAME = "UPSTREAM_PROVIDER_WIRING.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


class UpstreamProviderWiringError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UpstreamProviderWiringError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UpstreamProviderWiringError(f"invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _snapshot_root(snapshot: str | Path) -> Path:
    root = Path(snapshot).resolve()
    modules = root / "modules"
    if root.is_symlink() or not root.is_dir() or modules.is_symlink() or not modules.is_dir():
        raise UpstreamProviderWiringError("snapshot must be one real directory containing modules/")
    return root


def _safe_module(root: Path, name: str) -> Path:
    if not name or not SAFE_COMPONENT.fullmatch(name):
        raise UpstreamProviderWiringError(f"unsafe module name: {name!r}")
    modules = (root / "modules").resolve()
    candidate = (modules / name).resolve()
    try:
        candidate.relative_to(modules)
    except ValueError as exc:
        raise UpstreamProviderWiringError(f"module path escapes snapshot: {name}") from exc
    if candidate.is_symlink() or not candidate.is_dir():
        raise UpstreamProviderWiringError(f"module directory missing or unsafe: {name}")
    return candidate


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UpstreamProviderWiringError(f"unsafe submodule_path: {value!r}")
    if not all(SAFE_COMPONENT.fullmatch(part) for part in path.parts):
        raise UpstreamProviderWiringError(f"unsafe submodule_path component: {value!r}")
    return path


def _expected_git_url(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def _gitmodule_declared(consumer: Path, submodule_path: str, repository: str) -> bool:
    path = consumer / ".gitmodules"
    if path.is_symlink() or not path.is_file():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return False
    wanted_url = _expected_git_url(repository)
    for section in parser.sections():
        if parser.get(section, "path", fallback="").strip() == submodule_path and parser.get(section, "url", fallback="").strip() == wanted_url:
            return True
    return False


def _source_record(module_root: Path) -> dict[str, Any] | None:
    path = module_root / SOURCE_NAME
    if path.is_symlink() or not path.is_file():
        return None
    value = _read_json(path)
    return value if isinstance(value, dict) else None


def _tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(hashlib.sha256(data).digest())
    return "sha256:" + digest.hexdigest()


def resolve(snapshot: str | Path, consumer_module: str) -> dict[str, Any]:
    root = _snapshot_root(snapshot)
    consumer = _safe_module(root, consumer_module)
    manifest_path = consumer / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return {"status": "NOT_APPLICABLE", "consumer_module": consumer_module, "reason": f"no {MANIFEST_NAME}"}

    try:
        manifest = _read_json(manifest_path)
        if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
            raise UpstreamProviderWiringError("unsupported or malformed upstream manifest schema")
        repository = str(manifest.get("source_repository") or "")
        commit = str(manifest.get("source_commit") or "").lower()
        submodule_path = str(manifest.get("submodule_path") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise UpstreamProviderWiringError(f"invalid source_repository: {repository!r}")
        if not HEX40.fullmatch(commit):
            raise UpstreamProviderWiringError(f"invalid source_commit: {commit!r}")
        _safe_relative_path(submodule_path)
        if not _gitmodule_declared(consumer, submodule_path, repository):
            raise UpstreamProviderWiringError(".gitmodules does not match manifest path/repository")

        matches: list[tuple[str, Path, dict[str, Any]]] = []
        for module_dir in sorted((root / "modules").iterdir()):
            if module_dir.is_symlink() or not module_dir.is_dir():
                continue
            record = _source_record(module_dir)
            if not record:
                continue
            if str(record.get("repository") or "") == repository and str(record.get("commit") or "").lower() == commit:
                matches.append((module_dir.name, module_dir, record))
        if len(matches) != 1:
            raise UpstreamProviderWiringError(
                f"exact selected provider match count is {len(matches)} for {repository}@{commit}"
            )
        provider_module, provider_root, provider_record = matches[0]
        consumer_record = _source_record(consumer) or {}
        return {
            "schema": "axm.monolith.exact-upstream-provider/v0.1",
            "status": "PASS",
            "consumer_module": consumer_module,
            "consumer_repository": str(consumer_record.get("repository") or ""),
            "consumer_commit": str(consumer_record.get("commit") or ""),
            "provider_module": provider_module,
            "provider_repository": repository,
            "provider_commit": commit,
            "provider_source_record": provider_record,
            "submodule_path": submodule_path,
            "manifest": MANIFEST_NAME,
            "manifest_schema": MANIFEST_SCHEMA,
            "provider_root": provider_root.as_posix(),
            "truth_boundary": "Exact selected-provider identity and declared submodule placement are verified; interoperability still requires execution/test evidence.",
        }
    except (UpstreamProviderWiringError, OSError, ValueError) as exc:
        return {
            "schema": "axm.monolith.exact-upstream-provider/v0.1",
            "status": "HOLD",
            "consumer_module": consumer_module,
            "reason": str(exc),
            "truth_boundary": "A declared upstream dependency is never staged when identity/path evidence is incomplete or mismatched.",
        }


def stage(snapshot: str | Path, consumer_module: str, consumer_copy: str | Path) -> dict[str, Any]:
    root = _snapshot_root(snapshot)
    resolution = resolve(root, consumer_module)
    if resolution.get("status") != "PASS":
        return resolution

    provider = _safe_module(root, str(resolution["provider_module"]))
    work = Path(consumer_copy).resolve()
    if work.is_symlink() or not work.is_dir():
        raise UpstreamProviderWiringError("consumer_copy must be a real isolated workspace directory")
    relative = _safe_relative_path(str(resolution["submodule_path"]))
    destination = (work / relative).resolve()
    try:
        destination.relative_to(work)
    except ValueError as exc:
        raise UpstreamProviderWiringError("staging destination escapes isolated workspace") from exc
    if destination.exists() or destination.is_symlink():
        raise UpstreamProviderWiringError(f"staging destination already exists: {relative.as_posix()}")

    before = _tree_fingerprint(provider)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        provider,
        destination,
        symlinks=False,
        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".pytest_cache"),
    )
    after = _tree_fingerprint(provider)
    if before != after:
        raise UpstreamProviderWiringError("provider donor bytes changed while staging isolated copy")

    return {
        **{k: v for k, v in resolution.items() if k != "provider_root"},
        "status": "STAGED_EXACT_PROVIDER_COPY",
        "staged_relative_path": relative.as_posix(),
        "provider_donor_fingerprint_before": before,
        "provider_donor_fingerprint_after": after,
        "provider_donor_unchanged": True,
        "consumer_donor_unchanged": True,
        "staging_scope": "isolated copied execution workspace only",
        "truth_boundary": "Exact selected provider was copied into the consumer's declared submodule path only inside the temporary execution workspace; this staging alone does not prove interoperability.",
    }


def apply(snapshot: str | Path) -> dict[str, Any]:
    root = _snapshot_root(snapshot)
    entries: list[dict[str, Any]] = []
    for module_dir in sorted((root / "modules").iterdir()):
        if module_dir.is_symlink() or not module_dir.is_dir() or not (module_dir / MANIFEST_NAME).is_file():
            continue
        result = resolve(root, module_dir.name)
        if result.get("status") != "NOT_APPLICABLE":
            result = {k: v for k, v in result.items() if k != "provider_root"}
            entries.append(result)
    counts: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    payload = {
        "schema": "axm.monolith.upstream-provider-wiring-registry/v0.1",
        "status": "PASS" if not entries or all(item.get("status") == "PASS" for item in entries) else "PASS_WITH_HOLDS",
        "entry_count": len(entries),
        "status_counts": dict(sorted(counts.items())),
        "entries": entries,
        "donor_module_bytes_modified": False,
        "truth_boundary": "Registry entries prove only exact manifest/submodule/provider identity resolution. Actual interoperability remains separate execution/test evidence.",
    }
    _write_json(root / RECEIPT_NAME, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve exact selected upstream providers for an AXM monolith snapshot")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = apply(args.snapshot)
    except (UpstreamProviderWiringError, OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
