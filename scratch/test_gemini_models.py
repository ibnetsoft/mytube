
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai

async def test_nanobanana():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("FAIL: No API Key found")
        return

    genai.configure(api_key=api_key)
    
    # Try the model in the code
    model_name = "gemini-3.1-flash-image-preview"
    # Or common names
    other_models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "imagen-3.0-generate-001"
    ]
    
    print(f"Testing model: {model_name}")
    
    try:
        model = genai.GenerativeModel(model_name)
        # Simple test prompt
        response = await model.generate_content_async(
            "A cute banana wearing sunglasses"
        )
        print("SUCCESS!")
    except Exception as e:
        print(f"FAILED for {model_name}: {e}")

    # List available models
    print("\n--- Available Models ---")
    try:
        for m in genai.list_models():
            # Filter for models that supports image generation if possible
            # or just list all text/multimodal ones
            print(f"- {m.name} (Methods: {m.supported_generation_methods})")
    except Exception as e:
        print(f"Could not list models: {e}")

if __name__ == "__main__":
    asyncio.run(test_nanobanana())
