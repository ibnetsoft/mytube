#!/usr/bin/env python3
"""Fix subtitle logic to make English exclusion optional based on configuration setting"""

import re

file_path = "app/routers/video.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the automatic language check with optional check
old_code = '''        if project and project.get("language") == "en":
            print(f"DEBUG: Project {project_id} is English, disabling subtitles")
            use_subtitles_effective = False'''

new_code = '''        skip_subtitles_for_english = db.get_global_setting("skip_subtitles_for_english", False)
        if skip_subtitles_for_english and project and project.get("language") == "en":
            print(f"DEBUG: Project {project_id} is English and skip_subtitles_for_english is enabled, disabling subtitles")
            use_subtitles_effective = False'''

if old_code in content:
    content = content.replace(old_code, new_code)
    print("✓ Replaced automatic language check with optional logic")
else:
    print("✗ Could not find the code to replace")

# Also update the call to render_executor_func to use use_subtitles_effective
old_call = '''        background_tasks.add_task(render_executor_func, output_dir, request.use_subtitles, target_resolution, bg_video_url, intro_v_path)'''

new_call = '''        background_tasks.add_task(render_executor_func, output_dir, use_subtitles_effective, target_resolution, bg_video_url, intro_v_path)'''

if old_call in content:
    content = content.replace(old_call, new_call)
    print("✓ Updated render_executor_func call to use use_subtitles_effective")
else:
    print("✗ Could not find render_executor_func call to update")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ File updated successfully")
