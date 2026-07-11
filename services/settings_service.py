
import json
import os
from config import config

# [FIX] 이전에는 config.BASE_DIR(설치 폴더, PyInstaller 빌드에서는 exe가 있는
# 위치)를 기준으로 삼아, 신규 설치 환경에서 그 하위에 data/ 폴더가 아직 없으면
# "No such file or directory"로 저장이 실패했다 (주제 선택 -> db.create_project()
# 경로에서 그대로 사용자에게 노출됨). DB 등 나머지 사용자 데이터가 전부 쓰는
# config.DATA_DIR(%LOCALAPPDATA%\AIRStudio\data, 쓰기 가능이 보장되고 앱
# 업데이트로 설치 폴더가 교체돼도 유지됨)로 통일한다.
SETTINGS_FILE = os.path.join(config.DATA_DIR, "settings.json")

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
        except Exception:
            return {}

    def save_settings(self, settings: dict):
        # Determine existing to merge or overwrite?
        # Simple overwrite/merge logic
        current = self.get_settings()
        current.update(settings)

        # [FIX] open(path, "w")는 파일은 만들어도 없는 상위 디렉터리(data/)는
        # 만들지 않는다. 신규 설치 등 아직 data/ 폴더가 없는 환경에서 첫 저장
        # 시도 시 FileNotFoundError([Errno 2])가 그대로 호출부(예: 주제 선택 시
        # db.create_project() -> 이 함수)까지 전파되던 문제를 막는다.
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
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
