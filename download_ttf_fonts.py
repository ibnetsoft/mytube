import os
import requests

def download_file(url, save_path):
    try:
        if os.path.exists(save_path):
            print(f"File already exists: {save_path}")
            return
            
        print(f"Downloading {url}...")
        response = requests.get(url)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            print(f"Saved to {save_path}")
        else:
            print(f"Failed to download: {response.status_code}")
    except Exception as e:
        print(f"Error downloading: {e}")

fonts_dir = "static/fonts"
os.makedirs(fonts_dir, exist_ok=True)

# List of fonts to download (Google Fonts / Public CDN)
fonts = {
    "GmarketSansBold.ttf": "https://raw.githubusercontent.com/projectnoonnu/noonfonts_2001/master/GmarketSansBold.ttf",
    "GmarketSansMedium.ttf": "https://raw.githubusercontent.com/projectnoonnu/noonfonts_2001/master/GmarketSansMedium.ttf",
    "Recipekorea.ttf": "https://raw.githubusercontent.com/projectnoonnu/noonfonts_2001/master/Recipekorea_RECIPE.ttf",
    "NanumGothic.ttf": "https://fonts.gstatic.com/s/nanumgothic/v23/PN_3Rfi-oW3hYwmKDpxS7F_z-7rE.ttf",
    "NanumPen.ttf": "https://fonts.gstatic.com/s/nanumpenscript/v18/TqO2Z44hJ-Y6y-u5rQYyg41w.ttf",
    "CookieRun-Regular.ttf": "https://raw.githubusercontent.com/projectnoonnu/noonfonts_two/master/CookieRun-Regular.ttf"
}

for name, url in fonts.items():
    download_file(url, os.path.join(fonts_dir, name))
