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
datas += copy_metadata("replicate")
try:
    datas += copy_metadata("google-generativeai")
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
    (".env", "."),
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
    name="AIRStudio",
)
