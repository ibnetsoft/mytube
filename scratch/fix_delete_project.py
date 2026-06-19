import re

with open('database.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the delete_project tables list
old = (
    "    tables = ['analysis', 'script_structure', 'scripts', 'image_prompts',\r\n"
    "              'tts_audio', 'metadata', 'thumbnails', 'shorts']\r\n"
    "    for table in tables:\r\n"
    "        cursor.execute(f\"DELETE FROM {table} WHERE project_id = ?\", (project_id,))"
)
new = (
    "    tables = ['analysis', 'script_structure', 'scripts', 'image_prompts',\r\n"
    "              'tts_audio', 'metadata', 'thumbnails', 'shorts',\r\n"
    "              'project_settings', 'music_track_plans', 'project_sources']\r\n"
    "    for table in tables:\r\n"
    "        try:\r\n"
    "            cursor.execute(f\"DELETE FROM {table} WHERE project_id = ?\", (project_id,))\r\n"
    "        except Exception:\r\n"
    "            pass  # Table may not exist yet"
)

if old in content:
    content = content.replace(old, new)
    with open('database.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: delete_project updated")
else:
    # Try LF only version
    old_lf = old.replace('\r\n', '\n')
    if old_lf in content:
        new_lf = new.replace('\r\n', '\n')
        content = content.replace(old_lf, new_lf)
        with open('database.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("SUCCESS (LF): delete_project updated")
    else:
        print("NOT FOUND - manual fix needed")
        # Print surrounding context for debugging
        idx = content.find("def delete_project")
        if idx >= 0:
            print("Found function at:", idx)
            print(repr(content[idx:idx+400]))
