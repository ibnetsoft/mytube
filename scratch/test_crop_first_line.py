import asyncio
import os
import sys
import json
import base64
import httpx
import re
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

    # Laura voice ID
    voice_id = "FGY2WhTYpPnrIDTdsKH5"
    
    text = "(헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?"
    
    # Let's simulate tts_service behavior
    EMOTION_MAP = {
        "웃음": "happy"
    }
    
    PRE_PROMPT_MAP = {
        "happy": "In an extremely happy, cheerful, and laughing voice, they say: "
    }
    
    def replace_ko_emotions(match):
        content = match.group(1).strip()
        emotion_tag = ""
        for ko_key, en_tag in EMOTION_MAP.items():
            if ko_key in content:
                emotion_tag = f"[{en_tag}]"
                break
        return emotion_tag
        
    text_processed = re.sub(r'\(([^)]*)\)', replace_ko_emotions, text)
    print("Processed text:", text_processed)
    
    emotion_tag_match = re.search(r'\[([a-zA-Z\s]+)\]', text_processed)
    prompt_text = ""
    cleaned_text = text_processed
    has_emotion_prompt = False
    
    if emotion_tag_match:
        tag_content = emotion_tag_match.group(1).lower().strip()
        if tag_content in PRE_PROMPT_MAP:
            prompt_text = PRE_PROMPT_MAP[tag_content]
            cleaned_text = text_processed.replace(emotion_tag_match.group(0), "").strip()
            has_emotion_prompt = True
            
    text_to_send = prompt_text + cleaned_text
    print("Text to send:", text_to_send)
    print("Cleaned text (Korean):", cleaned_text)
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text_to_send,
        "model_id": "eleven_v3", # Test with eleven_v3!
        "voice_settings": {
            "stability": 0.0,
            "similarity_boost": 0.75,
            "style": 1.0
        }
    }
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            alignment = data.get("alignment", {})
            characters = alignment.get("characters", [])
            char_start_times = alignment.get("character_start_times_seconds", [])
            char_end_times = alignment.get("character_end_times_seconds", [])
            
            print(f"Alignment data: characters length={len(characters)}, start times length={len(char_start_times)}")
            
            # Print characters around split point
            split_idx = len(prompt_text)
            print(f"Split index: {split_idx}")
            
            # Print last 15 chars of pre-prompt and first 15 chars of Korean in the characters alignment list
            for idx in range(max(0, split_idx - 15), min(len(characters), split_idx + 15)):
                print(f"Index {idx}: Character='{characters[idx]}', Start={char_start_times[idx]:.3f}s")
                
            first_real_char = cleaned_text.strip()[0] if cleaned_text.strip() else ""
            print(f"First real char search: '{first_real_char}'")
            found_idx = -1
            if first_real_char:
                start_search = max(0, split_idx - 5)
                for i in range(start_search, len(characters)):
                    if characters[i] == first_real_char:
                        found_idx = i
                        break
            
            print(f"Found index: {found_idx}")
            if found_idx == -1:
                found_idx = split_idx
                
            t_start = char_start_times[found_idx] if 0 <= found_idx < len(char_start_times) else 0.0
            print(f"Calculated t_start: {t_start:.3f}s")
            
            # Check if total duration is less than t_start
            total_duration = char_end_times[-1] if char_end_times else 0.0
            print(f"Total duration from alignment: {total_duration:.3f}s")
            
            if t_start >= total_duration:
                print("⚠️ WARNING: t_start is GREATER than or equal to total duration! This will result in an EMPTY audio file!")
            else:
                print("t_start is safe.")
        else:
            print("Failed:", response.text)

if __name__ == "__main__":
    asyncio.run(test())
