import os
import shutil
import subprocess
import sys


def build():
    app_name = "PicadiriRemoteWorker"
    main_script = "remote_drive_worker.py"

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    for path in ["build", os.path.join("dist", app_name)]:
        if os.path.exists(path):
            shutil.rmtree(path)

    hidden_imports = [
        "googleapiclient.discovery",
        "googleapiclient.http",
        "google_auth_oauthlib.flow",
        "google.oauth2.credentials",
        "moviepy",
        "moviepy.audio.fx.all",
        "moviepy.video.fx.all",
        "pydub",
        "PIL",
        "requests",
        "urllib3",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        app_name,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--console",
    ]

    for hidden in hidden_imports:
        cmd.extend(["--hidden-import", hidden])

    cmd.append(main_script)

    print("Executing:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"\nBuild complete: dist\\{app_name}.exe")
    print("Copy .env or configure environment variables beside the EXE before running it.")


if __name__ == "__main__":
    build()
