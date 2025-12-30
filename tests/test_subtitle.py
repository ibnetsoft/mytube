import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tts_service import tts_service
from config import config

async def test_subtitle_generation():
    print("--- Subtitle Generation Test ---")
    
    # 1. Generate TTS
    text = "안녕하세요. 이것은 자막 생성 테스트입니다. 잘 작동하나요?"
    filename = "test_subtitle_audio.mp3"
    print(f"Generating TTS for text: '{text}'")
    
    # Use generate_edge_tts directly as it's the core engine we modified
    output_path = await tts_service.generate_edge_tts(
        text=text,
        voice="ko-KR-SunHiNeural",
        filename=filename
    )
    
    if not output_path or not os.path.exists(output_path):
        print("❌ Error: Audio file generation failed.")
        return

    print(f"✅ Audio generated: {output_path}")

    # 2. Check VTT file
    vtt_path = output_path.replace(".mp3", ".vtt")
    if os.path.exists(vtt_path):
        print(f"✅ VTT file found: {vtt_path}")
        
        print("\n--- VTT Content ---")
        with open(vtt_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(content)
        print("-------------------\n")
        
        # 3. Test Parsing (Simulate main.py logic)
        try:
            import webvtt
            print("Testing webvtt parsing...")
            count = 0
            for caption in webvtt.read(vtt_path):
                print(f"[{caption.start} --> {caption.end}]: {caption.text}")
                count += 1
            print(f"✅ Parsed {count} subtitle lines successfully.")
        except ImportError:
            print("⚠️ webvtt-py library not found. Skipping parse test.")
        except Exception as e:
            print(f"❌ Parsing failed: {e}")

    else:
        print("❌ Error: VTT file was NOT generated.")
        
    # Cleanup
    # try:
    #     os.remove(output_path)
    #     if os.path.exists(vtt_path):
    #         os.remove(vtt_path)
    # except:
    #     pass

if __name__ == "__main__":
    asyncio.run(test_subtitle_generation())
