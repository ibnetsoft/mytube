import requests
import sqlite3
import os
import sys

# Get latest project ID
try:
    conn = sqlite3.connect('data/wingsai.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        print("No projects.")
        sys.exit(0)
    
    pid = row[0]
    print(f"Testing Project ID: {pid}")
    
    url = f"http://127.0.0.1:8000/api/projects/{pid}/full"
    print(f"Requesting: {url}")
    
    try:
        resp = requests.get(url, timeout=5)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            prompts = data.get('image_prompts')
            print(f"Keys: {data.keys()}")
            print(f"Image Prompts Count: {len(prompts) if prompts else 0}")
            if prompts and len(prompts) > 0:
                print(f"Sample Prompt: {prompts[0]}")
            else:
                print("Prompts is empty list or None")
        else:
            print(f"Error Body: {resp.text}")
            
    except Exception as e:
        print(f"Request Failed: {e}")

except Exception as e:
    print(f"DB Error: {e}")
