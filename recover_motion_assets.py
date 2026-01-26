
import os
import glob
import json
import sqlite3
import re
from config import config
import database as db

def recover_motion_assets():
    print("🔍 Scanning for lost motion assets...")
    
    # 1. Scan for motion files
    # Pattern: motion_{project_id}_{scene_number}_{timestamp}.mp4
    # Location: output/motion_*.mp4
    # Also check project subfolders if they exist
    
    search_patterns = [
        os.path.join(config.OUTPUT_DIR, "motion_*.mp4"),
        os.path.join(config.OUTPUT_DIR, "*", "motion_*.mp4") # In case of subfolders
    ]
    
    motion_files = []
    for pattern in search_patterns:
        motion_files.extend(glob.glob(pattern))
        
    print(f"📂 Found {len(motion_files)} candidate motion files.")
    
    recovered_count = 0
    
    conn = db.get_db()
    cursor = conn.cursor()
    
    for file_path in motion_files:
        filename = os.path.basename(file_path)
        
        # Parse filename
        # Expected: motion_15_1_... OR motion_p28_s1_...
        match = re.match(r"motion_(?:p)?(\d+)_(?:s)?(\d+)_", filename)
        if not match:
            print(f"⚠️ Skipping non-standard file: {filename}")
            continue
            
        project_id = int(match.group(1))
        scene_number = int(match.group(2))
        
        # Web URL
        rel_path = os.path.relpath(file_path, config.OUTPUT_DIR)
        web_url = f"/output/{rel_path}".replace("\\", "/")
        
        print(f"➡️ Processing: P={project_id}, S={scene_number}, URL={web_url}")
        
        # 1. Update DB (image_prompts)
        try:
            cursor.execute(
                "UPDATE image_prompts SET video_url = ? WHERE project_id = ? AND scene_number = ?",
                (web_url, project_id, scene_number)
            )
            if cursor.rowcount > 0:
                print(f"   ✅ DB Updated for Scene {scene_number}")
                recovered_count += 1
            else:
                print(f"   ⚠️ Scene {scene_number} not found in DB for Project {project_id}")
                
            # 2. Update Timeline JSON
            # Load project settings to find timeline path
            cursor.execute("SELECT video_path, timeline_images_path, image_timings_path FROM project_settings WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            
            if row and row['timeline_images_path'] and os.path.exists(row['timeline_images_path']):
                tm_path = row['timeline_images_path']
                
                with open(tm_path, 'r', encoding='utf-8') as f:
                    timeline = json.load(f)
                
                # Check if this scene corresponds to any index in timeline
                # We don't have direct mapping index->scene here easily, 
                # BUT usually timeline order matches scene order if not reordered.
                # BETTER APPROACH: Retrieve the original image_url for this scene from DB and replace it in timeline.
                
                cursor.execute("SELECT image_url FROM image_prompts WHERE project_id=? AND scene_number=?", (project_id, scene_number))
                img_row = cursor.fetchone()
                
                if img_row and img_row['image_url']:
                    orig_img_url = img_row['image_url']
                    
                    patched = False
                    for i, item in enumerate(timeline):
                        # Match by URL or Filename
                        if item == orig_img_url or os.path.basename(item) == os.path.basename(orig_img_url):
                            timeline[i] = web_url
                            patched = True
                            print(f"   ✅ Timeline Patched at index {i}")
                    
                    if patched:
                        with open(tm_path, 'w', encoding='utf-8') as f:
                            json.dump(timeline, f, indent=2)
                            
        except Exception as e:
            print(f"   ❌ Error updating DB/Timeline: {e}")
            
    conn.commit()
    conn.close()
    
    print(f"\n🎉 Recovery Complete. {recovered_count} assets linked.")

if __name__ == "__main__":
    recover_motion_assets()
