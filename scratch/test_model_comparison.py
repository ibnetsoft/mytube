import asyncio
import os
import sys
import httpx
import re
from dotenv import load_dotenv

# Ensure UTF-8 output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

async def test_line(model_id, voice_id, text, emotion_map, pre_prompt_map):
    load_dotenv(override=True)
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("No ELEVENLABS_API_KEY found")
        return

    def replace_ko_emotions(match):
        content = match.group(1).strip()
        emotion_tag = ""
        for ko_key, en_tag in emotion_map.items():
            if ko_key in content:
                emotion_tag = f"[{en_tag}]"
                break
        return emotion_tag
        
    text_processed = re.sub(r'\(([^)]*)\)', replace_ko_emotions, text)
    
    emotion_tag_match = re.search(r'\[([a-zA-Z\s]+)\]', text_processed)
    prompt_text = ""
    cleaned_text = text_processed
    has_emotion_prompt = False
    
    if emotion_tag_match:
        tag_content = emotion_tag_match.group(1).lower().strip()
        if tag_content in pre_prompt_map:
            prompt_text = pre_prompt_map[tag_content]
            cleaned_text = text_processed.replace(emotion_tag_match.group(0), "").strip()
            has_emotion_prompt = True
            
    text_to_send = prompt_text + cleaned_text
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text_to_send,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.0,
            "similarity_boost": 0.75,
            "style": 1.0
        }
    }
    
    print(f"\n--- Model: {model_id} | Voice: {voice_id} | Text: {text} ---")
    print(f"Sent text: {text_to_send}")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            alignment = data.get("alignment", {})
            characters = alignment.get("characters", [])
            char_start_times = alignment.get("character_start_times_seconds", [])
            char_end_times = alignment.get("character_end_times_seconds", [])
            
            total_duration = char_end_times[-1] if char_end_times else 0.0
            print(f"Total Duration: {total_duration:.3f}s")
            
            # Find first real char
            split_idx = len(prompt_text)
            first_real_char = cleaned_text.strip()[0] if cleaned_text.strip() else ""
            found_idx = -1
            if first_real_char:
                start_search = max(0, split_idx - 5)
                for i in range(start_search, len(characters)):
                    if characters[i] == first_real_char:
                        found_idx = i
                        break
            if found_idx == -1:
                found_idx = split_idx
                
            t_start = char_start_times[found_idx] if 0 <= found_idx < len(char_start_times) else 0.0
            print(f"Split index: {split_idx}, Found index: {found_idx}")
            print(f"Calculated t_start: {t_start:.3f}s")
            
            if t_start >= total_duration - 0.2:
                print("⚠️ Crop safety triggered! t_start is too close to or exceeds total duration.")
            else:
                print("Crop is safe.")
        else:
            print("Failed:", response.text)

async def main():
    # Define emotion maps
    emotion_map = {
        "웃음": "happy",
        "진지": "thoughtful"
    }
    pre_prompt_map = {
        "happy": "In an extremely happy, cheerful, and laughing voice, they say: ",
        "thoughtful": "In a deep, serious, and thoughtful tone, they say: "
    }
    
    # We will use Laura voice (FGY2WhTYpPnrIDTdsKH5) for the happy line
    # Lily voice as default: bIHbv24MWmeRgasZH58o
    
    # First line: (헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?
    text1 = "(헛웃음 치며) 타격감이 완전 제로야. 세상 평온해 보이는데?"
    # Last line: (진지하게) 그리고 아프리카
    text2 = "(진지하게) 그리고 아프리카"
    
    laura = "FGY2WhTYpPnrIDTdsKH5"
    roger = "CwhRBWXzGAHq8TQ4Fs17"
    
    print("Testing line 1 with multilingual_v2")
    await test_line("eleven_multilingual_v2", laura, text1, emotion_map, pre_prompt_map)
    
    print("Testing line 1 with eleven_v3")
    await test_line("eleven_v3", laura, text1, emotion_map, pre_prompt_map)
    
    print("Testing line 2 with multilingual_v2")
    await test_line("eleven_multilingual_v2", roger, text2, emotion_map, pre_prompt_map)
    
    print("Testing line 2 with eleven_v3")
    await test_line("eleven_v3", roger, text2, emotion_map, pre_prompt_map)

if __name__ == "__main__":
    asyncio.run(main())
