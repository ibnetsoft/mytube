
import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from services.gemini_service import gemini_service
from config import config

async def test():
    print("Testing generate_image_prompts_from_script...")
    script = """
    5초 안에 빵 터짐 보장! 오늘, 당신의 웃음 책임집니다!
    (화려한 척 뽐내며) 나는야 완벽한 커리어우먼! 칼퇴? 그게 뭔데요?
    (갑자기 헝클어진 머리, 퀭한 눈) 8시 59분 59초... 땡! 퇴근!!!
    """
    try:
        prompts = await gemini_service.generate_image_prompts_from_script(script, 50)
        print(f"Result Count: {len(prompts)}")
        for i, p in enumerate(prompts):
            print(f"Scene {i+1}: {p.get('prompt_en')[:50]}...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
