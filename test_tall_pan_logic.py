import os
import sys
import subprocess
import shutil

# Ensure we can import modules from current directory
sys.path.append(os.getcwd())

try:
    import config
    from services.video_service import VideoService
except ImportError as e:
    print(f"Import Error: {e}")
    # Create mock config if needed
    class Config:
        OUTPUT_DIR = "test_output"
        FFMPEG_PATH = "ffmpeg"
    config = Config()
    if not os.path.exists(config.OUTPUT_DIR):
        os.makedirs(config.OUTPUT_DIR)
    # Mock VideoService if import fails (unlikely if in root)
    print("Using Mock Config")

def run_test():
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"DEBUG: ffmpeg_exe path: {ffmpeg_exe}")
    print(f"DEBUG: exists? {os.path.exists(ffmpeg_exe)}")
    
    # 1. Create Dummy Tall Video (9:32)
    # Input: 270x960 (9:32)
    test_video_path = "test_tall_input.mp4"
    target_w = 720
    target_h = 1280
    duration = 5.0
    
    print(f"🎥 [Step 1] Creating Dummy Tall Video: {test_video_path} (270x960, 9:32)")
    # Pattern: color block moving to simulate content? Just output is fine.
    cmd = [
        ffmpeg_exe, "-y", "-f", "lavfi", "-i", f"testsrc=size=270x960:rate=30:duration={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", test_video_path
    ]
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        print("   ✅ Input Video Created.")
    except Exception as e:
        print(f"   ❌ FFMPEG Failed to create input: {e}")
        return

    # 2. Initialize Service
    print("\n🚀 [Step 2] Initializing VideoService & Running Pan Down...")
    try:
        service = VideoService()
        # Override output dir for safety
        service.output_dir = "test_output"
        os.makedirs(service.output_dir, exist_ok=True)
        
        # 3. Executing Pan Down
        # Explicitly call the function we modified
        # direction="down"
        output_path = service._preprocess_video_tall_pan(
            test_video_path, target_w, target_h, duration, fps=30, direction="down"
        )
        print(f"   ✅ Process Completed. Output: {output_path}")
        
        probe_exe = ffmpeg_exe.replace("ffmpeg", "ffprobe")
        print(f"DEBUG: probe_exe path: {probe_exe}")
        print(f"DEBUG: probe_exe exists? {os.path.exists(probe_exe)}")
        
        # 4. Verify Output Dimensions
        print("\n🔍 [Step 3] Verifying Output...")
        
        probe_cmd = [
            probe_exe, "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", 
            "-of", "csv=p=0", output_path
        ]
        res = subprocess.run(probe_cmd, capture_output=True, text=True)
        dims = res.stdout.strip()
        print(f"   Output Dimensions: {dims}")
        
        if dims == f"{target_w},{target_h}":
            print(f"   🎉 TEST PASSED! Output is exactly {target_w}x{target_h} (9:16).")
            print("   The Pan Down logic executed successfully without errors.")
        else:
            print(f"   ❌ TEST FAILED: Expected {target_w}x{target_h}, got {dims}")

    except Exception as e:
        print(f"   ❌ Execution Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
