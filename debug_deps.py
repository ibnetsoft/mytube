
import asyncio
import os
import sys

# Mock config
class Config:
    OUTPUT_DIR = "output"
    GEMINI_API_KEY = "dummy"
    ELEVENLABS_API_KEY = "dummy"
    TYPECAST_API_KEY = "dummy"
    GOOGLE_APPLICATION_CREDENTIALS = "dummy"
    TEMPLATES_DIR = "templates"
    STATIC_DIR = "static"
    YOUTUBE_API_KEY = "dummy"
    YOUTUBE_BASE_URL = "dummy"
    GEMINI_URL = "dummy"

sys.modules["config"] = type("config_module", (), {"config": Config()})

async def test_edge_tts():
    print("Testing Edge TTS...")
    try:
        import edge_tts
        print("edge_tts imported successfully.")
        
        text = "안녕하세요. 이것은 테스트 음성입니다."
        voice = "ko-KR-SunHiNeural"
        communicate = edge_tts.Communicate(text, voice)
        
        output_path = "test_tts.mp3"
        with open(output_path, "wb") as file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    file.write(chunk["data"])
                    
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"TTS generated successfully: {output_path} ({os.path.getsize(output_path)} bytes)")
        else:
            print("TTS generation failed: File empty or not found.")
            
    except ImportError:
        print("edge_tts not installed.")
    except Exception as e:
        print(f"TTS Error: {e}")

def test_moviepy():
    print("\nTesting MoviePy...")
    try:
        from moviepy.editor import ColorClip
        print("moviepy imported successfully.")
        
        clip = ColorClip(size=(100, 100), color=(255, 0, 0), duration=2)
        clip.fps = 24
        output_path = "test_video.mp4"
        clip.write_videofile(output_path, logger=None) # suppress logger
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
             print(f"Video generated successfully: {output_path} ({os.path.getsize(output_path)} bytes)")
        else:
             print("Video generation failed.")
             
    except ImportError:
        print("moviepy not installed.")
    except Exception as e:
        print(f"MoviePy Error: {e}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_edge_tts())
    test_moviepy()
