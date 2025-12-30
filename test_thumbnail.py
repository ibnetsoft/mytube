
import requests
import json
import base64
import os
import webbrowser

def test_thumbnail():
    url = "http://127.0.0.1:8000/api/image/generate-thumbnail"
    
    # payload with Japanese text and language
    payload = {
        "prompt": "A futuristic city with neon lights, cinematic, 8k",
        "text": "衝撃の真実", # Shocking Truth (Japanese)
        "text_position": "center",
        "text_color": "#FFFF00", # Yellow
        "font_size": 90,
        "language": "ja" # Testing Japanese font selection
    }
    
    print(f"Testing Thumbnail Generation with payload: {payload}")
    
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "ok":
                print("Thumbnail generated successfully!")
                print(f"URL: {result.get('url')}")
                # The URL is relative or absolute web path? usually /output/...
                # Let's try to open it if it's a file path
                
                # Check if we can find the file locally to verify
                # result['url'] might be like '/output/thumbnail_...'
                file_url = result.get('url')
                if file_url:
                     print(f"Generated Image URL: {file_url}")
            else:
                print(f"Failed (status not ok): {result}")
        else:
            print(f"Failed with status code {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Exception checking thumbnail: {e}")

if __name__ == "__main__":
    test_thumbnail()
