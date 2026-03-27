
import os

path = "main.py"
with open(path, "rb") as f:
    data = f.read()

# 1. Update ApiKeySave model
start_match = b"class ApiKeySave(BaseModel):"
end_match = b"@app.get(\"/api/settings/api-keys\")"
s = data.find(start_match)
e = data.find(end_match, s)

if s != -1 and e != -1:
    new_model = """class ApiKeySave(BaseModel):
    youtube: Optional[str] = None
    gemini: Optional[str] = None
    elevenlabs: Optional[str] = None
    typecast: Optional[str] = None
    replicate: Optional[str] = None
    topview: Optional[str] = None
    topview_uid: Optional[str] = None
    akool_id: Optional[str] = None
    akool_secret: Optional[str] = None
    akool_api_key: Optional[str] = None
    blog_client_id: Optional[str] = None
    blog_client_secret: Optional[str] = None
    blog_id: Optional[str] = None
    wp_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_password: Optional[str] = None

""".encode('utf-8')
    data = data[:s] + new_model + data[e:]
    print("Updated ApiKeySave model")

# 2. Update save_api_keys and remove emojis
start_match = b"async def save_api_keys(req: ApiKeySave):"
s = data.find(start_match)
if s != -1:
    ret_idx = data.find(b"return {", s)
    if ret_idx != -1:
        e = data.find(b"}", ret_idx) + 1
        while e < len(data) and data[e:e+1] in b" \r\n\t":
            e += 1
    else:
        e = data.find(b"\n@", s)

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
    data = data[:s] + new_func + data[e:]
    print("Updated save_api_keys function")

# 3. Remove ALL redundant /api/settings routes
def remove_all_simple(data, pattern):
    count = 0
    while True:
        idx = data.find(pattern)
        if idx == -1: break
        next_app = data.find(b"@app.", idx + 1)
        if next_app == -1:
            data = data[:idx]
            count += 1
            break
        else:
            data = data[:idx] + data[next_app:]
            count += 1
    return data, count

data, c1 = remove_all_simple(data, b"@app.get(\"/api/settings\")")
data, c2 = remove_all_simple(data, b"@app.post(\"/api/settings\")")
print(f"Removed {c1} GET and {c2} POST redundant routes")

with open(path, "wb") as f:
    f.write(data)
print("FINAL SUCCESS")
