import sys
print("Test started")
sys.path.append(".")
try:
    from app.routers.webtoon import slice_webtoon
    import numpy as np
    from PIL import Image
    import os
    
    # Create simple image
    print("Creating test image...")
    img = np.zeros((1000, 500, 3), dtype=np.uint8)
    img[100:900, 100:400] = 255
    out = Image.fromarray(img)
    os.makedirs("test_webtoon", exist_ok=True)
    out.save("test_webtoon/test.jpg")
    
    print("Running slice_webtoon...")
    cuts = slice_webtoon("test_webtoon/test.jpg", "test_webtoon", start_idx=1)
    print("Cuts:", cuts)
except Exception as e:
    import traceback
    traceback.print_exc()
print("Test finished")
