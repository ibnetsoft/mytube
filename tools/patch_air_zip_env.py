from pathlib import Path
import hashlib
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
zip_path = root / "release" / "AIRStudio-0.1.0-win-x64.zip"
env_path = root / "release" / "staging" / "AIRStudio" / "app" / ".env"
config_path = root / "release" / "staging" / "AIRStudio" / "Launcher" / "update_config.json"
tmp_path = zip_path.with_suffix(".tmp")

with zipfile.ZipFile(zip_path, "r") as zin, zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        normalized = info.filename.replace("\\", "/")
        if normalized in {"app/.env", "Launcher/update_config.json"}:
            continue
        zout.writestr(info, zin.read(info.filename))
    zout.writestr("app/.env", env_path.read_bytes())
    zout.writestr("Launcher/update_config.json", config_path.read_bytes())

shutil.move(str(tmp_path), str(zip_path))
print(hashlib.sha256(zip_path.read_bytes()).hexdigest())
