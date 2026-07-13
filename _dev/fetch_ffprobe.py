"""
[AIR-0227E-P2-VALIDATION §4] Fetches ffprobe.exe from the exact same source
and version as the ffmpeg.exe already bundled via the `imageio-ffmpeg`
Python package (gyan.dev "essentials" build, mirrored on GitHub at
GyanD/codexffmpeg), so AIRWorker ships a matched ffmpeg+ffprobe set - same
build, same configuration flags, same license - rather than two binaries
from different builds that could disagree on codec support or behavior.

Confirmed match (see docs/AIR_WORKER_FFMPEG_LICENSE.md for the full
writeup): both report
`{ffmpeg,ffprobe} version 7.1-essentials_build-www.gyan.dev` with an
identical `configuration:` string.

Saves to _dev/vendor/ffprobe/ffprobe.exe (gitignored - this is a ~87MB
vendored build input, not something to commit; packaging/windows/*.spec
picks it up from this path if present).

Usage: python _dev/fetch_ffprobe.py
"""
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = "https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip"
EXPECTED_SHA256 = "436bf02524d50135ed9965b90d1e0ad7f26c5c236132613a2edb87ef8b6873d0"  # ffprobe.exe itself, verified 2026-07-13
ZIP_MEMBER_EXE = "ffmpeg-7.1-essentials_build/bin/ffprobe.exe"
ZIP_MEMBER_LICENSE = "ffmpeg-7.1-essentials_build/LICENSE"

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "_dev" / "vendor" / "ffprobe"
DEST_EXE = VENDOR_DIR / "ffprobe.exe"
DEST_LICENSE = VENDOR_DIR / "FFmpeg-LICENSE.txt"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if DEST_EXE.exists() and sha256_of(DEST_EXE) == EXPECTED_SHA256:
        print(f"Already present and verified: {DEST_EXE}")
        return 0

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "ffmpeg-essentials.zip"
        print(f"Downloading {RELEASE_URL} ...")
        urllib.request.urlretrieve(RELEASE_URL, zip_path)

        with zipfile.ZipFile(zip_path) as zf:
            with zf.open(ZIP_MEMBER_EXE) as src, open(DEST_EXE, "wb") as dst:
                shutil.copyfileobj(src, dst)
            with zf.open(ZIP_MEMBER_LICENSE) as src, open(DEST_LICENSE, "wb") as dst:
                shutil.copyfileobj(src, dst)

    actual = sha256_of(DEST_EXE)
    if actual != EXPECTED_SHA256:
        print(f"SHA256 MISMATCH: expected {EXPECTED_SHA256}, got {actual}", file=sys.stderr)
        return 1

    print(f"ffprobe.exe verified and saved to {DEST_EXE} (sha256={actual})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
