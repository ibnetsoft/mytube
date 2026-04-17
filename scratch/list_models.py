
import asyncio
import httpx
import os
from config import config
from services.auth_service import auth_service

async def list_models():
    auth_service.verify_license()
    api_key = config.GEMINI_API_KEY
    if not api_key:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("No API Key found.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"Available models ({len(models)}):")
            for m in models:
                print(f"- {m['name']} (Supported: {m['supportedGenerationMethods']})")
        else:
            print(f"Failed to list models: {response.status_code} - {response.text}")

if __name__ == "__main__":
    asyncio.run(list_models())
