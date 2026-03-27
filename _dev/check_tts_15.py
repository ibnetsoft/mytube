
import database as db

try:
    t = db.get_tts(15)
    print(f"TTS Data for 15: {t}")
except Exception as e:
    print(f"Error: {e}")
