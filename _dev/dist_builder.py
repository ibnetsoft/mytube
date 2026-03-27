import os
import subprocess
import sys
import shutil

def build():
    print("🚀 Build Start: Creating standalone executable...")
    
    # 1. Install PyInstaller if missing
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Clean previous builds
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")
    
    # 3. Define Build Options
    app_name = "MyTubeStudio"
    main_script = "main.py"
    
    # Hidden imports required for Uvicorn/FastAPI/MoviePy
    hidden_imports = [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "engineio.async_drivers.asgi",
        "moviepy.audio.fx.all",
        "moviepy.video.fx.all",
        "pydub"
    ]
    
    # [FIX] Use python -m PyInstaller to avoid PATH issues
    cmd = [sys.executable, "-m", "PyInstaller"]
    
    cmd.extend([
        "--name", app_name,
        "--onefile",  # Create single .exe file
        "--clean",
        "--noconfirm",
    ])
    
    # Add hidden imports
    for hidden in hidden_imports:
        cmd.extend(["--hidden-import", hidden])
        
    # Add Data Files (Safe check)
    sep = ";" if os.name == 'nt' else ":"
    
    datas = [
        ("templates", "templates"),
        ("static", "static"),
        ("default_img.jpg", ".")
    ]
    
    for src, dest in datas:
        if os.path.exists(src):
            cmd.extend(["--add-data", f"{src}{sep}{dest}"])
        else:
            print(f"⚠️ Warning: Resource '{src}' not found. Skipping.")
    
    cmd.append(main_script)
    
    # 4. Run PyInstaller
    print(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    
    print("\n✅ Build Success!")
    print(f"Executable is located in: dist/{app_name}.exe")
    print("\n[NOTE] FFmpeg Handling:")
    print("MoviePy requires FFmpeg. You might need to place 'ffmpeg.exe' in the same folder as the generated .exe")
    print("or ensure IMAGEIO_FFMPEG_EXE environment variable is set.")

if __name__ == "__main__":
    build()
