"""
Test Imagen 4 API response structure
"""
import asyncio
import httpx
import sys
import os

sys.path.append(os.getcwd())

from config import config

async def test_imagen():
    api_key = config.GEMINI_API_KEY
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    models_to_test = [
        "imagen-4.0-generate-001",
        "imagen-4.0-fast-generate-001",
    ]
    
    test_prompt = "A highly realistic photo of a modern office"
    
    for model_name in models_to_test:
        print(f"\n{'='*60}")
        print(f"Testing model: {model_name}")
        print(f"{'='*60}")
        
        url = f"{base_url}/models/{model_name}:predict?key={api_key}"
        
        payload = {
            "instances": [{"prompt": test_prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "16:9",
                "safetySetting": "block_low_and_above"
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                print(f"Sending request to: {url[:80]}...")
                response = await client.post(url, json=payload)
                
                print(f"Status Code: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"Response keys: {list(result.keys())}")
                    
                    if "predictions" in result:
                        print(f"✅ Has 'predictions' key")
                        print(f"Predictions count: {len(result['predictions'])}")
                        if result['predictions']:
                            pred = result['predictions'][0]
                            print(f"First prediction keys: {list(pred.keys())}")
                            if 'bytesBase64Encoded' in pred:
                                print(f"✅ Has 'bytesBase64Encoded'")
                                print(f"Image data length: {len(pred['bytesBase64Encoded'])} chars")
                            else:
                                print(f"❌ No 'bytesBase64Encoded', available keys: {pred.keys()}")
                    else:
                        print(f"❌ No 'predictions' key")
                        print(f"Full response: {result}")
                    
                    print(f"✅ SUCCESS with {model_name}")
                    break  # Found working model
                    
                else:
                    print(f"❌ Error: {response.status_code}")
                    print(f"Response: {response.text[:500]}")
                    
        except Exception as e:
            print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_imagen())
