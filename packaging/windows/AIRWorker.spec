"""
[AIR-0227E] PyInstaller spec for AIRWorker.exe - the single executable that
plays every AIR Worker role (Manager, Render Worker, Hermes Worker, Local
API), re-invoked with `--role <name>` for each (see
worker/air_worker_entry.py and worker/manager.py's _child_command()).

Modeled on AIRStudio.spec (Render Worker imports the exact same
services/app modules AIRStudio.exe does - services/remote_render_service.py
-> services/video_service.py, transitively services/app/config/database),
but onefile + console (docs/AIR_WORKER_ARCHITECTURE.md's CLI status screen,
and AIRWorker is meant to run unattended on a rendering PC, not present a
GUI) instead of AIRStudio's onedir + windowed.
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

# [AIR-0227E, found via live build+run QA] services/video_service.py's
# MoviePy import falls all the way through to "MoviePy 또는 Requests가
# 설치되지 않았습니다" with the underlying cause "No package metadata was
# found for imageio" - moviepy/imageio check their own version via
# importlib.metadata at import time, which fails in a frozen app unless
# each package's .dist-info is explicitly bundled (PyInstaller does not
# do this automatically, same class of issue AIRStudio.spec already hit
# and fixed for google-genai/pykakasi above).
for _pkg in ("imageio", "imageio-ffmpeg", "moviepy"):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

# [AIR-0227E-P2-VALIDATION §4] ffprobe.exe, matched build/version to the
# bundled ffmpeg.exe - see AIRWorker_onedir.spec's identical block for the
# full rationale. Onefile is portable/diagnostic-only per this task's
# confirmed decision, but still ships ffprobe for consistency.
_ffprobe_path = os.path.join(root, "_dev", "vendor", "ffprobe", "ffprobe.exe")
if os.path.exists(_ffprobe_path):
    binaries.append((_ffprobe_path, "."))
else:
    print(f"WARNING: ffprobe.exe not found at {_ffprobe_path} - run `python _dev/fetch_ffprobe.py` first. Building WITHOUT ffprobe bundled.")

_ffprobe_license_path = os.path.join(root, "_dev", "vendor", "ffprobe", "FFmpeg-LICENSE.txt")
if os.path.exists(_ffprobe_license_path):
    datas.append((_ffprobe_license_path, "licenses"))

_notices_src = os.path.join(SPECPATH, "THIRD_PARTY_NOTICES.md")
if os.path.exists(_notices_src):
    _notices_build_dir = os.path.join(root, "build", "_generated")
    os.makedirs(_notices_build_dir, exist_ok=True)
    _notices_txt = os.path.join(_notices_build_dir, "THIRD_PARTY_NOTICES.txt")
    with open(_notices_src, "r", encoding="utf-8") as _f:
        _notices_content = _f.read()
    with open(_notices_txt, "w", encoding="utf-8") as _f:
        _f.write(_notices_content)
    datas.append((_notices_txt, "licenses"))

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
    # [AIR-0225B, incident response] Do NOT add ".env" here - see the
    # identical note in AIRStudio.spec. AIRWorker never needs Supabase
    # credentials at all (docs/AIR_WORKER_SECURITY.md §1), so no packaged
    # .env is written for it by any build step, unlike AIRStudio.
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
    # pywin32 - worker/local_api_token.py's DPAPI token storage
    # (win32crypt.CryptProtectData/CryptUnprotectData). win32timezone is the
    # classic PyInstaller+pywin32 hidden-import gotcha (pywin32 imports it
    # lazily in a way static analysis regularly misses).
    "win32crypt",
    "win32api",
    "pywintypes",
    "win32timezone",
]
hiddenimports += pykakasi_hiddenimports
hiddenimports += collect_submodules("pykakasi")
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("services")
# moviepy/PIL - services/video_service.py imports many of their submodules
# inside try/except blocks (moviepy 1.x/2.x compat fallbacks), which is
# fragile for PyInstaller's static import scan - collect_submodules is the
# same broad-net approach AIRStudio.spec uses for pykakasi.
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AIRWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.path.join(SPECPATH, "version_info.txt"),
)
