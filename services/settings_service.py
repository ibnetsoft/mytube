
import json
import os
from config import config

SETTINGS_FILE = os.path.join(config.BASE_DIR, "data", "settings.json")

class SettingsService:
    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(SETTINGS_FILE):
             default_settings = {
                 "gemini_tts": {
                     "voice_name": "Puck",
                     "language_code": "ko-KR",
                     "style_prompt": ""
                 }
             }
             self.save_settings(default_settings)

    def get_settings(self) -> dict:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save_settings(self, settings: dict):
        # Determine existing to merge or overwrite?
        # Simple overwrite/merge logic
        current = self.get_settings()
        current.update(settings)
        
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)

    def get_gemini_tts_settings(self):
        settings = self.get_settings()
        return settings.get("gemini_tts", {
             "voice_name": "Puck",
             "language_code": "ko-KR",
             "style_prompt": ""
        })

settings_service = SettingsService()
