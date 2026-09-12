#!/usr/bin/env python3
"""AXM Monolith on-demand public-stack assembler.

This tool is intentionally inert until a human or machine explicitly runs a command.
It discovers only PUBLIC repositories owned by the configured AXM owner, applies an
explicit exclusion list, pins exact default-branch commit SHAs, and can materialize a
namespaced full-stack snapshot without modifying any source repository.

When a build is finally enabled, the materialized stack is automatically passed to the
local deterministic stack inspector so the output contains an offline capability map,
candidate connection graph, human-test queue, and OPEN_ME.html dashboard.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

API_ROOT = "https://api.github.com"
USER_AGENT = "axm-monolith/0.2"
SELF_REPO = "mike-axiom-mir/axm-monolith"


class AssemblyError(RuntimeError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    required = ["owner", "selection", "excluded_repositories"]
    missing = [key for key in required if key not in config]
    if missing:
        raise AssemblyError(f"config missing required keys: {', '.join(missing)}")
    if config["selection"].get("visibility") != "public-only":
        raise AssemblyError("selection.visibility must remain 'public-only'")
    return config


def api_get_json(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssemblyError(f"GitHub API error {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AssemblyError(f"GitHub API unavailable for {url}: {exc}") from exc


def exclusion_map(config: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in config.get("excluded_repositories", []):
        if isinstance(entry, str):
            result[entry.lower()] = "explicitly excluded"
            continue
        repo = str(entry.get("repository", "")).strip()
        if not repo:
            raise AssemblyError("excluded_repositories entry missing repository")
        result[repo.lower()] = str(entry.get("reason", "explicitly excluded"))
    result[SELF_REPO.lower()] = "assembler must never recursively assemble itself"
    return result


def filter_repositories(
    repositories: Iterable[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    owner = str(config["owner"])
    selection = config["selection"]
    excluded = exclusion_map(config)
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for repo in repositories:
        full_name = str(repo.get("full_name", ""))
        name = str(repo.get("name", ""))
        repo_owner = str((repo.get("owner") or {}).get("login", ""))
        reason: str | None = None

        if not full_name or not name:
            reason = "missing repository identity"
        elif repo_owner.lower() != owner.lower():
            reason = "owner mismatch"
        elif bool(repo.get("private", False)):
            reason = "private repository rejected by invariant"
        elif repo.get("visibility") not in (None, "public"):
            reason = f"non-public visibility rejected: {repo.get('visibility')}"
        elif not selection.get("include_forks", False) and bool(repo.get("fork", False)):
            reason = "fork excluded by policy"
        elif not selection.get("include_archived", False) and bool(repo.get("archived", False)):
            reason = "archived repository excluded by policy"
        elif full_name.lower() in excluded:
            reason = excluded[full_name.lower()]

        if reason:
            rejected.append({"repository": full_name or name or "<unknown>", "reason": reason})
            continue

        clone_url = str(repo.get("clone_url", ""))
        default_branch = str(repo.get("default_branch", ""))
        if not clone_url.startswith("https://github.com/") or not default_branch:
            rejected.append({"repository": full_name, "reason": "missing safe public HTTPS clone URL or default branch"})
            continue

        eligible.append({
            "name": name,
            "full_name": full_name,
            "clone_url": clone_url,
            "default_branch": default_branch,
            "archived": bool(repo.get("archived", False)),
            "fork": bool(repo.get("fork", False)),
        })

    eligible.sort(key=lambda item: item["full_name"].lower())
    rejected.sort(key=lambda item: item["repository"].lower())
    return eligible, rejected


def discover_public_repositories(
    config: dict[str, Any], getter: Callable[[str, str | None], Any] = api_get_json
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    owner = urllib.parse.quote(str(config["owner"]), safe="")
    token = os.environ.get("GITHUB_TOKEN")
    page = 1
    raw: list[dict[str, Any]] = []
    while True:
        # Public endpoint deliberately prevents a token from widening discovery to private repos.
        url = f"{API_ROOT}/users/{owner}/repos?type=owner&sort=full_name&direction=asc&per_page=100&page={page}"
        payload = getter(url, token)
        if not isinstance(payload, list):
            raise AssemblyError("unexpected GitHub repository discovery payload")
        raw.extend(payload)
        if len(payload) < 100:
            break
        page += 1
    return filter_repositories(raw, config)


def resolve_plan(
    config: dict[str, Any], getter: Callable[[str, str | None], Any] = api_get_json
) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN")
    eligible, rejected = discover_public_repositories(config, getter=getter)
    modules: list[dict[str, Any]] = []
    for repo in eligible:
        full = repo["full_name"]
        branch = urllib.parse.quote(repo["default_branch"], safe="")
        url = f"{API_ROOT}/repos/{full}/commits/{branch}"
        commit = getter(url, token)
        sha = str((commit or {}).get("sha", ""))
        if len(sha) != 40:
            raise AssemblyError(f"could not resolve exact default-branch head for {full}")
        modules.append({**repo, "commit": sha})

    return {
        "schema_version": "0.2",
        "owner": config["owner"],
        "selection": config["selection"],
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "module_count": len(modules),
        "modules": modules,
        "excluded_or_rejected": rejected,
        "truth_boundary": "plan contains only public owner repositories that passed the configured selection boundary; no source repository was modified",
    }


def run_git(args: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except FileNotFoundError as exc:
        raise AssemblyError("git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise AssemblyError(f"git command failed: git {' '.join(args)}\n{exc.stderr.strip()}") from exc
    return completed.stdout.strip()


def safe_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise AssemblyError(f"refusing to build into non-empty directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def materialize_module(module: dict[str, Any], modules_dir: Path, strip_git: bool) -> dict[str, Any]:
    destination = modules_dir / module["name"]
    if destination.exists():
        raise AssemblyError(f"duplicate module destination: {destination}")
    destination.mkdir(parents=True)

    run_git(["init", "-q"], cwd=destination)
    run_git(["remote", "add", "origin", module["clone_url"]], cwd=destination)
    run_git(["fetch", "-q", "--depth=1", "origin", module["commit"]], cwd=destination)
    run_git(["checkout", "-q", "--detach", "FETCH_HEAD"], cwd=destination)
    actual = run_git(["rev-parse", "HEAD"], cwd=destination)
    if actual != module["commit"]:
        raise AssemblyError(f"materialized SHA mismatch for {module['full_name']}: expected {module['commit']}, got {actual}")

    source_record = {
        "repository": module["full_name"],
        "source_url": module["clone_url"],
        "default_branch_at_plan_time": module["default_branch"],
        "commit": module["commit"],
        "visibility": "public",
    }
    with (destination / "AXM_MONOLITH_SOURCE.json").open("w", encoding="utf-8") as handle:
        json.dump(source_record, handle, indent=2, sort_keys=True)
        handle.write("\n")

    if strip_git:
        shutil.rmtree(destination / ".git")

    return {"repository": module["full_name"], "commit": module["commit"], "path": f"modules/{module['name']}", "materialized": True}


def run_stack_analysis(output: Path) -> dict[str, Any]:
    try:
        from inspect_stack import analyze_build
    except ImportError as exc:
        raise AssemblyError("stack inspector is missing; tools/inspect_stack.py must be present") from exc
    try:
        return analyze_build(output)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise AssemblyError(f"stack analysis failed after materialization: {exc}") from exc


def build_monolith(config: dict[str, Any], output: Path, confirm: bool) -> dict[str, Any]:
    if not bool(config.get("build_enabled", False)):
        raise AssemblyError("build is currently disabled by config hold; finish/reconcile the growth merge batch before enabling it")
    if not confirm:
        raise AssemblyError("build is inert by default; pass --confirm-build to materialize a monolith")

    plan = resolve_plan(config)
    safe_output_dir(output)
    modules_dir = output / "modules"
    modules_dir.mkdir()

    with (output / "axm-stack.lock.json").open("w", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=2, sort_keys=True)
        handle.write("\n")

    strip_git = bool(config.get("output", {}).get("strip_nested_git", True))
    materialized: list[dict[str, Any]] = []
    for module in plan["modules"]:
        materialized.append(materialize_module(module, modules_dir, strip_git=strip_git))

    inventory_lines = [
        "# AXM Monolith Inventory", "", f"Modules: {len(materialized)}", "",
        "Every module below was public at discovery time and pinned to the exact SHA in `axm-stack.lock.json`.", "",
    ]
    inventory_lines.extend(f"- `{item['repository']}` @ `{item['commit']}` → `{item['path']}`" for item in materialized)
    inventory_lines.extend(["", "No source repository was modified. Repository identities remain namespaced rather than flattened together.", ""])
    (output / "INVENTORY.md").write_text("\n".join(inventory_lines), encoding="utf-8")

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "source_lock": "axm-stack.lock.json",
        "module_count": len(materialized),
        "modules": materialized,
        "namespace_rule": "each source repository remains in its own modules/<repo> directory; no files are flattened or silently merged",
        "source_mutation": "none; assembly is read-only against source repositories",
    }
    with (output / "MONOLITH_MANIFEST.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    if bool(config.get("analysis", {}).get("enabled", True)):
        manifest["analysis"] = run_stack_analysis(output)
        with (output / "MONOLITH_MANIFEST.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return manifest


def inspect_existing_build(path: Path) -> dict[str, Any]:
    if not (path / "modules").is_dir():
        raise AssemblyError(f"missing modules directory in build: {path}")
    return run_stack_analysis(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AXM on-demand public-stack monolith assembler")
    parser.add_argument("--config", default="config/assembly.json", help="path to assembly config (default: config/assembly.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover", help="read-only: print eligible and rejected repositories; resolve no commit pins")
    sub.add_parser("plan", help="read-only: resolve exact public default-branch heads and print a reproducible plan")
    build = sub.add_parser("build", help="materialize an on-demand full-stack snapshot and analyze it")
    build.add_argument("--output", required=True, help="new or empty output directory")
    build.add_argument("--confirm-build", action="store_true", help="required explicit acknowledgement; without it build refuses to create a monolith")
    inspect = sub.add_parser("inspect", help="offline: analyze/re-analyze an already materialized build")
    inspect.add_argument("--build", required=True, help="existing monolith build directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(Path(args.config))
        if args.command == "discover":
            eligible, rejected = discover_public_repositories(config)
            print(json.dumps({"eligible_count": len(eligible), "eligible": eligible, "excluded_or_rejected": rejected, "source_mutation": "none"}, indent=2, sort_keys=True))
            return 0
        if args.command == "plan":
            print(json.dumps(resolve_plan(config), indent=2, sort_keys=True))
            return 0
        if args.command == "build":
            print(json.dumps(build_monolith(config, Path(args.output), confirm=args.confirm_build), indent=2, sort_keys=True))
            return 0
        if args.command == "inspect":
            print(json.dumps(inspect_existing_build(Path(args.build)), indent=2, sort_keys=True))
            return 0
        raise AssemblyError(f"unknown command: {args.command}")
    except AssemblyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
