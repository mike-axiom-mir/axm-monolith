#!/usr/bin/env python3
"""AXM Monolith on-demand public-stack assembler.

This tool is intentionally inert until a human or machine explicitly runs a command.
It discovers only PUBLIC repositories owned by the configured AXM owner, applies an
explicit exclusion list, pins exact default-branch commit SHAs, and can materialize a
namespaced full-stack snapshot without modifying any source repository.

When a build is finally enabled, the materialized stack is automatically passed to the
local deterministic stack inspector and the AI-native capability/user-facing generator.
The result contains an offline capability map, candidate connection graph, human-test
queue, and a default OPEN_ME.html Capability Lab with a machine input path into
browser-facing surfaces.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

API_ROOT = "https://api.github.com"
USER_AGENT = "axm-monolith/0.3"
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


def api_get_json(
    url: str,
    token: str | None = None,
    *,
    attempts: int = 4,
    timeout_seconds: float = 30.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    """Read GitHub JSON with bounded retries for transient transport failures."""
    if attempts < 1:
        raise AssemblyError("GitHub API attempts must be at least one")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with opener(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code not in retryable_statuses or attempt == attempts:
                raise AssemblyError(
                    f"GitHub API error {exc.code} for {url} after {attempt} attempt(s): {detail}"
                ) from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = min(float(retry_after), 8.0) if retry_after else min(0.5 * (2 ** (attempt - 1)), 4.0)
            except ValueError:
                delay = min(0.5 * (2 ** (attempt - 1)), 4.0)
            sleeper(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts:
                raise AssemblyError(
                    f"GitHub API unavailable for {url} after {attempt} attempt(s): {exc}"
                ) from exc
            sleeper(min(0.5 * (2 ** (attempt - 1)), 4.0))
    raise AssemblyError(f"GitHub API unavailable for {url}")


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

    def resolve_head(repo: dict[str, Any]) -> dict[str, Any]:
        full = repo["full_name"]
        branch = urllib.parse.quote(repo["default_branch"], safe="")
        url = f"{API_ROOT}/repos/{full}/commits/{branch}"
        method = "github-api"
        try:
            commit = getter(url, token)
            sha = str((commit or {}).get("sha", ""))
        except AssemblyError as api_error:
            try:
                ref = f"refs/heads/{repo['default_branch']}"
                line = run_git(["ls-remote", "--refs", repo["clone_url"], ref])
                sha = line.split(maxsplit=1)[0] if line else ""
                method = "git-ls-remote-fallback"
            except AssemblyError as git_error:
                raise AssemblyError(
                    f"could not resolve exact default-branch head for {full}; "
                    f"API failed ({api_error}); Git fallback failed ({git_error})"
                ) from git_error
        if len(sha) != 40:
            raise AssemblyError(f"could not resolve exact default-branch head for {full}")
        return {**repo, "commit": sha, "head_resolution": method}

    configured_workers = config.get("selection", {}).get("plan_workers", 8)
    if not isinstance(configured_workers, int) or not 1 <= configured_workers <= 16:
        raise AssemblyError("selection.plan_workers must be an integer between 1 and 16")
    by_name: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(configured_workers, max(1, len(eligible)))) as executor:
        futures = {executor.submit(resolve_head, repo): repo["full_name"] for repo in eligible}
        for future in as_completed(futures):
            module = future.result()
            by_name[module["full_name"]] = module
    modules = [by_name[repo["full_name"]] for repo in eligible]

    return {
        "schema_version": "0.3",
        "owner": config["owner"],
        "selection": config["selection"],
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "module_count": len(modules),
        "modules": modules,
        "excluded_or_rejected": rejected,
        "truth_boundary": "plan contains only public owner repositories that passed the configured selection boundary; every module has an exact SHA; no source repository was modified",
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
        from user_surface import generate_user_surface
    except ImportError as exc:
        raise AssemblyError("stack inspector/user surface is missing; tools/inspect_stack.py and tools/user_surface.py must be present") from exc
    try:
        analysis = analyze_build(output)
        user_surface = generate_user_surface(output)
        return {**analysis, "user_surface": user_surface}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise AssemblyError(f"stack analysis/user-surface generation failed after materialization: {exc}") from exc


def run_snapshot_plumbing(output: Path, *, refresh_analysis: bool = False) -> dict[str, Any]:
    try:
        from monolith_plumbing import plumb_snapshot
    except ImportError as exc:
        raise AssemblyError("monolith plumbing is missing; tools/monolith_plumbing.py must be present") from exc
    try:
        return plumb_snapshot(output, refresh_analysis=refresh_analysis)
    except (ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        raise AssemblyError(f"snapshot plumbing failed after materialization: {exc}") from exc


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
        "schema_version": "0.3",
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
        manifest["plumbing"] = run_snapshot_plumbing(output, refresh_analysis=False)
        with (output / "MONOLITH_MANIFEST.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return manifest


def inspect_existing_build(path: Path) -> dict[str, Any]:
    if not (path / "modules").is_dir():
        raise AssemblyError(f"missing modules directory in build: {path}")
    analysis = run_stack_analysis(path)
    plumbing = run_snapshot_plumbing(path, refresh_analysis=False)
    return {"analysis": analysis, "plumbing": plumbing}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AXM on-demand public-stack monolith assembler")
    parser.add_argument("--config", default="config/assembly.json", help="path to assembly config (default: config/assembly.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover", help="read-only: print eligible and rejected repositories; resolve no commit pins")
    sub.add_parser("plan", help="read-only: resolve exact public default-branch heads and print a reproducible plan")
    build = sub.add_parser("build", help="materialize an on-demand full-stack snapshot, analyze it, and generate the default capability lab")
    build.add_argument("--output", required=True, help="new or empty output directory")
    build.add_argument("--confirm-build", action="store_true", help="required explicit acknowledgement; without it build refuses to create a monolith")
    inspect = sub.add_parser("inspect", help="offline: analyze/re-analyze an already materialized build and regenerate the capability lab")
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
