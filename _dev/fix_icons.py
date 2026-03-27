import os
import shutil

# Paths
base_dir = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\extensions\google_flow_bridge\icons"
source_icon = r"C:\Users\kimse\.gemini\antigravity\brain\f0144c95-10df-4801-b393-2ce3e9f16c57\extension_icon_1773283919419.png"

# Ensure directory exists
if not os.path.exists(base_dir):
    os.makedirs(base_dir)

# Target filenames
targets = ["icon16.png", "icon48.png", "icon128.png"]

for t in targets:
    target_path = os.path.join(base_dir, t)
    print(f"Copying to {target_path}...")
    shutil.copy2(source_icon, target_path)

print("Done!")
