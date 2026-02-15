import database as db
s = db.get_project_settings(78)
print(f"all_video: {s.get('all_video')}")
print(f"video_engine: {s.get('video_engine')}")
print(f"video_scene_count: {s.get('video_scene_count')}")
print(f"app_mode: {s.get('app_mode')}")
