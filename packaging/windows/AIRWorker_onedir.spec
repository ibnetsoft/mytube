"""
[AIR-0227E-P2] Onedir variant of AIRWorker.spec, for comparison against the
onefile build (P1) and as the basis for the Inno Setup installer (P2-6).
Onedir avoids onefile's self-extraction-to-temp-dir step on every launch,
which P1's testing showed has variable (15-60s+ observed under load) cold
start latency - onedir should start close to instantly since nothing needs
extracting. Same Analysis inputs as AIRWorker.spec; only the EXE/COLLECT
tail differs (exclude_binaries=True + COLLECT, matching AIRStudio.spec's
onedir pattern) instead of onefile's single EXE.
"""
import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
    collect_data_files,
)

block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
worker_dir = os.path.join(root, "worker")

datas = []
binaries = []
try:
    datas += copy_metadata("google-genai")
except Exception:
    pass

for _pkg in ("imageio", "imageio-ffmpeg", "moviepy"):
    try:
        datas += copy_metadata(_pkg)
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
]:
    path = os.path.join(root, src)
    if os.path.exists(path):
        datas.append((path, dest))

hiddenimports = [
    "pykakasi",
    "fastapi",
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
    "requests",
    "urllib3",
    "win32crypt",
    "win32api",
    "pywintypes",
    "win32timezone",
]
hiddenimports += pykakasi_hiddenimports
hiddenimports += collect_submodules("pykakasi")
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("services")
hiddenimports += collect_submodules("moviepy")
hiddenimports += collect_submodules("PIL")

a = Analysis(
    [os.path.join(worker_dir, "air_worker_entry.py")],
    pathex=[root, worker_dir],
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
    name="AIRWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name="AIRWorker",
)
