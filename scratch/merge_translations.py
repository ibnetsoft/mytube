import sys
import os
sys.path.append(os.getcwd())

from services.i18n import PLATFORM_TRANSLATIONS

def merge():
    pt_keys = set(PLATFORM_TRANSLATIONS['pt'].keys())
    vi_keys = set(PLATFORM_TRANSLATIONS['vi'].keys())
    diff = pt_keys - vi_keys
    print(f"Number of keys to merge: {len(diff)}")
    
    # Read the file
    with open("services/i18n.py", "r", encoding="utf-8") as f:
        content = f.read()
        
    # We will locate the line "'vi': {"
    target = "'vi': {"
    idx = content.find(target)
    if idx == -1:
        print("Could not find 'vi': { in i18n.py")
        return
        
    # We will insert the keys right after the opening brace of 'vi': {
    insert_pos = idx + len(target)
    
    insert_str = "\n"
    for k in sorted(list(diff)):
        val = PLATFORM_TRANSLATIONS['pt'][k]
        # Escape single quotes in value
        escaped_val = val.replace("'", "\\'")
        insert_str += f"        '{k}': '{escaped_val}',\n"
        
    new_content = content[:insert_pos] + insert_str + content[insert_pos:]
    
    with open("services/i18n.py", "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print("Successfully merged keys into services/i18n.py!")

if __name__ == "__main__":
    merge()
