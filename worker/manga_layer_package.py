"""Build reviewable, genuinely layered PSDs for manga AE templates.

This module never tries to infer a character cutout from a flattened scene.
Each named role must arrive as an independently authored, full-canvas PNG.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from psd_tools import PSDImage

try:
    from .manga_lip_sync import MOUTH_ROLES, validate_lip_sync
except ImportError:
    from manga_lip_sync import MOUTH_ROLES, validate_lip_sync


SCHEMA = "manga_layer_packages/v1"
CANVAS_SIZE = (1920, 1080)
ROLE_ORDER = (
    "background", "foreground", "wall_intact", "wall_broken", "character_left",
    "character_center", "character_right", "character", "hand_foreground",
    "talisman", "reflection_scene", "training_prop", "title_backdrop",
    "debris", "qi_overlay", "ink_splat", "speedlines", "lens_glint",
    "light_core", "light_rays", *MOUTH_ROLES,
    "pose_sleeping", "pose_waking", "pose_turning", "pose_resting", "blanket", "shoji",
    "prop_focus", "hair_cloth", "atmosphere", "light_overlay",
)
TEMPLATE_REQUIRED = {
    "parallax_layered_scene": ("background", "character", "foreground"),
    "directed_performance": ("background",),
    "dialogue_closeup": ("background", "character"),
    "angled_triple_reaction": ("background", "character_left", "character_center", "character_right"),
    "body_following_qi": ("background", "character", "talisman"),
    "ink_splat_impact": ("background", "character", "talisman"),
    "wall_impact_debris": ("background", "character", "wall_intact", "wall_broken"),
    "glasses_reflection": ("background", "character", "reflection_scene"),
    "kinetic_title_reveal": ("background", "character"),
    "backlit_hand_reveal": ("background", "hand_foreground"),
}
TEMPLATE_OPTIONAL = {
    "parallax_layered_scene": ("prop_focus", "hair_cloth", "atmosphere", "light_overlay"),
    "directed_performance": ("character", "pose_sleeping", "pose_waking", "pose_turning",
                             "pose_resting", "blanket", "shoji", "prop_focus", "light_core", "light_rays",
                             "debris", "speedlines", "lens_glint", "atmosphere"),
    "dialogue_closeup": (),
    "angled_triple_reaction": ("speedlines",),
    "body_following_qi": ("qi_overlay", "speedlines"),
    "ink_splat_impact": ("ink_splat", "speedlines"),
    "wall_impact_debris": ("debris", "speedlines"),
    "glasses_reflection": ("lens_glint",),
    "kinetic_title_reveal": ("training_prop", "title_backdrop", "speedlines"),
    "backlit_hand_reveal": ("light_core", "light_rays"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scene_number(scene: dict[str, Any], fallback: int) -> int:
    return int(scene.get("scene_number") or scene.get("scene_order") or fallback)


def _roles(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(role, str) or role not in ROLE_ORDER for role in value):
        raise ValueError(f"{label} must contain known layer role names")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate layer roles")
    return value


def scene_spec(scene: dict[str, Any], fallback: int) -> dict[str, Any] | None:
    """Return the strictly validated package spec for a template scene."""
    plan = scene.get("ae_effect_plan") if isinstance(scene.get("ae_effect_plan"), dict) else {}
    template = str(plan.get("template") or "").strip()
    if not plan.get("enabled") or not template:
        layer_plan = scene.get("psd_layer_plan") if isinstance(scene.get("psd_layer_plan"), dict) else {}
        if (layer_plan.get("enabled") and layer_plan.get("selection_source") == "explicit_scene_range"
                and layer_plan.get("template") == "parallax_layered_scene"):
            plan = layer_plan
            template = "parallax_layered_scene"
        else:
            return None
    if template not in TEMPLATE_REQUIRED:
        raise ValueError(f"unknown manga AE template: {template}")
    requirements = plan.get("asset_requirements")
    if template == "parallax_layered_scene" and requirements is None:
        requirements = {
            "required_layers": plan.get("required_layers"),
            "optional_layers": plan.get("optional_layers"),
        }
    if requirements is None:
        requirements = {}
    if not isinstance(requirements, dict):
        raise ValueError("asset_requirements must be an object")
    lip_sync = plan.get("lip_sync")
    enabled_lips = isinstance(lip_sync, dict) and lip_sync.get("enabled") is True
    if lip_sync is not None:
        errors = validate_lip_sync(
            lip_sync, template=template,
            character_key=str((plan.get("character_role_keys") or {}).get("character") or ""),
            duration=float(plan.get("duration_seconds") or scene.get("duration_seconds") or 0),
        )
        if errors:
            raise ValueError("; ".join(errors))
    allowed = set(TEMPLATE_REQUIRED[template]) | set(TEMPLATE_OPTIONAL[template])
    if enabled_lips:
        allowed.update(MOUTH_ROLES)
    declared_required = set(_roles(requirements.get("required_layers"), "required_layers"))
    declared_optional = set(_roles(requirements.get("optional_layers"), "optional_layers"))
    unsupported = (declared_required | declared_optional) - allowed
    if unsupported:
        raise ValueError(f"{template}: unrelated layer roles are not allowed: {sorted(unsupported)}")
    required = set(TEMPLATE_REQUIRED[template]) | declared_required
    if enabled_lips:
        required.update(MOUTH_ROLES)
    optional = (set(TEMPLATE_OPTIONAL[template]) | declared_optional) - required
    number = _scene_number(scene, fallback)
    if number < 1:
        raise ValueError("scene number must be positive")
    return {
        "scene_number": number,
        "template": template,
        "mouth_box": lip_sync["mouth_box"] if enabled_lips else None,
        "required_layers": [role for role in ROLE_ORDER if role in required],
        "optional_layers": [role for role in ROLE_ORDER if role in optional],
        "layer_files": {role: f"scene-{number:03d}-{role.replace('_', '-')}.png"
                        for role in ROLE_ORDER if role in required or role in optional},
    }


def scene_specs(scenes: list[Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            continue
        spec = scene_spec(scene, index)
        if spec:
            if spec["scene_number"] in seen:
                raise ValueError("duplicate template scene number")
            seen.add(spec["scene_number"])
            specs.append(spec)
    return specs


def _validate_png(path: Path, role: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required layer is missing: {path}")
    with Image.open(path) as image:
        if image.format != "PNG" or image.size != CANVAS_SIZE:
            raise ValueError(f"{path.name}: expected a {CANVAS_SIZE[0]}x{CANVAS_SIZE[1]} PNG")
        rgba = image.convert("RGBA")
        alpha_min, alpha_max = rgba.getchannel("A").getextrema()
        if role == "background":
            if alpha_min != 255:
                raise ValueError(f"{path.name}: background must cover the full canvas")
        elif alpha_min == 255 or alpha_max == 0:
            raise ValueError(f"{path.name}: {role} must be a visible transparent cutout")
    return {"role": role, "file": path.name, "sha256": _sha256(path)}


def _inputs(spec: dict[str, Any], images_dir: Path) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        filename = spec["layer_files"].get(role)
        if not filename:
            continue
        path = images_dir / filename
        if role in spec["required_layers"] or path.exists():
            layers.append(_validate_png(path, role))
    if spec.get("mouth_box"):
        left, top, right, bottom = spec["mouth_box"]
        centers = []
        for role in MOUTH_ROLES:
            with Image.open(images_dir / spec["layer_files"][role]) as image:
                bounds = image.convert("RGBA").getchannel("A").getbbox()
            if not bounds:
                raise ValueError(f"{role}: mouth patch is empty")
            x0, y0, x1, y1 = [float(v) for v in bounds]
            width, height = CANVAS_SIZE
            if (x0 / width < left - .01 or x1 / width > right + .01
                    or y0 / height < top - .01 or y1 / height > bottom + .01):
                raise ValueError(f"{role}: mouth patch falls outside the approved mouth_box")
            centers.append(((x0 + x1) / (2 * width), (y0 + y1) / (2 * height)))
        if any(abs(x - centers[0][0]) > .018 or abs(y - centers[0][1]) > .018
               for x, y in centers[1:]):
            raise ValueError("mouth poses do not share the same face registration")
    return layers


def receipt_path(images_dir: Path) -> Path:
    return images_dir / "manga-layer-review.json"


def issues_path(images_dir: Path) -> Path:
    return images_dir / "manga-layer-issues.json"


def _package_paths(images_dir: Path, number: int) -> tuple[Path, Path]:
    folder = images_dir / "layer-packages"
    return folder / f"scene-{number:03d}.psd", folder / f"scene-{number:03d}-preview.png"


def _build_psd(images_dir: Path, layers: list[dict[str, Any]], psd_path: Path, preview_path: Path) -> None:
    psd_path.parent.mkdir(parents=True, exist_ok=True)
    psd = PSDImage.new("RGBA", CANVAS_SIZE, color=0)
    for layer in layers:
        with Image.open(images_dir / layer["file"]) as source:
            psd.create_pixel_layer(source.convert("RGBA"), name=layer["role"])
    tmp = psd_path.with_suffix(".psd.tmp")
    try:
        psd.save(tmp)
        reopened = PSDImage.open(tmp)
        names = [layer.name for layer in reopened]
        if reopened.size != CANVAS_SIZE or names != [layer["role"] for layer in layers]:
            raise RuntimeError(f"PSD layer validation failed for {psd_path.name}: {names}")
        composite = reopened.composite()
        if composite is None:
            raise RuntimeError(f"PSD has no visible composite: {psd_path.name}")
        composite.save(preview_path, format="PNG", optimize=True)
        tmp.replace(psd_path)
    finally:
        tmp.unlink(missing_ok=True)


def prepare(manifest_path: Path, images_dir: Path, specs: list[dict[str, Any]]) -> dict[str, Any]:
    """Create PSDs and a pending human visual-review receipt, without network access.

    Re-running an unchanged package preserves its approval. Changed inputs require
    a new images directory, so previous review and output are never overwritten.
    """
    receipt_file = receipt_path(images_dir)
    manifest_hash = _sha256(manifest_path)
    if receipt_file.exists():
        existing = json.loads(receipt_file.read_text(encoding="utf-8"))
        if existing.get("schema") != SCHEMA or existing.get("manifest_sha256") != manifest_hash:
            raise FileExistsError("layer review belongs to a different manifest; use a new revision directory")
        validate_receipt(manifest_path, images_dir, specs, require_approved=False)
        return existing

    # Validate every template scene before writing any package. In particular, a
    # flattened grid crop or a blurred depth proxy cannot satisfy a character role.
    staged = []
    issues = []
    for spec in specs:
        try:
            staged.append((spec, _inputs(spec, images_dir)))
        except (FileNotFoundError, ValueError) as exc:
            issues.append({"scene_number": spec["scene_number"], "template": spec["template"],
                           "status": "needs_review", "reason": str(exc),
                           "required_layers": spec["required_layers"]})
    if issues:
        images_dir.mkdir(parents=True, exist_ok=True)
        issues_path(images_dir).write_text(
            json.dumps({"schema": SCHEMA, "issues": issues}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError(f"manga layer inputs need review: {issues_path(images_dir)}")
    issues_path(images_dir).unlink(missing_ok=True)
    packages: dict[str, dict[str, Any]] = {}
    for spec, layers in staged:
        number = spec["scene_number"]
        psd_path, preview_path = _package_paths(images_dir, number)
        if psd_path.exists() or preview_path.exists():
            raise FileExistsError(f"untracked layer package already exists: {psd_path}")
        _build_psd(images_dir, layers, psd_path, preview_path)
        packages[str(number)] = {
            "scene_number": number,
            "template": spec["template"],
            "required_layers": spec["required_layers"],
            "layers": layers,
            "psd_file": str(psd_path.relative_to(images_dir)).replace("\\", "/"),
            "psd_sha256": _sha256(psd_path),
            "preview_file": str(preview_path.relative_to(images_dir)).replace("\\", "/"),
            "preview_sha256": _sha256(preview_path),
            "status": "pending_visual_review",
            "review": None,
        }
    receipt = {"schema": SCHEMA, "manifest_sha256": manifest_hash,
               "created_at": datetime.now(timezone.utc).isoformat(), "packages": packages}
    receipt_file.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


def validate_receipt(manifest_path: Path, images_dir: Path, specs: list[dict[str, Any]],
                     *, require_approved: bool) -> dict[str, Any]:
    path = receipt_path(images_dir)
    if not path.is_file():
        raise ValueError("manga layer packages are not prepared; run prepare-layers first")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("schema") != SCHEMA or receipt.get("manifest_sha256") != _sha256(manifest_path):
        raise ValueError("manga layer review does not match the source manifest")
    packages = receipt.get("packages")
    expected = {str(spec["scene_number"]): spec for spec in specs}
    if not isinstance(packages, dict) or set(packages) != set(expected):
        raise ValueError("manga layer review does not cover all template scenes")
    for number, spec in expected.items():
        entry = packages[number]
        if entry.get("template") != spec["template"] or entry.get("required_layers") != spec["required_layers"]:
            raise ValueError(f"scene {number}: layer review plan changed")
        current = _inputs(spec, images_dir)
        if current != entry.get("layers"):
            raise ValueError(f"scene {number}: layer inputs changed after preparation")
        psd_path, preview_path = _package_paths(images_dir, spec["scene_number"])
        if (entry.get("psd_file") != str(psd_path.relative_to(images_dir)).replace("\\", "/") or
                entry.get("preview_file") != str(preview_path.relative_to(images_dir)).replace("\\", "/") or
                _sha256(psd_path) != entry.get("psd_sha256") or
                _sha256(preview_path) != entry.get("preview_sha256")):
            raise ValueError(f"scene {number}: reviewed PSD or preview changed")
        if require_approved and (entry.get("status") != "approved" or not isinstance(entry.get("review"), dict)):
            raise ValueError(f"scene {number}: layer package needs visual review")
    return receipt


def approve(manifest_path: Path, images_dir: Path, specs: list[dict[str, Any]],
            *, reviewer: str, note: str) -> dict[str, Any]:
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer and visual-review note are required")
    receipt = validate_receipt(manifest_path, images_dir, specs, require_approved=False)
    for entry in receipt["packages"].values():
        entry["status"] = "approved"
        entry["review"] = {"reviewer": reviewer.strip(), "note": note.strip(),
                           "reviewed_at": datetime.now(timezone.utc).isoformat()}
    receipt_path(images_dir).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt
