
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
                 },
                 "script_styles": {
                     "news": "당신은 전문 뉴스 앵커입니다. 사실에 기반하여 객관적이고 신뢰감 있는 톤으로 소식을 전달하세요. 정확한 정보를 구조적으로 설명해야 합니다.",
                     "story": "당신은 구수한 입담을 가진 이야기꾼입니다. 전래동화나 역사 이야기를 들려주듯 몰입감 있고 흥미진진하게 이야기를 전개하세요. 청중이 이야기에 푹 빠져들 수 있도록 묘사와 감정을 풍부하게 사용하세요."
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
