
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai

async def test_live_preview_image():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    
    # Try the model that IS in the list
    model_name = "gemini-3.1-flash-live-preview"
    print(f"Testing model: {model_name}")
    
    try:
        model = genai.GenerativeModel(model_name)
        # Use v1beta generateContent
        # Note: Some live models require specific config or might not support standard image gen
        response = await model.generate_content_async(
            "Generate a high-quality 2D anime style image of a cute banana wearing sunglasses"
        )
        print("SUCCESS!")
        # Check if there are image parts
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') or hasattr(part, 'file_data'):
                    print("Found image data!")
                else:
                    print(f"Part type: {type(part)}")
                    print(f"Text: {part.text[:50]}...")
    except Exception as e:
        print(f"FAILED for {model_name}: {e}")

if __name__ == "__main__":
    asyncio.run(test_live_preview_image())
