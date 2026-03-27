
import os

path = "main.py"
with open(path, "rb") as f:
    data = f.read()

# Let's find the start of the save_api_keys function
start_marker = b"async def save_api_keys(req: ApiKeySave):"
# And find the likely end which is the return and the following braces
# Specifically, we want to look for the return that has the Korean text

# I'll just find the first occurrence of the function and the very end of it
# based on the known structure.

s = data.find(start_marker)
if s != -1:
    # Find the end of this function. It should end after return { ... }
    # Let's look for the next @app. which signifies the next route
    e = data.find(b"\n@app.", s + 1)
    if e == -1:
        # If no more routes, find the end of file or some other marker
        e = data.find(b"\n#", s + 1)
    
    if e != -1:
        new_func = """async def save_api_keys(req: ApiKeySave):
    \"\"\"API 키 저장\"\"\"
    updated = []
    
    mapping = {
        'youtube': 'YOUTUBE_API_KEY',
        'gemini': 'GEMINI_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'typecast': 'TYPECAST_API_KEY',
        'replicate': 'REPLICATE_API_TOKEN',
        'topview': 'TOPVIEW_API_KEY',
        'topview_uid': 'TOPVIEW_UID',
        'akool_id': 'AKOOL_CLIENT_ID',
        'akool_secret': 'AKOOL_CLIENT_SECRET',
        'akool_api_key': 'AKOOL_API_KEY',
        'blog_client_id': 'BLOG_CLIENT_ID',
        'blog_client_secret': 'BLOG_CLIENT_SECRET',
        'blog_id': 'BLOG_ID',
        'wp_url': 'WP_URL',
        'wp_username': 'WP_USERNAME',
        'wp_password': 'WP_PASSWORD'
    }

    req_dict = req.dict()
    print(f"[API_KEY] Save request received. Fields present: {[k for k,v in req_dict.items() if v is not None]}")
    for field, config_key in mapping.items():
        val = req_dict.get(field)
        if val is not None and val.strip():
            print(f"[API_KEY] Updating {field} -> {config_key} (len: {len(val.strip())})")
            config.update_api_key(config_key, val.strip())
            updated.append(field)

    return {
        "status": "ok",
        "updated": updated,
        "message": f"{len(updated)}개의 API 키가 저장되었습니다"
    }

""".encode('utf-8')
        
        fixed_data = data[:s] + new_func + data[e:]
        
        with open(path, "wb") as f:
            f.write(fixed_data)
        print("FIXED main.py")
    else:
        print("Could not find end of function")
else:
    print("Could not find start of function")
