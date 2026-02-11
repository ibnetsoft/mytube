
import os
import sys

log_path = os.path.join(os.path.dirname(__file__), "audit_log.txt")
utf8_path = os.path.join(os.path.dirname(__file__), "audit_log_utf8.txt")

try:
    with open(log_path, 'r', encoding='utf-16le') as f:
        content = f.read()
    
    # Filter for relevant log entries (e.g., project_id=67 or "비트코인")
    lines = content.split('\n')
    relevant_log = []
    
    print(f"Reading {len(lines)} lines from audit_log.txt...")
    
    for line in lines:
        if "67" in line or "비트코인" in line or "autopilot" in line.lower():
            relevant_log.append(line)
            
    # Print the last 20 relevant lines
    print("\n--- RELEVANT LOGS ---")
    for l in relevant_log[-20:]:
        print(l)
        
except Exception as e:
    print(f"Error reading log: {e}")

# Also try to execute the youtube search to reproduce
print("\n--- REPRODUCING YOUTUBE SEARCH ---")
try:
    # We need to import config to get the API Key, but config might import other things.
    # Let's try to mock the environment or just import config if possible.
    sys.path.append(os.path.dirname(__file__))
    import config
    import httpx
    import asyncio
    
    async def search_youtube():
        keyword = "비트코인전망"
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet", 
            "q": keyword, 
            "type": "video",
            "maxResults": 5, 
            "order": "viewCount", 
            "videoDuration": "short",
            "key": config.YOUTUBE_API_KEY
        }
        
        print(f"Searching for: {keyword}")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                for i, item in enumerate(items):
                    title = item["snippet"]["title"]
                    vid = item["id"]["videoId"]
                    desc = item["snippet"]["description"]
                    print(f"[{i+1}] {title} ({vid})")
                    print(f"    Desc: {desc[:100]}...")
                    if "기안84" in title or "기안84" in desc:
                         print("    *** MATCH FOUND: This video mentions 기안84! ***")
            else:
                print(f"Search failed: {response.status_code} {response.text}")

    asyncio.run(search_youtube())
    
except Exception as e:
    print(f"Search reproduction error: {e}")
