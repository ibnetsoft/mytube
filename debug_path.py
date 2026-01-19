
import os
import sys
from config import config

print(f"BASE_DIR: {config.BASE_DIR}")
print(f"OUTPUT_DIR: {config.OUTPUT_DIR}")
print(f"STATIC_DIR: {config.STATIC_DIR}")

test_dir = os.path.join(config.OUTPUT_DIR, "thumbnails")
print(f"Target Save Dir: {test_dir}")

try:
    os.makedirs(test_dir, exist_ok=True)
    print(f"Created dir: {test_dir}")
    
    test_file = os.path.join(test_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("test")
    print(f"Created file: {test_file}")
    
    import glob
    files = glob.glob(os.path.join(test_dir, "*"))
    print(f"Files in dir: {files}")
    
except Exception as e:
    print(f"Error: {e}")
