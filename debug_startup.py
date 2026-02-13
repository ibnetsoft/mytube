try:
    print("Importing main...")
    import main
    print("Main imported successfully.")
    
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    
    print("Requesting /webtoon...")
    response = client.get("/webtoon")
    print(f"Status: {response.status_code}")
    if response.status_code == 500:
        print("Body:")
        print(response.text)
    else:
        print("Success or other status.")
except Exception as e:
    print(f"Startup error: {e}")
    import traceback
    traceback.print_exc()
