import database as db

pid = 68
print(f"--- PROJECT {pid} ASSETS ---")
prompts = db.get_image_prompts(pid)
for p in prompts:
    print(f"Scene {p['scene_number']}:")
    print(f"  Image: {p.get('image_url')}")
    print(f"  Video: {p.get('video_url')}")
