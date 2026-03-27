
import os
import requests

fonts_dir = "static/fonts"
os.makedirs(fonts_dir, exist_ok=True)

urls = {
    "GmarketSansBold.woff": "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/GmarketSansBold.woff",
    "CookieRun-Regular.woff": "https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/CookieRun-Regular.woff"
}

for name, url in urls.items():
    try:
        print(f"Downloading {name}...")
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            with open(os.path.join(fonts_dir, name), "wb") as f:
                f.write(res.content)
            print("Success.")
        else:
            print(f"Failed: {res.status_code}")
    except Exception as e:
        print(f"Error: {e}")
