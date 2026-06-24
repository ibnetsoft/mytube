import os
import json

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
    collect_data_files,
)

# 루트 경로
root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

# 데이터 수집
datas = []
binaries = []
datas += copy_metadata("replicate")
try:
    datas += copy_metadata("google-generativeai")
except Exception:
    pass

datas += collect_all("pykakasi")
binaries += pykakasi_binaries
datas += collect_data_files("pykakasi")

datas += collect_data_files("pykakasi")
try:
    datas += copy_metadata("pykakasi")
except Exception:
    pass

# 파일 복사
for src, dest in [
    ("templates", "templates"),
    ("static", "static"),
    ("assets", "assets"),
    (".env", "."),
]:
    path = os.path.join(root, src)
    if os.path.exists(path):
        datas.append((path, dest))

# 숨견 제외
hidden_imports = [
    "pykakasi",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "pydub",
    "webview",
]
hidden_imports += collect_submodules("pykakasi")
hidden_imports += collect_submodules("app")
hidden_imports += collect_submodules("services")

# 분석 실행 설정
a = Analysis(
    [os.path.join(root, "main.py")],
    pathex=[root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "auth-web",
        "saasfrontend",
        "tests",
        ".claude",
        ".env",
        "env.*",
    ],
    # 백엔드 모드 실행 옵션
    win_no_prefer_redirects=False,  # ← 항상상: true로 설정하면 창이 안 뜸
    win_private_assemblies=False,
    noarchive=False,
)

# 패키징
pyz = PYZ(
    a.pure,
    a.scripts,
    [],
    exclude_binaries=True,
    upx=True,
    upx_exclude=[],
    name="AIRStudio",
    debug=False,
    console=True,  # ← 콘솔 창 표시
    disable_windowed_traceback=False,
    argv_emulation=False,
)