#!/usr/bin/env python3
"""Build the Blackline Relay modular 3D kit from one AXM monolith snapshot.

The supplied reference sheet is treated as an authored direction/evidence input,
not as hidden geometry. AXM Game Asset Forge supplies native geometry and PBR
generation; Universal Creation supplies the structured visual recipe. Pillow is
used only as a declared compatible preview rasterizer.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Iterable


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ghost_studio_asset_trial import (  # noqa: E402
    TrialError,
    _install_module_paths,
    _portable_receipt_paths,
    _sha256_file,
    _write_json,
    load_snapshot,
)


SCHEMA = "axm.monolith.ghost-studio-reference-kit/v0.1"
SEED = 247031
CANONICAL_ASSETS = (
    "relay_online",
    "relay_offline",
    "relay_base",
    "conduit_segment",
    "floor_panel_1m",
    "wall_panel_2m",
    "door_closed",
    "platform_2m",
    "ramp_2m",
)

MATERIALS: dict[str, dict[str, Any]] = {
    "dark_metal": {
        "rgb": (24, 34, 39), "metal_rgb": (88, 101, 106), "metallic": 0.90,
        "roughness": 0.34, "wear": 0.24, "scratches": 14, "emissive": (0.0, 0.0, 0.0),
    },
    "light_metal": {
        "rgb": (95, 108, 113), "metal_rgb": (160, 169, 171), "metallic": 0.88,
        "roughness": 0.28, "wear": 0.18, "scratches": 10, "emissive": (0.0, 0.0, 0.0),
    },
    "black_rubber": {
        "rgb": (10, 15, 17), "metal_rgb": (36, 42, 44), "metallic": 0.18,
        "roughness": 0.67, "wear": 0.08, "scratches": 3, "emissive": (0.0, 0.0, 0.0),
    },
    "teal_glow": {
        "rgb": (18, 180, 164), "metal_rgb": (58, 232, 211), "metallic": 0.24,
        "roughness": 0.22, "wear": 0.05, "scratches": 1, "emissive": (0.05, 1.0, 0.86),
    },
    "red_glow": {
        "rgb": (190, 28, 31), "metal_rgb": (255, 70, 61), "metallic": 0.20,
        "roughness": 0.24, "wear": 0.06, "scratches": 1, "emissive": (1.0, 0.025, 0.018),
    },
    "amber_trim": {
        "rgb": (191, 126, 25), "metal_rgb": (235, 181, 69), "metallic": 0.68,
        "roughness": 0.30, "wear": 0.20, "scratches": 8, "emissive": (0.16, 0.075, 0.005),
    },
}


@dataclass(frozen=True, slots=True)
class Part:
    part_id: str
    mesh: Any
    material: str
    role: str


@dataclass(frozen=True, slots=True)
class Asset:
    asset_id: str
    label: str
    parts: tuple[Part, ...]
    collision: Any
    budget: int
    dimensions_note: str
    canonical: bool = True


def reference_contract() -> dict[str, Any]:
    return {
        "title": "AXM Ghost Studio — Blackline Relay Environment & Asset Reference v1.0",
        "art_direction": [
            "minimalist high-contrast industrial sci-fi maintenance facility",
            "readability over realism",
            "functional modular reusable forms",
            "high-contrast teal/red state communication",
            "minimal meaningful detail",
            "consistent real-world scale and grid",
            "clean technical slightly mysterious Blackline Relay tone",
        ],
        "scale": {
            "unit_m": 1.0,
            "relay_height_m": 3.0,
            "floor_panel_m": [1.0, 1.0],
            "wall_panel_m": [2.0, 2.0],
            "platform_footprint_m": [2.0, 2.0],
            "ramp_footprint_m": [2.0, 2.0],
        },
        "delivery": {
            "preferred": ["glb", "gltf"],
            "hero_triangle_budget": "<5000",
            "modular_triangle_budget": "<1000",
            "origin": "base/center",
            "pbr_maps": ["base_color", "normal", "roughness", "metallic", "orm"],
            "simple_collision": True,
        },
        "canonical_assets": list(CANONICAL_ASSETS),
        "state_variant": "conduit_segment_off",
    }


def validate_reference(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    if source.is_symlink() or not source.is_file():
        raise TrialError("reference must be one real image file")
    data = source.read_bytes()
    try:
        from PIL import Image
        with Image.open(source) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except Exception as exc:
        raise TrialError("Blackline Relay reference must be a valid PNG or JPEG image") from exc
    if image_format not in {"PNG", "JPEG"}:
        raise TrialError("Blackline Relay reference must be a PNG or JPEG image")
    if width < 800 or height < 500:
        raise TrialError("reference image is too small to bind as the supplied direction sheet")
    return {
        "source": source,
        "sha256": _sha256_file(source),
        "bytes": len(data),
        "dimensions_px": [width, height],
        "image_format": image_format,
        "stored_name": f"blackline-relay-reference-v1.{image_format.lower().replace('jpeg', 'jpg')}",
        "visible_evidence_verdict": "PASS_REFERENCE_SHEET_AVAILABLE",
    }


def _native_api(snapshot: dict[str, Any]) -> SimpleNamespace:
    _install_module_paths(snapshot)
    from native_construction_kit import beam_segment, lathe_profile, pipe_path, torus_ring
    from native_geometry import Mesh, bounds, combine, face_normal, topology_report, triangulate, vertex_normals
    from native_glb_delivery import validate_glb_delivery
    from native_gltf import validate_gltf
    from native_modeling import make_chamfered_box, make_cylinder
    from native_pbr import PaintedMetalSpec, write_painted_metal
    return SimpleNamespace(**locals())


def _box(api: SimpleNamespace, name: str, size: tuple[float, float, float], at: tuple[float, float, float], chamfer: float = 0.02):
    mesh = api.make_chamfered_box(size[0], size[1], size[2], min(chamfer, min(size) * 0.24), name=name)
    from native_geometry import translate
    return translate(mesh, at, name=name)


def _mesh_part(parts: list[Part], part_id: str, mesh: Any, material: str, role: str) -> None:
    if material not in MATERIALS:
        raise TrialError(f"unknown material family: {material}")
    parts.append(Part(part_id, mesh, material, role))


def _relay(api: SimpleNamespace, *, online: bool) -> Asset:
    state = "online" if online else "offline"
    glow = "teal_glow" if online else "red_glow"
    parts: list[Part] = []
    _mesh_part(parts, "base_plinth", _box(api, "base_plinth", (1.24, 0.16, 1.24), (0, 0.08, 0), 0.08), "dark_metal", "grounded base")
    _mesh_part(parts, "base_step", _box(api, "base_step", (1.02, 0.14, 1.02), (0, 0.21, 0), 0.05), "light_metal", "service plinth")
    for index, y in enumerate((0.34, 0.54, 2.46, 2.68)):
        _mesh_part(parts, f"structural_ring_{index}", api.torus_ring((0, y, 0), radius=0.44 if index in (0, 3) else 0.39, tube=0.065, axis="y", major_segments=24, minor_segments=6, name=f"ring_{index}"), "dark_metal", "structural ring")
    for index, y in enumerate((0.63, 2.38)):
        _mesh_part(parts, f"state_ring_{index}", api.torus_ring((0, y, 0), radius=0.405, tube=0.035, axis="y", major_segments=24, minor_segments=5, name=f"state_ring_{index}"), glow, "readable state ring")
    core = api.lathe_profile([(0.0, 0.46), (0.235, 0.46), (0.235, 2.53), (0.0, 2.53)], axis="y", segments=24, name="energy_column")
    _mesh_part(parts, "energy_column", core, glow, "central charge column")
    for index, angle in enumerate((45, 135, 225, 315)):
        rad = math.radians(angle)
        x, z = math.cos(rad) * 0.36, math.sin(rad) * 0.36
        _mesh_part(parts, f"outer_strut_{index}", api.beam_segment((x, 0.50, z), (x, 2.56, z), width=0.075, depth=0.075, name=f"strut_{index}"), "light_metal", "protective strut")
    for index, (x, z) in enumerate(((0.27, 0), (-0.27, 0), (0, 0.27), (0, -0.27))):
        _mesh_part(parts, f"state_bar_{index}", api.beam_segment((x, 0.58, z), (x, 2.42, z), width=0.032, depth=0.026, name=f"state_bar_{index}"), glow, "vertical state light")
    top = api.lathe_profile([(0.0, 2.67), (0.37, 2.67), (0.37, 2.81), (0.25, 2.81), (0.25, 2.94), (0.0, 3.0)], axis="y", segments=24, name="relay_cap")
    _mesh_part(parts, "relay_cap", top, "dark_metal", "service cap")
    _mesh_part(parts, "cap_state", api.torus_ring((0, 2.82, 0), radius=0.27, tube=0.035, axis="y", major_segments=20, minor_segments=5, name="cap_state"), glow, "top state beacon")
    for index, (x, z) in enumerate(((-0.49, -0.49), (0.49, -0.49), (-0.49, 0.49), (0.49, 0.49))):
        _mesh_part(parts, f"foot_{index}", _box(api, f"foot_{index}", (0.24, 0.10, 0.24), (x, 0.05, z), 0.035), "dark_metal", "mounting foot")
    collision = api.lathe_profile([(0.0, 0.0), (0.62, 0.0), (0.62, 0.34), (0.48, 0.34), (0.48, 3.0), (0.0, 3.0)], axis="y", segments=12, name=f"relay_{state}_collision")
    return Asset(f"relay_{state}", f"Relay ({state})", tuple(parts), collision, 5000, "approximately 1.24 m diameter × 3.0 m high")


def _relay_base(api: SimpleNamespace) -> Asset:
    parts: list[Part] = []
    _mesh_part(parts, "base", _box(api, "base", (1.45, 0.18, 1.45), (0, 0.09, 0), 0.08), "dark_metal", "modular footprint")
    _mesh_part(parts, "inset", _box(api, "inset", (1.04, 0.08, 1.04), (0, 0.22, 0), 0.04), "light_metal", "relay mounting plate")
    _mesh_part(parts, "socket", api.torus_ring((0, 0.29, 0), radius=0.36, tube=0.055, axis="y", major_segments=20, minor_segments=5, name="socket"), "black_rubber", "relay socket")
    for index, (x, z) in enumerate(((-0.57, -0.57), (0.57, -0.57), (-0.57, 0.57), (0.57, 0.57))):
        _mesh_part(parts, f"corner_lock_{index}", _box(api, f"corner_lock_{index}", (0.20, 0.08, 0.20), (x, 0.20, z), 0.03), "amber_trim", "corner lock")
    collision = _box(api, "relay_base_collision", (1.45, 0.28, 1.45), (0, 0.14, 0), 0.03)
    return Asset("relay_base", "Relay Base (modular)", tuple(parts), collision, 1000, "1.45 m square modular base")


def _conduit(api: SimpleNamespace, *, online: bool) -> Asset:
    state = "online" if online else "offline"
    glow = "teal_glow" if online else "black_rubber"
    asset_id = "conduit_segment" if online else "conduit_segment_off"
    parts: list[Part] = []
    _mesh_part(parts, "housing", _box(api, "housing", (2.0, 0.16, 0.34), (0, 0.08, 0), 0.045), "dark_metal", "floor conduit housing")
    for index, z in enumerate((-0.09, 0.0, 0.09)):
        _mesh_part(parts, f"energy_line_{index}", api.pipe_path(((-0.88, 0.18, z), (0.88, 0.18, z)), radius=0.028 if index != 1 else 0.036, sides=8, name=f"energy_line_{index}"), glow, "charge channel")
    for index, x in enumerate((-0.91, 0.91)):
        _mesh_part(parts, f"coupler_{index}", _box(api, f"coupler_{index}", (0.16, 0.25, 0.42), (x, 0.125, 0), 0.035), "light_metal", "modular connector")
    _mesh_part(parts, "amber_key", _box(api, "amber_key", (0.08, 0.025, 0.42), (0.60, 0.205, 0), 0.006), "amber_trim", "orientation key")
    collision = _box(api, f"{asset_id}_collision", (2.0, 0.23, 0.42), (0, 0.115, 0), 0.02)
    return Asset(asset_id, f"Conduit Segment ({state})", tuple(parts), collision, 1000, "2.0 m long modular state variant", canonical=online)


def _floor_panel(api: SimpleNamespace) -> Asset:
    parts: list[Part] = []
    _mesh_part(parts, "slab", _box(api, "slab", (1.0, 0.08, 1.0), (0, 0.04, 0), 0.025), "dark_metal", "load-bearing tile proxy")
    _mesh_part(parts, "inset", _box(api, "inset", (0.78, 0.035, 0.78), (0, 0.097, 0), 0.015), "light_metal", "non-slip inset")
    for index, x in enumerate((-0.30, -0.15, 0.0, 0.15, 0.30)):
        _mesh_part(parts, f"grate_x_{index}", _box(api, f"grate_x_{index}", (0.025, 0.018, 0.70), (x, 0.124, 0), 0.003), "black_rubber", "grate rib")
    for index, z in enumerate((-0.30, -0.15, 0.0, 0.15, 0.30)):
        _mesh_part(parts, f"grate_z_{index}", _box(api, f"grate_z_{index}", (0.70, 0.018, 0.025), (0, 0.124, z), 0.003), "black_rubber", "grate rib")
    collision = _box(api, "floor_panel_1m_collision", (1.0, 0.10, 1.0), (0, 0.05, 0), 0.01)
    return Asset("floor_panel_1m", "Floor Panel (1 m × 1 m)", tuple(parts), collision, 1000, "1.0 m × 1.0 m grid tile")


def _wall_panel(api: SimpleNamespace) -> Asset:
    parts: list[Part] = []
    _mesh_part(parts, "wall_body", _box(api, "wall_body", (2.0, 2.0, 0.14), (0, 1.0, 0), 0.04), "dark_metal", "modular wall body")
    _mesh_part(parts, "wall_inset", _box(api, "wall_inset", (1.72, 1.62, 0.05), (0, 1.0, 0.095), 0.025), "light_metal", "service panel")
    for index, x in enumerate((-0.70, -0.35, 0.0, 0.35, 0.70)):
        _mesh_part(parts, f"vertical_rib_{index}", _box(api, f"vertical_rib_{index}", (0.055, 1.60, 0.055), (x, 1.0, 0.145), 0.008), "dark_metal", "panel rib")
    for index, y in enumerate((0.16, 1.84)):
        _mesh_part(parts, f"edge_rail_{index}", _box(api, f"edge_rail_{index}", (1.86, 0.10, 0.07), (0, y, 0.145), 0.012), "black_rubber", "edge rail")
    for index, (x, y) in enumerate(((-0.82, 0.18), (0.82, 0.18), (-0.82, 1.82), (0.82, 1.82))):
        bolt = api.make_cylinder(0.032, 0.04, segments=10, name=f"bolt_{index}")
        from native_geometry import translate
        _mesh_part(parts, f"bolt_{index}", translate(bolt, (x, y, 0.17), name=f"bolt_{index}"), "amber_trim", "service fastener")
    collision = _box(api, "wall_panel_2m_collision", (2.0, 2.0, 0.18), (0, 1.0, 0), 0.01)
    return Asset("wall_panel_2m", "Wall Panel (2 m × 2 m)", tuple(parts), collision, 1000, "2.0 m × 2.0 m modular wall")


def _door(api: SimpleNamespace) -> Asset:
    parts: list[Part] = []
    _mesh_part(parts, "door_leaf", _box(api, "door_leaf", (1.30, 2.10, 0.16), (0, 1.05, 0), 0.07), "dark_metal", "closed collision leaf")
    _mesh_part(parts, "inner_panel", _box(api, "inner_panel", (0.92, 1.50, 0.055), (0, 1.02, 0.105), 0.08), "light_metal", "door inset")
    for side, x in (("left", -0.73), ("right", 0.73)):
        _mesh_part(parts, f"frame_{side}", _box(api, f"frame_{side}", (0.18, 2.20, 0.28), (x, 1.10, 0), 0.035), "black_rubber", "door frame")
    _mesh_part(parts, "frame_top", _box(api, "frame_top", (1.64, 0.18, 0.28), (0, 2.11, 0), 0.035), "black_rubber", "door frame")
    _mesh_part(parts, "state_light", _box(api, "state_light", (0.52, 0.07, 0.035), (0, 1.86, 0.16), 0.012), "teal_glow", "door state light")
    _mesh_part(parts, "warning_bar", _box(api, "warning_bar", (0.56, 0.08, 0.035), (0, 0.48, 0.16), 0.012), "amber_trim", "maintenance warning")
    for index, y in enumerate((0.72, 1.30)):
        _mesh_part(parts, f"lock_bar_{index}", _box(api, f"lock_bar_{index}", (0.72, 0.055, 0.04), (0, y, 0.155), 0.009), "dark_metal", "locking rib")
    collision = _box(api, "door_closed_collision", (1.48, 2.20, 0.28), (0, 1.10, 0), 0.015)
    return Asset("door_closed", "Door (closed)", tuple(parts), collision, 5000, "1.48 m wide × 2.20 m high closed door")


def _platform(api: SimpleNamespace) -> Asset:
    parts: list[Part] = []
    _mesh_part(parts, "deck", _box(api, "deck", (2.0, 0.16, 2.0), (0, 0.08, 0), 0.05), "dark_metal", "2 m modular deck")
    for index, (x, z) in enumerate(((-0.47, -0.47), (0.47, -0.47), (-0.47, 0.47), (0.47, 0.47))):
        _mesh_part(parts, f"deck_panel_{index}", _box(api, f"deck_panel_{index}", (0.86, 0.035, 0.86), (x, 0.18, z), 0.025), "light_metal", "non-slip deck panel")
    posts = [(-0.92, -0.92), (0, -0.92), (0.92, -0.92), (-0.92, 0), (0.92, 0), (-0.92, 0.92), (0.92, 0.92)]
    for index, (x, z) in enumerate(posts):
        _mesh_part(parts, f"rail_post_{index}", api.beam_segment((x, 0.18, z), (x, 0.92, z), width=0.055, depth=0.055, name=f"rail_post_{index}"), "amber_trim", "safety rail post")
    rails = [((-0.92, 0.88, -0.92), (0.92, 0.88, -0.92)), ((-0.92, 0.88, -0.92), (-0.92, 0.88, 0.92)), ((0.92, 0.88, -0.92), (0.92, 0.88, 0.92))]
    for index, (start, end) in enumerate(rails):
        _mesh_part(parts, f"top_rail_{index}", api.beam_segment(start, end, width=0.065, depth=0.065, name=f"top_rail_{index}"), "amber_trim", "top safety rail")
    collision = _box(api, "platform_2m_collision", (2.0, 0.20, 2.0), (0, 0.10, 0), 0.02)
    return Asset("platform_2m", "Platform with railings (2 m × 2 m)", tuple(parts), collision, 1000, "2.0 m × 2.0 m footprint; three-sided rail")


def _wedge(api: SimpleNamespace, name: str, *, width: float = 2.0, length: float = 2.0, low: float = 0.06, high: float = 0.66):
    x, z = width * 0.5, length * 0.5
    vertices = [(-x, 0, -z), (x, 0, -z), (x, 0, z), (-x, 0, z), (-x, high, -z), (x, high, -z), (x, low, z), (-x, low, z)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
    return api.Mesh(name, vertices, faces)


def _ramp(api: SimpleNamespace) -> Asset:
    parts: list[Part] = []
    _mesh_part(parts, "ramp_body", _wedge(api, "ramp_body"), "dark_metal", "2 m modular ramp")
    for index, z in enumerate((-0.78, -0.52, -0.26, 0.0, 0.26, 0.52, 0.78)):
        y = 0.06 + (0.66 - 0.06) * ((1.0 - z) / 2.0) + 0.025
        _mesh_part(parts, f"grip_bar_{index}", api.beam_segment((-0.86, y, z), (0.86, y, z), width=0.035, depth=0.035, name=f"grip_bar_{index}"), "light_metal", "ramp grip bar")
    for side, x in (("left", -0.92), ("right", 0.92)):
        for index, z in enumerate((-0.92, 0.0, 0.92)):
            surface = 0.06 + (0.66 - 0.06) * ((1.0 - z) / 2.0)
            _mesh_part(parts, f"{side}_post_{index}", api.beam_segment((x, surface, z), (x, surface + 0.68, z), width=0.052, depth=0.052, name=f"{side}_post_{index}"), "amber_trim", "ramp rail post")
        _mesh_part(parts, f"{side}_rail", api.beam_segment((x, 1.02, -0.92), (x, 0.74, 0.92), width=0.065, depth=0.065, name=f"{side}_rail"), "amber_trim", "ramp safety rail")
    collision = _wedge(api, "ramp_2m_collision")
    return Asset("ramp_2m", "Ramp (2 m × 2 m footprint)", tuple(parts), collision, 1000, "2.0 m × 2.0 m footprint; 0.66 m rise")


def build_assets(api: SimpleNamespace) -> list[Asset]:
    assets = [
        _relay(api, online=True), _relay(api, online=False), _relay_base(api),
        _conduit(api, online=True), _conduit(api, online=False), _floor_panel(api),
        _wall_panel(api), _door(api), _platform(api), _ramp(api),
    ]
    canonical = tuple(asset.asset_id for asset in assets if asset.canonical)
    if canonical != CANONICAL_ASSETS:
        raise TrialError("constructed asset set drifted from the bound reference contract")
    return assets


def _group_parts(api: SimpleNamespace, parts: Iterable[Part]) -> dict[str, Any]:
    groups: dict[str, list[Any]] = {}
    for part in parts:
        groups.setdefault(part.material, []).append(part.mesh)
    return {material: api.combine(meshes, name=f"material_{material}") for material, meshes in groups.items()}


def _pack_floats(values: Iterable[Iterable[float]]) -> bytes:
    flat = [float(value) for row in values for value in row]
    return struct.pack("<" + "f" * len(flat), *flat)


def _pad4(data: bytes, byte: bytes) -> bytes:
    return data if len(data) % 4 == 0 else data + byte * (4 - len(data) % 4)


def _compile_glb(api: SimpleNamespace, asset_id: str, groups: dict[str, Any], materials_root: Path, *, reference_sha256: str, collision: bool = False) -> tuple[bytes, dict[str, Any]]:
    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []

    def add_view(payload: bytes, target: int | None = None) -> int:
        while len(blob) % 4:
            blob.append(0)
        offset = len(blob)
        blob.extend(payload)
        view: dict[str, Any] = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        views.append(view)
        return len(views) - 1

    def add_accessor(payload: bytes, count: int, kind: str, component: int, *, target: int, mins=None, maxs=None) -> int:
        item: dict[str, Any] = {"bufferView": add_view(payload, target), "componentType": component, "count": count, "type": kind}
        if mins is not None:
            item["min"] = list(mins)
            item["max"] = list(maxs)
        accessors.append(item)
        return len(accessors) - 1

    material_names = list(groups)
    primitives = []
    triangle_total = 0
    for material_index, material_name in enumerate(material_names):
        mesh = groups[material_name]
        tri = api.triangulate(mesh)
        normals = api.vertex_normals(mesh)
        lo, hi = api.bounds(mesh)
        spans = [hi[i] - lo[i] for i in range(3)]
        axes = sorted(range(3), key=lambda i: spans[i], reverse=True)[:2]
        uv = [((vertex[axes[0]] - lo[axes[0]]) / max(spans[axes[0]], 1e-9), (vertex[axes[1]] - lo[axes[1]]) / max(spans[axes[1]], 1e-9)) for vertex in mesh.vertices]
        indices = [index for face in tri.faces for index in face]
        pos_acc = add_accessor(_pack_floats(mesh.vertices), len(mesh.vertices), "VEC3", 5126, target=34962, mins=lo, maxs=hi)
        normal_acc = add_accessor(_pack_floats(normals), len(normals), "VEC3", 5126, target=34962)
        uv_acc = add_accessor(_pack_floats(uv), len(uv), "VEC2", 5126, target=34962)
        index_acc = add_accessor(struct.pack("<" + "I" * len(indices), *indices), len(indices), "SCALAR", 5125, target=34963, mins=[min(indices)], maxs=[max(indices)])
        primitives.append({"attributes": {"POSITION": pos_acc, "NORMAL": normal_acc, "TEXCOORD_0": uv_acc}, "indices": index_acc, "material": material_index, "mode": 4})
        triangle_total += len(indices) // 3

    images: list[dict[str, Any]] = []
    textures: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    for material_name in material_names:
        texture_indices = {}
        for channel in ("base_color", "orm", "normal"):
            data = (materials_root / material_name / f"{channel}.png").read_bytes()
            view = add_view(data)
            images.append({"name": f"{material_name}_{channel}", "bufferView": view, "mimeType": "image/png"})
            textures.append({"sampler": 0, "source": len(images) - 1})
            texture_indices[channel] = len(textures) - 1
        state = MATERIALS[material_name]
        material: dict[str, Any] = {
            "name": material_name,
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": texture_indices["base_color"]},
                "metallicRoughnessTexture": {"index": texture_indices["orm"]},
                "metallicFactor": state["metallic"],
                "roughnessFactor": state["roughness"],
            },
            "normalTexture": {"index": texture_indices["normal"], "scale": 0.62},
            "occlusionTexture": {"index": texture_indices["orm"]},
        }
        if any(state["emissive"]):
            material["emissiveTexture"] = {"index": texture_indices["base_color"]}
            material["emissiveFactor"] = list(state["emissive"])
        materials.append(material)

    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "AXM Monolith Blackline Reference Kit v0.1"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": asset_id, "mesh": 0}],
        "meshes": [{"name": asset_id, "primitives": primitives}],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": images,
        "textures": textures,
        "materials": materials,
        "extras": {"axm": {
            "schema": SCHEMA,
            "asset_id": asset_id,
            "units": "meters",
            "origin": "base_center",
            "reference_sha256": reference_sha256,
            "triangle_count": triangle_total,
            "collision_proxy": collision,
            "truth": "Original deterministic prototype geometry; visual fit and engine performance require downstream review.",
        }},
    }
    document["buffers"][0]["byteLength"] = len(blob)
    gltf_validation = api.validate_gltf(document, bytes(blob))
    if gltf_validation["status"] != "pass":
        raise TrialError(f"internal glTF validation failed for {asset_id}: {gltf_validation}")
    json_bytes = _pad4(json.dumps(document, sort_keys=True, separators=(",", ":")).encode(), b" ")
    binary = _pad4(bytes(blob), b"\x00")
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    glb = b"".join((
        struct.pack("<4sII", b"glTF", 2, total),
        struct.pack("<II", len(json_bytes), 0x4E4F534A), json_bytes,
        struct.pack("<II", len(binary), 0x004E4942), binary,
    ))
    delivery_validation = api.validate_glb_delivery(glb)
    return glb, {"gltf": gltf_validation, "glb": delivery_validation, "triangles": triangle_total, "materials": material_names}


def _write_obj_mtl(api: SimpleNamespace, asset: Asset, root: Path) -> dict[str, Any]:
    obj_path = root / f"{asset.asset_id}.obj"
    mtl_path = root / f"{asset.asset_id}.mtl"
    root.mkdir(parents=True, exist_ok=True)
    mtl_lines = []
    for name in sorted({part.material for part in asset.parts}):
        state = MATERIALS[name]
        rgb = [value / 255 for value in state["rgb"]]
        mtl_lines.extend((f"newmtl {name}", f"Kd {rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}", f"Ke {state['emissive'][0]:.6f} {state['emissive'][1]:.6f} {state['emissive'][2]:.6f}", f"Pm {state['metallic']:.6f}", f"Pr {state['roughness']:.6f}", ""))
    mtl_path.write_text("\n".join(mtl_lines), encoding="utf-8")
    lines = [f"mtllib {mtl_path.name}", f"o {asset.asset_id}"]
    offset = 0
    for part in asset.parts:
        lines.extend((f"g {part.part_id}", f"usemtl {part.material}"))
        lines.extend(f"v {x:.7f} {y:.7f} {z:.7f}" for x, y, z in part.mesh.vertices)
        for face in part.mesh.faces:
            lines.append("f " + " ".join(str(index + 1 + offset) for index in face))
        offset += len(part.mesh.vertices)
    obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"obj": obj_path.name, "obj_sha256": _sha256_file(obj_path), "mtl": mtl_path.name, "mtl_sha256": _sha256_file(mtl_path)}


def _render_preview(api: SimpleNamespace, asset: Asset, output: Path, view: str, *, size: int = 512) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFilter
    groups = _group_parts(api, asset.parts)
    faces = []
    projected_all = []

    def project(v):
        x, y, z = v
        if view == "front":
            return x, y, z
        if view == "side":
            return z, y, -x
        if view == "top":
            return x, -z, y
        return (x - z) * 0.7071, y * 0.86 - (x + z) * 0.29, (x + z) * 0.7071 + y * 0.18

    for material, mesh in groups.items():
        for face in api.triangulate(mesh).faces:
            points = [project(mesh.vertices[index]) for index in face]
            projected_all.extend(points)
            normal = api.face_normal(mesh, face)
            light = max(0.18, min(1.0, 0.33 + 0.67 * max(0.0, normal[0] * -0.35 + normal[1] * 0.78 + normal[2] * 0.52)))
            faces.append((sum(point[2] for point in points) / 3, points, material, light))
    if not projected_all:
        raise TrialError(f"empty preview geometry: {asset.asset_id}")
    min_x = min(p[0] for p in projected_all); max_x = max(p[0] for p in projected_all)
    min_y = min(p[1] for p in projected_all); max_y = max(p[1] for p in projected_all)
    span_x = max(max_x - min_x, 1e-6); span_y = max(max_y - min_y, 1e-6)
    margin = size * 0.09
    scale = min((size - 2 * margin) / span_x, (size - 2 * margin) / span_y)
    center_x = (min_x + max_x) * 0.5; center_y = (min_y + max_y) * 0.5

    def screen(points):
        return [(size * 0.5 + (p[0] - center_x) * scale, size * 0.52 - (p[1] - center_y) * scale) for p in points]

    image = Image.new("RGB", (size, size), (4, 11, 14))
    draw = ImageDraw.Draw(image)
    for radius, color in ((size * 0.46, (8, 25, 29)), (size * 0.32, (10, 33, 37))):
        draw.ellipse((size/2-radius, size/2-radius, size/2+radius, size/2+radius), fill=color)
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0)); glow_draw = ImageDraw.Draw(glow_layer)
    for _, points, material, _light in sorted(faces, key=lambda row: row[0]):
        if any(MATERIALS[material]["emissive"]):
            rgb = MATERIALS[material]["rgb"]
            glow_draw.polygon(screen(points), fill=(*rgb, 155))
    image = Image.alpha_composite(image.convert("RGBA"), glow_layer.filter(ImageFilter.GaussianBlur(13)))
    draw = ImageDraw.Draw(image)
    for _, points, material, light in sorted(faces, key=lambda row: row[0]):
        rgb = MATERIALS[material]["rgb"]
        if any(MATERIALS[material]["emissive"]):
            color = tuple(min(255, int(value * (0.88 + light * 0.32))) for value in rgb)
        else:
            color = tuple(max(2, int(value * light)) for value in rgb)
        draw.polygon(screen(points), fill=(*color, 255), outline=(8, 17, 20, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, "PNG", optimize=True)
    return {"path": output.name, "sha256": _sha256_file(output), "view": view, "size": [size, size]}


def _contact_sheet(previews: list[tuple[str, Path]], output: Path) -> None:
    from PIL import Image, ImageDraw
    thumb = 330; label_h = 48; columns = 5; rows = math.ceil(len(previews) / columns)
    sheet = Image.new("RGB", (columns * thumb, rows * (thumb + label_h)), (3, 10, 13))
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(previews):
        image = Image.open(path).convert("RGB").resize((thumb, thumb))
        x = (index % columns) * thumb; y = (index // columns) * (thumb + label_h)
        sheet.paste(image, (x, y))
        draw.text((x + 12, y + thumb + 13), label, fill=(220, 238, 239))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)


def _gallery(assets: list[Asset]) -> str:
    cards = []
    for asset in assets:
        cards.append(f'''<article><h2>{asset.label}</h2><img src="assets/{asset.asset_id}/previews/isometric.png" alt="{asset.label} isometric software preview"><p>{asset.dimensions_note}</p><p><a href="assets/{asset.asset_id}/delivery/{asset.asset_id}.glb">3D GLB</a> · <a href="assets/{asset.asset_id}/source/{asset.asset_id}.obj">OBJ source</a> · <a href="assets/{asset.asset_id}/collision/{asset.asset_id}_collision.glb">collision GLB</a> · <a href="assets/{asset.asset_id}/asset_receipt.json">receipt</a></p></article>''')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Blackline Relay 3D Kit</title><style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#030a0d;color:#e6f1f2;font:16px/1.5 system-ui,sans-serif}main{width:min(1400px,calc(100% - 30px));margin:auto;padding:30px 0 60px}h1{letter-spacing:.08em;color:#5ff7e5}header{border-bottom:1px solid #27444c;margin-bottom:20px}.truth{max-width:80ch;color:#9fb5ba}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}article{background:#08171b;border:1px solid #27444c;border-radius:14px;padding:14px}article img{width:100%;display:block;background:#020607;border-radius:9px}h2{font-size:1.05rem;color:#ffc866}a{color:#65f6e5}.sheet{width:100%;margin:20px 0;border:1px solid #27444c}</style></head><body><main><header><p>AXM Ghost Studio</p><h1>BLACKLINE RELAY — MODULAR 3D KIT</h1><p class="truth">Original deterministic prototype geometry built through the installed AXM monolith from the supplied reference sheet. GLB structure, scale, triangle budgets, texture embedding, collision deliveries, and file hashes are verified. Art-direction fit, engine performance, gameplay collision fit, and studio adoption remain review decisions.</p></header><img class="sheet" src="CONTACT_SHEET.png" alt="isometric contact sheet"><div class="grid">''' + "".join(cards) + '''</div><p><a href="KIT_RECEIPT.json">Exact build receipt</a> · <a href="KIT_SPEC.json">Bound reference specification</a></p></main></body></html>'''


def run(build: str | Path, reference: str | Path, output: str | Path, *, seed: int = SEED) -> dict[str, Any]:
    snapshot = load_snapshot(build)
    reference_state = validate_reference(reference)
    destination = Path(output).resolve()
    if destination.exists():
        raise TrialError("output must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        api = _native_api(snapshot)
        from axm_uc.visual_creation_grammar import compile_visual_recipe
        from PIL import __version__ as pillow_version

        contract = reference_contract()
        recipe = compile_visual_recipe({
            "subject": "Blackline Relay modular industrial sci-fi maintenance environment kit",
            "seed": seed,
            "aliases": ["3drender", "isometricview", "retrofuturistic", "texturefocus"],
            "style": ["minimalist", "moody", "retrofuturistic", "texture-focus"],
            "environment": ["custom-scene"],
            "criteria": contract["art_direction"],
            "constraints": ["real-world meter scale", "modular reuse", "base-centered origins", "separate collision deliveries", "original local/offline output"],
            "avoid": ["photoreal clutter", "protected visual identity", "false final-art claim", "silent Ghost Studio installation"],
            "technical_requirements": contract["delivery"],
        })
        _write_json(stage / "KIT_SPEC.json", {"schema": SCHEMA, "reference": {key: value for key, value in reference_state.items() if key != "source"}, "contract": contract, "visual_recipe": recipe})
        reference_target = stage / "reference" / reference_state["stored_name"]
        reference_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reference_state["source"], reference_target)

        material_receipts = {}
        for index, (name, state) in enumerate(MATERIALS.items()):
            material_receipts[name] = api.write_painted_metal(
                stage / "materials" / name,
                size=128,
                seed=seed + index * 103,
                spec=api.PaintedMetalSpec(
                    paint_rgb=state["rgb"], metal_rgb=state["metal_rgb"],
                    paint_roughness=state["roughness"], metal_roughness=max(0.12, state["roughness"] - 0.08),
                    wear=state["wear"], scratches=state["scratches"], grain_scale=34.0,
                    height_grain_amplitude=0.035, height_broad_amplitude=0.018,
                    height_scratch_depth=0.055, height_pit_depth=0.035,
                    pit_wear_strength=0.18, base_grain_variation=0.07,
                    roughness_grain_variation=0.045, normal_strength=1.8,
                ),
            )

        assets = build_assets(api)
        asset_receipts = {}
        contact_previews = []
        for asset in assets:
            asset_root = stage / "assets" / asset.asset_id
            groups = _group_parts(api, asset.parts)
            combined = api.combine((part.mesh for part in asset.parts), name=asset.asset_id)
            topology = api.topology_report(combined)
            source = _write_obj_mtl(api, asset, asset_root / "source")
            glb, validation = _compile_glb(api, asset.asset_id, groups, stage / "materials", reference_sha256=reference_state["sha256"])
            if validation["triangles"] >= asset.budget:
                raise TrialError(f"{asset.asset_id} exceeds reference triangle budget")
            delivery = asset_root / "delivery" / f"{asset.asset_id}.glb"
            delivery.parent.mkdir(parents=True, exist_ok=True)
            delivery.write_bytes(glb)
            delivery_receipt = {
                "schema": "axm.game-assets.verified-glb-delivery/v0.1",
                "status": "READY_FOR_EXPLICIT_CONSUMER_LOAD",
                "source": {
                    "package_schema": "axm.ghost-studio.reference-asset/v0.1",
                    "manifest_sha256": source["obj_sha256"],
                },
                "asset": {"name": asset.asset_id},
                "consumer_request": None,
                "delivery": {
                    "format": "glb",
                    "sha256": _sha256_file(delivery),
                    "bytes": len(glb),
                    "self_contained": True,
                    "validation": validation["glb"],
                },
                "authority": {
                    "canonical_genome_mutation": False,
                    "source_package_mutation": False,
                    "automatic_consumer_install": False,
                    "automatic_runtime_adoption": False,
                    "visual_approval": False,
                    "merge": False,
                    "canon": False,
                },
                "truth": {
                    "rigid_snapshot_only": True,
                    "skeleton_or_animation_claim": False,
                    "reference_match_requires_visual_review": True,
                },
            }
            _write_json(delivery.parent / "delivery-receipt.json", delivery_receipt)

            collision_groups = {"dark_metal": asset.collision}
            collision_glb, collision_validation = _compile_glb(api, f"{asset.asset_id}_collision", collision_groups, stage / "materials", reference_sha256=reference_state["sha256"], collision=True)
            collision_path = asset_root / "collision" / f"{asset.asset_id}_collision.glb"
            collision_path.parent.mkdir(parents=True, exist_ok=True)
            collision_path.write_bytes(collision_glb)
            collision_bounds = api.bounds(asset.collision)
            _write_json(asset_root / "collision" / "collision.json", {"schema": "axm.game-assets.simple-collision/v0.1", "asset_id": asset.asset_id, "kind": "authored simple mesh", "bounds_m": collision_bounds, "triangles": collision_validation["triangles"], "glb": collision_path.name, "glb_sha256": _sha256_file(collision_path), "gameplay_fit_proven": False})

            previews = []
            for view in ("isometric", "front", "side", "top"):
                preview_path = asset_root / "previews" / f"{view}.png"
                previews.append(_render_preview(api, asset, preview_path, view))
            contact_previews.append((asset.label, asset_root / "previews" / "isometric.png"))
            bounds = api.bounds(combined)
            receipt = {
                "schema": "axm.ghost-studio.reference-asset/v0.1",
                "asset_id": asset.asset_id,
                "label": asset.label,
                "canonical_reference_asset": asset.canonical,
                "dimensions_note": asset.dimensions_note,
                "units": "meters",
                "origin": "base_center",
                "bounds_m": bounds,
                "parts": [{"part_id": part.part_id, "material": part.material, "role": part.role} for part in asset.parts],
                "source": source,
                "topology": topology,
                "delivery": {"path": f"delivery/{asset.asset_id}.glb", "sha256": _sha256_file(delivery), "bytes": len(glb), **validation},
                "collision": {"path": f"collision/{asset.asset_id}_collision.glb", "sha256": _sha256_file(collision_path), "bytes": len(collision_glb), **collision_validation},
                "previews": previews,
                "truth": {"structurally_verified": True, "engine_loaded": False, "visual_fit_approved": False, "gameplay_collision_fit_proven": False, "final_art": False},
            }
            _write_json(asset_root / "asset_receipt.json", receipt)
            asset_receipts[asset.asset_id] = receipt

        _contact_sheet(contact_previews, stage / "CONTACT_SHEET.png")
        (stage / "OPEN_KIT.html").write_text(_gallery(assets), encoding="utf-8")
        files = [{"path": path.relative_to(stage).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256_file(path)} for path in sorted(stage.rglob("*")) if path.is_file() and path.name != "KIT_RECEIPT.json"]
        receipt = {
            "schema": SCHEMA,
            "status": "EXECUTED_AND_STRUCTURALLY_VERIFIED",
            "reference": {key: value for key, value in reference_state.items() if key != "source"},
            "snapshot": {"lock_sha256": snapshot["lock_sha256"], "module_count": len(snapshot["lock"]["modules"]), "required_modules": snapshot["module_records"]},
            "execution": {"canonical_asset_count": len(CANONICAL_ASSETS), "delivery_count": len(assets), "state_variant_count": 1, "generated_file_count_excluding_receipt": len(files), "assets": asset_receipts, "materials": material_receipts, "files": files},
            "tools": {"geometry_material_glb": "AXM Game Asset Forge native modules", "visual_recipe": "AXM Universal Creation", "preview_rasterizer": {"name": "Pillow", "version": pillow_version, "classification": "compatible open component; preview only", "license": "HPND"}},
            "source_mutation": "none",
            "truth": {"reference_bound": True, "geometry_executed": True, "self_contained_glbs_validated": True, "triangle_budgets_passed": True, "collision_deliveries_present": True, "pbr_maps_generated": True, "engine_import_or_performance_proven": False, "visual_match_approved": False, "ghost_studio_gameplay_composition_retested": False, "automatic_ghost_studio_installation": False, "canon": False},
            "authority": {"consumer_install": False, "studio_adoption": False, "merge": False, "canon": False},
        }
        receipt = _portable_receipt_paths(receipt, stage)
        _write_json(stage / "KIT_RECEIPT.json", receipt)
        os.replace(stage, destination)
        return receipt
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the supplied Blackline Relay reference sheet as a modular 3D kit")
    parser.add_argument("--build", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--confirm-create", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_create:
        parser.error("--confirm-create is required")
    try:
        result = run(args.build, args.reference, args.output, seed=args.seed)
    except TrialError as exc:
        raise SystemExit(f"Blackline reference kit rejected: {exc}") from exc
    print(json.dumps({"status": result["status"], "canonical_assets": result["execution"]["canonical_asset_count"], "deliveries": result["execution"]["delivery_count"], "files": result["execution"]["generated_file_count_excluding_receipt"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
