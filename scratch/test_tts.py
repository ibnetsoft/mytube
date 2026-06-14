import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.tts_service import tts_service

async def test():
    # 시어머니 대사 시뮬레이션
    text = "(한숨을 쉬며) 에휴... 내가 왜 그랬을까. (슬프게) 평생 고생만 한 며느리인데..."
    
    # 테스트 1: 안정도 0.0, 스타일 과장 1.0 (감정이 아주 강하게 실림)
    print("\n--- TEST 1: Stability 0.0, Style 1.0 ---")
    result_low = await tts_service.generate_elevenlabs(
        text, 
        filename="test_stability_0.mp3",
        voice_settings={"stability": 0.0, "style": 1.0}
    )
    print("Stability 0.0 Result path:", result_low.get("audio_path"))

    # 테스트 2: 안정도 1.0, 스타일 과장 0.0 (매우 차분하고 단조로움, 감정 무시)
    print("\n--- TEST 2: Stability 1.0, Style 0.0 ---")
    result_high = await tts_service.generate_elevenlabs(
        text, 
        filename="test_stability_1.mp3",
        voice_settings={"stability": 1.0, "style": 0.0}
    )
    print("Stability 1.0 Result path:", result_high.get("audio_path"))

if __name__ == "__main__":
    asyncio.run(test())
