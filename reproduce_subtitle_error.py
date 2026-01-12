import os
import sys
import database as db
from config import config
import webvtt
import json

# Mocking the get_project_output_dir function from main.py
def get_project_output_dir(project_id: int):
    # This logic is copied from main.py for reproduction
    project = db.get_project(project_id)
    if not project:
        return config.OUTPUT_DIR, "/output"

    import re
    import datetime
    safe_name = re.sub(r'[\\/*?:"<>|]', "", project['name']).strip().replace(" ", "_")
    # Assuming 'today' logic matches what was used. 
    # For PID 10, the folder is "등산_20260106"
    today = "20260106" 
    folder_name = f"{safe_name}_{today}"
    
    abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
    web_path = f"/output/{folder_name}"
    return abs_path, web_path

def reproduce_get_subtitle(project_id):
    print(f"Testing get_subtitle for Project ID: {project_id}")
    try:
        tts_data = db.get_tts(project_id)
        if not tts_data:
            print("No TTS Data found.")
            return

        print(f"TTS Data: {tts_data}")
        audio_path = tts_data["audio_path"]
        vtt_path = audio_path.replace(".mp3", ".vtt")
        print(f"Audio Path: {audio_path}")
        print(f"VTT Path: {vtt_path}")
        
        subtitles = []
        
        # 1. Check existing JSON
        output_dir, web_dir = get_project_output_dir(project_id)
        print(f"Output Dir: {output_dir}")
        saved_sub_path = os.path.join(output_dir, f"subtitles_{project_id}.json")
        print(f"Saved Sub Path: {saved_sub_path}")
        
        if os.path.exists(saved_sub_path):
            print("Found existing subtitles JSON.")
            try:
                with open(saved_sub_path, "r", encoding="utf-8") as f:
                    subtitles = json.load(f)
            except Exception as e:
                print(f"Error loading JSON: {e}")
        
        # 2. Check VTT
        if not subtitles and os.path.exists(vtt_path):
            print("Parsing VTT...")
            try:
                for caption in webvtt.read(vtt_path):
                    subtitles.append({
                        "start": caption.start_in_seconds,
                        "end": caption.end_in_seconds,
                        "text": caption.text
                    })
                print(f"Parsed {len(subtitles)} subtitles from VTT.")
            except ImportError:
                print("webvtt not installed (ImportError)")
            except Exception as e:
                print(f"Error parsing VTT: {e}")
                import traceback
                traceback.print_exc()

        # 3. Audio URL Calculation (Potential Error Source)
        try:
            rel_path = os.path.relpath(audio_path, config.OUTPUT_DIR)
            audio_url = f"/output/{rel_path}".replace("\\", "/")
            print(f"Audio URL: {audio_url}")
        except ValueError as e:
            # os.path.relpath fails if paths are on different drives
            print(f"Relpath error: {e}")
            audio_url = f"/output/{os.path.basename(audio_path)}"

        # 4. Image Loading
        print("Loading images...")
        try:
            prompts = db.get_image_prompts(project_id)
            prompts.sort(key=lambda x: x.get('scene_number', 0))
            images = [p['image_url'] for p in prompts if p.get('image_url')]
            print(f"Found {len(images)} images.")
        except Exception as e:
            print(f"Error loading images: {e}")
            import traceback
            traceback.print_exc()
            
        print("Success.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce_get_subtitle(10)
