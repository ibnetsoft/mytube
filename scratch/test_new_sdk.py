
import os
from dotenv import load_dotenv
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("google-genai not installed or import error")
    exit(1)

def test_new_sdk_models():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("FAIL: No API Key")
        return

    client = genai.Client(api_key=api_key)
    
    print("--- NEW SDK MODEL LIST ---")
    try:
        # The new SDK has a different way to list models
        for m in client.models.list():
            print(f"Name: {m.name}")
            # print(f"  Capabilities: {m.supported_actions}")
            print("-" * 20)
            
        # Try generate image with NanoBanana if possible
        # Check if 3.1-flash-image exists in the list first
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_new_sdk_models()
