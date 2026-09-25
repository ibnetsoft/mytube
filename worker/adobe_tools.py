"""Adobe desktop app discovery helpers for Windows render workers.

The production render host may have current Creative Cloud apps installed while
older test hosts can still have CS6. Keep discovery data-driven so workers can
move between machines by changing env vars instead of code.
"""
from __future__ import annotations

import os
from pathlib import Path


ADOBE_ROOTS = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Adobe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Adobe",
)


def _version_score(path: Path) -> tuple[int, int, str]:
    text = str(path).lower()
    year = 0
    for token in path.parts:
        if token.isdigit() and len(token) == 4:
            year = max(year, int(token))
        for piece in token.replace("-", " ").replace("_", " ").split():
            if piece.isdigit() and len(piece) == 4:
                year = max(year, int(piece))
    if " beta" in text or "beta" in text:
        beta = 0
    else:
        beta = 1
    # CS releases predate Creative Cloud yearly builds.
    if "cs6" in text:
        year = max(year, 2012)
    return (year, beta, str(path))


def _find_executable(app_folder_keyword: str, executable_names: tuple[str, ...], support_files: bool = False) -> Path | None:
    candidates: list[Path] = []
    for root in ADOBE_ROOTS:
        if not root.is_dir():
            continue
        for app_dir in root.iterdir():
            if not app_dir.is_dir() or app_folder_keyword.lower() not in app_dir.name.lower():
                continue
            search_dirs = [app_dir]
            if support_files:
                search_dirs.insert(0, app_dir / "Support Files")
            for search_dir in search_dirs:
                for name in executable_names:
                    candidate = search_dir / name
                    if candidate.is_file():
                        candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(key=_version_score, reverse=True)
    return candidates[0]


def find_afterfx() -> Path | None:
    env = os.getenv("AE_AFTERFX_PATH") or os.getenv("AFTERFX_PATH")
    if env and Path(env).is_file():
        return Path(env)
    return _find_executable("After Effects", ("AfterFX.com", "AfterFX.exe"), support_files=True)


def find_aerender() -> Path | None:
    env = os.getenv("AE_AERENDER_PATH") or os.getenv("AERENDER_PATH")
    if env and Path(env).is_file():
        return Path(env)
    return _find_executable("After Effects", ("aerender.exe",), support_files=True)


def find_premiere() -> Path | None:
    env = os.getenv("PREMIERE_PATH") or os.getenv("PREMIERE_PRO_PATH")
    if env and Path(env).is_file():
        return Path(env)
    return _find_executable("Premiere Pro", ("Adobe Premiere Pro.exe",), support_files=False)


def find_media_encoder() -> Path | None:
    env = os.getenv("AME_PATH") or os.getenv("ADOBE_MEDIA_ENCODER_PATH")
    if env and Path(env).is_file():
        return Path(env)
    return _find_executable("Media Encoder", ("Adobe Media Encoder.exe",), support_files=False)


def capability_report() -> dict[str, str | bool]:
    afterfx = find_afterfx()
    aerender = find_aerender()
    premiere = find_premiere()
    ame = find_media_encoder()
    return {
        "afterfx_path": str(afterfx or ""),
        "afterfx_exists": bool(afterfx and afterfx.is_file()),
        "aerender_path": str(aerender or ""),
        "aerender_exists": bool(aerender and aerender.is_file()),
        "premiere_path": str(premiere or ""),
        "premiere_exists": bool(premiere and premiere.is_file()),
        "media_encoder_path": str(ame or ""),
        "media_encoder_exists": bool(ame and ame.is_file()),
    }
