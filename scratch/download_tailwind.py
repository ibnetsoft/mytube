import requests
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Force bypass of all proxy environment variables
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

url = "https://cdn.tailwindcss.com"
try:
    print("Sending request to download Tailwind from cdn.tailwindcss.com...")
    r = requests.get(url, verify=False, timeout=15, proxies={"http": "", "https": ""})
    print(f"Status Code: {r.status_code}")
    print(f"Content Preview (first 200 chars): {r.text[:200]}")
    if r.status_code == 200 and not "html" in r.text[:100].lower():
        os.makedirs("static/js", exist_ok=True)
        with open("static/js/tailwind.min.js", "w", encoding="utf-8") as f:
            f.write(r.text)
        print("SUCCESS")
    else:
        print("FAILED: Content was HTML or status was not 200")
except Exception as e:
    print(f"ERROR: {e}")
