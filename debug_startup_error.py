
from fastapi.testclient import TestClient
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

try:
    from main import app
    client = TestClient(app)
    
    print("Attempting to GET /")
    response = client.get("/")
    print(f"Status Code: {response.status_code}")
    if response.status_code != 200:
        print("Response Text (Error contents):")
        print(response.text)
except Exception as e:
    import traceback
    print("Exception during import or request:")
    traceback.print_exc()
