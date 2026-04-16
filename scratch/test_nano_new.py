
import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types

async def test_nanobanana_new_sdk():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("FAIL: No API Key")
        return

    # Initialize the client with the NEW SDK
    client = genai.Client(api_key=api_key)
    
    model_name = "gemini-3.1-flash-image-preview"
    prompt = "A high-quality 2D anime style image of a cute banana wearing sunglasses"
    
    print(f"Testing model with NEW SDK: {model_name}")
    
    try:
        # Generate the content with the NEW response_modalities
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
        
        print("SUCCESS! Model responded.")
        
        # Check for image data in candidates
        img_found = False
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data:
                    print(f"✅ Found Image Data! Size: {len(part.inline_data.data)} bytes")
                    img_found = True
                    # Optional: save to check
                    # with open("scratch/test_nano.png", "wb") as f:
                    #     f.write(part.inline_data.data)
        
        if not img_found:
            print("❌ No image data found in response parts.")
            print(f"Response parts: {[type(p) for p in response.candidates[0].content.parts]}")
            
    except Exception as e:
        print(f"FAILED for {model_name} with NEW SDK: {e}")

if __name__ == "__main__":
    asyncio.run(test_nanobanana_new_sdk())
