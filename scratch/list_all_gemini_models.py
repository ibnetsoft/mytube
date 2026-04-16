
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai

async def list_all_models():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("FAIL: No API Key found")
        return

    genai.configure(api_key=api_key)
    
    print("--- FULL MODEL LIST ---")
    try:
        # Get all models including restricted ones if possible
        for m in genai.list_models():
            print(f"Name: {m.name}")
            print(f"  Description: {m.description}")
            print(f"  Methods: {m.supported_generation_methods}")
            print("-" * 30)
    except Exception as e:
        print(f"Could not list models: {e}")

if __name__ == "__main__":
    asyncio.run(list_all_models())
