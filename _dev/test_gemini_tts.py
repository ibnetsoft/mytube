
import os
import asyncio
import httpx
import base64
from dotenv import load_dotenv
from google import genai

load_dotenv()


async def test_gemini_tts():
    api_key = os.getenv("GEMINI_API_KEY")
    # Try the specific TTS preview model
    model = "gemini-2.5-flash-preview-tts" 
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": "안녕하세요. 이것은 제미나이 2.5 TTS 모델 테스트입니다."}]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": "Puck"
                    }
                }
            }
        }
    }
    
    print(f"Testing model: {model}")
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            try:
                # Structure might be different or same
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "inlineData" in parts[0]:
                        audio_data = parts[0]["inlineData"]["data"]
                        with open(f"gemini_tts_{model}.wav", "wb") as f:
                            f.write(base64.b64decode(audio_data))
                        print(f"Success! Saved gemini_tts_{model}.wav")
                    else:
                        print("No inlineData in parts")
                        print(data)
                else:
                    print("No candidates")
                    print(data)
            except Exception as e:
                print(f"Failed to parse audio: {e}")
                print(data)
        else:
            print(f"Error: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_gemini_tts())
