
import database as db
import json

def check_project_5():
    pid = 5
    print(f"--- Checking Project {pid} ---")
    
    # 1. Check Scripts Table
    script_entry = db.get_script(pid)
    print(f"[Scripts Table] Entry exists: {script_entry is not None}")
    if script_entry:
        print(f"  - full_script length: {len(script_entry.get('full_script', ''))}")
    
    # 2. Check Project Settings Table
    settings = db.get_project_settings(pid)
    print(f"[Settings Table] Entry exists: {settings is not None}")
    if settings:
        print(f"  - script field length: {len(settings.get('script') or '')}")
        print(f"  - script content preview: {(settings.get('script') or '')[:50]}...")
        
    # 3. Check Image Prompts
    prompts = db.get_image_prompts(pid)
    print(f"[Image Prompts] Count: {len(prompts)}")
    for i, p in enumerate(prompts):
        print(f"  - [{i+1}] url: {p.get('image_url')}")
        
    # 4. Check API response simulation
    full_data = db.get_project_full_data(pid)
    print(f"[API Response Keys] {list(full_data.keys())}")
    print(f"  - 'image_prompts' in keys? {'image_prompts' in full_data}")
    print(f"  - 'images' in keys? {'images' in full_data}")

if __name__ == "__main__":
    check_project_5()
