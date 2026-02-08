from services.gemini_service import gemini_service
import asyncio

async def test():
    try:
        res = await gemini_service.generate_text("Hello, who are you?")
        print(f"Gemini Response: {res}")
    except Exception as e:
        print(f"Gemini Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
