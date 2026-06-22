# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = []
datas += copy_metadata("replicate")
try:
    datas += copy_metadata("google-generativeai")
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
]
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("services")

a = Analysis(
    [os.path.join(root, "main.py")],
    pathex=[root],
    binaries=[],
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
    name="PicadillyStudio",
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
    name="PicadillyStudio",
)
