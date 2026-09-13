#!/usr/bin/env python3
"""Execute a bounded Ghost Studio asset trial from one assembled AXM snapshot.

This is deliberately a cross-module experiment, not a new source home. It reads
the pinned monolith, invokes Universal Creation and Game Asset Forge in place,
and publishes only a separate receipt-bearing result directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


SCHEMA = "axm.monolith.ghost-studio-asset-trial/v0.1"
REQUIRED_MODULES = (
    "axm-ghost-studio",
    "axm-universal-creation",
    "Axm-game-assets",
)


class TrialError(RuntimeError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _portable_receipt_paths(value: Any, stage: Path) -> Any:
    """Replace staging-root paths with portable paths and reject escapes."""
    if isinstance(value, list):
        return [_portable_receipt_paths(item, stage) for item in value]
    if not isinstance(value, dict):
        return value
    portable: dict[str, Any] = {}
    for key, item in value.items():
        if key == "path" and isinstance(item, str) and Path(item).is_absolute():
            try:
                portable[key] = Path(item).relative_to(stage).as_posix()
            except ValueError as exc:
                raise TrialError("generated receipt path escaped the staging directory") from exc
        else:
            portable[key] = _portable_receipt_paths(item, stage)
    return portable


def load_snapshot(build: str | Path) -> dict[str, Any]:
    root = Path(build).resolve()
    if root.is_symlink() or not root.is_dir():
        raise TrialError("build must be a real assembled directory")
    lock_path = root / "axm-stack.lock.json"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise TrialError("assembled snapshot lock is missing")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrialError("assembled snapshot lock is not valid UTF-8 JSON") from exc
    modules = lock.get("modules")
    if not isinstance(modules, list):
        raise TrialError("assembled snapshot lock has no module list")
    by_name = {
        item.get("name"): item
        for item in modules
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    missing = [name for name in REQUIRED_MODULES if name not in by_name]
    if missing:
        raise TrialError(f"assembled snapshot lacks required modules: {missing}")
    roots = {name: root / "modules" / name for name in REQUIRED_MODULES}
    for name, module_root in roots.items():
        if module_root.is_symlink() or not module_root.is_dir():
            raise TrialError(f"materialized module is missing or unsafe: {name}")
    charter = roots["axm-ghost-studio"] / "GAME_CHARTER.md"
    if charter.is_symlink() or not charter.is_file():
        raise TrialError("Ghost Studio GAME_CHARTER.md is missing")
    charter_bytes = charter.read_bytes()
    if b"Blackline Relay" not in charter_bytes:
        raise TrialError("Ghost Studio charter is not the expected Blackline Relay body")
    return {
        "root": root,
        "lock": lock,
        "lock_sha256": _sha256_file(lock_path),
        "module_records": {name: by_name[name] for name in REQUIRED_MODULES},
        "module_roots": roots,
        "charter_sha256": _sha256_bytes(charter_bytes),
    }


def _install_module_paths(snapshot: dict[str, Any]) -> None:
    roots = snapshot["module_roots"]
    for path in (
        roots["Axm-game-assets"],
        roots["axm-universal-creation"] / "src",
    ):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def _asset_meshes() -> dict[str, Any]:
    from native_geometry import combine, make_box, make_uv_sphere, translate
    from native_modeling import make_chamfered_box, make_cylinder

    core = combine(
        [
            make_cylinder(1.25, 0.42, segments=32, name="core-ring"),
            translate(make_uv_sphere(0.72, segments=24, rings=12, name="core-orb"), (0, 0, -0.15)),
            translate(make_box((0.22, 2.9, 0.28), name="core-spine"), (0, 0, 0.25)),
            translate(make_box((2.9, 0.22, 0.28), name="core-crossbar"), (0, 0, 0.25)),
        ],
        name="blackline-energy-core",
    )
    relay = combine(
        [
            make_chamfered_box(1.35, 2.25, 0.62, 0.16, name="relay-body"),
            translate(make_chamfered_box(1.7, 0.38, 0.76, 0.08, name="relay-foot"), (0, -1.18, 0)),
            translate(make_uv_sphere(0.36, segments=20, rings=10, name="relay-node"), (0, 0.55, -0.42)),
            translate(make_box((0.18, 1.0, 0.18), name="relay-antenna"), (0, 1.55, 0)),
            translate(make_box((0.22, 0.22, 0.22), name="relay-tip"), (0, 2.1, 0)),
        ],
        name="blackline-relay-beacon",
    )
    runner = combine(
        [
            make_chamfered_box(1.5, 0.82, 0.58, 0.16, name="runner-body"),
            translate(make_uv_sphere(0.38, segments=20, rings=10, name="runner-core"), (0, 0, -0.42)),
            translate(make_chamfered_box(0.52, 0.42, 0.68, 0.09, name="runner-left-pod"), (-0.92, -0.08, 0)),
            translate(make_chamfered_box(0.52, 0.42, 0.68, 0.09, name="runner-right-pod"), (0.92, -0.08, 0)),
            translate(make_box((0.3, 0.72, 0.18), name="runner-tail"), (0, 0.72, 0.18)),
        ],
        name="blackline-runner-drone",
    )
    return {mesh.name: mesh for mesh in (core, relay, runner)}


def _gallery_html(asset_names: list[str]) -> str:
    cards = []
    for name in asset_names:
        cards.append(
            f'<article><h2>{name}</h2><div class="views">'
            + "".join(
                f'<figure><img src="previews/{name}/{view}-normal.png" alt="{name} {view} diagnostic"><figcaption>{view}</figcaption></figure>'
                for view in ("front", "side", "top")
            )
            + f'</div><p><a href="deliveries/{name}.glb">GLB</a> · '
            f'<a href="packages/{name}/package-manifest.json">source manifest</a> · '
            f'<a href="previews/{name}/review.html">diagnostic board</a></p></article>'
        )
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Ghost Studio Asset Trial</title>
<style>:root{color-scheme:dark;--bg:#071014;--panel:#10242a;--line:#31525a;--teal:#35d4c4;--amber:#ffcc66}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#19363d,#071014 55%);color:#eef8f8;font:16px/1.5 system-ui,sans-serif}main{width:min(1100px,calc(100% - 28px));margin:auto;padding:34px 0 60px}h1{margin:.2rem 0;color:var(--teal)}.truth{max-width:75ch;color:#adc2c5}article{margin:18px 0;padding:18px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(145deg,var(--panel),#091417)}h2{margin-top:0;color:var(--amber)}.views{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}figure{margin:0;background:#020608;border-radius:10px;overflow:hidden}img{display:block;width:100%;image-rendering:pixelated}figcaption{padding:7px;text-align:center;text-transform:uppercase;font-size:.75rem;letter-spacing:.1em}a{color:var(--teal)}@media(max-width:700px){.views{grid-template-columns:1fr}}</style></head><body><main>
<p>AXM Monolith · executed cross-module proof</p><h1>Blackline Relay asset trial</h1>
<p class="truth">These are newly generated, deterministic prototype assets and diagnostic software renders. Structural and receipt checks passed; aesthetic quality, gameplay fit, animation, and engine performance are not automatically claimed.</p>
""" + "".join(cards) + """
<p><a href="TRIAL_RECEIPT.json">Open exact trial receipt</a> · <a href="visual-recipe.json">Open creation recipe</a></p>
</main></body></html>"""


def run_trial(build: str | Path, output: str | Path, *, seed: int = 104729) -> dict[str, Any]:
    snapshot = load_snapshot(build)
    destination = Path(output).resolve()
    if destination.exists():
        raise TrialError("output must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        _install_module_paths(snapshot)
        from axm_uc.visual_assets import generate_decal, generate_material, generate_texture
        from axm_uc.visual_creation_grammar import compile_visual_recipe
        from native_geometry import write_obj
        from native_glb_delivery import build_verified_glb_delivery, validate_glb_delivery
        from native_pbr import PaintedMetalSpec
        from native_pipeline import build_rigid_package, verify_rigid_package
        from native_preview import write_preview
        from native_visual_evidence import build_capture_packet, validate_capture_packet, write_capture_packet

        recipe_request = {
            "subject": "Blackline Relay energy core, relay beacon, and service runner asset family",
            "seed": seed,
            "aliases": ["3drender", "isometricview", "retrofuturistic", "texturefocus"],
            "style": ["moody"],
            "environment": ["studio"],
            "criteria": [
                "readable top-down silhouette",
                "shared family language",
                "core relay runner role distinction",
                "clear energy-node focal point",
            ],
            "constraints": [
                "original local offline assets",
                "preserve Ghost Studio source unchanged",
                "prototype geometry must not be called final art",
            ],
            "avoid": ["proprietary visual identity", "unreadable micro-detail", "false AAA claim"],
            "technical_requirements": {
                "delivery": "glb",
                "diagnostic_views": ["front", "side", "top"],
                "material_maps": ["base_color", "normal", "orm"],
            },
            "scene": {
                "focus": "three compact energy-service props",
                "lighting": "high-contrast teal and amber diagnostic stage",
                "atmosphere": "dark maintenance chamber",
                "environment_notes": "Blackline Relay browser-game direction source",
            },
        }
        recipe = compile_visual_recipe(recipe_request)
        _write_json(stage / "visual-recipe.json", recipe)

        uc_receipts = _portable_receipt_paths({
            "material": generate_material(stage / "universal-creation" / "sci-fi-material", "sci-fi", seed=seed, size=128),
            "circuit_texture": generate_texture(
                stage / "universal-creation" / "blackline-circuit.png",
                "circuit",
                seed=seed + 1,
                size=128,
                colors=("#071014", "#17343a", "#35d4c4", "#ffcc66"),
            ),
            "warning_decal": generate_decal(
                stage / "universal-creation" / "warning.svg", "warning", seed=seed + 2
            ),
        }, stage)
        _write_json(stage / "universal-creation" / "receipts.json", uc_receipts)

        specs = {
            "blackline-energy-core": PaintedMetalSpec(
                paint_rgb=(24, 85, 91), metal_rgb=(90, 126, 130), wear=0.2, scratches=10
            ),
            "blackline-relay-beacon": PaintedMetalSpec(
                paint_rgb=(36, 71, 77), metal_rgb=(118, 126, 128), wear=0.38, scratches=18
            ),
            "blackline-runner-drone": PaintedMetalSpec(
                paint_rgb=(166, 116, 36), metal_rgb=(102, 112, 116), wear=0.28, scratches=14
            ),
        }
        asset_receipts: dict[str, Any] = {}
        meshes = _asset_meshes()
        for index, (name, mesh) in enumerate(meshes.items()):
            obj_path = stage / "sources" / f"{name}.obj"
            obj_path.parent.mkdir(parents=True, exist_ok=True)
            write_obj(mesh, obj_path)
            package_root = stage / "packages" / name
            package = build_rigid_package(
                obj_path,
                package_root,
                uv_mode="auto",
                material_size=128,
                seed=seed + index * 101,
                spec=specs[name],
            )
            verification = verify_rigid_package(
                package_root, expected_manifest_sha256=package["manifest_sha256"]
            )
            delivery_path = stage / "deliveries" / f"{name}.glb"
            delivery_receipt = build_verified_glb_delivery(
                package_root,
                delivery_path,
                expected_manifest_sha256=package["manifest_sha256"],
            )
            glb_validation = validate_glb_delivery(delivery_path.read_bytes())
            preview = write_preview(mesh, stage / "previews" / name, size=256)
            capture_png = stage / "previews" / name / "top-normal.png"
            capture = build_capture_packet(
                capture_png.read_bytes(),
                asset_digest=delivery_receipt["delivery"]["sha256"],
                engine={"name": "AXM native_preview", "mode": "software diagnostic rasterizer"},
                camera={"projection": "orthographic", "view": "top"},
                render_settings={"size": [256, 256], "signal": "face-normal"},
                metrics={"coverage": preview["views"][2]["coverage"]},
                source_receipts=[package["manifest_sha256"]],
            )
            capture_validation = validate_capture_packet(capture, capture_png.read_bytes())
            write_capture_packet(stage / "previews" / name / "capture-receipt.json", capture)
            if verification["status"] != "pass" or glb_validation["status"] != "pass" or capture_validation["status"] != "pass":
                raise TrialError(f"asset verification failed: {name}")
            asset_receipts[name] = {
                "source_obj": {"path": obj_path.relative_to(stage).as_posix(), "sha256": _sha256_file(obj_path)},
                "package_manifest_sha256": package["manifest_sha256"],
                "package_verification": verification,
                "delivery": delivery_receipt["delivery"],
                "delivery_validation": glb_validation,
                "preview_report": f"previews/{name}/preview-report.json",
                "capture_validation": capture_validation,
            }

        (stage / "OPEN_ASSET_TRIAL.html").write_text(
            _gallery_html(list(meshes)), encoding="utf-8"
        )
        files = [
            {
                "path": path.relative_to(stage).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name != "TRIAL_RECEIPT.json"
        ]
        receipt = {
            "schema": SCHEMA,
            "status": "EXECUTED_AND_STRUCTURALLY_VERIFIED",
            "consumer": {
                "repository": "mike-axiom-mir/axm-ghost-studio",
                "charter_sha256": snapshot["charter_sha256"],
                "game": "Blackline Relay",
            },
            "snapshot": {
                "lock_sha256": snapshot["lock_sha256"],
                "module_count": len(snapshot["lock"]["modules"]),
                "required_modules": snapshot["module_records"],
            },
            "execution": {
                "universal_creation_recipe_sha256": "sha256:" + recipe["recipe_sha256"],
                "universal_creation_assets": uc_receipts,
                "game_asset_forge_assets": asset_receipts,
                "generated_file_count_excluding_receipt": len(files),
                "generated_files": files,
            },
            "source_mutation": "none",
            "truth": {
                "assembly_proven": True,
                "cross_module_asset_execution_proven_for_this_exact_trial": True,
                "all_224_detected_capabilities_executed": False,
                "diagnostic_pngs_are_not_engine_renders": True,
                "aesthetic_quality_or_gameplay_fit_proven": False,
                "animation_or_character_rigging_proven": False,
                "automatic_ghost_studio_adoption": False,
            },
            "authority": {
                "source_repository_mutation": False,
                "ghost_studio_installation": False,
                "visual_approval": False,
                "canon": False,
            },
        }
        _write_json(stage / "TRIAL_RECEIPT.json", receipt)
        os.replace(stage, destination)
        return receipt
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and verify a Ghost Studio asset pack from one AXM monolith snapshot")
    parser.add_argument("--build", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--confirm-create", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_create:
        parser.error("--confirm-create is required")
    try:
        result = run_trial(args.build, args.output, seed=args.seed)
    except TrialError as exc:
        raise SystemExit(f"Ghost Studio asset trial rejected: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
