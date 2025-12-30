import requests
import json
import sqlite3
import os

def test_save_subtitle():
    # 1. Get latest project ID
    conn = sqlite3.connect('data/wingsai.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects ORDER BY updated_at DESC LIMIT 1")
    pid = cursor.fetchone()[0]
    conn.close()
    
    print(f"Testing save for Project ID: {pid}")
    
    # 2. Mock Subtitles
    subtitles = [
        {"start": 0, "end": 2, "text": "Test Subtitle 1"},
        {"start": 2, "end": 4, "text": "Test Subtitle 2"}
    ]
    
    # 3. Send Request
    url = "http://127.0.0.1:8000/api/subtitle/save"
    payload = {
        "project_id": pid,
        "subtitles": subtitles
    }
    
    try:
        res = requests.post(url, json=payload)
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text}")
        
        if res.status_code == 200:
            print("Save successful via API.")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_save_subtitle()
