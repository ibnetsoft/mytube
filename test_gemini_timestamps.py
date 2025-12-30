
import asyncio
import os
from google import genai
from config import config

async def test_gemini_timestamps():
    if not config.GEMINI_API_KEY:
        print("No API Key")
        return

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    # 1. Create a dummy audio or use existing if any.
    # Since I don't have a guaranteed audio file, I'll assume one exists or skip.
    # Actually, let's create a quick TTS file first using the existing tts logic or just a placeholder if file exists.
    # I'll just check if 'output/tts_output.mp3' exists from previous runs.
    
    audio_path = os.path.join(config.OUTPUT_DIR, "intro.mp3") # Hypothetical file
    if not os.path.exists(audio_path):
        # Try to find ANY mp3 in output
        files = [f for f in os.listdir(config.OUTPUT_DIR) if f.endswith('.mp3')]
        if not files:
            print("No audio file found to test.")
            return
        audio_path = os.path.join(config.OUTPUT_DIR, files[0])
    
    print(f"Testing with file: {audio_path}")
    
    try:
        # Upload
        vid_file = client.files.upload(file=audio_path)
        print(f"Uploaded file: {vid_file.name}")
        
        # Wait for processing
        import time
        while True:
            file_meta = client.files.get(name=vid_file.name)
            if file_meta.state.name == "ACTIVE":
                print("File is ACTIVE")
                break
            elif file_meta.state.name == "FAILED":
                print("File processing FAILED")
                return
            print("Waiting for file processing...")
            time.sleep(1)
        
        # Prompt
        prompt = """
        Listen to this audio and transcribe it.
        Crucially, provide the start and end timestamp for EACH sentence.
        Format the output strictly as a JSON list of objects:
        [
            {"text": "Sentence 1", "start": 0.0, "end": 2.5},
            ...
        ]
        RETURN ONLY JSON.
        """
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[vid_file, prompt]
        )
        
        print("Response:")
        print(response.text)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini_timestamps())
