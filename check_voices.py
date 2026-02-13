import asyncio
import os
import sys

# 현재 디렉토리를 path에 추가하여 모듈 import 가능하게 함
sys.path.append(os.getcwd())

from services.tts_service import tts_service

async def main():
    print("Checking ElevenLabs API key...", end=" ")
    if tts_service.elevenlabs_key:
        print("OK")
    else:
        print("MISSING")
        return

    print("Fetching voice list from ElevenLabs...", end=" ")
    try:
        voices = await tts_service.get_elevenlabs_voices()
        print(f"Done. Found {len(voices)} voices.")
        
        print("\n[Voice List Summary]")
        print(f"{'Name':<20} {'Gender':<10} {'Category':<15} {'Voice ID'}")
        print("-" * 60)
        
        counts = {'male': 0, 'female': 0, 'other': 0}
        
        for v in voices:
            name = v.get('name', 'Unknown')[:18]
            labels = v.get('labels', {})
            gender = labels.get('gender', 'N/A')
            category = v.get('category', 'N/A')
            voice_id = v.get('voice_id')
            
            print(f"{name:<20} {gender:<10} {category:<15} {voice_id}")
            
            if gender == 'male': counts['male'] += 1
            elif gender == 'female': counts['female'] += 1
            else: counts['other'] += 1
            
        print("-" * 60)
        print(f"Total: {len(voices)} (Male: {counts['male']}, Female: {counts['female']}, Other: {counts['other']})")
        
    except Exception as e:
        print(f"\nError fetching voices: {e}")

if __name__ == "__main__":
    asyncio.run(main())
