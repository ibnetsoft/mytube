import asyncio
import os
import sys
import httpx
import base64
from dotenv import load_dotenv

# Ensure we use UTF-8 output even on Windows command line
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add workspace directory to path
sys.path.append(os.path.abspath("."))

async def test():
    load_dotenv(override=True)
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("No ELEVENLABS_API_KEY found")
        return

    # Lily voice ID
    voice_id = "bIHbv24MWmeRgasZH58o"
    
    # We will test generating with eleven_multilingual_v2
    # text: standard Korean text with English pre-prompt to steer emotion
    text_with_prompt = "In a very sad, sobbing, and crying voice, the character says: 평생을 애써도 칭찬 한 번 못 들었다."
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    # We will set stability=0.05 and style=0.85 to make it EXTREMELY emotional
    payload = {
        "text": text_with_prompt,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.1,
            "similarity_boost": 0.75,
            "style": 0.85
        }
    }
    
    print("=== TESTING GENERATION WITH eleven_multilingual_v2 + ENGLISH PRE-PROMPT ===")
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            alignment = data.get("alignment", {})
            characters = alignment.get("characters", [])
            char_start_times = alignment.get("character_start_times_seconds", [])
            
            # Find crop index for "In a very sad, sobbing, and crying voice, the character says: "
            # Length of this prompt is 65 characters
            split_idx = len("In a very sad, sobbing, and crying voice, the character says: ")
            t_start = 0.0
            if characters and char_start_times:
                # search for first character of real text (평)
                first_char = "평"
                found_idx = -1
                for i in range(max(0, split_idx - 5), len(characters)):
                    if characters[i] == first_char:
                        found_idx = i
                        break
                if found_idx == -1:
                    found_idx = split_idx
                t_start = char_start_times[found_idx]
                
            print(f"Success! Pre-prompt length={split_idx}, crop start time={t_start:.3f}s")
            
            audio_base64 = data.get("audio_base64", "")
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                output_path = "output/test_sad_multilingual_v2.mp3"
                os.makedirs("output", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
                print(f"Saved raw audio to {output_path}")
        else:
            print("Failed with status:", response.status_code)
            print("Response:", response.text)

if __name__ == "__main__":
    asyncio.run(test())
