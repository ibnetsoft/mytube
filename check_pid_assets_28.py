import database as db

pid = 28
print(f"--- PROJECT {pid} ASSETS ---")
prompts = db.get_image_prompts(pid)
for p in prompts:
    v = p.get('video_url')
    if v:
        print(f"Scene {p['scene_number']}: {v}")
