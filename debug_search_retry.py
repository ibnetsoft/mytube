
import os
import sys
import asyncio
import httpx
from datetime import datetime

# Adjust path to import config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    # Check if config.config exists (instance) or just config.Config (class)
    if hasattr(config, 'config'):
        conf = config.config
    else:
        conf = config.Config
        
    api_key = conf.YOUTUBE_API_KEY
    if not api_key:
        print("Error: YOUTUBE_API_KEY not found in config.")
        sys.exit(1)
        
    async def search_youtube():
        keyword = "비트코인전망"
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet", 
            "q": keyword, 
            "type": "video",
            "maxResults": 5, 
            "order": "relevance", 
            "videoDuration": "short",
            "key": api_key
        }
        
        print(f"--- REPRODUCING YOUTUBE SEARCH FOR '{keyword}' ---")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                for i, item in enumerate(items):
                    title = item["snippet"]["title"]
                    vid = item["id"]["videoId"]
                    desc = item["snippet"]["description"]
                    channel = item["snippet"]["channelTitle"]
                    
                    print(f"[{i+1}] {title} ({vid}) by {channel}")
                    # print(f"    Desc: {desc[:100]}...")
                    
                    if "기안84" in title or "기안84" in desc:
                         print("    *** MATCH FOUND: This video mentions 기안84! ***")
            else:
                print(f"Search failed: {response.status_code} {response.text}")

    asyncio.run(search_youtube())

except Exception as e:
    print(f"Error: {e}")
