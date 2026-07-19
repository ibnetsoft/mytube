import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
    collect_data_files,
)

block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = []
binaries = []
try:
    datas += copy_metadata("google-genai")
except Exception:
    pass

# [FIX] moviepy(via imageio) reads its own package metadata at import time.
# Without it bundled, the FIRST `from moviepy import ...` attempt in
# services/tts_service.py raises "No package metadata was found for
# imageio", which leaves moviepy.audio.AudioClip partially initialized in
# sys.modules - every subsequent fallback import then fails with the more
# confusing "cannot import name 'CompositeAudioClip' from partially
# initialized module ... (most likely due to a circular import)", which is
# what actually surfaced as a broken TTS generation button in v2.3.13/14.
# Reproduced and confirmed fixed with a minimal PyInstaller build before
# adding this.
try:
    datas += copy_metadata("imageio")
except Exception:
    pass

pykakasi_datas, pykakasi_binaries, pykakasi_hiddenimports = collect_all("pykakasi")
datas += pykakasi_datas
binaries += pykakasi_binaries
datas += collect_data_files("pykakasi")
try:
    datas += copy_metadata("pykakasi")
except Exception:
    pass

for src, dest in [
    ("templates", "templates"),
    ("static", "static"),
    ("assets", "assets"),
    # [AIR-0225B, incident response] Do NOT add ".env" here. This used to blanket-
    # copy whatever .env sits at the repo root (including a developer's own local
    # SUPABASE_SERVICE_ROLE_KEY) straight into the frozen bundle on any local
    # PyInstaller build, independent of and in addition to the CI-side .env write
    # in tools/build_windows.ps1. The packaged .env is now written exclusively (and
    # only with the public Supabase URL) by tools/build_windows.ps1 after this
    # PyInstaller step runs - see
    # worknote/AIR-0225B-stage0-service-role-removal-investigation.md §1.
]:
    path = os.path.join(root, src)
    if os.path.exists(path):
        datas.append((path, dest))

hiddenimports = [
    "pykakasi",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "pydub",
    "webview",
]
hiddenimports += pykakasi_hiddenimports
hiddenimports += collect_submodules("pykakasi")
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("services")

a = Analysis(
    [os.path.join(root, "main.py")],
    pathex=[root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "auth-web",
        "saas-frontend",
        "tests",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AIRStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AIRStudio",
)
